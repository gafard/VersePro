import asyncio
import time
import uuid
from typing import Dict, Any, Set
from fastapi import WebSocket
from loguru import logger
from .base import BaseOutput

class BrowserOutput(BaseOutput):
    """
    Driver de sortie pour les clients navigateurs connectés via WebSockets (ex: /ws/output).
    """
    def __init__(self):
        super().__init__(name="browser", enabled=True)
        self.connections: Set[WebSocket] = set()
        # Écrans de PRÉPARATION : la console de l'opérateur. Séparés des écrans
        # de salle, jamais atteints par une projection à l'antenne.
        self.preview_connections: Set[WebSocket] = set()
        self.receipts = {}
        self.preview_scene: Dict[str, Any] = {}
        self.current_scene: Dict[str, Any] = {
            "scene_id": uuid.uuid4().hex,
            "type": "scripture",
            "text": "En attente d'affichage...",
            "reference": "",
            "background": "black",
            "theme": "presentation",
            "translations": {}
        }

    def _scene_initiale(self) -> Dict[str, Any]:
        """Scène d'accueil enrichie des réglages d'affichage du moment.

        Tant qu'aucun verset n'a été projeté, la scène par défaut ne portait ni
        habillage ni style : un écran allumé avant le culte, ou rouvert après un
        redémarrage du moteur, restait nu jusqu'à la première projection. Les
        réglages, eux, sont connus dès le démarrage — autant les envoyer.
        """
        scene = dict(self.current_scene)
        try:
            from ..core.config import settings
            from ..services import overlay_store, background_store
            scene.setdefault("style", settings.PROJECTION_STYLE)
            scene.setdefault("show_version", settings.SHOW_BIBLE_VERSION)
            scene.setdefault("active_version", settings.BIBLE_VERSION)
            scene["backdrop"] = background_store.resolve_background(settings)
            if not scene.get("reference"):
                scene["overlay"] = overlay_store.resolve_overlay(
                    settings.PROJECTION_STYLE, settings.OVERLAY_ZONES, settings.OVERLAY_SHAPES
                )
        except Exception as exc:  # un écran nu vaut mieux qu'un écran en erreur
            logger.debug(f"Scène initiale sans habillage : {exc}")
        return scene

    async def register_connection(self, websocket: WebSocket, canal: str = "program"):
        """Enregistre un écran et lui envoie la scène de SON canal.

        Deux canaux, et c'est toute la différence entre un détecteur et une
        régie :

          • `program` — ce que l'assemblée voit. Tous les écrans de salle, et
            c'est le seul canal que les autres sorties (NDI, vMix, OBS…) suivent.
          • `preview`  — ce que l'opérateur PRÉPARE. Visible de lui seul, sur sa
            console, tant qu'il ne l'a pas envoyé à l'antenne.

        Sans cette séparation, valider une détection l'envoyait directement
        devant l'assemblée : aucun moyen de voir à quoi ressemblerait l'écran
        avant qu'il y soit.
        """
        if canal == "preview":
            self.preview_connections.add(websocket)
            scene = self.preview_scene or self._scene_initiale()
        else:
            self.connections.add(websocket)
            scene = self._scene_initiale()
            self.receipts[websocket] = {"client_id": uuid.uuid4().hex[:8], "scene_id": scene.get("scene_id"), "sent_at": time.time(), "rendered_at": None, "surface": "écran"}
        try:
            await websocket.send_json(scene)
        except Exception as e:
            self.unregister_connection(websocket)
            logger.debug(f"Erreur envoi initial client navigateur: {e}")

    def unregister_connection(self, websocket: WebSocket):
        """Retire un client d'affichage déconnecté, quel que soit son canal"""
        self.connections.discard(websocket)
        self.preview_connections.discard(websocket)
        self.receipts.pop(websocket, None)

    def acknowledge(self, websocket, message):
        receipt = self.receipts.get(websocket)
        if not receipt or message.get("type") != "rendered" or not receipt.get("scene_id"):
            return
        if message.get("scene_id") == receipt["scene_id"]:
            receipt["rendered_at"] = time.time()
            surface = message.get("surface", "écran")
            receipt["surface"] = surface if surface in {"output", "obs", "stage", "follow", "companion"} else "écran"

    def delivery_status(self):
        now = time.time()
        clients = []
        for connection, receipt in self.receipts.items():
            if connection not in self.connections:
                continue
            fresh = bool(receipt["rendered_at"] and now - receipt["rendered_at"] < 15)
            clients.append({**receipt, "status": "rendered" if fresh else "sent"})
        return {"scene_id": self.current_scene.get("scene_id"), "reference": self.current_scene.get("reference", ""), "connected": len(self.connections), "rendered": sum(c["status"] == "rendered" for c in clients), "clients": clients}

    async def send_preview(self, scene: Dict[str, Any]) -> bool:
        """Diffuse une scène au seul canal de préparation.

        N'atteint JAMAIS la salle : c'est la garantie qui rend la
        pré-visualisation utilisable en plein culte.
        """
        self.preview_scene = {
            "type": "scripture", "text": "", "reference": "",
            "background": "black", "theme": "presentation", "translations": {},
            **{k: v for k, v in scene.items() if v is not None},
        }
        if not self.preview_connections:
            return True
        await asyncio.gather(
            *[self._send_to_conn(c, self.preview_scene) for c in list(self.preview_connections)],
            return_exceptions=True,
        )
        return True

    async def send_scene(self, scene: Dict[str, Any]) -> bool:
        """Diffuse la scène à tous les navigateurs connectés"""
        # Conserve la scène COMPLÈTE (y compris next_reference/next_text pour le
        # moniteur prédicateur) en garantissant les clés minimales.
        self.current_scene = {
            "type": "scripture",
            "text": "",
            "reference": "",
            "background": "black",
            "theme": "presentation",
            "translations": {},
            **{k: v for k, v in scene.items() if v is not None}
        }
        self.current_scene["scene_id"] = uuid.uuid4().hex
        for connection, receipt in self.receipts.items():
            if connection not in self.connections:
                continue
            receipt.update(scene_id=self.current_scene["scene_id"], sent_at=time.time(), rendered_at=None)
        
        if not self.connections:
            return True

        # Diffusion asynchrone aux clients
        tasks = []
        for conn in list(self.connections):
            tasks.append(self._send_to_conn(conn, self.current_scene))
        await asyncio.gather(*tasks, return_exceptions=True)
        return True

    async def _send_to_conn(self, conn: WebSocket, payload: Dict[str, Any]):
        try:
            await conn.send_json(payload)
        except Exception as e:
            logger.debug(f"Erreur diffusion client navigateur: {e}")
            # Des deux ensembles : un écran de préparation tombé restait sinon
            # dans la liste, et chaque envoi suivant relançait la même erreur.
            self.connections.discard(conn)
            self.preview_connections.discard(conn)
            self.receipts.pop(conn, None)

    async def broadcast_event(self, payload: Dict[str, Any]):
        """Diffuse un événement léger (progression de lecture, traduction live)
        sans écraser la scène courante — les pages ignorent les types inconnus."""
        if not self.connections:
            return
        await asyncio.gather(
            *(self._send_to_conn(conn, payload) for conn in list(self.connections)),
            return_exceptions=True,
        )

    async def clear(self) -> bool:
        """Efface l'écran"""
        try:
            from ..core.config import settings
            from ..services import background_store
            backdrop = background_store.resolve_background(settings)
        except Exception:
            backdrop = self.current_scene.get("backdrop", {})
        clear_scene = {
            "type": "scripture",
            "text": "",
            "reference": "",
            "background": self.current_scene.get("background", "black"),
            "theme": self.current_scene.get("theme", "presentation"),
            "translations": {},
            "backdrop": backdrop,
        }
        return await self.send_scene(clear_scene)
