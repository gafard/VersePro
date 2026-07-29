"""
VersePro v2 - Backend Principal
Architecture moderne avec FastAPI + WebSocket pour streaming temps réel, multi-traduction,
projection autonome et fallback hors-ligne Vosk local ultra-léger et robuste.
"""

import asyncio
import json
import os
import re
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
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from loguru import logger
import uvicorn

from .core.config import settings, RESOURCE_DIR
from .core.security import http_request_allowed, websocket_allowed
from .services.deepgram_service import DeepgramService
from .services.verse_parser import VerseParserService, version_label
from .services.database import DatabaseService, get_database
from .services.vosk_service import VoskService
from .services.whisper_service import WhisperService
from .services.ai_service import AIService
from .services.semantic_search import LocalSemanticService
from .services.verse_graph import VerseGraphService
from .services.transcription_health import SanteTranscription
from .services.detection_fusion import fuse as fuse_detection, strip_attribution, recent_window
from .services.reading_tracker import ReadingTracker
from .services.secret_store import secret_store
from .services import overlay_store
from .outputs import OutputManager
from .api.routes import router as api_router


# Services globaux
deepgram_service: DeepgramService | None = None
output_manager: OutputManager | None = None
verse_parser: VerseParserService | None = None
db_service: DatabaseService | None = None
vosk_service: VoskService | None = None
whisper_service: WhisperService | None = None
ai_service: AIService | None = None
semantic_service: LocalSemanticService | None = None
verse_graph: VerseGraphService | None = None
sante_transcription: SanteTranscription = SanteTranscription()
current_session_id: int | None = None
osc_service: Any = None

# Connexions et état de projection
projector_connections = set()

# Lecture vivante : position de la voix du prédicateur dans le verset projeté
reading_tracker = ReadingTracker()

async def broadcast_output_event(payload: dict):
    """Événement léger vers les écrans (progression de lecture, traduction live)"""
    if output_manager:
        browser = output_manager.outputs.get("browser")
        if browser:
            await browser.broadcast_event(payload)
current_projection_slide = {
    "text": "En attente d'affichage...",
    "reference": "",
    "background": "black",
    "theme": "classic",
    "translations": {}
}

async def _lookup_next_verse(reference: str) -> tuple[str, str]:
    """Texte du verset suivant (pré-affiché sur le moniteur prédicateur)"""
    try:
        if not verse_parser or not reference:
            return "", ""
        parsed = await verse_parser.parse(reference, skip_text_search=True)
        if not parsed or parsed.get("verse_start") is None:
            return "", ""
        next_v = (parsed.get("verse_end") or parsed["verse_start"]) + 1
        text = verse_parser.bible_loader.get_verse_text(parsed["book_abbr"], parsed["chapter"], next_v)
        if not text:
            return "", ""
        return f"{parsed['book_abbr']} {parsed['chapter']}:{next_v}", text
    except Exception:
        return "", ""


async def broadcast_projection(text: str, reference: str, background: str | None = None, translations: dict | None = None, theme: str | None = None):
    """Diffuse le slide à tous les projecteurs et suiveurs connectés via OutputManager"""
    global current_projection_slide

    next_ref, next_text = await _lookup_next_verse(reference)
    
    book = None
    chapter = None
    verse_start = None
    verse_end = None
    if reference and verse_parser:
        parsed = await verse_parser.parse(reference, skip_text_search=True)
        if parsed:
            book = parsed.get("book")
            chapter = parsed.get("chapter")
            verse_start = parsed.get("verse_start")
            verse_end = parsed.get("verse_end")

    current_projection_slide = {
        "text": text,
        "reference": reference,
        "book": book,
        "chapter": chapter,
        "verse_start": verse_start,
        "verse_end": verse_end,
        "background": background or current_projection_slide.get("background", "black"),
        "theme": theme or current_projection_slide.get("theme", "presentation"),
        "translations": translations or {},
        "next_reference": next_ref,
        "next_text": next_text,
        "active_version": settings.BIBLE_VERSION,
        "active_version_label": version_label(settings.BIBLE_VERSION),
        "active_version_short": version_label(settings.BIBLE_VERSION, short=True),
        "show_version": settings.SHOW_BIBLE_VERSION,
        "style": settings.PROJECTION_STYLE,
        "dual_translations": settings.DUAL_TRANSLATIONS,
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestion du cycle de vie de l'application"""
    global deepgram_service, output_manager, verse_parser, db_service, vosk_service, whisper_service, ai_service, semantic_service, verse_graph, current_session_id, osc_service
    
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
    if settings.PROPRESENTER_PORT == 12345:
        settings.PROPRESENTER_PORT = 1025
        await db_service.set_setting("propresenter_port", 1025)
        logger.info("⚙️ Port ProPresenter migré de 12345 vers 1025 (API officielle 7.9+)")
                
    # Crée une session par défaut
    current_session_id = await db_service.create_session("Session automatique")
    
    # Initialisation des autres services avec la config SQLite chargée
    deepgram_service = DeepgramService(settings.DEEPGRAM_API_KEY)
    
    # Initialisation d'OutputManager avec ses drivers
    output_manager = OutputManager()
    await output_manager.initialize_defaults()
    
    verse_parser = VerseParserService()
    vosk_service = VoskService()
    whisper_service = WhisperService()
    ai_service = AIService()
    semantic_service = LocalSemanticService(verse_parser.bible_loader)
    verse_graph = VerseGraphService(semantic_service)
    
    # Ne télécharge rien au démarrage. Un modèle Vosk déjà présent est seulement
    # chargé en arrière-plan; les installations restent des actions explicites.
    if os.environ.get("VERSEPRO_TESTING") != "1":
        if Path(vosk_service.model_dir).exists():
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
    
    if current_session_id:
        await db_service.end_session(current_session_id)
    
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
    version="2.0.0",
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
        "version": "2.0.0"
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
    html_content = """
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="utf-8">
        <title>Rendu d'Affichage - VersePro</title>
        <style>
            /* Polices du produit, servies par le backend (/fonts) : une source
               navigateur OBS doit fonctionner hors ligne, donc rien de distant. */
            @font-face { font-family:"Space Grotesk"; font-weight:600; font-display:block;
                         src:url("/fonts/space-grotesk-latin-600-normal.woff2") format("woff2"); }
            @font-face { font-family:"Space Grotesk"; font-weight:700; font-display:block;
                         src:url("/fonts/space-grotesk-latin-700-normal.woff2") format("woff2"); }
            @font-face { font-family:"Geist Sans"; font-weight:400; font-display:block;
                         src:url("/fonts/geist-sans-latin-400-normal.woff2") format("woff2"); }
            @font-face { font-family:"Geist Sans"; font-weight:500; font-display:block;
                         src:url("/fonts/geist-sans-latin-500-normal.woff2") format("woff2"); }
            @font-face { font-family:"JetBrains Mono"; font-weight:500; font-display:block;
                         src:url("/fonts/jetbrains-mono-latin-500-normal.woff2") format("woff2"); }
            @font-face { font-family:"JetBrains Mono"; font-weight:600; font-display:block;
                         src:url("/fonts/jetbrains-mono-latin-600-normal.woff2") format("woff2"); }

            :root { --accent: oklch(76% 0.17 50); --accent-2: oklch(68% 0.16 18); --read: #ffffff; --unread: rgba(255,255,255,0.34);
                    --ink: oklch(97% 0.005 262); --accent-ink: oklch(18% 0.05 50);
                    --font-display: "Space Grotesk", system-ui, sans-serif;
                    --font-body: "Geist Sans", -apple-system, BlinkMacSystemFont, sans-serif;
                    --font-mono: "JetBrains Mono", ui-monospace, monospace; }
            html { font-size: 16px; }
            body {
                margin: 0; padding: 0;
                background-color: #000; color: #fff;
                font-family: var(--font-body);
                overflow: hidden;
                display: flex; align-items: center; justify-content: center;
                height: 100vh; text-align: center;
                transition: background 0.3s ease, background-color 0.3s ease;
            }
            .bg-transparent { background: transparent !important; background-color: transparent !important; }
            .chroma-green { background: #00ff00 !important; background-color: #00ff00 !important; }
            .chroma-blue { background: #0000ff !important; background-color: #0000ff !important; }

            @keyframes fadeInUp {
                from { opacity: 0; transform: translateY(8px); }
                to { opacity: 1; transform: translateY(0); }
            }

            #container { width: 88%; max-width: 1200px; }
            #text {
                font-size: 3.5rem; line-height: 1.45; font-weight: 500;
                margin-bottom: 2rem;
                text-shadow: 2px 2px 8px rgba(0, 0, 0, 0.9);
                opacity: 0;
            }
            #reference {
                font-size: 2.2rem; font-weight: 700;
                color: var(--accent);
                text-transform: uppercase; letter-spacing: 2px;
                text-shadow: 2px 2px 8px rgba(0, 0, 0, 0.9);
                opacity: 0;
            }
            #container.visible #text { animation: fadeInUp 180ms cubic-bezier(0.16, 1, 0.3, 1) forwards; }
            #container.visible #reference { animation: fadeInUp 180ms cubic-bezier(0.16, 1, 0.3, 1) 120ms forwards; }

            /* ── Lecture vivante : chaque mot s'illumine quand il est prononcé ── */
            #text.karaoke .w { color: var(--unread); transition: color 0.35s ease, text-shadow 0.35s ease; }
            #text.karaoke .w.read { color: var(--read); }
            #text.karaoke .w.cur { text-shadow: 0 0 18px rgba(255, 255, 255, 0.55); }

            /* ── Sous-titre : traduction simultanée IA ── */
            #subtitle {
                position: fixed; left: 50%; bottom: 4vh; transform: translateX(-50%);
                max-width: 82%;
                background: rgba(8, 9, 12, 0.82);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 10px;
                padding: 12px 26px;
                font-size: 1.5rem; line-height: 1.4; font-weight: 500;
                opacity: 0; transition: opacity 0.3s ease;
                pointer-events: none;
            }
            #subtitle.on { opacity: 1; }
            #subtitle .lang {
                display: block; font-size: 0.7rem; font-weight: 700;
                letter-spacing: 0.14em; text-transform: uppercase;
                color: var(--accent); margin-bottom: 4px;
            }

            /* Témoin de signal (backend injoignable) */
            #signal { position: fixed; right: 14px; bottom: 12px; width: 9px; height: 9px;
                      border-radius: 50%; background: #d93025; opacity: 0; transition: opacity 0.4s; }
            #signal.lost { opacity: 0.85; }

            /* --- THEME: PRESENTATION --- */
            body.theme-presentation {
                background: radial-gradient(circle, #101114 0%, #030304 100%);
                font-family: Georgia, "Times New Roman", serif;
            }
            body.theme-presentation #text { font-weight: 400; font-style: italic; letter-spacing: 0.5px; }
            body.theme-presentation #reference { color: var(--accent); font-weight: 600; font-size: 1.8rem; }

            /* --- THEME: BROADCAST (lower third) --- */
            body.theme-broadcast { justify-content: center; align-items: flex-end; }
            body.theme-broadcast #container {
                width: 90%; max-width: 1400px;
                background: rgba(10, 11, 15, 0.85);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-left: 6px solid var(--accent);
                border-radius: 8px; padding: 24px 40px; margin-bottom: 5vh;
                box-shadow: 0 10px 30px rgba(0,0,0,0.5);
                display: flex; justify-content: space-between; align-items: center;
                gap: 40px; text-align: left; box-sizing: border-box;
            }
            body.theme-broadcast #text { font-size: 1.8rem; line-height: 1.4; margin-bottom: 0; font-weight: 450; text-shadow: none; flex: 1; }
            body.theme-broadcast #reference {
                font-size: 1.4rem; font-weight: 800; letter-spacing: 1px; text-shadow: none; flex-shrink: 0;
                background: rgba(59, 130, 246, 0.12); border: 1px solid rgba(59, 130, 246, 0.2);
                padding: 6px 16px; border-radius: 6px;
            }
            body.theme-broadcast #subtitle { display: none; }

            /* --- STYLE: FILET (défaut recommandé) ---------------------------
               Pas de cadre : le texte pose sur un voile dégradé et une seule
               règle laiton le tient. Un lower third encadré fait « carte web » ;
               la diffusion demande des arêtes franches et peu de chrome.
               Conforme à design.md : accents laiton uniquement, Geist pour le
               verset, mono pour la ligne de service.                          */
            body.theme-broadcast.style-filet { align-items: flex-end; justify-content: flex-start; }
            body.theme-broadcast.style-filet #container {
                width: 100%; max-width: none; background: none; border: none; border-radius: 0;
                box-shadow: none; margin: 0; padding: 8rem 5.5rem 3.6rem;
                display: block; text-align: left;
                background: linear-gradient(to top,
                    oklch(8% 0.01 265 / 0.92) 0%, oklch(8% 0.01 265 / 0.72) 45%, transparent 100%);
            }
            body.theme-broadcast.style-filet #container::before {
                content: ""; display: block; width: 44px; height: 3px;
                background: var(--accent); margin-bottom: 1.1rem;
            }
            body.theme-broadcast.style-filet #text {
                font-family: var(--font-body); font-size: 2.4rem; line-height: 1.32; font-weight: 400;
                color: var(--ink); margin: 0; text-shadow: none; max-width: 62ch;
            }
            body.theme-broadcast.style-filet #text.karaoke .w { color: rgba(255,255,255,0.34); }
            body.theme-broadcast.style-filet #text.karaoke .w.read { color: var(--ink); }
            body.theme-broadcast.style-filet #reference {
                display: inline-block; margin-top: 1rem; padding: 0; background: none; border: none;
                font-family: var(--font-mono); font-size: 0.88rem; font-weight: 600;
                letter-spacing: 0.14em; text-transform: uppercase; color: var(--accent);
            }
            body.theme-broadcast.style-filet #edition {
                display: inline-block; margin-left: 0.9rem;
                font-family: var(--font-mono); font-size: 0.88rem; font-weight: 500;
                letter-spacing: 0.14em; text-transform: uppercase; color: rgba(255,255,255,0.6);
            }

            /* --- STYLE: CARTOUCHE -------------------------------------------
               Bloc laiton plein à gauche, verset sur voile sombre à droite.
               Arêtes franches, aucun rayon : registre télévision. La grille
               place trois frères (#reference, #edition, #text) sans conteneur
               supplémentaire — le balisage est partagé par tous les styles.   */
            body.theme-broadcast.style-cartouche { align-items: flex-end; justify-content: flex-start; }
            body.theme-broadcast.style-cartouche #container {
                width: auto; max-width: 92%; background: none; border: none; border-radius: 0;
                box-shadow: none; padding: 0; margin: 0 0 4.6rem 0;
                display: grid; grid-template-columns: auto minmax(0, 1fr);
                grid-template-areas: "ref text" "ed text"; text-align: left; gap: 0;
                /* Le conteneur broadcast de base centre ses enfants ; en grille
                   cela empêche les deux moitiés du cartouche de s'étirer sur
                   leur rangée et ouvre une couture sombre entre elles. */
                align-items: stretch;
            }
            body.theme-broadcast.style-cartouche #reference {
                grid-area: ref; margin: 0; border: none; border-radius: 0;
                background: var(--accent); color: var(--accent-ink);
                font-family: var(--font-display); font-weight: 700; font-size: 1.75rem;
                letter-spacing: -0.01em; white-space: nowrap;
                padding: 1.1rem 1.7rem 0.15rem; display: flex; align-items: flex-end;
            }
            body.theme-broadcast.style-cartouche #edition {
                grid-area: ed; margin: 0; background: var(--accent); color: var(--accent-ink);
                font-family: var(--font-mono); font-size: 0.62rem; font-weight: 600;
                letter-spacing: 0.14em; text-transform: uppercase;
                /* Alpha sur la COULEUR seulement : une opacité d'élément
                   ternissait aussi le fond laiton et coupait le bloc en deux
                   teintes. */
                color: oklch(18% 0.05 50 / 0.72);
                padding: 0 1.7rem 1.15rem; white-space: nowrap;
            }
            body.theme-broadcast.style-cartouche #text {
                grid-area: text; margin: 0; font-family: var(--font-body); font-weight: 400;
                font-size: 1.9rem; line-height: 1.34; color: var(--ink); text-shadow: none;
                background: oklch(10% 0.012 265 / 0.93); padding: 1.2rem 2.2rem;
                display: flex; align-items: center;
            }
            body.theme-broadcast.style-cartouche #text.karaoke .w { color: rgba(255,255,255,0.34); }
            body.theme-broadcast.style-cartouche #text.karaoke .w.read { color: var(--ink); }

            /* --- HABILLAGE PERSONNALISÉ -------------------------------------
               L'église fournit son graphique ; VersePro n'y pose que le texte.
               L'image occupe tout le cadre et les zones sont positionnées en
               pourcentages, si bien que le réglage fait sur un portable reste
               juste sur le vidéoprojecteur. Aucun style de VersePro ne s'y
               applique : le design appartient entièrement au fichier fourni.  */
            #overlay-layer { position: fixed; inset: 0; display: none; z-index: 5; }
            body.has-overlay #overlay-layer { display: block; }
            /* Le graphique remplace toute mise en scène : on masque le bloc
               habituel plutôt que de le superposer à l'image. */
            body.has-overlay #container { display: none !important; }
            #overlay-image {
                position: absolute; inset: 0;
                width: 100%; height: 100%; object-fit: fill;
            }
            .overlay-zone {
                position: absolute; display: flex; box-sizing: border-box;
                overflow: hidden; text-shadow: none; white-space: pre-wrap;
                font-family: Arial, "Helvetica Neue", Helvetica, sans-serif;
            }
            .overlay-zone.font-display { font-family: var(--font-display); }
            .overlay-zone.font-serif { font-family: Georgia, "Times New Roman", serif; }
            .overlay-zone.font-mono { font-family: var(--font-mono); }
            #overlay-shapes { position: absolute; inset: 0; }
            /* Formes vectorielles : nettes à toute résolution, là où une image
               exportée pour du 1080p se dégrade sur un vidéoprojecteur 4K. */
            .overlay-shape { position: absolute; }
            .overlay-zone .overlay-inner { display: block; width: 100%; }
            .overlay-zone .vnum {
                display: inline; font-size: 0.55em; vertical-align: super;
                line-height: 0; margin-right: 0.06em;
            }

            /* --- STYLE: BANDEAU ---------------------------------------------
               Reproduction fidèle du bandeau demandé : panneau blanc quasi
               pleine largeur, étiquette turquoise posée dessus à droite, verset
               en marine gras précédé de son numéro en exposant.

               Tout est dimensionné en unités de viewport, à rebours des autres
               styles : ceux-ci héritent d'un rem figé à 16 px, si bien qu'ils
               changent d'allure entre un 720p et un 4K. Un bandeau qu'on veut
               identique trait pour trait doit garder ses proportions partout.

               Mesures relevées sur la référence (2027 × 1148) : panneau à 90 %
               de large et 15 % de haut, verset à 5 vh sur deux lignes serrées,
               marges intérieures étroites, étiquette de 5,4 vh largement
               respirée à l'horizontale et alignée sur le bord droit.          */
            body.style-bandeau, body.style-agoe, body.style-agoe-logope { align-items: flex-end; justify-content: center; }
            body.style-bandeau #container, body.style-agoe #container, body.style-agoe-logope #container {
                width: 90%; max-width: none; background: none; border: none;
                border-radius: 0; box-shadow: none; padding: 0; margin: 0 0 4.2vh 0;
                display: flex; flex-direction: column; align-items: flex-end;
                text-align: left; gap: 0; position: relative;
            }
            body.style-bandeau #reference, body.style-agoe #reference, body.style-agoe-logope #reference {
                order: -1;
                margin: 0 0 -1.4vh 0; z-index: 10; border: none; text-transform: none;
                background: linear-gradient(90deg, #1fb98f 0%, #2ed7b0 100%); color: #ffffff; text-shadow: 0 1px 2px rgba(0, 0, 0, 0.15);
                font-family: Arial, "Helvetica Neue", Helvetica, sans-serif;
                font-size: 2.7vh; font-weight: 700; letter-spacing: 0;
                white-space: nowrap; padding: 0 4.8vw; text-align: center;
                height: 5.2vh; line-height: 5.2vh;
                border-radius: 1.3vh 1.3vh 0 1.3vh;
                box-shadow: 0 4px 15px rgba(31, 185, 143, 0.35);
            }
            body.style-bandeau #text, body.style-agoe #text, body.style-agoe-logope #text {
                width: 100%; margin: 0; box-sizing: border-box;
                background: #ffffff; color: #0b1d45;
                font-family: Arial, "Helvetica Neue", Helvetica, sans-serif;
                font-size: 4.8vh; font-weight: 700; line-height: 1.25;
                text-shadow: none; padding: 2.2vh 2.5vw 2.2vh 1.8vw;
                border-radius: 2.2vh 0 5vh 2.2vh;
                box-shadow: 0 12px 35px rgba(0, 0, 0, 0.4);
            }
            body.style-bandeau #text .vnum, body.style-agoe #text .vnum, body.style-agoe-logope #text .vnum {
                display: inline; font-size: 0.6em; font-weight: 800; color: #0b1d45;
                vertical-align: super; line-height: 0; margin-right: 0.08em;
            }
            body.style-bandeau #edition, body.style-agoe #edition, body.style-agoe-logope #edition { display: none; }
            body.style-bandeau #text.karaoke .w, body.style-agoe #text.karaoke .w, body.style-agoe-logope #text.karaoke .w { color: rgba(11, 29, 69, 0.32); }
            body.style-bandeau #text.karaoke .w.read, body.style-agoe #text.karaoke .w.read, body.style-agoe-logope #text.karaoke .w.read { color: #0b1d45; }

            /* Le numéro de verset s'affiche sur les styles bandeau et agoe */
            body:not(.style-bandeau):not(.style-agoe):not(.style-agoe-logope) #text .vnum { display: none; }

            /* --- STYLE: LIGNE DE BASE ---------------------------------------
               Filet pleine largeur sous le verset, référence à gauche et
               édition à droite. Le filet naît des bordures hautes des deux
               cellules : une seule ligne continue, sans élément décoratif.    */
            body.theme-broadcast.style-ligne { align-items: flex-end; justify-content: flex-start; }
            body.theme-broadcast.style-ligne #container {
                width: 100%; max-width: none; background: none; border: none; border-radius: 0;
                box-shadow: none; margin: 0; padding: 8rem 6rem 3.4rem; text-align: left;
                /* Aucun écart entre les colonnes : le filet naît des bordures
                   hautes des deux cellules, et le moindre column-gap le coupe
                   en deux tronçons. L'air se fait au rembourrage de l'édition. */
                display: grid; grid-template-columns: 1fr auto; column-gap: 0;
                background: linear-gradient(to top, oklch(8% 0.01 265 / 0.9), transparent 78%);
            }
            body.theme-broadcast.style-ligne #text {
                grid-column: 1 / -1; margin: 0 0 1.3rem; font-family: var(--font-body);
                font-weight: 400; font-size: 2.5rem; line-height: 1.28; color: var(--ink);
                text-shadow: none; max-width: 60ch;
            }
            body.theme-broadcast.style-ligne #text.karaoke .w { color: rgba(255,255,255,0.34); }
            body.theme-broadcast.style-ligne #text.karaoke .w.read { color: var(--ink); }
            body.theme-broadcast.style-ligne #reference {
                grid-column: 1; margin: 0; padding: 0.85rem 0 0; background: none; border: none;
                border-top: 1px solid var(--accent); border-radius: 0;
                font-family: var(--font-mono); font-size: 0.84rem; font-weight: 600;
                letter-spacing: 0.15em; text-transform: uppercase; color: var(--accent);
            }
            body.theme-broadcast.style-ligne #edition {
                grid-column: 2; margin: 0; padding: 0.85rem 0 0 2.5rem;
                border-top: 1px solid oklch(90% 0.01 262 / 0.22);
                font-family: var(--font-mono); font-size: 0.84rem; font-weight: 500;
                letter-spacing: 0.15em; text-transform: uppercase;
                color: rgba(255,255,255,0.55); text-align: right; align-self: end;
            }

            /* --- THEME: SOUFFLE (adoration) ---------------------------------
               Aucun décor : le verset seul, centré, sur un halo bas. Pour les
               moments où le graphisme doit s'effacer devant le texte.         */
            body.theme-souffle { justify-content: center; align-items: flex-end; }
            body.theme-souffle #container {
                width: 100%; max-width: none; background: none; border: none; box-shadow: none;
                padding: 0 8rem 5rem; text-align: center;
                background: radial-gradient(60% 42% at 50% 100%, oklch(8% 0.01 265 / 0.86) 0%, transparent 72%);
            }
            body.theme-souffle #text {
                font-family: var(--font-body); font-size: 2.9rem; line-height: 1.34; font-weight: 400;
                color: var(--ink); margin: 0 auto; max-width: 26ch;
                text-shadow: 0 2px 24px oklch(6% 0.01 265 / 0.7);
            }
            body.theme-souffle #text.karaoke .w { color: rgba(255,255,255,0.3); }
            body.theme-souffle #text.karaoke .w.read { color: var(--ink); }
            body.theme-souffle #reference {
                display: inline-block; margin-top: 1.6rem; padding: 0; background: none; border: none;
                font-family: var(--font-mono); font-size: 0.85rem; font-weight: 600;
                letter-spacing: 0.16em; text-transform: uppercase; color: var(--accent);
            }
            body.theme-souffle #edition {
                display: inline-block; margin-left: 0.85rem;
                font-family: var(--font-mono); font-size: 0.85rem; font-weight: 500;
                letter-spacing: 0.16em; text-transform: uppercase; color: rgba(255,255,255,0.68);
            }
            body.theme-souffle #edition::before { content: "•"; margin-right: 0.85rem; color: var(--accent); }
            body.theme-souffle #subtitle { display: none; }

            /* --- THEME: CONFIDENCE (moniteur simple) --- */
            body.theme-confidence { background: #000 !important; justify-content: flex-start; align-items: flex-start; text-align: left; }
            body.theme-confidence #container { width: 95%; margin: 40px; }
            body.theme-confidence #text { font-size: 4rem; font-weight: bold; margin-bottom: 30px; text-shadow: none; }
            body.theme-confidence #reference { font-size: 3rem; color: #ff0; text-shadow: none; }

            /* --- THEME: ELEGANT (cérémonie, serif doré) --- */
            body.theme-elegant {
                background: radial-gradient(ellipse 90% 80% at 50% 30%, #14100a 0%, #050403 70%);
                font-family: Georgia, "Times New Roman", serif;
            }
            body.theme-elegant #text {
                font-size: 3.8rem; font-weight: 400; line-height: 1.5;
                color: #f5efe2; letter-spacing: 0.3px; text-shadow: none;
            }
            body.theme-elegant #text.karaoke .w { color: rgba(245, 239, 226, 0.3); }
            body.theme-elegant #text.karaoke .w.read { color: #f5efe2; }
            body.theme-elegant #text.karaoke .w.cur { text-shadow: 0 0 22px rgba(226, 184, 101, 0.6); }
            body.theme-elegant #reference {
                color: #e2b865; font-size: 1.6rem; font-weight: 600;
                letter-spacing: 0.35em; text-shadow: none;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            }
            body.theme-elegant #reference::before,
            body.theme-elegant #reference::after { content: "—"; margin: 0 18px; color: rgba(226, 184, 101, 0.4); }

            /* --- THEME: MINIMAL (typographie géante) --- */
            body.theme-minimal { background: #000; }
            body.theme-minimal #container { width: 92%; max-width: 1500px; text-align: left; }
            body.theme-minimal #text {
                font-size: 4.6rem; font-weight: 750; line-height: 1.22;
                letter-spacing: -0.015em; text-shadow: none; margin-bottom: 2.5rem;
            }
            body.theme-minimal #text.karaoke .w { color: rgba(255, 255, 255, 0.22); }
            body.theme-minimal #text.karaoke .w.read { color: #ffffff; }
            body.theme-minimal #reference {
                font-size: 1.3rem; font-weight: 600; color: #8e8e93;
                letter-spacing: 0.2em; text-shadow: none;
            }

            /* --- THEME: DUAL (multi-versions) --- */
             body.theme-dual #container { width: 90%; max-width: 1300px; text-align: left; }
            body.theme-dual .split-columns { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 40px; }
            body.theme-dual .split-col { border-left: 3px solid rgba(255,255,255,0.15); padding-left: 20px; }
            body.theme-dual .split-ver { font-size: 1.8rem; line-height: 1.5; color: #f3f4f6; margin-bottom: 12px; opacity: 0; }
            body.theme-dual .split-label { font-size: 11px; font-weight: bold; color: #9ca3af; text-transform: uppercase; letter-spacing: 1px; opacity: 0; }
            body.theme-dual #container.visible .split-ver { animation: fadeInUp 180ms cubic-bezier(0.16, 1, 0.3, 1) forwards; }
            body.theme-dual #container.visible .split-label { animation: fadeInUp 180ms cubic-bezier(0.16, 1, 0.3, 1) 120ms forwards; }

            /* --- NOUVEAUX STYLES DE BROADCAST --- */

            /* Style: glass (Frosted Glassmorphism - Moderne) */
            body.theme-broadcast.style-glass #container {
                background: rgba(15, 17, 24, 0.65);
                backdrop-filter: blur(12px) saturate(160%);
                -webkit-backdrop-filter: blur(12px) saturate(160%);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 16px;
                padding: 22px 36px;
                display: flex;
                justify-content: space-between;
                align-items: center;
                gap: 28px;
                box-shadow: 0 10px 40px rgba(0, 0, 0, 0.35), inset 0 1px 0 rgba(255, 255, 255, 0.1);
            }
            body.theme-broadcast.style-glass #text {
                font-size: 1.6rem;
                color: rgba(255, 255, 255, 0.95);
                text-shadow: none;
                margin-bottom: 0;
                flex: 1;
                font-weight: 400;
            }
            body.theme-broadcast.style-glass #text.karaoke .w { color: rgba(255, 255, 255, 0.32); }
            body.theme-broadcast.style-glass #text.karaoke .w.read { color: #ffffff; }
            body.theme-broadcast.style-glass #reference {
                background: linear-gradient(135deg, oklch(70% 0.16 265) 0%, oklch(60% 0.15 285) 100%);
                color: #ffffff;
                border: none;
                font-size: 1.1rem;
                font-weight: 700;
                border-radius: 8px;
                padding: 8px 20px;
                text-shadow: 0 1px 2px rgba(0,0,0,0.25);
                box-shadow: 0 4px 12px rgba(123, 131, 235, 0.25);
                flex-shrink: 0;
            }

            /* Style: neon-glow (Cyberpunk Minimalist) */
            body.theme-broadcast.style-neon-glow #container {
                background: transparent;
                border: none;
                border-radius: 0;
                padding: 16px 20px;
                display: flex;
                justify-content: space-between;
                align-items: center;
                gap: 32px;
                box-shadow: none;
            }
            body.theme-broadcast.style-neon-glow #text {
                font-size: 1.7rem;
                color: #ffffff;
                font-weight: 600;
                text-shadow: 0 2px 10px rgba(0, 0, 0, 0.85);
                margin-bottom: 0;
                flex: 1;
            }
            body.theme-broadcast.style-neon-glow #text.karaoke .w { color: rgba(255, 255, 255, 0.35); text-shadow: 0 2px 10px rgba(0, 0, 0, 0.85); }
            body.theme-broadcast.style-neon-glow #text.karaoke .w.read { color: #ffffff; text-shadow: 0 0 12px rgba(255,255,255,0.4); }
            body.theme-broadcast.style-neon-glow #reference {
                background: #000000;
                color: oklch(76% 0.17 50);
                border: 2px solid oklch(76% 0.17 50);
                font-size: 1.15rem;
                font-weight: 800;
                border-radius: 4px;
                padding: 6px 18px;
                text-shadow: none;
                box-shadow: 0 0 15px rgba(253, 186, 116, 0.25);
                flex-shrink: 0;
            }

            /* Style: elegant-serif (Georgia Dorée - Vantage) */
            body.theme-broadcast.style-elegant-serif #container {
                background: rgba(20, 16, 10, 0.94);
                border: none;
                border-left: 4px solid #e2b865;
                border-radius: 4px;
                padding: 20px 36px;
                display: flex;
                justify-content: space-between;
                align-items: center;
                gap: 28px;
                box-shadow: 0 8px 32px rgba(0,0,0,0.5);
                font-family: Georgia, "Times New Roman", serif;
            }
            body.theme-broadcast.style-elegant-serif #text {
                font-size: 1.6rem;
                font-style: italic;
                color: #f5efe2;
                text-shadow: none;
                margin-bottom: 0;
                flex: 1;
            }
            body.theme-broadcast.style-elegant-serif #text.karaoke .w { color: rgba(245, 239, 226, 0.35); }
            body.theme-broadcast.style-elegant-serif #text.karaoke .w.read { color: #f5efe2; }
            body.theme-broadcast.style-elegant-serif #reference {
                color: #e2b865;
                font-size: 1.1rem;
                font-weight: 600;
                border: none;
                padding: 0;
                margin: 0;
                text-shadow: none;
                flex-shrink: 0;
                text-transform: uppercase;
                letter-spacing: 2px;
            }

            /* Style: pill (Capsule Moderne - Image 1) */
            body.theme-broadcast.style-pill #container {
                background: rgba(18, 20, 26, 0.88);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 9999px;
                padding: 16px 36px 16px 48px;
                display: flex;
                justify-content: space-between;
                align-items: center;
                gap: 24px;
                box-shadow: 0 10px 40px rgba(0,0,0,0.5);
            }
            body.theme-broadcast.style-pill #text {
                font-size: 1.55rem;
                color: #f3f4f6;
                margin-bottom: 0;
                text-shadow: none;
                flex: 1;
            }
            body.theme-broadcast.style-pill #reference {
                background: oklch(0.85 0.18 112); /* Jaune/Vert néon */
                color: #0c1c0c;
                border: none;
                font-size: 1.1rem;
                font-weight: 800;
                border-radius: 9999px;
                padding: 6px 20px;
                text-shadow: none;
                flex-shrink: 0;
            }

            /* Style: sage (Sauge & Terracotta - Image 2) */
            body.theme-broadcast.style-sage #container {
                background: rgba(148, 166, 149, 0.94); /* Vert sauge */
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 24px;
                padding: 24px 44px;
                display: flex;
                justify-content: space-between;
                align-items: center;
                gap: 32px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.3);
            }
            body.theme-broadcast.style-sage #text {
                font-size: 1.6rem;
                color: #121813;
                font-weight: 600;
                text-shadow: none;
                margin-bottom: 0;
                flex: 1;
            }
            body.theme-broadcast.style-sage #text.karaoke .w { color: rgba(18, 24, 19, 0.35); }
            body.theme-broadcast.style-sage #text.karaoke .w.read { color: #121813; }
            body.theme-broadcast.style-sage #reference {
                background: oklch(0.55 0.14 32); /* Terracotta */
                color: #ffffff;
                border: none;
                font-size: 1.15rem;
                border-radius: 9999px;
                padding: 8px 24px;
                text-shadow: none;
                flex-shrink: 0;
            }

            /* Style: split (Barre Complète Divisée - Image 4) */
            body.theme-broadcast.style-split {
                align-items: flex-end;
            }
            body.theme-broadcast.style-split #container {
                width: 100%;
                max-width: 100%;
                margin-bottom: 0;
                background: #0d0e12;
                border: none;
                border-top: 2px solid oklch(0.62 0.17 29); /* Ligne rouge */
                border-radius: 0;
                padding: 0;
                display: grid;
                grid-template-columns: 320px 1fr;
                align-items: stretch;
                box-shadow: 0 -10px 40px rgba(0,0,0,0.6);
            }
            body.theme-broadcast.style-split #reference {
                background: #090a0d;
                color: #ffffff;
                border: none;
                border-radius: 0;
                padding: 24px;
                display: flex;
                flex-direction: column;
                justify-content: center;
                align-items: center;
                font-size: 1.3rem;
                font-weight: 700;
                border-right: 1px solid rgba(255, 255, 255, 0.05);
            }
            body.theme-broadcast.style-split #text {
                padding: 24px 48px;
                font-size: 1.65rem;
                color: #f3f4f6;
                margin: 0;
                text-shadow: none;
                display: flex;
                align-items: center;
                text-align: left;
                flex: 1;
            }

            /* --- NOUVEAUX THÈMES PLEIN ÉCRAN / SOCIAL --- */

            /* Thème: poster (Cadre Vertical Sacré - Image 3) */
            body.theme-poster {
                background: radial-gradient(circle, #3d080c 0%, #120204 100%);
                display: flex;
                align-items: center;
                justify-content: center;
            }
            body.theme-poster #container {
                width: 580px;
                height: 720px;
                background: #ffffff;
                border-radius: 40px;
                box-shadow: 0 30px 90px rgba(0, 0, 0, 0.6);
                padding: 60px 48px;
                display: flex;
                flex-direction: column;
                justify-content: space-between;
                align-items: center;
                box-sizing: border-box;
                position: relative;
            }
            /* Badge Logo fictif en haut */
            body.theme-poster #container::before {
                content: "VP";
                display: flex;
                align-items: center;
                justify-content: center;
                width: 60px;
                height: 60px;
                border-radius: 50%;
                background: #0d0d0d;
                color: #ffffff;
                font-weight: 800;
                font-size: 1.2rem;
                border: 4px solid #ffffff;
                position: absolute;
                top: -30px;
                box-shadow: 0 10px 25px rgba(0,0,0,0.15);
            }
            body.theme-poster #text {
                font-size: 2.1rem;
                line-height: 1.6;
                color: #1a1a1a;
                font-weight: 500;
                margin: auto 0;
                text-shadow: none;
            }
            body.theme-poster #text.karaoke .w { color: rgba(26, 26, 26, 0.3); }
            body.theme-poster #text.karaoke .w.read { color: #1a1a1a; }
            body.theme-poster #reference {
                width: 100%;
                text-align: center;
                color: #990000;
                font-size: 1.4rem;
                font-weight: 800;
                border-top: 2px solid #e6e6e6;
                padding-top: 20px;
                text-shadow: none;
            }

            /* Thème: story (Carte Rétro avec Filigrane - Image 5) */
            body.theme-story {
                background: linear-gradient(135deg, #0e1e24 0%, #18333c 100%);
                display: flex;
                align-items: center;
                justify-content: center;
                position: relative;
                overflow: hidden;
            }
            /* Grand filigrane en arrière-plan */
            body.theme-story::before {
                content: "VP";
                position: absolute;
                font-size: 32rem;
                font-weight: 900;
                color: rgba(255, 255, 255, 0.035);
                line-height: 1;
                z-index: 0;
                left: -40px;
                bottom: -60px;
                pointer-events: none;
            }
            body.theme-story #container {
                z-index: 1;
                width: 620px;
                background: oklch(0.38 0.12 165); /* Vert émeraude/forêt profond */
                border-radius: 32px;
                box-shadow: 0 35px 80px rgba(0, 0, 0, 0.5);
                padding: 48px;
                display: flex;
                flex-direction: column;
                gap: 24px;
                position: relative;
                box-sizing: border-box;
            }
            /* Ruban "étiquette" en bas à droite */
            body.theme-story #container::after {
                content: "VERSEPRO";
                position: absolute;
                right: 24px;
                bottom: -12px;
                background: #ffffff;
                color: #121813;
                font-size: 10px;
                font-weight: 800;
                padding: 6px 16px;
                border-radius: 4px;
                box-shadow: 0 4px 10px rgba(0,0,0,0.1);
                letter-spacing: 0.1em;
            }
            body.theme-story #reference {
                color: #ffffff;
                font-family: "Impact", "Arial Black", sans-serif;
                font-size: 2.8rem;
                text-transform: uppercase;
                text-align: left;
                border: none;
                padding: 0;
                margin: 0;
                letter-spacing: 1px;
                text-shadow: none;
            }
            body.theme-story #text {
                font-size: 1.8rem;
                line-height: 1.5;
                color: #e6f2ec;
                font-weight: 450;
                text-align: left;
                text-shadow: none;
                margin-bottom: 20px;
            }
            body.theme-story #text.karaoke .w { color: rgba(230, 242, 236, 0.35); }
            body.theme-story #text.karaoke .w.read { color: #ffffff; }
        </style>
    </head>
    <body>
        <!-- Habillage fourni par l'église : image plein cadre et zones de
             texte. Reste vide et masqué tant qu'aucun PNG n'est installé. -->
        <div id="overlay-layer">
            <img id="overlay-image" alt="">
            <!-- Formes construites dans VersePro, entre l'image et les textes :
                 une église sans graphiste compose son bandeau ici. -->
            <div id="overlay-shapes"></div>
            <!-- Le texte vit dans un enfant : la zone est en flex pour son
                 alignement vertical, et un flex y ferait de l'exposant un
                 élément de rangée au lieu de le laisser couler dans la phrase. -->
            <div class="overlay-zone" id="overlay-text"><span class="overlay-inner"></span></div>
            <div class="overlay-zone" id="overlay-reference"><span class="overlay-inner"></span></div>
        </div>
        <div id="container">
            <div id="text">En attente d'affichage...</div>
            <div id="reference"></div>
            <!-- Édition en toutes lettres, à côté de la référence. Masquée par
                 défaut : seuls les styles qui la mettent en scène l'affichent,
                 les autres gardent le sigle entre parenthèses. -->
            <div id="edition" style="display: none;"></div>
            <div id="split-container" style="display: none;">
                <div class="split-columns" id="split-cols"></div>
            </div>
        </div>
        <div id="subtitle"><span class="lang"></span><span class="txt"></span></div>
        <div id="signal"></div>

        <script>
            const container = document.getElementById('container');
            const textEl = document.getElementById('text');
            const refEl = document.getElementById('reference');
            const splitContainer = document.getElementById('split-container');
            const splitCols = document.getElementById('split-cols');
            const subtitleEl = document.getElementById('subtitle');
            const signalEl = document.getElementById('signal');

            const params = new URLSearchParams(window.location.search);
            const forcedBg = params.get('bg');
            const forcedTheme = params.get('theme');
            const scale = parseFloat(params.get('scale') || '1');
            const subtitlesEnabled = params.get('subtitle') !== 'off';
            // Mode démonstration : sert les aperçus de réglages. Tant qu'aucun
            // verset n'est projeté, la page reste noire — un opérateur qui
            // compare des styles avant le culte ne verrait donc rien. Le verset
            // d'exemple ne s'affiche JAMAIS sur un écran de projection : il faut
            // le demander explicitement par l'URL.
            const modeDemo = params.get('demo') === '1';
            const SCENE_DEMO = {
                type: 'scripture',
                text: "Lorsque Moïse élevait sa main, Israël était le plus fort; et lorsqu'il baissait sa main, Amalek était le plus fort.",
                reference: 'Exode 17:11',
                book: 'Exode', chapter: 17, verse_start: 11,
                active_version: 'LSG', active_version_label: 'Louis Segond 1910',
                show_version: true, background: 'black',
                translations: {
                    LSG: "Lorsque Moïse élevait sa main, Israël était le plus fort; et lorsqu'il baissait sa main, Amalek était le plus fort.",
                    SEM: "Tant que Moïse tenait ses mains levées, Israël était le plus fort, mais dès qu'il les laissait retomber, Amalek l'emportait."
                }
            };
            // Le zoom s'applique à TOUS les thèmes (tout est dimensionné en rem)
            if (scale && scale !== 1) document.documentElement.style.fontSize = (16 * scale) + 'px';

            let currentKey = null;
            let subtitleTimer = null;

            // Rendu du texte en mots individuels (Lecture vivante) — DOM sûr, pas d'innerHTML
            function renderWords(text, verseNum) {
                textEl.textContent = '';
                // La lecture vivante éteint les mots non encore prononcés (34 %
                // d'opacité). Poser « karaoke » dès le rendu affichait TOUT le
                // verset en gris tant qu'aucune voix ne le suivait : projection
                // manuelle, micro coupé, simple silence. Le verset attendait une
                // lecture qui ne venait pas. On n'arme le suivi qu'au premier
                // événement de progression — voir applyProgress.
                textEl.classList.remove('karaoke');
                // Numéro de verset en exposant, à la manière d'une bible
                // imprimée. Hors du flux des mots (.w) pour ne pas fausser le
                // suivi karaoké, et masqué tant qu'un style ne l'appelle pas.
                if (verseNum !== undefined && verseNum !== null && verseNum !== '') {
                    const sup = document.createElement('sup');
                    sup.className = 'vnum';
                    sup.textContent = verseNum;
                    textEl.appendChild(sup);
                }
        (text || '').split(/\\s+/).filter(Boolean).forEach((word) => {
                    const span = document.createElement('span');
                    span.className = 'w';
                    span.textContent = word;
                    textEl.appendChild(span);
                    textEl.appendChild(document.createTextNode(' '));
                });
            }

            function applyProgress(matched) {
                const spans = textEl.querySelectorAll('.w');
                if (!spans.length) return;
                // Une voix suit réellement le texte : on peut armer l'extinction
                // des mots à venir. Sans cette garde, un verset projeté sans
                // lecture restait gris de bout en bout devant l'assemblée.
                if (matched > 0) textEl.classList.add('karaoke');
                spans.forEach((span, i) => {
                    span.classList.toggle('read', i < matched);
                    span.classList.toggle('cur', i === matched - 1);
                });
            }

             function getFullReference(data) {
                if (!data) return '';
                if (!data.book) return data.reference || '';
                let ref = data.book + ' ' + data.chapter;
                if (data.verse_start !== undefined && data.verse_start !== null) {
                    ref += ':' + data.verse_start;
                    if (data.verse_end) {
                        ref += '-' + data.verse_end;
                    }
                }
                if (data.active_version && data.show_version !== false) {
                    ref += ' (' + data.active_version + ')';
                }
                return ref;
            }

            // ── Habillage personnalisé ───────────────────────────────────────
            const overlayLayer = document.getElementById('overlay-layer');
            const overlayImage = document.getElementById('overlay-image');
            const overlayZones = {
                text: document.getElementById('overlay-text'),
                reference: document.getElementById('overlay-reference')
            };
            let overlayVersion = null;

            function applyZone(el, zone) {
                if (!el || !zone) return;
                el.style.left = zone.x + '%';
                el.style.top = zone.y + '%';
                el.style.width = zone.w + '%';
                el.style.height = zone.h + '%';
                // La taille suit la HAUTEUR du cadre : c'est ce qui garde les
                // proportions identiques d'un 720p à un 4K.
                el.style.fontSize = zone.size + 'vh';
                el.style.lineHeight = zone.line;
                el.style.color = zone.color;
                el.style.fontWeight = zone.weight;
                el.style.textAlign = zone.align;
                el.style.justifyContent =
                    zone.align === 'center' ? 'center' : zone.align === 'right' ? 'flex-end' : 'flex-start';
                el.style.alignItems =
                    zone.valign === 'middle' ? 'center' : zone.valign === 'bottom' ? 'flex-end' : 'flex-start';
                el.className = 'overlay-zone font-' + zone.font;
            }

            // Contour d'une forme, coin par coin. Doit rester le jumeau exact de
            // shape_geometry.py, qui sert la sortie NDI : mêmes angles, même
            // ordre, même nombre de segments.
            const SEGMENTS_ARC = 10;
            function contourForme(L, H, coins) {
                const limite = Math.max(0, Math.min(L, H) / 2);
                const r = [], m = [];
                for (let i = 0; i < 4; i++) {
                    const c = (coins && coins[i]) || {};
                    r.push(Math.max(0, Math.min(limite, Number(c.r) || 0)));
                    m.push(['out', 'in', 'cut'].includes(c.mode) ? c.mode : 'out');
                }
                const P = Math.PI;
                const sommets = [[0, 0], [L, 0], [L, H], [0, H]];
                const entrees = [[0, r[0]], [L - r[1], 0], [L, H - r[2]], [r[3], H]];
                const sorties = [[r[0], 0], [L, r[1]], [L - r[2], H], [0, H - r[3]]];
                const centres = [[r[0], r[0]], [L - r[1], r[1]], [L - r[2], H - r[2]], [r[3], H - r[3]]];
                const angles = [[P, 1.5 * P], [1.5 * P, 2 * P], [0, 0.5 * P], [0.5 * P, P]];
                const rentrants = [[0.5 * P, 0], [P, 0.5 * P], [1.5 * P, P], [0, -0.5 * P]];
                const pts = [];
                const arc = (centre, rayon, a, b) => {
                    for (let i = 0; i <= SEGMENTS_ARC; i++) {
                        const t = a + (b - a) * i / SEGMENTS_ARC;
                        pts.push([centre[0] + rayon * Math.cos(t), centre[1] + rayon * Math.sin(t)]);
                    }
                };
                for (let i = 0; i < 4; i++) {
                    if (r[i] <= 0) { pts.push(sommets[i]); continue; }
                    pts.push(entrees[i]);
                    if (m[i] === 'in') arc(sommets[i], r[i], rentrants[i][0], rentrants[i][1]);
                    else if (m[i] !== 'cut') arc(centres[i], r[i], angles[i][0], angles[i][1]);
                    pts.push(sorties[i]);
                }
                return pts;
            }

            function renderShapes(formes) {
                const hote = document.getElementById('overlay-shapes');
                hote.textContent = '';
                // Les coins peuvent être creusés ou biseautés : border-radius ne
                // sait faire que l'arrondi sortant, on trace donc le contour.
                const cadreL = window.innerWidth, cadreH = window.innerHeight;
                (formes || []).forEach((f) => {
                    const L = f.w * cadreL / 100, H = f.h * cadreH / 100;
                    const coins = (f.corners && f.corners.length)
                        ? f.corners.map((c) => ({ r: (c.r || 0) * cadreH / 100, mode: c.mode }))
                        : Array.from({ length: 4 }, () => ({ r: (f.radius || 0) * cadreH / 100, mode: 'out' }));
                    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
                    svg.setAttribute('class', 'overlay-shape');
                    svg.setAttribute('viewBox', `0 0 ${L} ${H}`);
                    svg.setAttribute('preserveAspectRatio', 'none');
                    svg.style.left = f.x + '%';
                    svg.style.top = f.y + '%';
                    svg.style.width = f.w + '%';
                    svg.style.height = f.h + '%';
                    svg.style.opacity = f.opacity;
                    const poly = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
                    poly.setAttribute('points', contourForme(L, H, coins).map((p) => p.join(',')).join(' '));
                    poly.setAttribute('fill', f.fill);
                    svg.appendChild(poly);
                    hote.appendChild(svg);
                });
            }

            // Les contours sont calculés en pixels : un changement de taille de
            // fenêtre doit les refaire, sinon les coins se déforment.
            let dernieresFormes = null;
            window.addEventListener('resize', () => {
                if (dernieresFormes) renderShapes(dernieresFormes);
            });

            function renderOverlay(data) {
                const info = data.overlay;
                const formes = (info && info.shapes) || [];
                const forcedStyle = params.get('style') || data.style || '';
                const estHabillageStyle = forcedStyle.startsWith('habillage:');
                // En mode aperçu des thèmes (boîte d'aperçu des paramètres), on laisse
                // l'opérateur prévisualiser librement tous les thèmes standards (presentation,
                // agoe-logope, glass, dual, etc.). L'habillage ne s'affiche dans l'aperçu
                // que si un habillage spécifique est sélectionné dans le menu.
                if ((modeDemo && !estHabillageStyle) || !info || (!info.image_url && !formes.length)) {
                    document.body.classList.remove('has-overlay');
                    return false;
                }
                // L'URL vient du serveur : elle désigne l'habillage courant ou
                // celui d'un préréglage, et porte sa version pour le cache.
                const urlImage = info.image_url || '';
                overlayImage.style.display = urlImage ? '' : 'none';
                if (urlImage && overlayVersion !== urlImage) {
                    overlayVersion = urlImage;
                    overlayImage.src = urlImage;
                }
                dernieresFormes = formes;
                renderShapes(formes);
                const zones = info.zones || {};
                applyZone(overlayZones.text, zones.text);
                applyZone(overlayZones.reference, zones.reference);
                const dedansRef = overlayZones.reference.querySelector('.overlay-inner');
                const dedansTexte = overlayZones.text.querySelector('.overlay-inner');
                dedansRef.textContent = getFullReference(data);
                dedansTexte.textContent = '';
                if (data.verse_start !== undefined && data.verse_start !== null) {
                    const sup = document.createElement('sup');
                    sup.className = 'vnum';
                    sup.textContent = data.verse_start;
                    dedansTexte.appendChild(sup);
                }
                dedansTexte.appendChild(document.createTextNode(data.text || ''));
                document.body.classList.add('has-overlay');
                return true;
            }

            function renderScene(data) {
                const bg = forcedBg || data.background;
                document.body.className = '';
                if (bg === 'transparent') document.body.classList.add('bg-transparent');
                else if (bg === 'green') document.body.classList.add('chroma-green');
                else if (bg === 'blue') document.body.classList.add('chroma-blue');

                const theme = forcedTheme || data.theme || 'presentation';
                document.body.classList.add('theme-' + theme);

                const forcedStyle = params.get('style') || data.style;
                if (forcedStyle) {
                    document.body.classList.add('style-' + forcedStyle);
                }

                // Après les classes : renderScene remet className à zéro, et
                // « has-overlay » serait effacé s'il était posé plus tôt.
                const overlayActif = renderOverlay(data);

                // Même verset (changement de thème/fond seulement) : pas de re-animation
                const fullRef = getFullReference(data);
                const key = fullRef + '|' + (data.text || '') + '|' + theme + '|' + (forcedStyle || '')
                    + '|' + (overlayActif ? (data.overlay.updated_at
                        + JSON.stringify(data.overlay.zones) + JSON.stringify(data.overlay.shapes)) : '');
                if (key === currentKey) return;
                currentKey = key;

                container.classList.remove('visible');
                setTimeout(() => {
                    splitContainer.style.display = 'none';
                    textEl.style.display = 'block';
                    // Style inline volontairement vidé plutôt que forcé à
                    // « block » : les styles qui posent la référence et l'édition
                    // sur une même ligne les déclarent inline-block en CSS, et un
                    // style inline l'emporterait sur eux.
                    refEl.style.display = '';

                    const translations = data.translations || {};
                    if (theme === 'dual' && Object.keys(translations).length > 1) {
                        textEl.style.display = 'none';
                        refEl.style.display = 'none';
                        splitContainer.style.display = 'block';
                        splitCols.textContent = '';
                        
                        let versionsToShow = [];
                        const versionsParam = params.get('versions');
                        if (versionsParam) {
                            versionsToShow = versionsParam.split(',').map(v => v.trim().toUpperCase());
                        } else if (data.dual_translations) {
                            versionsToShow = data.dual_translations.split(',').map(v => v.trim().toUpperCase());
                        } else {
                            const active = data.active_version || 'LSG';
                            versionsToShow = [active];
                            Object.keys(translations).forEach(v => {
                                if (v !== active && versionsToShow.length < 2) {
                                    versionsToShow.push(v);
                                }
                            });
                        }

                        versionsToShow.forEach((version) => {
                            const txt = translations[version];
                            if (!txt) return;
                            const col = document.createElement('div');
                            col.className = 'split-col';
                            const ver = document.createElement('div');
                            ver.className = 'split-ver';
                            ver.textContent = txt;
                            const label = document.createElement('div');
                            label.className = 'split-label';
                            const showVer = data.show_version !== false;
                            label.textContent = (showVer ? version + ' — ' : '') + getFullReference({...data, show_version: false});
                            col.appendChild(ver);
                            col.appendChild(label);
                            splitCols.appendChild(col);
                        });
                    } else {
                        renderWords(data.text, data.verse_start);
                        // Les styles « filet » et « souffle » portent l'édition dans
                        // un élément propre, en toutes lettres : « Louis Segond 1910 »
                        // plutôt qu'un « (LSG) » que personne dans l'assemblée ne sait
                        // lire. Les autres gardent le sigle collé à la référence.
                        const editionEl = document.getElementById('edition');
                        const spelled = ['style-filet', 'style-cartouche', 'style-ligne', 'theme-souffle']
                            .some((c) => document.body.classList.contains(c));
                        if (spelled && data.show_version !== false && data.active_version_label) {
                            refEl.textContent = getFullReference({...data, show_version: false});
                            editionEl.textContent = data.active_version_label;
                            editionEl.style.display = '';
                        } else {
                            refEl.textContent = fullRef;
                            editionEl.style.display = 'none';
                        }
                    }

                    if (data.text || data.reference) container.classList.add('visible');
                }, 150);
            }

            function showSubtitle(data) {
                if (!subtitlesEnabled) return;
                subtitleEl.querySelector('.lang').textContent = (data.lang || '').toUpperCase();
                subtitleEl.querySelector('.txt').textContent = data.text || '';
                subtitleEl.classList.add('on');
                clearTimeout(subtitleTimer);
                subtitleTimer = setTimeout(() => subtitleEl.classList.remove('on'), 7000);
            }

            let ws;
            function connect() {
                const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                ws = new WebSocket(`${proto}//${window.location.host}/ws/output`);
                ws.onopen = () => { signalEl.classList.remove('lost'); container.classList.add('visible'); };
                ws.onmessage = (event) => {
                    const data = JSON.parse(event.data);
                    if (data.type === 'reading_progress') { applyProgress(data.matched); return; }
                    if (data.type === 'live_translation') { showSubtitle(data); return; }
                    if (data.type && data.type !== 'scripture') return;
                    // En aperçu, tant qu'aucun verset n'est projeté on montre
                    // l'exemple ; l'habillage et les réglages restent ceux du
                    // serveur. La RÉFÉRENCE est le signal fiable : la scène au
                    // repos porte déjà le texte « En attente d'affichage… ».
                    if (modeDemo && !data.reference) {
                        renderScene({ ...data, ...SCENE_DEMO });
                        return;
                    }
                    renderScene(data);
                };
                ws.onclose = () => { signalEl.classList.add('lost'); setTimeout(connect, 2000); };
            }
            connect();
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


@app.get("/stage", response_class=HTMLResponse)
async def get_stage_display():
    """
    Moniteur prédicateur (« stage display ») : verset courant avec lecture
    vivante, horloge, et verset SUIVANT pré-affiché. Ce que ProPresenter vend
    en option, en mieux : l'écran sait où en est la lecture.
    """
    html_content = """
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>VersePro — Moniteur prédicateur</title>
        <style>
            :root { color-scheme: dark; }
            * { box-sizing: border-box; }
            body {
                margin: 0; height: 100vh; overflow: hidden;
                background: #000; color: #fff;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
                display: flex; flex-direction: column;
                padding: 3.5vh 4vw;
            }
            header { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 3vh; }
            #reference { font-size: 3.2vw; font-weight: 800; color: oklch(76% 0.17 50); letter-spacing: 0.04em; text-transform: uppercase; }
            #clock { font-family: ui-monospace, "SF Mono", Menlo, monospace; font-size: 3.2vw; font-weight: 700; color: #fff; }
            main { flex: 1; display: flex; align-items: center; }
            #text { font-size: 4.2vw; line-height: 1.4; font-weight: 600; }
            #text .w { color: rgba(255, 255, 255, 0.36); transition: color 0.3s ease; }
            #text .w.read { color: #fff; }
            #text .w.cur { color: oklch(76% 0.17 50); }
            footer { border-top: 2px solid rgba(255, 255, 255, 0.14); padding-top: 2.2vh; min-height: 16vh; }
            footer .label { font-size: 1.2vw; font-weight: 800; letter-spacing: 0.16em; color: #30d158; text-transform: uppercase; }
            #next-text {
                margin-top: 0.8vh; font-size: 2.1vw; line-height: 1.4; color: rgba(255, 255, 255, 0.6);
                display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
            }
            .waiting { color: rgba(255,255,255,0.35); }
            #signal { position: fixed; right: 14px; bottom: 12px; width: 9px; height: 9px;
                      border-radius: 50%; background: #d93025; opacity: 0; transition: opacity 0.4s; }
            #signal.lost { opacity: 0.85; }
        </style>
    </head>
    <body>
        <header>
            <div id="reference">—</div>
            <div id="clock">--:--:--</div>
        </header>
        <main><div id="text" class="waiting">En attente du prochain verset…</div></main>
        <footer>
            <span class="label" id="next-label">Suivant</span>
            <div id="next-text">—</div>
        </footer>
        <div id="signal"></div>
        <script>
            const refEl = document.getElementById('reference');
            const textEl = document.getElementById('text');
            const clockEl = document.getElementById('clock');
            const nextLabel = document.getElementById('next-label');
            const nextText = document.getElementById('next-text');

            setInterval(() => {
                clockEl.textContent = new Date().toLocaleTimeString('fr-FR');
            }, 1000);

            function renderWords(text) {
                textEl.textContent = '';
                textEl.classList.remove('waiting');
        (text || '').split(/\\s+/).filter(Boolean).forEach((word) => {
                    const span = document.createElement('span');
                    span.className = 'w';
                    span.textContent = word;
                    textEl.appendChild(span);
                    textEl.appendChild(document.createTextNode(' '));
                });
            }

            function applyProgress(matched) {
                const spans = textEl.querySelectorAll('.w');
                spans.forEach((span, i) => {
                    span.classList.toggle('read', i < matched);
                    span.classList.toggle('cur', i === matched - 1);
                });
            }

            function getFullReference(data) {
                if (!data) return '';
                if (!data.book) return data.reference || '';
                let ref = data.book + ' ' + data.chapter;
                if (data.verse_start !== undefined && data.verse_start !== null) {
                    ref += ':' + data.verse_start;
                    if (data.verse_end) {
                        ref += '-' + data.verse_end;
                    }
                }
                if (data.active_version && data.show_version !== false) {
                    ref += ' (' + data.active_version + ')';
                }
                return ref;
            }

            function renderScene(data) {
                const fullRef = getFullReference(data);
                refEl.textContent = fullRef || '—';
                if (data.text) {
                    renderWords(data.text);
                } else {
                    textEl.classList.add('waiting');
                    textEl.textContent = 'En attente du prochain verset…';
                }
                nextLabel.textContent = data.next_reference ? ('Suivant · ' + data.next_reference) : 'Suivant';
                nextText.textContent = data.next_text || '—';
            }

            const signalEl = document.getElementById('signal');
            let ws;
            function connect() {
                const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                const url = `${proto}//${window.location.host}/ws/output`;
                console.log('⏳ [Moniteur] Tentative de connexion WebSocket sur', url);
                ws = new WebSocket(url);
                ws.onopen = () => {
                    console.log('✅ [Moniteur] WebSocket connecté !');
                    signalEl.classList.remove('lost');
                };
                ws.onmessage = (event) => {
                    const data = JSON.parse(event.data);
                    console.log('📥 [Moniteur] Message reçu :', data);
                    if (data.type === 'reading_progress') { 
                        applyProgress(data.matched); 
                        return; 
                    }
                    if (data.type && data.type !== 'scripture') return;
                    renderScene(data);
                };
                ws.onclose = () => {
                    console.warn('❌ [Moniteur] WebSocket déconnecté. Reconnexion dans 2s...');
                    signalEl.classList.add('lost');
                    setTimeout(connect, 2000);
                };
            }
            connect();
        </script>
    </body>
    </html>
    """
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

    html_content = """
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <meta name="theme-color" content="#0a0b0d">
        <title>VersePro — Suivre le culte</title>
        <style>
            :root { color-scheme: dark; }
            * { box-sizing: border-box; }
            body {
                margin: 0;
                min-height: 100vh;
                background: #0a0b0d;
                color: #f0f1f3;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                display: flex;
                flex-direction: column;
            }
            header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 12px;
                padding: 14px 18px;
                border-bottom: 1px solid #25262b;
            }
            header .brand { font-size: 14px; font-weight: 700; }
            header .brand span { color: oklch(76% 0.17 50); }
            select {
                background: #16171b;
                color: #f0f1f3;
                border: 1px solid #35363d;
                border-radius: 8px;
                padding: 7px 10px;
                font-size: 14px;
            }
            main {
                flex: 1;
                display: flex;
                flex-direction: column;
                justify-content: center;
                padding: 28px 22px 40px;
                max-width: 640px;
                margin: 0 auto;
                width: 100%;
            }
            #reference {
                font-size: 15px;
                font-weight: 700;
                letter-spacing: 0.06em;
                text-transform: uppercase;
                color: oklch(76% 0.17 50);
                margin-bottom: 14px;
            }
            #text {
                font-size: 26px;
                line-height: 1.5;
                font-weight: 450;
                transition: opacity 0.25s ease;
            }
            #status {
                font-size: 12px;
                color: #63666d;
                padding: 12px 18px;
                border-top: 1px solid #25262b;
                display: flex;
                justify-content: space-between;
            }
            .waiting { color: #63666d; font-size: 18px; }
        </style>
    </head>
    <body>
        <header>
            <div class="brand">Verse<span>Pro</span> · Suivre le culte</div>
            <select id="version" aria-label="Choisir la traduction">__OPTIONS__</select>
        </header>
        <main>
            <div id="reference"></div>
            <div id="text" class="waiting">En attente du prochain verset projeté…</div>
        </main>
        <div id="status"><span id="conn">Connexion…</span><span id="count"></span></div>
        <script>
            const refEl = document.getElementById('reference');
            const textEl = document.getElementById('text');
            const connEl = document.getElementById('conn');
            const versionEl = document.getElementById('version');

            const saved = localStorage.getItem('versepro_follow_version');
            if (saved) versionEl.value = saved;
            versionEl.addEventListener('change', () => {
                localStorage.setItem('versepro_follow_version', versionEl.value);
                render(lastSlide);
            });

            let lastSlide = null;
            function render(data) {
                if (!data) return;
                lastSlide = data;
                const wanted = versionEl.value;
                const translations = data.translations || {};
                const text = (wanted && translations[wanted]) || data.text || '';
                refEl.textContent = data.reference || '';
                if (data.reference || text) {
                    textEl.classList.remove('waiting');
                    textEl.textContent = text;
                } else {
                    textEl.classList.add('waiting');
                    textEl.textContent = 'En attente du prochain verset projeté…';
                }
            }

            let ws;
            function connect() {
                const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                ws = new WebSocket(`${proto}//${window.location.host}/ws/output`);
                ws.onopen = () => { connEl.textContent = 'En direct'; };
                ws.onmessage = (event) => {
                    const data = JSON.parse(event.data);
                    // Les événements de progression/traduction ne remplacent pas le verset
                    if (data.type && data.type !== 'scripture') return;
                    render(data);
                };
                ws.onclose = () => {
                    connEl.textContent = 'Reconnexion…';
                    setTimeout(connect, 2500);
                };
            }
            connect();
        </script>
    </body>
    </html>
    """.replace("__OPTIONS__", options)
    return HTMLResponse(content=html_content)


@app.websocket("/ws/output")
async def websocket_output(websocket: WebSocket):
    """WebSocket pour les écrans d'affichage unifiés (écoute uniquement)"""
    await websocket.accept()
    browser_driver = output_manager.outputs.get("browser") if output_manager else None
    if browser_driver:
        await browser_driver.register_connection(websocket)
        try:
            while True:
                await websocket.receive_text()
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
    
    await broadcast_projection(text, ref, bg, translations=translations, theme=theme)
    
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


@app.post("/api/v1/bibles/select")
async def select_bible_version(data: dict):
    """Change la version active pour le parser"""
    version = data.get("version", "").upper()
    if not verse_parser or not verse_parser.bible_loader:
        raise HTTPException(status_code=500, detail="Service de parsing indisponible")
        
    loader = verse_parser.bible_loader
    if version not in loader.versions:
        raise HTTPException(status_code=400, detail=f"Version non disponible. Reçue: {version}")
        
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


# Mots-indices de l'Écriture. L'arbitrage IA de dernier recours (étage C) ne se
# déclenche qu'en leur présence en mode strict : inutile de solliciter le modèle
# sur « le café est prêt après le culte ».
BIBLE_KEYWORDS = {
    "dieu", "seigneur", "jésus", "jesus", "christ", "esprit", "bible", "écriture",
    "ecriture", "verset", "parole", "évangile", "evangile", "psaume", "apôtre",
    "apotre", "prophète", "prophete", "épître", "epitre", "royaume", "salut",
    "grâce", "grace", "péché", "peche", "foi", "prière", "priere", "alliance",
    "testament", "saint", "messie", "croix", "résurrection", "resurrection",
    "disciple", "éternel", "eternel", "amen", "béni", "beni", "sauveur",
}

# Une seule requête d'arbitrage IA en vol pour tout le processus. Une annulation
# libère automatiquement le verrou, contrairement à un simple drapeau global.
_ai_last_resort_lock = asyncio.Lock()

# Frontières de clause : le prédicateur enchâsse souvent l'allusion dans du
# commentaire (« y a Philippe qui va s'asseoir avec lui… POURQUOI est-ce si
# important ? PARCE QUE tout n'est pas évident… »).
_CLAUSE_SPLIT = re.compile(
    r"[.!?;:,]|\bparce que\b|\bpourquoi\b|\bmais\b|\bdonc\b|\balors\b|\bensuite\b|\bet puis\b",
    re.IGNORECASE,
)


def _retrieval_windows(text: str) -> list[str]:
    """Fenêtre(s) de récupération.

    Le découpage en clauses a été ESSAYÉ puis retiré : mesuré sur le corpus de
    référence, il faisait passer le rappel des paraphrases de 12/12 à 11/12 (une
    fenêtre voisine remportait un quasi ex æquo — Ésaïe 40:29 volait Philippiens
    4:13) sans rattraper le cas qui l'avait motivé (l'allusion narrative
    « Philippe va s'asseoir avec lui »). Les allusions à un RÉCIT ne se résolvent
    pas par appariement de texte : c'est le rôle de l'arbitrage IA (étage C).
    On garde donc une fenêtre unique, la plus récente.
    """
    return [" ".join(text.split()[-settings.HYBRID_WINDOW_WORDS:])]


async def run_detection_cascade(analysis_text: str, final_state: bool) -> dict | None:
    """Cascade de détection PARTAGÉE par le direct et le mode répétition.

    A. CITATION EXPLICITE (regex) — instantané (< 1 ms), précision quasi
       parfaite. Renvoyée telle quelle (seul étage autorisé à projeter direct).
    B. FUSION HYBRIDE des paraphrases (fin d'énoncé seulement) — deux
       récupérateurs indépendants en parallèle (lexical/flou + sémantique e5),
       agrégés par RRF, filtrés par accord + recouvrement lexical. Ne remonte
       que des versets réels du corpus.

    Renvoie la référence détectée (dict) ou None. AUCUN effet de bord.
    """
    if not verse_parser:
        return None

    # Fenêtre RÉCENTE partagée (dernière phrase) : on ne détecte que sur l'énoncé
    # courant. Sinon une citation explicite (« Jean 3:16 ») reste dans le buffer
    # de 40 mots et masque toute paraphrase pendant ~20 s ; et un verset précédent
    # masque le verset courant. La fenêtre fait suivre le prédicateur en temps réel.
    recent = recent_window(analysis_text, settings.HYBRID_WINDOW_WORDS)

    # ── A. Citation explicite sur la fenêtre récente ──
    reference = await verse_parser.parse(recent, skip_text_search=True)
    if reference:
        return reference

    if not final_state or not settings.LOCAL_SEMANTIC_ENABLED:
        return None

    # ── Santé de la transcription : au-delà d'ici, tout est DEVINÉ ───────────
    #    L'étage A ne devine pas — il lit une référence énoncée, vérifiable
    #    mot pour mot. Il passe donc toujours, même dans un vacarme. Ce qui
    #    suit propose des versets que personne n'a nommés : ça n'a de sens que
    #    si l'on a correctement entendu.
    #
    #    Deux conditions, mesurées sur de vrais enregistrements :
    #    — ce segment-ci doit porter assez de mots (« j'avais de l'eau », 4
    #      mots, suffisait à faire sortir Ézéchiel 47:4) ;
    #    — la transcription récente ne doit pas être hachée. Dans une église
    #      charismatique — musique pendant la prédication, parler en langues —
    #      Vosk tombe à 4 mots par segment contre 35 sur du son propre, et la
    #      recherche sémantique se met à trouver des versets dans du charabia.
    if not sante_transcription.segment_exploitable(recent):
        return None
    if not sante_transcription.est_fiable():
        return None

    # ── B. Fusion : nettoyage vocal + retrait de l'encadrement d'attribution
    #    (« Paul dit », « David a écrit »…) qui dilue l'embedding du verset cité.
    cleaned = verse_parser.normalize_spoken(recent)
    # On détecte sur le texte DÉ-ENCADRÉ. S'il reste trop court (attribution
    # partielle en cours d'énoncé), on attend la suite plutôt que de retomber sur
    # le texte encadré — sinon le nom réintroduit attire un mauvais verset.
    query = strip_attribution(cleaned)
    if len(query.split()) < 4:
        return None

    if semantic_service and not semantic_service.initialized and not semantic_service.indexing:
        await asyncio.to_thread(semantic_service.initialize, False)

    # ── B'. VERSEGRAPH : allusion dans le passage déjà ouvert ────────────────
    #    Passe AVANT la fusion globale, et le choix est délibéré : l'ancre
    #    vient d'une citation explicite confirmée — un fait — là où la fusion
    #    globale cherche parmi 31 102 versets sans contexte. Mesuré sur « il a
    #    crié d'une voix forte devant le tombeau » : la fusion globale propose
    #    Apocalypse 10:3, l'ancre donne Jean 11:43.
    #    Deux verrous stricts (score ET écart) l'empêchent de parler pour ne
    #    rien dire ; s'il se tait, la fusion reprend normalement la main.
    #    L'ancre est posée par l'appelant, jamais ici : cette fonction reste
    #    sans effet de bord, ce qui permet au rejeu de la piloter cas par cas.
    #    On lui passe le texte BRUT, pas `query` : l'index a été encodé depuis
    #    du texte naturel (apostrophes comprises), et `normalize_spoken`, utile
    #    au chemin lexical, éloigne la requête de cette distribution. Mesuré
    #    sur les cas ancrés du corpus : 6 détections sur 6 en brut, 4 sur 6 en
    #    normalisé, à précision identique.
    if verse_graph:
        ancre = verse_graph.resoudre(recent)
        if ancre:
            return ancre

    async def _decide(window: str) -> dict | None:
        """Récupération + fusion sur UNE fenêtre."""
        async def _lexical():
            return await asyncio.to_thread(
                verse_parser.bible_loader.search_candidates, window, settings.HYBRID_TOP_K
            )

        async def _semantic():
            if not (semantic_service and semantic_service.initialized):
                return []
            return await asyncio.to_thread(
                semantic_service.search, window, settings.HYBRID_TOP_K, 0.0
            )

        lexical, semantic = await asyncio.gather(_lexical(), _semantic())

        # Enrichit les candidats sémantiques de leurs traductions : le recouvrement
        # lexical peut alors confirmer une paraphrase de n'importe quelle version.
        for cand in semantic:
            if "translations" not in cand and cand.get("verse_start") is not None:
                cand["translations"] = verse_parser.bible_loader.translations_for(
                    cand["book_abbr"], cand["chapter"], cand["verse_start"]
                )

        return fuse_detection(
            lexical, semantic, window,
            semantic_threshold=(semantic_service.active_threshold if semantic_service else settings.LOCAL_SEMANTIC_THRESHOLD),
            semantic_margin=(semantic_service.active_margin if semantic_service else settings.LOCAL_SEMANTIC_MARGIN),
            overlap_min=settings.HYBRID_OVERLAP_MIN,
            top_n=settings.HYBRID_TOP_K,
        )

    # Plusieurs découpes en parallèle : la meilleure décision l'emporte.
    windows = _retrieval_windows(query)
    found = [d for d in await asyncio.gather(*[_decide(w) for w in windows]) if d]
    if found:
        # Accord entre récupérateurs d'abord, puis recouvrement, puis confiance.
        found.sort(
            key=lambda d: (
                bool((d.get("fusion") or {}).get("agreement")),
                float((d.get("fusion") or {}).get("overlap") or 0),
                float(d.get("confidence") or 0),
            ),
            reverse=True,
        )
        return found[0]

    # ── C. DERNIER RECOURS : arbitrage IA (Ollama local ou cloud) ────────────
    #    Ne se déclenche QUE si toute la chaîne locale est muette : le cas normal
    #    ne paie donc AUCUNE latence. Trois garde-fous : un indice biblique doit
    #    être présent (mode strict), une seule requête en vol à la fois, et la
    #    réponse est REVALIDÉE contre la Bible chargée — l'IA ne peut pas inventer
    #    un verset. Le résultat part toujours en validation manuelle.
    if not (ai_service and ai_service.enabled and settings.AI_AGENT_ENABLED):
        return None
    if _ai_last_resort_lock.locked():
        return None
    if settings.AI_FILTERING_MODE == "strict" and not any(k in query.lower() for k in BIBLE_KEYWORDS):
        return None

    async with _ai_last_resort_lock:
        try:
            # Vivier ancré : l'IA choisit parmi des versets RÉELS du corpus.
            shortlist = await asyncio.to_thread(
                verse_parser.bible_loader.search_candidates, query, 3
            )
            if semantic_service and semantic_service.initialized:
                shortlist += await asyncio.to_thread(semantic_service.search, query, 3, 0.0)
            if not shortlist:
                return None
            res = await ai_service.detect_bible_reference(query, candidates=shortlist)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.debug(f"Arbitrage IA de dernier recours indisponible : {exc}")
            return None

    if not res or not res.get("reference"):
        return None

    # Défense en profondeur : même un fournisseur mal configuré ou un faux
    # service de test ne peut sortir de la liste locale transmise au modèle.
    selected = next(
        (
            candidate for candidate in shortlist
            if AIService._normalize_reference(candidate.get("reference", ""))
            == AIService._normalize_reference(res.get("reference", ""))
        ),
        None,
    )
    if not selected:
        logger.info("Suggestion IA écartée : référence absente de la liste fermée")
        return None
    if not res.get("candidate_validated"):
        raw_confidence = max(0.0, min(100.0, float(res.get("confidence") or 0)))
        try:
            raw_score = selected.get("score")
            if raw_score is None:
                raw_score = selected.get("semantic_score")
            if raw_score is None:
                raw_score = selected.get("confidence")
            score = max(0.0, min(1.0, float(raw_score)))
            candidate_confidence = 70.0 + (score * 30.0)
        except (TypeError, ValueError):
            score = None
            candidate_confidence = 85.0
        res = {
            **res,
            "reference": selected["reference"],
            "raw_model_confidence": raw_confidence,
            "confidence": min(raw_confidence, candidate_confidence),
            "candidate_score": score,
            "candidate_validated": True,
        }
    confidence = float(res.get("confidence") or 0)
    if confidence < settings.AI_CONFIDENCE_THRESHOLD:
        logger.info(f"🛡️ Suggestion IA écartée (confiance {confidence:.0f} % < {settings.AI_CONFIDENCE_THRESHOLD} %)")
        return None

    grounded = await verse_parser.parse(res["reference"], skip_text_search=True)
    if not grounded or not grounded.get("text"):
        logger.info(f"🛡️ Suggestion IA écartée (référence introuvable dans la Bible) : {res['reference']!r}")
        return None

    grounded["confidence"] = confidence / 100.0
    grounded["detection_method"] = "ai_semantic"
    grounded["requires_review"] = True
    grounded["candidate_validated"] = True
    grounded["candidate_score"] = res.get("candidate_score")
    grounded["raw_model_confidence"] = res.get("raw_model_confidence")
    logger.info(f"🤖 Dernier recours IA → {grounded['reference']} ({confidence:.0f} %)")
    return grounded


# WebSocket principal de réception audio avec Fallback Vosk local
@app.websocket("/ws/audio")
async def websocket_audio(websocket: WebSocket):
    """
    WebSocket pour streaming audio temps réel avec détection et secours local Vosk ultra-rapide.
    """
    if not websocket_allowed(websocket):
        await websocket.close(code=1008, reason="Jeton API requis pour les clients distants")
        return

    await websocket.accept()

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
    whisper_window_queue: asyncio.Queue = asyncio.Queue(maxsize=2)

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
    use_vosk = False
    use_whisper = False
    transcription_session = None
    recognizer = None

    # Barrière vocale : ignore musique et silences avant transcription (optionnelle)
    voice_gate = None
    if settings.VOICE_GATE_ENABLED:
        try:
            from .services.vad_service import VoiceGate, vad_available
            if vad_available():
                voice_gate = await asyncio.to_thread(VoiceGate, settings.AUDIO_SAMPLE_RATE)
                logger.info("🎚️ Barrière vocale active sur cette session")
            else:
                logger.warning("⚠️ VOICE_GATE_ENABLED mais modèle silero_vad.onnx absent de data/")
        except Exception as vg_err:
            logger.error(f"❌ Barrière vocale indisponible : {vg_err}")
    
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
        nonlocal use_vosk, use_whisper, recognizer
        success = await asyncio.to_thread(vosk_service.initialize)
        if not success:
            return False
        recognizer = vosk_service.get_recognizer(settings.AUDIO_SAMPLE_RATE)
        if not recognizer:
            return False
        use_vosk = True
        use_whisper = False
        await send_json({"type": "status_update", "status": status, "mode": "vosk"})
        return True

    async def activate_whisper(status: str = "connected", allow_download: bool = False) -> bool:
        nonlocal use_vosk, use_whisper
        if not whisper_service:
            return False
        success = await asyncio.to_thread(whisper_service.initialize, allow_download)
        if not success:
            return False
        whisper_service.reset()
        use_whisper = True
        use_vosk = False
        await send_json({
            "type": "status_update",
            "status": status,
            "mode": "whisper",
            "model": whisper_service.model_name,
        })
        return True

    async def whisper_transcription_worker() -> None:
        """Transcrit hors de la boucle réseau et garde toujours l'audio le plus récent."""
        while True:
            audio_window = await whisper_window_queue.get()
            try:
                if audio_window is None:
                    return
                if whisper_service and use_whisper:
                    text = await asyncio.to_thread(whisper_service.transcribe_window, audio_window)
                    if text:
                        await queue_transcript(text, True)
            finally:
                whisper_window_queue.task_done()

    # Lecture du paramètre query 'engine' et 'translation_lang'.
    engine = websocket.query_params.get("engine", settings.ASR_DEFAULT_ENGINE)
    translation_lang = websocket.query_params.get("translation_lang", "")
    logger.info(f"🔌 Connexion WebSocket audio demandée avec le moteur : {engine} | Traduction: {translation_lang or 'aucune'}")

    if engine in ("vosk", "whisper", "local_auto"):
        local_ready = False
        # Vosk (grand modèle) est le moteur local de référence : au réel, il
        # s'est montré plus juste et plus réactif que Whisper fenêtré. Whisper
        # ne passe en premier que sur choix explicite de l'opérateur.
        if engine == "whisper":
            local_ready = await activate_whisper(
                allow_download=bool(settings.WHISPER_AUTO_DOWNLOAD)
            )
        if not local_ready:
            local_ready = await activate_vosk(status="fallback" if engine == "whisper" else "connected")
        if not local_ready and engine == "local_auto":
            local_ready = await activate_whisper(status="fallback")
        if not local_ready:
            try:
                transcription_session = await deepgram_service.create_session(on_transcript_received)
                await send_json({
                    "type": "status_update",
                    "status": "fallback",
                    "mode": "deepgram",
                    "reason": "Moteurs locaux indisponibles. Deepgram activé en secours.",
                })
            except Exception as exc:
                with suppress(Exception):
                    await websocket.close(code=1011, reason=f"Aucun moteur ASR disponible : {exc}")
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
        # Mode automatique : Deepgram, puis Whisper déjà préparé, puis Vosk.
        try:
            transcription_session = await deepgram_service.create_session(on_transcript_received)
            await send_json({"type": "status_update", "status": "connected", "mode": "deepgram"})
            logger.info("🎙️ Session de transcription en ligne Deepgram connectée")
        except Exception as e:
            logger.warning(f"Échec connexion Deepgram ({e}). Activation du secours local...")
            try:
                success = await activate_vosk(status="fallback")
                if not success:
                    success = await activate_whisper(status="fallback", allow_download=False)
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
        nonlocal use_vosk, use_whisper, recognizer, transcription_session
        
        # Pour le mécanisme de reconnexion automatique de Deepgram
        reconnecting_deepgram = False
        last_reconnect_attempt = 0
        # Limite les tentatives de bascule Vosk (évite un chargement + un log d'erreur par chunk audio)
        last_fallback_attempt = 0.0

        try:
            while True:
                data = await websocket.receive_bytes()
                logger.debug(f"🎙️ Chunk audio reçu: {len(data)} bytes")

                # Porte vocale : les chunks sans parole (musique, silence) sont ignorés
                if voice_gate is not None:
                    is_speech = await asyncio.to_thread(voice_gate.accept, data)
                    if not is_speech:
                        continue

                # Si on utilise en théorie Deepgram mais que la session est inactive (déconnexion 1011 ou erreur)
                if not use_vosk and not use_whisper and (
                    not transcription_session or not transcription_session.is_active
                ):
                    now = asyncio.get_event_loop().time()
                    if now - last_fallback_attempt < 5:
                        continue  # Aucun moteur disponible : on ignore ce chunk sans re-tenter ni logger
                    last_fallback_attempt = now
                    # Bascule dynamique à chaud sur un moteur local déjà préparé.
                    try:
                        success = await activate_vosk(status="fallback")
                        if not success:
                            success = await activate_whisper(status="fallback", allow_download=False)
                        if success:
                            logger.warning("Session Deepgram inactive. Bascule automatique sur le moteur local.")
                        else:
                            logger.error("Impossible de basculer en local : modèle indisponible. Nouvelle tentative dans 5 s.")
                            continue
                    except Exception as ve:
                        logger.error(f"Erreur de bascule ASR locale : {ve}")
                        continue

                if use_whisper:
                    audio_window = whisper_service.push_audio(data) if whisper_service else None
                    if audio_window is not None and whisper_service:
                        if whisper_window_queue.full():
                            with suppress(asyncio.QueueEmpty):
                                whisper_window_queue.get_nowait()
                                whisper_window_queue.task_done()
                        whisper_window_queue.put_nowait(audio_window)
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
                            
                # Retour vers Deepgram après une bascule Whisper OU Vosk.
                if engine == "auto" and (use_vosk or use_whisper) and not reconnecting_deepgram:
                    current_time = asyncio.get_event_loop().time()
                    if current_time - last_reconnect_attempt > 15:
                        last_reconnect_attempt = current_time
                        reconnecting_deepgram = True

                        async def try_reconnect_deepgram():
                            nonlocal transcription_session, use_vosk, use_whisper, reconnecting_deepgram
                            logger.info("Tentative de reconnexion en arrière-plan à Deepgram...")
                            try:
                                new_session = await deepgram_service.create_session(on_transcript_received)
                                if transcription_session:
                                    with suppress(Exception):
                                        await transcription_session.close()
                                transcription_session = new_session
                                use_vosk = False
                                use_whisper = False
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
            with suppress(asyncio.QueueFull):
                whisper_window_queue.put_nowait(None)
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
            return (
                method == "explicit"
                and confidence >= 0.95
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
                ref["detection_method"] = "semantic_local" if source == "semantic" else "ai_semantic"
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
            elif source == "semantic":
                explanation = (
                    "Suggestion locale issue de l'accord lexical et sémantique. "
                    f"Recouvrement: {float(fusion.get('overlap') or 0):.2f}."
                )
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
                and now - last_detected_at < 8.0
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

            if db_service and db_service.db:
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
                decision = await run_detection_cascade(analysis_text, final_state)
                if not decision or not is_current(generation):
                    return
                method = decision.get("detection_method")
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
        spawn_session_task(whisper_transcription_worker(), "whisper-worker")
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

    await websocket.accept()
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


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8001,
        reload=settings.DEBUG,
        log_level="info"
    )
