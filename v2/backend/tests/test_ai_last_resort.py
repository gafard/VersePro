"""Arbitrage IA de DERNIER RECOURS (étage C de la cascade).

Garanties vérifiées ici :
  1. l'IA n'est JAMAIS sollicitée quand la chaîne locale trouve (zéro latence
     ajoutée au cas normal — c'est tout l'intérêt du « dernier recours ») ;
  2. elle est sollicitée quand le local est muet ET qu'un indice biblique est là ;
  3. elle reste muette sur la parole du quotidien (mode strict) ;
  4. elle ne peut pas INVENTER un verset : toute réponse est revalidée contre
     la Bible chargée ;
  5. sous le seuil de confiance, la suggestion est écartée ;
  6. ce qui remonte part toujours en validation manuelle.
"""

import asyncio

import pytest

from app import main as M
from app.core.config import settings
from app.services.verse_parser import VerseParserService


class FakeAI:
    """Faux service IA : compte les appels et renvoie une réponse scriptée."""

    def __init__(self, reference="Jean 3:16", confidence=97):
        self.enabled = True
        self.calls = 0
        self.reference = reference
        self.confidence = confidence

    async def detect_bible_reference(self, text, candidates=None):
        self.calls += 1
        if self.reference is None:
            return None
        return {"reference": self.reference, "confidence": self.confidence}


@pytest.fixture
def wired(monkeypatch):
    parser = VerseParserService()
    monkeypatch.setattr(M, "verse_parser", parser)
    monkeypatch.setattr(M, "semantic_service", None)  # local sémantique indisponible
    monkeypatch.setattr(M, "_ai_last_resort_busy", False)
    return parser


def _run(text):
    return asyncio.run(M.run_detection_cascade(text, final_state=True))


def test_ai_not_called_when_local_finds(wired, monkeypatch):
    """Verset lu mot à mot : le local trouve → l'IA n'est pas sollicitée."""
    ai = FakeAI()
    monkeypatch.setattr(M, "ai_service", ai)
    out = _run("l'éternel est mon berger je ne manquerai de rien")
    assert out and out["reference"] == "Psaumes 23:1"
    assert ai.calls == 0, "l'IA ne doit pas être appelée quand le local trouve"


def test_ai_not_called_on_everyday_speech(wired, monkeypatch):
    """Parole du quotidien sans indice biblique : l'IA reste muette (strict)."""
    monkeypatch.setattr(settings, "AI_FILTERING_MODE", "strict")
    ai = FakeAI()
    monkeypatch.setattr(M, "ai_service", ai)
    assert _run("on se retrouve tous après la réunion pour un café dans la salle") is None
    assert ai.calls == 0


def test_ai_called_as_last_resort_and_grounded(wired, monkeypatch):
    """Local muet + indice biblique → l'IA tranche, et sa réponse est ancrée."""
    ai = FakeAI(reference="Jean 3:16", confidence=97)
    monkeypatch.setattr(M, "ai_service", ai)
    out = _run("le seigneur a montré son amour d'une manière que nul ne pouvait imaginer ce jour-là")
    assert ai.calls == 1
    assert out and out["reference"] == "Jean 3:16"
    assert out["detection_method"] == "ai_semantic"
    assert out["requires_review"] is True, "une suggestion IA ne se projette jamais seule"
    assert out["text"], "le texte du verset doit venir de la Bible chargée"


def test_ai_hallucination_is_rejected(wired, monkeypatch):
    """L'IA invente une référence inexistante → écartée."""
    ai = FakeAI(reference="Hezekiah 9:99", confidence=99)
    monkeypatch.setattr(M, "ai_service", ai)
    out = _run("le seigneur a montré sa grâce d'une manière que nul ne pouvait imaginer ce jour-là")
    assert ai.calls == 1
    assert out is None, "une référence introuvable dans la Bible ne doit jamais remonter"


def test_ai_low_confidence_is_rejected(wired, monkeypatch):
    """Sous le seuil de confiance, la suggestion est écartée."""
    monkeypatch.setattr(settings, "AI_CONFIDENCE_THRESHOLD", 95)
    ai = FakeAI(reference="Jean 3:16", confidence=60)
    monkeypatch.setattr(M, "ai_service", ai)
    out = _run("le seigneur a montré sa grâce d'une manière que nul ne pouvait imaginer ce jour-là")
    assert ai.calls == 1
    assert out is None


def test_ai_disabled_is_silent(wired, monkeypatch):
    """IA désactivée : la cascade s'arrête proprement au local."""
    ai = FakeAI()
    ai.enabled = False
    monkeypatch.setattr(M, "ai_service", ai)
    assert _run("le seigneur a montré sa grâce d'une manière que nul ne pouvait imaginer") is None
    assert ai.calls == 0
