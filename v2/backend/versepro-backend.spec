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

# Index sémantique PRÉ-CALCULÉ (e5-base, float16, ~49 Mo npz+json) : identique
# pour tous les postes (même Bible, même modèle), il est livré avec l'app et
# copié vers le dossier utilisateur au premier lancement (_seed_bundled_index).
# L'onboarding passe de « télécharger 265 Mo PUIS indexer ~8 min » à
# « télécharger 265 Mo, terminé ». Sélection par dimension (768 = e5-base) pour
# ne pas embarquer les index périmés d'autres modèles.
import glob
import numpy as _np
for npz in glob.glob(os.path.join(SPECPATH, "data", "semantic", "index-*.npz")):
    try:
        if _np.load(npz)["matrix"].shape[1] != 768:
            continue
    except Exception:
        continue
    meta = npz[:-4] + ".json"
    if os.path.exists(meta):
        datas.append((npz, os.path.join("data", "semantic")))
        datas.append((meta, os.path.join("data", "semantic")))

# Polices servies aux écrans de diffusion (/fonts). 152 Ko, indispensables :
# sans elles l'application empaquetée projette en police système et les
# bandeaux perdent l'identité du produit.
_fonts = os.path.join(SPECPATH, "data", "fonts")
if os.path.isdir(_fonts):
    for _f in os.listdir(_fonts):
        if _f.endswith(".woff2"):
            datas.append((os.path.join(_fonts, _f), os.path.join("data", "fonts")))

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
    [],                # NE PAS inliner binaries/datas → mode onedir
    name="versepro-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    exclude_binaries=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="versepro-backend",
)
