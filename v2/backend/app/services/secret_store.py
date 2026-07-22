"""Stockage des identifiants VersePro dans le gestionnaire de secrets du système."""

import asyncio
from typing import Optional

from loguru import logger

try:
    import keyring
except ImportError:  # L'application reste utilisable sans persistance des secrets.
    keyring = None


class SecretStore:
    SERVICE_NAME = "VersePro"
    SECRET_KEYS = ("deepgram_api_key", "openrouter_api_key", "gemini_api_key")

    def __init__(self) -> None:
        self._memory: dict[str, str] = {}
        self.available = keyring is not None

    async def get(self, key: str) -> str:
        if key in self._memory:
            return self._memory[key]
        if not self.available:
            return ""
        try:
            value = await asyncio.to_thread(keyring.get_password, self.SERVICE_NAME, key)
            return value or ""
        except Exception as exc:
            self.available = False
            logger.warning(f"Gestionnaire de secrets indisponible : {type(exc).__name__}")
            return ""

    async def set(self, key: str, value: str) -> bool:
        value = str(value or "").strip()
        self._memory[key] = value
        if not self.available:
            return False
        try:
            if value:
                await asyncio.to_thread(keyring.set_password, self.SERVICE_NAME, key, value)
            else:
                try:
                    await asyncio.to_thread(keyring.delete_password, self.SERVICE_NAME, key)
                except Exception:
                    pass
            return True
        except Exception as exc:
            self.available = False
            logger.warning(f"Secret conservé uniquement pour cette session : {type(exc).__name__}")
            return False

    async def migrate_from_database(self, database) -> None:
        """Transfère puis supprime les anciens secrets SQLite en clair."""
        for key in self.SECRET_KEYS:
            legacy = await database.get_setting(key, "")
            if not legacy:
                continue
            stored = await self.set(key, legacy)
            if stored:
                logger.info(f"Secret {key} migré vers le gestionnaire système")
            else:
                logger.warning(f"Secret {key} retiré de SQLite et conservé pour cette session")
            await database.delete_setting(key)


secret_store = SecretStore()

