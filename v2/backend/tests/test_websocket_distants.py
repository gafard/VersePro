import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
import app.main as main
from app.core.config import settings
from app.services.deepgram_service import DeepgramService
from app.services.verse_parser import VerseParserService
from app.services.vosk_service import VoskService


class FakeDeepgramSession:
    def __init__(self, callback):
        self.callback = callback
        self.is_active = True
        self.sent = 0

    async def send_audio(self, data):
        self.sent += 1
        if self.sent == 1:
            result = type("Result", (), {
                "channel": type("Channel", (), {
                    "alternatives": [type("Alternative", (), {"transcript": "Jean 3:16"})()]
                })(),
                "is_final": True,
            })()
            await self.callback(result)

    async def close(self):
        self.is_active = False


class FakeDeepgramService:
    async def create_session(self, callback):
        return FakeDeepgramSession(callback)

    async def disconnect(self):
        return None

@pytest.fixture(autouse=True)
def configure_api_token(monkeypatch):
    monkeypatch.setattr(settings, "API_TOKEN", "secure-integration-token")
    yield

@pytest.fixture(autouse=True)
def init_main_services():
    # Initialisation rapide des services requis pour le WebSocket d'audio et d'affichage
    main.deepgram_service = DeepgramService("fake-key")
    main.verse_parser = VerseParserService()
    main.vosk_service = VoskService()
    if not main.output_manager:
        main.output_manager = main.OutputManager()
        import asyncio
        asyncio.run(main.output_manager.initialize_defaults())
    yield
    main.deepgram_service = None
    main.verse_parser = None
    main.vosk_service = None

def test_remote_projection_ws_is_public():
    # L'écran d'affichage est public : même à distance (ex: 203.0.113.10), il doit se connecter sans token.
    remote_client = TestClient(main.app, client=("203.0.113.10", 49152))
    with remote_client.websocket_connect("/ws/output") as websocket:
        data = websocket.receive_json()
        assert "text" in data
        assert "reference" in data

def test_remote_audio_ws_requires_token_and_rejects_invalid():
    remote_client = TestClient(main.app, client=("203.0.113.10", 49152))
    # Tentative sans token
    with pytest.raises(WebSocketDisconnect) as exc_missing:
        with remote_client.websocket_connect("/ws/audio"):
            pass
    assert exc_missing.value.code == 1008

    # Tentative avec mauvais token
    with pytest.raises(WebSocketDisconnect) as exc_invalid:
        with remote_client.websocket_connect("/ws/audio?token=wrong-token"):
            pass
    assert exc_invalid.value.code == 1008

def test_remote_audio_ws_accepts_valid_token_query_param():
    remote_client = TestClient(main.app, client=("203.0.113.10", 49152))
    # Connexion valide avec token dans l'URL
    with remote_client.websocket_connect("/ws/audio?token=secure-integration-token") as websocket:
        # Reçoit le statut initial
        data = websocket.receive_json()
        assert data["type"] == "ai_status"

def test_remote_audio_ws_accepts_valid_token_header():
    remote_client = TestClient(main.app, client=("203.0.113.10", 49152))
    # Connexion avec token dans l'en-tête Authorization
    headers = {"Authorization": "Bearer secure-integration-token"}
    with remote_client.websocket_connect("/ws/audio", headers=headers) as websocket:
        data = websocket.receive_json()
        assert data["type"] == "ai_status"


def test_remote_audio_stream_reaches_production_parser(monkeypatch):
    """Intégration distante: octets audio -> ASR -> transcript -> référence."""
    monkeypatch.setattr(main, "deepgram_service", FakeDeepgramService())
    monkeypatch.setattr(settings, "SUNDAY_SAFE_MODE", True)
    remote_client = TestClient(main.app, client=("203.0.113.10", 49152))

    with remote_client.websocket_connect(
        "/ws/audio?token=secure-integration-token&engine=deepgram"
    ) as websocket:
        assert websocket.receive_json()["type"] == "ai_status"
        status = websocket.receive_json()
        assert status == {"type": "status_update", "status": "connected", "mode": "deepgram"}
        websocket.send_bytes(b"\x00\x00" * 4096)
        transcript = websocket.receive_json()
        detected = websocket.receive_json()

    assert transcript["type"] == "transcript"
    assert transcript["text"] == "Jean 3:16"
    assert detected["type"] == "reference_detected"
    assert detected["reference"]["reference"] == "Jean 3:16"
    assert detected["reference"]["auto_projected"] is False
