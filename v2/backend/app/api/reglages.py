"""Lecture et écriture des réglages."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
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
    asr_default_engine: Optional[str] = None
    local_semantic_enabled: Optional[bool] = None
    local_semantic_threshold: Optional[float] = None
    projection_theme: Optional[str] = None
    background_enabled: Optional[bool] = None
    background_asset: Optional[str] = None
    background_fit: Optional[str] = None
    background_position_x: Optional[float] = None
    background_position_y: Optional[float] = None
    background_overlay_color: Optional[str] = None
    background_overlay_opacity: Optional[float] = None
    background_blur: Optional[float] = None
    background_scale: Optional[float] = None
    background_crop_top: Optional[float] = None
    background_crop_bottom: Optional[float] = None
    background_crop_left: Optional[float] = None
    background_crop_right: Optional[float] = None
    projection_style: Optional[str] = None
    show_bible_version: Optional[bool] = None
    dual_translations: Optional[str] = None
    sunday_safe_mode: Optional[bool] = None
    shadow_mode: Optional[bool] = None


@router.get("/settings")
async def get_settings():
    """Récupère la configuration"""
    from ..core.config import settings
    from ..main import ai_service, output_manager, semantic_service, nemotron_service
    from ..services.secret_store import secret_store
    from ..services import overlay_store, background_store

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
        "asr_default_engine": settings.ASR_DEFAULT_ENGINE,
        "nemotron_status": nemotron_service.status() if nemotron_service else {},
        "local_semantic_enabled": settings.LOCAL_SEMANTIC_ENABLED,
        "local_semantic_threshold": semantic_service.active_threshold if semantic_service else settings.LOCAL_SEMANTIC_THRESHOLD,
        "local_semantic_model": settings.LOCAL_SEMANTIC_MODEL,
        "semantic_status": semantic_service.status() if semantic_service else {},
        "projection_theme": settings.PROJECTION_THEME,
        "background_enabled": settings.BACKGROUND_ENABLED,
        "background_asset": settings.BACKGROUND_ASSET,
        "background_fit": settings.BACKGROUND_FIT,
        "background_position_x": settings.BACKGROUND_POSITION_X,
        "background_position_y": settings.BACKGROUND_POSITION_Y,
        "background_overlay_color": settings.BACKGROUND_OVERLAY_COLOR,
        "background_overlay_opacity": settings.BACKGROUND_OVERLAY_OPACITY,
        "background_blur": settings.BACKGROUND_BLUR,
        "background_scale": settings.BACKGROUND_SCALE,
        "background_crop_top": settings.BACKGROUND_CROP_TOP,
        "background_crop_bottom": settings.BACKGROUND_CROP_BOTTOM,
        "background_crop_left": settings.BACKGROUND_CROP_LEFT,
        "background_crop_right": settings.BACKGROUND_CROP_RIGHT,
        "background": background_store.resolve_background(settings),
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

    # La diffusion automatique et le mode dimanche sûr sont incompatibles :
    # le premier envoie une détection sans validation, le second l'interdit.
    # La règle est appliquée après les deux champs pour qu'un formulaire qui
    # envoie simultanément auto_send=true et sunday_safe_mode=true reste sûr.
    if settings.PROPRESENTER_AUTO_SEND and settings.SUNDAY_SAFE_MODE:
        settings.SUNDAY_SAFE_MODE = False
        await db.set_setting("sunday_safe_mode", False)

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
        new_name = update["ndi_source_name"].strip()[:60]
        name_changed = new_name != settings.NDI_SOURCE_NAME
        settings.NDI_SOURCE_NAME = new_name
        await db.set_setting("ndi_source_name", settings.NDI_SOURCE_NAME)
        # Si le nom change alors que NDI émet déjà, il faut redémarrer
        # l'émetteur pour que le nouveau nom apparaisse sur le réseau.
        if name_changed and settings.NDI_ENABLED and output_manager and "ndi" in output_manager.outputs:
            pilote = output_manager.outputs["ndi"]
            pilote.stop_sending()
            pilote.source_name = settings.NDI_SOURCE_NAME
            await pilote.connect()

    if update.get("ndi_enabled") is not None:
        settings.NDI_ENABLED = bool(update["ndi_enabled"])
        await db.set_setting("ndi_enabled", settings.NDI_ENABLED)
        if output_manager and "ndi" in output_manager.outputs:
            pilote = output_manager.outputs["ndi"]
            pilote.source_name = settings.NDI_SOURCE_NAME
            pilote.enabled = settings.NDI_ENABLED
            if settings.NDI_ENABLED:
                # Créer immédiatement la source NDI sur le réseau pour que le
                # régisseur puisse la configurer dans OBS/vMix avant le culte.
                await pilote.connect()
            else:
                # Éteindre doit libérer la source tout de suite : un mélangeur
                # qui voit encore « VersePro » alors que la sortie est coupée
                # ferait perdre du temps à l'opérateur.
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


    if update.get("asr_default_engine"):
        engine = str(update["asr_default_engine"])
        if engine not in {"auto", "deepgram", "nemotron", "vosk", "local_auto"}:
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

    background_keys = {
        "background_enabled", "background_asset", "background_fit",
        "background_position_x", "background_position_y",
        "background_overlay_color", "background_overlay_opacity", "background_blur",
        "background_scale", "background_crop_top", "background_crop_bottom",
        "background_crop_left", "background_crop_right",
    }
    if background_keys.intersection(update):
        from ..services import background_store

        asset_id = str(update.get("background_asset", settings.BACKGROUND_ASSET) or "").strip().lower()
        if asset_id and not background_store.get_asset(asset_id):
            raise HTTPException(status_code=400, detail="Fond plein ecran introuvable")
        options = background_store.sanitise_options(
            fit=update.get("background_fit", settings.BACKGROUND_FIT),
            position_x=update.get("background_position_x", settings.BACKGROUND_POSITION_X),
            position_y=update.get("background_position_y", settings.BACKGROUND_POSITION_Y),
            overlay_color=update.get("background_overlay_color", settings.BACKGROUND_OVERLAY_COLOR),
            overlay_opacity=update.get("background_overlay_opacity", settings.BACKGROUND_OVERLAY_OPACITY),
            blur=update.get("background_blur", settings.BACKGROUND_BLUR),
            scale=update.get("background_scale", settings.BACKGROUND_SCALE),
            crop_top=update.get("background_crop_top", settings.BACKGROUND_CROP_TOP),
            crop_bottom=update.get("background_crop_bottom", settings.BACKGROUND_CROP_BOTTOM),
            crop_left=update.get("background_crop_left", settings.BACKGROUND_CROP_LEFT),
            crop_right=update.get("background_crop_right", settings.BACKGROUND_CROP_RIGHT),
        )
        settings.BACKGROUND_ASSET = asset_id
        settings.BACKGROUND_ENABLED = bool(
            update.get("background_enabled", settings.BACKGROUND_ENABLED) and asset_id
        )
        settings.BACKGROUND_FIT = options["fit"]
        settings.BACKGROUND_POSITION_X = options["position_x"]
        settings.BACKGROUND_POSITION_Y = options["position_y"]
        settings.BACKGROUND_OVERLAY_COLOR = options["overlay_color"]
        settings.BACKGROUND_OVERLAY_OPACITY = options["overlay_opacity"]
        settings.BACKGROUND_BLUR = options["blur"]
        settings.BACKGROUND_SCALE = options["scale"]
        settings.BACKGROUND_CROP_TOP = options["crop_top"]
        settings.BACKGROUND_CROP_BOTTOM = options["crop_bottom"]
        settings.BACKGROUND_CROP_LEFT = options["crop_left"]
        settings.BACKGROUND_CROP_RIGHT = options["crop_right"]
        for key, value in {
            "background_enabled": settings.BACKGROUND_ENABLED,
            "background_asset": settings.BACKGROUND_ASSET,
            "background_fit": settings.BACKGROUND_FIT,
            "background_position_x": settings.BACKGROUND_POSITION_X,
            "background_position_y": settings.BACKGROUND_POSITION_Y,
            "background_overlay_color": settings.BACKGROUND_OVERLAY_COLOR,
            "background_overlay_opacity": settings.BACKGROUND_OVERLAY_OPACITY,
            "background_blur": settings.BACKGROUND_BLUR,
            "background_scale": settings.BACKGROUND_SCALE,
            "background_crop_top": settings.BACKGROUND_CROP_TOP,
            "background_crop_bottom": settings.BACKGROUND_CROP_BOTTOM,
            "background_crop_left": settings.BACKGROUND_CROP_LEFT,
            "background_crop_right": settings.BACKGROUND_CROP_RIGHT,
        }.items():
            await db.set_setting(key, value)

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
