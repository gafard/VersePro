"""Recadrage et zoom du fond plein écran, côté NDI.

Recadrer retire une bande de l'IMAGE, puis ce qui reste est cadré sur toute
la trame. L'écran HTML suit la même règle (placerFond dans output.html, testé
par frontend/tests/fond-recadrage.test.js avec les mêmes chiffres) : vMix/OBS
et le vidéoprojecteur doivent recevoir la même image.

Image d'essai 1600x900 : un quart gauche rouge, le reste bleu.
"""

from PIL import Image, ImageDraw

from app.outputs.ndi_render import rendre_habillage

ROUGE = (220, 30, 30)
NOIR = (0, 0, 0)


def _fond(tmp_path, taille=(1600, 900)):
    image = Image.new("RGB", taille, (30, 60, 200))
    ImageDraw.Draw(image).rectangle([0, 0, taille[0] // 4 - 1, taille[1]], fill=ROUGE)
    chemin = tmp_path / "fond.png"
    image.save(chemin)
    return str(chemin)


def _rendu(tmp_path, **options):
    image = rendre_habillage(
        960, 540, [], [], "", "", None, None,
        arriere_plan=_fond(tmp_path, options.pop("taille", (1600, 900))), **options,
    )
    return image.convert("RGB")


def _etendue(rendu, predicat, y=270):
    xs = [x for x in range(rendu.width) if predicat(rendu.getpixel((x, y)))]
    return (xs[0], xs[-1]) if xs else None


def _rouge(p):
    return p[0] > 150 and p[2] < 100


def test_recadrer_retire_l_image_et_non_l_ecran(tmp_path):
    """20 % à gauche : il reste 80 px de rouge sur 1280, agrandis à 960/1280."""
    rendu = _rendu(tmp_path, crop_arriere_plan=(0, 0, 0, 20))

    assert rendu.getpixel((0, 270)) != NOIR, "le recadrage a noirci le bord de l'écran"
    assert _etendue(rendu, _rouge) == (0, 59)


def test_contain_recadre_garde_ses_proportions(tmp_path):
    """Partie gardée 1280x810 cadrée dans 960x540 : 853 px de large, centrée."""
    rendu = _rendu(tmp_path, cadrage_arriere_plan="contain", crop_arriere_plan=(10, 0, 0, 20))

    assert _etendue(rendu, lambda p: p != NOIR) == (54, 906)
    assert _etendue(rendu, _rouge) == (54, 106)


def test_contain_agrandit_une_image_plus_petite_que_la_trame(tmp_path):
    """object-fit: contain agrandit ; thumbnail() ne faisait que réduire.

    Une image 480x270 laissait un cadre noir en NDI, et seulement en NDI.
    """
    rendu = _rendu(tmp_path, taille=(480, 270), cadrage_arriere_plan="contain")

    assert _etendue(rendu, lambda p: p != NOIR) == (0, 959)


def test_le_zoom_reste_centre_sur_l_ecran(tmp_path):
    """Zoom 60 % autour du centre de la trame, cadrage calé à 30 %."""
    rendu = _rendu(
        tmp_path, cadrage_arriere_plan="contain", position_arriere_plan=(30, 50),
        scale_arriere_plan=60, crop_arriere_plan=(5, 0, 20, 10),
    )

    gauche, droite = _etendue(rendu, lambda p: p != NOIR)
    assert abs(gauche - 192) <= 3 and abs(droite - 767) <= 3
    assert rendu.getpixel((100, 270)) == NOIR
