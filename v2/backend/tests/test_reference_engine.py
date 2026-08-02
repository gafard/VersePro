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
async def test_incremental_parser_book_and_chapter(reference_engine):
    # Test book + chapter
    text = "prenons dans le livre de jean chapitre 3"
    result = await reference_engine.process(text, is_final=False, generation=2)
    
    assert result is not None
    assert result["type"] == "incremental_reference"
    assert result["payload"]["book_abbr"] == "Jn"
    assert result["payload"]["chapter"] == 3
    assert result["payload"]["verse"] is None

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
