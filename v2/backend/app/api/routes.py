"""
Routes API REST pour VersePro v2
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from loguru import logger

router = APIRouter()


SECRET_SETTING_KEYS = {"deepgram_api_key", "openrouter_api_key", "gemini_api_key"}


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
    from ..main import propresenter_service, deepgram_service, verse_parser
    
    propresenter_connected = False
    if propresenter_service:
        propresenter_connected = await propresenter_service.is_connected()
    
    return {
        "status": "healthy",
        "version": "2.0.0",
        "services": {
            "deepgram": deepgram_service is not None,
            "propresenter": propresenter_connected,
            "parser": verse_parser is not None
        }
    }


@router.post("/references/send", response_model=ReferenceResponse)
async def send_reference(request: ReferenceRequest):
    """
    Envoie manuellement une référence à ProPresenter
    
    Utile pour:
    - Validation manuelle avant envoi
    - Correction de référence détectée
    - Envoi direct sans détection audio
    """
    from ..main import propresenter_service
    
    if not propresenter_service:
        raise HTTPException(status_code=503, detail="Service ProPresenter non disponible")
    
    reference = {
        "reference": request.reference,
        "text": request.text,
        "version": request.version
    }
    
    sent = await propresenter_service.show_verse(reference)
    
    if sent:
        return {
            "success": True,
            "reference": request.reference,
            "message": "Verset envoyé à ProPresenter"
        }
    else:
        raise HTTPException(
            status_code=500,
            detail="Échec de l'envoi à ProPresenter"
        )


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


@router.get("/propresenter/status")
async def propresenter_status():
    """Récupère le statut de ProPresenter"""
    from ..main import propresenter_service
    
    if not propresenter_service:
        raise HTTPException(status_code=503, detail="Service non disponible")
    
    status = await propresenter_service.get_status()
    stats = propresenter_service.get_stats()
    
    return {
        "connected": await propresenter_service.is_connected(),
        "status": status,
        "stats": stats
    }


@router.post("/propresenter/clear")
async def clear_display():
    """Efface l'affichage ProPresenter"""
    from ..main import propresenter_service
    
    if not propresenter_service:
        raise HTTPException(status_code=503, detail="Service non disponible")
    
    cleared = await propresenter_service.clear_display()
    
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
        "model_name": vosk_service.model_name,
        "model_type": vosk_service.model_type
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


@router.get("/settings")
async def get_settings():
    """Récupère la configuration"""
    from ..core.config import settings
    from ..main import ai_service, propresenter_service
    
    return {
        "deepgram_model": settings.DEEPGRAM_MODEL,
        "deepgram_language": settings.DEEPGRAM_LANGUAGE,
        "propresenter_host": settings.PROPRESENTER_HOST,
        "propresenter_port": settings.PROPRESENTER_PORT,
        "auto_send": settings.PROPRESENTER_AUTO_SEND,
        "bible_version": settings.BIBLE_VERSION,
        "ai_agent_enabled": settings.AI_AGENT_ENABLED,
        "ai_available": bool(ai_service and ai_service.enabled),
        "propresenter_connected": await propresenter_service.is_connected() if propresenter_service else False,
        "deepgram_api_key_configured": bool(settings.DEEPGRAM_API_KEY),
        "openrouter_api_key_configured": bool(settings.OPENROUTER_API_KEY),
        "gemini_api_key_configured": bool(settings.GEMINI_API_KEY),
        "deepgram_api_key_hint": _mask_secret(settings.DEEPGRAM_API_KEY),
        "openrouter_api_key_hint": _mask_secret(settings.OPENROUTER_API_KEY),
        "gemini_api_key_hint": _mask_secret(settings.GEMINI_API_KEY),
        "ai_confidence_threshold": settings.AI_CONFIDENCE_THRESHOLD,
        "ai_filtering_mode": settings.AI_FILTERING_MODE,
    }


@router.post("/settings")
async def update_settings(settings_update: SettingsUpdate):
    """Met à jour la configuration et la persiste dans SQLite"""
    from ..core.config import settings
    from ..main import propresenter_service, verse_parser, ai_service, deepgram_service
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
            
    if update.get("propresenter_host"):
        settings.PROPRESENTER_HOST = update["propresenter_host"]
        await db.set_setting("propresenter_host", settings.PROPRESENTER_HOST)
        if propresenter_service:
            propresenter_service.host = settings.PROPRESENTER_HOST
            reconnect_propresenter = True
            
    if update.get("propresenter_port") is not None:
        settings.PROPRESENTER_PORT = int(update["propresenter_port"])
        await db.set_setting("propresenter_port", settings.PROPRESENTER_PORT)
        if propresenter_service:
            propresenter_service.port = settings.PROPRESENTER_PORT
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

    if reconnect_propresenter and propresenter_service:
        await propresenter_service.disconnect()
        if settings.PROPRESENTER_AUTO_CONNECT:
            await propresenter_service.connect()

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
