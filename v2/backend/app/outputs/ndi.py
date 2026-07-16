import os
import sys
import numpy as np
from typing import Dict, Any
from loguru import logger
from .base import BaseOutput
from PIL import Image, ImageDraw, ImageFont

# Chargement robuste de NDI
try:
    import NDIlib as ndi
    NDI_AVAILABLE = True
except Exception as e:
    logger.warning(f"⚠️ NDIlib non importable ou DLL NDI manquante : {e}")
    NDI_AVAILABLE = False

class NDIOutput(BaseOutput):
    """
    Driver de sortie NDI (Network Device Interface) pour diffuser
    les versets sur le réseau local avec canal alpha transparent.
    """
    def __init__(self, enabled: bool = False):
        super().__init__(name="ndi", enabled=enabled)
        self.functional = False
        self.ndi_send = None
        
        if NDI_AVAILABLE:
            try:
                if ndi.initialize():
                    self.functional = True
                    logger.info("🟢 Service NDI initialisé avec succès.")
                else:
                    logger.warning("⚠️ Échec de l'initialisation de NDIlib.")
            except Exception as e:
                logger.error(f"❌ Erreur lors de l'initialisation de NDIlib : {e}")

    def _ensure_sender(self) -> bool:
        if not self.functional or not self.enabled:
            return False
        if self.ndi_send is not None:
            return True
            
        try:
            send_settings = ndi.SendCreate()
            send_settings.ndi_name = 'VersePro - Projection'
            self.ndi_send = ndi.send_create(send_settings)
            if self.ndi_send:
                logger.info("🟢 Source d'émission NDI 'VersePro - Projection' créée.")
                return True
        except Exception as e:
            logger.error(f"❌ Impossible de créer l'émetteur NDI : {e}")
        return False

    def _render_frame(self, reference: str, text: str) -> np.ndarray:
        width, height = 1920, 1080
        img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        # Tentative de chargement de polices système
        font_path = "/System/Library/Fonts/Helvetica.ttc"
        if not os.path.exists(font_path):
            font_path = "/System/Library/Fonts/Supplemental/Arial.ttf"
            
        try:
            if os.path.exists(font_path):
                font_title = ImageFont.truetype(font_path, 42)
                font_text = ImageFont.truetype(font_path, 34)
            else:
                font_title = ImageFont.load_default(size=40)
                font_text = ImageFont.load_default(size=30)
        except Exception:
            font_title = ImageFont.load_default()
            font_text = ImageFont.load_default()

        # Rendu Lower Thirds esthétique (style régie pro)
        # Fond sombre semi-transparent
        bg_height = 220
        bg_y = height - bg_height - 60
        
        # Boîte de fond aux coins légèrement arrondis ou rectangles imbriqués
        draw.rectangle([120, bg_y, width - 120, bg_y + bg_height], fill=(16, 17, 20, 220))
        # Petite ligne d'accentuation lila sur le côté gauche
        draw.rectangle([120, bg_y, 128, bg_y + bg_height], fill=(123, 131, 235, 255))
        
        # Référence (Lila/Indigo #7b83eb)
        draw.text((150, bg_y + 24), reference, fill=(123, 131, 235, 255), font=font_title)
        
        # Découpage du texte du verset en lignes
        words = text.split(' ')
        lines = []
        current_line = ""
        for word in words:
            test_line = current_line + " " + word if current_line else word
            w = draw.textlength(test_line, font=font_text)
            if w < (width - 340):
                current_line = test_line
            else:
                lines.append(current_line)
                current_line = word
        if current_line:
            lines.append(current_line)
            
        y_offset = bg_y + 85
        for line in lines[:3]:  # Max 3 lignes dans le lower-third
            draw.text((150, y_offset), line, fill=(240, 241, 243, 255), font=font_text)
            y_offset += 42
            
        # Conversion RGBA en BGRX (format standard requis par NDI)
        arr = np.array(img)
        bgrx = np.empty((height, width, 4), dtype=np.uint8)
        bgrx[..., 0] = arr[..., 2] # B
        bgrx[..., 1] = arr[..., 1] # G
        bgrx[..., 2] = arr[..., 0] # R
        bgrx[..., 3] = arr[..., 3] # X (alpha canal conservé)
        return bgrx

    async def send_scene(self, scene: Dict[str, Any]) -> bool:
        if not self._ensure_sender():
            return False
            
        try:
            reference = scene.get("reference", "")
            text = scene.get("text", "")
            if not reference or not text:
                return await self.clear()
                
            frame_data = self._render_frame(reference, text)
            
            # Configuration de la frame NDI
            video_frame = ndi.VideoFrameV2()
            video_frame.xres = 1920
            video_frame.yres = 1080
            video_frame.FourCC = ndi.FOURCC_VIDEO_TYPE_BGRX
            video_frame.frame_format_type = ndi.FRAME_FORMAT_TYPE_PROGRESSIVE
            video_frame.picture_aspect_ratio = 16.0 / 9.0
            video_frame.data = frame_data
            
            # Envoi asynchrone
            ndi.send_send_video_v2(self.ndi_send, video_frame)
            return True
        except Exception as e:
            logger.error(f"❌ Erreur lors de l'envoi de la trame NDI : {e}")
        return False

    async def clear(self) -> bool:
        if not self._ensure_sender():
            return False
            
        try:
            # Envoyer une trame vide (transparente) pour vider l'écran
            width, height = 1920, 1080
            frame_data = np.zeros((height, width, 4), dtype=np.uint8)
            
            video_frame = ndi.VideoFrameV2()
            video_frame.xres = width
            video_frame.yres = height
            video_frame.FourCC = ndi.FOURCC_VIDEO_TYPE_BGRX
            video_frame.data = frame_data
            
            ndi.send_send_video_v2(self.ndi_send, video_frame)
            return True
        except Exception as e:
            logger.error(f"❌ Erreur lors du nettoyage de l'écran NDI : {e}")
        return False

    def close(self):
        if self.ndi_send:
            try:
                ndi.send_destroy(self.ndi_send)
                logger.info("🟢 Destructeur NDI appelé.")
            except Exception as e:
                logger.error(f"Erreur de libération NDI : {e}")
            self.ndi_send = None
        if self.functional:
            try:
                ndi.destroy()
            except Exception:
                pass
            self.functional = False
