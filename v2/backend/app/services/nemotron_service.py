"""
NemotronService - NVIDIA Nemotron-3.5-ASR via parakeet.cpp / GGUF (q8_0)
Streaming ASR local, CPU-only, cross-platform (Metal/Vulkan/CUDA via GGML).
"""

from __future__ import annotations

import ctypes
import json
import os
import platform
import threading
import time
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


def _load_parakeet_library() -> Optional[ctypes.CDLL]:
    """Charge la bibliothèque PARTAGÉE de parakeet.cpp, ou None si absente.

    Renvoyer None plutôt que lever : l'appelant doit pouvoir se rabattre sur
    Vosk sans que la session micro tombe. Une exception ici remonterait
    jusqu'au gestionnaire WebSocket et couperait le direct.

    À noter, et c'est le point qui bloque aujourd'hui : la compilation locale
    produit `libparakeet.a`, une bibliothèque STATIQUE, que ctypes ne sait pas
    charger. Il faut un `.dylib` / `.so` / `.dll` — c'est-à-dire recompiler
    parakeet.cpp avec BUILD_SHARED_LIBS=ON. Tant que ce fichier n'existe pas,
    ce chargeur renvoie None et le moteur reste indisponible, proprement.
    """
    systeme = platform.system()
    noms = {
        "Darwin": ["libparakeet.dylib"],
        "Linux": ["libparakeet.so"],
        "Windows": ["parakeet.dll", "libparakeet.dll"],
    }.get(systeme, ["libparakeet.so"])

    racine = Path(__file__).resolve().parents[2]
    dossiers = [
        racine / "bin",
        racine / "_internal" / "bin",   # gel PyInstaller (mode onedir)
        racine / "_internal",
        racine.parent / "bin",
        racine / "tmp" / "parakeet_src" / "build",
    ]
    def _valide(lib: ctypes.CDLL) -> bool:
        """Une poignée ne suffit pas : le symbole doit exister.

        Sur macOS, ctypes.CDLL(« libparakeet.dylib ») RÉUSSIT même sans aucun
        fichier de ce nom — il rend une poignée creuse dont tous les dlsym
        échouent ensuite. Sans cette vérification, le service croirait avoir
        chargé la bibliothèque et planterait plus loin, au pire moment.
        """
        try:
            getattr(lib, "parakeet_init")
            return True
        except AttributeError:
            return False

    for dossier in dossiers:
        for nom in noms:
            chemin = dossier / nom
            if not chemin.exists():
                continue
            try:
                lib = ctypes.CDLL(str(chemin))
            except OSError as exc:
                logger.warning(f"Bibliothèque parakeet illisible ({chemin}) : {exc}")
                continue
            if _valide(lib):
                return lib
            logger.warning(f"Bibliothèque parakeet sans les symboles attendus : {chemin}")

    # Dernier recours : le chargeur du système (LD_LIBRARY_PATH, /usr/local/lib…)
    for nom in noms:
        try:
            lib = ctypes.CDLL(nom)
        except OSError:
            continue
        if _valide(lib):
            return lib

    logger.info(
        "Bibliothèque parakeet.cpp partagée introuvable (%s). Le moteur Nemotron "
        "reste indisponible ; VersePro se rabattra sur Vosk.",
        " / ".join(noms),
    )
    return None


# ── Binding C flat via ctypes ──────────────────────────────────────────────
class _ParakeetCAPI:
    def __init__(self, lib: ctypes.CDLL) -> None:
        self.lib = lib
        try:
            # void* parakeet_init(const char* model_path, const char* params_json);
            self.lib.parakeet_init.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
            self.lib.parakeet_init.restype = ctypes.c_void_p

            # void parakeet_free(void* ctx);
            self.lib.parakeet_free.argtypes = [ctypes.c_void_p]
            self.lib.parakeet_free.restype = None

            # void* parakeet_create_stream(void* ctx);
            self.lib.parakeet_create_stream.argtypes = [ctypes.c_void_p]
            self.lib.parakeet_create_stream.restype = ctypes.c_void_p

            # void parakeet_free_stream(void* stream);
            self.lib.parakeet_free_stream.argtypes = [ctypes.c_void_p]
            self.lib.parakeet_free_stream.restype = None

            # void parakeet_accept_waveform(void* stream, float* samples, int n_samples);
            self.lib.parakeet_accept_waveform.argtypes = [
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_float),
                ctypes.c_int,
            ]
            self.lib.parakeet_accept_waveform.restype = None

            # int parakeet_is_ready(void* ctx, void* stream);
            self.lib.parakeet_is_ready.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
            self.lib.parakeet_is_ready.restype = ctypes.c_int

            # void parakeet_decode_stream(void* ctx, void* stream);
            self.lib.parakeet_decode_stream.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
            self.lib.parakeet_decode_stream.restype = None

            # const char* parakeet_get_result(void* ctx, void* stream);
            self.lib.parakeet_get_result.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
            self.lib.parakeet_get_result.restype = ctypes.c_char_p

            # void parakeet_reset_stream(void* ctx, void* stream);
            self.lib.parakeet_reset_stream.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
            self.lib.parakeet_reset_stream.restype = None
        except AttributeError as e:
            raise RuntimeError(f"Symboles C-API parakeet.cpp manquants dans la librairie dynamique: {e}")


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

        self._capi: Optional[_ParakeetCAPI] = None
        self._ctx: Optional[ctypes.c_void_p] = None
        self._stream: Optional[ctypes.c_void_p] = None

        self._lock = threading.Lock()
        self._text_buffer = ""
        self._running = False
        self.downloading = False
        self.download_progress = 0.0
        self.last_error = ""
        self._decode_thread: Optional[threading.Thread] = None

        self._sample_queue: list[np.ndarray] = []
        self._queue_event = threading.Event()

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
            "loaded": self._ctx is not None,
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

    def start(self) -> None:
        if not self.is_ready and self.lib_factory is None:
            raise RuntimeError("Modèle Nemotron non téléchargé. Appelez prepare() d'abord.")

        if self.lib_factory:
            lib = self.lib_factory()
        else:
            lib = _load_parakeet_library()

        if lib is None:
            self.last_error = (
                "Bibliothèque parakeet.cpp partagée absente. La compilation locale "
                "produit libparakeet.a (statique) ; ctypes exige un .dylib/.so — "
                "recompiler avec BUILD_SHARED_LIBS=ON."
            )
            raise RuntimeError(self.last_error)

        self._capi = _ParakeetCAPI(lib)

        params = {
            "language": "fr",
            "translate": False,
            "n_threads": max(1, os.cpu_count() or 1),
            "use_gpu": False,
        }
        params_json = json.dumps(params)

        self._ctx = self._capi.lib.parakeet_init(
            # `resolved_model_path` et non `_model_path` : is_ready cherche le
            # modèle dans sept emplacements, l'initialisation doit utiliser
            # CELUI qui a été trouvé, sinon elle échoue sur un chemin vide.
            str(self.resolved_model_path).encode("utf-8"),
            params_json.encode("utf-8"),
        )
        if not self._ctx:
            raise RuntimeError("parakeet_init a échoué.")

        self._stream = self._capi.lib.parakeet_create_stream(self._ctx)
        if not self._stream:
            raise RuntimeError("parakeet_create_stream a échoué.")

        self._text_buffer = ""
        self._running = True
        self._decode_thread = threading.Thread(target=self._decode_loop, daemon=True)
        self._decode_thread.start()

        logger.info("NemotronService démarré (streaming).")

    def stop(self) -> None:
        self._running = False
        self._queue_event.set()

        if self._decode_thread and self._decode_thread.is_alive():
            self._decode_thread.join(timeout=2.0)

        with self._lock:
            if self._stream and self._capi:
                try:
                    self._capi.lib.parakeet_free_stream(self._stream)
                except Exception:
                    pass
                self._stream = None
            if self._ctx and self._capi:
                try:
                    self._capi.lib.parakeet_free(self._ctx)
                except Exception:
                    pass
                self._ctx = None

        logger.info("NemotronService arrêté.")

    def reset(self) -> None:
        with self._lock:
            if self._ctx and self._stream and self._capi:
                try:
                    self._capi.lib.parakeet_reset_stream(self._ctx, self._stream)
                except Exception as e:
                    logger.warning(f"Erreur réinitialisation stream Nemotron : {e}")
            self._text_buffer = ""

    def accept_waveform(self, samples: np.ndarray) -> None:
        if not self._running or self._stream is None:
            return

        if samples.dtype == np.int16:
            samples = samples.astype(np.float32) / 32768.0
        elif samples.dtype != np.float32:
            samples = samples.astype(np.float32)

        if samples.ndim > 1:
            samples = samples.reshape(-1)

        with self._lock:
            self._sample_queue.append(samples.copy())
        self._queue_event.set()

    def get_result(self) -> str:
        with self._lock:
            return self._text_buffer

    def _decode_loop(self) -> None:
        while self._running:
            self._queue_event.wait(timeout=0.05)
            self._queue_event.clear()

            chunks: list[np.ndarray] = []
            with self._lock:
                if self._sample_queue:
                    chunks = self._sample_queue
                    self._sample_queue = []

            if not chunks or self._ctx is None or self._stream is None or self._capi is None:
                continue

            pcm = np.concatenate(chunks)
            n = len(pcm)
            if n == 0:
                continue

            buf = pcm.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            self._capi.lib.parakeet_accept_waveform(self._stream, buf, n)

            while (
                self._capi.lib.parakeet_is_ready(self._ctx, self._stream) != 0
                and self._running
            ):
                self._capi.lib.parakeet_decode_stream(self._ctx, self._stream)
                c_str = self._capi.lib.parakeet_get_result(self._ctx, self._stream)
                if c_str:
                    text = ctypes.string_at(c_str).decode("utf-8", errors="replace")
                    with self._lock:
                        if text and text != self._text_buffer:
                            self._text_buffer = text
                            logger.debug(f"Nemotron partial: {text}")
