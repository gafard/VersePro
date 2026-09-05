import pytest
from fastapi.testclient import TestClient
from app.main import app, current_projection_slide
from app.services.osc_service import OSCService

@pytest.fixture
def client():
    # Assurons-nous que l'application est bien initialisée
    with TestClient(app) as c:
        yield c

@pytest.fixture(autouse=True)
def cleanup_projection():
    yield
    # Réinitialiser après chaque test de contrôle pour ne pas interférer avec les autres tests
    from app.main import current_projection_slide
    current_projection_slide.clear()
    current_projection_slide.update({
        "text": "En attente d'affichage...",
        "reference": "",
        "background": "black",
        "theme": "classic",
        "translations": {}
    })

def test_http_control_project_success(client):
    response = client.post("/api/v1/control/project", json={
        "reference": "Jean 3:16",
        "text": "Dieu a tant aime le monde"
    })
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    # Le parser ou la valeur par défaut résout la référence
    assert "Jean 3:16" in data["reference"]

def test_http_control_clear(client):
    response = client.post("/api/v1/control/clear")
    assert response.status_code == 200
    assert response.json()["success"] is True


def test_diffusion_direct_desactive_le_mode_dimanche_sur(client):
    """Le mode automatique ne peut pas rester protégé par le verrou dimanche."""
    client.post("/api/v1/settings", json={"auto_send": False, "sunday_safe_mode": True})
    response = client.post("/api/v1/settings", json={"auto_send": True})
    assert response.status_code == 200
    data = response.json()
    assert data["auto_send"] is True
    assert data["sunday_safe_mode"] is False

def test_http_control_status(client):
    # Projeter un élément
    client.post("/api/v1/control/project", json={
        "reference": "Jn 3:16",
        "text": "Dieu a tant aime le monde"
    })
    
    response = client.get("/api/v1/control/status")
    assert response.status_code == 200
    data = response.json()
    assert data["on_air"] is True
    assert "Jean 3:16" in data["reference"]

def test_http_control_navigation(client):
    # Projeter Jean 3:16
    client.post("/api/v1/control/project", json={
        "reference": "Jean 3:16"
    })
    
    # Suivant (Jean 3:17)
    response_next = client.post("/api/v1/control/next")
    assert response_next.status_code == 200
    
    # Précédent (Jean 3:16)
    response_prev = client.post("/api/v1/control/prev")
    assert response_prev.status_code == 200
    assert response_prev.json()["success"] is True
    assert "3:16" in response_prev.json()["reference"]


def test_manual_reference_rejects_invalid_input(client):
    response = client.post(
        "/api/v1/references/send",
        json={"reference": "ceci-n-est-pas-un-verset"},
    )
    assert response.status_code == 422
    assert "invalide" in response.json()["detail"]


def test_osc_service_init():
    service = OSCService()
    assert service.server is None
    assert service.client is None
