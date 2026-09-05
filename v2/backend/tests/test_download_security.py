import hashlib
from pathlib import Path
import zipfile

import pytest

from app.services import e5_encoder as e5_module
from app.services.download_utils import safe_extract_zip, verify_sha256


def test_safe_extract_rejects_zip_slip(tmp_path):
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("../outside.txt", "forbidden")

    with pytest.raises(ValueError, match="dangereux"):
        safe_extract_zip(archive, tmp_path / "out")
    assert not (tmp_path / "outside.txt").exists()


def test_sha256_verification(tmp_path):
    artifact = tmp_path / "model.bin"
    artifact.write_bytes(b"versepro")
    verify_sha256(artifact, "f988d28c681e92b251fe90a091476787b5ecf943b4301d35677503114b355ac4")
    with pytest.raises(ValueError, match="SHA-256"):
        verify_sha256(artifact, "0" * 64)


def test_sha256_requires_an_expected_digest(tmp_path):
    artifact = tmp_path / "model.bin"
    artifact.write_bytes(b"versepro")
    with pytest.raises(ValueError, match="manquant"):
        verify_sha256(artifact, "")


def test_e5_download_replaces_an_existing_invalid_file(tmp_path, monkeypatch):
    expected = b"verified-model"
    encoder = e5_module.E5OnnxEncoder(cache_dir=tmp_path, variant="e5-small")
    encoder.REQUIRED_FILES = {"model_quantized.onnx": "onnx/model_quantized.onnx"}
    encoder.HASHES = {
        "model_quantized.onnx": hashlib.sha256(expected).hexdigest(),
    }
    encoder.model_path.write_bytes(b"stale-model")

    def fake_download(_url, destination, _progress):
        Path(destination).write_bytes(expected)

    monkeypatch.setattr(e5_module, "download_file", fake_download)

    assert encoder.download_model() is True
    assert encoder.model_path.read_bytes() == expected
    assert not Path(str(encoder.model_path) + ".part").exists()
