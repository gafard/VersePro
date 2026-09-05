"""
Service de transcription Deepgram v2 (SDK v6.0.0+)
Streaming temps réel avec latence ultra-faible (~300ms)
"""

import asyncio
from typing import Optional, Callable
from loguru import logger
from deepgram import AsyncDeepgramClient
from deepgram.core.events import EventType

from ..core.config import settings


class DeepgramSession:
    """Session de transcription en streaming utilisant listen.v1 du SDK v6"""
    
    def __init__(self, client: AsyncDeepgramClient, callback: Callable):
        self.client = client
        self.callback = callback
        self.connection = None
        self.is_active = False
        self._ctx = None
        self._listen_task = None
        self._keepalive_task = None
    
    async def start(self):
        """Démarre la session de streaming"""
        try:
            # Paramètres de connexion listen.v1
            kwargs = {
                "model": settings.DEEPGRAM_MODEL,
                "encoding": "linear16",
                "sample_rate": str(settings.AUDIO_SAMPLE_RATE),
                "language": settings.DEEPGRAM_LANGUAGE,
                "smart_format": "true" if settings.DEEPGRAM_SMART_FORMAT else "false",
                "punctuate": "true",
                "interim_results": "true",
                "endpointing": "300" # Coupe et finalise après 300ms de pause pour suivre la cadence rapide
            }
            
            logger.debug("⏳ Connexion au WebSocket Deepgram...")
            
            # Ouvre le context manager pour obtenir la connexion WebSocket
            self._ctx = self.client.listen.v1.connect(**kwargs)
            self.connection = await self._ctx.__aenter__()
            
            logger.debug("✅ WebSocket Deepgram connecté, envoi keep-alive immédiat...")
            
            # Envoi immédiat d'un keep-alive pour empêcher le timeout Deepgram
            # Deepgram ferme la connexion si aucun audio/message n'est reçu en ~10s
            await self.connection.send_keep_alive()
            
            # Enregistrement des callbacks
            async def on_message(result):
                try:
                    await self.callback(result)
                except Exception as e:
                    logger.error(f"Erreur dans le callback Deepgram: {e}")
                    
            async def on_error(*args, **kwargs):
                logger.error(f"Deepgram live error: {args}")
                # En cas d'erreur de connexion, marquer comme inactif
                self.is_active = False
                
            self.connection.on(EventType.MESSAGE, on_message)
            self.connection.on(EventType.ERROR, on_error)
            
            # Lance l'écoute en arrière-plan (NE PAS ATTENDRE - c'est bloquant)
            # start_listening lance la boucle de réception de messages websocket
            self._listen_task = asyncio.create_task(self.connection.start_listening())

            self.is_active = True

            # Keep-alive périodique : Deepgram coupe après ~10s sans audio ni message.
            # Sans cette boucle, une pause micro (prière, silence) tue la session.
            self._keepalive_task = asyncio.create_task(self._keepalive_loop())

            logger.info("🎤 Session Deepgram listen.v1 démarrée avec succès")
            
        except Exception as e:
            logger.error(f"❌ Erreur démarrage Deepgram: {e}")
            raise
    
    async def send_audio(self, audio_data: bytes):
        """Envoie un chunk audio"""
        if not self.is_active or not self.connection:
            return
        
        try:
            await self.connection.send_media(audio_data)
        except Exception as e:
            logger.error(f"❌ Erreur envoi audio à Deepgram: {e}")
            # Marque la session comme inactive pour stopper les envois en boucle
            self.is_active = False
    
    async def _keepalive_loop(self):
        """Envoie un keep-alive toutes les 5 secondes tant que la session est active"""
        try:
            while self.is_active and self.connection:
                await asyncio.sleep(5)
                if self.is_active and self.connection:
                    await self.connection.send_keep_alive()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug(f"Arrêt du keep-alive Deepgram: {e}")

    async def close(self):
        """Ferme la session et quitte proprement le contexte manager"""
        self.is_active = False
        if self._keepalive_task and not self._keepalive_task.done():
            self._keepalive_task.cancel()
            self._keepalive_task = None
        if self.connection:
            try:
                await self.connection.send_close_stream()
            except Exception as e:
                logger.debug(f"Note lors de la fermeture de la connexion: {e}")
            self.connection = None
        
        # Annule la tâche d'écoute en arrière-plan
        if self._listen_task and not self._listen_task.done():
            self._listen_task.cancel()
            try:
                await self._listen_task
            except (asyncio.CancelledError, Exception):
                pass
            self._listen_task = None
            
        if self._ctx:
            try:
                await self._ctx.__aexit__(None, None, None)
            except Exception as e:
                logger.debug(f"Note lors du nettoyage du context manager: {e}")
            self._ctx = None
            
        logger.info("🔒 Session Deepgram fermée")


class DeepgramService:
    """Service principal Deepgram"""
    
    def __init__(self, api_key: str = ""):
        self.api_key = api_key or settings.DEEPGRAM_API_KEY
        self.client = None
        
        if not self.api_key:
            logger.warning("⚠️ Clé API Deepgram non configurée dans .env")
        else:
            self._init_client()
    
    def _init_client(self):
        """Initialise le client Deepgram asynchrone"""
        try:
            self.client = AsyncDeepgramClient(api_key=self.api_key)
            logger.info("✅ Client Deepgram initialisé")
        except Exception as e:
            logger.error(f"❌ Erreur initialisation Deepgram: {e}")
            raise
    
    async def create_session(self, callback: Callable) -> DeepgramSession:
        """Crée une nouvelle session de transcription"""
        if not self.client:
            raise RuntimeError("Client Deepgram non initialisé (clé manquante)")
        
        session = DeepgramSession(self.client, callback)
        await session.start()
        return session
    
    async def disconnect(self):
        """Déconnecte le client"""
        self.client = None
