import pytest
import asyncio
from app.services.verse_parser import VerseParserService
from app.services.reference_engine import BibleReferenceEngine
from unittest.mock import AsyncMock, MagicMock

@pytest.fixture
def parser_service():
    # Use a dummy JSON path for tests or real if available, let's just initialize it
    # We might need to mock BibleLoader if it takes time, but it's usually fast.
    return VerseParserService()

@pytest.fixture
def reference_engine(parser_service):
    settings_mock = MagicMock()
    settings_mock.HYBRID_WINDOW_WORDS = 40
    settings_mock.LOCAL_SEMANTIC_ENABLED = False
    
    return BibleReferenceEngine(
        verse_parser=parser_service,
        semantic_service=None,
        verse_graph=None,
        ai_service=None,
        settings=settings_mock,
        db_service=None,
        sante_transcription=None
    )

@pytest.mark.anyio
async def test_incremental_parser_book_only(reference_engine):
    # Test just the book
    text = "prenons dans le livre de jean"
    result = await reference_engine.process(text, is_final=False, generation=1)
    
    assert result is not None
    assert result["type"] == "incremental_reference"
    assert result["payload"]["book_abbr"] == "Jn"
    assert result["payload"]["chapter"] is None
    assert result["payload"]["verse"] is None

@pytest.mark.anyio
async def test_livre_et_chapitre_sont_une_VRAIE_detection(reference_engine):
    """« Jean chapitre 3 » n'est pas une piste : c'est un passage ouvert.

    L'étage explicite le reconnaît comme `chapter_candidate`, ce qui vaut bien
    mieux qu'un badge informatif — cette détection pose aussi l'ancre
    VerseGraph, qui permettra de rattacher les allusions des minutes suivantes.
    """
    text = "prenons dans le livre de jean chapitre 3"
    result = await reference_engine.process(text, is_final=False, generation=2)

    assert result is not None
    assert result["type"] == "reference_detected"
    assert result["payload"]["book_abbr"] == "Jn"
    assert result["payload"]["chapter"] == 3
    assert result["payload"]["detection_method"] == "chapter_candidate"


@pytest.mark.anyio
async def test_une_reference_complete_sort_DES_le_partiel(reference_engine):
    """Ne pas attendre la fin de l'énoncé quand la référence est déjà dite.

    Le prédicateur continue de parler plusieurs secondes après avoir annoncé
    son verset. Attendre le « final » ajouterait tout ce délai avant l'écran —
    c'est exactement ce que faisait le moteur avant cette correction : l'étage
    incrémental répondait en premier et court-circuitait l'explicite.
    """
    text = "c'est vraiment la parole ouvrons ensemble romains chapitre huit verset vingt-huit"
    result = await reference_engine.process(text, is_final=False, generation=4)

    assert result is not None
    assert result["type"] == "reference_detected"
    assert result["payload"]["reference"] == "Romains 8:28"

@pytest.mark.anyio
async def test_final_parser_full_verse(reference_engine):
    # Test full explicit citation when final
    text = "prenons dans le livre de jean chapitre 3 verset 16"
    result = await reference_engine.process(text, is_final=True, generation=3)
    
    assert result is not None
    assert result["type"] == "reference_detected"
    payload = result["payload"]
    assert payload["book_abbr"] == "Jn"
    assert payload["chapter"] == 3
    assert payload["verse_start"] == 16
    assert payload["detection_method"] == "explicit"
