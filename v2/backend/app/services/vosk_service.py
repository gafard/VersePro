import os
import zipfile
import urllib.request
import sys
import threading
from loguru import logger
from ..core.config import settings

class VoskService:
    """Service asynchrone pour la transcription locale hors-ligne avec Vosk (supporte les modèles small et large)"""
    
    def __init__(self):
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        
        self.model_type = getattr(settings, "VOSK_MODEL_TYPE", "small").lower()
        if self.model_type == "large":
            self.model_name = "vosk-model-fr-0.22"
            self.url = "https://alphacephei.com/vosk/models/vosk-model-fr-0.22.zip"
        else:
            self.model_name = "vosk-model-small-fr-0.22"
            self.url = "https://alphacephei.com/vosk/models/vosk-model-small-fr-0.22.zip"
            
        self.model_dir = os.path.join(base_dir, "data", self.model_name)
        self.model = None
        self.initialized = False
        self.downloading = False
        
    def initialize(self) -> bool:
        """Initialise le modèle Vosk (lance le téléchargement en tâche de fond si nécessaire)"""
        if self.initialized:
            return True
            
        try:
            import vosk
        except ImportError:
            logger.error("Vosk n'est pas installé dans l'environnement virtuel.")
            return False
            
        if not os.path.exists(self.model_dir):
            if not self.downloading:
                self.downloading = True
                logger.info(f"📥 Modèle Vosk {self.model_type} absent. Lancement du téléchargement en arrière-plan...")
                threading.Thread(target=self._bg_download_and_init, daemon=True).start()
            return False
            
        try:
            logger.info(f"🎙️ Chargement du modèle Vosk local ({self.model_type}) depuis {self.model_dir}...")
            self.model = vosk.Model(self.model_dir)
            self.initialized = True
            logger.info(f"✅ Modèle Vosk local ({self.model_type}) chargé avec succès")
            return True
        except Exception as e:
            logger.error(f"❌ Erreur lors du chargement du modèle Vosk: {e}")
            return False
            
    def _bg_download_and_init(self):
        """Méthode exécutée dans un thread séparé pour télécharger et initialiser sans bloquer l'application"""
        try:
            success = self._download_model()
            if success:
                import vosk
                logger.info(f"🎙️ Initialisation du modèle Vosk local ({self.model_type})...")
                self.model = vosk.Model(self.model_dir)
                self.initialized = True
                logger.info(f"✅ Modèle Vosk local ({self.model_type}) chargé et prêt en arrière-plan")
        except Exception as e:
            logger.error(f"❌ Échec chargement du modèle Vosk téléchargé: {e}")
        finally:
            self.downloading = False

    def _download_model(self) -> bool:
        """Télécharge le modèle Vosk sélectionné"""
        parent_dir = os.path.dirname(self.model_dir)
        os.makedirs(parent_dir, exist_ok=True)
        
        zip_path = os.path.join(parent_dir, f"{self.model_name}.zip")
        
        try:
            logger.info(f"📥 Téléchargement du modèle Vosk français ({self.model_type})...")
            
            # Callback de progression pour le téléchargement
            last_percent = -1
            def progress_callback(blocknum, blocksize, totalsize):
                nonlocal last_percent
                readsofar = blocknum * blocksize
                if totalsize > 0:
                    percent = int(readsofar * 100 / totalsize)
                    if percent % 5 == 0 and percent != last_percent: # Log toutes les 5 % pour éviter d'inonder les logs
                        last_percent = percent
                        logger.info(f"📥 Téléchargement Vosk: {percent}% ({readsofar / (1024**2):.1f} Mo / {totalsize / (1024**2):.1f} Mo)")
            
            urllib.request.urlretrieve(self.url, zip_path, progress_callback)
            
            logger.info("📦 Extraction du modèle (cela peut prendre quelques instants)...")
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(parent_dir)
                
            if os.path.exists(zip_path):
                os.remove(zip_path)
                
            logger.info(f"✅ Modèle Vosk ({self.model_type}) prêt à l'emploi")
            return True
        except Exception as e:
            logger.error(f"❌ Échec du téléchargement du modèle Vosk: {e}")
            if os.path.exists(zip_path):
                os.remove(zip_path)
            return False

    def get_recognizer(self, sample_rate: int = 16000):
        """Retourne un nouveau KaldiRecognizer pour le décodage audio"""
        if not self.initialized:
            if not self.initialize():
                return None
        import vosk
        return vosk.KaldiRecognizer(self.model, sample_rate)
