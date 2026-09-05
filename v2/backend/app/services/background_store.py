"""Bibliotheque locale de fonds plein ecran.

Les images sont validees puis normalisees par Pillow avant d'etre exposees aux
ecrans. Le navigateur ne recoit jamais un chemin fourni par l'utilisateur et
les sorties restent utilisables hors ligne.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional

from PIL import Image, ImageOps, UnidentifiedImageError
from loguru import logger

from ..core.config import DATA_DIR


BACKGROUND_DIR = Path(DATA_DIR) / "backgrounds"
MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
MAX_ASSETS = 80
_ASSET_ID_RE = re.compile(r"^[a-f0-9]{16}$")
_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


class BackgroundInvalide(ValueError):
    pass


def _clamp(value: Any, low: float, high: float, default: float) -> float:
    try:
        return max(low, min(high, float(value)))
    except (TypeError, ValueError):
        return default


def _safe_asset_id(asset_id: str) -> str:
    candidate = str(asset_id or "").strip().lower()
    if not _ASSET_ID_RE.fullmatch(candidate):
        raise BackgroundInvalide("Identifiant de fond invalide.")
    return candidate


def _asset_dir(asset_id: str) -> Path:
    return BACKGROUND_DIR / _safe_asset_id(asset_id)


def decode_upload(payload: str) -> bytes:
    """Decode une data-URL ou du base64 nu, avec une limite avant Pillow."""
    data = str(payload or "").strip()
    if data.startswith("data:"):
        header, separator, data = data.partition(",")
        if not separator or not header.lower().startswith("data:image/"):
            raise BackgroundInvalide("Le fichier doit etre une image.")
    try:
        raw = base64.b64decode(data, validate=True)
    except Exception as exc:
        raise BackgroundInvalide("Image illisible ou encodage invalide.") from exc
    if not raw:
        raise BackgroundInvalide("Image vide.")
    if len(raw) > MAX_IMAGE_BYTES:
        raise BackgroundInvalide(
            f"Image trop lourde ({len(raw) / (1024 * 1024):.1f} Mo) ; "
            f"maximum {MAX_IMAGE_BYTES // (1024 * 1024)} Mo."
        )
    return raw


def _load_image(raw: bytes) -> Image.Image:
    try:
        source = Image.open(io.BytesIO(raw))
        if getattr(source, "n_frames", 1) != 1:
            raise BackgroundInvalide("Les images animees ne sont pas acceptees.")
        width, height = source.size
        if width < 64 or height < 64:
            raise BackgroundInvalide("Image trop petite (minimum 64 x 64 px).")
        if width * height > MAX_IMAGE_PIXELS:
            raise BackgroundInvalide("Image trop grande (maximum 40 megapixels).")
        source.load()
        return ImageOps.exif_transpose(source)
    except BackgroundInvalide:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise BackgroundInvalide("Format non reconnu. Utilisez PNG, JPEG ou WebP.") from exc


def _write_atomic(path: Path, writer) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=str(path.parent), suffix=".part")
    os.close(handle)
    temp_path = Path(temporary)
    try:
        writer(temp_path)
        os.replace(temp_path, path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def _normalise_name(name: str) -> str:
    cleaned = " ".join(str(name or "Fond sans titre").strip().split())
    return cleaned[:100] or "Fond sans titre"


def _save_image_file(image: Image.Image, path: Path, *, thumbnail: bool = False) -> None:
    prepared = image.copy()
    if thumbnail:
        prepared.thumbnail((640, 360), Image.Resampling.LANCZOS)
    has_alpha = "A" in prepared.getbands() or "transparency" in prepared.info
    if has_alpha:
        prepared.convert("RGBA").save(path, format="PNG", optimize=True)
    else:
        prepared.convert("RGB").save(path, format="JPEG", quality=90, optimize=True)


def _read_meta(asset_id: str) -> Optional[Dict[str, Any]]:
    try:
        folder = _asset_dir(asset_id)
    except BackgroundInvalide:
        return None
    metadata_path = folder / "metadata.json"
    if not metadata_path.is_file():
        return None
    try:
        data = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    image_name = data.get("image_file")
    thumb_name = data.get("thumbnail_file")
    if image_name not in {"image.jpg", "image.png"} or thumb_name not in {"thumb.jpg", "thumb.png"}:
        return None
    image_path = folder / image_name
    thumb_path = folder / thumb_name
    if not image_path.is_file() or not thumb_path.is_file():
        return None
    return {
        "id": asset_id,
        "name": _normalise_name(data.get("name", "")),
        "width": int(data.get("width") or 0),
        "height": int(data.get("height") or 0),
        "bytes": int(image_path.stat().st_size),
        "updated_at": int(data.get("updated_at") or metadata_path.stat().st_mtime),
        "media_type": "image/png" if image_name.endswith(".png") else "image/jpeg",
        "image_file": image_name,
        "thumbnail_file": thumb_name,
        "image_path": image_path,
        "thumbnail_path": thumb_path,
        "image_url": f"/assets/backgrounds/{asset_id}/image",
        "thumbnail_url": f"/assets/backgrounds/{asset_id}/thumbnail",
    }


def public_asset(asset: Dict[str, Any]) -> Dict[str, Any]:
    return {
        key: asset[key]
        for key in (
            "id", "name", "width", "height", "bytes", "updated_at",
            "media_type", "image_url", "thumbnail_url",
        )
    }


def list_assets() -> list[Dict[str, Any]]:
    if not BACKGROUND_DIR.is_dir():
        return []
    assets = []
    for folder in BACKGROUND_DIR.iterdir():
        if not folder.is_dir() or not _ASSET_ID_RE.fullmatch(folder.name):
            continue
        asset = _read_meta(folder.name)
        if asset:
            assets.append(public_asset(asset))
    return sorted(assets, key=lambda item: item["updated_at"], reverse=True)


def get_asset(asset_id: str) -> Optional[Dict[str, Any]]:
    """Renvoie les metadonnees publiques d'un fond valide."""
    asset = _read_meta(asset_id)
    return public_asset(asset) if asset else None


def save_asset(raw: bytes, name: str = "") -> Dict[str, Any]:
    image = _load_image(raw)
    asset_id = hashlib.sha256(raw).hexdigest()[:16]
    folder = _asset_dir(asset_id)
    exists = _read_meta(asset_id)
    if not exists and len(list_assets()) >= MAX_ASSETS:
        raise BackgroundInvalide(f"Bibliotheque pleine ({MAX_ASSETS} fonds maximum).")

    has_alpha = "A" in image.getbands() or "transparency" in image.info
    image_name = "image.png" if has_alpha else "image.jpg"
    thumb_name = "thumb.png" if has_alpha else "thumb.jpg"
    folder.mkdir(parents=True, exist_ok=True)
    _write_atomic(folder / image_name, lambda path: _save_image_file(image, path))
    _write_atomic(folder / thumb_name, lambda path: _save_image_file(image, path, thumbnail=True))

    now = int(time.time())
    metadata = {
        "name": _normalise_name(name),
        "width": image.width,
        "height": image.height,
        "updated_at": now,
        "image_file": image_name,
        "thumbnail_file": thumb_name,
    }
    _write_atomic(
        folder / "metadata.json",
        lambda path: path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
        ),
    )
    asset = _read_meta(asset_id)
    if not asset:
        raise OSError("Le fond a ete ecrit mais ne peut pas etre relu.")
    logger.info(f"Fond plein ecran enregistre : {asset['name']} ({image.width}x{image.height})")
    return public_asset(asset)


def delete_asset(asset_id: str) -> None:
    import shutil

    folder = _asset_dir(asset_id)
    if folder.is_dir():
        shutil.rmtree(folder)


def asset_file(asset_id: str, variant: str = "image") -> Optional[tuple[Path, str]]:
    asset = _read_meta(asset_id)
    if not asset:
        return None
    if variant == "thumbnail":
        path = asset["thumbnail_path"]
    elif variant == "image":
        path = asset["image_path"]
    else:
        return None
    return path, asset["media_type"]


def sanitise_options(
    *, fit: Any = "cover", position_x: Any = 50, position_y: Any = 50,
    overlay_color: Any = "#000000", overlay_opacity: Any = 0.42,
    blur: Any = 0,
) -> Dict[str, Any]:
    fit_value = str(fit or "cover").lower()
    if fit_value not in {"cover", "contain", "fill"}:
        fit_value = "cover"
    color = str(overlay_color or "#000000").strip()
    if not _HEX_COLOR_RE.fullmatch(color):
        color = "#000000"
    return {
        "fit": fit_value,
        "position_x": _clamp(position_x, 0, 100, 50),
        "position_y": _clamp(position_y, 0, 100, 50),
        "overlay_color": color.lower(),
        "overlay_opacity": _clamp(overlay_opacity, 0, 0.9, 0.42),
        "blur": _clamp(blur, 0, 20, 0),
    }


def resolve_background(settings: Any, *, include_path: bool = False) -> Dict[str, Any]:
    asset_id = str(getattr(settings, "BACKGROUND_ASSET", "") or "").strip().lower()
    asset = _read_meta(asset_id) if asset_id else None
    options = sanitise_options(
        fit=getattr(settings, "BACKGROUND_FIT", "cover"),
        position_x=getattr(settings, "BACKGROUND_POSITION_X", 50),
        position_y=getattr(settings, "BACKGROUND_POSITION_Y", 50),
        overlay_color=getattr(settings, "BACKGROUND_OVERLAY_COLOR", "#000000"),
        overlay_opacity=getattr(settings, "BACKGROUND_OVERLAY_OPACITY", 0.42),
        blur=getattr(settings, "BACKGROUND_BLUR", 0),
    )
    enabled = bool(getattr(settings, "BACKGROUND_ENABLED", False) and asset)
    resolved = {
        "enabled": enabled,
        "asset_id": asset_id if asset else "",
        "image_url": (
            f"{asset['image_url']}?v={asset['updated_at']}" if enabled and asset else ""
        ),
        "width": asset["width"] if asset else 0,
        "height": asset["height"] if asset else 0,
        **options,
    }
    # Le chemin local n'entre jamais dans une scene WebSocket publique : Path
    # n'est pas serialisable par send_json et expose inutilement le poste. NDI
    # le demande explicitement pour composer sa trame dans le backend.
    if include_path:
        resolved["image_path"] = asset["image_path"] if enabled and asset else None
    return resolved
