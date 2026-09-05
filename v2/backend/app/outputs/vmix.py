import httpx
from typing import Dict, Any, Optional
from loguru import logger
from .base import BaseOutput

class VMixOutput(BaseOutput):
    """
    Driver de sortie pour vMix (requêtes HTTP GET SetText).
    """
    def __init__(self, host: str = "127.0.0.1", port: int = 8088, enabled: bool = False, input_id: str = "VerseProTitle"):
        super().__init__(name="vmix", enabled=enabled)
        self.host = host
        self.port = port
        self.input_id = input_id
        self.client = httpx.AsyncClient(timeout=2.0)

    async def update_settings(self, host: str, port: int, enabled: bool, input_id: str):
        self.host = host
        self.port = port
        self.enabled = enabled
        self.input_id = input_id

    async def disconnect(self):
        await self.client.aclose()

    async def send_scene(self, scene: Dict[str, Any]) -> bool:
        """Envoie les textes et références à l'API vMix Title"""
        if not self.enabled:
            return False

        text = scene.get("text", "")
        reference = scene.get("reference", "")
        base_url = f"http://{self.host}:{self.port}/API/"
        
        try:
            # 1. Envoi du texte (champ 'VerseText')
            params_text = {
                "Function": "SetText",
                "Input": self.input_id,
                "SelectedName": "VerseText",
                "Value": text
            }
            response_text = await self.client.get(base_url, params=params_text)
            
            # 2. Envoi de la référence (champ 'VerseRef')
            params_ref = {
                "Function": "SetText",
                "Input": self.input_id,
                "SelectedName": "VerseRef",
                "Value": reference
            }
            response_ref = await self.client.get(base_url, params=params_ref)
            
            # Re-plis pour les champs standard
            if response_text.status_code != 200 or response_ref.status_code != 200:
                params_text["SelectedName"] = "Text"
                response_text = await self.client.get(base_url, params=params_text)
                
                params_ref["SelectedName"] = "Title"
                response_ref = await self.client.get(base_url, params=params_ref)

            return response_text.status_code == 200 and response_ref.status_code == 200
        except Exception as e:
            logger.debug(f"Erreur envoi vMix: {e}")
            return False

    async def clear(self) -> bool:
        return await self.send_scene({"text": "", "reference": ""})
