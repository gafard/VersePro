"""Portable model data only: no runtimes, credentials, Bible texts or user files."""
import hashlib
import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from .e5_encoder import E5OnnxEncoder
from .nemotron_service import NemotronService, MODEL_FILENAME
from ..core.config import DATA_DIR

MAX_BYTES = 1_600_000_000
NEMOTRON = f"models/nemotron/{MODEL_FILENAME}"
# Q8_0 LFS digest from the publisher, revision 6d44e540bc31b0de1dbe174a3cea87f53a7f22fb.
ALLOWED = {NEMOTRON: "b94545b313b3223fda7b2857a52681da813935c2127643d1e9ff0c23d988089c"}
for variant, config in E5OnnxEncoder.VARIANTS.items():
    for filename, digest in config["sha256"].items():
        ALLOWED[f"semantic/models/{variant}/{filename}"] = digest

def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b""):
            h.update(chunk)
    return h.hexdigest()

def inventory():
    files = []
    for relative in ALLOWED:
        path = NemotronService().resolved_model_path if relative == NEMOTRON else Path(DATA_DIR)/relative
        if path.is_file():
            files.append({"name": relative, "size": path.stat().st_size})
    return {"files": files, "bytes": sum(f["size"] for f in files), "format_version": 1}

def export_kit():
    entries = inventory()["files"]
    if not entries:
        raise ValueError("Préparez au moins un modèle local avant de créer le kit.")
    root = Path(tempfile.mkdtemp(prefix="versepro-kit-"))
    target = root/"versepro-offline.zip"
    try:
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_STORED) as archive:
            manifest = {"format": "versepro-offline", "schema_version": 1, "files": [],
                        "sources": {"nemotron": "https://huggingface.co/handy-computer/nemotron-3.5-asr-streaming-0.6b-gguf/tree/6d44e540bc31b0de1dbe174a3cea87f53a7f22fb",
                                    **{key: value["url"].replace("/resolve/", "/tree/") for key, value in E5OnnxEncoder.VARIANTS.items()}}}
            for entry in entries:
                path = NemotronService().resolved_model_path if entry["name"] == NEMOTRON else Path(DATA_DIR)/entry["name"]
                sha = digest(path)
                expected = ALLOWED[entry["name"]]
                if expected and sha != expected:
                    raise ValueError("Un modèle installé ne correspond pas à son empreinte attendue.")
                manifest["files"].append({**entry, "sha256": sha})
                archive.write(path, entry["name"])
            archive.writestr("manifest.json", json.dumps(manifest))
        return target
    except BaseException:
        shutil.rmtree(root, ignore_errors=True)
        raise

def import_kit(source, destination=None):
    base = Path(destination or DATA_DIR).resolve()
    base.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".kit-", dir=base))
    moved = []
    try:
        with zipfile.ZipFile(source) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(infos) > len(ALLOWED)+1 or len(set(names)) != len(names) or any(n != "manifest.json" and n not in ALLOWED for n in names):
                raise ValueError("Le kit contient des fichiers non autorisés.")
            if sum(i.file_size for i in infos) > MAX_BYTES or archive.getinfo("manifest.json").file_size > 10000:
                raise ValueError("Le kit dépasse la taille autorisée.")
            manifest = json.loads(archive.read("manifest.json"))
            if not isinstance(manifest, dict) or manifest.get("format") != "versepro-offline" or manifest.get("schema_version") != 1:
                raise ValueError("Format de kit non reconnu.")
            files = manifest.get("files", [])
            if not isinstance(files, list) or not files or not all(isinstance(f, dict) and isinstance(f.get("name"), str) for f in files) or len(files) > len(ALLOWED) or {f.get("name") for f in files} != set(names)-{"manifest.json"} or len(files) != len(names)-1:
                raise ValueError("Le manifeste ne correspond pas au contenu du kit.")
            if shutil.disk_usage(base).free < sum(i.file_size for i in infos) + 100_000_000:
                raise ValueError("Espace disque insuffisant pour vérifier et installer le kit.")
            for entry in files:
                name = entry["name"]
                if entry.get("size") != archive.getinfo(name).file_size:
                    raise ValueError("Taille de modèle incorrecte.")
                path = staging/name
                path.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(name) as src, open(path, "wb") as dst:
                    shutil.copyfileobj(src, dst, 1024*1024)
                sha = digest(path)
                if sha != entry.get("sha256") or (ALLOWED[name] and sha != ALLOWED[name]):
                    raise ValueError("Un modèle est corrompu ou ne correspond pas à sa version.")
                if name == NEMOTRON:
                    with path.open("rb") as stream:
                        if stream.read(4) != b"GGUF" or path.stat().st_size < 700*1024*1024:
                            raise ValueError("Modèle vocal incomplet ou format incorrect.")
                target = base/name
                if not target.resolve().is_relative_to(base):
                    raise ValueError("Le dossier du modèle pointe hors du stockage local.")
                if target.exists() and digest(target) != sha:
                    raise ValueError("Un modèle différent est déjà installé. Le kit ne le remplace pas.")
            # Every member is validated before any destination changes.
            for entry in files:
                target = base/entry["name"]
                if not target.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(staging/entry["name"], target)
                    moved.append(target)
        return {"installed": len(moved), "verified": len(files), "restart_required": bool(moved)}
    except BaseException:
        for path in moved:
            path.unlink(missing_ok=True)
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)
