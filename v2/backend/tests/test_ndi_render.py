"""Rendu pixel de l'habillage pour NDI.

Ce module doit produire la MÊME composition que l'écran de projection : c'est
tout l'intérêt d'avoir un modèle d'habillage partagé. Les tests ne jugent pas
l'esthétique — ils vérifient que la géométrie, les couleurs et la transparence
sont respectées, et que le rendu ne dépend pas du runtime NDI.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.outputs.ndi_render import rendre_habillage, vers_bgra, _rgba
from app.services import overlay_store


def _rendu(**extra):
    base = dict(
        largeur=640, hauteur=360,
        zones=overlay_store.parse_zones(""),
        formes=overlay_store.parse_shapes(""),
        reference="Exode 17:11 (LSG)",
        texte="Lorsque Moïse élevait sa main, Israël était le plus fort.",
        numero_verset=11,
    )
    base.update(extra)
    return rendre_habillage(**base)


# ── Couleurs ─────────────────────────────────────────────────────────────────

def test_couleur_hexadecimale_longue():
    assert _rgba("#489e8c") == (72, 158, 140, 255)


def test_couleur_hexadecimale_courte():
    assert _rgba("#fff") == (255, 255, 255, 255)


def test_opacite_appliquee_a_lalpha():
    assert _rgba("#000000", 0.5)[3] == 127


def test_couleur_illisible_retombe_sur_blanc():
    """Le nettoyage amont doit déjà l'empêcher ; le rendu ne plante pas pour autant."""
    assert _rgba("pas-une-couleur")[:3] == (255, 255, 255)


# ── Composition ──────────────────────────────────────────────────────────────

def test_le_haut_du_cadre_reste_transparent():
    """Un bandeau doit laisser voir la vidéo au-dessus de lui."""
    image = _rendu()
    assert image.getpixel((320, 30))[3] == 0


def test_le_panneau_est_opaque_et_clair():
    image = _rendu()
    # Milieu du panneau blanc (y ≈ 88 % de la hauteur)
    r, v, b, a = image.getpixel((320, int(360 * 0.88)))
    assert a > 200 and min(r, v, b) > 200


def test_letiquette_porte_sa_couleur():
    image = _rendu()
    # Milieu de l'étiquette turquoise (x ≈ 80 %, y ≈ 77 %)
    r, v, b, a = image.getpixel((int(640 * 0.80), int(360 * 0.771)))
    assert a > 200 and v > r and v > b


def test_sans_forme_ni_image_le_cadre_reste_vide():
    image = _rendu(formes=[], reference="", texte="")
    assert image.getbbox() is None


def test_le_texte_marque_le_panneau():
    """Un verset rendu doit assombrir le panneau ; sinon rien n'est écrit."""
    avec = _rendu()
    sans = _rendu(texte="", reference="")
    bande = [(x, int(360 * 0.86)) for x in range(120, 520, 4)]
    sombres_avec = sum(1 for p in bande if avec.getpixel(p)[0] < 120)
    sombres_sans = sum(1 for p in bande if sans.getpixel(p)[0] < 120)
    assert sombres_avec > sombres_sans


def test_le_rendu_suit_la_resolution():
    petit, grand = _rendu(largeur=640, hauteur=360), _rendu(largeur=1920, hauteur=1080)
    assert petit.size == (640, 360) and grand.size == (1920, 1080)
    # Le panneau occupe la même fraction du cadre dans les deux cas.
    assert petit.getpixel((320, int(360 * 0.88)))[3] > 200
    assert grand.getpixel((960, int(1080 * 0.88)))[3] > 200


def test_une_image_de_fond_absente_nempeche_pas_le_rendu():
    image = _rendu(image_fond="/chemin/qui/nexiste/pas.png")
    assert image.size == (640, 360)


# ── Conversion pour NDI ──────────────────────────────────────────────────────

def test_conversion_bgrx_permute_le_rouge_et_le_bleu():
    from PIL import Image
    source = Image.new("RGBA", (2, 2), (10, 20, 30, 40))
    arr = vers_bgra(source)
    assert tuple(arr[0, 0]) == (30, 20, 10, 40)


def test_la_trame_est_contigue_pour_la_bibliotheque_native():
    """NDIlib lit un tampon brut : un tableau non contigu produirait du bruit."""
    arr = vers_bgra(_rendu())
    assert arr.flags["C_CONTIGUOUS"] and arr.dtype.name == "uint8"


# ── Canal alpha : ce qui distingue une incrustation d'un cache ───────────────

def test_la_trame_porte_un_alpha_reellement_variable():
    """Une incrustation professionnelle EXIGE de la transparence.

    Mesuré sur un bandeau 1920×1080 : 99,3 % de la trame est totalement
    transparente, 0,5 % opaque, et 0,19 % en dégradé — les bords adoucis du
    texte et des coins arrondis.

    L'émission déclarait pourtant `FOURCC_VIDEO_TYPE_BGRX`, où le « X » signifie
    octet IGNORÉ : le mélangeur recevait un cadre opaque plein écran qui
    masquait la vidéo. L'alpha était calculé, transporté, puis jeté à la
    dernière ligne.
    """
    formes = overlay_store.parse_shapes(
        '[{"x":0.03,"y":0.78,"w":0.94,"h":0.18,"fill":"#101418",'
        '"corners":[{"r":18,"mode":"out"},{"r":18,"mode":"out"},'
        '{"r":18,"mode":"out"},{"r":18,"mode":"out"}]}]'
    )
    image = rendre_habillage(
        640, 360, overlay_store.parse_zones(""), formes,
        "Jean 3:16", "Car Dieu a tant aimé le monde", None, None,
    )
    alpha = vers_bgra(image)[..., 3]

    assert alpha.min() == 0, "aucun pixel transparent : rien à incruster"
    assert alpha.max() == 255, "aucun pixel opaque : le bandeau serait invisible"
    part_transparente = float((alpha == 0).mean())
    assert part_transparente > 0.5, (
        f"seulement {part_transparente:.0%} de transparent — le bandeau "
        "couvrirait la vidéo au lieu de s'y incruster"
    )


def test_l_ordre_des_octets_est_bien_BGRA():
    """B et R permutés par rapport à Pillow, alpha inchangé en 4e position."""
    from PIL import Image
    source = Image.new("RGBA", (2, 2), (10, 20, 30, 40))
    arr = vers_bgra(source)
    assert tuple(arr[0, 0]) == (30, 20, 10, 40)


# ── Fonds animés : optionnels, et la sobriété reste le défaut ────────────────

def _output_html():
    """Le HTML de l'écran de projection, tel que servi."""
    from pathlib import Path
    template = Path(__file__).resolve().parents[1] / "app" / "templates" / "output.html"
    return template.read_text(encoding="utf-8")


def test_les_fonds_animes_ne_tournent_que_sur_demande():
    """Sans `?bg=`, l'écran ne déclare AUCUNE animation infinie.

    C'est une propriété de performance, pas un détail : elle rend l'écran
    tenable sur la machine modeste d'une petite église. Les fonds animés sont
    donc conditionnés à une classe qu'aucun réglage par défaut ne pose.
    """
    html = _output_html()
    assert 'body[class*="fond-"]::before' in html, "le fond animé doit être conditionné"
    # L'animation infinie n'existe QUE sous ce sélecteur conditionnel.
    for ligne in html.split("\n"):
        if "infinite" in ligne:
            assert "derive-fond" in ligne, (
                f"animation infinie hors des fonds optionnels : {ligne.strip()}"
            )


def test_un_fond_anime_respecte_le_mouvement_reduit():
    """Un fond qui bouge peut gêner ; la demande système existe pour ça."""
    html = _output_html()
    assert "prefers-reduced-motion" in html
    bloc = html[html.index("prefers-reduced-motion"):]
    assert 'fond-' in bloc[:220] and "animation: none" in bloc[:220]


def test_la_liste_des_fonds_est_fermee():
    """`bg` vient d'un paramètre d'URL : une valeur libre concaténée dans un nom
    de classe laisserait n'importe qui styler l'écran depuis un lien."""
    html = _output_html()
    assert "['aurore', 'braise', 'nuit', 'sable'].includes(bg)" in html
