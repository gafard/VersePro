"""Un livre absent de la traduction active ne doit pas projeter un écran vide.

Les fichiers sources contiennent « "Chapters": [] » pour Nahum dans la NBS et
la TOB ; 2 et 3 Jean manquent au Français courant. Nahum 1:7 était détecté,
puis projeté avec un texte vide. Le texte vient désormais de la Segond, et
l'écran affiche « LSG » — pas une traduction qui n'a rien fourni.
"""

import pytest
from fastapi.testclient import TestClient

from app import main


@pytest.fixture
def nbs_active():
    with TestClient(main.app) as client:
        loader = main.verse_parser.bible_loader
        if "NBS" not in loader.versions or loader.versions["NBS"].get("na"):
            pytest.skip("NBS absente, ou désormais complète")
        avant = loader.active_version
        loader.active_version = "NBS"
        yield client, loader
        loader.active_version = avant


def test_nahum_en_nbs_projette_le_texte_de_la_segond(nbs_active):
    client, loader = nbs_active

    reponse = client.post("/api/v1/control/project", json={"reference": "Nahum 1:7"})

    assert reponse.status_code == 200
    ecran = main.current_projection_slide
    assert ecran["text"].strip(), "écran vide devant l'assemblée"
    assert ecran["text"] == loader.get_verse_text("Na", 1, 7, version_id="LSG")
    assert ecran["active_version"] == "LSG", "l'écran attribuait le texte à la NBS"


def test_une_version_demandee_ne_se_replie_jamais(nbs_active):
    """La liste des traductions ne doit pas prêter à la NBS un texte de la Segond."""
    _, loader = nbs_active

    assert loader.get_verse_text("Na", 1, 7, version_id="NBS") == ""
    assert loader.version_du_texte("Na", 1, 7) == "LSG"
    assert loader.version_du_texte("Jn", 3, 16) == "NBS"


def test_un_verset_present_garde_la_traduction_active(nbs_active):
    client, _ = nbs_active

    client.post("/api/v1/control/project", json={"reference": "Jean 3:16"})

    assert main.current_projection_slide["active_version"] == "NBS"
