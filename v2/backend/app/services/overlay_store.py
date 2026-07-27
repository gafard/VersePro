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
import shutil
import struct
import tempfile
import unicodedata
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


# ── Bibliothèque d'habillages ────────────────────────────────────────────────
# Jusqu'ici VersePro n'avait qu'UN habillage, écrasé à chaque modification :
# essayer une variante détruisait la précédente. La bibliothèque enregistre des
# habillages nommés et rangés par catégorie, que le menu des styles propose à
# côté des styles livrés.

LIBRARY_DIR = OVERLAY_DIR / "bibliotheque"
MAX_PRESETS = 60
PREFIXE_STYLE = "habillage:"


def slugify(nom: str) -> str:
    """Nom de dossier sûr : jamais de séparateur, jamais de remontée de chemin."""
    base = unicodedata.normalize("NFKD", str(nom or "")).encode("ascii", "ignore").decode()
    slug = "".join(c if c.isalnum() else "-" for c in base.lower()).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug[:48] or "habillage"


def _dossier_preset(slug: str) -> Path:
    """Résout le dossier d'un habillage en refusant toute évasion de chemin."""
    cible = (LIBRARY_DIR / slugify(slug)).resolve()
    if not str(cible).startswith(str(LIBRARY_DIR.resolve())):
        raise ValueError("Identifiant d'habillage invalide.")
    return cible


def list_presets() -> list:
    if not LIBRARY_DIR.is_dir():
        return []
    presets = []
    for dossier in sorted(LIBRARY_DIR.iterdir()):
        fiche = dossier / "habillage.json"
        if not fiche.is_file():
            continue
        try:
            donnees = json.loads(fiche.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            logger.warning(f"Habillage illisible ignoré : {dossier.name}")
            continue
        image = dossier / "image.png"
        presets.append({
            "slug": dossier.name,
            "name": str(donnees.get("name") or dossier.name),
            "category": str(donnees.get("category") or "Mes habillages"),
            "has_image": image.is_file(),
            "updated_at": int(fiche.stat().st_mtime),
        })
    return presets


def load_preset(slug: str) -> Optional[Dict[str, Any]]:
    dossier = _dossier_preset(slug)
    fiche = dossier / "habillage.json"
    if not fiche.is_file():
        return None
    try:
        donnees = json.loads(fiche.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None
    image = dossier / "image.png"
    return {
        "slug": dossier.name,
        "name": str(donnees.get("name") or dossier.name),
        "category": str(donnees.get("category") or "Mes habillages"),
        "zones": parse_zones(json.dumps(donnees.get("zones"))),
        "shapes": parse_shapes(json.dumps(donnees.get("shapes"))),
        "image_path": image if image.is_file() else None,
        "updated_at": int(fiche.stat().st_mtime),
    }


def save_preset(nom: str, categorie: str, zones: Any, formes: Any,
                image_source: Optional[Path] = None) -> Dict[str, Any]:
    """Enregistre l'habillage courant sous un nom. Réenregistrer écrase le même."""
    slug = slugify(nom)
    existants = {p["slug"] for p in list_presets()}
    if slug not in existants and len(existants) >= MAX_PRESETS:
        raise ValueError(f"Bibliothèque pleine ({MAX_PRESETS} habillages).")
    dossier = _dossier_preset(slug)
    dossier.mkdir(parents=True, exist_ok=True)
    fiche = {
        "name": str(nom or slug).strip()[:80],
        "category": str(categorie or "Mes habillages").strip()[:40],
        "zones": json.loads(dump_zones(zones)),
        "shapes": json.loads(dump_shapes(formes)),
    }
    (dossier / "habillage.json").write_text(
        json.dumps(fiche, ensure_ascii=False, indent=2), encoding="utf-8")
    if image_source and Path(image_source).is_file():
        shutil.copyfile(image_source, dossier / "image.png")
    logger.info(f"🖼️ Habillage « {fiche['name']} » enregistré ({fiche['category']}).")
    return {"slug": slug, **fiche}


def delete_preset(slug: str) -> None:
    dossier = _dossier_preset(slug)
    if dossier.is_dir():
        shutil.rmtree(dossier)
        logger.info(f"🖼️ Habillage « {dossier.name} » supprimé.")


def style_slug(style: Optional[str]) -> Optional[str]:
    """Extrait le slug d'un style de la forme « habillage:mon-bandeau »."""
    if isinstance(style, str) and style.startswith(PREFIXE_STYLE):
        return style[len(PREFIXE_STYLE):]
    return None


def resolve_overlay_info(style: Optional[str], zones_actives: Optional[str],
                        formes_actives: Optional[str]) -> Dict[str, Any]:
    """Habillage à envoyer aux écrans : celui d'un préréglage de la bibliothèque
    si l'opérateur a sélectionné 'habillage:slug' dans le menu des styles.

    Si le style sélectionné est un style natif (agoe-logope, glass, neon-glow, etc.),
    aucun habillage n'est forcé et le style natif s'affiche.
    """
    slug = style_slug(style)
    if slug:
        preset = load_preset(slug)
        if preset:
            return {
                "installed": preset["image_path"] is not None,
                "width": 0, "height": 0,
                "updated_at": preset["updated_at"],
                "image_url": (f"/overlay/bibliotheque/{preset['slug']}/image.png"
                              f"?v={preset['updated_at']}") if preset["image_path"] else "",
                "image_path": preset["image_path"],
                "zones": preset["zones"],
                "shapes": preset["shapes"],
                "preset": preset["slug"],
            }
        logger.warning(f"Habillage « {slug} » introuvable.")
    return {
        "installed": False,
        "width": 0, "height": 0,
        "updated_at": 0,
        "image_url": "",
        "image_path": None,
        "zones": parse_zones(zones_actives),
        "shapes": parse_shapes(formes_actives),
        "preset": None,
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


_CORNER_MODES = ("out", "in", "cut")


def _sanitize_corners(brut: Any, rayon_global: float) -> list:
    """Quatre coins, dans le sens horaire depuis le haut-gauche.

    Un habillage enregistré avant les coins indépendants ne porte qu'un rayon
    global : il doit continuer de s'afficher exactement pareil, d'où le repli.
    """
    if not isinstance(brut, list) or not brut:
        return [{"r": rayon_global, "mode": "out"} for _ in range(4)]
    coins = []
    for index in range(4):
        c = brut[index] if index < len(brut) and isinstance(brut[index], dict) else {}
        mode = c.get("mode")
        coins.append({
            "r": _clamp(c.get("r"), 0, 50, rayon_global),
            "mode": mode if mode in _CORNER_MODES else "out",
        })
    return coins


def _sanitize_shape(brut: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(brut, dict):
        return None
    rayon = _clamp(brut.get("radius"), 0, 50, 0.0)
    return {
        "x": _clamp(brut.get("x"), -20, 120, 0.0),
        "y": _clamp(brut.get("y"), -20, 120, 0.0),
        "w": _clamp(brut.get("w"), 0.5, 140, 20.0),
        "h": _clamp(brut.get("h"), 0.5, 140, 10.0),
        # Conservé pour les habillages antérieurs et comme valeur de repli.
        "radius": rayon,
        "corners": _sanitize_corners(brut.get("corners"), rayon),
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
