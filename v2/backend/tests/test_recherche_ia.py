"""La barre de recherche et l'assistant : ne jamais attendre, ne jamais cacher.

Constaté avant correction :
- /bible/search attendait l'IA jusqu'à 5 s, y compris pour relire le texte de
  « Jean 3:16 » avant de le projeter (3,15 s avec une IA qui répond en 3 s) ;
- sa proposition était ajoutée après au moins douze résultats locaux, puis
  coupée à `limit` : jamais affichée, même pour « zzz qwx blorp » ;
- `min(confiance, 0.95)` sur une échelle 0–100 affichait 95 % pour 40 %.
"""

import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from app import main
from app.api import routes


class _IA:
    """Assistant simulé : répond ce qu'on lui dit, après le délai voulu."""

    enabled = True

    def __init__(self, reponse=None, delai=0.0):
        self.reponse, self.delai, self.appels = reponse, delai, 0

    async def trouver_passage_decrit(self, description):
        self.appels += 1
        await asyncio.sleep(self.delai)
        return self.reponse

    async def detect_bible_reference(self, *args, **kwargs):
        self.appels += 1
        await asyncio.sleep(self.delai)
        return self.reponse


@pytest.fixture
def client(monkeypatch):
    with TestClient(main.app) as c:
        routes._RECHERCHES_RECENTES.clear()
        yield c
        routes._RECHERCHES_RECENTES.clear()


def _avec_ia(monkeypatch, ia):
    monkeypatch.setattr(main, "ai_service", ia)
    return ia


def test_relire_un_verset_n_attend_jamais_l_ia(client, monkeypatch):
    ia = _avec_ia(monkeypatch, _IA({"reference": "Exode 12:7", "confidence": 90}, delai=3))

    debut = time.perf_counter()
    reponse = client.get("/api/v1/bible/search", params={"q": "Jean 3:16", "limit": 1})
    duree = time.perf_counter() - debut

    assert reponse.json()["results"][0]["reference"] == "Jean 3:16"
    assert duree < 1.5, f"{duree:.2f} s : la relecture attendait l'assistant"
    assert ia.appels == 0


def test_la_proposition_de_l_ia_arrive_en_tete(client, monkeypatch):
    _avec_ia(monkeypatch, _IA({"reference": "Exode 12:7", "confidence": 40}))

    reponse = client.get("/api/v1/bible/search/ia", params={"q": "zzz qwx blorp", "limit": 6}).json()

    assert reponse["ia"] == "proposee"
    tete = reponse["results"][0]
    assert tete["reference"] == "Exode 12:7" and tete["source"] == "ai"
    assert tete["confidence"] == 0.40, "40 sur 100 doit s'afficher 40 %, pas 95 %"
    assert tete["requires_review"] is True
    assert len(reponse["results"]) <= 6


def test_une_proposition_deja_trouvee_remonte_et_se_confirme(client, monkeypatch):
    locaux = client.get("/api/v1/bible/search", params={"q": "lumière du monde", "limit": 6}).json()["results"]
    deuxieme = locaux[1]["reference"]
    _avec_ia(monkeypatch, _IA({"reference": deuxieme, "confidence": 80}))

    reponse = client.get("/api/v1/bible/search/ia", params={"q": "lumière du monde", "limit": 6}).json()

    assert reponse["results"][0]["reference"] == deuxieme
    assert reponse["results"][0]["ia_confirme"] is True
    assert [r["reference"] for r in reponse["results"]].count(deuxieme) == 1


def test_un_verset_invente_est_ecarte(client, monkeypatch):
    _avec_ia(monkeypatch, _IA({"reference": "Jean 99:1", "confidence": 95}))

    reponse = client.get("/api/v1/bible/search/ia", params={"q": "une description quelconque"}).json()

    assert reponse["ia"] == "aucune"
    assert all(r.get("source") != "ai" for r in reponse["results"])


def test_une_reference_explicite_ne_consulte_pas_l_ia(client, monkeypatch):
    ia = _avec_ia(monkeypatch, _IA({"reference": "Exode 12:7", "confidence": 90}))

    reponse = client.get("/api/v1/bible/search/ia", params={"q": "Jean 3:16"}).json()

    assert reponse["ia"] == "inutile" and ia.appels == 0


def test_la_fusion_ne_perd_ni_ne_duplique_rien():
    locaux = [{"reference": "A"}, {"reference": "B"}, {"reference": "C"}]

    assert routes.fusionner_suggestion_ia(locaux, None, 2) == locaux[:2]
    fusion = routes.fusionner_suggestion_ia(locaux, {"reference": "Z", "source": "ai"}, 3)
    assert [r["reference"] for r in fusion] == ["Z", "A", "B"]
    fusion = routes.fusionner_suggestion_ia(locaux, {"reference": "C", "source": "ai"}, 3)
    assert [r["reference"] for r in fusion] == ["C", "A", "B"] and fusion[0]["ia_confirme"]
