import asyncio
import json
from typing import Optional, Dict, Any, Union
from loguru import logger
from .base import BaseOutput
from ..core.config import settings

class ProPresenterOutput(BaseOutput):
    """
    Driver de sortie pour ProPresenter 7+ (connexion TCP et API).
    """
    def __init__(self, host: str = "127.0.0.1", port: int = 12345, enabled: bool = False):
        super().__init__(name="propresenter", enabled=enabled)
        self.host = host
        self.port = port
        self.timeout = 2.0
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self.connected = False
        # Cooldown : après un échec, on ne retente pas la connexion avant 20 s
        # pour ne pas payer un timeout TCP à chaque verset projeté.
        self._retry_after = 0.0
        
        self.stats = {
            "commands_sent": 0,
            "commands_failed": 0,
            "last_command": None,
            "last_reference": None,
            "connection_attempts": 0
        }

    async def connect(self) -> bool:
        if not self.enabled:
            return False
        try:
            self.stats["connection_attempts"] += 1
            self.reader, self.writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=self.timeout
            )
            self.connected = True
            logger.info(f"✅ Connecté à ProPresenter ({self.host}:{self.port})")
            return True
        except Exception as e:
            logger.warning(f"❌ Impossible de se connecter à ProPresenter: {e}")
            self.connected = False
            return False

    async def disconnect(self):
        if self.writer:
            try:
                self.writer.close()
                await self.writer.wait_closed()
            except Exception:
                pass
            self.writer = None
            self.reader = None
        self.connected = False
        logger.info("🔌 Déconnecté de ProPresenter")

    async def _ensure_connected(self) -> bool:
        if not self.connected:
            now = asyncio.get_event_loop().time()
            if now < self._retry_after:
                return False
            ok = await self.connect()
            if not ok:
                self._retry_after = now + 20.0
            return ok
        return True

    async def _send_command(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not await self._ensure_connected():
            return None
        try:
            json_line = json.dumps(payload, ensure_ascii=False) + "\r\n"
            self.writer.write(json_line.encode('utf-8'))
            await self.writer.drain()
            self.stats["commands_sent"] += 1
            self.stats["last_command"] = payload.get("action", "unknown")
            
            # Attente de la réponse
            line = await asyncio.wait_for(self.reader.readline(), timeout=self.timeout)
            if line:
                return json.loads(line.decode('utf-8').strip())
        except Exception as e:
            logger.debug(f"Erreur commande ProPresenter: {e}")
            self.stats["commands_failed"] += 1
            self.connected = False
        return None

    async def send_scene(self, scene: Dict[str, Any]) -> bool:
        """Envoie les informations de la scène (verset) à ProPresenter"""
        if not self.enabled:
            return False
            
        ref_text = scene.get("reference", "")
        verse_text = scene.get("text", "")
        if not ref_text:
            return await self.clear()

        payload = {
            "action": "showBible",
            "reference": ref_text,
            "version": settings.BIBLE_VERSION,
            "text": verse_text
        }
        
        logger.info(f"📖 Envoi verset à ProPresenter: {ref_text}")
        response = await self._send_command(payload)
        self.stats["last_reference"] = ref_text
        return response is not None

    async def clear(self) -> bool:
        if not self.enabled:
            return False
        payload = {"action": "clearDisplay"}
        response = await self._send_command(payload)
        return response is not None

    async def is_connected(self) -> bool:
        if not self.enabled:
            return False
        if not self.connected:
            return False
        payload = {"action": "getStatus"}
        response = await self._send_command(payload)
        return response is not None
