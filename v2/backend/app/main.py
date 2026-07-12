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
current_projection_slide = {
    "text": "En attente d'affichage...",
    "reference": "",
    "background": "black",
    "theme": "classic",
    "translations": {}
}

async def broadcast_projection(text: str, reference: str, background: str | None = None, translations: dict | None = None, theme: str | None = None):
    """Diffuse le slide à tous les projecteurs et suiveurs connectés via OutputManager"""
    global current_projection_slide
    current_projection_slide = {
        "text": text,
        "reference": reference,
        "background": background or current_projection_slide.get("background", "black"),
        "theme": theme or current_projection_slide.get("theme", "presentation"),
        "translations": translations or {}
    }
    
    if output_manager:
        await output_manager.project(
            text=text,
            reference=reference,
            background=background,
            translations=translations,
            theme=theme
        )


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


# Endpoints de Rendu d'Affichage Web Autonome (Outputs)
@app.get("/output", response_class=HTMLResponse)
async def get_output_page():
    """Sert l'écran d'affichage HTML5 universel (Render Engine)"""
    html_content = """
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="utf-8">
        <title>Rendu d'Affichage - VersePro</title>
        <style>
            body {
                margin: 0;
                padding: 0;
                background-color: #000;
                color: #fff;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
                overflow: hidden;
                display: flex;
                align-items: center;
                justify-content: center;
                height: 100vh;
                text-align: center;
                transition: background 0.3s ease, background-color 0.3s ease;
            }
            
            /* Support transparent */
            .bg-transparent {
                background: transparent !important;
                background-color: transparent !important;
            }
            .chroma-green {
                background: #00ff00 !important;
                background-color: #00ff00 !important;
            }
            .chroma-blue {
                background: #0000ff !important;
                background-color: #0000ff !important;
            }

            /* Animations Apple-Style ultra-sobres */
            @keyframes fadeInUp {
                from {
                    opacity: 0;
                    transform: translateY(8px);
                }
                to {
                    opacity: 1;
                    transform: translateY(0);
                }
            }

            #container {
                width: 85%;
                max-width: 1200px;
            }

            #text {
                font-size: 3.5rem;
                line-height: 1.4;
                font-weight: 500;
                margin-bottom: 2rem;
                text-shadow: 2px 2px 8px rgba(0, 0, 0, 0.9);
                opacity: 0;
            }
            #reference {
                font-size: 2.2rem;
                font-weight: 700;
                color: #3b82f6; /* Bleu moderne */
                text-transform: uppercase;
                letter-spacing: 2px;
                text-shadow: 2px 2px 8px rgba(0, 0, 0, 0.9);
                opacity: 0;
            }

            /* Déclenchement séquentiel des animations */
            #container.visible #text {
                animation: fadeInUp 180ms cubic-bezier(0.16, 1, 0.3, 1) forwards;
            }
            #container.visible #reference {
                animation: fadeInUp 180ms cubic-bezier(0.16, 1, 0.3, 1) 120ms forwards;
            }

            /* --- TYPE: PRESENTATION (Cinématique épuré) --- */
            body.theme-presentation {
                background: radial-gradient(circle, #101114 0%, #030304 100%);
                font-family: "Playfair Display", Georgia, "Times New Roman", serif;
            }
            body.theme-presentation #text {
                font-weight: 400;
                font-style: italic;
                letter-spacing: 0.5px;
            }
            body.theme-presentation #reference {
                color: #e2b865; /* Ambre */
                font-weight: 600;
                font-size: 1.8rem;
            }

            /* --- TYPE: BROADCAST (Lower Thirds) --- */
            body.theme-broadcast {
                justify-content: center;
                align-items: flex-end;
            }
            body.theme-broadcast #container {
                width: 90%;
                max-width: 1400px;
                background: rgba(10, 11, 15, 0.85);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-left: 6px solid #3b82f6;
                border-radius: 8px;
                padding: 24px 40px;
                margin-bottom: 5vh;
                box-shadow: 0 10px 30px rgba(0,0,0,0.5);
                display: flex;
                justify-content: space-between;
                align-items: center;
                gap: 40px;
                text-align: left;
                box-sizing: border-box;
            }
            body.theme-broadcast #text {
                font-size: 1.8rem;
                line-height: 1.4;
                margin-bottom: 0;
                font-weight: 450;
                text-shadow: none;
                flex: 1;
            }
            body.theme-broadcast #reference {
                font-size: 1.4rem;
                font-weight: 800;
                letter-spacing: 1px;
                text-shadow: none;
                flex-shrink: 0;
                background: rgba(59, 130, 246, 0.12);
                border: 1px solid rgba(59, 130, 246, 0.2);
                padding: 6px 16px;
                border-radius: 6px;
            }

            /* --- TYPE: CONFIDENCE (Moniteur de scène) --- */
            body.theme-confidence {
                background: #000 !important;
                color: #ff0 !important; /* Jaune très lisible */
                justify-content: flex-start;
                align-items: flex-start;
                text-align: left;
            }
            body.theme-confidence #container {
                width: 95%;
                margin: 40px;
            }
            body.theme-confidence #text {
                font-size: 4rem;
                font-weight: bold;
                color: #fff;
                margin-bottom: 30px;
                text-shadow: none;
            }
            body.theme-confidence #reference {
                font-size: 3rem;
                color: #ff0;
                text-shadow: none;
            }

            /* --- TYPE: DUAL (Multi-Langues) --- */
            body.theme-dual #container {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 50px;
                text-align: left;
                width: 90%;
                max-width: 1300px;
            }
            body.theme-dual #text {
                font-size: 2.2rem;
                line-height: 1.5;
                grid-column: span 2;
                margin-bottom: 1rem;
            }
            body.theme-dual .split-columns {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 40px;
                grid-column: span 2;
            }
            body.theme-dual .split-col {
                border-left: 3px solid rgba(255,255,255,0.15);
                padding-left: 20px;
            }
            body.theme-dual .split-ver {
                font-size: 1.8rem;
                line-height: 1.5;
                color: #f3f4f6;
                margin-bottom: 12px;
                opacity: 0;
            }
            body.theme-dual .split-label {
                font-size: 11px;
                font-weight: bold;
                color: #9ca3af;
                text-transform: uppercase;
                letter-spacing: 1px;
                opacity: 0;
            }

            body.theme-dual #container.visible .split-ver {
                animation: fadeInUp 180ms cubic-bezier(0.16, 1, 0.3, 1) forwards;
            }
            body.theme-dual #container.visible .split-label {
                animation: fadeInUp 180ms cubic-bezier(0.16, 1, 0.3, 1) 120ms forwards;
            }
        </style>
    </head>
    <body>
        <div id="container">
            <div id="text">En attente d'affichage...</div>
            <div id="reference"></div>
            <!-- Zone pour l'affichage double version split -->
            <div id="split-container" style="display: none;">
                <div class="split-columns" id="split-cols">
                    <!-- Généré en JS -->
                </div>
            </div>
        </div>
        
        <script>
            const container = document.getElementById('container');
            const textEl = document.getElementById('text');
            const refEl = document.getElementById('reference');
            const splitContainer = document.getElementById('split-container');
            const splitCols = document.getElementById('split-cols');

            const params = new URLSearchParams(window.location.search);
            const forcedBg = params.get('bg');
            const forcedTheme = params.get('theme');
            const scale = parseFloat(params.get('scale') || '1');

            if (scale && scale !== 1) {
                textEl.style.fontSize = (3.5 * scale) + 'rem';
                refEl.style.fontSize = (2.2 * scale) + 'rem';
            }

            let ws;
            function connect() {
                const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                const wsUrl = `${proto}//${window.location.host}/ws/output`;
                ws = new WebSocket(wsUrl);
                
                ws.onopen = () => {
                    console.log('🔗 Connecté au moteur de rendu');
                    container.classList.add('visible');
                };
                
                ws.onmessage = (event) => {
                    const data = JSON.parse(event.data);
                    
                    // Couleur d'arrière-plan
                    const bg = forcedBg || data.background;
                    document.body.className = '';
                    if (bg === 'transparent') {
                        document.body.classList.add('bg-transparent');
                    } else if (bg === 'green') {
                        document.body.classList.add('chroma-green');
                    } else if (bg === 'blue') {
                        document.body.classList.add('chroma-blue');
                    }

                    // Thème dynamique
                    const theme = forcedTheme || data.theme || 'presentation';
                    document.body.classList.add('theme-' + theme);
                    
                    // Réinitialisation des animations en enlevant la classe visible
                    container.classList.remove('visible');
                    
                    setTimeout(() => {
                        // Nettoyage dual/split
                        splitContainer.style.display = 'none';
                        textEl.style.display = 'block';
                        refEl.style.display = 'block';

                        if (theme === 'dual' && data.translations && Object.keys(data.translations).length > 0) {
                            textEl.style.display = 'none';
                            refEl.style.display = 'none';
                            splitContainer.style.display = 'block';
                            
                            splitCols.innerHTML = '';
                            Object.entries(data.translations).slice(0, 2).forEach(([version, txt]) => {
                                const col = document.createElement('div');
                                col.className = 'split-col';
                                col.innerHTML = `
                                    <div class="split-ver">"${txt}"</div>
                                    <div class="split-label">${version} — ${data.reference || ''}</div>
                                `;
                                splitCols.appendChild(col);
                            });
                        } else {
                            textEl.textContent = data.text || '';
                            refEl.textContent = data.reference || '';
                        }
                        
                        if (data.text || data.reference) {
                            container.classList.add('visible');
                        }
                    }, 150); // Petit délai de ré-apparition
                };
                
                ws.onclose = () => {
                    console.log('🔌 Déconnecté, reconnexion...');
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
            header .brand span { color: #7b83eb; }
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
                color: #7b83eb;
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
                ws.onmessage = (event) => render(JSON.parse(event.data));
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
                        
                        if db_service and db_service.db:
                            verse_id = await db_service.add_detected_verse(
                                reference=ref,
                                session_id=current_session_id,
                                context=analysis_text,
                                confidence=int(float(ref.get("confidence") or 1.0) * 100),
                                source=source
                            )
                            
                        # Notification au client
                        try:
                            await websocket.send_json({
                                "type": "reference_detected",
                                "reference": ref,
                                "text": analysis_text,
                                "verse_id": verse_id
                            })
                        except Exception:
                            pass
                        
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
