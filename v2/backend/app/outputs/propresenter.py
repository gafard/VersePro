"""Sortie ProPresenter 7 (API TCP/IP officielle, 7.9+).

L'église garde SES habillages : VersePro n'impose aucun design, il remplit un
« Message » que l'opérateur a préparé et stylé dans ProPresenter. Le message
porte des jetons (tokens) — typiquement une référence et un texte — que ce
driver renseigne à chaque verset.

Protocole (documenté par Renewed Vision) : chaque requête est un objet JSON sur
UNE ligne terminée par CRLF, enveloppé ainsi :
    {"url": "v1/messages", "method": "GET", "body": {...}, "chunked": false}
et la réponse revient de même, avec un champ `data` (succès) ou `error`.
"""

import asyncio
import json
import unicodedata
from typing import Optional, Dict, Any, List
from loguru import logger
from .base import BaseOutput
from ..core.config import settings

# Noms de jetons acceptés pour chaque rôle, tolérants aux accents et à la casse.
# Une église francophone nommera « référence » et « verset » ; une autre
# « reference » et « text ». Les deux doivent fonctionner sans réglage.
_TOKEN_ALIASES = {
    "reference": ("reference", "ref", "passage", "versereference"),
    "text": ("text", "texte", "verset", "verse", "contenu", "corps"),
}


def _fold(value: str) -> str:
    """Minuscules sans accents ni espaces : pour comparer des noms de jetons."""
    stripped = unicodedata.normalize("NFKD", value or "")
    stripped = "".join(c for c in stripped if not unicodedata.combining(c))
    return "".join(c for c in stripped.lower() if c.isalnum())


class ProPresenterOutput(BaseOutput):
    """Driver de sortie pour ProPresenter 7.9+ via son API TCP/IP."""

    def __init__(self, host: str = "127.0.0.1", port: int = 1025, enabled: bool = False):
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
        # Une seule requête à la fois : les réponses arrivent en flux de lignes,
        # les entrelacer mélangerait les réponses entre elles.
        self._lock = asyncio.Lock()
        self._message_id: Optional[str] = None
        self._message_tokens: List[str] = []
        self.last_error = ""

        self.stats = {
            "commands_sent": 0,
            "commands_failed": 0,
            "last_command": None,
            "last_reference": None,
            "connection_attempts": 0
        }

    # ── Transport ────────────────────────────────────────────────────────────

    async def _request(self, url: str, method: str = "GET",
                       body: Any = None) -> Optional[Dict[str, Any]]:
        """Envoie une requête dans l'enveloppe TCP/IP et retourne la réponse."""
        if not self.writer or not self.reader:
            return None
        payload: Dict[str, Any] = {"url": url, "method": method, "chunked": False}
        if body is not None:
            payload["body"] = body
        try:
            async with self._lock:
                line = json.dumps(payload, ensure_ascii=False) + "\r\n"
                self.writer.write(line.encode("utf-8"))
                await self.writer.drain()
                self.stats["commands_sent"] += 1
                self.stats["last_command"] = url
                raw = await asyncio.wait_for(self.reader.readline(), timeout=self.timeout)
            if not raw:
                raise ConnectionError("réponse vide")
            response = json.loads(raw.decode("utf-8").strip())
            if "error" in response:
                self.last_error = str(response.get("error"))
                logger.warning(f"ProPresenter a refusé {url} : {self.last_error}")
                self.stats["commands_failed"] += 1
                return None
            return response
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            logger.debug(f"Erreur requête ProPresenter {url}: {exc}")
            self.stats["commands_failed"] += 1
            self.connected = False
            return None

    # ── Connexion ────────────────────────────────────────────────────────────

    async def connect(self) -> bool:
        if not self.enabled:
            return False
        try:
            self.stats["connection_attempts"] += 1
            self.reader, self.writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=self.timeout
            )
            # Un socket ouvert ne prouve pas qu'on parle à ProPresenter : on le
            # vérifie par une requête réelle, sinon la pastille passerait au vert
            # devant n'importe quel service qui écoute sur ce port.
            version = await self._request("v1/version")
            if version is None:
                self.last_error = (
                    f"Aucune réponse ProPresenter sur {self.host}:{self.port}. "
                    "Vérifiez Réglages → Réseau (API activée) et le port."
                )
                logger.warning(f"❌ {self.last_error}")
                await self.disconnect()
                return False
            self.connected = True
            self.last_error = ""
            logger.info(f"✅ Connecté à ProPresenter ({self.host}:{self.port})")
            await self._resolve_message()
            return True
        except Exception as e:
            self.last_error = f"Connexion impossible ({self.host}:{self.port}) : {e}"
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
        self._message_id = None
        self._message_tokens = []
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

    # ── Message de l'église ──────────────────────────────────────────────────

    async def _resolve_message(self) -> bool:
        """Retrouve, parmi les messages de ProPresenter, celui de VersePro."""
        wanted = _fold(getattr(settings, "PROPRESENTER_MESSAGE_NAME", "VersePro"))
        response = await self._request("v1/messages")
        messages = response.get("data") if response else None
        if not isinstance(messages, list):
            self.last_error = "Impossible de lister les messages ProPresenter."
            return False

        for message in messages:
            identifier = message.get("id") or {}
            name = identifier.get("name") or message.get("name") or ""
            if _fold(name) != wanted:
                continue
            self._message_id = identifier.get("uuid") or identifier.get("name") or name
            self._message_tokens = [
                token.get("name", "")
                for token in (message.get("tokens") or [])
                if isinstance(token, dict)
            ]
            logger.info(
                f"📖 Message ProPresenter « {name} » trouvé "
                f"(jetons : {self._message_tokens or 'aucun'})"
            )
            return True

        available = ", ".join(
            (m.get("id") or {}).get("name") or m.get("name") or "?" for m in messages
        ) or "aucun"
        self.last_error = (
            f"Aucun message nommé « {getattr(settings, 'PROPRESENTER_MESSAGE_NAME', 'VersePro')} » "
            f"dans ProPresenter. Messages disponibles : {available}. "
            "Créez-en un avec vos habillages, avec un jeton de référence et un de texte."
        )
        logger.warning(f"⚠️ {self.last_error}")
        return False

    def _build_tokens(self, reference: str, text: str) -> List[Dict[str, Any]]:
        """Associe nos valeurs aux jetons tels que l'église les a nommés."""
        values = {"reference": reference, "text": text}
        tokens: List[Dict[str, Any]] = []
        unmatched = list(self._message_tokens)

        for role, aliases in _TOKEN_ALIASES.items():
            for name in list(unmatched):
                folded = _fold(name)
                if folded in aliases or any(alias in folded for alias in aliases):
                    tokens.append({"name": name, "text": {"text": values[role]}})
                    unmatched.remove(name)
                    break

        # Aucun nom reconnu : on remplit dans l'ordre (1er = référence, 2e = texte)
        # plutôt que de ne rien projeter du tout.
        if not tokens and self._message_tokens:
            for name, value in zip(self._message_tokens, (reference, text)):
                tokens.append({"name": name, "text": {"text": value}})
        return tokens

    # ── API de sortie ────────────────────────────────────────────────────────

    async def send_scene(self, scene: Dict[str, Any]) -> bool:
        """Envoie le verset ; ProPresenter l'habille avec le thème de l'église."""
        if not self.enabled:
            return False

        ref_text = scene.get("reference", "")
        verse_text = scene.get("text", "")
        if not ref_text:
            return await self.clear()

        if not await self._ensure_connected():
            return False
        if not self._message_id and not await self._resolve_message():
            return False

        tokens = self._build_tokens(ref_text, verse_text)
        logger.info(f"📖 Envoi verset à ProPresenter: {ref_text}")
        response = await self._request(
            f"v1/message/{self._message_id}/trigger", "POST", tokens
        )
        self.stats["last_reference"] = ref_text
        return response is not None

    async def clear(self) -> bool:
        if not self.enabled or not self.connected or not self._message_id:
            return False
        response = await self._request(f"v1/message/{self._message_id}/clear", "GET")
        return response is not None

    async def is_connected(self) -> bool:
        if not self.enabled or not self.connected:
            return False
        return await self._request("v1/version") is not None
