"""Whisper local adaptatif et session de transcription PCM par blocs."""

from __future__ import annotations

import asyncio
import inspect
import threading
from pathlib import Path
from typing import Awaitable, Callable, Optional

import numpy as np
from loguru import logger

from ..core.config import settings
from .hardware_profile import HardwareProfile, detect_hardware_profile


TranscriptCallback = Callable[[str, bool], Awaitable[None] | None]


class WhisperService:
    """Transcription locale haute précision avec sélection matérielle prudente."""

    def __init__(self, model_size: Optional[str] = None):
        self.hardware: HardwareProfile = detect_hardware_profile()
        configured = (model_size or settings.WHISPER_MODEL or "auto").lower()
        self.model_size = (
            self.hardware.recommended_whisper_model if configured == "auto" else configured
        )
        self.model = None
        self.initialized = False
        self.loading = False
        self.last_error = ""
        self._init_lock = threading.Lock()
        self.model_root = Path(__file__).resolve().parents[2] / "data" / "whisper_models"

    @property
    def model_downloaded(self) -> bool:
        if not self.model_root.exists():
            return False
        candidates = (
            self.model_root / f"models--Systran--faster-whisper-{self.model_size}",
            self.model_root / self.model_size,
        )
        return any(path.exists() for path in candidates)

    def configure_model(self, model_size: str) -> None:
        chosen = (model_size or "auto").lower()
        if chosen == "auto":
            chosen = self.hardware.recommended_whisper_model
        if chosen not in {"base", "small", "medium", "turbo", "large-v3"}:
            raise ValueError(f"Modèle Whisper non pris en charge: {chosen}")
        if chosen != self.model_size:
            self.model_size = chosen
            self.model = None
            self.initialized = False

    def initialize(self, allow_download: bool = True) -> bool:
        if self.initialized:
            return True

        with self._init_lock:
            if self.initialized:
                return True
            if not allow_download and not self.model_downloaded:
                self.last_error = "Modèle Whisper non téléchargé"
                return False

            self.loading = True
            try:
                from faster_whisper import WhisperModel

                device = "cuda" if self.hardware.cuda else "cpu"
                compute_type = "float16" if device == "cuda" else "int8"
                logger.info(
                    "Chargement Whisper local '{}' (device={}, compute={})",
                    self.model_size,
                    device,
                    compute_type,
                )
                self.model_root.mkdir(parents=True, exist_ok=True)
                self.model = WhisperModel(
                    self.model_size,
                    device=device,
                    compute_type=compute_type,
                    download_root=str(self.model_root),
                )
                self.initialized = True
                self.last_error = ""
                logger.info("Whisper local '{}' prêt", self.model_size)
                return True
            except Exception as exc:
                self.last_error = str(exc)
                logger.error("Whisper local indisponible: {}", exc)
                return False
            finally:
                self.loading = False

    def transcribe(self, audio_data: bytes) -> str:
        if not self.initialized and not self.initialize():
            return ""
        if not audio_data:
            return ""

        try:
            audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
            segments, _ = self.model.transcribe(
                audio_np,
                language=settings.DEEPGRAM_LANGUAGE or "fr",
                beam_size=max(1, int(settings.WHISPER_BEAM_SIZE)),
                vad_filter=True,
                condition_on_previous_text=False,
                vad_parameters={"min_silence_duration_ms": 350},
            )
            return " ".join(segment.text.strip() for segment in segments if segment.text.strip()).strip()
        except Exception as exc:
            self.last_error = str(exc)
            logger.error("Erreur de transcription Whisper locale: {}", exc)
            return ""

    def status(self) -> dict:
        return {
            "available": self.initialized or self.model_downloaded,
            "initialized": self.initialized,
            "loading": self.loading,
            "downloaded": self.model_downloaded,
            "model": self.model_size,
            "last_error": self.last_error,
            "hardware": self.hardware.to_dict(),
        }

    def create_streaming_session(
        self,
        callback: TranscriptCallback,
        sample_rate: int = 16000,
        chunk_seconds: Optional[float] = None,
    ) -> "WhisperStreamingSession":
        return WhisperStreamingSession(
            service=self,
            callback=callback,
            sample_rate=sample_rate,
            chunk_seconds=chunk_seconds or settings.WHISPER_CHUNK_SECONDS,
        )


class WhisperStreamingSession:
    """Accumule le PCM sans bloquer le WebSocket puis transcrit séquentiellement."""

    def __init__(
        self,
        service: WhisperService,
        callback: TranscriptCallback,
        sample_rate: int,
        chunk_seconds: float,
    ):
        self.service = service
        self.callback = callback
        self.sample_rate = sample_rate
        self.chunk_seconds = max(1.0, min(float(chunk_seconds), 8.0))
        self.target_bytes = int(self.sample_rate * 2 * self.chunk_seconds)
        self.queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=96)
        self.worker: Optional[asyncio.Task] = None
        self.active = False
        self.dropped_chunks = 0

    async def start(self, allow_download: bool = True) -> bool:
        ready = await asyncio.to_thread(self.service.initialize, allow_download)
        if not ready:
            return False
        self.active = True
        self.worker = asyncio.create_task(self._run())
        return True

    async def send_audio(self, data: bytes) -> None:
        if not self.active or not data:
            return
        try:
            self.queue.put_nowait(data)
        except asyncio.QueueFull:
            self.dropped_chunks += 1
            try:
                self.queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            self.queue.put_nowait(data)

    async def close(self) -> None:
        if not self.active and not self.worker:
            return
        self.active = False
        try:
            self.queue.put_nowait(None)
        except asyncio.QueueFull:
            await self.queue.put(None)
        if self.worker:
            try:
                await self.worker
            except asyncio.CancelledError:
                pass
        self.worker = None

    async def _emit(self, text: str) -> None:
        result = self.callback(text, True)
        if inspect.isawaitable(result):
            await result

    async def _run(self) -> None:
        buffer = bytearray()
        try:
            while True:
                data = await self.queue.get()
                if data is None:
                    break
                buffer.extend(data)
                while len(buffer) >= self.target_bytes:
                    block = bytes(buffer[: self.target_bytes])
                    del buffer[: self.target_bytes]
                    text = await asyncio.to_thread(self.service.transcribe, block)
                    if text:
                        await self._emit(text)

            if len(buffer) >= self.sample_rate:  # au moins 0,5 seconde de PCM16
                text = await asyncio.to_thread(self.service.transcribe, bytes(buffer))
                if text:
                    await self._emit(text)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Session Whisper interrompue: {}", exc)
        finally:
            self.active = False
