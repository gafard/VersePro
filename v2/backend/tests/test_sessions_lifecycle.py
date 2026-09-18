import pytest
from app.services.database import get_database


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_session_lifecycle_and_verse_count():
    db = get_database()
    await db.connect()

    # 1. Création d'une session
    session_id = await db.create_session("Culte de Test")
    assert session_id > 0

    # 2. Récupération de la session
    session = await db.get_session(session_id)
    assert session is not None
    assert session["name"] == "Culte de Test"
    assert session["verse_count"] == 0

    # 3. Ajout de versets rattachés à cette session
    v1_id = await db.add_detected_verse(
        {
            "reference": "Jean 3:16",
            "book": "Jean",
            "book_abbr": "Jn",
            "chapter": 3,
            "verse_start": 16,
            "text": "Car Dieu a tant aimé le monde...",
            "version": "LSG",
        },
        session_id=session_id,
        confidence=99,
        source="local",
    )
    assert v1_id > 0

    v2_id = await db.add_detected_verse(
        {
            "reference": "Psaumes 23:1",
            "book": "Psaumes",
            "book_abbr": "Ps",
            "chapter": 23,
            "verse_start": 1,
            "text": "L'Éternel est mon berger...",
            "version": "LSG",
        },
        session_id=session_id,
        confidence=95,
        source="local",
    )
    assert v2_id > 0

    # 4. Vérification que get_session et get_recent_sessions comptent dynamiquement les versets
    session_after = await db.get_session(session_id)
    assert session_after["verse_count"] == 2

    recent = await db.get_recent_sessions(limit=5)
    matching = [s for s in recent if s["id"] == session_id]
    assert len(matching) == 1
    assert matching[0]["verse_count"] == 2

    # 5. Transcription cumulée
    await db.append_to_session_transcript(session_id, "Bonjour bien-aimés dans le Seigneur.")
    await db.append_to_session_transcript(session_id, "Ouvrons la Parole dans Jean 3 verset 16.")
    session_transcript = await db.get_session(session_id)
    assert "Jean 3 verset 16" in session_transcript["transcript"]

    # 6. Clôture de la session
    await db.end_session(session_id)
    ended_session = await db.get_session(session_id)
    assert ended_session["ended_at"] is not None
    assert ended_session["verse_count"] == 2

    await db.disconnect()
