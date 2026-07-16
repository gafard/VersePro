"""
Barrière vocale (VAD) — Silero VAD en ONNX, 100 % local (~2 Mo).

Filtre le flux audio en amont des moteurs de transcription : la musique,
les chants et les silences ne sont plus transcrits, ce qui supprime les
fausses détections pendant la louange et économise le quota Deepgram.

Fonctionnement : le modèle donne une probabilité de parole par trame de
512 échantillons (32 ms à 16 kHz). Une hystérésis évite le hachage :
la porte s'ouvre dès qu'une trame dépasse le seuil et reste ouverte
~1,5 s après la dernière parole détectée (les fins de phrases passent).
"""

import os
from typing import Optional

import numpy as np
from loguru import logger

FRAME_SIZE = 512          # 32 ms à 16 kHz (imposé par Silero VAD v5)
SPEECH_THRESHOLD = 0.5    # probabilité minimale pour ouvrir la porte
HANGOVER_CHUNKS = 6       # ~1,5 s de grâce après la dernière parole (chunks de 256 ms)

from ..core.config import DATA_DIR
_MODEL_PATH = str(DATA_DIR / "silero_vad.onnx")

_shared_session = None


def _get_session():
    """Session ONNX partagée entre toutes les connexions (le modèle est sans état)"""
    global _shared_session
    if _shared_session is None:
        import onnxruntime as ort
        opts = ort.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        _shared_session = ort.InferenceSession(_MODEL_PATH, sess_options=opts)
        logger.info("🎚️ Barrière vocale Silero VAD chargée")
    return _shared_session


def vad_available() -> bool:
    return os.path.exists(_MODEL_PATH)


class VoiceGate:
    """Porte de parole avec hystérésis — une instance par connexion audio (garde l'état RNN)."""

    def __init__(self, sample_rate: int = 16000):
        self.session = _get_session()
        self.sample_rate = sample_rate
        # État récurrent du modèle (h et c), propre à ce flux
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._sr = np.array(sample_rate, dtype=np.int64)
        self._hangover = 0
        self._leftover = np.empty(0, dtype=np.float32)
        # Statistiques d'efficacité (exposées au client)
        self.chunks_total = 0
        self.chunks_passed = 0

    def _frame_prob(self, frame: np.ndarray) -> float:
        out, self._state = self.session.run(
            None,
            {"input": frame.reshape(1, -1), "state": self._state, "sr": self._sr},
        )
        return float(out[0][0])

    def accept(self, pcm_bytes: bytes) -> bool:
        """
        True si le chunk contient (ou suit de près) de la parole.
        Entrée : PCM 16 bits mono à self.sample_rate.
        """
        self.chunks_total += 1

        audio = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        audio = np.concatenate([self._leftover, audio])

        max_prob = 0.0
        n_frames = len(audio) // FRAME_SIZE
        for i in range(n_frames):
            frame = audio[i * FRAME_SIZE:(i + 1) * FRAME_SIZE]
            prob = self._frame_prob(frame)
            if prob > max_prob:
                max_prob = prob
        self._leftover = audio[n_frames * FRAME_SIZE:]

        if max_prob >= SPEECH_THRESHOLD:
            self._hangover = HANGOVER_CHUNKS
            self.chunks_passed += 1
            return True
        if self._hangover > 0:
            self._hangover -= 1
            self.chunks_passed += 1
            return True
        return False

    def stats(self) -> dict:
        blocked = self.chunks_total - self.chunks_passed
        return {
            "chunks_total": self.chunks_total,
            "chunks_blocked": blocked,
            "blocked_ratio": round(blocked / self.chunks_total, 2) if self.chunks_total else 0.0,
        }
