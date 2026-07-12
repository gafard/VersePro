from typing import Dict, Any
from .base import BaseOutput

class NDIOutput(BaseOutput):
    """
    Driver de sortie NDI (Network Device Interface).
    Sera implémenté avec les bindings NDI officiels dans une version ultérieure.
    """
    def __init__(self, enabled: bool = False):
        super().__init__(name="ndi", enabled=enabled)

    async def send_scene(self, scene: Dict[str, Any]) -> bool:
        return True

    async def clear(self) -> bool:
        return True
