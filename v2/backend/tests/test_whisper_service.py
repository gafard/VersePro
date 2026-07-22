from types import SimpleNamespace

import numpy as np

from app.core.config import settings
from app.services.whisper_service import WhisperService


class FakeModel:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    def transcribe(self, audio, **kwargs):
        assert isinstance(audio, np.ndarray)
        return iter([SimpleNamespace(text=" Jean trois seize ")]), SimpleNamespace(language="fr")


def test_whisper_uses_local_only_unless_download_is_explicit(monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.whisper_service.DATA_DIR", tmp_path)
    service = WhisperService(model_factory=FakeModel)

    assert service.initialize(allow_download=False)
    assert service.model.kwargs["local_files_only"] is True
    assert service.status()["ready"] is True


def test_whisper_emits_only_complete_bounded_windows(monkeypatch):
    monkeypatch.setattr(settings, "WHISPER_CHUNK_SECONDS", 0.1)
    monkeypatch.setattr(settings, "WHISPER_OVERLAP_SECONDS", 0.02)
    service = WhisperService(model_factory=FakeModel)
    assert service.initialize(allow_download=False)
    half = b"\x00\x00" * int(settings.AUDIO_SAMPLE_RATE * 0.05)

    assert service.push_audio(half) is None
    window = service.push_audio(half)
    assert window is not None
    assert len(window) == int(settings.AUDIO_SAMPLE_RATE * 0.1)
    assert service.transcribe_window(window) == "Jean trois seize"


def test_adaptive_model_selection(monkeypatch):
    monkeypatch.setattr(WhisperService, "_memory_gb", staticmethod(lambda: 18.0))
    monkeypatch.setattr("app.services.whisper_service.platform.machine", lambda: "arm64")
    assert WhisperService.select_model("auto") == "small"
    assert WhisperService.select_model("tiny") == "tiny"

