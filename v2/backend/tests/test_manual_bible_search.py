"""Contrat HTTP de la recherche biblique saisie par l'opérateur."""

from fastapi.testclient import TestClient

from app.main import app


def test_palette_finds_short_fragment_from_middle_of_verse():
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/bible/search",
            params={"q": "source corrompue", "limit": 6},
        )

    assert response.status_code == 200
    results = response.json()["results"]
    assert results
    assert results[0]["reference"] == "Proverbes 25:26"
    assert results[0]["detection_method"] == "manual_exact"
    assert results[0]["confidence"] == 1.0


def test_palette_returns_cross_verse_passage_without_projecting_it():
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/bible/search",
            params={"q": "vie éternelle Dieu en effet", "limit": 6},
        )

    assert response.status_code == 200
    results = response.json()["results"]
    assert any(result["reference"] == "Jean 3:16-17" for result in results)


def test_palette_caps_result_limit():
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/bible/search",
            params={"q": "amour", "limit": 5000},
        )

    assert response.status_code == 200
    assert len(response.json()["results"]) <= 20

