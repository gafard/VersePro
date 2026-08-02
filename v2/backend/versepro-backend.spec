# -*- mode: python ; coding: utf-8 -*-
"""Spec PyInstaller du backend VersePro (sidecar Tauri).

Fige run_server.py en un exécutable autonome. On collecte explicitement les
dépendances à extensions natives / fichiers de données que l'analyse statique
de PyInstaller ne suit pas seule :
  - onnxruntime  (encodeur e5 : .dylib + capi)
  - tokenizers   (extension Rust)
  - vosk         (libvosk + bindings)
  - huggingface_hub (téléchargement du modèle Nemotron)
  - keyring      (trousseau macOS / Windows)
  - uvicorn      (workers/protocols chargés dynamiquement)
On NE bundle PAS les modèles : ils sont préparés explicitement dans le dossier
de données inscriptible depuis l'assistant de premier lancement ou Paramètres.
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

# Binaire C++ natif d'accélération ASR (transcribe-cli / Metal GPU)
_cli_bin = os.path.join(SPECPATH, "bin", "transcribe-cli")
if os.path.exists(_cli_bin):
    binaries.append((_cli_bin, "bin"))

# Bibliothèque partagée de parakeet.cpp (moteur Nemotron). Elle n'existe que si
# parakeet.cpp a été compilé avec BUILD_SHARED_LIBS=ON ; la compilation par
# défaut ne produit qu'un .a statique, inutilisable par ctypes.
for _lib in ("libparakeet.dylib", "libparakeet.so", "parakeet.dll"):
    _p = os.path.join(SPECPATH, "bin", _lib)
    if os.path.exists(_p):
        binaries.append((_p, "bin"))

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

for pkg in (
    "onnxruntime", "tokenizers", "vosk",
    "huggingface_hub", "keyring",
    # certifi : sans son cacert.pem embarqué, l'application figée n'a AUCUNE
    # autorité de certification et tout téléchargement de modèle meurt en
    # CERTIFICATE_VERIFY_FAILED (constaté sur macOS et Windows).
    "certifi",
):
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
    "PIL", "numpy", "keyring.backends.macOS", "keyring.backends.Windows",
]

a = Analysis(
    ["run_server.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    # NDIlib n'est plus exclu : sans lui, la sortie NDI ne pouvait exister que
    # sur un poste de développement. La bibliothèque native reste facultative —
    # le driver la charge dans un try/except et se désactive proprement si le
    # runtime NDI de Vizrt n'est pas installé sur la machine.
    excludes=["PyInstaller"],
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
