import httpx
from loguru import logger
from typing import Optional

class VMixService:
    """
    Service de pont avec l'API Web vMix.
    Permet de mettre à jour des titres en direct (GT Title Designer) via HTTP GET.
    """
    def __init__(self, host: str = "127.0.0.1", port: int = 8088, enabled: bool = False):
        self.host = host
        self.port = port
        self.enabled = enabled
        self.client = httpx.AsyncClient(timeout=2.0)
        logger.info(f"🎬 Service vMix initialisé (enabled={enabled}, host={host}:{port})")

    async def update_settings(self, host: str, port: int, enabled: bool):
        """Met à jour dynamiquement la configuration vMix"""
        self.host = host
        self.port = port
        self.enabled = enabled
        logger.info(f"🔌 Configuration vMix mise à jour: {host}:{port} (actif={enabled})")

    async def send_verse(self, text: str, reference: str, input_name_or_id: Optional[str] = None) -> bool:
        """
        Envoie le texte et la référence biblique vers l'API de titre de vMix.
        Tente de cibler les champs nommés 'VerseText' et 'VerseRef' de l'Input spécifié.
        """
        if not self.enabled:
            return False
            
        target_input = input_name_or_id or "VerseProTitle"
        base_url = f"http://{self.host}:{self.port}/API/"
        
        try:
            # 1. Envoi du texte du verset (champ 'VerseText')
            params_text = {
                "Function": "SetText",
                "Input": target_input,
                "SelectedName": "VerseText",
                "Value": text
            }
            response_text = await self.client.get(base_url, params=params_text)
            
            # 2. Envoi de la référence (champ 'VerseRef')
            params_ref = {
                "Function": "SetText",
                "Input": target_input,
                "SelectedName": "VerseRef",
                "Value": reference
            }
            response_ref = await self.client.get(base_url, params=params_ref)
            
            # Essai de repli si le titre vMix utilise des champs de texte standard 'Text' / 'Title'
            if response_text.status_code != 200 or response_ref.status_code != 200:
                logger.debug("Tentative de repli vMix avec les champs par défaut 'Text' et 'Title'")
                params_text["SelectedName"] = "Text"
                response_text = await self.client.get(base_url, params=params_text)
                
                params_ref["SelectedName"] = "Title"
                response_ref = await self.client.get(base_url, params=params_ref)

            if response_text.status_code == 200 and response_ref.status_code == 200:
                logger.info(f"🎬 Verset envoyé avec succès à vMix Title Input '{target_input}'")
                return True
            else:
                logger.warning(f"⚠️ Erreur de retour API vMix : Text={response_text.status_code}, Ref={response_ref.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Impossible de joindre vMix sur http://{self.host}:{self.port} : {e}")
            return False

    async def clear(self, input_name_or_id: Optional[str] = None) -> bool:
        """Efface le titre affiché sur vMix"""
        return await self.send_verse("", "", input_name_or_id)

    async def disconnect(self):
        """Ferme proprement le client HTTP"""
        await self.client.aclose()
        logger.info("🎬 Service vMix déconnecté")
