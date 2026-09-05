"""Géométrie des formes d'habillage, partagée par l'écran et par NDI.

`border-radius` ne sait faire qu'un arc SORTANT. Dès qu'on veut un coin creusé
ou biseauté, il faut décrire le contour soi-même. Plutôt que d'écrire deux
rendus qui finiraient par diverger, on produit une seule liste de points :
l'écran la donne à un <polygon> SVG, NDI à Pillow. Le tracé est donc identique
des deux côtés par construction, pas par relecture attentive.

Coins numérotés dans le sens horaire depuis le haut-gauche :
    0 = haut-gauche, 1 = haut-droit, 2 = bas-droit, 3 = bas-gauche

Modes :
    « out » arc sortant (l'arrondi classique)
    « in »  arc rentrant, le coin est creusé
    « cut » pan coupé, un simple biseau droit
"""

import math
from typing import Any, Dict, List, Sequence, Tuple

MODES = ("out", "in", "cut")
# 10 segments par quart de tour : à 1080p, l'écart au cercle parfait reste sous
# le demi-pixel pour les rayons usuels. Inutile d'en mettre plus, chaque point
# est un sommet de polygone que l'écran comme Pillow doivent traiter.
SEGMENTS = 10


def _arc(centre: Tuple[float, float], rayon: float,
         depuis: float, vers: float, segments: int) -> List[Tuple[float, float]]:
    cx, cy = centre
    return [
        (cx + rayon * math.cos(depuis + (vers - depuis) * i / segments),
         cy + rayon * math.sin(depuis + (vers - depuis) * i / segments))
        for i in range(segments + 1)
    ]


def polygon_points(largeur: float, hauteur: float,
                   coins: Sequence[Dict[str, Any]],
                   segments: int = SEGMENTS) -> List[Tuple[float, float]]:
    """Contour d'une forme de `largeur` × `hauteur`, coin par coin.

    Les rayons reçus sont exprimés dans la même unité que les dimensions ; ils
    sont écrêtés à la moitié du plus petit côté pour qu'un rayon exagéré déforme
    la figure au lieu de la retourner.
    """
    L, H = float(largeur), float(hauteur)
    limite = max(0.0, min(L, H) / 2)
    rayons = []
    modes = []
    for index in range(4):
        coin = coins[index] if index < len(coins) and isinstance(coins[index], dict) else {}
        rayons.append(max(0.0, min(limite, float(coin.get("r", 0) or 0))))
        mode = coin.get("mode", "out")
        modes.append(mode if mode in MODES else "out")

    # Sommets géométriques, dans le sens horaire depuis le haut-gauche.
    sommets = [(0.0, 0.0), (L, 0.0), (L, H), (0.0, H)]
    # Pour chaque coin : point d'entrée sur le côté précédent, point de sortie
    # sur le côté suivant, et centre de l'arc sortant.
    entrees = [(0.0, rayons[0]), (L - rayons[1], 0.0), (L, H - rayons[2]), (rayons[3], H)]
    sorties = [(rayons[0], 0.0), (L, rayons[1]), (L - rayons[2], H), (0.0, H - rayons[3])]
    centres = [(rayons[0], rayons[0]), (L - rayons[1], rayons[1]),
               (L - rayons[2], H - rayons[2]), (rayons[3], H - rayons[3])]
    # Angles de l'arc SORTANT, par coin (repère écran : y vers le bas).
    angles = [(math.pi, 1.5 * math.pi), (1.5 * math.pi, 2 * math.pi),
              (0.0, 0.5 * math.pi), (0.5 * math.pi, math.pi)]
    # Pour l'arc RENTRANT, le centre est le SOMMET lui-même : l'arc passe alors
    # par l'intérieur de la forme et le coin se creuse au lieu de bomber. Les
    # angles vont du point d'entrée au point de sortie, dans ce sens.
    angles_rentrants = [(0.5 * math.pi, 0.0), (math.pi, 0.5 * math.pi),
                        (1.5 * math.pi, math.pi), (0.0, -0.5 * math.pi)]

    points: List[Tuple[float, float]] = []
    for index in range(4):
        rayon = rayons[index]
        if rayon <= 0:
            points.append(sommets[index])
            continue
        points.append(entrees[index])
        if modes[index] == "cut":
            pass  # le segment droit vers la sortie suffit
        elif modes[index] == "in":
            debut, fin = angles_rentrants[index]
            points.extend(_arc(sommets[index], rayon, debut, fin, segments))
        else:
            debut, fin = angles[index]
            points.extend(_arc(centres[index], rayon, debut, fin, segments))
        points.append(sorties[index])
    return points


def normalise_corners(forme: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Coins d'une forme, en acceptant l'ancien champ `radius` uniforme.

    Les habillages enregistrés avant cette fonctionnalité n'ont qu'un rayon
    global : ils doivent continuer de s'afficher exactement pareil.
    """
    coins = forme.get("corners")
    if isinstance(coins, list) and coins:
        return [
            {
                "r": float(c.get("r", 0) or 0) if isinstance(c, dict) else 0.0,
                "mode": (c.get("mode") if isinstance(c, dict) and c.get("mode") in MODES else "out"),
            }
            for c in (list(coins) + [{}] * 4)[:4]
        ]
    rayon = float(forme.get("radius", 0) or 0)
    return [{"r": rayon, "mode": "out"} for _ in range(4)]
