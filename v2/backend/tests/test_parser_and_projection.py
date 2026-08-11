import asyncio
import os

import pytest

from app.outputs.propresenter import ProPresenterOutput
from app.services.verse_parser import VerseParserService, get_standard_abbr


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
        ("Éphésiens deux huit jusqu'au verset neuf", "Éphésiens 2:8-9"),
        ("Genèse chapitre un versets un à trois", "Genèse 1:1-3"),
        ("Luc chapitre dix les versets dix-sept et dix-huit", "Luc 10:17-18"),
        ("Actes chapitre seize seize à dix-neuf", "Actes 16:16-19"),
        ("un Jean chapitre quatre verset dix-sept", "1 Jean 4:17"),
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


@pytest.mark.parametrize(
    ("fragment", "reference"),
    [
        # Fragments courts pris au MILIEU du verset : l'ancien index ne
        # conservait que ses cinq premiers mots.
        ("source corrompue", "Proverbes 25:26"),
        ("cherchant qui il dévorera", "1 Pierre 5:8"),
        ("ta parole est la vérité", "Jean 17:17"),
        # Petite faute de frappe/ASR sur « rugissant ».
        ("lion rugisant", "1 Pierre 5:8"),
        # Fragment traversant Jean 3:16 puis Jean 3:17.
        ("vie éternelle Dieu en effet", "Jean 3:16-17"),
    ],
)
def test_manual_search_finds_fragments_anywhere(fragment, reference):
    parser = VerseParserService()
    results = parser.bible_loader.search_manual_candidates(fragment, 10)

    assert results, fragment
    assert any(result["reference"] == reference for result in results), (
        fragment,
        [result["reference"] for result in results],
    )


def test_manual_search_covers_every_installed_translation_and_rejects_noise():
    parser = VerseParserService()

    # La formulation « tellement aimé » est celle du Français courant et
    # n'existe pas telle quelle dans la LSG. Quand cette traduction est
    # installée, elle doit tout de même conduire à Jean 3:16.
    if "FC" in parser.bible_loader.versions:
        results = parser.bible_loader.search_manual_candidates(
            "dieu a tellement aimé le monde", 6
        )
        assert results and results[0]["reference"] == "Jean 3:16"
        assert results[0]["matched_version"] == "FC"

    assert parser.bible_loader.search_manual_candidates(
        "réunion planning projecteur", 6
    ) == []


def test_parser_returns_most_recent_reference_in_buffer():
    """Dans un buffer de parole continue contenant deux références, la plus
    récemment prononcée doit primer (c'est elle que le prédicateur cite)."""
    parser = VerseParserService()
    result = asyncio.run(parser.parse(
        "nous avons lu jean 3:16 tout à l'heure et maintenant philippiens 4:13"
    ))
    assert result is not None
    assert result["reference"] == "Philippiens 4:13"


def test_curated_philippians_phrase_beats_nearby_strength_verse():
    parser = VerseParserService()
    result = asyncio.run(parser.parse("je peux tout par celui qui me donne la force"))
    assert result is not None
    assert result["reference"] == "Philippiens 4:13"


def test_voice_gate_blocks_silence_and_reports_stats():
    """La barrière vocale doit fermer la porte sur du silence pur."""
    from app.services.vad_service import VoiceGate, vad_available

    if os.environ.get("VERSEPRO_SKIP_NATIVE_VAD_TEST") == "1":
        pytest.skip("Inférence VAD vérifiée sur les runners macOS et Windows de la release")
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


def test_toutes_les_traductions_embarquees_indexent_les_66_livres():
    """Un nom de livre éditorial ne doit pas supprimer un livre du corpus.

    Darby stocke ses noms en anglais et Français courant sous des libellés
    longs (« Première lettre aux Corinthiens »). Avant ce garde-fou, certaines
    éditions perdaient jusqu'à 36 livres lors du chargement.
    """
    parser = VerseParserService()
    # La distribution publique/CI n'embarque légalement que LSG + KJF ; les
    # autres éditions sont présentes sur le poste de développement ou
    # importées par l'utilisateur. Toute édition effectivement disponible doit
    # cependant conserver ses 66 livres.
    assert {"LSG", "KJF"}.issubset(parser.bible_loader.versions)
    for version_id in {"LSG", "NBS", "SEM", "TOB", "KJF", "DBY", "FC"} & set(parser.bible_loader.versions):
        assert len(parser.bible_loader.versions[version_id]) == 66, version_id

    # Les libellés responsables des pertes restent testés même quand les
    # fichiers optionnels ne sont pas distribués sur le runner public.
    assert get_standard_abbr("Habakkuk") == "Hab"
    assert get_standard_abbr("Michée") == "Mi"
    assert get_standard_abbr("Première lettre aux Corinthiens") == "1 Co"
    assert get_standard_abbr("Apocalypse ou Revelation accordee a Jean") == "Ap"


def test_propresenter_output_initialization():
    driver = ProPresenterOutput(host="10.0.0.1", port=54321, enabled=True)
    
    assert driver.name == "propresenter"
    assert driver.host == "10.0.0.1"
    assert driver.port == 54321
    assert driver.enabled is True
    assert driver.connected is False
