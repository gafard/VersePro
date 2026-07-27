import asyncio
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
        self.current_scene: Dict[str, Any] = {
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
        if scene.get("reference"):
            return scene  # un verset est à l'antenne : sa scène fait foi
        try:
            from ..core.config import settings
            from ..services import overlay_store
            scene.setdefault("style", settings.PROJECTION_STYLE)
            scene.setdefault("show_version", settings.SHOW_BIBLE_VERSION)
            scene.setdefault("active_version", settings.BIBLE_VERSION)
            scene["overlay"] = overlay_store.resolve_overlay(
                settings.PROJECTION_STYLE, settings.OVERLAY_ZONES, settings.OVERLAY_SHAPES
            )
        except Exception as exc:  # un écran nu vaut mieux qu'un écran en erreur
            logger.debug(f"Scène initiale sans habillage : {exc}")
        return scene

    async def register_connection(self, websocket: WebSocket):
        """Enregistre un nouveau client d'affichage et lui envoie la scène courante"""
        self.connections.add(websocket)
        try:
            await websocket.send_json(self._scene_initiale())
        except Exception as e:
            logger.debug(f"Erreur envoi initial client navigateur: {e}")

    def unregister_connection(self, websocket: WebSocket):
        """Retire un client d'affichage déconnecté"""
        self.connections.discard(websocket)

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
            self.connections.discard(conn)

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
        clear_scene = {
            "type": "scripture",
            "text": "",
            "reference": "",
            "background": self.current_scene.get("background", "black"),
            "theme": self.current_scene.get("theme", "presentation"),
            "translations": {}
        }
        return await self.send_scene(clear_scene)
