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

    async def register_connection(self, websocket: WebSocket):
        """Enregistre un nouveau client d'affichage et lui envoie la scène courante"""
        self.connections.add(websocket)
        try:
            await websocket.send_json(self.current_scene)
        except Exception as e:
            logger.debug(f"Erreur envoi initial client navigateur: {e}")

    def unregister_connection(self, websocket: WebSocket):
        """Retire un client d'affichage déconnecté"""
        self.connections.discard(websocket)

    async def send_scene(self, scene: Dict[str, Any]) -> bool:
        """Diffuse la scène à tous les navigateurs connectés"""
        self.current_scene = {
            "type": scene.get("type", "scripture"),
            "text": scene.get("text", ""),
            "reference": scene.get("reference", ""),
            "background": scene.get("background", "black"),
            "theme": scene.get("theme", "presentation"),
            "translations": scene.get("translations") or {}
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
