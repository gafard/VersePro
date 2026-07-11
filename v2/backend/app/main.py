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
from fastapi.responses import HTMLResponse, JSONResponse
from loguru import logger
import uvicorn

from .core.config import settings
from .core.security import http_request_allowed, websocket_allowed
from .services.deepgram_service import DeepgramService
from .services.propresenter_service import ProPresenterService
from .services.verse_parser import VerseParserService
from .services.database import DatabaseService, get_database
from .services.vosk_service import VoskService
from .services.ai_service import AIService
from .api.routes import router as api_router


# Services globaux
deepgram_service: DeepgramService | None = None
propresenter_service: ProPresenterService | None = None
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
    "background": "black"
}

async def broadcast_projection(text: str, reference: str, background: str | None = None):
    """Diffuse le slide à tous les projecteurs connectés"""
    global current_projection_slide
    current_projection_slide = {
        "text": text,
        "reference": reference,
        "background": background or current_projection_slide.get("background", "black")
    }
    for conn in list(projector_connections):
        try:
            await conn.send_json(current_projection_slide)
        except Exception as e:
            logger.debug(f"Erreur envoi client projection: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestion du cycle de vie de l'application"""
    global deepgram_service, propresenter_service, verse_parser, db_service, vosk_service, ai_service, current_session_id
    
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
    propresenter_service = ProPresenterService(
        host=settings.PROPRESENTER_HOST,
        port=settings.PROPRESENTER_PORT
    )
    verse_parser = VerseParserService()
    vosk_service = VoskService()
    ai_service = AIService()
    
    # Chargement en arrière-plan du modèle local Vosk pour éviter de bloquer l'application
    threading.Thread(target=vosk_service.initialize, daemon=True).start()
    
    # Connexion à ProPresenter
    if settings.PROPRESENTER_AUTO_CONNECT:
        connected = await propresenter_service.connect()
        if connected:
            logger.info("✅ Connecté à ProPresenter")
        else:
            logger.warning("⚠️ ProPresenter non détecté (démarrage quand même)")
    
    logger.info("✅ Services initialisés")
    
    yield
    
    # Shutdown
    logger.info("🛑 Arrêt de VersePro v2...")
    
    if current_session_id:
        await db_service.end_session(current_session_id)
    
    if deepgram_service:
        await deepgram_service.disconnect()
    if propresenter_service:
        await propresenter_service.disconnect()
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
    if propresenter_service:
        propresenter_connected = await propresenter_service.is_connected()
    
    return {
        "status": "healthy",
        "services": {
            "deepgram": deepgram_service is not None,
            "propresenter": propresenter_connected,
            "parser": verse_parser is not None,
            "vosk_loaded": vosk_service.initialized if vosk_service else False
        }
    }


# Endpoints de Projection Web Autonome
@app.get("/projection", response_class=HTMLResponse)
async def get_projection_page():
    """Sert l'écran de projection HTML5 natif"""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Écran de Projection - VersePro</title>
        <style>
            body {
                margin: 0;
                padding: 0;
                background-color: #000;
                color: #fff;
                /* Pile de polices système : aucune dépendance réseau (usage hors-ligne) */
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
                overflow: hidden;
                display: flex;
                align-items: center;
                justify-content: center;
                height: 100vh;
                text-align: center;
                transition: background-color 0.3s ease;
            }
            .chroma-green {
                background-color: #00ff00 !important;
            }
            .chroma-blue {
                background-color: #0000ff !important;
            }
            #container {
                width: 85%;
                max-width: 1200px;
                opacity: 0;
                transform: translateY(20px);
                transition: opacity 0.4s cubic-bezier(0.4, 0, 0.2, 1), transform 0.4s cubic-bezier(0.4, 0, 0.2, 1);
            }
            #container.visible {
                opacity: 1;
                transform: translateY(0);
            }
            #text {
                font-size: 3.5rem;
                line-height: 1.4;
                font-weight: 500;
                margin-bottom: 2rem;
                text-shadow: 2px 2px 8px rgba(0, 0, 0, 0.9);
            }
            #reference {
                font-size: 2.2rem;
                font-weight: 700;
                color: #3b82f6; /* Bleu moderne */
                text-transform: uppercase;
                letter-spacing: 2px;
                text-shadow: 2px 2px 8px rgba(0, 0, 0, 0.9);
            }
        </style>
    </head>
    <body>
        <div id="container">
            <div id="text">En attente d'affichage...</div>
            <div id="reference"></div>
        </div>
        <script>
            const container = document.getElementById('container');
            const textEl = document.getElementById('text');
            const refEl = document.getElementById('reference');
            
            let ws;
            function connect() {
                const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                const wsUrl = `${proto}//${window.location.host}/ws/projection`;
                ws = new WebSocket(wsUrl);
                
                ws.onopen = () => {
                    console.log('🔗 Connecté au flux de projection');
                    container.classList.add('visible');
                };
                
                ws.onmessage = (event) => {
                    const data = JSON.parse(event.data);
                    
                    // Gestion de la couleur d'arrière-plan (Chroma Key)
                    document.body.className = '';
                    if (data.background === 'green') {
                        document.body.classList.add('chroma-green');
                    } else if (data.background === 'blue') {
                        document.body.classList.add('chroma-blue');
                    }
                    
                    // Effet de transition fluide
                    container.classList.remove('visible');
                    
                    setTimeout(() => {
                        textEl.textContent = data.text || '';
                        refEl.textContent = data.reference || '';
                        
                        if (data.text || data.reference) {
                            container.classList.add('visible');
                        }
                    }, 400);
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


@app.websocket("/ws/projection")
async def websocket_projection(websocket: WebSocket):
    """WebSocket pour les écrans de projection (écoute uniquement)"""
    await websocket.accept()
    projector_connections.add(websocket)
    try:
        # Envoie immédiatement l'état courant
        await websocket.send_json(current_projection_slide)
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        projector_connections.discard(websocket)


@app.post("/api/v1/project")
async def project_slide(slide: dict):
    """Envoie manuellement un contenu à projeter"""
    global current_projection_slide
    text = slide.get("text", "")
    ref = slide.get("reference", "")
    bg = slide.get("background", "black")
    
    await broadcast_projection(text, ref, bg)
    
    # Optionnel: envoi à ProPresenter également
    if slide.get("send_to_propresenter", False) and propresenter_service and ref:
        await propresenter_service.show_verse({"reference": ref, "text": text})
        
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
                            await broadcast_projection(ref.get("text", ""), ref["reference"])
                            sent = await propresenter_service.show_verse(ref)
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


@app.websocket("/ws/propresenter")
async def websocket_propresenter(websocket: WebSocket):
    """Contrôle manuel de la projection"""
    if not websocket_allowed(websocket):
        await websocket.close(code=1008, reason="Jeton API requis pour les clients distants")
        return

    await websocket.accept()
    if not propresenter_service:
        await websocket.close(code=1011, reason="Service non initialisé")
        return
        
    try:
        logger.info("📺 Session contrôle manuel ouverte")
        while True:
            data = await websocket.receive_json()
            action = data.get("action")
            
            if action == "send_reference":
                ref = data.get("reference")
                if ref:
                    # Envoi à ProPresenter
                    parsed = await verse_parser.parse(ref) if verse_parser else None
                    sent = await propresenter_service.show_verse(parsed or ref)
                    
                    # Récupère le texte de la bible pour le projeter sur l'écran autonome
                    if parsed:
                        await broadcast_projection(parsed.get("text", ""), parsed["reference"])
                            
                    await websocket.send_json({
                        "type": "send_result",
                        "success": sent,
                        "reference": ref
                    })
                    
            elif action == "clear":
                cleared = await propresenter_service.clear_display()
                await broadcast_projection("", "")  # Efface l'écran autonome
                await websocket.send_json({
                    "type": "clear_result",
                    "success": cleared
                })
                
            elif action == "status":
                status = await propresenter_service.get_status()
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
