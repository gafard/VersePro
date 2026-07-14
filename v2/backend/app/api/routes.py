"""
Routes API REST pour VersePro v2
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from loguru import logger

router = APIRouter()


SECRET_SETTING_KEYS = {"deepgram_api_key", "openrouter_api_key", "gemini_api_key"}


def _vad_available() -> bool:
    try:
        from ..services.vad_service import vad_available
        return vad_available()
    except Exception:
        return False


def _mask_secret(value: str) -> str:
    """Expose only a short hint so API keys never leave the backend in clear text."""
    if not value:
        return ""
    if len(value) <= 8:
        return "configured"
    return f"{value[:4]}...{value[-4:]}"


def _redact_update(update: Dict[str, Any]) -> Dict[str, Any]:
    """Keep settings logs useful without leaking credentials."""
    redacted = dict(update)
    for key in SECRET_SETTING_KEYS:
        if key in redacted:
            redacted[key] = _mask_secret(str(redacted[key] or ""))
    return redacted


# Modèles Pydantic
class ReferenceRequest(BaseModel):
    """Requête d'envoi de référence"""
    reference: str
    text: Optional[str] = None
    version: Optional[str] = "LSG"


class ParseRequest(BaseModel):
    text: str
    skip_text_search: bool = False


class SettingsUpdate(BaseModel):
    auto_send: Optional[bool] = None
    bible_version: Optional[str] = None
    propresenter_host: Optional[str] = None
    propresenter_port: Optional[int] = None
    deepgram_model: Optional[str] = None
    deepgram_language: Optional[str] = None
    ai_agent_enabled: Optional[bool] = None
    deepgram_api_key: Optional[str] = None
    openrouter_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    ai_confidence_threshold: Optional[int] = None
    ai_filtering_mode: Optional[str] = None
    voice_gate_enabled: Optional[bool] = None
    asr_default_engine: Optional[str] = None
    local_semantic_enabled: Optional[bool] = None
    local_semantic_threshold: Optional[float] = None


class PrepareModelRequest(BaseModel):
    model: Optional[str] = None


class SemanticSearchRequest(BaseModel):
    text: str
    top_k: int = 5


class ReferenceResponse(BaseModel):
    """Réponse de référence"""
    success: bool
    reference: str
    message: Optional[str] = None


class TranscriptResponse(BaseModel):
    """Réponse de transcription"""
    text: str
    language: str = "fr"
    confidence: Optional[float] = None


class HealthResponse(BaseModel):
    """Réponse de santé"""
    status: str
    version: str
    services: Dict[str, bool]


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Endpoint de santé"""
    from ..main import output_manager, deepgram_service, verse_parser
    
    propresenter_connected = False
    if output_manager and "propresenter" in output_manager.outputs:
        propresenter_connected = await output_manager.outputs["propresenter"].is_connected()
    
    return {
        "status": "healthy",
        "version": "2.0.0",
        "services": {
            "deepgram": deepgram_service is not None,
            "propresenter": propresenter_connected,
            "parser": verse_parser is not None
        }
    }


@router.post("/references/send")
async def send_reference(request: ReferenceRequest):
    """
    Envoie manuellement une référence vers TOUS les canaux de projection :
    l'écran autonome local (broadcast WebSocket) et ProPresenter si connecté.

    Utile pour:
    - Validation manuelle avant envoi
    - Correction de référence détectée
    - Envoi direct sans détection audio
    """
    from ..main import output_manager, verse_parser, broadcast_projection

    # Résout la référence pour récupérer le texte du verset
    parsed = None
    if verse_parser:
        parsed = await verse_parser.parse(request.reference, skip_text_search=True)

    reference = parsed or {
        "reference": request.reference,
        "text": request.text or "",
        "version": request.version,
    }

    # 1. Écran de projection autonome (toujours disponible)
    await broadcast_projection(
        reference.get("text") or request.text or "",
        reference.get("reference", request.reference),
        translations=reference.get("translations") if isinstance(reference, dict) else None,
    )

    # 2. ProPresenter (meilleur effort via OutputManager)
    sent_propresenter = False
    if output_manager and "propresenter" in output_manager.outputs:
        pp_driver = output_manager.outputs["propresenter"]
        if pp_driver.enabled:
            sent_propresenter = await pp_driver.send_scene({
                "reference": reference.get("reference", request.reference),
                "text": reference.get("text") or request.text or ""
            })

    return {
        "success": True,
        "reference": reference.get("reference", request.reference),
        "text": reference.get("text") or request.text or "",
        "propresenter_sent": sent_propresenter,
        "message": "Verset projeté" + (" (+ ProPresenter)" if sent_propresenter else " (écran autonome)"),
    }


@router.post("/references/parse")
async def parse_reference(request: ParseRequest):
    """
    Parse un texte pour extraire une référence biblique
    
    Utile pour tester le parser sans audio
    """
    from ..main import verse_parser
    
    if not verse_parser:
        raise HTTPException(status_code=503, detail="Service parser non disponible")
    
    reference = await verse_parser.parse(request.text, skip_text_search=request.skip_text_search)
    
    if reference:
        return {
            "success": True,
            "reference": reference,
            "input_text": request.text
        }
    else:
        return {
            "success": False,
            "reference": None,
            "input_text": request.text,
            "message": "Aucune référence détectée"
        }


@router.get("/bible/search")
async def bible_search(q: str, limit: int = 6):
    """
    Recherche unifiée pour la palette de commande :
    référence explicite (Jn 3:16, "rom 8 28"), début de texte, citation approximative.
    Renvoie plusieurs candidats avec texte et score, sans rien projeter.
    """
    from ..main import verse_parser

    if not verse_parser or not q or not q.strip():
        return {"results": []}

    query = q.strip()
    results = []
    seen = set()

    # 1. Référence explicite (avec texte du verset)
    explicit = await verse_parser.parse(query, skip_text_search=True)
    if explicit:
        key = explicit["reference"]
        seen.add(key)
        results.append(explicit)
        # Propose aussi les 2 versets suivants (lecture de passage)
        if explicit.get("verse_start") is not None:
            for offset in (1, 2):
                v = explicit["verse_start"] + offset
                text = verse_parser.bible_loader.get_verse_text(explicit["book_abbr"], explicit["chapter"], v)
                if text:
                    results.append({
                        "reference": f"{explicit['book_abbr']} {explicit['chapter']}:{v}",
                        "book_abbr": explicit["book_abbr"],
                        "chapter": explicit["chapter"],
                        "verse_start": v,
                        "text": text,
                        "detection_method": "adjacent",
                        "confidence": 0.5,
                    })

    # 2. Recherche textuelle (exacte puis floue)
    if len(query) >= 8:
        for cand in verse_parser.bible_loader.search_candidates(query, limit=limit):
            if cand["reference"] not in seen:
                seen.add(cand["reference"])
                results.append(cand)

    return {"results": results[:limit]}


@router.get("/session/current")
async def get_current_session():
    """ID de la session de culte en cours (pour restaurer la file après un rechargement)"""
    from .. import main as main_module
    return {"session_id": main_module.current_session_id}


class RehearseRequest(BaseModel):
    transcript: str


@router.post("/rehearse")
async def rehearse(request: RehearseRequest):
    """
    Mode répétition : rejoue un transcript complet dans la chaîne de détection
    (fenêtres glissantes de mots, comme en direct) SANS rien projeter.
    Permet de valider la reconnaissance avant le culte.
    """
    from ..main import verse_parser, run_detection_cascade

    if not verse_parser:
        raise HTTPException(status_code=503, detail="Parser non disponible")

    words = request.transcript.split()
    detections = []
    seen = set()

    # Rejoue EXACTEMENT la cascade du direct (explicite + fusion hybride des
    # paraphrases), fenêtre par fenêtre. Chaque fin de fenêtre est un « final ».
    for end in range(6, len(words) + 1, 3):
        window = " ".join(words[max(0, end - 40):end])
        ref = await run_detection_cascade(window, final_state=True)
        if ref and ref["reference"] not in seen:
            seen.add(ref["reference"])
            detections.append({
                "reference": ref["reference"],
                "text": ref.get("text", ""),
                "detection_method": ref.get("detection_method"),
                "confidence": ref.get("confidence"),
                "fusion": ref.get("fusion"),
                "window": window[-90:],
            })

    return {"detections": detections, "total": len(detections)}


@router.get("/propresenter/status")
async def propresenter_status():
    """Récupère le statut de ProPresenter"""
    from ..main import output_manager
    
    if not output_manager or "propresenter" not in output_manager.outputs:
        raise HTTPException(status_code=503, detail="Service non disponible")
        
    pp_driver = output_manager.outputs["propresenter"]
    
    return {
        "connected": await pp_driver.is_connected(),
        "status": {"enabled": pp_driver.enabled},
        "stats": getattr(pp_driver, "stats", {})
    }


@router.post("/propresenter/clear")
async def clear_display():
    """Efface l'affichage ProPresenter"""
    from ..main import output_manager
    
    if not output_manager or "propresenter" not in output_manager.outputs:
        raise HTTPException(status_code=503, detail="Service non disponible")
        
    pp_driver = output_manager.outputs["propresenter"]
    cleared = await pp_driver.clear()
    
    return {
        "success": cleared,
        "message": "Affichage effacé" if cleared else "Échec de l'effacement"
    }



@router.get("/vosk/status")
async def get_vosk_status():
    """Récupère le statut du modèle Vosk local"""
    from ..main import vosk_service
    if not vosk_service:
        return {"installed": False, "downloading": False, "model_name": "", "model_type": ""}
    
    import os
    installed = os.path.exists(vosk_service.model_dir) and vosk_service.initialized
    return {
        "installed": installed,
        "downloading": vosk_service.downloading,
        "download_progress": getattr(vosk_service, "download_progress", 0.0),
        "model_name": vosk_service.model_name,
        "model_type": vosk_service.model_type,
        "last_error": getattr(vosk_service, "last_error", "")
    }


@router.post("/vosk/download")
async def download_vosk_model():
    """Déclenche le téléchargement du modèle Vosk en tâche de fond"""
    from ..main import vosk_service
    if not vosk_service:
        raise HTTPException(status_code=503, detail="Service Vosk non disponible")
    
    import os
    import asyncio
    if os.path.exists(vosk_service.model_dir) and vosk_service.initialized:
        return {"status": "already_installed", "message": "Le modèle Vosk est déjà installé"}

    if vosk_service.downloading:
        return {"status": "downloading", "message": "Téléchargement déjà en cours"}

    # Déclenche l'initialisation (téléchargement en arrière-plan, ou chargement du
    # modèle déjà présent — potentiellement long, donc hors event loop)
    await asyncio.to_thread(vosk_service.initialize)
    return {"status": "started", "message": "Téléchargement du modèle Vosk démarré en arrière-plan"}


@router.get("/asr/status")
async def get_asr_status():
    """Capacites locales et recommandation adaptee a la machine."""
    from ..main import vosk_service
    from ..core.config import settings

    return {
        "default_engine": settings.ASR_DEFAULT_ENGINE,
        "vosk": {
            "available": bool(vosk_service and vosk_service.initialized),
            "model": getattr(vosk_service, "model_name", ""),
        },
    }


@router.post("/asr/prepare")

@router.get("/semantic/status")
async def get_semantic_status():
    from ..main import semantic_service
    return semantic_service.status() if semantic_service else {"enabled": False, "installed": False}


@router.post("/semantic/prepare")
async def prepare_semantic_index():
    """Installe le modele ONNX et indexe le corpus biblique en arriere-plan."""
    from ..main import semantic_service
    if not semantic_service:
        raise HTTPException(status_code=503, detail="Service semantique indisponible")
    import threading
    if not semantic_service.indexing:
        threading.Thread(
            target=semantic_service.initialize,
            kwargs={"allow_download": True},
            daemon=True,
        ).start()
    return {"status": "preparing", **semantic_service.status()}


@router.post("/semantic/search")
async def semantic_search(request: SemanticSearchRequest):
    from ..main import semantic_service
    if not semantic_service or not semantic_service.initialized:
        raise HTTPException(status_code=503, detail="Index semantique non prepare")
    import asyncio
    results = await asyncio.to_thread(semantic_service.search, request.text, min(max(request.top_k, 1), 10))
    return {"results": results}


@router.get("/settings")
async def get_settings():
    """Récupère la configuration"""
    from ..core.config import settings
    from ..main import ai_service, output_manager, semantic_service
    
    propresenter_connected = False
    if output_manager and "propresenter" in output_manager.outputs:
        propresenter_connected = await output_manager.outputs["propresenter"].is_connected()
        
    return {
        "deepgram_model": settings.DEEPGRAM_MODEL,
        "deepgram_language": settings.DEEPGRAM_LANGUAGE,
        "propresenter_host": settings.PROPRESENTER_HOST,
        "propresenter_port": settings.PROPRESENTER_PORT,
        "auto_send": settings.PROPRESENTER_AUTO_SEND,
        "bible_version": settings.BIBLE_VERSION,
        "ai_agent_enabled": settings.AI_AGENT_ENABLED,
        "ai_available": bool(ai_service and ai_service.enabled),
        "propresenter_connected": propresenter_connected,
        "deepgram_api_key_configured": bool(settings.DEEPGRAM_API_KEY),
        "openrouter_api_key_configured": bool(settings.OPENROUTER_API_KEY),
        "gemini_api_key_configured": bool(settings.GEMINI_API_KEY),
        "deepgram_api_key_hint": _mask_secret(settings.DEEPGRAM_API_KEY),
        "openrouter_api_key_hint": _mask_secret(settings.OPENROUTER_API_KEY),
        "gemini_api_key_hint": _mask_secret(settings.GEMINI_API_KEY),
        "ai_confidence_threshold": settings.AI_CONFIDENCE_THRESHOLD,
        "ai_filtering_mode": settings.AI_FILTERING_MODE,
        "voice_gate_enabled": settings.VOICE_GATE_ENABLED,
        "voice_gate_available": _vad_available(),
        "asr_default_engine": settings.ASR_DEFAULT_ENGINE,
        "local_semantic_enabled": settings.LOCAL_SEMANTIC_ENABLED,
        "local_semantic_threshold": semantic_service.active_threshold if semantic_service else settings.LOCAL_SEMANTIC_THRESHOLD,
        "local_semantic_model": settings.LOCAL_SEMANTIC_MODEL,
        "semantic_status": semantic_service.status() if semantic_service else {},
    }


@router.post("/settings")
async def update_settings(settings_update: SettingsUpdate):
    """Met à jour la configuration et la persiste dans SQLite"""
    from ..core.config import settings
    from ..main import output_manager, verse_parser, ai_service, deepgram_service, semantic_service
    from ..services.database import get_database
    
    db = get_database()
    update = settings_update.model_dump(exclude_unset=True)
    logger.info(f"Mise à jour settings: {_redact_update(update)}")

    reconnect_propresenter = False

    if "auto_send" in update:
        settings.PROPRESENTER_AUTO_SEND = bool(update["auto_send"])
        await db.set_setting("auto_send", settings.PROPRESENTER_AUTO_SEND)
        
    if update.get("bible_version"):
        version = update["bible_version"].upper()
        settings.BIBLE_VERSION = version
        await db.set_setting("bible_version", settings.BIBLE_VERSION)
        if verse_parser and verse_parser.bible_loader and version in verse_parser.bible_loader.versions:
            verse_parser.bible_loader.active_version = version
            if semantic_service:
                semantic_service.reset()
                import threading
                threading.Thread(
                    target=semantic_service.initialize,
                    kwargs={"allow_download": False},
                    daemon=True,
                ).start()
            
    if update.get("propresenter_host"):
        settings.PROPRESENTER_HOST = update["propresenter_host"]
        await db.set_setting("propresenter_host", settings.PROPRESENTER_HOST)
        if output_manager and "propresenter" in output_manager.outputs:
            output_manager.outputs["propresenter"].host = settings.PROPRESENTER_HOST
            reconnect_propresenter = True
            
    if update.get("propresenter_port") is not None:
        settings.PROPRESENTER_PORT = int(update["propresenter_port"])
        await db.set_setting("propresenter_port", settings.PROPRESENTER_PORT)
        if output_manager and "propresenter" in output_manager.outputs:
            output_manager.outputs["propresenter"].port = settings.PROPRESENTER_PORT
            reconnect_propresenter = True
            
    if update.get("deepgram_model"):
        settings.DEEPGRAM_MODEL = update["deepgram_model"]
        await db.set_setting("deepgram_model", settings.DEEPGRAM_MODEL)
        
    if update.get("deepgram_language"):
        settings.DEEPGRAM_LANGUAGE = update["deepgram_language"]
        await db.set_setting("deepgram_language", settings.DEEPGRAM_LANGUAGE)
        
    if "ai_agent_enabled" in update:
        settings.AI_AGENT_ENABLED = bool(update["ai_agent_enabled"])
        await db.set_setting("ai_agent_enabled", settings.AI_AGENT_ENABLED)
        if ai_service:
            ai_service.enabled = settings.AI_AGENT_ENABLED and (
                bool(ai_service.openrouter_key) or bool(ai_service.api_key) or bool(ai_service.ollama_url)
            )
            
    if update.get("deepgram_api_key"):
        settings.DEEPGRAM_API_KEY = update["deepgram_api_key"]
        await db.set_setting("deepgram_api_key", settings.DEEPGRAM_API_KEY)
        if deepgram_service:
            deepgram_service.api_key = settings.DEEPGRAM_API_KEY
            if settings.DEEPGRAM_API_KEY:
                deepgram_service._init_client()
                
    if update.get("openrouter_api_key"):
        settings.OPENROUTER_API_KEY = update["openrouter_api_key"]
        await db.set_setting("openrouter_api_key", settings.OPENROUTER_API_KEY)
        if ai_service:
            ai_service.openrouter_key = settings.OPENROUTER_API_KEY
            ai_service.enabled = settings.AI_AGENT_ENABLED and (
                bool(ai_service.openrouter_key) or bool(ai_service.api_key) or bool(ai_service.ollama_url)
            )
            
    if update.get("gemini_api_key"):
        settings.GEMINI_API_KEY = update["gemini_api_key"]
        await db.set_setting("gemini_api_key", settings.GEMINI_API_KEY)
        if ai_service:
            ai_service.api_key = settings.GEMINI_API_KEY
            ai_service.enabled = settings.AI_AGENT_ENABLED and (
                bool(ai_service.openrouter_key) or bool(ai_service.api_key) or bool(ai_service.ollama_url)
            )
            
    if "ai_confidence_threshold" in update:
        settings.AI_CONFIDENCE_THRESHOLD = int(update["ai_confidence_threshold"])
        await db.set_setting("ai_confidence_threshold", settings.AI_CONFIDENCE_THRESHOLD)
        
    if "ai_filtering_mode" in update:
        settings.AI_FILTERING_MODE = str(update["ai_filtering_mode"])
        await db.set_setting("ai_filtering_mode", settings.AI_FILTERING_MODE)

    if "voice_gate_enabled" in update:
        settings.VOICE_GATE_ENABLED = bool(update["voice_gate_enabled"])
        await db.set_setting("voice_gate_enabled", settings.VOICE_GATE_ENABLED)

    if update.get("asr_default_engine"):
        engine = str(update["asr_default_engine"])
        if engine not in {"auto", "deepgram", "vosk"}:
            raise HTTPException(status_code=400, detail="Moteur ASR invalide")
        settings.ASR_DEFAULT_ENGINE = engine
        await db.set_setting("asr_default_engine", engine)

    if "local_semantic_enabled" in update:
        settings.LOCAL_SEMANTIC_ENABLED = bool(update["local_semantic_enabled"])
        await db.set_setting("local_semantic_enabled", settings.LOCAL_SEMANTIC_ENABLED)

    if "local_semantic_threshold" in update:
        threshold = float(update["local_semantic_threshold"])
        if not 0.4 <= threshold <= 0.98:
            raise HTTPException(status_code=400, detail="Seuil semantique hors limites")
        # Le curseur agit sur le modèle réellement actif (Qwen ou e5), chacun
        # ayant sa propre échelle de scores. Ainsi le réglage suit l'encodeur.
        active = (semantic_service.active_model if semantic_service else None) or settings.LOCAL_SEMANTIC_MODEL
        settings.LOCAL_SEMANTIC_CALIBRATION.setdefault(active, {})["threshold"] = threshold
        settings.LOCAL_SEMANTIC_THRESHOLD = threshold
        await db.set_setting(f"local_semantic_threshold_{active}", threshold)

    if reconnect_propresenter and output_manager and "propresenter" in output_manager.outputs:
        pp_driver = output_manager.outputs["propresenter"]
        await pp_driver.disconnect()
        if settings.PROPRESENTER_AUTO_CONNECT:
            await pp_driver.connect()

    return await get_settings()


# ============================================
# Routes Historique & Statistiques
# ============================================

@router.get("/history/verses")
async def get_history(limit: int = 50, session_id: Optional[int] = None):
    """Récupère l'historique des versets détectés"""
    from ..services.database import get_database
    
    db = get_database()
    if not db.db:
        raise HTTPException(status_code=503, detail="Base de données non connectée")
    
    verses = await db.get_recent_verses(limit=limit, session_id=session_id)
    
    return {
        "verses": verses,
        "total": len(verses)
    }


@router.get("/history/verses/{verse_id}")
async def get_verse(verse_id: int):
    """Récupère un verset spécifique"""
    from ..services.database import get_database
    
    db = get_database()
    verse = await db.get_verse_by_id(verse_id)
    
    if not verse:
        raise HTTPException(status_code=404, detail="Verset non trouvé")
    
    return verse


@router.delete("/history/verses/{verse_id}")
async def delete_verse(verse_id: int):
    """Supprime un verset de l'historique"""
    from ..services.database import get_database
    
    db = get_database()
    await db.delete_verse(verse_id)
    
    return {"success": True, "message": "Verset supprimé"}


@router.post("/history/verses/{verse_id}/validate")
async def validate_verse(verse_id: int, validated: bool = True):
    """Valide manuellement un verset"""
    from ..services.database import get_database
    
    db = get_database()
    await db.update_verse_validation(verse_id, validated)
    
    return {"success": True}


@router.get("/history/sessions")
async def get_sessions(limit: int = 10):
    """Récupère l'historique des sessions"""
    from ..services.database import get_database
    
    db = get_database()
    sessions = await db.get_recent_sessions(limit=limit)
    
    return {
        "sessions": sessions,
        "total": len(sessions)
    }


@router.post("/history/sessions/start")
async def start_session(name: Optional[str] = None):
    """Démarre une nouvelle session"""
    from ..services.database import get_database
    
    db = get_database()
    session_id = await db.create_session(name)
    
    return {"success": True, "session_id": session_id}


@router.post("/history/sessions/{session_id}/end")
async def end_session(session_id: int):
    """Termine une session"""
    from ..services.database import get_database
    
    db = get_database()
    await db.end_session(session_id)
    
    return {"success": True}


@router.get("/history/sessions/{session_id}")
async def get_session_detail(session_id: int):
    """Récupère une session spécifique avec sa transcription et son résumé"""
    from ..services.database import get_database
    
    db = get_database()
    session = await db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session non trouvée")
    
    return session


@router.post("/history/sessions/{session_id}/summary")
async def generate_session_summary(session_id: int):
    """Génère le résumé d'une session par l'IA et l'enregistre"""
    from ..services.database import get_database
    from ..main import ai_service
    
    if not ai_service or not ai_service.enabled:
         raise HTTPException(status_code=503, detail="Agent IA non configuré ou inactif")
         
    db = get_database()
    session = await db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session non trouvée")
        
    transcript = session.get("transcript")
    if not transcript or not transcript.strip():
        raise HTTPException(status_code=400, detail="La transcription de cette session est vide. Impossible de résumer.")
        
    # Génération du résumé par l'Agent IA
    summary = await ai_service.generate_sermon_summary(transcript)
    if not summary:
        raise HTTPException(status_code=500, detail="Échec de la génération du résumé par l'Agent IA")
        
    # Enregistrement
    await db.update_session_summary(session_id, summary)
    
    return {"success": True, "summary": summary}


@router.get("/statistics")
async def get_statistics(days: int = 30):
    """Récupère les statistiques complètes"""
    from ..services.database import get_database
    
    db = get_database()
    if not db.db:
        raise HTTPException(status_code=503, detail="Base de données non connectée")
    
    stats = await db.get_statistics(days=days)
    
    return stats


@router.get("/statistics/books")
async def get_book_statistics(days: int = 30):
    """Statistiques par livre de la Bible"""
    from ..services.database import get_database
    
    db = get_database()
    books = await db.get_book_statistics(days=days)
    
    return {"books": books}


@router.get("/statistics/daily/{date}")
async def get_daily_stats(date: str):
    """Statistiques pour un jour spécifique (YYYY-MM-DD)"""
    from ..services.database import get_database
    
    db = get_database()
    stats = await db.get_daily_stats(date)
    
    return stats


@router.post("/history/export/csv")
async def export_csv(session_id: Optional[int] = None):
    """Exporte l'historique en CSV"""
    from ..services.database import get_database
    from fastapi.responses import FileResponse
    from starlette.background import BackgroundTask
    import tempfile
    import os

    db = get_database()

    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        output_path = f.name

    await db.export_to_csv(output_path, session_id=session_id)

    return FileResponse(
        output_path,
        media_type="text/csv",
        filename="versepro_export.csv",
        background=BackgroundTask(os.remove, output_path)
    )


@router.post("/history/export/json")
async def export_json(session_id: Optional[int] = None):
    """Exporte l'historique en JSON"""
    from ..services.database import get_database
    from fastapi.responses import FileResponse
    from starlette.background import BackgroundTask
    import tempfile
    import os

    db = get_database()

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        output_path = f.name

    await db.export_to_json(output_path, session_id=session_id)

    return FileResponse(
        output_path,
        media_type="application/json",
        filename="versepro_export.json",
        background=BackgroundTask(os.remove, output_path)
    )


# ── HTTP CONTROL API (STREAM DECK / PHYSICAL CONTROLLERS) ──

class ControlProjectRequest(BaseModel):
    reference: str
    text: Optional[str] = None
    version: Optional[str] = None

@router.post("/control/project")
async def control_project(req: ControlProjectRequest):
    """Projette une référence directement à l'antenne à distance"""
    from ..main import output_manager, verse_parser, broadcast_projection
    
    parsed = None
    if verse_parser:
        parsed = await verse_parser.parse(req.reference)
        
    ref_name = parsed.get("reference") if parsed else req.reference
    ref_text = parsed.get("text") if parsed else (req.text or "")
    translations = parsed.get("translations") if parsed else None
    
    await broadcast_projection(ref_text, ref_name, translations=translations)
    if output_manager:
        await output_manager.project(ref_text, ref_name, translations=translations)
        
    return {
        "success": True, 
        "reference": ref_name, 
        "text": ref_text
    }

@router.post("/control/clear")
async def control_clear():
    """Efface toutes les projections de l'écran (black screen)"""
    from ..main import output_manager, broadcast_projection
    await broadcast_projection("", "")
    if output_manager:
        await output_manager.clear()
    return {"success": True}

@router.post("/control/next")
async def control_next():
    """Navigue vers le verset suivant dans le passage en cours"""
    from ..main import output_manager, broadcast_projection, current_projection_slide
    if current_projection_slide and current_projection_slide.get("next_reference"):
        next_ref = current_projection_slide["next_reference"]
        next_text = current_projection_slide["next_text"]
        await broadcast_projection(next_text, next_ref)
        if output_manager:
            await output_manager.project(next_text, next_ref)
        return {"success": True, "reference": next_ref, "text": next_text}
    return {"success": False, "detail": "Aucun verset suivant disponible"}

@router.post("/control/prev")
async def control_prev():
    """Navigue vers le verset précédent dans le passage en cours"""
    from ..main import output_manager, broadcast_projection, current_projection_slide, verse_parser
    ref = current_projection_slide.get("reference")
    if ref and verse_parser:
        try:
            parsed = await verse_parser.parse(ref, skip_text_search=True)
            if parsed and parsed.get("verse_start") is not None:
                prev_v = parsed["verse_start"] - 1
                if prev_v > 0:
                    prev_text = verse_parser.bible_loader.get_verse_text(parsed["book_abbr"], parsed["chapter"], prev_v)
                    if prev_text:
                        prev_ref = f"{parsed['book_abbr']} {parsed['chapter']}:{prev_v}"
                        await broadcast_projection(prev_text, prev_ref)
                        if output_manager:
                            await output_manager.project(prev_text, prev_ref)
                        return {"success": True, "reference": prev_ref, "text": prev_text}
        except Exception:
            pass
    return {"success": False, "detail": "Aucun verset précédent disponible"}

@router.get("/control/status")
async def control_status():
    """Renvoie l'état courant de la projection"""
    from ..main import current_projection_slide
    return {
        "on_air": bool(current_projection_slide.get("reference")),
        "reference": current_projection_slide.get("reference", ""),
        "text": current_projection_slide.get("text", ""),
        "next_reference": current_projection_slide.get("next_reference", ""),
        "next_text": current_projection_slide.get("next_text", "")
    }
