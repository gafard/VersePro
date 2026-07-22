"""Primitives de téléchargement atomique et d'extraction sans Zip Slip."""

import hashlib
import shutil
import zipfile
from pathlib import Path


def verify_sha256(path: str | Path, expected: str) -> None:
    expected = str(expected or "").strip().lower()
    if not expected:
        return
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    actual = digest.hexdigest()
    if actual != expected:
        raise ValueError(f"SHA-256 invalide: attendu {expected}, reçu {actual}")


def safe_extract_zip(archive: str | Path, destination: str | Path) -> None:
    root = Path(destination).resolve()
    root.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "r") as bundle:
        for member in bundle.infolist():
            target = (root / member.filename).resolve()
            if target != root and root not in target.parents:
                raise ValueError(f"Chemin ZIP dangereux: {member.filename}")
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(member, "r") as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)

