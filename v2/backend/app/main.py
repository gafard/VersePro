"""
VersePro v2 - Backend Principal
Architecture moderne avec FastAPI + WebSocket pour streaming temps réel, multi-traduction,
projection autonome et fallback hors-ligne Vosk local ultra-léger et robuste.
"""

import asyncio
import json
import os
import re
import sys
import subprocess
import threading
import time

# Autorités TLS de l'application figée.
#
# Cette ligne remplace un « ssl._create_default_https_context =
# ssl._create_unverified_context » qui désactivait la vérification des
# certificats pour TOUT le processus — bibliothèques tierces comprises. Le
# symptôme qu'il masquait est réel : empaquetée par PyInstaller, l'application
# n'a pas de magasin d'autorités et le moindre téléchargement échoue en
# CERTIFICATE_VERIFY_FAILED. Mais la réponse était pire que le mal : un modèle
# de reconnaissance vocale est du code qui s'exécutera sur le poste de
# l'église, et l'accepter sans vérifier revient à laisser un intermédiaire le
# remplacer.
#
# On fournit donc de VRAIES autorités, celles de certifi embarquées dans le
# gel, à toutes les bibliothèques d'un coup — et la vérification reste active.
try:
    import certifi
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
except Exception:  # pragma: no cover - certifi absent : magasin système
    pass

from typing import Any, Dict, List, Optional
from contextlib import asynccontextmanager, suppress

import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from loguru import logger
import uvicorn

from .core.config import settings, RESOURCE_DIR
from .core.security import http_request_allowed, websocket_allowed, websocket_subprotocol
from .services.deepgram_service import DeepgramService
from .services.verse_parser import VerseParserService, version_label
from .services.reference_engine import BibleReferenceEngine, DEDUPLICATION_SECONDS
from .services.database import DatabaseService, get_database
from .services.vosk_service import VoskService
from .services.nemotron_service import NemotronService
from .services.ai_service import AIService
from .services.semantic_search import LocalSemanticService
from .services.verse_graph import VerseGraphService
from .services.transcription_health import SanteTranscription
from .services.detection_fusion import fuse as fuse_detection, strip_attribution, recent_window
from .services.reading_tracker import ReadingTracker
from .services.secret_store import secret_store
from .services import overlay_store, background_store
from .outputs import OutputManager
from .api.routes import router as api_router


# Services globaux
deepgram_service: DeepgramService | None = None
output_manager: OutputManager | None = None
verse_parser: VerseParserService | None = None
db_service: DatabaseService | None = None
vosk_service: VoskService | None = None
nemotron_service: NemotronService | None = None
ai_service: AIService | None = None
semantic_service: LocalSemanticService | None = None
verse_graph: VerseGraphService | None = None

reference_engine: BibleReferenceEngine | None = None
sante_transcription: SanteTranscription = SanteTranscription()
current_session_id: int | None = None
osc_service: Any = None

# Connexions et état de projection
projector_connections = set()

# Lecture vivante : position de la voix du prédicateur dans le verset projeté
reading_tracker = ReadingTracker()

async def broadcast_output_event(payload: dict):
    """Diffuse un événement léger, ou redessine une scène annotée sur NDI."""
    if output_manager:
        browser = output_manager.outputs.get("browser")
        if browser:
            await browser.broadcast_event(payload)
        # Les annotations modifient aussi les sorties qui rendent une image
        # (NDI). On les rattache à la scène courante puis on la reprojette : le
        # navigateur reçoit son événement léger et NDI redessine la même zone
        # sur la trame BGRA.
        if payload.get("type") == "annotation":
            current_projection_slide["annotations"] = list(payload.get("annotations") or [])
            await output_manager.project_scene(dict(current_projection_slide))
current_projection_slide = {
    "text": "En attente d'affichage...",
    "reference": "",
    "background": "black",
    "theme": "classic",
    "translations": {}
}

# Ce que l'opérateur PRÉPARE, distinct de ce qui est à l'antenne. Vide tant
# qu'il n'a rien monté. Aucune sortie autre que la console ne le voit.
preview_slide: dict = {}

async def _lookup_next_verse(reference: str) -> tuple[str, str]:
    """Texte du verset suivant (pré-affiché sur le moniteur prédicateur)"""
    try:
        if not verse_parser or not reference:
            return "", ""
        parsed = await verse_parser.parse(reference, skip_text_search=True)
        if not parsed or parsed.get("verse_start") is None:
            return "", ""
        # Pour un passage (ex. Jean 3:16-18), « suivant » désigne le
        # deuxième verset du passage, pas le verset 19. L'écran de sortie
        # pagine ensuite le reste ; la télécommande et la commande vocale
        # doivent suivre le même ordre.
        next_v = parsed["verse_start"] + 1
        text = verse_parser.bible_loader.get_verse_text(parsed["book_abbr"], parsed["chapter"], next_v)
        if not text:
            return "", ""
        return f"{parsed['book_abbr']} {parsed['chapter']}:{next_v}", text
    except Exception:
        return "", ""


async def broadcast_projection(
    text: str,
    reference: str,
    background: str | None = None,
    translations: dict | None = None,
    theme: str | None = None,
    version: str | None = None,
):
    """Diffuse le slide à tous les projecteurs et suiveurs connectés via OutputManager"""
    global current_projection_slide

    cur_version = (
        (version or "").strip().upper()
        or (verse_parser.bible_loader.active_version if verse_parser and verse_parser.bible_loader else None)
        or settings.BIBLE_VERSION
    )

    next_ref, next_text = await _lookup_next_verse(reference)
    
    book = None
    chapter = None
    verse_start = None
    verse_end = None
    # Initialisé ici : effacer l'écran appelle cette fonction SANS référence,
    # et le découpage en versets plus bas lit `parsed` dans tous les cas.
    parsed = None
    if reference and verse_parser:
        parsed = await verse_parser.parse(reference, skip_text_search=True)
        if parsed:
            book = parsed.get("book")
            chapter = parsed.get("chapter")
            verse_start = parsed.get("verse_start")
            verse_end = parsed.get("verse_end")

    # Passage de plusieurs versets : on envoie les versets UN À UN plutôt qu'un
    # bloc collé. L'écran affiche le premier et attend — un lower-third n'a pas
    # la place pour douze versets, et les entasser obligerait à réduire la
    # police jusqu'à l'illisible. Le découpage se fait ici parce que c'est ici
    # qu'on connaît les frontières de versets : le texte assemblé, lui, ne les
    # porte plus.
    versets_pages = []
    if (verse_parser and parsed and verse_end and verse_start
            and verse_end > verse_start):
        loader = verse_parser.bible_loader
        for numero in range(int(verse_start), int(verse_end) + 1):
            morceau = loader.get_verse_text(parsed.get("book_abbr"), chapter, numero, None, version_id=cur_version)
            if (morceau or "").strip():
                versets_pages.append({"n": numero, "text": morceau.strip()})
        # Un seul verset retrouvé : autant garder le texte d'origine.
        if len(versets_pages) < 2:
            versets_pages = []

    current_projection_slide = {
        "text": text,
        "reference": reference,
        "book": book,
        "chapter": chapter,
        "verse_start": verse_start,
        "verse_end": verse_end,
        # Vide pour un verset seul ; sinon la liste des versets du passage,
        # que l'écran affiche un par un.
        "verses": versets_pages,
        "background": background or current_projection_slide.get("background", "black"),
        "theme": theme or current_projection_slide.get("theme", "presentation"),
        "translations": translations or {},
        "next_reference": next_ref,
        "next_text": next_text,
        "active_version": cur_version,
        "active_version_label": version_label(cur_version),
        "active_version_short": version_label(cur_version, short=True),
        "show_version": settings.SHOW_BIBLE_VERSION,
        "style": settings.PROJECTION_STYLE,
        "dual_translations": settings.DUAL_TRANSLATIONS,
        "backdrop": background_store.resolve_background(settings),
        # Habillage personnalisé : l'écran n'a besoin que de savoir qu'une image
        # existe, de sa version (anti-cache) et de l'emplacement des textes.
        # Un style « habillage:xxx » désigne un habillage de la bibliothèque ;
        # sinon l'écran reçoit celui en cours d'édition.
        "overlay": overlay_store.resolve_overlay(
            settings.PROJECTION_STYLE, settings.OVERLAY_ZONES, settings.OVERLAY_SHAPES
        ),
    }

    # Nouveau verset à l'écran : la lecture vivante repart de zéro
    reading_tracker.set_verse(text if reference else "")

    if output_manager:
        return await output_manager.project_scene(current_projection_slide)
    return {}


async def preparer_projection(text: str, reference: str, translations: dict | None = None):
    """Monte une scène en PRÉPARATION, sans rien envoyer à la salle.

    Le geste fondamental d'une régie : voir l'écran avant qu'il y soit. Avant
    ça, valider une détection l'envoyait directement devant l'assemblée —
    l'opérateur découvrait le rendu en même temps qu'elle.
    """
    global preview_slide
    if not output_manager:
        return {}
    browser = output_manager.outputs.get("browser")
    if not browser:
        return {}

    versets = []
    numero_debut = None
    if reference and verse_parser:
        analyse = await verse_parser.parse(reference, skip_text_search=True)
        if analyse:
            numero_debut = analyse.get("verse_start")
            fin = analyse.get("verse_end")
            if fin and numero_debut and fin > numero_debut:
                loader = verse_parser.bible_loader
                for n in range(int(numero_debut), int(fin) + 1):
                    morceau = loader.get_verse_text(analyse.get("book_abbr"),
                                                    analyse.get("chapter"), n, None)
                    if (morceau or "").strip():
                        versets.append({"n": n, "text": morceau.strip()})
                if len(versets) < 2:
                    versets = []

    preview_slide = {
        "type": "scripture",
        "text": text,
        "reference": reference,
        "verse_start": numero_debut,
        "verses": versets,
        "translations": translations or {},
        "background": current_projection_slide.get("background", "black"),
        "theme": current_projection_slide.get("theme", "presentation"),
        "style": settings.PROJECTION_STYLE,
        "show_version": settings.SHOW_BIBLE_VERSION,
        "active_version": settings.BIBLE_VERSION,
        "backdrop": background_store.resolve_background(settings),
    }
    await browser.send_preview(preview_slide)
    return preview_slide


async def envoyer_preparation():
    """Envoie à l'antenne ce qui est en préparation. Le « take » d'une régie."""
    if not preview_slide.get("reference") and not preview_slide.get("text"):
        return None
    receipts = await broadcast_projection(
        preview_slide.get("text", ""),
        preview_slide.get("reference", ""),
        translations=preview_slide.get("translations"),
    )
    return receipts


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestion du cycle de vie de l'application"""
    global deepgram_service, output_manager, verse_parser, db_service, vosk_service, nemotron_service, ai_service, semantic_service, verse_graph, reference_engine, current_session_id, osc_service
    
    # Startup
    logger.info("🚀 Démarrage de VersePro v2...")
    
    # Initialisation de la base de données
    db_service = get_database()
    await db_service.connect()

    # Les clés historiques stockées dans SQLite sont transférées vers le
    # Trousseau macOS (ou le gestionnaire de secrets de l'OS), puis effacées.
    await secret_store.migrate_from_database(db_service)
    for secret_key, attr_name in {
        "deepgram_api_key": "DEEPGRAM_API_KEY",
        "openrouter_api_key": "OPENROUTER_API_KEY",
        "gemini_api_key": "GEMINI_API_KEY",
    }.items():
        if not getattr(settings, attr_name, ""):
            stored_secret = await secret_store.get(secret_key)
            if stored_secret:
                setattr(settings, attr_name, stored_secret)
    
    # Charger la configuration dynamique depuis SQLite
    stored_settings = await db_service.get_all_settings()
    for key, val in stored_settings.items():
        attr_name = key.upper()
        if hasattr(settings, attr_name):
            expected_type = type(getattr(settings, attr_name))
            try:
                if expected_type is bool:
                    typed_val = val.lower() in ("true", "1", "yes")
                else:
                    typed_val = expected_type(val)
                setattr(settings, attr_name, typed_val)
                # Les secrets ne doivent JAMAIS apparaître en clair dans les logs
                # (fichiers de log, rapports de bug, captures d'écran…).
                shown = "•••" if any(m in attr_name.upper() for m in ("KEY", "TOKEN", "SECRET", "PASSWORD")) else typed_val
                logger.info(f"⚙️ Config chargée depuis SQLite : {attr_name} = {shown}")
            except Exception as e:
                logger.error(f"Impossible de convertir {key}={val} en {expected_type}: {e}")

    # Migration : 12345 était l'ancien port par défaut, hérité d'un protocole
    # maison que ProPresenter n'a jamais parlé. Les postes déjà configurés le
    # gardent en base et resteraient muets ; on les ramène au port officiel.
                logger.warning(f"Impossible de restaurer le paramètre {key} ({val}) : {e}")
                
    # Initialisation des autres services avec la config SQLite chargée
    deepgram_service = DeepgramService(settings.DEEPGRAM_API_KEY)
    
    # Initialisation d'OutputManager avec ses drivers
    output_manager = OutputManager()
    await output_manager.initialize_defaults()
    
    verse_parser = VerseParserService()
    vosk_service = VoskService()
    nemotron_service = NemotronService()
    ai_service = AIService()
    semantic_service = LocalSemanticService(verse_parser.bible_loader)
    verse_graph = VerseGraphService(semantic_service)
    
    # Instanciation du moteur de référence (accessible au niveau global)
    reference_engine = BibleReferenceEngine(
        verse_parser=verse_parser,
        semantic_service=semantic_service,
        verse_graph=verse_graph,
        ai_service=ai_service,
        settings=settings,
        db_service=db_service,
        sante_transcription=sante_transcription
    )
    
    # Ne télécharge rien au démarrage. Un modèle Nemotron ou Vosk déjà présent est seulement
    # chargé en arrière-plan; les installations restent des actions explicites.
    if os.environ.get("VERSEPRO_TESTING") != "1":
        if nemotron_service.is_ready:
            logger.info("🎙️ Pré-chargement de Nemotron 3.5-ASR en arrière-plan...")
            threading.Thread(target=nemotron_service.prewarm, daemon=True).start()
        elif Path(vosk_service.model_dir).exists():
            logger.info("🎙️ Nemotron indisponible, initialisation du moteur de secours Vosk...")
            threading.Thread(target=vosk_service.initialize, daemon=True).start()
        threading.Thread(
            target=semantic_service.initialize,
            kwargs={"allow_download": settings.LOCAL_SEMANTIC_AUTO_DOWNLOAD},
            daemon=True,
        ).start()
    
    # Démarrage du service OSC pour le pilotage à distance (Stream Deck, Companion)
    from .services.osc_service import OSCService
    osc_service = OSCService()
    await osc_service.start()
    
    logger.info("✅ Services initialisés")
    
    yield
    
    # Shutdown
    logger.info("🛑 Arrêt de VersePro v2...")
    from .services.companion import companion
    await companion.stop()
    from .api.launch import cleanup_kits
    await cleanup_kits()
    if osc_service:
        await osc_service.stop()
    if deepgram_service:
        await deepgram_service.disconnect()
    if output_manager:
        await output_manager.disconnect_all()
    if db_service:
        await db_service.disconnect()


app = FastAPI(
    title="VersePro v2",
    description="Détection automatique de versets bibliques avec IA",
    version="2.1.9",
    lifespan=lifespan
)

# CORS pour le frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Contrôle d'accès : les clients distants (LAN) doivent fournir API_TOKEN,
# sauf pour l'écran de projection qui reste public (voir core/security.py)
@app.middleware("http")
async def access_control_middleware(request, call_next):
    if not http_request_allowed(request):
        return JSONResponse(
            status_code=401,
            content={"detail": "Accès refusé : jeton API requis pour les clients distants (Authorization: Bearer <API_TOKEN>)"},
        )
    return await call_next(request)

# Routes API
app.include_router(api_router, prefix="/api/v1")
from .api.launch import router as launch_router
app.include_router(launch_router, prefix="/api/v1")
from .api.launch import practice_audio
app.add_api_websocket_route("/ws/rehearsal", practice_audio)

# Polices du produit servies aux écrans de diffusion. Sans elles, /output et
# /stage retombent sur la police système : un bandeau se juge d'abord à sa
# typographie, et le laiton de Lumen sur du Helvetica ne ressemble à rien.
# Servies en local — une source navigateur OBS doit fonctionner hors ligne.
_fonts_dir = Path(RESOURCE_DIR) / "data" / "fonts"
if _fonts_dir.is_dir():
    app.mount("/fonts", StaticFiles(directory=str(_fonts_dir)), name="fonts")
else:
    logger.warning(f"⚠️ Polices de diffusion absentes ({_fonts_dir}) : repli police système")


@app.get("/")
async def root():
    """Endpoint de santé"""
    return {
        "name": "VersePro v2",
        "status": "running",
        "version": "2.1.9"
    }


@app.get("/health")
async def health_check():
    """Check de santé détaillé"""
    propresenter_connected = False
    if output_manager and "propresenter" in output_manager.outputs:
        propresenter_connected = await output_manager.outputs["propresenter"].is_connected()
    
    return {
        "status": "healthy",
        "services": {
            "deepgram": deepgram_service is not None,
            "propresenter": propresenter_connected,
            "parser": verse_parser is not None,
            "vosk_loaded": vosk_service.initialized if vosk_service else False,
        }
    }


@app.get("/projection")
async def get_projection_page_legacy():
    """Redirige les anciennes requêtes d'affichage vers le nouvel endpoint Output unifié"""
    return RedirectResponse(url="/output")


@app.get("/overlay/bibliotheque/{slug}/image.png")
async def get_preset_image(slug: str):
    """Sert l'image d'un habillage enregistré (le slug est assaini en amont)."""
    from fastapi.responses import FileResponse, Response
    try:
        chemin = overlay_store._dossier_preset(slug) / "image.png"
    except ValueError:
        return Response(status_code=400)
    if not chemin.is_file():
        return Response(status_code=404)
    return FileResponse(str(chemin), media_type="image/png",
                        headers={"Cache-Control": "public, max-age=31536000, immutable"})


@app.get("/overlay.png")
async def get_overlay_image():
    """Sert l'habillage de l'église aux écrans (projection, OBS, aperçu)."""
    from fastapi.responses import FileResponse, Response
    if not overlay_store.IMAGE_PATH.is_file():
        return Response(status_code=404)
    # L'URL porte un paramètre de version (?v=mtime) : le navigateur peut donc
    # garder l'image en cache sans jamais afficher l'ancienne après un
    # remplacement — un habillage changé le samedi doit être visible le dimanche.
    return FileResponse(
        str(overlay_store.IMAGE_PATH),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@app.get("/assets/backgrounds/{asset_id}/{variant}")
async def get_background_asset(asset_id: str, variant: str):
    """Sert uniquement les fichiers valides de la bibliotheque locale."""
    from fastapi.responses import FileResponse, Response

    asset = background_store.asset_file(asset_id, variant)
    if not asset:
        return Response(status_code=404)
    path, media_type = asset
    return FileResponse(
        str(path),
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


def _get_template_path(name: str) -> Path:
    if hasattr(sys, '_MEIPASS'):
        p = Path(sys._MEIPASS) / "app" / "templates" / name
        if p.exists():
            return p
    p2 = Path(__file__).parent / "templates" / name
    if p2.exists():
        return p2
    return Path(__file__).parent / "templates" / name


# Endpoints de Rendu d'Affichage Web Autonome (Outputs)
@app.get("/output", response_class=HTMLResponse)
async def get_output_page():
    """
    Écran d'affichage universel v2 — « Lecture vivante ».
    Le texte est rendu mot à mot : pendant que le prédicateur lit, chaque mot
    s'illumine au rythme de sa voix (événements reading_progress). La traduction
    simultanée IA s'affiche en sous-titre live. Thèmes : presentation (défaut),
    broadcast (lower-third), confidence, dual. Params : ?theme= ?bg= ?scale= ?subtitle=off
    """
    html_content = _get_template_path("output.html").read_text(encoding="utf-8")
    return HTMLResponse(content=html_content)


@app.get("/stage", response_class=HTMLResponse)
async def get_stage_display():
    """
    Moniteur prédicateur (« stage display ») : verset courant avec lecture
    vivante, horloge, et verset SUIVANT pré-affiché. Ce que ProPresenter vend
    en option, en mieux : l'écran sait où en est la lecture.
    """
    html_content = _get_template_path("stage.html").read_text(encoding="utf-8")
    return HTMLResponse(content=html_content)


@app.get("/obs")
async def get_obs_browser_source():
    """Redirige les anciens flux vers le nouvel endpoint Output unifié"""
    return RedirectResponse(url="/output?theme=broadcast&bg=transparent")


@app.get("/projection")
async def get_legacy_projection_page():
    """Compatibilité : l'ancien écran /projection vit désormais sur /output"""
    return RedirectResponse(url="/output")


@app.get("/follow", response_class=HTMLResponse)
async def get_follow_page():
    """
    Page « assemblée » : suit en direct les versets projetés, sur mobile,
    dans la traduction choisie par chacun. Publique et en lecture seule.
    """
    versions = []
    if verse_parser and verse_parser.bible_loader:
        versions = list(verse_parser.bible_loader.versions.keys())
    options = "".join(f'<option value="{v}">{v}</option>' for v in versions) or '<option value="">Par défaut</option>'

    html_content = _get_template_path("follow.html").read_text(encoding="utf-8").replace("__OPTIONS__", options)
    return HTMLResponse(content=html_content)


@app.websocket("/ws/output")
async def websocket_output(websocket: WebSocket):
    """WebSocket pour les écrans d'affichage unifiés (écoute uniquement).

    `?canal=preview` abonne au canal de PRÉPARATION : ce que l'opérateur monte
    sans que l'assemblée le voie. Par défaut, `program` — la salle.
    """
    await websocket.accept(subprotocol=websocket_subprotocol(websocket))
    canal = websocket.query_params.get("canal", "program")
    browser_driver = output_manager.outputs.get("browser") if output_manager else None
    if browser_driver:
        await browser_driver.register_connection(websocket, canal)
        try:
            while True:
                try:
                    message = json.loads(await websocket.receive_text())
                    if isinstance(message, dict):
                        browser_driver.acknowledge(websocket, message)
                except (ValueError, TypeError):
                    continue
        except WebSocketDisconnect:
            pass
        finally:
            browser_driver.unregister_connection(websocket)
    else:
        await websocket.close(code=1011, reason="Moteur d'affichage non initialisé")


@app.websocket("/ws/projection")
async def websocket_projection_legacy(websocket: WebSocket):
    """Alias rétrocompatible pour les anciens clients d'affichage"""
    await websocket_output(websocket)


@app.get("/api/v1/projection/current")
async def get_current_projection():
    """État de projection courant — permet à la console de le restaurer après un rechargement"""
    return current_projection_slide


@app.post("/api/v1/projection/theme")
async def update_projection_theme(payload: dict):
    """Change le thème de la projection en direct"""
    theme = payload.get("theme", "presentation")
    settings.PROJECTION_THEME = theme
    from .services.database import get_database
    db = get_database()
    await db.set_setting("projection_theme", theme)
    await broadcast_projection(
        current_projection_slide.get("text", ""),
        current_projection_slide.get("reference", ""),
        current_projection_slide.get("background", "black"),
        translations=current_projection_slide.get("translations"),
        theme=theme
    )
    return {"status": "success", "theme": theme}


@app.post("/api/v1/projection/vmix")
async def update_vmix_config(payload: dict):
    """Met à jour les paramètres de session vMix en direct"""
    host = payload.get("host", "127.0.0.1")
    port = int(payload.get("port", 8088))
    enabled = bool(payload.get("enabled", False))
    input_id = payload.get("input_id", "VerseProTitle")
    
    settings.VMIX_HOST = host
    settings.VMIX_PORT = port
    settings.VMIX_ENABLED = enabled
    settings.VMIX_INPUT_ID = input_id
    
    if output_manager and "vmix" in output_manager.outputs:
        await output_manager.outputs["vmix"].update_settings(host, port, enabled, input_id)
        
    if db_service:
        await db_service.set_setting("vmix_host", host)
        await db_service.set_setting("vmix_port", str(port))
        await db_service.set_setting("vmix_enabled", "true" if enabled else "false")
        await db_service.set_setting("vmix_input_id", input_id)
        
    return {"status": "success", "config": payload}


@app.post("/api/v1/project")
async def project_slide(slide: dict):
    """Envoie manuellement un contenu à projeter"""
    global current_projection_slide
    text = slide.get("text", "")
    ref = slide.get("reference", "")
    bg = slide.get("background", "black")
    translations = slide.get("translations") if isinstance(slide.get("translations"), dict) else None
    theme = slide.get("theme", current_projection_slide.get("theme", "presentation"))
    version = slide.get("version") or slide.get("active_version")
    
    await broadcast_projection(text, ref, bg, translations=translations, theme=theme, version=version)
    
    # Si send_to_propresenter est activé, on demande spécifiquement au driver propresenter
    if slide.get("send_to_propresenter", False) and output_manager and "propresenter" in output_manager.outputs:
        await output_manager.outputs["propresenter"].send_scene({
            "text": text,
            "reference": ref
        })
        
    return {"status": "success", "slide": current_projection_slide}


# APIs Multi-Traduction
@app.get("/api/v1/bibles")
async def get_bibles():
    """Liste les versions de la Bible disponibles et active"""
    if not verse_parser or not verse_parser.bible_loader:
        return {"active": "LSG", "versions": ["LSG"]}
    loader = verse_parser.bible_loader
    return {
        "active": loader.active_version,
        "versions": list(loader.versions.keys())
    }


@app.get("/api/v1/ai/pull-local-model")
async def pull_local_model():
    """Télécharge le modèle Ollama en streaming SSE avec progression en temps réel."""
    import httpx

    model_name = settings.OLLAMA_MODEL or "llama3.1:8b"
    ollama_url = (settings.OLLAMA_URL or "http://localhost:11434").rstrip("/")

    def essayer_demarrer_ollama() -> bool:
        """Ouvre Ollama si l'utilisateur l'a installé mais pas encore lancé.

        Le bouton « Installer l'IA locale » doit pouvoir amorcer le serveur
        desktop. Si Ollama n'est pas installé, les exceptions sont ignorées et
        le flux SSE renvoie un diagnostic explicite au lieu d'un simple
        « connexion perdue ».
        """
        if not any(hote in ollama_url for hote in ("localhost", "127.0.0.1", "::1")):
            return False
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", "-a", "Ollama"], stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, start_new_session=True)
            elif os.name == "nt":
                subprocess.Popen(["ollama", "app.exe"], stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
            else:
                subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, start_new_session=True)
            return True
        except (FileNotFoundError, OSError):
            return False

    async def stream_progress():
        client_timeout = httpx.Timeout(600.0, connect=10.0)
        try:
            async with httpx.AsyncClient(timeout=client_timeout) as client:
                # Le premier lancement de l'app Ollama peut prendre quelques
                # secondes. On vérifie puis on ouvre l'app et on retente avant
                # d'abandonner le téléchargement.
                pret = False
                for tentative in range(5):
                    try:
                        tags = await client.get(f"{ollama_url}/api/tags", timeout=10.0)
                        if tags.status_code == 200:
                            pret = True
                            break
                    except httpx.HTTPError:
                        pass
                    if tentative == 0:
                        essayer_demarrer_ollama()
                    await asyncio.sleep(1.0 + tentative * 0.75)
                if not pret:
                    yield f'data: {json.dumps({"error": "Ollama est introuvable. Installez Ollama puis relancez le bouton ; l\'application a tenté de le démarrer automatiquement."})}\n\n'
                    return

                async with client.stream(
                    "POST",
                    f"{ollama_url}/api/pull",
                    json={"name": model_name, "stream": True},
                ) as response:
                    if response.status_code != 200:
                        yield f'data: {json.dumps({"error": f"Ollama refuse le téléchargement du modèle {model_name}", "status": response.status_code})}\n\n'
                        return
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            chunk = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        status = chunk.get("status", "")
                        total = chunk.get("total", 0)
                        completed = chunk.get("completed", 0)
                        pct = round((completed / total) * 100, 1) if total else 0
                        payload = {"status": status, "total": total, "completed": completed, "percent": pct}
                        yield f"data: {json.dumps(payload)}\n\n"
                # Fin du stream — rafraîchit le fournisseur actif sans redémarrer
                # VersePro, puis confirme au navigateur que le modèle est prêt.
                if ai_service:
                    await ai_service._detect_ollama()
                yield f'data: {json.dumps({"status": "done", "percent": 100, "model": model_name})}\n\n'
        except httpx.ConnectError:
            yield f'data: {json.dumps({"error": "Impossible de se connecter à Ollama. Vérifiez son installation."})}\n\n'
        except Exception as exc:
            yield f'data: {json.dumps({"error": str(exc)})}\n\n'

    return StreamingResponse(
        stream_progress(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/v1/bibles/select")
async def select_bible_version(data: dict):
    """Change la version active pour le parser"""
    version = data.get("version", "").upper()
    if not verse_parser or not verse_parser.bible_loader:
        raise HTTPException(status_code=500, detail="Service de parsing indisponible")
        
    loader = verse_parser.bible_loader
    loader.active_version = version
    settings.BIBLE_VERSION = version
    if semantic_service:
        semantic_service.reset()
        threading.Thread(
            target=semantic_service.initialize,
            kwargs={"allow_download": False},
            daemon=True,
        ).start()
    logger.info(f"🔄 Traduction de la Bible modifiée : {version}")
    return {"status": "success", "active": version}



# WebSocket principal de réception audio avec Fallback Vosk local
@app.websocket("/ws/audio")
async def websocket_audio(websocket: WebSocket):
    from .api.launch import audio_rehearsal_lock, kit_lock
    if not websocket_allowed(websocket):
        await websocket.close(code=1008)
        return
    if audio_rehearsal_lock.locked() or kit_lock.locked():
        await websocket.accept(subprotocol=websocket_subprotocol(websocket))
        await websocket.send_json({"type": "error", "message": "Arrêtez la répétition ou attendez la fin du kit avant d’ouvrir le micro."})
        await websocket.close(code=1013)
        return
    async with audio_rehearsal_lock:
        await _websocket_audio_session(websocket)


async def _websocket_audio_session(websocket: WebSocket):
    """
    WebSocket pour streaming audio temps réel avec détection et secours local Vosk ultra-rapide.
    """
    if not websocket_allowed(websocket):
        await websocket.close(code=1008, reason="Jeton API requis pour les clients distants")
        return

    await websocket.accept(subprotocol=websocket_subprotocol(websocket))

    if not deepgram_service or not verse_parser or not vosk_service:
        await websocket.close(code=1011, reason="Services non initialisés")
        return

    # Le micro s'ouvre : ce qu'on avait entendu au culte précédent — ou avant
    # une coupure — ne dit plus rien de la salle actuelle.
    sante_transcription.reinitialiser()

    send_lock = asyncio.Lock()

    async def send_json(payload: dict) -> None:
        """Sérialise les écritures concurrentes sur le WebSocket Starlette."""
        async with send_lock:
            await websocket.send_json(payload)

    session_tasks: set[asyncio.Task] = set()

    def spawn_session_task(coro, label: str) -> asyncio.Task | None:
        """Suit les tâches courtes et refuse leur accumulation sans limite."""
        if len(session_tasks) >= 32:
            if hasattr(coro, "close"):
                coro.close()
            logger.warning(f"Tâche temps réel abandonnée (saturation) : {label}")
            return None
        task = asyncio.create_task(coro, name=f"versepro:{label}")
        session_tasks.add(task)
        task.add_done_callback(session_tasks.discard)
        return task

    persistence_queue: asyncio.Queue = asyncio.Queue(maxsize=128)

    def persist_later(label: str, factory) -> None:
        try:
            persistence_queue.put_nowait((label, factory))
        except asyncio.QueueFull:
            logger.error(f"File de persistance saturée, événement ignoré : {label}")

    async def persistence_worker() -> None:
        while True:
            item = await persistence_queue.get()
            if item is None:
                return
            label, factory = item
            try:
                await factory()
            except Exception as exc:
                logger.error(f"Persistance {label} impossible : {exc}")
            finally:
                persistence_queue.task_done()
        
    # Envoi de l'état d'activation de l'Agent IA sémantique au client
    await send_json({
        "type": "ai_status",
        "enabled": ai_service.enabled if ai_service else False
    })
        
    transcript_queue: asyncio.Queue = asyncio.Queue(maxsize=64)

    async def queue_transcript(transcript: str, is_final: bool) -> None:
        """Conserve toutes les finales, mais laisse tomber un partiel obsolète."""
        item = (transcript, is_final)
        if is_final:
            await transcript_queue.put(item)
            return
        try:
            transcript_queue.put_nowait(item)
        except asyncio.QueueFull:
            logger.debug("Partiel ASR ignoré : file de transcription saturée")
    transcription_session = None
    recognizer = None
    use_vosk = False
    use_nemotron = False
    # Dernier partiel Nemotron transmis : on ne renvoie que ce qui a changé.
    dernier_partiel_nemotron = ""

    # PLUS DE BARRIÈRE VOCALE SUR LE CHEMIN AUDIO.
    #
    # Elle promettait d'écarter musique et silences avant transcription. Deux
    # raisons de la retirer, pas une.
    #
    # La première est mesurée : nourrie d'une fenêtre incomplète, elle bloquait
    # 100 % de trente minutes de prédication réelle. Le défaut est corrigé,
    # mais il avait dormi des mois sans que rien ne le signale, parce qu'une
    # porte qui bloque tout passe toutes les vérifications d'une porte qui
    # bloque le silence.
    #
    # La seconde est de fond, et c'est elle qui tranche : VersePro sert des
    # églises où la musique accompagne la prédication et où l'on prie à voix
    # haute. Un filtre qui décide de ce qui est « de la parole » se trompe
    # précisément là. Le filtre « son difficile » avait déjà été retiré pour
    # ce motif — celui-ci revenait par une autre porte.
    #
    # Un verset raté coûte plus cher qu'un peu de son transcrit pour rien.
    
    # Callback pour Deepgram
    async def on_transcript_received(result):
        try:
            type_name = type(result).__name__
            
            # Ignorer les messages de métadonnées (ListenV1Metadata)
            if type_name == "ListenV1Metadata" or not hasattr(result, "channel"):
                return
            
            # Structure ListenV1Results: result.channel.alternatives[0].transcript
            channel = result.channel
            if channel and hasattr(channel, "alternatives") and channel.alternatives:
                transcript = channel.alternatives[0].transcript
                is_final = getattr(result, "is_final", False)
                if transcript.strip():
                    logger.debug(f"📝 Deepgram: '{transcript}' (final={is_final})")
                    await queue_transcript(transcript, is_final)
        except Exception as e:
            logger.error(f"❌ Erreur callback transcription Deepgram: {e}")

    async def activate_vosk(status: str = "connected") -> bool:
        nonlocal use_vosk, use_nemotron, recognizer
        success = await asyncio.to_thread(vosk_service.initialize)
        if not success:
            return False
        recognizer = vosk_service.get_recognizer(settings.AUDIO_SAMPLE_RATE)
        if not recognizer:
            return False
        use_vosk = True
        use_nemotron = False
        await send_json({"type": "status_update", "status": status, "mode": "vosk"})
        return True

    async def activate_nemotron(status: str = "connected") -> bool:
        nonlocal use_vosk, use_nemotron
        if not nemotron_service or not nemotron_service.is_ready:
            return False
        try:
            # Sans start(), le fil de décodage ne tourne pas et
            # accept_waveform jette silencieusement les échantillons.
            await asyncio.to_thread(nemotron_service.start)
        except Exception as exc:
            logger.error(f"Démarrage de Nemotron impossible : {exc}")
            return False
        use_nemotron = True
        use_vosk = False
        await send_json({
            "type": "status_update",
            "status": status,
            "mode": "nemotron",
            "model": "Nemotron 3.5-ASR 0.6B",
        })
        return True

    # Lecture du paramètre query 'engine' et 'translation_lang'.
    engine = websocket.query_params.get("engine", settings.ASR_DEFAULT_ENGINE)
    translation_lang = websocket.query_params.get("translation_lang", "")
    logger.info(f"🔌 Connexion WebSocket audio demandée avec le moteur : {engine} | Traduction: {translation_lang or 'aucune'}")

    if engine in ("vosk", "nemotron", "local_auto"):
        # Un moteur local explicitement choisi est une contrainte de
        # confidentialité, pas une préférence. Il ne doit jamais envoyer le
        # son vers Deepgram en silence. Seul « auto » autorise le cloud.
        if engine == "nemotron":
            local_ready = await activate_nemotron()
            reason = (
                getattr(nemotron_service, "last_error", "")
                or "Nemotron n'est pas opérationnel. Vérifiez le moteur natif et le modèle local."
            )
        elif engine == "vosk":
            local_ready = await activate_vosk()
            reason = "Vosk n'est pas opérationnel. Préparez le modèle local."
        else:
            # local_auto reste strictement hors ligne : Nemotron en priorité,
            # puis Vosk, sans aucune sortie réseau.
            local_ready = await activate_nemotron()
            if not local_ready:
                local_ready = await activate_vosk(status="fallback")
            reason = "Aucun moteur ASR local n'est opérationnel."

        if not local_ready:
            logger.error(f"Moteur ASR local demandé indisponible : {reason}")
            await send_json({
                "type": "status_update",
                "status": "error",
                "mode": engine,
                "reason": reason,
            })
            with suppress(Exception):
                await websocket.close(code=1011, reason=reason[:120])
            return
    elif engine == "deepgram":
        # Mode Deepgram cloud forcé
        try:
            transcription_session = await deepgram_service.create_session(on_transcript_received)
            await send_json({"type": "status_update", "status": "connected", "mode": "deepgram"})
            logger.info("🎙️ Session de transcription Deepgram connectée (Mode forcé)")
        except Exception as e:
            logger.error(f"❌ Échec démarrage Deepgram forcé : {e}")
            try:
                await websocket.close(code=1011, reason=f"Connexion Deepgram impossible : {e}")
            except Exception:
                pass
            return
    else:
        # Mode automatique : Deepgram, puis Nemotron déjà préparé, puis Vosk.
        try:
            transcription_session = await deepgram_service.create_session(on_transcript_received)
            await send_json({"type": "status_update", "status": "connected", "mode": "deepgram"})
            logger.info("🎙️ Session de transcription en ligne Deepgram connectée")
        except Exception as e:
            logger.warning(f"Échec connexion Deepgram ({e}). Activation du secours local...")
            try:
                success = await activate_nemotron()
                if not success:
                    success = await activate_vosk(status="fallback")
                if success:
                    logger.info("Secours local activé et prêt")
                else:
                    raise RuntimeError("Aucun modèle local disponible")
            except Exception as we:
                logger.error(f"Échec de la bascule locale : {we}")
                try:
                    await websocket.close(code=1011, reason="Connexion Deepgram impossible et moteur local hors-service")
                except Exception:
                    pass
                return
            
    async def receive_audio_task():
        """Reçoit l'audio client et l'envoie au moteur de transcription actif"""
        nonlocal use_vosk, use_nemotron, recognizer, transcription_session, dernier_partiel_nemotron
        
        # Pour le mécanisme de reconnexion automatique de Deepgram
        reconnecting_deepgram = False
        last_reconnect_attempt = 0
        last_fallback_attempt = 0.0

        try:
            while True:
                data = await websocket.receive_bytes()
                # TRACE et non DEBUG : vingt-trois lignes par seconde pendant toute la
                # prédication, sur le chemin chaud de l'audio.
                logger.trace(f"🎙️ Chunk audio reçu: {len(data)} bytes")

                # Si on utilise en théorie Deepgram mais que la session est inactive (déconnexion 1011 ou erreur)
                if not use_vosk and not use_nemotron and (
                    not transcription_session or not transcription_session.is_active
                ):
                    now = asyncio.get_event_loop().time()
                    if now - last_fallback_attempt < 5:
                        continue
                    last_fallback_attempt = now
                    try:
                        success = await activate_nemotron()
                        if not success:
                            success = await activate_vosk(status="fallback")
                        if success:
                            logger.warning("Session Deepgram inactive. Bascule automatique sur le moteur local.")
                        else:
                            logger.error("Impossible de basculer en local : modèle indisponible. Nouvelle tentative dans 5 s.")
                            continue
                    except Exception as ve:
                        logger.error(f"Erreur de bascule ASR locale : {ve}")
                        continue

                if use_nemotron:
                    # Le décodage se fait dans le thread pour ne pas bloquer la
                    # boucle d'événements.
                    echantillons = np.frombuffer(data, dtype=np.int16)
                    await asyncio.to_thread(nemotron_service.accept_waveform, echantillons)
                    enonce = nemotron_service.prendre_enonce_fini()
                    if enonce:
                        await queue_transcript(enonce, True)
                        dernier_partiel_nemotron = ""
                    else:
                        # Le PARTIEL, sans quoi la console reste muette entre
                        # deux phrases. Mesuré sur 10,7 s : un seul message
                        # partait, alors que 39 blocs sur 43 avaient un partiel
                        # à montrer — l'écran ne bougeait pas pendant neuf
                        # secondes, puis une phrase entière tombait d'un coup.
                        # C'était plus saccadé que Vosk, qui lui en envoie.
                        partiel = nemotron_service.get_result()
                        if partiel and partiel != dernier_partiel_nemotron:
                            dernier_partiel_nemotron = partiel
                            await queue_transcript(partiel, False)
                elif not use_vosk:
                    await transcription_session.send_audio(data)
                else:
                    # Vosk local : traitement en temps réel du flux audio non-bloquant
                    is_accepted = await asyncio.to_thread(recognizer.AcceptWaveform, data)
                    if is_accepted:
                        result_str = await asyncio.to_thread(recognizer.Result)
                        result = json.loads(result_str)
                        text = result.get("text", "")
                        if text.strip():
                            await queue_transcript(text, True)
                    else:
                        partial_str = await asyncio.to_thread(recognizer.PartialResult)
                        partial = json.loads(partial_str)
                        text = partial.get("partial", "")
                        if text.strip():
                            await queue_transcript(text, False)
                            
                # Retour vers Deepgram après une bascule sur un moteur local.
                if engine == "auto" and (use_vosk or use_nemotron) and not reconnecting_deepgram:
                    current_time = asyncio.get_event_loop().time()
                    if current_time - last_reconnect_attempt > 15:
                        last_reconnect_attempt = current_time
                        reconnecting_deepgram = True

                        async def try_reconnect_deepgram():
                            nonlocal transcription_session, use_vosk, use_nemotron, reconnecting_deepgram
                            logger.info("Tentative de reconnexion en arrière-plan à Deepgram...")
                            try:
                                new_session = await deepgram_service.create_session(on_transcript_received)
                                if transcription_session:
                                    with suppress(Exception):
                                        await transcription_session.close()
                                transcription_session = new_session
                                use_vosk = False
                                use_nemotron = False
                                if nemotron_service:
                                    with suppress(Exception):
                                        nemotron_service.stop()
                                await send_json({"type": "status_update", "status": "connected", "mode": "deepgram"})
                                logger.info("Connexion Deepgram rétablie. Retour au moteur principal.")
                            except Exception as re_err:
                                logger.debug(f"Reconnexion Deepgram différée : {re_err}")
                            finally:
                                reconnecting_deepgram = False

                        spawn_session_task(try_reconnect_deepgram(), "deepgram-reconnect")
                            
        except WebSocketDisconnect:
            logger.info("🔌 Client WebSocket déconnecté (audio)")
        except Exception as e:
            logger.error(f"❌ Erreur réception audio: {e}")
        finally:
            if transcription_session:
                with suppress(Exception):
                    await transcription_session.close()
            if use_nemotron and nemotron_service:
                with suppress(Exception):
                    nemotron_service.stop()
            # Signal de fermeture de la queue
            await transcript_queue.put(None)

    async def send_transcript_task():
        """Prend le texte transcrit, le parse et notifie le technicien + projecteur"""
        buffer_text = ""
        last_detected_ref = None
        last_detected_at = 0.0
        last_partial_words = []
        analysis_generation = 0
        analysis_task: asyncio.Task | None = None
        translation_task: asyncio.Task | None = None

        def is_current(generation: int) -> bool:
            return generation == analysis_generation

        def is_direct_projection_allowed(ref: dict) -> bool:
            method = ref.get("detection_method")
            confidence = float(ref.get("confidence") or 0)
            # Un texte retrouvé par l'index exact est aussi fiable qu'une
            # référence explicitement structurée. Seules les recherches
            # floues, sémantiques ou IA restent soumises à validation.
            exact_methods = {"explicit", "text_phrase", "text_index"}
            minimum = 0.90 if method == "text_index" else (0.95 if method in exact_methods else 0.75)
            # Plusieurs références dans une même phrase : une seule peut aller
            # à l'écran, et c'est la première annoncée — celle que le
            # prédicateur va lire. Les autres attendent dans la file.
            if ref.get("annonce_multiple"):
                return False
            # UN VERSET DÉDUIT NE VA PLUS À L'ÉCRAN TOUT SEUL.
            #
            # `chapter_contextual_text` est le cas où le prédicateur n'annonce
            # QUE le chapitre — « laissez-moi vous donner un exemple tiré de
            # 2 Rois chapitre 6 » — et où le verset est retrouvé en comparant
            # la phrase au texte du chapitre. C'est une déduction, souvent
            # juste, jamais certaine : le numéro n'a pas été prononcé.
            #
            # Relevé sur une heure de prédication réelle : « 2 Rois 6:11 » et
            # « Romains 10:8 » (trois fois) sont partis à l'antenne alors que
            # seul le chapitre avait été dit — dans le second cas, le « 2 » de
            # « parle de 2 types de justice » a servi de numéro de verset. Sur
            # cette session, 50 détections sur 50 ont été projetées d'office.
            #
            # La déduction reste précieuse : elle continue d'alimenter la file
            # en carte, prête en un clic. Elle ne s'impose simplement plus à
            # l'assemblée sans qu'un régisseur l'ait regardée.
            # …SAUF s'il figure au plan de prédication.
            #
            # Le pasteur a écrit « 2 Rois 6:15 » dans ses notes et annonce
            # « un exemple tiré de 2 Rois chapitre 6 » : la déduction n'est
            # plus un pari, elle est confirmée par une source antérieure au
            # culte, que le micro ne peut pas avoir mal entendue. C'est le
            # seul cas où l'on rend sa confiance à un verset non prononcé.
            methodes_projetables = set(exact_methods) | {"relative_jump"}
            if ref.get("au_plan"):
                methodes_projetables.add("chapter_contextual_text")
            return (
                method in methodes_projetables
                and confidence >= minimum
                and ref.get("verse_start") is not None
                and not ref.get("requires_review")
            )

        async def process_detected_reference(
            raw_ref: dict,
            analysis_text: str,
            generation: int,
            source: str = "local",
        ) -> None:
            nonlocal last_detected_ref, last_detected_at
            if not is_current(generation):
                return

            ref = dict(raw_ref)
            ref["source"] = source
            if source != "local":
                # Le moteur peut avoir produit une décision plus précise que
                # le simple canal d'origine (notamment ``semantic_conflict``).
                # Ne l'écrasons pas ici : l'interface doit pouvoir expliquer
                # qu'une référence prononcée contredit le texte réellement cité.
                if source == "ai":
                    ref["detection_method"] = "ai_semantic"
                else:
                    ref.setdefault("detection_method", "semantic_local")
                ref["confidence"] = min(float(ref.get("confidence") or 0.95), 0.95)
                ref["requires_review"] = True
                ref["projection_policy"] = "manual_review"
            else:
                ref.setdefault("requires_review", False)
                direct_allowed = is_direct_projection_allowed(ref)
                ref["requires_review"] = not direct_allowed
                ref["projection_policy"] = "autopilot_direct" if direct_allowed else "manual_review"
                # Une citation explicite ouvre un passage : VerseGraph pourra
                # y rattacher les allusions des minutes suivantes. C'est ici
                # que l'ancre se pose — la cascade, elle, reste sans effet de
                # bord pour que le rejeu puisse la jouer cas par cas.
                if verse_graph:
                    verse_graph.ancrer(ref)

            direct_allowed = is_direct_projection_allowed(ref)
            ref["auto_projected"] = bool(
                settings.PROPRESENTER_AUTO_SEND
                and direct_allowed
                and not settings.SUNDAY_SAFE_MODE
                and not settings.SHADOW_MODE
            )
            if ref["auto_projected"]:
                ref["projection_policy"] = "autopilot_projected"
            elif settings.SHADOW_MODE:
                ref["projection_policy"] = "shadow_only"
            elif settings.SUNDAY_SAFE_MODE:
                ref["projection_policy"] = "safe_manual_review"

            fusion = ref.get("fusion") or {}
            if ref.get("detection_method") == "explicit":
                explanation = "Référence biblique prononcée explicitement et vérifiée dans le corpus local."
            elif ref.get("detection_method") in {"spoken_revision", "local_correction"}:
                explanation = ref.get("explanation") or "Correction à valider par l’opérateur."
            elif ref.get("detection_method") == "semantic_conflict":
                conflict = ref.get("explicit_conflict") or {}
                explanation = (
                    f"Le texte cité correspond à {ref.get('reference')} mais la référence "
                    f"prononcée était {conflict.get('spoken_reference')}. Validation requise."
                )
            elif ref.get("detection_method") in {"semantic_local", "semantic_anchored"}:
                explanation = (
                    "Suggestion locale issue de l'accord lexical et sémantique. "
                    f"Recouvrement: {float(fusion.get('overlap') or 0):.2f}."
                )
            elif ref.get("detection_method") == "chapter_candidate":
                explanation = "Chapitre annoncé ; recherche du verset en cours."
            else:
                explanation = "Suggestion IA choisie dans une liste fermée de versets réels. Validation humaine requise."
            ref["explanation"] = explanation
            ref["decision_generation"] = generation

            ref_key = (
                f"{ref.get('book_abbr')}_{ref.get('chapter')}_"
                f"{ref.get('verse_start')}_{ref.get('verse_end') or ''}"
            )
            now = time.monotonic()
            if (
                ref_key == last_detected_ref
                and now - last_detected_at < DEDUPLICATION_SECONDS
            ) or not is_current(generation):
                return
            last_detected_ref = ref_key
            last_detected_at = now

            try:
                await send_json({
                    "type": "reference_detected",
                    "reference": ref,
                    "text": analysis_text,
                    "verse_id": None,
                })
            except Exception:
                return

            if not is_current(generation):
                return

            # Un chapitre seul est un état d'interface temporaire, pas un
            # verset détecté. Le conserver créait les nombreuses entrées :0
            # observées dans l'historique du sermon.
            if not ref.get("transient") and db_service and db_service.db:
                ref_snapshot = dict(ref)
                persist_later(
                    "detected-verse",
                    lambda ref_snapshot=ref_snapshot, analysis_text=analysis_text, source=source:
                        db_service.add_detected_verse(
                            reference=ref_snapshot,
                            session_id=current_session_id,
                            context=analysis_text,
                            confidence=int(float(ref_snapshot.get("confidence") or 1.0) * 100),
                            source=source,
                        ),
                )

            if ref["auto_projected"] and is_current(generation):
                await broadcast_projection(
                    ref.get("text", ""),
                    ref["reference"],
                    translations=ref.get("translations"),
                )
                if not is_current(generation):
                    return
                sent = False
                if output_manager and "propresenter" in output_manager.outputs:
                    sent = await output_manager.outputs["propresenter"].send_scene({
                        "reference": ref["reference"],
                        "text": ref.get("text", ""),
                    })
                with suppress(Exception):
                    await send_json({
                        "type": "propresenter_status",
                        "sent": sent,
                        "reference": ref,
                        "verse_id": None,
                    })

        async def analyze_and_detect(
            analysis_text: str,
            final_state: bool,
            generation: int,
        ) -> None:
            try:
                # Le flux audio doit rester opérationnel même si le moteur de
                # détection n'a pas encore fini son initialisation (notamment
                # pendant le démarrage local ou dans un profil ASR minimal).
                if reference_engine is None:
                    logger.debug("Détection biblique indisponible : moteur non initialisé.")
                    return
                result = await reference_engine.process(
                    analysis_text, final_state, generation, session_id=current_session_id
                )
                if not result or not is_current(generation):
                    return
                

                decision = result["payload"]
                method = decision.get("detection_method")
                source = decision.get("source", "local")

                if method in ("explicit", "chapter_candidate"):
                    await process_detected_reference(decision, analysis_text, generation)
                elif method == "ai_semantic":
                    await process_detected_reference(decision, analysis_text, generation, source="ai")
                else:
                    fusion = decision.get("fusion")
                    if fusion:
                        logger.info(
                            f"🔗 Fusion → {decision['reference']} "
                            f"({fusion['reason']}, recouvrement {fusion['overlap']})"
                        )
                    await process_detected_reference(decision, analysis_text, generation, source="semantic")

                # Les autres références de la MÊME phrase. Elles étaient
                # simplement perdues : la cascade n'en rendait qu'une, la
                # dernière prononcée. Relevé sur une heure de prédication,
                # « Samuel 16:7 » disparaissait ainsi derrière « Jean 4:24 »
                # annoncé deux phrases plus loin, sans laisser de trace.
                for extra in decision.get("references_multiples") or []:
                    if not is_current(generation):
                        break
                    await process_detected_reference(extra, analysis_text, generation)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error(f"Analyse de détection impossible : {exc}")

        async def perform_translation(text_to_translate: str, target_lang: str, generation: int) -> None:
            try:
                translated = await ai_service.translate_text(text_to_translate, target_lang)
                if not translated or not is_current(generation):
                    return
                await send_json({"type": "translation", "text": translated, "lang": target_lang})
                if is_current(generation):
                    await broadcast_output_event({
                        "type": "live_translation",
                        "text": translated,
                        "lang": target_lang,
                    })
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error(f"Traduction directe impossible : {exc}")

        try:
            while True:
                item = await transcript_queue.get()
                if item is None:
                    transcript_queue.task_done()
                    break
                    
                transcript, is_final = item
                
                # 1. Envoi immédiat et sans blocage du retour visuel de la transcription courante
                await send_json({
                    "type": "transcript",
                    "text": transcript,
                    "is_final": is_final,
                    "buffer": buffer_text
                })

                # 1.5. Lecture vivante : n'alimente le traqueur qu'avec les MOTS NOUVEAUX
                # de l'énoncé (les transcriptions partielles répètent le début à chaque fois)
                if reading_tracker.active:
                    cur_words = transcript.split()
                    common = 0
                    while (common < len(last_partial_words) and common < len(cur_words)
                           and last_partial_words[common] == cur_words[common]):
                        common += 1
                    new_words = " ".join(cur_words[common:])
                    last_partial_words = [] if is_final else cur_words
                    if new_words and reading_tracker.feed(new_words):
                        spawn_session_task(broadcast_output_event({
                            "type": "reading_progress",
                            "reference": current_projection_slide.get("reference", ""),
                            "matched": reading_tracker.position,
                            "total": reading_tracker.total
                        }), "reading-progress")
                elif is_final:
                    last_partial_words = []

                if is_final:
                    # Chaque transcription finale EST un segment : sa longueur
                    # nourrit la mesure de santé. On note ici, et pas dans la
                    # cascade, pour que celle-ci reste sans effet de bord et
                    # que le rejeu puisse la piloter cas par cas.
                    etait_fiable = sante_transcription.est_fiable()
                    sante_transcription.noter(transcript)
                    # On ne prévient qu'aux BASCULES. Un bandeau qui se répète
                    # à chaque phrase devient un bruit de plus ; ce qui compte,
                    # c'est le moment où le logiciel change de comportement.
                    if sante_transcription.est_fiable() != etait_fiable:
                        with suppress(Exception):
                            await send_json({
                                "type": "transcription_health",
                                **sante_transcription.etat(),
                            })

                # Le texte complet à analyser
                current_analysis_text = (buffer_text + " " + transcript).strip()

                # Une transcription plus récente invalide immédiatement toute
                # décision précédente, y compris une réponse IA encore en vol.
                analysis_generation += 1
                if analysis_task and not analysis_task.done():
                    analysis_task.cancel()
                analysis_task = spawn_session_task(
                    analyze_and_detect(current_analysis_text, is_final, analysis_generation),
                    "detection",
                )
                
                # 3. Traitement des fins de phrases
                if is_final:
                    # Accumulation du buffer pour assurer la continuité
                    if buffer_text:
                        buffer_text += " " + transcript
                    else:
                        buffer_text = transcript
                        
                    # Conserver uniquement les 40 derniers mots
                    words = buffer_text.split()
                    if len(words) > 40:
                        buffer_text = " ".join(words[-40:])
                        
                    # Enregistrement cumulé du transcript en BDD (non-bloquant)
                    if db_service and db_service.db and current_session_id:
                        persist_later(
                            "transcript",
                            lambda transcript=transcript: db_service.append_to_session_transcript(
                                current_session_id, transcript
                            ),
                        )
                        
                    # Traduction en direct (non-bloquante)
                    if translation_lang and ai_service and ai_service.enabled:
                        if translation_task and not translation_task.done():
                            translation_task.cancel()
                        translation_task = spawn_session_task(
                            perform_translation(transcript, translation_lang, analysis_generation),
                            "translation",
                        )
                transcript_queue.task_done()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"❌ Erreur émission transcription: {e}")
        finally:
            for task in (analysis_task, translation_task):
                if task and not task.done():
                    task.cancel()
            await asyncio.gather(
                *[task for task in (analysis_task, translation_task) if task],
                return_exceptions=True,
            )

    try:
        persistence_job = asyncio.create_task(persistence_worker(), name="versepro:persistence")
        receive_job = asyncio.create_task(receive_audio_task(), name="versepro:audio-receive")
        send_job = asyncio.create_task(send_transcript_task(), name="versepro:transcript-send")

        done, pending = await asyncio.wait(
            {receive_job, send_job},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        for task in done:
            if task.exception():
                raise task.exception()

        await persistence_queue.put(None)
        try:
            await asyncio.wait_for(persistence_job, timeout=2.0)
        except asyncio.TimeoutError:
            persistence_job.cancel()
            await asyncio.gather(persistence_job, return_exceptions=True)
            
    except Exception as e:
        logger.error(f"❌ Erreur WebSocket principal: {e}")
    finally:
        for task in list(session_tasks):
            task.cancel()
        await asyncio.gather(*session_tasks, return_exceptions=True)
        logger.info("🔒 Session audio fermée")


@app.websocket("/ws/control")
async def websocket_control(websocket: WebSocket):
    """Contrôle manuel de la projection multi-sorties"""
    if not websocket_allowed(websocket):
        await websocket.close(code=1008, reason="Jeton API requis pour les clients distants")
        return

    await websocket.accept(subprotocol=websocket_subprotocol(websocket))
    if not output_manager:
        await websocket.close(code=1011, reason="Moteur de sortie non initialisé")
        return
        
    try:
        logger.info("📺 Session contrôle manuel ouverte")
        pp_driver = output_manager.outputs.get("propresenter")
        
        while True:
            data = await websocket.receive_json()
            action = data.get("action")
            
            if action == "send_reference":
                ref = data.get("reference")
                if ref:
                    parsed = await verse_parser.parse(ref) if verse_parser else None
                    receipts = {}
                    if parsed and parsed.get("text"):
                        receipts = await broadcast_projection(
                            parsed["text"],
                            parsed["reference"],
                            translations=parsed.get("translations"),
                        )
                    await websocket.send_json({
                        "type": "send_result",
                        "success": bool(parsed and parsed.get("text") and receipts.get("browser")),
                        "reference": parsed["reference"] if parsed else ref,
                        "outputs": receipts,
                        "error": None if parsed else "Référence biblique invalide",
                    })
                    
            elif action == "clear":
                # Effacement universel
                receipts = await broadcast_projection("", "")
                await websocket.send_json({
                    "type": "clear_result",
                    "success": bool(receipts.get("browser")),
                    "outputs": receipts,
                })
                
            elif action == "status":
                status = {}
                if pp_driver:
                    status = {
                        "connected": await pp_driver.is_connected(),
                        "stats": pp_driver.stats
                    }
                await websocket.send_json({
                    "type": "status",
                    "data": status
                })
    except WebSocketDisconnect:
        logger.info("🔌 Client contrôle manuel déconnecté")
    except Exception as e:
        logger.error(f"❌ Erreur contrôle manuel: {e}")


# Pas de bloc `__main__` ici. Il en existait un qui lançait uvicorn sur
# 0.0.0.0 — donc exposait la régie sur tout le réseau — en contradiction avec
# run_server.py, le vrai point d'entrée, qui écoute sur 127.0.0.1.
