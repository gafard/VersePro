"""Sortie NDI : le bandeau de l'église diffusé sur le réseau de la régie.

Deux différences avec la version précédente, qui ne servait à personne :

  • le rendu n'est plus un design codé en dur (boîte sombre, filet indigo) mais
    l'habillage RÉEL — image, formes et zones de texte — partagé avec l'écran de
    projection. Un mélangeur branché en NDI reçoit ce que l'assemblée voit ;

  • l'émission est continue. NDI n'est pas un protocole d'images isolées : un
    récepteur qui ne reçoit plus rien considère la source perdue et décroche.
    Un fil d'entretien réémet donc la dernière trame à cadence réduite.
"""

import threading
from typing import Any, Dict, Optional

import numpy as np
from loguru import logger

from .base import BaseOutput
from .ndi_render import rendre_habillage, vers_bgrx

try:
    import NDIlib as ndi
    NDI_AVAILABLE = True
except Exception as exc:  # bibliothèque native absente : la sortie se désactive
    logger.info(f"Sortie NDI indisponible sur ce poste : {exc}")
    NDI_AVAILABLE = False

LARGEUR, HAUTEUR = 1920, 1080
# 10 images par seconde : assez pour qu'un récepteur garde la source accrochée,
# assez peu pour ne pas disputer le processeur à la reconnaissance vocale un
# dimanche matin. La trame est réémise telle quelle, jamais redessinée.
FPS_ENTRETIEN = 10


class NDIOutput(BaseOutput):
    """Émetteur NDI « VersePro » diffusant l'habillage avec son canal alpha."""

    def __init__(self, enabled: bool = False, source_name: str = "VersePro"):
        super().__init__(name="ndi", enabled=enabled)
        self.source_name = source_name
        self.functional = False
        self.last_error = "" if NDI_AVAILABLE else "NDIlib absent de ce poste"
        self._send = None
        self._frame_lock = threading.Lock()
        self._frame: Optional[np.ndarray] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

        if NDI_AVAILABLE:
            try:
                if ndi.initialize():
                    self.functional = True
                    logger.info("🟢 NDI initialisé.")
                else:
                    self.last_error = "ndi.initialize() a échoué (runtime NDI absent ?)"
                    logger.warning(f"⚠️ {self.last_error}")
            except Exception as exc:
                self.last_error = f"Initialisation NDI impossible : {exc}"
                logger.error(f"❌ {self.last_error}")

    # ── Émetteur et fil d'entretien ──────────────────────────────────────────

    def _ensure_sender(self) -> bool:
        if not self.functional or not self.enabled:
            return False
        if self._send is not None:
            return True
        try:
            reglages = ndi.SendCreate()
            reglages.ndi_name = self.source_name
            self._send = ndi.send_create(reglages)
            if not self._send:
                self.last_error = "Création de la source NDI refusée"
                return False
            logger.info(f"🟢 Source NDI « {self.source_name} » en ligne.")
            self._stop.clear()
            self._thread = threading.Thread(target=self._boucle_entretien, daemon=True)
            self._thread.start()
            return True
        except Exception as exc:
            self.last_error = f"Émetteur NDI impossible : {exc}"
            logger.error(f"❌ {self.last_error}")
            return False

    def _emettre(self, trame: np.ndarray) -> None:
        video = ndi.VideoFrameV2()
        video.xres, video.yres = LARGEUR, HAUTEUR
        video.FourCC = ndi.FOURCC_VIDEO_TYPE_BGRX
        video.frame_format_type = ndi.FRAME_FORMAT_TYPE_PROGRESSIVE
        video.picture_aspect_ratio = LARGEUR / HAUTEUR
        video.data = trame
        ndi.send_send_video_v2(self._send, video)

    def _boucle_entretien(self) -> None:
        periode = 1.0 / FPS_ENTRETIEN
        while not self._stop.wait(periode):
            with self._frame_lock:
                trame = self._frame
                envoyeur = self._send
            if trame is None or envoyeur is None:
                continue
            try:
                self._emettre(trame)
            except Exception as exc:
                logger.debug(f"Entretien NDI interrompu : {exc}")
                return

    # ── API de sortie ────────────────────────────────────────────────────────

    def _composer(self, reference: str, texte: str, numero: Any) -> np.ndarray:
        from ..core.config import settings
        from ..services import overlay_store
        image = overlay_store.IMAGE_PATH if overlay_store.IMAGE_PATH.is_file() else None
        rendu = rendre_habillage(
            LARGEUR, HAUTEUR,
            overlay_store.parse_zones(settings.OVERLAY_ZONES),
            overlay_store.parse_shapes(settings.OVERLAY_SHAPES),
            reference, texte, numero,
            str(image) if image else None,
        )
        return vers_bgrx(rendu)

    async def send_scene(self, scene: Dict[str, Any]) -> bool:
        if not self._ensure_sender():
            return False
        reference = scene.get("reference", "")
        texte = scene.get("text", "")
        if not reference and not texte:
            return await self.clear()
        try:
            import asyncio
            # Le dessin d'une trame 1920×1080 prend quelques dizaines de
            # millisecondes : hors de la boucle d'événements, qui sert le direct.
            trame = await asyncio.to_thread(
                self._composer, reference, texte, scene.get("verse_start")
            )
            with self._frame_lock:
                self._frame = trame
            self._emettre(trame)
            return True
        except Exception as exc:
            self.last_error = f"Envoi NDI impossible : {exc}"
            logger.error(f"❌ {self.last_error}")
            return False

    async def clear(self) -> bool:
        if not self._ensure_sender():
            return False
        try:
            vide = np.zeros((HAUTEUR, LARGEUR, 4), dtype=np.uint8)
            with self._frame_lock:
                self._frame = vide
            self._emettre(vide)
            return True
        except Exception as exc:
            logger.error(f"❌ Nettoyage NDI impossible : {exc}")
            return False

    async def is_connected(self) -> bool:
        return bool(self.enabled and self.functional and self._send is not None)

    async def connect(self) -> bool:
        return self._ensure_sender()

    async def disconnect(self):
        # Déconnexion ≠ extinction : le runtime reste prêt pour une réactivation.
        self.stop_sending()

    def status(self) -> Dict[str, Any]:
        return {
            "available": NDI_AVAILABLE and self.functional,
            "enabled": self.enabled,
            "sending": self._send is not None,
            "source_name": self.source_name,
            "last_error": self.last_error,
        }

    def stop_sending(self):
        """Retire la source du réseau SANS libérer le runtime.

        Éteindre puis rallumer la sortie doit rester possible sans redémarrer
        VersePro : détruire le runtime ici rendait NDI « indisponible » jusqu'au
        prochain lancement, et l'opérateur ne pouvait plus la réactiver.
        """
        self._stop.set()
        fil = self._thread
        if fil and fil.is_alive():
            fil.join(timeout=1.0)
        self._thread = None
        if self._send:
            try:
                ndi.send_destroy(self._send)
                logger.info("🔌 Source NDI retirée du réseau.")
            except Exception as exc:
                logger.debug(f"Libération de l'émetteur NDI : {exc}")
            self._send = None
        with self._frame_lock:
            self._frame = None

    def close(self):
        """Arrêt définitif : à l'extinction de l'application uniquement."""
        self.stop_sending()
        if self.functional:
            try:
                ndi.destroy()
            except Exception:
                pass
            self.functional = False
