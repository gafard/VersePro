"""
VersePro v2 - Backend Principal
Architecture moderne avec FastAPI + WebSocket pour streaming temps réel, multi-traduction,
projection autonome et fallback hors-ligne Vosk local ultra-léger et robuste.
"""

import asyncio
import json
import re
import threading
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from loguru import logger
import uvicorn

from .core.config import settings
from .core.security import http_request_allowed, websocket_allowed
from .services.deepgram_service import DeepgramService
from .services.verse_parser import VerseParserService
from .services.database import DatabaseService, get_database
from .services.vosk_service import VoskService
from .services.ai_service import AIService
from .services.reading_tracker import ReadingTracker
from .outputs import OutputManager
from .api.routes import router as api_router


# Services globaux
deepgram_service: DeepgramService | None = None
output_manager: OutputManager | None = None
verse_parser: VerseParserService | None = None
db_service: DatabaseService | None = None
vosk_service: VoskService | None = None
ai_service: AIService | None = None
current_session_id: int | None = None

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
    current_projection_slide = {
        "text": text,
        "reference": reference,
        "background": background or current_projection_slide.get("background", "black"),
        "theme": theme or current_projection_slide.get("theme", "presentation"),
        "translations": translations or {},
        "next_reference": next_ref,
        "next_text": next_text
    }

    # Nouveau verset à l'écran : la lecture vivante repart de zéro
    reading_tracker.set_verse(text if reference else "")

    if output_manager:
        await output_manager.project_scene(current_projection_slide)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestion du cycle de vie de l'application"""
    global deepgram_service, output_manager, verse_parser, db_service, vosk_service, ai_service, current_session_id
    
    # Startup
    logger.info("🚀 Démarrage de VersePro v2...")
    
    # Initialisation de la base de données
    db_service = get_database()
    await db_service.connect()
    
    # Charger la configuration dynamique depuis SQLite
    stored_settings = await db_service.get_all_settings()
    for key, val in stored_settings.items():
        attr_name = key.upper()
        if hasattr(settings, attr_name):
            # Évite d'écraser des clés API d'environnement valides (.env) par des valeurs vides stockées en base
            if attr_name in ("DEEPGRAM_API_KEY", "OPENROUTER_API_KEY", "GEMINI_API_KEY"):
                env_val = getattr(settings, attr_name, "")
                if env_val and (val is None or val.strip() == ""):
                    logger.info(f"⚙️ Conservation de la clé d'environnement pour {attr_name}")
                    # Enregistre la clé dans la base SQLite pour la synchroniser
                    await db_service.set_setting(key, env_val)
                    continue
                    
            expected_type = type(getattr(settings, attr_name))
            try:
                if expected_type is bool:
                    typed_val = val.lower() in ("true", "1", "yes")
                else:
                    typed_val = expected_type(val)
                setattr(settings, attr_name, typed_val)
                logger.info(f"⚙️ Config chargée depuis SQLite : {attr_name} = {typed_val}")
            except Exception as e:
                logger.error(f"Impossible de convertir {key}={val} en {expected_type}: {e}")
                
    # Crée une session par défaut
    current_session_id = await db_service.create_session("Session automatique")
    
    # Initialisation des autres services avec la config SQLite chargée
    deepgram_service = DeepgramService(settings.DEEPGRAM_API_KEY)
    
    # Initialisation d'OutputManager avec ses drivers
    output_manager = OutputManager()
    await output_manager.initialize_defaults()
    
    verse_parser = VerseParserService()
    vosk_service = VoskService()
    ai_service = AIService()
    
    # Chargement en arrière-plan du modèle local Vosk pour éviter de bloquer l'application
    threading.Thread(target=vosk_service.initialize, daemon=True).start()
    
    logger.info("✅ Services initialisés")
    
    yield
    
    # Shutdown
    logger.info("🛑 Arrêt de VersePro v2...")
    
    if current_session_id:
        await db_service.end_session(current_session_id)
    
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
            "vosk_loaded": vosk_service.initialized if vosk_service else False
        }
    }


@app.get("/projection")
async def get_projection_page_legacy():
    """Redirige les anciennes requêtes d'affichage vers le nouvel endpoint Output unifié"""
    return RedirectResponse(url="/output")


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
            :root { --accent: oklch(76% 0.17 50); --accent-2: oklch(68% 0.16 18); --read: #ffffff; --unread: rgba(255,255,255,0.34); }
            html { font-size: 16px; }
            body {
                margin: 0; padding: 0;
                background-color: #000; color: #fff;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
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
            body.theme-dual .split-columns { display: grid; grid-template-columns: 1fr 1fr; gap: 40px; }
            body.theme-dual .split-col { border-left: 3px solid rgba(255,255,255,0.15); padding-left: 20px; }
            body.theme-dual .split-ver { font-size: 1.8rem; line-height: 1.5; color: #f3f4f6; margin-bottom: 12px; opacity: 0; }
            body.theme-dual .split-label { font-size: 11px; font-weight: bold; color: #9ca3af; text-transform: uppercase; letter-spacing: 1px; opacity: 0; }
            body.theme-dual #container.visible .split-ver { animation: fadeInUp 180ms cubic-bezier(0.16, 1, 0.3, 1) forwards; }
            body.theme-dual #container.visible .split-label { animation: fadeInUp 180ms cubic-bezier(0.16, 1, 0.3, 1) 120ms forwards; }

            /* --- NOUVEAUX STYLES DE BROADCAST --- */

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
        <div id="container">
            <div id="text">En attente d'affichage...</div>
            <div id="reference"></div>
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
            // Le zoom s'applique à TOUS les thèmes (tout est dimensionné en rem)
            if (scale && scale !== 1) document.documentElement.style.fontSize = (16 * scale) + 'px';

            let currentKey = null;
            let subtitleTimer = null;

            // Rendu du texte en mots individuels (Lecture vivante) — DOM sûr, pas d'innerHTML
            function renderWords(text) {
                textEl.textContent = '';
                textEl.classList.add('karaoke');
                (text || '').split(/\s+/).filter(Boolean).forEach((word) => {
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

                // Même verset (changement de thème/fond seulement) : pas de re-animation
                const key = (data.reference || '') + '|' + (data.text || '');
                if (key === currentKey) return;
                currentKey = key;

                container.classList.remove('visible');
                setTimeout(() => {
                    splitContainer.style.display = 'none';
                    textEl.style.display = 'block';
                    refEl.style.display = 'block';

                    const translations = data.translations || {};
                    if (theme === 'dual' && Object.keys(translations).length > 1) {
                        textEl.style.display = 'none';
                        refEl.style.display = 'none';
                        splitContainer.style.display = 'block';
                        splitCols.textContent = '';
                        Object.entries(translations).slice(0, 2).forEach(([version, txt]) => {
                            const col = document.createElement('div');
                            col.className = 'split-col';
                            const ver = document.createElement('div');
                            ver.className = 'split-ver';
                            ver.textContent = txt;
                            const label = document.createElement('div');
                            label.className = 'split-label';
                            label.textContent = version + ' — ' + (data.reference || '');
                            col.appendChild(ver);
                            col.appendChild(label);
                            splitCols.appendChild(col);
                        });
                    } else {
                        renderWords(data.text);
                        refEl.textContent = data.reference || '';
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
                (text || '').split(/\s+/).filter(Boolean).forEach((word) => {
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

            function renderScene(data) {
                refEl.textContent = data.reference || '—';
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
    logger.info(f"🔄 Traduction de la Bible modifiée : {version}")
    return {"status": "success", "active": version}


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
        
    # Envoi de l'état d'activation de l'Agent IA sémantique au client
    await websocket.send_json({
        "type": "ai_status",
        "enabled": ai_service.enabled if ai_service else False
    })
        
    transcript_queue = asyncio.Queue()
    use_vosk = False
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
                    await transcript_queue.put((transcript, is_final))
        except Exception as e:
            logger.error(f"❌ Erreur callback transcription Deepgram: {e}")

    # Lecture du paramètre query 'engine' (auto, deepgram, vosk) et 'translation_lang'
    engine = websocket.query_params.get("engine", "auto")
    translation_lang = websocket.query_params.get("translation_lang", "")
    logger.info(f"🔌 Connexion WebSocket audio demandée avec le moteur : {engine} | Traduction: {translation_lang or 'aucune'}")

    if engine == "vosk":
        # Mode Vosk local forcé (chargement du modèle hors event loop)
        try:
            success = await asyncio.to_thread(vosk_service.initialize)
            if success:
                use_vosk = True
                recognizer = vosk_service.get_recognizer(settings.AUDIO_SAMPLE_RATE)
                await websocket.send_json({"type": "status_update", "status": "connected", "mode": "vosk"})
                logger.info("🎙️ Moteur local Vosk activé (Mode forcé)")
            else:
                raise RuntimeError("Modèle Vosk local non disponible")
        except Exception as we:
            logger.error(f"❌ Échec démarrage Vosk forcé : {we}")
            try:
                await websocket.close(code=1011, reason=f"Moteur Vosk local hors-service : {we}")
            except Exception:
                pass
            return
    elif engine == "deepgram":
        # Mode Deepgram cloud forcé
        try:
            transcription_session = await deepgram_service.create_session(on_transcript_received)
            await websocket.send_json({"type": "status_update", "status": "connected", "mode": "deepgram"})
            logger.info("🎙️ Session de transcription Deepgram connectée (Mode forcé)")
        except Exception as e:
            logger.error(f"❌ Échec démarrage Deepgram forcé : {e}")
            try:
                await websocket.close(code=1011, reason=f"Connexion Deepgram impossible : {e}")
            except Exception:
                pass
            return
    else:
        # Mode automatique (Deepgram avec fallback Vosk)
        try:
            transcription_session = await deepgram_service.create_session(on_transcript_received)
            await websocket.send_json({"type": "status_update", "status": "connected", "mode": "deepgram"})
            logger.info("🎙️ Session de transcription en ligne Deepgram connectée")
        except Exception as e:
            logger.warning(f"⚠️ Échec connexion Deepgram ({e}). Activation du secours local Vosk...")
            try:
                success = await asyncio.to_thread(vosk_service.initialize)
                if success:
                    use_vosk = True
                    recognizer = vosk_service.get_recognizer(settings.AUDIO_SAMPLE_RATE)
                    await websocket.send_json({"type": "status_update", "status": "connected", "mode": "vosk"})
                    logger.info("🎙️ Secours local Vosk activé et prêt")
                else:
                    raise RuntimeError("Modèle Vosk non disponible")
            except Exception as we:
                logger.error(f"❌ Échec de la bascule Vosk: {we}")
                try:
                    await websocket.close(code=1011, reason="Connexion Deepgram impossible et Vosk local hors-service")
                except Exception:
                    pass
                return
            
    async def receive_audio_task():
        """Reçoit l'audio client et l'envoie au moteur de transcription actif"""
        nonlocal use_vosk, recognizer, transcription_session
        
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
                if not use_vosk and (not transcription_session or not transcription_session.is_active):
                    now = asyncio.get_event_loop().time()
                    if now - last_fallback_attempt < 5:
                        continue  # Aucun moteur disponible : on ignore ce chunk sans re-tenter ni logger
                    last_fallback_attempt = now
                    # Bascule dynamique à chaud sur Vosk local si possible (hors event loop)
                    try:
                        success = await asyncio.to_thread(vosk_service.initialize)
                        if success:
                            use_vosk = True
                            recognizer = vosk_service.get_recognizer(settings.AUDIO_SAMPLE_RATE)
                            await websocket.send_json({"type": "status_update", "status": "fallback", "mode": "vosk"})
                            logger.warning("⚠️ Session Deepgram inactive. Bascule automatique et transparente sur Vosk local.")
                        else:
                            logger.error("❌ Impossible de basculer sur Vosk : modèle indisponible. Nouvelle tentative dans 5s.")
                            continue
                    except Exception as ve:
                        logger.error(f"❌ Erreur bascule à chaud Vosk : {ve}")
                        continue

                if not use_vosk:
                    await transcription_session.send_audio(data)
                else:
                    # Vosk local : traitement en temps réel du flux audio non-bloquant
                    is_accepted = await asyncio.to_thread(recognizer.AcceptWaveform, data)
                    if is_accepted:
                        result_str = await asyncio.to_thread(recognizer.Result)
                        result = json.loads(result_str)
                        text = result.get("text", "")
                        if text.strip():
                            await transcript_queue.put((text, True))
                    else:
                        partial_str = await asyncio.to_thread(recognizer.PartialResult)
                        partial = json.loads(partial_str)
                        text = partial.get("partial", "")
                        if text.strip():
                            await transcript_queue.put((text, False))
                            
                    # Tentative de reconnexion en tâche de fond pour Deepgram (uniquement en mode 'auto')
                    if engine == "auto" and not reconnecting_deepgram:
                        current_time = asyncio.get_event_loop().time()
                        if current_time - last_reconnect_attempt > 15:  # Retenter toutes les 15 secondes
                            last_reconnect_attempt = current_time
                            reconnecting_deepgram = True
                            
                            async def try_reconnect_deepgram():
                                nonlocal transcription_session, use_vosk, reconnecting_deepgram
                                logger.info("🔄 Tentative de reconnexion en arrière-plan à Deepgram...")
                                try:
                                    new_session = await deepgram_service.create_session(on_transcript_received)
                                    # Succès ! Fermeture propre de l'ancienne si elle existait encore
                                    if transcription_session:
                                        try:
                                            await transcription_session.close()
                                        except Exception:
                                            pass
                                    transcription_session = new_session
                                    use_vosk = False
                                    await websocket.send_json({"type": "status_update", "status": "connected", "mode": "deepgram"})
                                    logger.info("⚡ Connexion Deepgram rétablie en arrière-plan. Retour au moteur principal.")
                                except Exception as re_err:
                                    logger.debug(f"Note: Échec reconnexion Deepgram: {re_err}")
                                finally:
                                    reconnecting_deepgram = False
                                    
                            asyncio.create_task(try_reconnect_deepgram())
                            
        except WebSocketDisconnect:
            logger.info("🔌 Client WebSocket déconnecté (audio)")
        except Exception as e:
            logger.error(f"❌ Erreur réception audio: {e}")
        finally:
            if not use_vosk and transcription_session:
                await transcription_session.close()
            # Signal de fermeture de la queue
            await transcript_queue.put(None)

    async def send_transcript_task():
        """Prend le texte transcrit, le parse et notifie le technicien + projecteur"""
        buffer_text = ""
        last_projected_ref = None # Pour éviter de projeter/enregistrer plusieurs fois le même verset d'affilée
        last_deterministic_at = 0.0
        active_ai_tasks = set()
        # Lecture vivante : mots déjà transmis de l'énoncé en cours (les partiels se répètent)
        last_partial_words = []

        try:
            while True:
                item = await transcript_queue.get()
                if item is None:
                    break
                    
                transcript, is_final = item
                
                # 1. Envoi immédiat et sans blocage du retour visuel de la transcription courante
                await websocket.send_json({
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
                        asyncio.create_task(broadcast_output_event({
                            "type": "reading_progress",
                            "reference": current_projection_slide.get("reference", ""),
                            "matched": reading_tracker.position,
                            "total": reading_tracker.total
                        }))
                elif is_final:
                    last_partial_words = []
                
                # Le texte complet à analyser
                current_analysis_text = (buffer_text + " " + transcript).strip()
                
                # 2. Routine utilitaire pour traiter et notifier la référence détectée
                def is_direct_projection_allowed(ref):
                    method = ref.get("detection_method")
                    confidence = float(ref.get("confidence") or 0)
                    return (
                        method == "explicit"
                        and confidence >= 0.95
                        and ref.get("verse_start") is not None
                        and not ref.get("requires_review")
                    )

                async def process_detected_reference(ref, analysis_text, source="local"):
                    nonlocal last_projected_ref, last_deterministic_at

                    if source == "ai":
                        ref["detection_method"] = "ai_semantic"
                        ref["confidence"] = min(float(ref.get("confidence") or 0.95), 0.95)
                        ref["requires_review"] = True
                        ref["projection_policy"] = "manual_review"
                    else:
                        ref.setdefault("requires_review", False)
                        direct_allowed = is_direct_projection_allowed(ref)
                        ref["requires_review"] = not direct_allowed
                        ref["projection_policy"] = "autopilot_direct" if direct_allowed else "manual_review"
                        if direct_allowed:
                            last_deterministic_at = time.monotonic()
                            # Annuler activement toutes les tâches d'IA sémantique en cours
                            for task in list(active_ai_tasks):
                                if not task.done():
                                    logger.info(f"⚡ Annulation de requête IA en cours suite à détection déterministe locale ({ref['reference']})")
                                    task.cancel()
                            active_ai_tasks.clear()

                    direct_allowed = is_direct_projection_allowed(ref)
                    ref["auto_projected"] = bool(settings.PROPRESENTER_AUTO_SEND and direct_allowed)
                    if ref["auto_projected"]:
                        ref["projection_policy"] = "autopilot_projected"

                    ref_key = f"{ref['book_abbr']}_{ref['chapter']}_{ref['verse_start']}_{ref['verse_end'] or ''}"
                    
                    if ref_key != last_projected_ref:
                        last_projected_ref = ref_key
                        verse_id = None

                        # Notification au client D'ABORD — la persistance SQLite
                        # (commit disque) ne doit jamais retarder l'affichage régie
                        try:
                            await websocket.send_json({
                                "type": "reference_detected",
                                "reference": ref,
                                "text": analysis_text,
                                "verse_id": verse_id
                            })
                        except Exception:
                            pass

                        if db_service and db_service.db:
                            asyncio.create_task(db_service.add_detected_verse(
                                reference=ref,
                                session_id=current_session_id,
                                context=analysis_text,
                                confidence=int(float(ref.get("confidence") or 1.0) * 100),
                                source=source
                            ))
                        
                        # Projection directe uniquement pour les references explicites et fiables.
                        # Les deductions IA ou correspondances floues restent en validation manuelle.
                        if ref["auto_projected"]:
                            await broadcast_projection(ref.get("text", ""), ref["reference"], translations=ref.get("translations"))
                            sent = False
                            if output_manager and "propresenter" in output_manager.outputs:
                                sent = await output_manager.outputs["propresenter"].send_scene({
                                    "reference": ref["reference"],
                                    "text": ref.get("text", "")
                                })
                            try:
                                await websocket.send_json({
                                    "type": "propresenter_status",
                                    "sent": sent,
                                    "reference": ref,
                                    "verse_id": verse_id
                                })
                            except Exception:
                                pass

                # Mots-clés sémantiques pour filtrer les requêtes IA inutiles
                BIBLE_KEYWORDS = {
                    "verset", "chapitre", "passage", "écrit", "écriture", "évangile", "apôtre",
                    "prophète", "parabole", "histoire", "bible", "salut", "seigneur", "dieu", "jésus",
                    "christ", "livre", "lettre", "épître", "psaume", "proverbe", "loi", "alliance",
                    "commandement", "foi", "grâce", "esprit"
                }

                # 3. Définition de la routine asynchrone d'analyse (locale + IA) en arrière-plan
                async def analyze_and_detect(analysis_text, final_state, current_transcript):
                    analysis_started_at = time.monotonic()

                    # A. Détection locale rapide (Instantanéité absolue < 5ms)
                    reference = await verse_parser.parse(analysis_text, skip_text_search=not final_state)
                    
                    if reference:
                        await process_detected_reference(reference, analysis_text)
                        return
                        
                    # B. Fallback Agent IA sémantique (si final et non détecté localement)
                    if final_state and ai_service and ai_service.enabled:
                        lowercase_text = analysis_text.lower()
                        
                        # Évite d'interroger l'IA pour des phrases sans rapport (si mode strict activé)
                        bypass_filter = (settings.AI_FILTERING_MODE != "strict")
                        has_keyword = any(kw in lowercase_text for kw in BIBLE_KEYWORDS)
                        has_numbers = any(char.isdigit() for char in lowercase_text)
                        
                        if bypass_filter or has_keyword or has_numbers:
                            async def run_ai_detection():
                                try:
                                    # L'IA analyse le contexte large et renvoie le dictionnaire {"reference", "confidence"}
                                    res = await ai_service.detect_bible_reference(analysis_text)
                                    if res:
                                        ai_ref_str = res.get("reference")
                                        ai_conf = res.get("confidence", 95)
                                        
                                        # Filtrage de confiance couperet
                                        if ai_conf < settings.AI_CONFIDENCE_THRESHOLD:
                                            logger.info(f"🛡️ Réponse IA filtrée : score de confiance insuffisant ({ai_conf}% < {settings.AI_CONFIDENCE_THRESHOLD}%)")
                                            try:
                                                await websocket.send_json({
                                                    "type": "ai_rejected_suggestion",
                                                    "reference": ai_ref_str or "Inconnue",
                                                    "confidence": int(ai_conf),
                                                    "threshold": settings.AI_CONFIDENCE_THRESHOLD,
                                                    "reason": "low_confidence"
                                                })
                                            except Exception:
                                                pass
                                            return
                                            
                                        if last_deterministic_at > analysis_started_at:
                                            logger.info("🛡️ Réponse IA ignorée: une référence explicite plus récente a la priorité")
                                            try:
                                                await websocket.send_json({
                                                    "type": "ai_rejected_suggestion",
                                                    "reference": ai_ref_str or "Inconnue",
                                                    "confidence": int(ai_conf),
                                                    "threshold": settings.AI_CONFIDENCE_THRESHOLD,
                                                    "reason": "priority_local"
                                                })
                                            except Exception:
                                                pass
                                            return
                                            
                                        if ai_ref_str:
                                            reference = await verse_parser.parse(ai_ref_str, skip_text_search=True)
                                            if reference:
                                                reference["confidence"] = float(ai_conf) / 100.0
                                                await process_detected_reference(reference, analysis_text, source="ai")
                                except asyncio.CancelledError:
                                    logger.debug("⚡ Requête de détection IA annulée proprement")
                                except Exception as ai_err:
                                    logger.error(f"❌ Erreur détection IA en arrière-plan : {ai_err}")

                            # Lance la tâche IA asynchrone et l'enregistre pour une potentielle annulation active
                            ai_task = asyncio.create_task(run_ai_detection())
                            active_ai_tasks.add(ai_task)
                            ai_task.add_done_callback(lambda t: active_ai_tasks.discard(t))
                
                # Lance l'analyse en arrière-plan sans bloquer le flux de transcription
                asyncio.create_task(analyze_and_detect(current_analysis_text, is_final, transcript))
                
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
                        asyncio.create_task(db_service.append_to_session_transcript(current_session_id, transcript))
                        
                    # Traduction en direct (non-bloquante)
                    if translation_lang and ai_service and ai_service.enabled:
                        async def perform_translation(text_to_translate, target_lang):
                            translated = await ai_service.translate_text(text_to_translate, target_lang)
                            if translated:
                                try:
                                    await websocket.send_json({
                                        "type": "translation",
                                        "text": translated,
                                        "lang": target_lang
                                    })
                                except Exception as err:
                                    logger.error(f"❌ Impossible d'envoyer la traduction: {err}")
                                # Sous-titre live sur les écrans de projection/assemblée
                                await broadcast_output_event({
                                    "type": "live_translation",
                                    "text": translated,
                                    "lang": target_lang
                                })
                        
                        asyncio.create_task(perform_translation(transcript, translation_lang))
        except Exception as e:
            logger.error(f"❌ Erreur émission transcription: {e}")

    try:
        receive_job = asyncio.create_task(receive_audio_task())
        send_job = asyncio.create_task(send_transcript_task())
        
        await asyncio.gather(receive_job, send_job)
            
    except Exception as e:
        logger.error(f"❌ Erreur WebSocket principal: {e}")
    finally:
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
                    
                    # Rendu universel
                    if parsed:
                        await broadcast_projection(parsed.get("text", ""), parsed["reference"], translations=parsed.get("translations"))
                    
                    # Envoi à ProPresenter si configuré
                    sent = False
                    if pp_driver and pp_driver.enabled:
                        sent = await pp_driver.send_scene({
                            "reference": parsed["reference"] if parsed else ref,
                            "text": parsed.get("text", "") if parsed else ""
                        })
                            
                    await websocket.send_json({
                        "type": "send_result",
                        "success": sent or True, # On renvoie True si le rendu universel a réussi
                        "reference": ref
                    })
                    
            elif action == "clear":
                # Effacement universel
                await broadcast_projection("", "")
                cleared = False
                if pp_driver and pp_driver.enabled:
                    cleared = await pp_driver.clear()
                    
                await websocket.send_json({
                    "type": "clear_result",
                    "success": cleared or True
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
