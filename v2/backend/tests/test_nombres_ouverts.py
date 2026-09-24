"""Ne pas projeter « Galates 5:20 » pendant que le prédicateur dit « vingt-deux ».

Mesuré de bout en bout (benchmarks/latence_parole.py) : le moteur envoyait
Galates 5, puis 5:20 dès « vingt », puis 5:22. Un partiel explicite étant
projetable seul (0,98), l'autopilote affichait le mauvais verset. Et
« Romains 8:80 » — le chapitre en compte 39 — passait pour une référence.
"""

import asyncio

import pytest

from app.core.config import settings
from app.services.reference_engine import BibleReferenceEngine
from app.services.verse_parser import VerseParserService


class _SansIA:
    enabled = False


@pytest.fixture(scope="module")
def moteur():
    return BibleReferenceEngine(
        verse_parser=VerseParserService(), semantic_service=None, verse_graph=None,
        ai_service=_SansIA(), settings=settings,
    )


def _detecter(moteur, texte, final):
    resultat = asyncio.run(moteur.detecter_sans_effet(texte, final_state=final))
    return resultat and resultat.get("reference")


@pytest.mark.parametrize("texte", [
    "lisons galates chapitre cinq verset vingt",
    "lisons galates chapitre cinq verset 20",
    "matthieu chapitre cinq verset trente",
    "psaume cent dix-neuf verset quatre-vingt",
])
def test_un_nombre_ouvert_en_fin_de_partiel_attend(moteur, texte):
    assert _detecter(moteur, texte, final=False) is None


def test_la_suite_du_nombre_tranche(moteur):
    assert _detecter(moteur, "lisons galates chapitre cinq verset vingt deux", False) == "Galates 5:22"
    assert _detecter(moteur, "matthieu chapitre cinq verset trente car", False) == "Matthieu 5:30"


def test_la_fin_de_l_enonce_confirme_le_nombre_rond(moteur):
    """Le prédicateur a vraiment dit « vingt » : l'énoncé clos le dit."""
    assert _detecter(moteur, "lisons galates chapitre cinq verset vingt", True) == "Galates 5:20"


def test_une_reference_complete_reste_instantanee(moteur):
    assert _detecter(moteur, "ouvrons jean chapitre trois verset seize", False) == "Jean 3:16"


def test_un_verset_inexistant_n_est_pas_une_reference():
    parseur = VerseParserService()
    reference = asyncio.run(parseur.parse("Romains 8:80", skip_text_search=True))
    assert not (reference and reference.get("verse_start") == 80)
    assert asyncio.run(parseur.parse("Romains 8:39", skip_text_search=True))["reference"] == "Romains 8:39"
