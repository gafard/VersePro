"""Préparation et envoi à l'antenne — le geste fondamental d'une régie.

Avant ces routes, valider une détection l'envoyait DIRECTEMENT devant
l'assemblée. L'opérateur découvrait le rendu en même temps qu'elle, et n'avait
aucun moyen de rattraper un verset mal coupé ou un habillage inadapté.

La garantie que ces tests protègent tient en une phrase : **ce qui est en
préparation n'atteint jamais la salle**. Si elle tombe, la fonction devient
pire qu'absente — un opérateur qui croit préparer projetterait en direct.
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("VERSEPRO_TESTING", "1")

from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _antenne(client):
    return client.get("/api/v1/projection/current").json().get("reference")


# ── L'isolation, qui est tout ────────────────────────────────────────────────

def test_preparer_ne_touche_pas_l_antenne(client):
    client.post("/api/v1/references/send", json={"reference": "Jean 3:16"})
    avant = _antenne(client)

    client.post("/api/v1/projection/preview", json={"reference": "Psaumes 23:1"})

    assert _antenne(client) == avant, (
        "la préparation est arrivée à l'écran de salle — l'assemblée a vu ce que "
        "l'opérateur montait"
    )


def test_envoyer_bascule_la_preparation_a_l_antenne(client):
    client.post("/api/v1/references/send", json={"reference": "Jean 3:16"})
    client.post("/api/v1/projection/preview", json={"reference": "Psaumes 23:1"})

    reponse = client.post("/api/v1/projection/take")
    assert reponse.status_code == 200
    assert _antenne(client) == "Psaumes 23:1"


def test_envoyer_sans_rien_preparer_est_refuse(client):
    """Un « take » à vide effacerait l'écran par surprise."""
    from app import main
    main.preview_slide = {}
    assert client.post("/api/v1/projection/take").status_code == 409


# ── Contenu de la préparation ────────────────────────────────────────────────

def test_un_passage_est_prepare_verset_par_verset(client):
    """L'opérateur doit voir le découpage AVANT d'envoyer, pas le découvrir."""
    reponse = client.post("/api/v1/projection/preview",
                          json={"reference": "Romains 8:28-32"})
    versets = reponse.json().get("verses") or []
    assert len(versets) == 5
    assert versets[0]["n"] == 28
    assert all(v["text"].strip() for v in versets)


def test_la_preparation_se_relit_sans_etre_envoyee(client):
    client.post("/api/v1/projection/preview", json={"reference": "Jean 1:1"})
    monte = client.get("/api/v1/projection/preview").json()
    assert monte.get("reference") == "Jean 1:1"
    assert _antenne(client) != "Jean 1:1"


def test_on_peut_preparer_dans_une_autre_version(client):
    """« Prépare-moi ça dans la King James » : visible avant l'antenne."""
    lsg = client.post("/api/v1/projection/preview",
                      json={"reference": "Jean 3:16", "version": "LSG"}).json()["text"]
    kjf = client.post("/api/v1/projection/preview",
                      json={"reference": "Jean 3:16", "version": "KJF"}).json()["text"]
    assert lsg and kjf and lsg != kjf


def test_une_version_inconnue_est_refusee_en_preparation(client):
    reponse = client.post("/api/v1/projection/preview",
                          json={"reference": "Jean 3:16", "version": "XYZ"})
    assert reponse.status_code == 422


def test_une_reference_invalide_est_refusee(client):
    assert client.post("/api/v1/projection/preview",
                       json={"reference": "Hezekiah 9:99"}).status_code == 422
