"""« Samuel 16 7 » : le numéro du livre omis ne doit plus tout faire perdre.

Avant : None pour Samuel, Rois, Chroniques, Corinthiens, Thessaloniciens,
Timothée et Pierre cités sans « premier/deuxième ». Le livre est désormais
déduit du texte lui-même, et une déduction n'est jamais projetée seule.
"""

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.services.verse_parser import VerseParserService


@pytest.fixture(scope="module")
def parseur():
    return VerseParserService()


def _parse(parseur, texte):
    return asyncio.run(parseur.parse(texte, skip_text_search=True))


def test_seul_le_premier_livre_a_ce_chapitre(parseur):
    """2 Samuel s'arrête au chapitre 24 : Samuel 25 ne peut être que 1 Samuel."""
    ref = _parse(parseur, "Samuel 25 1")
    assert ref["reference"] == "1 Samuel 25:1"
    assert ref["alternatives"] == []
    assert ref["livre_deduit"] is True


def test_ambigu_propose_les_deux_sans_trancher(parseur):
    ref = _parse(parseur, "lisons Samuel chapitre 16 verset 7")
    assert ref["reference"] == "1 Samuel 16:7"
    assert ref["alternatives"] == ["2 Samuel 16:7"]
    assert ref["confidence"] <= 0.70


def test_une_deduction_n_atteint_jamais_l_autopilotage(parseur):
    """Le moteur ne projette seul qu'à partir de 0,95."""
    for texte in ("Samuel chapitre 25 verset 1", "Rois chapitre 3 verset 16"):
        assert _parse(parseur, texte)["confidence"] < 0.95, texte


def test_chapitre_inexistant_et_prenom_restent_ignores(parseur):
    assert _parse(parseur, "Samuel 40 1") is None
    assert _parse(parseur, "Pierre est venu 3 fois") is None


def test_le_numero_prononce_reste_prioritaire(parseur):
    ref = _parse(parseur, "deuxième Samuel 7 12")
    assert ref["reference"] == "2 Samuel 7:12"
    assert "livre_deduit" not in ref


def test_la_recherche_montre_les_deux_livres():
    from app.main import app

    with TestClient(app) as client:
        resultats = client.get("/api/v1/bible/search", params={"q": "Timothée 3 16"}).json()["results"]

    references = [r["reference"] for r in resultats[:3]]
    assert "1 Timothée 3:16" in references and "2 Timothée 3:16" in references
