"""Routes du moteur ASR local — le parcours de l'assistant de premier lancement.

Le bénévole ouvre VersePro pour la première fois, choisit « Mode recommandé »
et attend que le modèle se télécharge. Deux routes portent tout ce moment :

    GET  /nemotron/status     l'assistant interroge l'état
    POST /nemotron/download   il lance le téléchargement

La seconde levait `NameError: name 'asyncio' is not defined` — ce module
s'importe fonction par fonction dans routes.py, et celle-ci l'avait oublié.
L'assistant recevait une erreur 500 et le bénévole restait devant une barre
de progression qui ne démarrait jamais.

Ce genre de défaut ne se voit qu'à l'exécution : ni l'analyse statique ni la
compilation ne l'attrapent. D'où ces tests, qui APPELLENT les routes.
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("VERSEPRO_TESTING", "1")

from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_le_statut_repond(client):
    reponse = client.get("/api/v1/nemotron/status")
    assert reponse.status_code == 200
    donnees = reponse.json()
    assert "installed" in donnees
    assert "downloading" in donnees


def test_asr_prepare_accepte_un_corps_vide(client):
    """L'onboarding peut déclencher la préparation sans payload obligatoire."""
    reponse = client.post("/api/v1/asr/prepare")
    assert reponse.status_code == 200, reponse.text
    assert reponse.json().get("status") in {"preparing", "ready"}


def test_le_telechargement_demarre_sans_lever(client):
    """Le test qui aurait attrapé le NameError.

    On ne vérifie pas qu'un fichier de 716 Mo arrive — seulement que la route
    répond au lieu de casser. C'est exactement là qu'était le bug."""
    reponse = client.post("/api/v1/nemotron/download")
    assert reponse.status_code == 200, reponse.text
    assert reponse.json().get("status") == "started"


def test_le_telechargement_rend_l_etat_du_modele(client):
    """L'assistant a besoin de savoir où en est le téléchargement.

    Sans ces champs dans la réponse, il devrait attendre le prochain sondage
    avant d'afficher quoi que ce soit."""
    donnees = client.post("/api/v1/nemotron/download").json()
    for champ in ("ready", "downloading", "download_progress", "model_size_mb"):
        assert champ in donnees, f"champ « {champ} » absent de la réponse"


def test_un_service_absent_donne_503_et_pas_500(client, monkeypatch):
    """Un service non initialisé doit donner un refus lisible.

    503 dit « indisponible pour l'instant » ; 500 dit « le logiciel est
    cassé ». L'assistant peut proposer de réessayer sur le premier."""
    import app.main as M
    monkeypatch.setattr(M, "nemotron_service", None)
    reponse = client.post("/api/v1/nemotron/download")
    assert reponse.status_code == 503
