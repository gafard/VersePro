#!/usr/bin/env python3
"""Génère le jeu d'icônes de VersePro à partir d'une seule source dessinée ici.

Pourquoi un script plutôt que des PNG déposés à la main : une icône se retouche
(teinte, épaisseur, marges) et se décline en huit tailles. Sans source
reproductible, chaque retouche redevient un travail manuel, et les tailles
finissent par diverger.

Le motif est le produit lui-même : un bandeau clair posé en bas du cadre, avec
l'étiquette de référence en laiton au-dessus. C'est ce que l'assemblée voit sur
l'écran, réduit à deux formes — donc encore lisible à 16 px, là où un livre
ouvert ou une colombe deviendraient une tache.

Conventions respectées :
  • macOS (.icns) — la tuile arrondie est INCLUSE dans l'image, encastrée dans
    le canevas comme le veut la convention depuis Big Sur (environ 80 % du
    cadre). Sans cet encastrement, l'icône paraît plus grosse que ses voisines.
  • Windows (.ico) et PNG génériques — tuile pleine, sans marge.

Usage :  python3 generate_icons.py
"""

import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ICI = Path(__file__).resolve().parent

# Palette de la marque, convertie depuis les jetons oklch du produit.
FOND_HAUT = (16, 20, 32)     # ciel du cadre, légèrement plus clair
FOND_BAS = (5, 7, 13)        # --color-paper
PANNEAU = (243, 245, 249)    # le bandeau clair, comme à la projection
LAITON = (255, 140, 63)      # --accent de l'écran de projection
ENCRE = (14, 20, 38)         # trait d'écriture sur le panneau

# Facteur de suréchantillonnage : les arrondis et le dégradé sont calculés en
# grand puis réduits, sinon les bords crénellent aux petites tailles.
SUR = 4


def _degrade(taille: int) -> Image.Image:
    """Fond vertical sobre : donne du relief sans coûter de lisibilité."""
    fond = Image.new("RGB", (1, taille))
    crayon = ImageDraw.Draw(fond)
    for y in range(taille):
        t = y / max(1, taille - 1)
        crayon.point((0, y), fill=tuple(
            round(FOND_HAUT[c] + (FOND_BAS[c] - FOND_HAUT[c]) * t) for c in range(3)
        ))
    return fond.resize((taille, taille), Image.NEAREST)


def dessiner(taille: int, marge_ratio: float = 0.0) -> Image.Image:
    """Icône complète. `marge_ratio` encastre la tuile (convention macOS)."""
    T = taille * SUR
    image = Image.new("RGBA", (T, T), (0, 0, 0, 0))

    marge = int(T * marge_ratio)
    cote = T - 2 * marge
    rayon = int(cote * 0.225)  # proportion d'angle des tuiles macOS récentes

    # Tuile : dégradé découpé par un masque arrondi.
    tuile = _degrade(cote).convert("RGBA")
    masque = Image.new("L", (cote, cote), 0)
    ImageDraw.Draw(masque).rounded_rectangle([0, 0, cote - 1, cote - 1], radius=rayon, fill=255)
    image.paste(tuile, (marge, marge), masque)

    crayon = ImageDraw.Draw(image)

    def rel(x, y):
        """Coordonnées relatives à la tuile, en fraction de son côté."""
        return marge + x * cote, marge + y * cote

    # Le motif est posé un peu sous le centre — assez bas pour évoquer un
    # bandeau, assez haut pour que la tuile ne paraisse pas vide par le haut.

    # ── L'étiquette de référence, en laiton, posée au-dessus du panneau ──
    ex0, ey0 = rel(0.455, 0.398)
    ex1, ey1 = rel(0.845, 0.500)
    crayon.rounded_rectangle([ex0, ey0, ex1, ey1], radius=int(cote * 0.032), fill=LAITON)

    # ── Le bandeau clair, signature du produit ──
    px0, py0 = rel(0.155, 0.500)
    px1, py1 = rel(0.845, 0.742)
    crayon.rounded_rectangle([px0, py0, px1, py1], radius=int(cote * 0.058), fill=PANNEAU)

    # Deux traits d'écriture : suggèrent le verset sans être lisibles — à 16 px
    # ils fusionnent en une masse claire, ce qui reste juste.
    for x_fin, y in ((0.775, 0.572), (0.615, 0.650)):
        lx0, ly0 = rel(0.222, y)
        lx1, ly1 = rel(x_fin, y + 0.046)
        crayon.rounded_rectangle([lx0, ly0, lx1, ly1], radius=int(cote * 0.023), fill=ENCRE)

    return image.resize((taille, taille), Image.LANCZOS)


def ecrire_png(nom: str, taille: int, marge: float = 0.0) -> None:
    dessiner(taille, marge).save(ICI / nom)
    print(f"  {nom:26} {taille}×{taille}")


def main() -> int:
    print("Icônes VersePro")

    # PNG génériques et tuiles Windows : pleine tuile, sans marge.
    for nom, taille in (
        ("32x32.png", 32), ("128x128.png", 128), ("128x128@2x.png", 256),
        ("Square30x30Logo.png", 30), ("Square44x44Logo.png", 44),
        ("Square71x71Logo.png", 71), ("Square89x89Logo.png", 89),
        ("Square107x107Logo.png", 107), ("Square142x142Logo.png", 142),
        ("Square150x150Logo.png", 150), ("Square284x284Logo.png", 284),
        ("Square310x310Logo.png", 310), ("StoreLogo.png", 50),
        ("icon.png", 512),
    ):
        ecrire_png(nom, taille)

    # Windows .ico : plusieurs résolutions dans un seul fichier, sinon la barre
    # des tâches redimensionne le 256 px et le résultat bave.
    dessiner(256).save(ICI / "icon.ico", format="ICO",
                       sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("  icon.ico                   multi-résolutions")

    # macOS .icns : tuile encastrée, via iconutil (outil du système).
    if sys.platform == "darwin":
        jeu = ICI / "icon.iconset"
        jeu.mkdir(exist_ok=True)
        for base in (16, 32, 128, 256, 512):
            dessiner(base, marge_ratio=0.098).save(jeu / f"icon_{base}x{base}.png")
            dessiner(base * 2, marge_ratio=0.098).save(jeu / f"icon_{base}x{base}@2x.png")
        subprocess.run(["iconutil", "-c", "icns", str(jeu), "-o", str(ICI / "icon.icns")], check=True)
        for reste in jeu.iterdir():
            reste.unlink()
        jeu.rmdir()
        print("  icon.icns                  tuile encastrée (convention macOS)")
    else:
        print("  icon.icns                  ignoré (iconutil n'existe que sur macOS)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
