"""
Tests unitaires pour NemotronService.
Utilise des mocks de l'API C de parakeet.cpp.
"""

import ctypes
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.nemotron_service import MODEL_FILENAME, NemotronService


@pytest.fixture
def mock_parakeet_lib():
    """Mock complet de la librairie C parakeet.cpp."""
    mock_lib = MagicMock()
    mock_lib.parakeet_init.return_value = ctypes.c_void_p(0xDEADBEEF)
    mock_lib.parakeet_create_stream.return_value = ctypes.c_void_p(0xCAFEBABE)
    mock_lib.parakeet_is_ready.side_effect = [1, 0, 0, 0, 0]
    mock_lib.parakeet_get_result.return_value = b"Jean trois seize"

    mock_lib.parakeet_free.return_value = None
    mock_lib.parakeet_free_stream.return_value = None
    mock_lib.parakeet_accept_waveform.return_value = None
    mock_lib.parakeet_decode_stream.return_value = None
    mock_lib.parakeet_reset_stream.return_value = None

    return mock_lib


@pytest.fixture
def service(tmp_path, monkeypatch):
    svc = NemotronService()
    monkeypatch.setattr(svc, "_model_dir", tmp_path / "models" / "nemotron")
    monkeypatch.setattr(svc, "_model_path", svc._model_dir / MODEL_FILENAME)
    monkeypatch.setattr(type(svc), "resolved_model_path", property(lambda self: self._model_path))
    return svc


def test_status_not_ready(service):
    assert service.is_ready is False
    status = service.status()
    assert status["ready"] is False
    assert status["loaded"] is False


def test_status_ready(service):
    service._model_dir.mkdir(parents=True, exist_ok=True)
    service._model_path.write_bytes(b"fake-gguf")
    assert service.is_ready is True


def test_start_stop(service, mock_parakeet_lib):
    service._model_dir.mkdir(parents=True, exist_ok=True)
    service._model_path.write_bytes(b"fake-gguf")
    service.lib_factory = lambda: mock_parakeet_lib

    service.start()
    assert service._ctx is not None
    assert service._stream is not None
    assert service._running is True

    service.stop()
    assert service._running is False
    assert service._ctx is None


def test_accept_waveform_and_decode(service, mock_parakeet_lib):
    service._model_dir.mkdir(parents=True, exist_ok=True)
    service._model_path.write_bytes(b"fake-gguf")
    service.lib_factory = lambda: mock_parakeet_lib

    service.start()

    samples = np.zeros(16000, dtype=np.float32)
    service.accept_waveform(samples)

    import time
    time.sleep(0.2)

    text = service.get_result()
    assert "Jean trois seize" in text

    service.stop()


def test_reset(service, mock_parakeet_lib):
    service._model_dir.mkdir(parents=True, exist_ok=True)
    service._model_path.write_bytes(b"fake-gguf")
    service.lib_factory = lambda: mock_parakeet_lib

    service.start()
    service._text_buffer = "ancien texte"
    service.reset()
    assert service._text_buffer == ""


def test_int16_conversion(service, mock_parakeet_lib):
    service._model_dir.mkdir(parents=True, exist_ok=True)
    service._model_path.write_bytes(b"fake-gguf")
    service.lib_factory = lambda: mock_parakeet_lib

    service.start()
    samples_int16 = np.array([0, 32767, -32768], dtype=np.int16)
    service.accept_waveform(samples_int16)
    service.stop()
