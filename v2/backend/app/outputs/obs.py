from typing import Dict, Any
from loguru import logger
from .base import BaseOutput

class OBSOutput(BaseOutput):
    """
    Driver de sortie pour OBS (via OBS WebSocket ou API).
    Sert pour l'instant de stub (la diffusion passe principalement par le pilote browser
    via la source navigateur OBS).
    """
    def __init__(self, enabled: bool = False):
        super().__init__(name="obs", enabled=enabled)

    async def send_scene(self, scene: Dict[str, Any]) -> bool:
        # Intégrations WebSocket OBS futures si nécessaire
        return True

    async def clear(self) -> bool:
        return True
