"""Projeter un verset dans une AUTRE version que la version active.

Le cas réel : un verset est à l'écran, le pasteur demande « lisons-le dans la
Semeur ». L'opérateur ouvre le panneau de comparaison, clique sur SEM.

Ce que faisait le code avant : `parse()` rend toujours le texte de la version
ACTIVE, et le champ `version` de la requête était accepté puis ignoré. Le
panneau affichait bien la Semeur, l'interface marquait « ★ À l'antenne » sur
la Semeur — et l'assemblée continuait de lire la Segond.

Une fonction qui affirme le contraire de ce qu'elle fait est pire qu'une
fonction absente : l'opérateur ne peut pas voir l'écran de projection depuis
sa régie, il croit son interface.
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("VERSEPRO_TESTING", "1")

from fastapi.testclient import TestClient

from app.main import app

REFERENCE = "Jean 3:16"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _projeter(client, version=None):
    corps = {"reference": REFERENCE}
    if version:
        corps["version"] = version
    reponse = client.post("/api/v1/references/send", json=corps)
    assert reponse.status_code == 200, reponse.text
    return reponse.json().get("text", "")


def test_le_texte_projete_suit_la_version_demandee(client):
    """Le cœur du sujet : deux versions, deux textes RÉELLEMENT différents."""
    lsg = _projeter(client, "LSG")
    kjf = _projeter(client, "KJF")
    assert lsg and kjf
    assert lsg != kjf, "la version demandée n'a pas changé le texte projeté"


def test_ce_qui_est_projete_est_ce_que_la_comparaison_annonce(client):
    """Le panneau de comparaison et l'écran doivent dire la même chose.

    C'est exactement là que le mensonge se produisait : deux chemins de code
    distincts, l'un honorant la version, l'autre non."""
    apercus = client.get("/api/v1/bible/search",
                         params={"q": REFERENCE, "limit": 1}).json()["results"][0]["translations"]
    for version in ("LSG", "SEM", "KJF"):
        if version not in apercus:
            continue
        assert _projeter(client, version).strip() == apercus[version].strip(), (
            f"{version} : l'écran ne montre pas ce que la comparaison annonce"
        )


def test_sans_version_demandee_rien_ne_change(client):
    """Le chemin normal — une détection ordinaire — reste sur la version active."""
    assert _projeter(client) == _projeter(client, "LSG")


def test_une_version_inconnue_est_refusee(client):
    """Mieux vaut un refus net qu'un repli silencieux sur la Segond.

    Un repli laisserait l'opérateur croire qu'il a changé de version."""
    reponse = client.post("/api/v1/references/send",
                          json={"reference": REFERENCE, "version": "XYZ"})
    assert reponse.status_code == 422
    assert "XYZ" in reponse.json().get("detail", "")


def test_un_verset_absent_d_une_traduction_ne_vide_pas_l_ecran(client):
    """Les numérotations diffèrent d'une traduction à l'autre.

    Si le verset demandé n'existe pas dans la version choisie, on garde le
    texte déjà résolu : un écran vide en plein culte serait le pire résultat."""
    reponse = client.post("/api/v1/references/send",
                          json={"reference": "Psaumes 23:1", "version": "KJF"})
    assert reponse.status_code == 200
    assert reponse.json().get("text", "").strip()
