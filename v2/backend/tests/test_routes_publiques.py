"""« Public » veut dire lecture seule. Ce test le fait respecter.

CE QUI S'EST PASSÉ. PUBLIC_PREFIXES rend certaines routes accessibles sans
jeton, pour que les écrans de diffusion — ouverts sur le vidéoprojecteur,
dans un onglet qui n'a jamais vu le jeton de session — puissent charger leurs
polices, leurs images et le catalogue de bibles. Son commentaire promettait
« un préfixe n'ouvre qu'un GET ».

La règle, elle, ne regardait que le chemin. Une route écrivait sous un préfixe
public : POST /api/v1/bibles/select, qui change la traduction projetée devant
l'assemblée. Constaté avec un jeton de session configuré, comme dans
l'application empaquetée :

    GET  /api/v1/settings        sans jeton -> 401
    POST /api/v1/bibles/select   sans jeton -> 200   {"active": "XYZ"}

La version n'était même pas validée : « XYZ » était acceptée comme version
active.

Ce fichier vérifie la règle ET la table des routes réelle. Le premier test
échouera le jour où quelqu'un ajoutera une route d'écriture sous un préfixe
public — c'est précisément ainsi que celle-ci était arrivée là.
"""

import pytest

from app.core import security
from app.core.config import settings
from app.core.security import PUBLIC_PATHS, PUBLIC_PREFIXES, http_request_allowed

ECRITURES = {"POST", "PUT", "PATCH", "DELETE"}


class _Requete:
    """Requête minimale, le temps d'interroger la règle d'accès."""

    def __init__(self, chemin: str, methode: str = "GET", hote: str = "127.0.0.1"):
        self.url = type("U", (), {"path": chemin})()
        self.method = methode
        self.headers = {}
        self.query_params = {}
        self.client = type("C", (), {"host": hote})()


@pytest.fixture
def jeton_configure(monkeypatch):
    """Comme dans l'application empaquetée, où Tauri génère un jeton."""
    monkeypatch.setattr(settings, "API_TOKEN", "jeton-de-test")
    monkeypatch.delenv("VERSEPRO_SESSION_TOKEN", raising=False)


def _est_public(chemin: str) -> bool:
    return chemin in PUBLIC_PATHS or chemin.startswith(PUBLIC_PREFIXES)


def test_aucune_route_publique_n_ecrit_sans_jeton(jeton_configure):
    """Parcourt la VRAIE table des routes, pas une liste écrite à la main."""
    from app.main import app

    ouvertes = []
    for route in app.routes:
        chemin = getattr(route, "path", "")
        methodes = getattr(route, "methods", None) or set()
        if not _est_public(chemin):
            continue
        for methode in methodes & ECRITURES:
            if http_request_allowed(_Requete(chemin, methode)):
                ouvertes.append(f"{methode} {chemin}")

    assert not ouvertes, (
        "des routes publiques acceptent une écriture sans jeton : "
        f"{ouvertes}. Un chemin public est destiné aux écrans de diffusion, "
        "qui ne font que lire."
    )


def test_la_selection_de_bible_exige_le_jeton(jeton_configure):
    assert not http_request_allowed(_Requete("/api/v1/bibles/select", "POST"))


def test_les_ecrans_de_diffusion_lisent_toujours_sans_jeton(jeton_configure):
    """La restriction ne doit pas casser ce pour quoi les chemins sont publics."""
    for chemin in ("/output", "/stage", "/follow", "/fonts/geist.woff2",
                   "/api/v1/bibles/catalogue", "/overlay.png"):
        assert http_request_allowed(_Requete(chemin, "GET")), chemin


def test_une_version_inconnue_est_refusee():
    """« XYZ » n'est pas une bible, et ne doit pas devenir la version active."""
    from fastapi.testclient import TestClient
    from app import main
    from app.services.verse_parser import VerseParserService

    main.verse_parser = VerseParserService()
    avant = main.verse_parser.bible_loader.active_version
    client = TestClient(main.app)

    reponse = client.post("/api/v1/bibles/select", json={"version": "XYZ"})

    assert reponse.status_code == 422
    assert main.verse_parser.bible_loader.active_version == avant
