"""Transcription locale Whisper avec chargement paresseux et fenêtres bornées."""

import importlib.util
import os
import platform
import threading
from pathlib import Path
from typing import Any, Optional

import numpy as np
from loguru import logger

from ..core.config import DATA_DIR, settings


class WhisperService:
    def __init__(self, model_factory=None) -> None:
        self.model_factory = model_factory
        self.model: Any = None
        self.model_name = self.select_model(settings.WHISPER_MODEL)
        self.buffer = bytearray()
        self.overlap_bytes = int(settings.AUDIO_SAMPLE_RATE * 2 * settings.WHISPER_OVERLAP_SECONDS)
        self.window_bytes = int(settings.AUDIO_SAMPLE_RATE * 2 * settings.WHISPER_CHUNK_SECONDS)
        self.last_error = ""
        self.initializing = False
        self._initialize_lock = threading.Lock()

    @staticmethod
    def available() -> bool:
        return importlib.util.find_spec("faster_whisper") is not None

    @staticmethod
    def _memory_gb() -> float:
        try:
            return (os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")) / (1024 ** 3)
        except (AttributeError, ValueError, OSError):
            return 8.0

    @classmethod
    def select_model(cls, configured: str) -> str:
        if configured and configured != "auto":
            return configured
        memory = cls._memory_gb()
        machine = platform.machine().lower()
        if memory >= 16 and machine in {"arm64", "aarch64"}:
            return "small"
        if memory >= 8:
            return "base"
        return "tiny"

    @property
    def ready(self) -> bool:
        return self.model is not None

    def model_cached(self) -> bool:
        """Vérifie qu'un modèle complet existe sans provoquer de téléchargement."""
        root = Path(DATA_DIR) / "models" / "whisper"
        if not root.exists():
            return False
        model_marker = f"faster-whisper-{self.model_name}"
        return any(
            path.name == "model.bin" and model_marker in str(path.parent)
            for path in root.rglob("model.bin")
        )

    def initialize(self, allow_download: Optional[bool] = None) -> bool:
        if self.model is not None:
            return True
        if not self._initialize_lock.acquire(blocking=False):
            return False
        self.initializing = True
        if not self.available() and self.model_factory is None:
            self.last_error = "faster-whisper n'est pas installé"
            self.initializing = False
            self._initialize_lock.release()
            return False
        allow_download = settings.WHISPER_AUTO_DOWNLOAD if allow_download is None else allow_download
        try:
            factory = self.model_factory
            if factory is None:
                from faster_whisper import WhisperModel
                factory = WhisperModel
            download_root = Path(DATA_DIR) / "models" / "whisper"
            download_root.mkdir(parents=True, exist_ok=True)
            self.model = factory(
                self.model_name,
                device="cpu",
                compute_type=settings.WHISPER_COMPUTE_TYPE,
                download_root=str(download_root),
                local_files_only=not allow_download,
            )
            self.last_error = ""
            logger.info(f"Whisper local prêt : {self.model_name} ({settings.WHISPER_COMPUTE_TYPE})")
            return True
        except Exception as exc:
            self.model = None
            self.last_error = str(exc)
            logger.warning(f"Whisper local indisponible : {exc}")
            return False
        finally:
            self.initializing = False
            self._initialize_lock.release()

    def reset(self) -> None:
        self.buffer.clear()

    def push_audio(self, pcm16: bytes) -> Optional[np.ndarray]:
        """Retourne une fenêtre float32 quand suffisamment d'audio est accumulé."""
        self.buffer.extend(pcm16)
        if len(self.buffer) < self.window_bytes:
            return None
        window = bytes(self.buffer[:self.window_bytes])
        overlap = window[-self.overlap_bytes:] if self.overlap_bytes else b""
        del self.buffer[:self.window_bytes]
        if overlap:
            self.buffer[:0] = overlap
        return np.frombuffer(window, dtype=np.int16).astype(np.float32) / 32768.0

    def transcribe_window(self, audio: np.ndarray) -> str:
        if self.model is None:
            return ""
        segments, _ = self.model.transcribe(
            audio,
            language=settings.DEEPGRAM_LANGUAGE or "fr",
            beam_size=settings.WHISPER_BEAM_SIZE,
            best_of=1,
            vad_filter=True,
            condition_on_previous_text=False,
            temperature=0.0,
        )
        return " ".join(str(segment.text).strip() for segment in segments if str(segment.text).strip()).strip()

    def status(self) -> dict:
        return {
            "dependency_available": self.available() or self.model_factory is not None,
            "installed": self.ready or self.model_cached(),
            "ready": self.ready,
            "preparing": self.initializing,
            "model": self.model_name,
            "chunk_seconds": settings.WHISPER_CHUNK_SECONDS,
            "last_error": self.last_error,
        }
