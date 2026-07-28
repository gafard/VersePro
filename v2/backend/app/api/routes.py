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
    propresenter_message_name: Optional[str] = None
    overlay_zones: Optional[Any] = None
    overlay_shapes: Optional[Any] = None
    ndi_enabled: Optional[bool] = None
    ndi_source_name: Optional[str] = None
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
    projection_theme: Optional[str] = None
    projection_style: Optional[str] = None
    show_bible_version: Optional[bool] = None
    dual_translations: Optional[str] = None
    sunday_safe_mode: Optional[bool] = None
    shadow_mode: Optional[bool] = None


class PrepareModelRequest(BaseModel):
    model: Optional[str] = None


class SemanticSearchRequest(BaseModel):
    text: str
    top_k: int = 5


class OverlayImageRequest(BaseModel):
    """PNG de l'habillage, en data-URL ou base64 nu."""
    data: str


class BibleImportRequest(BaseModel):
    """Contenu JSON d'une traduction, et le sigle sous lequel l'installer."""
    content: str
    version_id: Optional[str] = ""


class OverlayPresetRequest(BaseModel):
    """Enregistrement d'un habillage dans la bibliothèque."""
    name: str
    category: Optional[str] = "Mes habillages"
    # Absents : on enregistre l'habillage tel qu'il est déjà en base.
    zones: Optional[Any] = None
    shapes: Optional[Any] = None


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


@router.get("/preflight")
async def preflight_check(probe_cloud: bool = False):
    """Contrôle opérationnel avant le direct, sans déclencher de téléchargement."""
    import asyncio
    import shutil
    from ..core.config import DATA_DIR, settings
    from ..main import (
        db_service,
        deepgram_service,
        output_manager,
        semantic_service,
        verse_parser,
        vosk_service,
        whisper_service,
    )
    from ..services.secret_store import secret_store

    disk = shutil.disk_usage(DATA_DIR)
    local_asr = bool(
        (whisper_service and whisper_service.ready)
        or (vosk_service and vosk_service.initialized)
    )
    cloud_configured = bool(settings.DEEPGRAM_API_KEY)
    cloud_verified = False
    cloud_error = ""
    if probe_cloud and cloud_configured and deepgram_service and deepgram_service.client:
        session = None
        async def ignore_probe_message(_):
            return None
        try:
            session = await asyncio.wait_for(
                deepgram_service.create_session(ignore_probe_message),
                timeout=5.0,
            )
            cloud_verified = bool(session.is_active)
        except Exception as exc:
            cloud_error = type(exc).__name__
        finally:
            if session:
                await session.close()

    browser = output_manager.outputs.get("browser") if output_manager else None
    browser_output = False
    browser_clients = 0
    if browser:
        try:
            browser_output = bool(await browser.send_scene(dict(browser.current_scene)))
            browser_clients = len(browser.connections)
        except Exception:
            browser_output = False

    configured_outputs = []
    if output_manager:
        for name, output in output_manager.outputs.items():
            if name == "browser" or not output.enabled:
                continue
            try:
                connected = bool(await output.is_connected())
            except Exception:
                connected = False
            configured_outputs.append((name, connected))

    cloud_ready = cloud_verified if probe_cloud else cloud_configured
    models_need_space = not local_asr or not bool(semantic_service and semantic_service.initialized)
    required_free = (4 if models_need_space else 1) * 1024 ** 3
    cloud_detail = (
        "Deepgram vérifié"
        if cloud_verified
        else f"Deepgram inaccessible ({cloud_error})"
        if probe_cloud and cloud_configured
        else "Deepgram configuré, test au démarrage du micro"
        if cloud_configured
        else ""
    )
    output_detail = (
        f"Moteur prêt · {browser_clients} écran(s) connecté(s)"
        if browser_output
        else "Le moteur d'affichage ne répond pas"
    )
    if configured_outputs:
        summary = ", ".join(f"{name}: {'prêt' if ok else 'indisponible'}" for name, ok in configured_outputs)
        output_detail = f"{output_detail} · {summary}"

    checks = [
        {"id": "database", "label": "Base locale", "ok": bool(db_service and db_service.db), "critical": True},
        {"id": "bible", "label": "Corpus biblique", "ok": bool(verse_parser and verse_parser.bible_loader.versions), "critical": True},
        {"id": "asr", "label": "Transcription", "ok": cloud_ready or local_asr, "critical": True,
         "detail": cloud_detail or ("Local prêt" if local_asr else "Préparer Whisper/Vosk ou ajouter une clé")},
        {"id": "output", "label": "Moteur de sortie", "ok": browser_output, "critical": True,
         "detail": output_detail},
        {"id": "configured_outputs", "label": "Sorties activées",
         "ok": all(ok for _, ok in configured_outputs), "critical": False,
         "detail": "Toutes prêtes" if all(ok for _, ok in configured_outputs) else "Une sortie optionnelle est indisponible"},
        {"id": "semantic", "label": "Recherche sémantique locale", "ok": bool(semantic_service and semantic_service.initialized), "critical": False},
        {"id": "disk", "label": "Espace disque", "ok": disk.free >= required_free, "critical": True,
         "detail": f"{disk.free / (1024 ** 3):.1f} Go libres · {required_free / (1024 ** 3):.0f} Go requis"},
        {"id": "secrets", "label": "Trousseau système", "ok": secret_store.available, "critical": False},
    ]
    return {
        "ready": all(item["ok"] for item in checks if item["critical"]),
        "checks": checks,
        "safety": {
            "sunday_safe_mode": settings.SUNDAY_SAFE_MODE,
            "shadow_mode": settings.SHADOW_MODE,
            "auto_send": settings.PROPRESENTER_AUTO_SEND,
        },
    }


@router.post("/safety/panic")
async def activate_panic_mode():
    """Coupe les automatismes et efface immédiatement toutes les sorties."""
    from ..core.config import settings
    from ..services.database import get_database
    from ..main import broadcast_projection
    settings.PROPRESENTER_AUTO_SEND = False
    settings.SUNDAY_SAFE_MODE = True
    settings.SHADOW_MODE = False
    db = get_database()
    await db.set_setting("auto_send", False)
    await db.set_setting("sunday_safe_mode", True)
    await db.set_setting("shadow_mode", False)
    receipts = await broadcast_projection("", "")
    return {
        "status": "safe",
        "auto_send": False,
        "sunday_safe_mode": True,
        "shadow_mode": False,
        "screen_cleared": bool(receipts.get("browser")),
        "outputs": receipts,
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

    if not parsed and not (request.text or "").strip():
        raise HTTPException(
            status_code=422,
            detail=f"Référence biblique invalide : {request.reference}",
        )

    reference = parsed or {
        "reference": request.reference.strip(),
        "text": request.text.strip(),
        "version": request.version,
    }
    projected_text = reference.get("text") or request.text or ""
    if not projected_text.strip():
        raise HTTPException(status_code=422, detail="Aucun texte à projeter")

    # OutputManager diffuse une seule fois vers chaque sortie et renvoie leurs
    # accusés. L'ancienne route envoyait ProPresenter une deuxième fois.
    receipts = await broadcast_projection(
        projected_text,
        reference.get("reference", request.reference),
        translations=reference.get("translations") if isinstance(reference, dict) else None,
    )
    browser_sent = bool(receipts.get("browser"))
    if not browser_sent:
        raise HTTPException(status_code=503, detail="Le moteur d'affichage n'a pas confirmé la scène")
    sent_propresenter = bool(receipts.get("propresenter"))

    return {
        "success": browser_sent,
        "reference": reference.get("reference", request.reference),
        "text": projected_text,
        "propresenter_sent": sent_propresenter,
        "outputs": receipts,
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


@router.get("/overlay/status")
async def get_overlay_status():
    """Habillage personnalisé : image installée et zones de texte."""
    from ..services import overlay_store
    from ..core.config import settings
    return {
        **overlay_store.status(),
        "zones": overlay_store.parse_zones(settings.OVERLAY_ZONES),
        "shapes": overlay_store.parse_shapes(settings.OVERLAY_SHAPES),
    }


@router.post("/overlay/image")
async def upload_overlay_image(request: OverlayImageRequest):
    """Reçoit le PNG en base64 : évite la dépendance python-multipart, que le
    backend figé n'embarque pas."""
    import asyncio
    from ..services import overlay_store
    try:
        raw = overlay_store.decode_upload(request.data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    try:
        return await asyncio.to_thread(overlay_store.save_image, raw)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Écriture impossible : {exc}")


@router.delete("/overlay/image")
async def remove_overlay_image():
    from ..services import overlay_store
    overlay_store.delete_image()
    return overlay_store.status()


@router.get("/bibles/imported")
async def list_imported_bibles():
    """Traductions ajoutées par l'église, distinctes de celles livrées."""
    from ..services import bible_import
    return {"versions": bible_import.lister(), "reserved": sorted(bible_import.SIGLES_RESERVES)}


@router.post("/bibles/import")
async def import_bible(request: BibleImportRequest):
    """Installe une traduction au format du corpus VersePro.

    Le fichier reste sur le poste de l'église : VersePro ne le rediffuse pas.
    La responsabilité des droits appartient à qui l'ajoute (voir CONDITIONS.md).
    """
    import asyncio
    from ..services import bible_import
    try:
        resume = await asyncio.to_thread(bible_import.importer, request.content, request.version_id or "")
    except bible_import.BibleInvalide as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {**resume, "restart_required": True}


@router.delete("/bibles/imported/{version_id}")
async def delete_imported_bible(version_id: str):
    from ..services import bible_import
    try:
        bible_import.supprimer(version_id)
    except bible_import.BibleInvalide as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"versions": bible_import.lister(), "restart_required": True}


@router.get("/overlay/library")
async def list_overlay_presets():
    """Habillages enregistrés, pour le menu des styles."""
    from ..services import overlay_store
    return {"presets": overlay_store.list_presets()}


@router.post("/overlay/library")
async def save_overlay_preset(request: OverlayPresetRequest):
    """Enregistre l'habillage courant sous un nom, dans sa catégorie."""
    from ..core.config import settings
    from ..services import overlay_store
    if not request.name.strip():
        raise HTTPException(status_code=400, detail="Un nom est requis.")
    try:
        return overlay_store.save_preset(
            request.name, request.category,
            request.zones if request.zones is not None else settings.OVERLAY_ZONES,
            request.shapes if request.shapes is not None else settings.OVERLAY_SHAPES,
            overlay_store.IMAGE_PATH if overlay_store.IMAGE_PATH.is_file() else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/overlay/library/{slug}/apply")
async def apply_overlay_preset(slug: str):
    """Recopie un habillage enregistré dans l'habillage en cours d'édition."""
    import shutil
    from ..core.config import settings
    from ..services import overlay_store
    from ..services.database import get_database
    preset = overlay_store.load_preset(slug)
    if not preset:
        raise HTTPException(status_code=404, detail="Habillage introuvable.")
    db = get_database()
    settings.OVERLAY_ZONES = overlay_store.dump_zones(preset["zones"])
    settings.OVERLAY_SHAPES = overlay_store.dump_shapes(preset["shapes"])
    await db.set_setting("overlay_zones", settings.OVERLAY_ZONES)
    await db.set_setting("overlay_shapes", settings.OVERLAY_SHAPES)
    if preset["image_path"]:
        overlay_store.OVERLAY_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(preset["image_path"], overlay_store.IMAGE_PATH)
    else:
        overlay_store.delete_image()
    return {"applied": preset["slug"], **overlay_store.status()}


@router.delete("/overlay/library/{slug}")
async def remove_overlay_preset(slug: str):
    from ..services import overlay_store
    overlay_store.delete_preset(slug)
    return {"presets": overlay_store.list_presets()}


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
    from ..main import vosk_service, whisper_service
    from ..core.config import settings

    return {
        "default_engine": settings.ASR_DEFAULT_ENGINE,
        "vosk": {
            "available": bool(vosk_service and vosk_service.initialized),
            "model": getattr(vosk_service, "model_name", ""),
        },
        "whisper": whisper_service.status() if whisper_service else {"installed": False, "ready": False},
    }


@router.post("/asr/prepare")
async def prepare_local_asr(request: PrepareModelRequest):
    """Prépare explicitement Whisper; aucun gros modèle n'est téléchargé au démarrage."""
    from ..main import whisper_service
    from ..core.config import settings
    if not whisper_service:
        raise HTTPException(status_code=503, detail="Service Whisper indisponible")
    if request.model and request.model not in {"auto", "tiny", "base", "small", "medium", "turbo"}:
        raise HTTPException(status_code=400, detail="Modèle Whisper invalide")
    if request.model and not whisper_service.ready:
        settings.WHISPER_MODEL = request.model
        whisper_service.model_name = whisper_service.select_model(request.model)
    if whisper_service.ready:
        return {"status": "ready", **whisper_service.status()}
    if not whisper_service.initializing:
        import threading
        threading.Thread(
            target=whisper_service.initialize,
            kwargs={"allow_download": True},
            daemon=True,
        ).start()
    return {"status": "preparing", **whisper_service.status()}


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
    from ..main import ai_service, output_manager, semantic_service, whisper_service
    from ..services.secret_store import secret_store
    from ..services import overlay_store

    propresenter_connected = False
    if output_manager and "propresenter" in output_manager.outputs:
        propresenter_connected = await output_manager.outputs["propresenter"].is_connected()
        
    return {
        "deepgram_model": settings.DEEPGRAM_MODEL,
        "deepgram_language": settings.DEEPGRAM_LANGUAGE,
        "propresenter_host": settings.PROPRESENTER_HOST,
        "propresenter_port": settings.PROPRESENTER_PORT,
        "propresenter_message_name": settings.PROPRESENTER_MESSAGE_NAME,
        "overlay_zones": overlay_store.parse_zones(settings.OVERLAY_ZONES),
        "overlay_shapes": overlay_store.parse_shapes(settings.OVERLAY_SHAPES),
        "ndi": (output_manager.outputs["ndi"].status()
                if output_manager and "ndi" in output_manager.outputs
                else {"available": False, "enabled": False, "sending": False,
                      "source_name": settings.NDI_SOURCE_NAME, "last_error": "sortie absente"}),
        "auto_send": settings.PROPRESENTER_AUTO_SEND,
        "sunday_safe_mode": settings.SUNDAY_SAFE_MODE,
        "shadow_mode": settings.SHADOW_MODE,
        "bible_version": settings.BIBLE_VERSION,
        "ai_agent_enabled": settings.AI_AGENT_ENABLED,
        "ai_available": bool(ai_service and ai_service.enabled),
        "ai_status": ai_service.status() if ai_service else {},
        "secret_storage_secure": secret_store.available,
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
        "whisper_status": whisper_service.status() if whisper_service else {},
        "local_semantic_enabled": settings.LOCAL_SEMANTIC_ENABLED,
        "local_semantic_threshold": semantic_service.active_threshold if semantic_service else settings.LOCAL_SEMANTIC_THRESHOLD,
        "local_semantic_model": settings.LOCAL_SEMANTIC_MODEL,
        "semantic_status": semantic_service.status() if semantic_service else {},
        "projection_theme": settings.PROJECTION_THEME,
        "projection_style": settings.PROJECTION_STYLE,
        "show_bible_version": settings.SHOW_BIBLE_VERSION,
        "dual_translations": settings.DUAL_TRANSLATIONS,
    }


@router.post("/settings")
async def update_settings(settings_update: SettingsUpdate):
    """Met à jour la configuration et la persiste dans SQLite"""
    from ..core.config import settings
    from ..main import output_manager, verse_parser, ai_service, deepgram_service, semantic_service
    from ..services.database import get_database
    from ..services.secret_store import secret_store
    
    db = get_database()
    update = settings_update.model_dump(exclude_unset=True)
    logger.info(f"Mise à jour settings: {_redact_update(update)}")

    reconnect_propresenter = False

    if "auto_send" in update:
        settings.PROPRESENTER_AUTO_SEND = bool(update["auto_send"])
        await db.set_setting("auto_send", settings.PROPRESENTER_AUTO_SEND)

    if "sunday_safe_mode" in update:
        settings.SUNDAY_SAFE_MODE = bool(update["sunday_safe_mode"])
        await db.set_setting("sunday_safe_mode", settings.SUNDAY_SAFE_MODE)

    if "shadow_mode" in update:
        settings.SHADOW_MODE = bool(update["shadow_mode"])
        await db.set_setting("shadow_mode", settings.SHADOW_MODE)
        
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
            
    if update.get("overlay_zones") is not None:
        from ..services import overlay_store
        # Nettoyage AVANT stockage : les zones finissent en styles inline sur
        # l'écran de projection, elles ne doivent jamais transporter n'importe quoi.
        settings.OVERLAY_ZONES = overlay_store.dump_zones(update["overlay_zones"])
        await db.set_setting("overlay_zones", settings.OVERLAY_ZONES)

    if update.get("ndi_source_name"):
        settings.NDI_SOURCE_NAME = update["ndi_source_name"].strip()[:60]
        await db.set_setting("ndi_source_name", settings.NDI_SOURCE_NAME)

    if update.get("ndi_enabled") is not None:
        settings.NDI_ENABLED = bool(update["ndi_enabled"])
        await db.set_setting("ndi_enabled", settings.NDI_ENABLED)
        if output_manager and "ndi" in output_manager.outputs:
            pilote = output_manager.outputs["ndi"]
            pilote.source_name = settings.NDI_SOURCE_NAME
            pilote.enabled = settings.NDI_ENABLED
            # Éteindre doit libérer la source tout de suite : un mélangeur qui
            # voit encore « VersePro » alors que la sortie est coupée ferait
            # perdre du temps à l'opérateur.
            if not settings.NDI_ENABLED:
                pilote.stop_sending()

    if update.get("overlay_shapes") is not None:
        from ..services import overlay_store
        settings.OVERLAY_SHAPES = overlay_store.dump_shapes(update["overlay_shapes"])
        await db.set_setting("overlay_shapes", settings.OVERLAY_SHAPES)

    if update.get("propresenter_message_name"):
        settings.PROPRESENTER_MESSAGE_NAME = update["propresenter_message_name"].strip()
        await db.set_setting("propresenter_message_name", settings.PROPRESENTER_MESSAGE_NAME)
        if output_manager and "propresenter" in output_manager.outputs:
            # Le message cible change : on oublie celui résolu, il sera recherché
            # à nouveau au prochain envoi.
            output_manager.outputs["propresenter"]._message_id = None
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
            ai_service.refresh_availability()
            
    if "deepgram_api_key" in update:
        settings.DEEPGRAM_API_KEY = str(update["deepgram_api_key"] or "").strip()
        await secret_store.set("deepgram_api_key", settings.DEEPGRAM_API_KEY)
        if deepgram_service:
            deepgram_service.api_key = settings.DEEPGRAM_API_KEY
            if settings.DEEPGRAM_API_KEY:
                deepgram_service._init_client()
                
    if "openrouter_api_key" in update:
        settings.OPENROUTER_API_KEY = str(update["openrouter_api_key"] or "").strip()
        await secret_store.set("openrouter_api_key", settings.OPENROUTER_API_KEY)
        if ai_service:
            ai_service.openrouter_key = settings.OPENROUTER_API_KEY
            ai_service.refresh_availability()
            
    if "gemini_api_key" in update:
        settings.GEMINI_API_KEY = str(update["gemini_api_key"] or "").strip()
        await secret_store.set("gemini_api_key", settings.GEMINI_API_KEY)
        if ai_service:
            ai_service.api_key = settings.GEMINI_API_KEY
            ai_service.refresh_availability()
            
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
        if engine not in {"auto", "deepgram", "whisper", "vosk", "local_auto"}:
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

    if "projection_theme" in update:
        theme = str(update["projection_theme"])
        settings.PROJECTION_THEME = theme
        await db.set_setting("projection_theme", theme)
        
    if "projection_style" in update:
        style = str(update["projection_style"])
        settings.PROJECTION_STYLE = style
        await db.set_setting("projection_style", style)
        
    if "show_bible_version" in update:
        show_ver = bool(update["show_bible_version"])
        settings.SHOW_BIBLE_VERSION = show_ver
        await db.set_setting("show_bible_version", settings.SHOW_BIBLE_VERSION)
        
    if "dual_translations" in update:
        dual_trans = str(update["dual_translations"])
        settings.DUAL_TRANSLATIONS = dual_trans
        await db.set_setting("dual_translations", dual_trans)

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
        # La raison précise vaut mieux qu'un « échec » muet : clé absente,
        # quota dépassé, délai expiré ne se corrigent pas de la même façon.
        raison = getattr(ai_service, "last_summary_error", "") or "cause inconnue"
        raise HTTPException(status_code=502, detail=f"Résumé impossible — {raison}")
        
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

@router.get("/update/check")
async def update_check():
    """État de mise à jour. Renvoie toujours 200, même hors ligne : ce contrôle
    est un confort, jamais une condition pour utiliser l'application."""
    from ..services.update_check import check_for_update
    return await check_for_update()


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
