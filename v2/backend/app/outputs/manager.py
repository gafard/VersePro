from typing import Dict, Any, Optional
from loguru import logger
from .base import BaseOutput
from .browser import BrowserOutput
from .propresenter import ProPresenterOutput
from .vmix import VMixOutput
from .obs import OBSOutput
from .ndi import NDIOutput
from ..core.config import settings

class OutputManager:
    """
    Manager unifié qui pilote l'ensemble des drivers de sortie.
    """
    def __init__(self):
        self.outputs: Dict[str, BaseOutput] = {}
        
    def register_output(self, name: str, output: BaseOutput):
        self.outputs[name] = output
        logger.info(f"🔌 Sortie enregistrée: '{name}' (enabled={output.enabled})")

    async def initialize_defaults(self):
        """Initialise les pilotes par défaut à partir des paramètres de configuration"""
        self.register_output("browser", BrowserOutput())
        self.register_output("propresenter", ProPresenterOutput(
            host=settings.PROPRESENTER_HOST,
            port=settings.PROPRESENTER_PORT,
            enabled=settings.PROPRESENTER_AUTO_CONNECT
        ))
        self.register_output("vmix", VMixOutput(
            host=settings.VMIX_HOST,
            port=settings.VMIX_PORT,
            enabled=settings.VMIX_ENABLED,
            input_id=settings.VMIX_INPUT_ID
        ))
        self.register_output("obs", OBSOutput(enabled=False))
        self.register_output("ndi", NDIOutput(enabled=False))

        # Connexions de démarrage
        for name, output in self.outputs.items():
            if output.enabled:
                await output.connect()

    async def disconnect_all(self):
        for name, output in self.outputs.items():
            await output.disconnect()
        logger.info("🔌 Toutes les sorties ont été déconnectées")

    async def project(self, text: str, reference: str, background: Optional[str] = None, translations: Optional[dict] = None, theme: Optional[str] = None):
        """Diffuse la scène construite à tous les drivers enregistrés et actifs"""
        scene = {
            "type": "scripture",
            "text": text,
            "reference": reference,
            "background": background or "black",
            "theme": theme or "presentation",
            "translations": translations or {}
        }
        
        for name, output in self.outputs.items():
            if output.enabled:
                try:
                    await output.send_scene(scene)
                except Exception as e:
                    logger.error(f"Erreur d'envoi vers la sortie {name}: {e}")

    async def clear(self):
        """Efface toutes les sorties actives"""
        for name, output in self.outputs.items():
            if output.enabled:
                try:
                    await output.clear()
                except Exception as e:
                    logger.error(f"Erreur de nettoyage de la sortie {name}: {e}")
