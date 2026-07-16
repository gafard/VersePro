import asyncio

import pytest

from app.outputs.propresenter import ProPresenterOutput
from app.services.verse_parser import VerseParserService


@pytest.mark.parametrize(
    ("text", "reference"),
    [
        ("Lisons Jean 3:16", "Jean 3:16"),
        ("Mt 5:1-12", "Matthieu 5:1-12"),
        ("1 Co 13:4-8", "1 Corinthiens 13:4-8"),
        ("Ésaïe chapitre 53", "Ésaïe 53"),
        ("Dieu est amour", "1 Jean 4:8"),
        ("L'Éternel est mon berger", "Psaumes 23:1"),
        ("Psaume cent dix neuf verset cent soixante seize", "Psaumes 119:176"),
    ],
)
def test_parser_high_value_cases(text, reference):
    parser = VerseParserService()
    result = asyncio.run(parser.parse(text))

    assert result is not None
    assert result["reference"] == reference


def test_loose_pattern_confidence_below_autopilot_threshold():
    """Le pattern sans séparateur ("jean 3 16", typique de Vosk) doit détecter la
    référence mais rester sous le seuil d'autopilotage (0.95) pour passer en
    validation manuelle — il est trop sujet aux faux positifs."""
    parser = VerseParserService()

    # Sans indice de citation, le pattern loose ne s'applique plus (anti-faux)
    assert asyncio.run(parser.parse("Jean trois seize")) is None

    loose = asyncio.run(parser.parse("lisons Jean trois seize"))
    assert loose is not None
    assert loose["reference"] == "Jean 3:16"
    assert loose["confidence"] < 0.95

    # Une référence bien formée garde sa confiance élevée (projection directe)
    explicit = asyncio.run(parser.parse("Lisons Jean 3:16"))
    assert explicit is not None
    assert explicit["confidence"] >= 0.95


def test_fuzzy_index_finds_approximate_quotes_and_rejects_noise():
    """L'index flou local doit retrouver une citation approximative (mots changés
    par le prédicateur ou l'ASR) et ignorer une phrase sans rapport."""
    from app.services.fuzzy_search import FuzzyVerseIndex

    parser = VerseParserService()
    index = FuzzyVerseIndex(parser.bible_loader.versions["LSG"])

    # Citation approximative de Jean 3:16 (formulation différente de la LSG)
    matches = index.search("dieu a tellement aimé le monde qu'il a donné son fils unique", min_score=0.55)
    assert matches, "La citation approximative devrait être retrouvée"
    top = matches[0]
    assert top["book_abbr"].lower() == "jn" and top["chapter"] == 3 and top["verse"] == 16

    # Phrase du quotidien : aucun verset ne doit sortir
    assert index.search("la réunion de lundi soir est reportée à mardi prochain", min_score=0.55) == []


def test_parser_returns_most_recent_reference_in_buffer():
    """Dans un buffer de parole continue contenant deux références, la plus
    récemment prononcée doit primer (c'est elle que le prédicateur cite)."""
    parser = VerseParserService()
    result = asyncio.run(parser.parse(
        "nous avons lu jean 3:16 tout à l'heure et maintenant philippiens 4:13"
    ))
    assert result is not None
    assert result["reference"] == "Philippiens 4:13"


def test_voice_gate_blocks_silence_and_reports_stats():
    """La barrière vocale doit fermer la porte sur du silence pur."""
    from app.services.vad_service import VoiceGate, vad_available

    if not vad_available():
        pytest.skip("Modèle silero_vad.onnx absent")

    import numpy as np
    gate = VoiceGate(sample_rate=16000)
    silence = np.zeros(4096, dtype=np.int16).tobytes()

    # Plusieurs chunks de silence : tous bloqués (aucune parole, pas de grâce initiale)
    results = [gate.accept(silence) for _ in range(4)]
    assert not any(results)
    assert gate.stats()["chunks_blocked"] == 4


def test_natural_french_phrasings_and_ordinals():
    """Les formulations orales réelles doivent détecter le BON livre, vite."""
    import time
    parser = VerseParserService()

    # Mots de liaison (« au chapitre… au verset… ») — manqué avant le correctif
    r = asyncio.run(parser.parse("dans le livre de jean au chapitre trois au verset seize"))
    assert r is not None and r["reference"] == "Jean 3:16"

    # Ordinal parlé : « première épître de jean » = 1 Jn, PAS Jn
    r = asyncio.run(parser.parse("première épître de jean chapitre quatre verset huit"))
    assert r is not None and r["reference"] == "1 Jean 4:8"

    r = asyncio.run(parser.parse("seconde lettre de pierre chapitre un verset trois"))
    assert r is not None and r["reference"] == "2 Pierre 1:3"

    # Garde de performance : une phrase libre ne doit JAMAIS bloquer la boucle
    # (l'ancien scan par sous-chaîne prenait ~2 600 ms)
    t0 = time.perf_counter()
    asyncio.run(parser.parse("et je crois que nous devons tous prendre au sérieux cette parole ce matin"))
    assert (time.perf_counter() - t0) < 0.8


def test_propresenter_output_initialization():
    driver = ProPresenterOutput(host="10.0.0.1", port=54321, enabled=True)
    
    assert driver.name == "propresenter"
    assert driver.host == "10.0.0.1"
    assert driver.port == 54321
    assert driver.enabled is True
    assert driver.connected is False
