"""Rendu pixel de l'habillage, pour les sorties qui ne savent pas lire du HTML.

L'écran de projection compose son bandeau en HTML/CSS ; NDI, lui, réclame des
trames d'image. Ce module dessine le MÊME modèle — image de fond, formes,
zones de texte — pour qu'une régie branchée en NDI reçoive exactement ce que
l'assemblée voit, et non un habillage parallèle qui divergerait au premier
changement de réglage.
"""

import os
import sys
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from loguru import logger

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
        boite = [x0, y0, x0 + forme["w"] * largeur / 100, y0 + forme["h"] * hauteur / 100]
        rayon = max(0, int(forme.get("radius", 0) * hauteur / 100))
        crayon.rounded_rectangle(boite, radius=rayon,
                                 fill=_rgba(forme.get("fill"), forme.get("opacity", 1.0)))
        cadre.alpha_composite(calque)

    crayon = ImageDraw.Draw(cadre)
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
            y += interligne

    return cadre


def vers_bgrx(image: Image.Image) -> np.ndarray:
    """NDI attend du BGRX ; Pillow produit du RGBA."""
    arr = np.asarray(image, dtype=np.uint8)
    bgrx = np.empty_like(arr)
    bgrx[..., 0] = arr[..., 2]
    bgrx[..., 1] = arr[..., 1]
    bgrx[..., 2] = arr[..., 0]
    bgrx[..., 3] = arr[..., 3]
    return np.ascontiguousarray(bgrx)
