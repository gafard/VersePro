"""Habillage personnalisé de l'écran autonome : image de fond + zones de texte.

Principe, repris de vMix et de ProPresenter : l'église fournit SON graphique
(exporté de Canva, Photoshop, peu importe) et VersePro ne fait qu'y poser le
verset et sa référence. Le rendu n'est donc pas une imitation du design de
l'église — c'est son fichier, au pixel près.

Les zones sont exprimées en POURCENTAGES du cadre : un habillage réglé sur un
portable en 720p reste juste sur le vidéoprojecteur en 4K.
"""

import base64
import json
import os
import struct
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from loguru import logger

from ..core.config import DATA_DIR

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
# Un habillage plein cadre en 4K compressé tient très largement dessous ; la
# borne existe pour qu'un fichier aberrant ne remplisse pas le disque d'une
# régie ni la mémoire du moteur.
MAX_IMAGE_BYTES = 12 * 1024 * 1024

OVERLAY_DIR = Path(DATA_DIR) / "overlay"
IMAGE_PATH = OVERLAY_DIR / "habillage.png"

# Valeurs de départ relevées sur un bandeau d'église réel : panneau large en bas
# et étiquette de référence posée au-dessus, à droite. L'opérateur les déplace
# ensuite à la souris ; elles ne servent qu'à ne pas partir d'une page blanche.
DEFAULT_ZONES: Dict[str, Dict[str, Any]] = {
    "text": {
        "x": 6.5, "y": 81.0, "w": 87.0, "h": 13.5,
        "size": 5.0, "color": "#1d2b63", "align": "left", "valign": "middle",
        "weight": 700, "font": "sans", "line": 1.16,
    },
    "reference": {
        "x": 63.5, "y": 74.5, "w": 32.0, "h": 5.4,
        "size": 2.8, "color": "#ffffff", "align": "center", "valign": "middle",
        "weight": 700, "font": "sans", "line": 1.2,
    },
}

_ALIGNS = ("left", "center", "right")
_VALIGNS = ("top", "middle", "bottom")
_FONTS = ("sans", "display", "serif", "mono")

# Formes construites DANS VersePro, pour l'église qui n'a pas de graphiste.
# Rendues en éléments vectoriels et non en image : nettes du 720p au 4K, et
# modifiables sans repasser par un logiciel de dessin.
# Valeurs de départ : le bandeau classique — panneau clair et étiquette posée
# dessus à droite — que l'opérateur recolorie ensuite à ses couleurs.
DEFAULT_SHAPES = [
    {"x": 5.5, "y": 80.1, "w": 90.1, "h": 15.1, "fill": "#ffffff", "opacity": 0.96, "radius": 3.2},
    {"x": 63.5, "y": 74.5, "w": 32.3, "h": 5.4, "fill": "#489e8c", "opacity": 1.0, "radius": 1.2},
]
# Un habillage raisonnable en compte deux ou trois ; la borne empêche qu'une
# charge fabriquée fasse rendre des milliers d'éléments à l'écran de projection.
MAX_SHAPES = 12


def png_dimensions(raw: bytes) -> tuple[int, int]:
    """Largeur/hauteur lues dans l'en-tête IHDR, sans dépendance d'image."""
    if len(raw) < 24 or not raw.startswith(_PNG_MAGIC):
        raise ValueError("Ce fichier n'est pas un PNG.")
    if raw[12:16] != b"IHDR":
        raise ValueError("PNG invalide : en-tête IHDR absent.")
    width, height = struct.unpack(">II", raw[16:24])
    if not width or not height:
        raise ValueError("PNG invalide : dimensions nulles.")
    return width, height


def decode_upload(payload: str) -> bytes:
    """Accepte une data-URL (« data:image/png;base64,… ») ou du base64 nu."""
    data = (payload or "").strip()
    if data.startswith("data:"):
        _, _, data = data.partition(",")
    try:
        raw = base64.b64decode(data, validate=True)
    except Exception as exc:
        raise ValueError(f"Contenu illisible : {exc}") from exc
    if len(raw) > MAX_IMAGE_BYTES:
        raise ValueError(
            f"Image trop lourde ({len(raw) / (1024 * 1024):.1f} Mo) ; "
            f"maximum {MAX_IMAGE_BYTES // (1024 * 1024)} Mo."
        )
    png_dimensions(raw)  # valide la signature avant d'écrire quoi que ce soit
    return raw


def save_image(raw: bytes) -> Dict[str, Any]:
    """Écrit l'habillage de façon atomique : jamais de PNG à moitié écrit."""
    OVERLAY_DIR.mkdir(parents=True, exist_ok=True)
    width, height = png_dimensions(raw)
    handle, temporaire = tempfile.mkstemp(dir=str(OVERLAY_DIR), suffix=".part")
    try:
        with os.fdopen(handle, "wb") as fichier:
            fichier.write(raw)
        os.replace(temporaire, IMAGE_PATH)
    except Exception:
        Path(temporaire).unlink(missing_ok=True)
        raise
    logger.info(f"🖼️ Habillage enregistré : {width}×{height}, {len(raw) / 1024:.0f} Ko")
    return status()


def delete_image() -> None:
    IMAGE_PATH.unlink(missing_ok=True)
    logger.info("🖼️ Habillage supprimé ; l'écran revient au style choisi.")


def status() -> Dict[str, Any]:
    if not IMAGE_PATH.is_file():
        return {"installed": False, "width": 0, "height": 0, "updated_at": 0, "bytes": 0}
    raw = IMAGE_PATH.read_bytes()
    try:
        width, height = png_dimensions(raw)
    except ValueError:
        width = height = 0
    return {
        "installed": True,
        "width": width,
        "height": height,
        # Horodatage utilisé comme numéro de version dans l'URL : sans lui,
        # l'écran garderait l'ancienne image en cache après un remplacement.
        "updated_at": int(IMAGE_PATH.stat().st_mtime),
        "bytes": len(raw),
    }


def _clamp(value: Any, bas: float, haut: float, defaut: float) -> float:
    try:
        return max(bas, min(haut, float(value)))
    except (TypeError, ValueError):
        return defaut


def _sanitize_zone(brut: Any, defaut: Dict[str, Any]) -> Dict[str, Any]:
    """Une zone venue du réseau ne doit jamais produire de CSS arbitraire."""
    if not isinstance(brut, dict):
        return dict(defaut)
    couleur = str(brut.get("color", defaut["color"])).strip()
    if not (len(couleur) in (4, 7, 9) and couleur.startswith("#")
            and all(c in "0123456789abcdefABCDEF" for c in couleur[1:])):
        couleur = defaut["color"]
    police = brut.get("font", defaut["font"])
    return {
        "x": _clamp(brut.get("x"), -20, 120, defaut["x"]),
        "y": _clamp(brut.get("y"), -20, 120, defaut["y"]),
        "w": _clamp(brut.get("w"), 1, 140, defaut["w"]),
        "h": _clamp(brut.get("h"), 1, 140, defaut["h"]),
        "size": _clamp(brut.get("size"), 0.5, 30, defaut["size"]),
        "line": _clamp(brut.get("line"), 0.8, 3, defaut["line"]),
        "color": couleur,
        "align": brut.get("align") if brut.get("align") in _ALIGNS else defaut["align"],
        "valign": brut.get("valign") if brut.get("valign") in _VALIGNS else defaut["valign"],
        "weight": int(_clamp(brut.get("weight"), 100, 900, defaut["weight"])),
        "font": police if police in _FONTS else defaut["font"],
    }


def parse_zones(brut: Optional[str]) -> Dict[str, Dict[str, Any]]:
    """Relit les zones enregistrées ; retombe sur les valeurs de départ."""
    donnees: Any = {}
    if brut:
        try:
            donnees = json.loads(brut)
        except (TypeError, ValueError):
            logger.warning("Zones d'habillage illisibles ; valeurs par défaut appliquées.")
            donnees = {}
    if not isinstance(donnees, dict):
        donnees = {}
    return {
        nom: _sanitize_zone(donnees.get(nom), defaut)
        for nom, defaut in DEFAULT_ZONES.items()
    }


def _hex_valide(valeur: Any, defaut: str) -> str:
    couleur = str(valeur or "").strip()
    if (len(couleur) in (4, 7, 9) and couleur.startswith("#")
            and all(c in "0123456789abcdefABCDEF" for c in couleur[1:])):
        return couleur
    return defaut


def _sanitize_shape(brut: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(brut, dict):
        return None
    return {
        "x": _clamp(brut.get("x"), -20, 120, 0.0),
        "y": _clamp(brut.get("y"), -20, 120, 0.0),
        "w": _clamp(brut.get("w"), 0.5, 140, 20.0),
        "h": _clamp(brut.get("h"), 0.5, 140, 10.0),
        "radius": _clamp(brut.get("radius"), 0, 50, 0.0),
        "opacity": _clamp(brut.get("opacity"), 0, 1, 1.0),
        "fill": _hex_valide(brut.get("fill"), "#ffffff"),
    }


def parse_shapes(brut: Optional[str]) -> list:
    """Relit les formes enregistrées. Une liste vide est un choix valide :
    elle signifie « pas de formes », pas « remets celles du départ »."""
    if brut is None or brut == "":
        return [dict(f) for f in DEFAULT_SHAPES]
    try:
        donnees = json.loads(brut)
    except (TypeError, ValueError):
        logger.warning("Formes d'habillage illisibles ; valeurs par défaut appliquées.")
        return [dict(f) for f in DEFAULT_SHAPES]
    if not isinstance(donnees, list):
        return [dict(f) for f in DEFAULT_SHAPES]
    formes = [f for f in (_sanitize_shape(b) for b in donnees[:MAX_SHAPES]) if f]
    return formes


def dump_shapes(formes: Any) -> str:
    if isinstance(formes, str):
        return json.dumps(parse_shapes(formes))
    return json.dumps(parse_shapes(json.dumps(formes)))


def dump_zones(zones: Any) -> str:
    """Sérialise après nettoyage : ce qui est stocké est déjà sûr."""
    return json.dumps(parse_zones(json.dumps(zones) if not isinstance(zones, str) else zones))
