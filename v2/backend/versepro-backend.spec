# -*- mode: python ; coding: utf-8 -*-
"""Spec PyInstaller du backend VersePro (sidecar Tauri).

Fige run_server.py en un exécutable autonome. On collecte explicitement les
dépendances à extensions natives / fichiers de données que l'analyse statique
de PyInstaller ne suit pas seule :
  - onnxruntime  (encodeur e5 : .dylib + capi)
  - tokenizers   (extension Rust)
  - vosk         (libvosk + bindings)
  - uvicorn      (workers/protocols chargés dynamiquement)
On NE bundle PAS les modèles (Vosk ~1,4 Go, e5 ~118 Mo) : ils se téléchargent
au premier lancement dans le dossier de données inscriptible.
"""
import os
from PyInstaller.utils.hooks import collect_all, collect_submodules

datas, binaries, hiddenimports = [], [], []

# Ressources bibliques EMBARQUÉES — domaine public uniquement (LSG + KJF).
# Les versions sous copyright (Semeur, TOB, NBS, Français courant) ne sont PAS
# distribuées. Elles atterrissent dans _internal/data/… côté figé.
for src, dst in (
    (os.path.join(SPECPATH, "data", "bible.json"), "data"),
    (os.path.join(SPECPATH, "data", "bibles_cache", "kjf.json"), os.path.join("data", "bibles_cache")),
):
    if os.path.exists(src):
        datas.append((src, dst))

for pkg in ("onnxruntime", "tokenizers", "vosk"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# Modules chargés dynamiquement.
hiddenimports += collect_submodules("uvicorn")
hiddenimports += collect_submodules("app")           # tout le backend
hiddenimports += [
    "anyio", "sniffio", "httpx", "httpcore", "aiosqlite", "aiohttp",
    "deepgram", "pydantic", "pydantic_settings", "loguru", "pythonosc",
    "PIL", "numpy",
]

a = Analysis(
    ["run_server.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    # NDIlib est optionnel (try/except) et tire une lib système lourde : on
    # l'exclut du figé pour ne pas casser le build. La sortie NDI se dégrade.
    excludes=["NDIlib", "PyInstaller"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="versepro-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)
