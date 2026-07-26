"""Le driver ProPresenter parle bien l'API TCP/IP officielle (7.9+).

Un faux ProPresenter répond selon le protocole documenté par Renewed Vision :
un objet JSON par ligne, enveloppé dans {"url", "method", "body"}. On vérifie
que VersePro remplit le Message préparé par l'église plutôt que d'imposer un
habillage, et qu'il refuse de se croire connecté face à un service muet.
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.outputs.propresenter import ProPresenterOutput, _fold


class FauxProPresenter:
    """Serveur TCP minimal qui imite l'API ProPresenter 7."""

    def __init__(self, tokens=("Reference", "Texte"), message_name="VersePro", muet=False):
        self.tokens = list(tokens)
        self.message_name = message_name
        self.muet = muet
        self.recu = []
        self.server = None
        self.port = None

    async def start(self):
        self.server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]
        return self.port

    async def stop(self):
        self.server.close()
        await self.server.wait_closed()

    async def _handle(self, reader, writer):
        while True:
            raw = await reader.readline()
            if not raw:
                break
            requete = json.loads(raw.decode())
            self.recu.append(requete)
            if self.muet:  # imite un service qui écoute mais ne répond pas
                continue
            url = requete.get("url", "")
            if url == "v1/version":
                data = {"name": "ProPresenter", "api_version": "v1"}
            elif url == "v1/messages":
                data = [{
                    "id": {"uuid": "UUID-42", "name": self.message_name, "index": 0},
                    "tokens": [{"name": t} for t in self.tokens],
                }]
            elif "/trigger" in url or "/clear" in url:
                data = {}
            else:
                writer.write((json.dumps({"url": url, "error": "not found"}) + "\r\n").encode())
                await writer.drain()
                continue
            writer.write((json.dumps({"url": url, "data": data}) + "\r\n").encode())
            await writer.drain()


async def _driver(faux, **kwargs):
    port = await faux.start()
    driver = ProPresenterOutput(host="127.0.0.1", port=port, enabled=True, **kwargs)
    return driver


async def _test_connexion_et_decouverte_du_message():
    """Le driver se connecte, vérifie la version et trouve le message de l'église."""
    faux = FauxProPresenter()
    driver = await _driver(faux)
    try:
        assert await driver.connect() is True
        assert driver._message_id == "UUID-42"
        assert driver._message_tokens == ["Reference", "Texte"]
        assert faux.recu[0]["url"] == "v1/version"
    finally:
        await driver.disconnect()
        await faux.stop()


async def _test_verset_envoye_dans_les_jetons_de_leglise():
    """Le verset remplit les jetons du Message : l'habillage reste celui de l'église."""
    faux = FauxProPresenter(tokens=("Reference", "Texte"))
    driver = await _driver(faux)
    try:
        await driver.connect()
        ok = await driver.send_scene({"reference": "Jean 3:16", "text": "Car Dieu a tant aimé le monde"})
        assert ok is True
        declenchement = [r for r in faux.recu if "/trigger" in r.get("url", "")][-1]
        assert declenchement["url"] == "v1/message/UUID-42/trigger"
        assert declenchement["method"] == "POST"
        valeurs = {t["name"]: t["text"]["text"] for t in declenchement["body"]}
        assert valeurs == {"Reference": "Jean 3:16", "Texte": "Car Dieu a tant aimé le monde"}
    finally:
        await driver.disconnect()
        await faux.stop()


async def _test_jetons_nommes_en_francais_avec_accents():
    """Une église qui nomme ses jetons « Référence » et « Verset » est comprise."""
    faux = FauxProPresenter(tokens=("Référence", "Verset"))
    driver = await _driver(faux)
    try:
        await driver.connect()
        await driver.send_scene({"reference": "Psaume 23:1", "text": "L'Éternel est mon berger"})
        declenchement = [r for r in faux.recu if "/trigger" in r.get("url", "")][-1]
        valeurs = {t["name"]: t["text"]["text"] for t in declenchement["body"]}
        assert valeurs == {"Référence": "Psaume 23:1", "Verset": "L'Éternel est mon berger"}
    finally:
        await driver.disconnect()
        await faux.stop()


async def _test_jetons_inconnus_remplis_dans_lordre():
    """Des noms de jetons imprévus sont remplis positionnellement, pas ignorés."""
    faux = FauxProPresenter(tokens=("Ligne1", "Ligne2"))
    driver = await _driver(faux)
    try:
        await driver.connect()
        await driver.send_scene({"reference": "Actes 1:8", "text": "Vous recevrez une puissance"})
        declenchement = [r for r in faux.recu if "/trigger" in r.get("url", "")][-1]
        assert [t["text"]["text"] for t in declenchement["body"]] == [
            "Actes 1:8", "Vous recevrez une puissance"
        ]
    finally:
        await driver.disconnect()
        await faux.stop()


async def _test_message_absent_donne_une_erreur_actionnable():
    """Sans le message préparé, on explique quoi faire au lieu d'échouer en silence."""
    faux = FauxProPresenter(message_name="Annonces")
    driver = await _driver(faux)
    try:
        await driver.connect()
        assert driver._message_id is None
        assert "Annonces" in driver.last_error       # ce qui existe
        assert "VersePro" in driver.last_error       # ce qu'on cherchait
        assert await driver.send_scene({"reference": "Jean 1:1", "text": "..."}) is False
    finally:
        await driver.disconnect()
        await faux.stop()


async def _test_service_muet_nest_pas_pris_pour_propresenter():
    """Un port ouvert ne suffit pas : sans réponse, la pastille ne passe pas au vert."""
    faux = FauxProPresenter(muet=True)
    driver = await _driver(faux)
    try:
        assert await driver.connect() is False
        assert driver.connected is False
        assert "Aucune réponse ProPresenter" in driver.last_error
    finally:
        await faux.stop()


def test_comparaison_de_noms_insensible_aux_accents():
    assert _fold("Référence") == _fold("reference")
    assert _fold("Texte ") == "texte"


# Le dépôt n'utilise pas pytest-asyncio : chaque scénario est exécuté par
# asyncio.run, comme les autres tests du projet.
def test_connexion_et_decouverte_du_message():
    asyncio.run(_test_connexion_et_decouverte_du_message())


def test_verset_envoye_dans_les_jetons_de_leglise():
    asyncio.run(_test_verset_envoye_dans_les_jetons_de_leglise())


def test_jetons_nommes_en_francais_avec_accents():
    asyncio.run(_test_jetons_nommes_en_francais_avec_accents())


def test_jetons_inconnus_remplis_dans_lordre():
    asyncio.run(_test_jetons_inconnus_remplis_dans_lordre())


def test_message_absent_donne_une_erreur_actionnable():
    asyncio.run(_test_message_absent_donne_une_erreur_actionnable())


def test_service_muet_nest_pas_pris_pour_propresenter():
    asyncio.run(_test_service_muet_nest_pas_pris_pour_propresenter())
