import os
import urllib.request
import sys
import threading
import tempfile
import shutil
from loguru import logger
from ..core.config import settings, DATA_DIR
from .download_utils import safe_extract_zip, verify_sha256, download_file

class VoskService:
    """Service asynchrone pour la transcription locale hors-ligne avec Vosk (supporte les modèles small et large)"""

    MODEL_VARIANTS = {
        "large": ("vosk-model-fr-0.22", "https://alphacephei.com/vosk/models/vosk-model-fr-0.22.zip"),
        "small": ("vosk-model-small-fr-0.22", "https://alphacephei.com/vosk/models/vosk-model-small-fr-0.22.zip"),
    }

    def __init__(self):
        self.model_type = getattr(settings, "VOSK_MODEL_TYPE", "small").lower()
        if self.model_type not in self.MODEL_VARIANTS:
            self.model_type = "small"
        # Un parc existant peut ne posséder que l'autre variante sur le disque.
        # Faute du modèle configuré, et le
        # téléchargement étant devenu explicite, on charge la variante présente
        # plutôt que de perdre silencieusement le secours local hors-ligne.
        if not os.path.isdir(os.path.join(str(DATA_DIR), self.MODEL_VARIANTS[self.model_type][0])):
            for variant, (name, _) in self.MODEL_VARIANTS.items():
                if variant != self.model_type and os.path.isdir(os.path.join(str(DATA_DIR), name)):
                    logger.info(f"Modèle Vosk {self.model_type} absent; utilisation du modèle {variant} déjà installé")
                    self.model_type = variant
                    break
        self.model_name, self.url = self.MODEL_VARIANTS[self.model_type]

        # Dossier inscriptible (téléchargement du modèle au premier lancement).
        self.model_dir = os.path.join(str(DATA_DIR), self.model_name)
        self.model = None
        self.initialized = False
        self.downloading = False
        self.download_progress = 0.0
        self.download_status = ""
        self.last_error = ""

    def is_installed(self) -> bool:
        """Vérifie si le modèle est présent sur le disque et complet."""
        if not os.path.isdir(self.model_dir):
            return False
        try:
            contents = os.listdir(self.model_dir)
            return len(contents) > 0 and any(k in contents for k in ("am", "conf", "graph", "ivector"))
        except OSError:
            return False

    def initialize(self, allow_download: bool = False) -> bool:
        """Charge Vosk; le téléchargement n'a lieu qu'après une action explicite."""
        if self.initialized:
            return True

        try:
            import vosk
        except ImportError:
            logger.error("Vosk n'est pas installé dans l'environnement virtuel.")
            return False

        if not self.is_installed():
            if allow_download and not self.downloading:
                self.downloading = True
                self.last_error = ""
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
            self.last_error = f"Chargement du modèle impossible : {e}"
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
            self.last_error = f"Chargement du modèle impossible : {e}"
            logger.error(f"❌ Échec chargement du modèle Vosk téléchargé: {e}")
        finally:
            self.downloading = False

    def _download_model(self) -> bool:
        """Télécharge le modèle Vosk sélectionné"""
        parent_dir = os.path.dirname(self.model_dir)
        os.makedirs(parent_dir, exist_ok=True)

        zip_path = os.path.join(parent_dir, f"{self.model_name}.zip")
        part_path = f"{zip_path}.part"

        try:
            logger.info(f"📥 Téléchargement du modèle Vosk français ({self.model_type})...")
            self.download_status = "téléchargement"

            # Callback de progression pour le téléchargement
            last_percent = -1
            def progress_callback(readsofar, totalsize):
                nonlocal last_percent
                if totalsize > 0:
                    percent = min(99.0, (readsofar * 99.0) / totalsize)
                    self.download_progress = percent
                    percent_int = int(percent)
                    if percent_int % 5 == 0 and percent_int != last_percent:
                        last_percent = percent_int
                        logger.info(f"📥 Téléchargement Vosk: {percent_int}% ({readsofar / (1024**2):.1f} Mo / {totalsize / (1024**2):.1f} Mo)")

            download_file(self.url, part_path, progress_callback)

            self.download_status = "vérification"
            verify_sha256(part_path, settings.VOSK_MODEL_SHA256)
            if os.path.exists(zip_path):
                os.remove(zip_path)
            os.replace(part_path, zip_path)

            self.download_status = "extraction"
            logger.info("📦 Extraction du modèle (cela peut prendre quelques instants)...")
            with tempfile.TemporaryDirectory(dir=parent_dir, prefix="vosk-extract-") as temp_dir:
                safe_extract_zip(zip_path, temp_dir)
                extracted = os.path.join(temp_dir, self.model_name)
                if not os.path.isdir(extracted):
                    items = [os.path.join(temp_dir, d) for d in os.listdir(temp_dir) if os.path.isdir(os.path.join(temp_dir, d))]
                    if len(items) == 1:
                        extracted = items[0]
                    else:
                        raise ValueError("Archive Vosk invalide: dossier modèle absent")
                if os.path.exists(self.model_dir):
                    shutil.rmtree(self.model_dir, ignore_errors=True)
                shutil.move(extracted, self.model_dir)

            if os.path.exists(zip_path):
                os.remove(zip_path)

            self.download_progress = 100.0
            self.download_status = "terminé"
            logger.info(f"✅ Modèle Vosk ({self.model_type}) prêt à l'emploi")
            return True
        except Exception as e:
            self.last_error = f"Téléchargement interrompu : {e}"
            self.download_status = "erreur"
            logger.error(f"❌ Échec du téléchargement du modèle Vosk: {e}")
            for candidate in (zip_path, part_path):
                if os.path.exists(candidate):
                    try:
                        os.remove(candidate)
                    except OSError:
                        pass
            return False

    def get_recognizer(self, sample_rate: int = 16000):
        """Retourne un nouveau KaldiRecognizer pour le décodage audio"""
        if not self.initialized:
            if not self.initialize(allow_download=False):
                return None
        import vosk
        return vosk.KaldiRecognizer(self.model, sample_rate)
