"""Deux numéros de verset du même chapitre, à la même seconde : lequel croire ?

RELEVÉ EN PRODUCTION, session du 11 août, 22 h 28. La même phrase a produit
deux détections :

    « Parlez à votre montagne Marc chapitre 11 verset 23. Il »   → Marc 11:23
    « Parlez à votre montagne, Marc chapitre 11 verset 29. »     → Marc 11:29

Et de même à 21 h 54 : Romains 5:14 puis Romains 5:4.

Les deux passent le seuil d'autopilotage avec 0,98 de confiance — motif
explicite, verset bel et bien prononcé — donc aucun filtre de confiance ne
les sépare. C'est le moteur vocal qui a mal entendu un chiffre. L'un des deux
est forcément faux, et rien dans le signal ne dit lequel.

Le moteur ne tranche donc pas : le premier part, le second devient une carte.
Le régisseur voit les deux côte à côte et choisit — ce qu'aucun seuil
numérique ne pouvait faire à sa place.
"""

import asyncio

import pytest

from app.core.config import settings
from app.services.reference_engine import BibleReferenceEngine
from app.services.verse_parser import VerseParserService


class SansIA:
    enabled = False


@pytest.fixture(scope="module")
def moteur():
    settings.AI_AGENT_ENABLED = False
    parser = VerseParserService()
    return BibleReferenceEngine(
        verse_parser=parser,
        semantic_service=None,
        verse_graph=None,
        ai_service=SansIA(),
        settings=settings,
    )


def test_le_second_verset_du_meme_chapitre_passe_en_validation(moteur):
    premier = asyncio.run(moteur.process(
        "Parlez à votre montagne Marc chapitre 11 verset 23. Il",
        is_final=True, generation=1,
    ))
    second = asyncio.run(moteur.process(
        "Parlez à votre montagne, Marc chapitre 11 verset 29.",
        is_final=True, generation=2,
    ))

    assert premier and premier["payload"]["reference"] == "Marc 11:23"
    assert premier["payload"].get("requires_review") is not True, (
        "la première référence part normalement : c'est la contradiction qui "
        "doit alerter, pas la citation elle-même"
    )

    assert second and second["payload"]["reference"] == "Marc 11:29"
    assert second["payload"]["requires_review"] is True
    assert second["payload"]["verset_conteste"] is True


def test_une_lecture_suivie_n_est_pas_une_contradiction(moteur):
    """« verset 3 » puis « verset 4 » douze secondes plus tard est une lecture.

    Le garde-fou ne vaut que dans la fenêtre courte où deux numéros du même
    chapitre trahissent un chiffre mal entendu. Au-delà, un prédicateur qui
    avance dans son passage doit continuer d'être suivi sans validation.
    """
    moteur._emis_recemment.clear()
    premier = asyncio.run(moteur.process(
        "Ouvrons Romains chapitre 12 verset 1", is_final=True, generation=1))
    assert premier and premier["payload"]["reference"] == "Romains 12:1"

    # On vieillit artificiellement la mémoire au-delà de la fenêtre.
    for cle in list(moteur._emis_recemment):
        moteur._emis_recemment[cle] -= moteur.CONTRADICTION_SECONDS + 1

    suivant = asyncio.run(moteur.process(
        "et maintenant Romains chapitre 12 verset 2", is_final=True, generation=2))
    assert suivant and suivant["payload"]["reference"] == "Romains 12:2"
    assert not suivant["payload"].get("verset_conteste")
