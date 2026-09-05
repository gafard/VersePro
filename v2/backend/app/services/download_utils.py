"""Primitives de téléchargement atomique et d'extraction sans Zip Slip."""

import hashlib
import shutil
import ssl
import urllib.request
import zipfile
from pathlib import Path


def ssl_context() -> ssl.SSLContext:
    """Contexte TLS qui trouve ses autorités de certification.

    Dans l'application figée par PyInstaller, le magasin d'autorités du système
    n'est pas toujours atteignable : sans le paquet `certifi` embarqué, tout
    téléchargement de modèle échoue par CERTIFICATE_VERIFY_FAILED — constaté sur
    macOS comme sur Windows.

    On ne désactive JAMAIS la vérification. Un modèle de reconnaissance vocale
    est du code qui s'exécutera sur le poste de l'église : accepter n'importe
    quel certificat reviendrait à laisser un intermédiaire le remplacer.
    """
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def download_file(url: str, destination: str | Path, on_progress=None,
                  chunk_size: int = 1 << 16, timeout: int = 30) -> None:
    """Télécharge `url` vers `destination`, certificat vérifié.

    `on_progress(octets_reçus, octets_total)` est appelé au fil de l'eau ;
    `octets_total` vaut 0 quand le serveur ne l'annonce pas.
    """
    request = urllib.request.Request(url, headers={"User-Agent": "VersePro"})
    with urllib.request.urlopen(request, context=ssl_context(), timeout=timeout) as response:
        total = int(response.headers.get("Content-Length") or 0)
        received = 0
        with open(destination, "wb") as handle:
            while True:
                block = response.read(chunk_size)
                if not block:
                    break
                handle.write(block)
                received += len(block)
                if on_progress:
                    on_progress(received, total)


def verify_sha256(path: str | Path, expected: str) -> None:
    expected = str(expected or "").strip().lower()
    if not expected:
        raise ValueError("SHA-256 attendu manquant : téléchargement non vérifiable")
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
