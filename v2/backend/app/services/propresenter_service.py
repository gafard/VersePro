"""
Service ProPresenter v2
Intégration native via API TCP/IP officielle
"""

import asyncio
import json
from typing import Optional, Dict, Any, Union
import aiohttp
from loguru import logger

from ..core.config import settings


class ProPresenterService:
    """
    Service de communication avec ProPresenter
    
    Utilise l'API TCP/IP officielle de Renewed Vision
    Format: JSON lines avec terminaison CRLF
    """
    
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 12345,
        timeout: float = 2.0
    ):
        self.host = host
        self.port = port
        self.timeout = timeout
        
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self.connected = False
        
        # Statistiques
        self.stats = {
            "commands_sent": 0,
            "commands_failed": 0,
            "last_command": None,
            "last_reference": None,
            "connection_attempts": 0
        }
    
    async def connect(self) -> bool:
        """
        Établit la connexion TCP avec ProPresenter
        
        Returns:
            True si connecté avec succès
        """
        try:
            self.stats["connection_attempts"] += 1
            
            self.reader, self.writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=self.timeout
            )
            
            self.connected = True
            logger.info(f"✅ Connecté à ProPresenter ({self.host}:{self.port})")
            return True
            
        except ConnectionRefusedError:
            logger.warning(f"❌ ProPresenter refusé la connexion (port {self.port})")
            self.connected = False
            return False
            
        except asyncio.TimeoutError:
            logger.warning(f"❌ Timeout connexion ProPresenter")
            self.connected = False
            return False
            
        except Exception as e:
            logger.error(f"❌ Erreur connexion ProPresenter: {e}")
            self.connected = False
            return False
    
    async def disconnect(self):
        """Ferme la connexion"""
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()
            self.writer = None
            self.reader = None
        self.connected = False
        logger.info("🔌 Déconnecté de ProPresenter")
    
    async def _ensure_connected(self) -> bool:
        """Vérifie et rétablit la connexion si nécessaire"""
        if not self.connected:
            return await self.connect()
        return True
    
    async def _send_command(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Envoie une commande JSON à ProPresenter
        
        Args:
            payload: Dictionnaire de commande
        
        Returns:
            Réponse de ProPresenter ou None
        """
        if not await self._ensure_connected():
            return None
        
        try:
            # Format JSON line avec CRLF
            json_line = json.dumps(payload, ensure_ascii=False) + "\r\n"
            
            # Envoi
            self.writer.write(json_line.encode('utf-8'))
            await self.writer.drain()
            
            self.stats["commands_sent"] += 1
            self.stats["last_command"] = payload.get("action", "unknown")
            
            # Lecture réponse
            response = await self._read_response()
            return response
            
        except Exception as e:
            logger.error(f"❌ Erreur envoi commande: {e}")
            self.stats["commands_failed"] += 1
            self.connected = False
            return None
    
    async def _read_response(self) -> Optional[Dict[str, Any]]:
        """Lit la réponse JSON de ProPresenter"""
        try:
            if not self.reader:
                return None
            
            # Lit jusqu'à CRLF
            line = await asyncio.wait_for(
                self.reader.readline(),
                timeout=self.timeout
            )
            
            if not line:
                return None
            
            # Parse JSON
            try:
                return json.loads(line.decode('utf-8').strip())
            except json.JSONDecodeError:
                logger.debug(f"Réponse non-JSON: {line[:100]}")
                return None
                
        except asyncio.TimeoutError:
            logger.debug("Timeout lecture réponse ProPresenter")
            return None
        except Exception as e:
            logger.debug(f"Erreur lecture réponse: {e}")
            return None
    
    def _normalize_reference(self, reference: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
        """Accepte les appels legacy en texte et le format enrichi interne."""
        if isinstance(reference, str):
            return {
                "reference": reference.strip(),
                "text": "",
                "version": settings.BIBLE_VERSION,
            }
        if isinstance(reference, dict):
            ref_text = str(reference.get("reference") or "").strip()
            return {
                **reference,
                "reference": ref_text,
                "text": reference.get("text") or "",
                "version": reference.get("version") or settings.BIBLE_VERSION,
            }
        return {"reference": "", "text": "", "version": settings.BIBLE_VERSION}

    async def show_verse(self, reference: Union[str, Dict[str, Any]]) -> bool:
        """
        Affiche un verset dans ProPresenter
        
        Args:
            reference: Dictionnaire enrichi ou chaîne de référence ("Jn 3:16")
        
        Returns:
            True si succès
        """
        normalized = self._normalize_reference(reference)
        ref_text = normalized.get("reference", "")
        verse_text = normalized.get("text", "")
        version = normalized.get("version", settings.BIBLE_VERSION)

        if not ref_text:
            logger.warning("Référence vide: envoi ProPresenter annulé")
            return False
        
        # Commande pour afficher un verset
        # Note: Le format exact dépend de la configuration ProPresenter
        payload = {
            "action": "showBible",
            "reference": ref_text,
            "version": version,
            "text": verse_text  # Optionnel: texte complet du verset
        }
        
        logger.info(f"📖 Envoi verset: {ref_text}")
        response = await self._send_command(payload)
        self.stats["last_reference"] = ref_text
        
        if response:
            success = response.get("success", True) is not False
            if success:
                logger.info(f"✅ Verset affiché: {ref_text}")
            else:
                logger.warning(f"⚠️ Échec affichage: {response}")
            return success
        
        return False
    
    async def set_bible_version(self, version: str) -> bool:
        """Définit la version de Bible"""
        payload = {
            "action": "setBibleVersion",
            "version": version
        }
        
        logger.info(f"📚 Version Bible: {version}")
        response = await self._send_command(payload)
        return response is not None
    
    async def clear_display(self) -> bool:
        """Efface l'affichage"""
        payload = {"action": "clearDisplay"}
        logger.debug("🧹 Effacement affichage")
        response = await self._send_command(payload)
        return response is not None
    
    async def get_status(self) -> Optional[Dict[str, Any]]:
        """Récupère le statut de ProPresenter"""
        payload = {"action": "getStatus"}
        response = await self._send_command(payload)
        return response
    
    async def is_connected(self) -> bool:
        """Vérifie la connexion"""
        if not self.connected:
            return False
        
        # Ping pour vérifier
        status = await self.get_status()
        return status is not None
    
    async def trigger_macro(self, macro_id: int) -> bool:
        """
        Déclenche une macro ProPresenter
        
        Args:
            macro_id: ID de la macro
        
        Returns:
            True si succès
        """
        payload = {
            "action": "triggerMacro",
            "macroId": macro_id
        }
        
        logger.info(f"🎯 Macro {macro_id} déclenchée")
        response = await self._send_command(payload)
        return response is not None
    
    def get_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques"""
        return self.stats.copy()


class ProPresenterHTTPClient:
    """
    Client HTTP alternatif pour ProPresenter 7+
    Utilise l'API REST si disponible
    """
    
    def __init__(self, host: str = "127.0.0.1", port: int = 12346):
        self.base_url = f"http://{host}:{port}/api"
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def connect(self):
        """Initialise la session HTTP"""
        self.session = aiohttp.ClientSession()
    
    async def disconnect(self):
        """Ferme la session"""
        if self.session:
            await self.session.close()
    
    async def show_verse(self, reference: str) -> bool:
        """Affiche un verset via API REST"""
        if not self.session:
            return False
        
        try:
            payload = {
                "type": "bible",
                "reference": reference
            }
            
            async with self.session.post(
                f"{self.base_url}/present",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                return response.status == 200
                
        except Exception as e:
            logger.error(f"❌ Erreur API HTTP ProPresenter: {e}")
            return False
