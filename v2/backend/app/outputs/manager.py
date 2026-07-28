import asyncio
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
        self.register_output("ndi", NDIOutput(
            enabled=settings.NDI_ENABLED,
            source_name=settings.NDI_SOURCE_NAME,
        ))

        # Connexions de démarrage
        for name, output in self.outputs.items():
            if output.enabled:
                await output.connect()

    async def disconnect_all(self):
        for name, output in self.outputs.items():
            close = getattr(output, "close", None)
            if callable(close):
                close()
            else:
                await output.disconnect()
        logger.info("🔌 Toutes les sorties ont été déconnectées")

    async def project(self, text: str, reference: str, background: Optional[str] = None, translations: Optional[dict] = None, theme: Optional[str] = None):
        """Compatibilité : construit la scène puis délègue à project_scene"""
        return await self.project_scene({
            "type": "scripture",
            "text": text,
            "reference": reference,
            "background": background or "black",
            "theme": theme or "presentation",
            "translations": translations or {}
        })

    async def project_scene(self, scene: Dict[str, Any]) -> Dict[str, bool]:
        """Diffuse une scène et retourne l'accusé de chaque sortie active."""
        scene = {"type": "scripture", **scene}

        # Envoi PARALLÈLE : un driver lent ou déconnecté (ProPresenter absent,
        # vMix qui timeout) ne retarde plus l'affichage sur les autres sorties.
        async def _safe_send(name: str, output: BaseOutput):
            try:
                return name, bool(await output.send_scene(scene))
            except Exception as e:
                logger.error(f"Erreur d'envoi vers la sortie {name}: {e}")
                return name, False

        results = await asyncio.gather(*(
            _safe_send(name, output)
            for name, output in self.outputs.items() if output.enabled
        ))
        return dict(results)

    async def clear(self) -> Dict[str, bool]:
        """Efface les sorties actives et retourne leurs accusés."""
        async def _safe_clear(name: str, output: BaseOutput):
            try:
                return name, bool(await output.clear())
            except Exception as e:
                logger.error(f"Erreur de nettoyage de la sortie {name}: {e}")
                return name, False

        results = await asyncio.gather(*(
            _safe_clear(name, output)
            for name, output in self.outputs.items() if output.enabled
        ))
        return dict(results)
