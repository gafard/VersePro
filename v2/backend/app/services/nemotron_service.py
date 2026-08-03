"""
NemotronService - NVIDIA Nemotron-3.5-ASR via parakeet.cpp / GGUF (q8_0)
Streaming ASR local, CPU-only, cross-platform (Metal/Vulkan/CUDA via GGML).
"""

from __future__ import annotations

import ctypes
import json
import os
import platform
import subprocess
import tempfile
import threading
import time
import wave
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
from loguru import logger

from ..core.config import DATA_DIR, settings
from .download_utils import download_file, verify_sha256

# ── Configuration modèle ──────────────────────────────────────────────────
MODEL_REPO = "handy-computer/nemotron-3.5-asr-streaming-0.6b-gguf"
MODEL_FILENAME = "nemotron-3.5-asr-streaming-0.6b-Q8_0.gguf"
MODEL_SHA256 = None  # Validé lors du téléchargement Hugging Face
MODEL_SUBDIR = "nemotron"
MODEL_SIZE_MB = 716

# Le locale COMPLET est obligatoire : le modèle refuse « fr » et « auto »
# (« run: unsupported language »), il accepte « fr-FR ».
LANGUE = "fr-FR"

# Découpage sur les silences. Un seuil d'énergie suffit ici : on ne cherche pas
# à distinguer voix et musique — seulement à repérer une fin de phrase pour ne
# pas couper les mots en deux.
SEUIL_SILENCE_RMS = 0.006
SILENCE_MS = 600.0        # silence avant de clore un énoncé
PAROLE_MIN_MS = 800.0     # en deçà, ce n'est pas une phrase
ENONCE_MAX_S = 15.0       # plafond : un orateur qui n'inspire jamais
DELAI_MAX_S = 60.0        # garde-fou sur le processus fils


def _find_transcribe_cli_binary() -> Optional[Path]:
    """Localise le binaire natif d'accélération C++ transcribe-cli."""
    system = platform.system()
    bin_name = "transcribe-cli.exe" if system == "Windows" else "transcribe-cli"
    
    base_dir = Path(__file__).parent.parent.parent
    candidates = [
        base_dir / "bin" / bin_name,
        base_dir / "_internal" / "bin" / bin_name,
        base_dir.parent / "bin" / bin_name,
        base_dir / "tmp" / "transcribe_src" / "build" / "bin" / bin_name,
    ]
    for cand in candidates:
        if cand.exists():
            return cand
            
    import shutil
    found = shutil.which(bin_name)
    if found:
        return Path(found)
        
    return None


# ── Service Nemotron ───────────────────────────────────────────────────────
class NemotronService:
    """
    Provider ASR local streaming utilisant Nemotron-3.5-ASR (0.6B q8_0)
    via parakeet.cpp. Exécute le décodage dans un thread dédié.
    """

    NAME = "nemotron"
    DISPLAY_NAME = "Nemotron-3.5-ASR 0.6B (Streaming local)"
    SAMPLE_RATE = 16000

    def __init__(self, lib_factory=None) -> None:
        self.lib_factory = lib_factory
        self._model_dir = Path(DATA_DIR) / "models" / MODEL_SUBDIR
        self._model_path = self._model_dir / MODEL_FILENAME

        self._binaire: Optional[Path] = None

        self._lock = threading.Lock()
        self._text_buffer = ""
        self._running = False
        self.downloading = False
        self.download_progress = 0.0
        self.last_error = ""
        self._decode_thread: Optional[threading.Thread] = None

        self._pcm: list[np.ndarray] = []
        self._silence_ms = 0.0
        self._parole_ms = 0.0
        # Énoncé transcrit, en attente d'être consommé par l'appelant.
        self._enonce_fini: Optional[str] = None

    @property
    def resolved_model_path(self) -> Path:
        candidates = [
            self._model_path,
            Path(DATA_DIR) / "models" / MODEL_SUBDIR / MODEL_FILENAME,
            Path(DATA_DIR) / MODEL_SUBDIR / MODEL_FILENAME,
            Path.home() / "Library/Application Support/VersePro/data/models/nemotron" / MODEL_FILENAME,
            Path.home() / "Library/Application Support/app.versepro.regie/models/nemotron" / MODEL_FILENAME,
            Path.home() / "Library/Application Support/app.versepro.regie/data/models/nemotron" / MODEL_FILENAME,
            Path(__file__).resolve().parents[2] / "data" / "models" / MODEL_SUBDIR / MODEL_FILENAME,
        ]
        for cand in candidates:
            if cand.exists() and cand.stat().st_size > 0:
                return cand
        return self._model_path

    @property
    def is_ready(self) -> bool:
        path = self.resolved_model_path
        return path.exists() and path.stat().st_size > 0

    @property
    def model_path(self) -> Path:
        return self.resolved_model_path

    def status(self) -> Dict[str, Any]:
        return {
            "provider": self.NAME,
            "display_name": self.DISPLAY_NAME,
            "ready": self.is_ready,
            "installed": self.is_ready,
            "model_path": str(self.resolved_model_path),
            "model_size_mb": MODEL_SIZE_MB,
            "loaded": self._running,
            "downloading": self.downloading and not self.is_ready,
            "download_progress": 1.0 if self.is_ready else self.download_progress,
            "last_error": self.last_error,
        }

    def prepare(self, allow_download: bool = True) -> bool:
        """Télécharge le GGUF depuis Hugging Face si absent."""
        if self.is_ready:
            logger.info("Modèle Nemotron déjà présent.")
            return True

        if not allow_download:
            self.last_error = "Modèle Nemotron-3.5-ASR non présent sur disque."
            return False

        if self.downloading:
            return True

        self._model_dir.mkdir(parents=True, exist_ok=True)
        self.downloading = True
        self.download_progress = 0.0

        def _download_task():
            try:
                try:
                    from huggingface_hub import hf_hub_download
                    import shutil
                    logger.info("Téléchargement de Nemotron-3.5-ASR via huggingface_hub...")
                    self.download_progress = 0.2
                    downloaded_path = hf_hub_download(
                        repo_id=MODEL_REPO,
                        filename=MODEL_FILENAME,
                    )
                    self.download_progress = 0.9
                    shutil.copy2(downloaded_path, self._model_path)
                except Exception as ex:
                    logger.warning(f"Fallback téléchargement direct pour Nemotron: {ex}")
                    def _progress_cb(received, total):
                        if total > 0:
                            self.download_progress = min(0.99, float(received) / float(total))
                        else:
                            self.download_progress = min(0.95, self.download_progress + 0.01)

                    url = f"https://huggingface.co/{MODEL_REPO}/resolve/main/{MODEL_FILENAME}"
                    logger.info(f"Téléchargement de Nemotron-3.5-ASR (716 Mo) depuis {url}...")
                    download_file(url, self._model_path, on_progress=_progress_cb)

                self.download_progress = 1.0
                logger.info("✅ Modèle Nemotron-3.5-ASR q8_0 téléchargé avec succès")
            except Exception as e:
                self.last_error = f"Échec téléchargement Nemotron : {e}"
                logger.error(self.last_error)
            finally:
                self.downloading = False

        threading.Thread(target=_download_task, daemon=True).start()
        return True

    # ── Transcription par le binaire natif ──────────────────────────────────
    #
    # POURQUOI PAS ctypes. Le service visait une API C en flux inventée de
    # toutes pièces : aucun des neuf symboles appelés n'existe. La vraie API de
    # transcribe.cpp (include/transcribe.h) est faite de structures versionnées
    # accompagnées d'un fichier `transcribe.abihash` — signe que la disposition
    # mémoire compte à l'octet près. Un binding ctypes s'y trompant ne lève pas
    # d'erreur : il corrompt la mémoire. C'est un chantier à part entière.
    #
    # Le binaire `transcribe-cli`, lui, fonctionne : il charge ce modèle et
    # transcrit le français à 8,5× le temps réel — 0,47 s pour 4 s d'audio,
    # lancement du processus compris. Et sa sortie est PONCTUÉE et
    # capitalisée, là où Vosk rend une bouillie en minuscules.
    #
    # On découpe sur les SILENCES et non à intervalle fixe : couper toutes les
    # quatre secondes tomberait au milieu des mots, et « Romains chapitre huit
    # verset » perdrait son numéro.

    def start(self) -> None:
        """Vérifie que le binaire et le modèle sont là. N'ouvre aucun processus."""
        if self._running:
            return
        binaire = _find_transcribe_cli_binary()
        if binaire is None:
            self.last_error = (
                "Binaire transcribe-cli introuvable. Attendu dans bin/ "
                "(voir tmp/transcribe_src pour le compiler)."
            )
            raise RuntimeError(self.last_error)
        chemin = self.resolved_model_path
        if not (chemin.exists() and chemin.stat().st_size > 0):
            self.last_error = f"Modèle Nemotron introuvable : {chemin}"
            raise RuntimeError(self.last_error)

        self._binaire = binaire
        with self._lock:
            self._pcm = []
            self._silence_ms = 0.0
            self._parole_ms = 0.0
            self._text_buffer = ""
            self._enonce_fini = None
        self._running = True
        logger.info("✅ Nemotron prêt (%s, langue %s)", binaire.name, LANGUE)

    def stop(self) -> None:
        """Transcrit ce qui reste dans le tampon, puis se ferme."""
        if not self._running:
            return
        self._running = False
        reste = self._vider()
        if reste:
            with self._lock:
                self._enonce_fini = reste
        self._binaire = None

    def reset(self) -> None:
        with self._lock:
            self._pcm = []
            self._silence_ms = 0.0
            self._parole_ms = 0.0
            self._text_buffer = ""
            self._enonce_fini = None

    def accept_waveform(self, samples: np.ndarray) -> None:
        """Accumule le son ; transcrit dès qu'un énoncé se termine.

        Appel BLOQUANT quand la transcription se déclenche (~0,5 s) : à
        exécuter hors de la boucle d'événements, ce que fait le WebSocket audio
        via asyncio.to_thread.
        """
        if not self._running:
            return

        if samples.dtype == np.int16:
            flottants = samples.astype(np.float32) / 32768.0
        elif samples.dtype != np.float32:
            flottants = samples.astype(np.float32)
        else:
            flottants = samples
        if flottants.ndim > 1:
            flottants = flottants.reshape(-1)
        if flottants.size == 0:
            return

        duree_ms = 1000.0 * flottants.size / self.SAMPLE_RATE
        energie = float(np.sqrt(np.mean(np.square(flottants))))

        with self._lock:
            self._pcm.append(flottants.copy())
            if energie >= SEUIL_SILENCE_RMS:
                self._parole_ms += duree_ms
                self._silence_ms = 0.0
            else:
                self._silence_ms += duree_ms
            accumule_ms = sum(p.size for p in self._pcm) * 1000.0 / self.SAMPLE_RATE
            # Fin d'énoncé : assez parlé, puis assez de silence. Le plafond
            # évite qu'un prédicateur enchaînant sans pause fasse enfler le
            # tampon indéfiniment.
            termine = (
                (self._parole_ms >= PAROLE_MIN_MS and self._silence_ms >= SILENCE_MS)
                or accumule_ms >= ENONCE_MAX_S * 1000.0
            )
        if not termine:
            return

        texte = self._vider()
        if texte:
            with self._lock:
                self._enonce_fini = texte

    def get_result(self) -> str:
        """Texte en attente. La CLI ne rend rien avant la fin de l'énoncé."""
        with self._lock:
            return self._text_buffer

    def prendre_enonce_fini(self) -> Optional[str]:
        """Renvoie et consomme l'énoncé transcrit, ou None."""
        with self._lock:
            fini, self._enonce_fini = self._enonce_fini, None
            return fini

    # ── Interne ─────────────────────────────────────────────────────────────

    def _vider(self) -> str:
        """Écrit le tampon en WAV, le fait transcrire, et rend le texte."""
        with self._lock:
            morceaux, self._pcm = self._pcm, []
            assez = self._parole_ms >= PAROLE_MIN_MS
            self._parole_ms = 0.0
            self._silence_ms = 0.0
        if not morceaux or not assez:
            return ""

        pcm = np.concatenate(morceaux)
        try:
            with tempfile.TemporaryDirectory() as dossier:
                wav = Path(dossier) / "enonce.wav"
                with wave.open(str(wav), "wb") as flux:
                    flux.setnchannels(1)
                    flux.setsampwidth(2)
                    flux.setframerate(self.SAMPLE_RATE)
                    flux.writeframes((np.clip(pcm, -1.0, 1.0) * 32767).astype(np.int16).tobytes())
                return self._transcrire(wav)
        except Exception as exc:
            self.last_error = f"Transcription Nemotron impossible : {exc}"
            logger.error(self.last_error)
            return ""

    def _transcrire(self, wav: Path) -> str:
        """Lance transcribe-cli et extrait la ligne « text: »."""
        resultat = subprocess.run(
            [str(self._binaire), "-q",
             "-m", str(self.resolved_model_path),
             "-l", LANGUE, str(wav)],
            capture_output=True, text=True, timeout=DELAI_MAX_S,
            # bin/ contient aussi les libggml dont le binaire dépend.
            env={**os.environ, "DYLD_LIBRARY_PATH": str(self._binaire.parent),
                 "LD_LIBRARY_PATH": str(self._binaire.parent)},
        )
        if resultat.returncode != 0:
            self.last_error = (resultat.stderr or "").strip()[:200]
            logger.warning(f"transcribe-cli a échoué : {self.last_error}")
            return ""
        for ligne in resultat.stdout.splitlines():
            if ligne.startswith("text:"):
                return ligne[len("text:"):].strip()
        return ""
