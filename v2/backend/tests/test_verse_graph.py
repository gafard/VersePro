"""Tests du service VerseGraph — allusions contextuelles dans le passage ouvert."""

import pytest
import time
from app.services.verse_graph import VerseGraphService, ANCRE_SCORE_MIN, ANCRE_ECART_MIN


class MockSemantic:
    """Mock sémantique simulant les entrées et l'encodage pour les tests."""
    def __init__(self):
        self.initialized = True
        self.entries = [
            {"reference": "Exode 17:11", "book_abbr": "Ex", "chapter": 17, "verse_start": 11, "text": "Lorsque Moïse élevait sa main, Israël était le plus fort"},
            {"reference": "Exode 17:12", "book_abbr": "Ex", "chapter": 17, "verse_start": 12, "text": "Les mains de Moïse étant fatiguées, ils prirent une pierre"},
            {"reference": "Jean 11:43", "book_abbr": "Jn", "chapter": 11, "verse_start": 43, "text": "Il cria d'une voix forte: Lazare, sors!"},
            {"reference": "Jean 11:44", "book_abbr": "Jn", "chapter": 11, "verse_start": 44, "text": "Et le mort sortit, les pieds et les mains liés"},
        ]
        import numpy as np
        # Matrice factice
        self.matrix = np.eye(len(self.entries), dtype=np.float32)

    def _encode(self, texts, kind="query"):
        import numpy as np
        # Pour les tests, renvoie un vecteur prévisible
        vec = np.zeros(len(self.entries), dtype=np.float32)
        txt = texts[0].lower()
        if "lazare" in txt or "tombeau" in txt or "voix forte" in txt:
            vec[2] = 0.85 # Jean 11:43
            vec[3] = 0.80 # Jean 11:44
        elif "mains" in txt or "moïse" in txt or "élevait" in txt:
            vec[0] = 0.84 # Exode 17:11
            vec[1] = 0.80 # Exode 17:12
        else:
            vec[2] = 0.81
            vec[3] = 0.805 # Écart trop faible = 0.005
        return np.array([vec], dtype=np.float32)


def test_verse_graph_ancrage_explicite():
    sem = MockSemantic()
    vg = VerseGraphService(sem)

    # Une détection non explicite ne doit pas ancrer
    assert vg.ancrer({"detection_method": "semantic", "book_abbr": "Ex", "chapter": 17, "reference": "Exode 17:11"}) is False
    assert vg.etat()["ancre"] is None

    # Une citation explicite confirme l'ancrage
    assert vg.ancrer({"detection_method": "explicit", "book_abbr": "Ex", "chapter": 17, "reference": "Exode 17:11"}) is True
    assert vg.etat()["ancre"] == "Exode 17"


def test_verse_graph_ancre_sur_un_chapitre_sans_verset():
    """« Allons dans Exode chapitre dix-sept » doit ouvrir le passage.

    C'est la façon NORMALE d'ouvrir un texte avant de l'expliquer, et le
    parseur la rend en « chapter_candidate » — même analyse par expressions
    régulières que « explicit », simplement sans numéro de verset.

    L'écoute d'un enregistrement l'a révélé : tant que cette forme n'ancrait
    pas, l'allusion prononcée deux phrases plus loin était perdue.
    """
    vg = VerseGraphService(MockSemantic())
    assert vg.ancrer({"detection_method": "chapter_candidate", "book_abbr": "Ex",
                      "chapter": 17, "reference": "Exode 17"}) is True
    assert vg.etat()["ancre"] == "Exode 17"


def test_verse_graph_refuse_d_ancrer_sur_une_hypothese():
    """La sûreté tient à ceci : seule une citation ÉNONCÉE ouvre un passage.

    Si une détection sémantique pouvait ancrer, une erreur en entraînerait
    d'autres dans le même chapitre — l'écart d'un faux positif deviendrait
    une dérive sur toute la prédication.
    """
    vg = VerseGraphService(MockSemantic())
    for methode in ("semantic_local", "semantic_anchored", "ai_semantic", "fusion"):
        assert vg.ancrer({"detection_method": methode, "book_abbr": "Jn",
                          "chapter": 11, "reference": "Jean 11:43"}) is False
    assert vg.etat()["ancre"] is None


def test_verse_graph_resoudre_allusion():
    sem = MockSemantic()
    vg = VerseGraphService(sem)

    # Ancrage sur Jean 11
    vg.ancrer({"detection_method": "explicit", "book_abbr": "Jn", "chapter": 11, "reference": "Jean 11:1"})

    # Allusion pertinente dans le chapitre ouvert
    res = vg.resoudre("il a crié d'une voix forte devant le tombeau")
    assert res is not None
    assert res["reference"] == "Jean 11:43"
    assert res["detection_method"] == "semantic_anchored"
    assert res["requires_review"] is True
    assert res["verse_graph"]["ancre"] == "Jean 11"
    assert res["verse_graph"]["ecart"] >= ANCRE_ECART_MIN


def test_verse_graph_rejette_bruit_et_ecart_faible():
    sem = MockSemantic()
    vg = VerseGraphService(sem)

    vg.ancrer({"detection_method": "explicit", "book_abbr": "Jn", "chapter": 11, "reference": "Jean 11:1"})

    # Phrasé générique (écart trop faible)
    res = vg.resoudre("mon frère jean va nous conduire dans la prière ce matin")
    assert res is None


def test_verse_graph_expiration_ancre():
    sem = MockSemantic()
    vg = VerseGraphService(sem, duree_s=0.1) # Expiration rapide 100ms

    vg.ancrer({"detection_method": "explicit", "book_abbr": "Ex", "chapter": 17, "reference": "Exode 17:1"})
    time.sleep(0.15) # Attendre l'expiration

    res = vg.resoudre("lorsque moïse élevait la main vers le ciel")
    assert res is None
