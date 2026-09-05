import asyncio
from typing import Any
from loguru import logger
from pythonosc.osc_server import AsyncIOOSCUDPServer
from pythonosc.dispatcher import Dispatcher
from pythonosc.udp_client import SimpleUDPClient
from ..core.config import settings

class OSCService:
    """
    Service OSC (Open Sound Control) pour piloter VersePro à distance
    (Stream Deck, Companion, TouchOSC) et renvoyer le statut.
    """
    def __init__(self):
        self.server = None
        self.transport = None
        self.protocol = None
        self.client = None
        self.loop_task = None
        
    def _project_handler(self, address: str, *args: Any):
        if not args:
            return
        reference = str(args[0])
        logger.info(f"🎛️ OSC Reçu : {address} -> {reference}")
        
        # Lancer la projection asynchrone
        from ..main import output_manager, verse_parser, broadcast_projection
        
        async def do_project():
            parsed = None
            if verse_parser:
                parsed = await verse_parser.parse(reference)
            
            ref_name = parsed.get("reference") if parsed else reference
            ref_text = parsed.get("text") if parsed else ""
            
            await broadcast_projection(ref_text, ref_name)
            if output_manager:
                await output_manager.project(ref_text, ref_name)
                
            # Envoyer le statut de retour aux clients OSC
            self.send_feedback(ref_name)
            
        asyncio.run_coroutine_threadsafe(do_project(), asyncio.get_event_loop())

    def _clear_handler(self, address: str, *args: Any):
        logger.info(f"🎛️ OSC Reçu : {address} (Clear)")
        from ..main import output_manager, broadcast_projection
        
        async def do_clear():
            await broadcast_projection("", "")
            if output_manager:
                await output_manager.clear()
            self.send_feedback("ÉCRAN NOIR")
            
        asyncio.run_coroutine_threadsafe(do_clear(), asyncio.get_event_loop())

    def _next_handler(self, address: str, *args: Any):
        logger.info(f"🎛️ OSC Reçu : {address} (Next)")
        from ..main import output_manager, broadcast_projection, current_projection_slide
        
        async def do_next():
            # Navigation vers le verset suivant si présent dans current_projection_slide
            if current_projection_slide and current_projection_slide.get("next_reference"):
                next_ref = current_projection_slide["next_reference"]
                next_text = current_projection_slide["next_text"]
                await broadcast_projection(next_text, next_ref)
                if output_manager:
                    await output_manager.project(next_text, next_ref)
                self.send_feedback(next_ref)
                
        asyncio.run_coroutine_threadsafe(do_next(), asyncio.get_event_loop())

    def send_feedback(self, reference: str):
        """Envoie l'état courant vers le port de retour OSC (ex: Companion)"""
        if self.client:
            try:
                self.client.send_message("/versepro/status", reference)
            except Exception as e:
                logger.debug(f"Erreur d'envoi de feedback OSC : {e}")

    async def start(self):
        if not settings.OSC_ENABLED:
            logger.info("ℹ️ Service OSC désactivé par configuration.")
            return

        dispatcher = Dispatcher()
        dispatcher.map("/versepro/project", self._project_handler)
        dispatcher.map("/versepro/clear", self._clear_handler)
        dispatcher.map("/versepro/next", self._next_handler)
        
        try:
            loop = asyncio.get_event_loop()
            self.server = AsyncIOOSCUDPServer(
                ("0.0.0.0", settings.OSC_PORT), 
                dispatcher, 
                loop
            )
            self.transport, self.protocol = await self.server.create_serve_endpoint()
            logger.info(f"🎛️ Serveur OSC UDP actif sur le port {settings.OSC_PORT}")
            
            # Client de retour par défaut (ex: Companion écoute sur port + 1)
            feedback_port = settings.OSC_PORT + 1
            self.client = SimpleUDPClient("127.0.0.1", feedback_port)
            logger.info(f"🎛️ Client OSC Feedback configuré vers 127.0.0.1:{feedback_port}")
            
        except Exception as e:
            logger.error(f"❌ Échec du démarrage du serveur OSC : {e}")

    async def stop(self):
        if self.transport:
            self.transport.close()
            logger.info("🎛️ Serveur OSC arrêté.")
            self.transport = None
