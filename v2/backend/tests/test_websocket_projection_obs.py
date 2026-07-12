from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import app.main as main
from app.core.config import settings
from app.core.security import websocket_allowed


@pytest.fixture(autouse=True)
def reset_projection_state():
    """Isole l'état global utilisé par le stream d'affichage."""
    if not main.output_manager:
        main.output_manager = main.OutputManager()
        import asyncio
        asyncio.run(main.output_manager.initialize_defaults())
        
    main.current_projection_slide = {
        "text": "En attente d'affichage...",
        "reference": "",
        "background": "black",
        "translations": {},
    }
    if main.output_manager and "browser" in main.output_manager.outputs:
        main.output_manager.outputs["browser"].connections.clear()
    yield
    if main.output_manager and "browser" in main.output_manager.outputs:
        main.output_manager.outputs["browser"].connections.clear()


def test_projection_websocket_sends_current_slide_on_connect():
    client = TestClient(main.app)

    with client.websocket_connect("/ws/output") as websocket:
        data = websocket.receive_json()

    assert data["text"] == "En attente d'affichage..."
    assert data["reference"] == ""
    assert data["background"] == "black"


def test_projection_websocket_receives_rest_broadcast_with_translations():
    client = TestClient(main.app)

    with client.websocket_connect("/ws/output") as websocket:
        websocket.receive_json()

        response = client.post(
            "/api/v1/project",
            json={
                "reference": "Jn 3:16",
                "text": "Car Dieu a tant aimé le monde...",
                "background": "transparent",
                "translations": {"EN": "For God so loved the world..."},
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["slide"]["reference"] == "Jn 3:16"
        assert payload["slide"]["translations"]["EN"] == "For God so loved the world..."

        streamed = websocket.receive_json()

    assert streamed["reference"] == "Jn 3:16"
    assert streamed["text"] == "Car Dieu a tant aimé le monde..."
    assert streamed["background"] == "transparent"
    assert streamed["translations"]["EN"] == "For God so loved the world..."


def test_obs_browser_source_redirects_to_output():
    remote_client = TestClient(main.app, client=("203.0.113.10", 50000))

    response = remote_client.get("/obs", follow_redirects=False)

    assert response.status_code in (302, 307)
    assert "/output" in response.headers["location"]


def test_output_page_uses_output_stream():
    remote_client = TestClient(main.app, client=("203.0.113.10", 50000))

    response = remote_client.get("/output")

    assert response.status_code == 200
    assert "/ws/output" in response.text


def test_remote_http_projection_control_requires_token():
    remote_client = TestClient(main.app, client=("203.0.113.10", 50000))

    response = remote_client.post(
        "/api/v1/project",
        json={"reference": "Jn 3:16", "text": "Forçage distant"},
    )

    assert response.status_code == 401


def test_remote_audio_websocket_is_rejected_without_token():
    remote_client = TestClient(main.app, client=("203.0.113.10", 50000))

    with pytest.raises(WebSocketDisconnect) as exc:
        with remote_client.websocket_connect("/ws/audio"):
            pass

    assert exc.value.code == 1008


def test_remote_websocket_security_accepts_valid_token(monkeypatch):
    monkeypatch.setattr(settings, "API_TOKEN", "secret-token")
    fake_websocket = SimpleNamespace(
        client=SimpleNamespace(host="203.0.113.10"),
        headers={},
        query_params={"token": "secret-token"},
        url=SimpleNamespace(path="/ws/audio"),
    )

    assert websocket_allowed(fake_websocket) is True
