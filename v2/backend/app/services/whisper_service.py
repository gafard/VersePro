import os
import numpy as np
from loguru import logger

class WhisperService:
    """Service de transcription locale utilisant faster-whisper pour une haute précision hors-ligne"""
    
    def __init__(self):
        self.model_size = "base"  # Modèle 'base' (~140 Mo) : excellent compromis vitesse/précision
        self.model = None
        self.initialized = False
        
    def initialize(self) -> bool:
        """Charge le modèle Whisper localement en mémoire"""
        if self.initialized:
            return True
            
        try:
            from faster_whisper import WhisperModel
            logger.info(f"🎙️ Chargement du modèle local Whisper '{self.model_size}'...")
            
            # Utilise 'cpu' avec 'int8' pour macOS/Windows sans GPU lourd, très rapide
            self.model = WhisperModel(
                self.model_size,
                device="cpu",
                compute_type="int8",
                download_root="v2/backend/data/whisper_models"
            )
            
            self.initialized = True
            logger.info(f"✅ Modèle local Whisper '{self.model_size}' chargé avec succès")
            return True
        except Exception as e:
            logger.error(f"❌ Erreur lors du chargement de Whisper: {e}")
            return False
            
    def transcribe(self, audio_data: bytes) -> str:
        """Transcrit un bloc d'audio PCM 16kHz mono (Int16)"""
        if not self.initialized:
            if not self.initialize():
                return ""
                
        try:
            # Convertit le flux d'octets Int16 en tableau NumPy Float32 normalisé entre -1.0 et 1.0
            audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
            
            # Lance la transcription
            segments, info = self.model.transcribe(
                audio_np,
                language="fr",
                beam_size=5,
                vad_filter=True, # Filtre les bruits de fond et silences
                vad_parameters=dict(min_silence_duration_ms=500)
            )
            
            # Concatène les segments transcrits
            text = " ".join([segment.text for segment in segments]).strip()
            return text
        except Exception as e:
            logger.error(f"❌ Erreur lors de la transcription locale Whisper: {e}")
            return ""
