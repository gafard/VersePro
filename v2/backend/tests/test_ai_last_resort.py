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

from app.core.config import settings
from app.services.reference_engine import BibleReferenceEngine
from app.services.verse_parser import VerseParserService


class FakeAI:
    """Faux service IA : compte les appels et renvoie une réponse scriptée."""

    def __init__(self, reference="Jean 3:16", confidence=97):
        self.enabled = True
        self.calls = 0
        self.reference = reference
        self.confidence = confidence
        self.contexte_recu = None
        self.candidats_recus = None

    async def detect_bible_reference(self, text, candidates=None, contexte=None):
        self.calls += 1
        self.contexte_recu = list(contexte or [])
        self.candidats_recus = list(candidates or [])
        if self.reference is None:
            return None
        return {"reference": self.reference, "confidence": self.confidence}


# La cascade a quitté main.py pour BibleReferenceEngine. Les six garanties
# ci-dessous portent sur le COMPORTEMENT, pas sur l'endroit où il vit : on
# construit donc un moteur avec des services factices, et on l'interroge par
# `detecter_sans_effet` — la cascade pure, sans la mémoire de déduplication
# que `process()` entretient pour le direct.
class _Moteur:
    """Petit conteneur : garde le moteur ET l'IA factice sous la main."""

    def __init__(self, parser):
        self.parser = parser
        self.ai = None

    def avec_ia(self, ai):
        self.ai = ai
        self.engine = BibleReferenceEngine(
            verse_parser=self.parser,
            semantic_service=None,   # local sémantique indisponible
            verse_graph=None,
            ai_service=ai,
            settings=settings,
        )
        return self.engine


@pytest.fixture
def wired(monkeypatch):
    return _Moteur(VerseParserService())


def _anchor_candidates(parser, monkeypatch):
    monkeypatch.setattr(
        parser.bible_loader,
        "search_candidates",
        lambda text, limit=3: [{
            "reference": "Jean 3:16",
            "text": "Car Dieu a tant aimé le monde qu'il a donné son Fils unique.",
            "book_abbr": "Jn",
            "chapter": 3,
            "verse_start": 16,
            "verse_end": None,
            "confidence": 0.9,
        }],
    )


def _run(moteur, text):
    return asyncio.run(moteur.detecter_sans_effet(text, final_state=True))


def test_ai_not_called_when_local_finds(wired, monkeypatch):
    """Verset lu mot à mot : le local trouve → l'IA n'est pas sollicitée."""
    ai = FakeAI()
    moteur = wired.avec_ia(ai)
    out = _run(moteur, "l'éternel est mon berger je ne manquerai de rien")
    assert out and out["reference"] == "Psaumes 23:1"
    assert ai.calls == 0, "l'IA ne doit pas être appelée quand le local trouve"


def test_ai_not_called_on_everyday_speech(wired, monkeypatch):
    """Parole du quotidien sans indice biblique : l'IA reste muette (strict)."""
    monkeypatch.setattr(settings, "AI_FILTERING_MODE", "strict")
    ai = FakeAI()
    moteur = wired.avec_ia(ai)
    assert _run(moteur, "on se retrouve tous après la réunion pour un café dans la salle") is None
    assert ai.calls == 0


def test_ai_called_as_last_resort_and_grounded(wired, monkeypatch):
    """Local muet + indice biblique → l'IA tranche, et sa réponse est ancrée."""
    ai = FakeAI(reference="Jean 3:16", confidence=97)
    _anchor_candidates(wired.parser, monkeypatch)
    moteur = wired.avec_ia(ai)
    out = _run(moteur, "le seigneur a montré son amour d'une manière que nul ne pouvait imaginer ce jour-là")
    assert ai.calls == 1
    assert out and out["reference"] == "Jean 3:16"
    assert out["detection_method"] == "ai_semantic"
    assert out["requires_review"] is True, "une suggestion IA ne se projette jamais seule"
    assert out["text"], "le texte du verset doit venir de la Bible chargée"


def test_ai_hallucination_is_rejected(wired, monkeypatch):
    """L'IA invente une référence inexistante → écartée."""
    ai = FakeAI(reference="Hezekiah 9:99", confidence=99)
    _anchor_candidates(wired.parser, monkeypatch)
    moteur = wired.avec_ia(ai)
    out = _run(moteur, "le seigneur a montré sa grâce d'une manière que nul ne pouvait imaginer ce jour-là")
    assert ai.calls == 1
    assert out is None, "une référence introuvable dans la Bible ne doit jamais remonter"


def test_ai_low_confidence_is_rejected(wired, monkeypatch):
    """Sous le seuil de confiance, la suggestion est écartée."""
    monkeypatch.setattr(settings, "AI_CONFIDENCE_THRESHOLD", 95)
    _anchor_candidates(wired.parser, monkeypatch)
    ai = FakeAI(reference="Jean 3:16", confidence=60)
    moteur = wired.avec_ia(ai)
    out = _run(moteur, "le seigneur a montré sa grâce d'une manière que nul ne pouvait imaginer ce jour-là")
    assert ai.calls == 1
    assert out is None


def test_ai_disabled_is_silent(wired, monkeypatch):
    """IA désactivée : la cascade s'arrête proprement au local."""
    ai = FakeAI()
    ai.enabled = False
    moteur = wired.avec_ia(ai)
    assert _run(moteur, "le seigneur a montré sa grâce d'une manière que nul ne pouvait imaginer") is None
    assert ai.calls == 0


# ── Contexte et liberté : ce qui manquait pour rivaliser sur les allusions ───

def test_l_ia_recoit_les_enonces_precedents(wired, monkeypatch):
    """Une allusion vit dans son fil.

    « Il tenait les bras levés » ne désigne rien tout seul ; précédé de « Moïse
    était sur la colline », il désigne Exode 17. Analyser la phrase hors de son
    contexte revient à juger une ligne sortie d'un livre.
    """
    ai = FakeAI(reference=None)
    moteur = wired.avec_ia(ai)
    _anchor_candidates(wired.parser, monkeypatch)

    asyncio.run(moteur.process("moïse était monté au sommet de la colline avec le bâton de dieu",
                               is_final=True, generation=1))
    asyncio.run(moteur.process("josué combattait amalek dans la vallée par la parole du seigneur",
                               is_final=True, generation=2))
    asyncio.run(moteur.process("et tant qu il tenait les bras levés le peuple l emportait",
                               is_final=True, generation=3))

    assert len(ai.contexte_recu) == 2, "les deux énoncés précédents doivent être transmis"
    assert "colline" in ai.contexte_recu[0]
    assert "amalek" in ai.contexte_recu[1].lower()
    assert ai.calls >= 1, "l'IA doit être interrogée malgré l'absence de mot biblique dans la phrase"


def test_le_contexte_ne_garde_que_les_enonces_clos(wired, monkeypatch):
    """Un partiel change à chaque seconde : le mémoriser remplirait le contexte
    de versions successives de la même phrase."""
    ai = FakeAI(reference=None)
    moteur = wired.avec_ia(ai)
    _anchor_candidates(wired.parser, monkeypatch)

    asyncio.run(moteur.process("le seigneur a montré", is_final=False, generation=1))
    asyncio.run(moteur.process("le seigneur a montré sa grâce", is_final=False, generation=2))
    asyncio.run(moteur.process("le seigneur a montré sa grâce ce jour là", is_final=True, generation=3))
    asyncio.run(moteur.process("et nous en avons tous été témoins ce matin", is_final=True, generation=4))

    assert len(ai.contexte_recu) == 1, "seul l'énoncé CLOS précédent compte"


def test_une_liste_vide_n_empeche_plus_d_interroger_l_ia(wired, monkeypatch):
    """LE défaut le plus profond de la cascade, mesuré.

    Sur « tant qu'il tenait les bras levés », la recherche lexicale rend ZÉRO
    candidat. Le code s'arrêtait là : l'IA n'était pas appelée, précisément
    dans le seul cas où elle sert. Une liste vide ne dit pas « rien à trouver »,
    elle dit « les moteurs locaux n'ont pas su ».
    """
    ai = FakeAI(reference="Exode 17:11", confidence=92)
    moteur = wired.avec_ia(ai)
    monkeypatch.setattr(wired.parser.bible_loader, "search_candidates",
                        lambda text, limit=3: [])
    # Mode ouvert : ce test porte sur la LISTE VIDE, pas sur le filtre strict,
    # qui a ses propres cas plus bas.
    monkeypatch.setattr(settings, "AI_FILTERING_MODE", "open")

    out = asyncio.run(moteur.process(
        "et tant qu il tenait les bras levés le peuple l emportait",
        is_final=True, generation=1))

    assert ai.calls == 1, "l'IA doit être interrogée même sans candidat"
    assert ai.candidats_recus == [], "et sans liste fermée"
    assert out and out["payload"]["reference"] == "Exode 17:11"
    assert out["payload"]["requires_review"] is True, "une proposition libre ne se projette jamais seule"


def test_une_proposition_libre_inventee_est_ecartee(wired, monkeypatch):
    """L'IA choisit, la BIBLE tranche. Sans liste fermée, c'est la résolution
    contre la Bible chargée qui empêche l'invention."""
    ai = FakeAI(reference="Hezekiah 9:99", confidence=99)
    moteur = wired.avec_ia(ai)
    monkeypatch.setattr(wired.parser.bible_loader, "search_candidates",
                        lambda text, limit=3: [])

    out = asyncio.run(moteur.process(
        "le seigneur a montré sa grâce d une manière que nul ne pouvait imaginer",
        is_final=True, generation=1))
    assert ai.calls == 1
    assert out is None


def test_une_proposition_libre_peu_sure_est_ecartee(wired, monkeypatch):
    """Seuil PROPRE aux propositions libres : aucune corroboration locale ne
    les appuie, seulement le jugement du modèle."""
    ai = FakeAI(reference="Jean 3:16", confidence=settings.AI_FREE_CONFIDENCE_THRESHOLD - 10)
    moteur = wired.avec_ia(ai)
    monkeypatch.setattr(wired.parser.bible_loader, "search_candidates",
                        lambda text, limit=3: [])

    out = asyncio.run(moteur.process(
        "le seigneur a montré sa grâce d une manière que nul ne pouvait imaginer",
        is_final=True, generation=1))
    assert out is None


def test_le_seuil_libre_est_plus_bas_que_le_seuil_ancre():
    """Sinon la voie libre serait interdite : sa confiance plafonnait à 85 sous
    un seuil de 95, faute de score de récupération."""
    assert settings.AI_FREE_CONFIDENCE_THRESHOLD < settings.AI_CONFIDENCE_THRESHOLD


def test_le_mode_strict_juge_sur_la_phrase_ET_son_contexte(wired, monkeypatch):
    """Le filtre strict écartait la plupart des ALLUSIONS.

    « Tant qu'il tenait les bras levés » ne contient aucun mot biblique. Le
    filtre l'écartait donc — et avec elle, précisément le genre de phrase que
    l'IA doit traiter. Précédée de « Moïse... la parole du Seigneur », la même
    phrase est manifestement religieuse.
    """
    monkeypatch.setattr(settings, "AI_FILTERING_MODE", "strict")
    ai = FakeAI(reference=None)
    moteur = wired.avec_ia(ai)
    _anchor_candidates(wired.parser, monkeypatch)

    # Sans contexte : écartée, et c'est voulu.
    asyncio.run(moteur.process("et tant qu il tenait les bras levés le peuple l emportait",
                               is_final=True, generation=1))
    assert ai.calls == 0

    # Le contexte rend le propos manifestement religieux.
    asyncio.run(moteur.process("la parole du seigneur était sur lui ce jour là",
                               is_final=True, generation=2))
    avant = ai.calls
    asyncio.run(moteur.process("et tant qu il tenait les bras levés le peuple l emportait",
                               is_final=True, generation=3))
    assert ai.calls > avant, "le contexte religieux doit ouvrir l'analyse"
