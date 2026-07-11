import asyncio

import pytest

from app.services.propresenter_service import ProPresenterService
from app.services.verse_parser import VerseParserService


@pytest.mark.parametrize(
    ("text", "reference"),
    [
        ("Lisons Jean 3:16", "Jn 3:16"),
        ("Mt 5:1-12", "Mt 5:1-12"),
        ("1 Co 13:4-8", "1 Co 13:4-8"),
        ("Ésaïe chapitre 53", "És 53"),
        ("Dieu est amour", "1 Jn 4:8"),
        ("L'Éternel est mon berger", "Ps 23:1"),
        ("Psaume cent dix neuf verset cent soixante seize", "Ps 119:176"),
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

    loose = asyncio.run(parser.parse("Jean trois seize"))
    assert loose is not None
    assert loose["reference"] == "Jn 3:16"
    assert loose["confidence"] < 0.95

    # Une référence bien formée garde sa confiance élevée (projection directe)
    explicit = asyncio.run(parser.parse("Lisons Jean 3:16"))
    assert explicit is not None
    assert explicit["confidence"] >= 0.95


def test_propresenter_reference_normalization_accepts_string_and_dict():
    service = ProPresenterService()

    assert service._normalize_reference("Jn 3:16")["reference"] == "Jn 3:16"

    normalized = service._normalize_reference({
        "reference": "Ps 23:1",
        "text": "L'Éternel est mon berger",
        "version": "LSG",
    })

    assert normalized["reference"] == "Ps 23:1"
    assert normalized["text"] == "L'Éternel est mon berger"
    assert normalized["version"] == "LSG"
