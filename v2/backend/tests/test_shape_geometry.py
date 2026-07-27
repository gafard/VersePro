"""Contour des formes d'habillage, coin par coin.

Cette géométrie est écrite deux fois : ici en Python pour la sortie NDI, et en
JavaScript pour l'écran de projection. Les tests fixent le comportement attendu
des deux — si l'un des deux dérive, c'est ici qu'on doit s'en apercevoir.
"""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.outputs.shape_geometry import normalise_corners, polygon_points

L, H = 200.0, 150.0


def _coins(rayon, mode):
    return [{"r": rayon, "mode": mode} for _ in range(4)]


def _dans_la_boite(points, marge=0.001):
    return all(-marge <= x <= L + marge and -marge <= y <= H + marge for x, y in points)


# ── Modes de coin ────────────────────────────────────────────────────────────

def test_sans_rayon_le_contour_est_un_rectangle():
    assert polygon_points(L, H, _coins(0, "out")) == [(0, 0), (L, 0), (L, H), (0, H)]


def test_le_coin_biseaute_ne_produit_que_deux_points():
    """Un pan coupé est un simple segment : aucun arc à approcher."""
    points = polygon_points(L, H, _coins(30, "cut"))
    assert len(points) == 8  # 2 points par coin


def test_un_coin_arrondi_reste_dans_la_boite():
    assert _dans_la_boite(polygon_points(L, H, _coins(40, "out")))


def test_un_coin_creuse_reste_dans_la_boite():
    """Le creux se prend sur la matière : jamais de débordement au-dehors.

    C'est exactement ce qui clochait au premier essai — les arcs bombaient à
    l'extérieur de la forme au lieu de l'entamer.
    """
    assert _dans_la_boite(polygon_points(L, H, _coins(40, "in")))


def test_arrondi_et_creuse_partent_des_memes_points():
    """Seule la courbure change : les points d'attache sur les côtés sont communs."""
    sortant = polygon_points(L, H, _coins(30, "out"))
    rentrant = polygon_points(L, H, _coins(30, "in"))
    assert sortant[0] == rentrant[0]
    assert sortant[-1] == rentrant[-1]


def test_le_creux_passe_par_linterieur():
    """Au milieu de l'arc rentrant du haut-gauche, on est DANS la forme."""
    rayon = 40
    points = polygon_points(L, H, [{"r": rayon, "mode": "in"}] + _coins(0, "out")[1:])
    milieu = points[1 + 5]  # entrée, puis 5e point de l'arc
    attendu = rayon * math.cos(math.pi / 4)
    assert milieu[0] == round(attendu, 10) or abs(milieu[0] - attendu) < 0.001
    assert abs(milieu[1] - attendu) < 0.001


def test_le_bombe_passe_par_lexterieur_du_centre():
    """L'arc sortant du haut-gauche s'éloigne du coin, vers (0,0)."""
    rayon = 40
    points = polygon_points(L, H, [{"r": rayon, "mode": "out"}] + _coins(0, "out")[1:])
    milieu = points[1 + 5]
    attendu = rayon - rayon * math.cos(math.pi / 4)
    assert abs(milieu[0] - attendu) < 0.001 and abs(milieu[1] - attendu) < 0.001


# ── Robustesse ───────────────────────────────────────────────────────────────

def test_un_rayon_demesure_est_ecrete_a_la_moitie_du_petit_cote():
    """Sans écrêtage, la figure se retourne sur elle-même."""
    assert _dans_la_boite(polygon_points(L, H, _coins(9999, "out")))
    assert _dans_la_boite(polygon_points(L, H, _coins(9999, "in")))


def test_un_mode_inconnu_retombe_sur_larrondi():
    inconnu = polygon_points(L, H, _coins(30, "spirale"))
    assert inconnu == polygon_points(L, H, _coins(30, "out"))


def test_des_coins_manquants_sont_traites_comme_droits():
    assert polygon_points(L, H, [{"r": 20, "mode": "out"}])[-1] == (0, H)


def test_chaque_coin_est_independant():
    points = polygon_points(L, H, [
        {"r": 40, "mode": "out"}, {"r": 40, "mode": "in"},
        {"r": 40, "mode": "cut"}, {"r": 0, "mode": "out"},
    ])
    assert points[-1] == (0, H)      # bas-gauche resté droit
    assert _dans_la_boite(points)


# ── Compatibilité avec les habillages antérieurs ─────────────────────────────

def test_un_ancien_rayon_uniforme_est_repris_sur_les_quatre_coins():
    """Les habillages enregistrés avant les coins indépendants ne doivent pas
    changer d'allure."""
    coins = normalise_corners({"radius": 3.2})
    assert coins == [{"r": 3.2, "mode": "out"}] * 4


def test_des_coins_explicites_priment_sur_le_rayon_global():
    coins = normalise_corners({"radius": 3.2, "corners": [{"r": 1, "mode": "in"}]})
    assert coins[0] == {"r": 1.0, "mode": "in"}
    assert len(coins) == 4


def test_une_forme_sans_rayon_ni_coins_reste_droite():
    assert normalise_corners({}) == [{"r": 0.0, "mode": "out"}] * 4
