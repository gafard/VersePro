from typing import Dict, Any

class BaseOutput:
    """
    Interface de base pour les drivers de sortie de VersePro.
    """
    def __init__(self, name: str, enabled: bool = False):
        self.name = name
        self.enabled = enabled

    async def connect(self) -> bool:
        """Initialise ou connecte la sortie"""
        return True

    async def disconnect(self):
        """Ferme proprement la sortie"""
        pass

    async def send_scene(self, scene: Dict[str, Any]) -> bool:
        """Envoie une scène complète à afficher/projeter"""
        raise NotImplementedError("Les drivers de sortie doivent implémenter la méthode send_scene")

    async def clear(self) -> bool:
        """Efface l'affichage de la sortie"""
        raise NotImplementedError("Les drivers de sortie doivent implémenter la méthode clear")

    async def is_connected(self) -> bool:
        """Retourne l'état de connexion de la sortie"""
        return True
