"""Moteurs de transcription : Vosk, Nemotron, préparation ASR locale."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import asyncio

router = APIRouter()


class PrepareModelRequest(BaseModel):
    model: Optional[str] = None



@router.get("/vosk/status")
async def get_vosk_status():
    """Récupère le statut du modèle Vosk local"""
    from ..main import vosk_service
    if not vosk_service:
        return {"installed": False, "downloading": False, "model_name": "", "model_type": ""}

    installed = vosk_service.initialized or vosk_service.is_installed()
    return {
        "installed": installed,
        "downloading": vosk_service.downloading and not installed,
        "download_progress": getattr(vosk_service, "download_progress", 0.0),
        "download_status": getattr(vosk_service, "download_status", ""),
        "model_name": vosk_service.model_name,
        "model_type": vosk_service.model_type,
        "last_error": getattr(vosk_service, "last_error", "")
    }


@router.get("/nemotron/status")
async def get_nemotron_status():
    """Récupère le statut du modèle Nemotron 3.5-ASR local"""
    from ..main import nemotron_service
    if not nemotron_service:
        return {"installed": False, "downloading": False, "model_name": "nemotron-3.5-asr-streaming-0.6b-Q8_0.gguf"}
    return {
        **nemotron_service.status(),
        "model_name": "nemotron-3.5-asr-streaming-0.6b-Q8_0.gguf",
    }


@router.post("/nemotron/download")
async def download_nemotron_model():
    """Démarre le téléchargement explicite du modèle Nemotron 3.5 ASR GGUF (716 Mo)."""
    # `asyncio` s'importe fonction par fonction dans ce module ; celle-ci
    # l'avait oublié, et levait NameError. Résultat : l'assistant de premier
    # lancement demandait le téléchargement, recevait une erreur 500, et le
    # bénévole restait devant une barre qui ne démarrait jamais.
    import asyncio

    from ..main import nemotron_service
    if not nemotron_service:
        raise HTTPException(status_code=503, detail="Service Nemotron indisponible")

    # `prepare` rend la main tout de suite : il lance son propre thread de
    # téléchargement. On l'appelle quand même hors de la boucle d'événements —
    # il crée des dossiers et vérifie le disque avant de déléguer.
    lance = await asyncio.to_thread(nemotron_service.prepare, True)
    if not lance:
        raise HTTPException(
            status_code=503,
            detail=nemotron_service.last_error or "Téléchargement impossible",
        )
    return {
        "status": "started",
        "message": "Téléchargement du modèle Nemotron 3.5-ASR démarré en arrière-plan",
        **nemotron_service.status(),
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
    await asyncio.to_thread(vosk_service.initialize, True)
    return {"status": "started", "message": "Téléchargement du modèle Vosk démarré en arrière-plan"}


@router.get("/asr/status")
async def get_asr_status():
    """Capacites locales et recommandation adaptee a la machine."""
    from ..main import vosk_service, nemotron_service
    from ..core.config import settings

    return {
        "default_engine": settings.ASR_DEFAULT_ENGINE,
        "vosk": {
            "available": bool(vosk_service and vosk_service.initialized),
            "model": getattr(vosk_service, "model_name", ""),
        },
        "nemotron": nemotron_service.status() if nemotron_service else {"installed": False, "ready": False},
    }


@router.post("/asr/prepare")
async def prepare_local_asr(request: Optional[PrepareModelRequest] = None):
    """Prépare explicitement le moteur local; rien n'est téléchargé au démarrage."""
    from ..main import nemotron_service
    if not nemotron_service:
        raise HTTPException(status_code=503, detail="Service ASR local indisponible")
    if nemotron_service.is_ready and nemotron_service.runtime_available:
        return {"status": "ready", **nemotron_service.status()}
    if nemotron_service.is_ready and not nemotron_service.runtime_available:
        raise HTTPException(
            status_code=503,
            detail=nemotron_service.last_error or "Moteur natif Nemotron absent de l'application",
        )
    if not nemotron_service.downloading:
        import threading
        threading.Thread(
            target=nemotron_service.prepare,
            kwargs={"allow_download": True},
            daemon=True,
        ).start()
    return {"status": "preparing", **nemotron_service.status()}
