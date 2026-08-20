# -*- mode: python ; coding: utf-8 -*-
"""Spec PyInstaller du backend VersePro (sidecar Tauri).

Fige run_server.py en un exécutable autonome. On collecte explicitement les
dépendances à extensions natives / fichiers de données que l'analyse statique
de PyInstaller ne suit pas seule :
  - onnxruntime  (encodeur e5 : .dylib + capi)
  - tokenizers   (extension Rust)
  - vosk         (libvosk + bindings)
  - transcribe_cpp / transcribe_cpp_native (moteur ASR local, .dylib/.dll)
  - huggingface_hub (téléchargement du modèle Nemotron)
  - keyring      (trousseau macOS / Windows)
  - uvicorn      (workers/protocols chargés dynamiquement)
On NE bundle PAS les modèles : ils sont préparés explicitement dans le dossier
de données inscriptible depuis l'assistant de premier lancement ou Paramètres.
"""
import os
from PyInstaller.utils.hooks import collect_all, collect_submodules

datas, binaries, hiddenimports = [], [], []

# Templates HTML indispensables pour les écrans de diffusion (/output, /stage, /follow)
templates_dir = os.path.join(SPECPATH, "app", "templates")
if os.path.isdir(templates_dir):
    for tpl in os.listdir(templates_dir):
        if tpl.endswith(".html"):
            datas.append((os.path.join(templates_dir, tpl), os.path.join("app", "templates")))

# Ressources bibliques et VAD embarquées
for src, dst in (
    (os.path.join(SPECPATH, "data", "bible.json"), "data"),
    (os.path.join(SPECPATH, "data", "bibles_cache", "kjf.json"), os.path.join("data", "bibles_cache")),
):
    if os.path.exists(src):
        datas.append((src, dst))

# La bibliothèque native du moteur ASR (Nemotron) arrive par la roue
# transcribe-cpp-native, une par plateforme : elle est collectée plus bas avec
# les autres paquets à extensions natives. Rien à compiler ni à copier ici —
# une version antérieure de ce fichier embarquait des binaires construits à la
# main, qui ne valaient que pour la machine du développeur.

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
    "onnxruntime", "tokenizers", "vosk", "transcribe_cpp", "transcribe_cpp_native",
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

# NDIlib : le binding ET le runtime NDI (30 Mo de libndi.dylib sur macOS,
# Processing.NDI.Lib.x64.dll sur Windows) arrivent ENSEMBLE dans la roue
# ndi-python. Rien à installer côté église : la sortie NDI marche à la sortie
# de la boîte dès que ce paquet est embarqué.
#
# Il l'a longtemps été à moitié : le workflow de release retirait ndi-python
# avant le gel. L'application livrée n'avait donc aucun module NDIlib,
# NDI_AVAILABLE valait False pour toujours, et Paramètres réclamait le
# « Runtime NDI » — que l'on pouvait installer autant de fois qu'on voulait
# sans jamais rien changer, puisqu'il ne fournit pas le module Python.
#
# Seul paquet OPTIONNEL de cette liste : un poste de développement sans
# ndi-python doit continuer à produire un gel utilisable, simplement privé de
# la sortie NDI.
try:
    d, b, h = collect_all("NDIlib")
    datas += d
    binaries += b
    hiddenimports += h
    print(f"spec : NDIlib collecté ({len(b)} binaires)")
except Exception as exc:
    print(f"spec : ATTENTION — NDIlib absent, la sortie NDI sera indisponible ({exc})")

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
    # VersePro n'importe RIEN de tout ceci. Ces paquets arrivent parce qu'ils
    # traînent dans l'environnement du développeur — mlx-whisper, installé pour
    # un script de comparaison de moteurs ASR, tire torch, numba et llvmlite.
    # Le gel les embarquait, soit 851 Mo sur un bundle de 1,2 Go.
    #
    # L'exclusion vaut mieux qu'une désinstallation : elle rend le résultat
    # indépendant de ce qui est installé sur la machine qui construit.
    #
    # La reconnaissance vocale passe par transcribe.cpp (Nemotron) et Vosk, la
    # recherche sémantique par onnxruntime : aucun de ces chemins n'a besoin de
    # torch. Si un jour un modèle PyTorch entre dans VersePro, retirer la ligne
    # correspondante ici — et remesurer le poids du bundle.
    excludes=[
        "PyInstaller",
        "torch", "torchvision", "torchaudio",
        "numba", "llvmlite",
        "mlx", "mlx_whisper", "mlx_lm",
        "faster_whisper", "ctranslate2", "whisper",
        "tensorboard", "matplotlib", "IPython", "notebook",
    ],
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
