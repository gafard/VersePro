import zipfile

import pytest

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
