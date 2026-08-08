"""Rendu pixel de l'habillage, pour les sorties qui ne savent pas lire du HTML.

L'écran de projection compose son bandeau en HTML/CSS ; NDI, lui, réclame des
trames d'image. Ce module dessine le MÊME modèle — image de fond, formes,
zones de texte — pour qu'une régie branchée en NDI reçoive exactement ce que
l'assemblée voit, et non un habillage parallèle qui divergerait au premier
changement de réglage.
"""

import os
import sys
import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from loguru import logger

from .shape_geometry import normalise_corners, polygon_points

# Polices réelles du système : Pillow ne sait pas lire les woff2 embarqués pour
# le navigateur. On vise les mêmes familles que la projection (« sans » = Arial)
# afin que les deux rendus se ressemblent vraiment.
_FONT_CANDIDATES: Dict[str, List[str]] = {
    "sans": [
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ],
    "serif": [
        "/System/Library/Fonts/Supplemental/Georgia.ttf",
        "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
        "C:/Windows/Fonts/georgia.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
    ],
    "mono": [
        "/System/Library/Fonts/Menlo.ttc",
        "C:/Windows/Fonts/consola.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    ],
}
_FONT_CANDIDATES["display"] = _FONT_CANDIDATES["sans"]

_BOLD_CANDIDATES: Dict[str, List[str]] = {
    "sans": [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ],
    "serif": [
        "/System/Library/Fonts/Supplemental/Georgia Bold.ttf",
        "C:/Windows/Fonts/georgiab.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    ],
    "mono": [
        "C:/Windows/Fonts/consolab.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
    ],
}
_BOLD_CANDIDATES["display"] = _BOLD_CANDIDATES["sans"]

_cache_polices: Dict[Tuple[str, int, bool], Any] = {}


def _police(famille: str, taille: int, gras: bool):
    cle = (famille, taille, gras)
    if cle in _cache_polices:
        return _cache_polices[cle]
    chemins = (_BOLD_CANDIDATES if gras else _FONT_CANDIDATES).get(famille, [])
    chemins = chemins + _FONT_CANDIDATES.get(famille, []) + _FONT_CANDIDATES["sans"]
    for chemin in chemins:
        if os.path.exists(chemin):
            try:
                _cache_polices[cle] = ImageFont.truetype(chemin, taille)
                return _cache_polices[cle]
            except Exception:
                continue
    logger.warning("Aucune police système trouvée pour NDI ; rendu en police par défaut.")
    _cache_polices[cle] = ImageFont.load_default(size=taille)
    return _cache_polices[cle]


def _rgba(couleur: str, opacite: float = 1.0) -> Tuple[int, int, int, int]:
    """« #rrggbb » ou « #rgb » vers un quadruplet, alpha compris."""
    couleurs = {
        "yellow": "#facc15",
        "red": "#ef4444",
        "blue": "#38bdf8",
        "sky": "#38bdf8",
        "white": "#ffffff",
    }
    couleur = couleurs.get(str(couleur or "").lower(), couleur)
    c = (couleur or "#ffffff").lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    if len(c) == 8:  # #rrggbbaa
        r, g, b, a = (int(c[i:i + 2], 16) for i in (0, 2, 4, 6))
        return r, g, b, int(a * max(0.0, min(1.0, opacite)))
    try:
        r, g, b = (int(c[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        r, g, b = 255, 255, 255
    return r, g, b, int(255 * max(0.0, min(1.0, opacite)))


def _decouper(dessin, texte: str, police, largeur: int, retrait: int) -> List[str]:
    """Découpe en lignes, la première amputée du retrait pris par l'exposant."""
    lignes: List[str] = []
    courante = ""
    dispo = max(1, largeur - retrait)
    for mot in (texte or "").split():
        essai = f"{courante} {mot}".strip()
        if dessin.textlength(essai, font=police) <= dispo or not courante:
            courante = essai
        else:
            lignes.append(courante)
            courante = mot
            dispo = largeur
    if courante:
        lignes.append(courante)
    return lignes


def rendre_habillage(
    largeur: int,
    hauteur: int,
    zones: Dict[str, Dict[str, Any]],
    formes: List[Dict[str, Any]],
    reference: str,
    texte: str,
    numero_verset: Optional[Any] = None,
    image_fond: Optional[str] = None,
    annotations: Optional[List[Dict[str, Any]]] = None,
) -> Image.Image:
    """Compose une image RGBA transparente : image, puis formes, puis textes."""
    cadre = Image.new("RGBA", (largeur, hauteur), (0, 0, 0, 0))

    if image_fond and os.path.isfile(image_fond):
        try:
            with Image.open(image_fond) as source:
                fond = source.convert("RGBA").resize((largeur, hauteur), Image.LANCZOS)
            cadre.alpha_composite(fond)
        except Exception as exc:
            logger.warning(f"Habillage NDI : image illisible ({exc})")

    for forme in formes or []:
        # Chaque forme sur son propre calque : alpha_composite mélange
        # correctement les translucides, là où un dessin direct les écraserait.
        calque = Image.new("RGBA", (largeur, hauteur), (0, 0, 0, 0))
        crayon = ImageDraw.Draw(calque)
        x0 = forme["x"] * largeur / 100
        y0 = forme["y"] * hauteur / 100
        L = forme["w"] * largeur / 100
        H = forme["h"] * hauteur / 100
        # Contour tracé point par point : les coins peuvent être creusés ou
        # biseautés, ce qu'un rectangle arrondi ne saurait rendre. La géométrie
        # est partagée avec l'écran, si bien que les deux rendus coïncident.
        coins = [
            {"r": c["r"] * hauteur / 100, "mode": c["mode"]}
            for c in normalise_corners(forme)
        ]
        points = [(x0 + px, y0 + py) for px, py in polygon_points(L, H, coins)]
        crayon.polygon(points, fill=_rgba(forme.get("fill"), forme.get("opacity", 1.0)))
        cadre.alpha_composite(calque)

    crayon = ImageDraw.Draw(cadre)
    # Coordonnées des mots réellement dessinés : les annotations opérateur
    # utilisent le même découpage que le texte NDI, y compris les passages
    # longs. Cela évite de tenter de deviner une position depuis la longueur
    # brute de la chaîne.
    boites_mots: List[Tuple[str, Tuple[float, float, float, float]]] = []
    for nom, contenu in (("reference", reference), ("text", texte)):
        zone = (zones or {}).get(nom)
        if not zone or not contenu:
            continue
        zx = zone["x"] * largeur / 100
        zy = zone["y"] * hauteur / 100
        zl = zone["w"] * largeur / 100
        zh = zone["h"] * hauteur / 100
        # Comme à l'écran, la taille se rapporte à la HAUTEUR du cadre.
        taille = max(8, int(zone["size"] * hauteur / 100))
        police = _police(zone.get("font", "sans"), taille, zone.get("weight", 400) >= 600)
        couleur = _rgba(zone.get("color"), 1.0)
        interligne = zone.get("line", 1.2) * taille

        retrait = 0
        police_num = None
        if nom == "text" and numero_verset not in (None, ""):
            police_num = _police(zone.get("font", "sans"), max(6, int(taille * 0.55)),
                                 zone.get("weight", 400) >= 600)
            retrait = int(crayon.textlength(str(numero_verset), font=police_num) + taille * 0.06)

        lignes = _decouper(crayon, str(contenu), police, int(zl), retrait)
        bloc = len(lignes) * interligne
        valign = zone.get("valign", "middle")
        y = zy if valign == "top" else (zy + zh - bloc if valign == "bottom" else zy + (zh - bloc) / 2)

        for index, ligne in enumerate(lignes):
            depart = retrait if index == 0 else 0
            largeur_ligne = crayon.textlength(ligne, font=police) + depart
            align = zone.get("align", "left")
            x = zx if align == "left" else (zx + zl - largeur_ligne if align == "right"
                                            else zx + (zl - largeur_ligne) / 2)
            if index == 0 and police_num is not None:
                # Exposant : calé sur le haut de la ligne, comme le « super » CSS.
                crayon.text((x, y - taille * 0.06), str(numero_verset), font=police_num, fill=couleur)
            crayon.text((x + depart, y), ligne, font=police, fill=couleur)
            if nom == "text":
                curseur = x + depart
                for mot in ligne.split():
                    largeur_mot = crayon.textlength(mot, font=police)
                    bbox = crayon.textbbox((curseur, y), mot, font=police)
                    boites_mots.append((_normaliser_mot(mot), bbox))
                    curseur += largeur_mot + crayon.textlength(" ", font=police)
            y += interligne

    # Les sorties navigateur/OBS et NDI reçoivent les mêmes annotations. Un
    # texte absent (par exemple une référence envoyée par une ancienne régie)
    # signifie « annoter le verset actuellement à l'antenne ».
    for annotation in annotations or []:
        if not isinstance(annotation, dict):
            continue
        cible = [mot for mot in _normaliser_mots(annotation.get("text", "")) if mot]
        debut = -1
        if cible:
            mots = [mot for mot, _ in boites_mots]
            for index in range(0, len(mots) - len(cible) + 1):
                if mots[index:index + len(cible)] == cible:
                    debut = index
                    break
        selection = boites_mots[debut:debut + len(cible)] if debut >= 0 else boites_mots
        if not selection:
            continue
        calque = Image.new("RGBA", cadre.size, (0, 0, 0, 0))
        annotation_draw = ImageDraw.Draw(calque)
        couleur = _rgba(annotation.get("color", "yellow"), 1.0)
        boxes = [box for _, box in selection]
        if annotation.get("type") == "highlight":
            for left, top, right, bottom in boxes:
                annotation_draw.rounded_rectangle(
                    (left - 2, top - 1, right + 2, bottom + 1),
                    radius=max(2, int((bottom - top) * 0.12)),
                    fill=(*couleur[:3], 105),
                )
        elif annotation.get("type") == "underline":
            for left, _top, right, bottom in boxes:
                annotation_draw.line(
                    (left, bottom + 2, right, bottom + 2),
                    fill=(*couleur[:3], 255),
                    width= max(2, int((bottom - _top) * 0.07)),
                )
        elif annotation.get("type") == "circle":
            # Une ellipse par ligne rend un groupe multi-ligne lisible sans
            # encercler tout le cadre NDI.
            lignes: List[List[Tuple[float, float, float, float]]] = []
            for box in boxes:
                if not lignes or abs(box[1] - lignes[-1][0][1]) > max(8, (box[3] - box[1]) * 0.6):
                    lignes.append([box])
                else:
                    lignes[-1].append(box)
            for ligne in lignes:
                left = min(box[0] for box in ligne) - 8
                top = min(box[1] for box in ligne) - 6
                right = max(box[2] for box in ligne) + 8
                bottom = max(box[3] for box in ligne) + 6
                annotation_draw.rounded_rectangle(
                    (left, top, right, bottom),
                    radius=max(8, int((bottom - top) * 0.45)),
                    outline=(*couleur[:3], 255),
                    width=max(2, int((bottom - top) * 0.08)),
                )
        cadre.alpha_composite(calque)

    return cadre


def _normaliser_mot(mot: Any) -> str:
    texte = unicodedata.normalize("NFD", str(mot or "").lower())
    texte = "".join(car for car in texte if unicodedata.category(car) != "Mn")
    return re.sub(r"[^\wÀ-ÿ]+", "", texte, flags=re.UNICODE)


def _normaliser_mots(texte: Any) -> List[str]:
    return [_normaliser_mot(mot) for mot in str(texte or "").split()]


def vers_bgra(image: Image.Image) -> np.ndarray:
    """Pillow produit du RGBA ; NDI attend les octets dans l'ordre BGRA.

    L'alpha est conservé tel quel : c'est lui qui permet au mélangeur
    d'incruster le bandeau sur la vidéo, sans chroma key.
    """
    arr = np.asarray(image, dtype=np.uint8)
    bgra = np.empty_like(arr)
    bgra[..., 0] = arr[..., 2]
    bgra[..., 1] = arr[..., 1]
    bgra[..., 2] = arr[..., 0]
    bgra[..., 3] = arr[..., 3]
    return np.ascontiguousarray(bgra)
