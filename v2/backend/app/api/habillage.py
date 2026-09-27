"""Habillages (overlay) et fonds plein écran."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Any
import asyncio

router = APIRouter()


class OverlayImageRequest(BaseModel):
    """PNG de l'habillage, en data-URL ou base64 nu."""
    data: str


class BackgroundImageRequest(BaseModel):
    """Image de fond en data-URL ou base64 nu."""
    data: str = Field(..., max_length=28_000_000)
    name: str = Field("Fond sans titre", max_length=100)


class OverlayPresetRequest(BaseModel):
    """Enregistrement d'un habillage dans la bibliothèque."""
    name: str = Field(..., max_length=100)
    category: Optional[str] = Field("Mes habillages", max_length=100)
    # Absents : on enregistre l'habillage tel qu'il est déjà en base.
    zones: Optional[Any] = None
    shapes: Optional[Any] = None


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


@router.get("/backgrounds")
async def list_backgrounds():
    """Liste la bibliotheque locale de fonds plein ecran."""
    from ..services import background_store
    return {"assets": await asyncio.to_thread(background_store.list_assets)}


@router.post("/backgrounds")
async def upload_background(request: BackgroundImageRequest):
    """Valide, normalise et copie un fond dans le stockage VersePro."""
    from ..services import background_store
    try:
        raw = background_store.decode_upload(request.data)
        asset = await asyncio.to_thread(background_store.save_asset, raw, request.name)
    except background_store.BackgroundInvalide as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Ecriture impossible : {exc}")
    return asset


@router.delete("/backgrounds/{asset_id}")
async def remove_background(asset_id: str):
    """Supprime un fond et desactive proprement celui qui etait utilise."""
    from ..core.config import settings
    from ..services import background_store
    from ..services.database import get_database

    try:
        await asyncio.to_thread(background_store.delete_asset, asset_id)
    except background_store.BackgroundInvalide as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if settings.BACKGROUND_ASSET == asset_id:
        settings.BACKGROUND_ENABLED = False
        settings.BACKGROUND_ASSET = ""
        db = get_database()
        await db.set_setting("background_enabled", False)
        await db.set_setting("background_asset", "")
    return {"assets": await asyncio.to_thread(background_store.list_assets)}


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
    # Un preset chargé est un style à part entière, comme « bandeau » ou
    # « filet ». Avant cette affectation, il était copié dans l'atelier mais
    # la sortie restait sur l'ancien style : l'habillage semblait enregistré
    # puis ne réapparaissait jamais dans le rendu.
    settings.PROJECTION_THEME = "broadcast"
    settings.PROJECTION_STYLE = f"habillage:{preset['slug']}"
    await db.set_setting("overlay_zones", settings.OVERLAY_ZONES)
    await db.set_setting("overlay_shapes", settings.OVERLAY_SHAPES)
    await db.set_setting("projection_theme", settings.PROJECTION_THEME)
    await db.set_setting("projection_style", settings.PROJECTION_STYLE)
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
