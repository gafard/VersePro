#!/usr/bin/env bash
# Empaquetage macOS de VersePro : gèle le backend Python en exécutable autonome
# (PyInstaller onedir), l'embarque dans le .app comme ressource, puis construit
# l'application Tauri. Résultat : un .app / .dmg qui LANCE le backend tout seul
# — aucun terminal, aucune installation de Python côté utilisateur.
#
# Prérequis : le venv de gel v2/backend/.freeze-venv (Python 3.12 + requirements
# + pyinstaller). Voir README. Onedir (pas onefile) : démarrage à froid ~6 s au
# lieu de ~40 s, car les bibliothèques natives ne sont pas ré-extraites ni
# re-scannées par Gatekeeper à chaque lancement.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
BACKEND="$HERE/../../backend"
FREEZE_VENV="$BACKEND/.freeze-venv"

if [ ! -x "$FREEZE_VENV/bin/pyinstaller" ]; then
  echo "❌ venv de gel absent. Créez-le :"
  echo "   python3.12 -m venv $BACKEND/.freeze-venv"
  echo "   $BACKEND/.freeze-venv/bin/pip install -r $BACKEND/requirements.txt pyinstaller"
  exit 1
fi

if ! "$FREEZE_VENV/bin/python" -c "import faster_whisper, keyring" >/dev/null 2>&1; then
  echo "Mise à niveau des dépendances du backend figé…"
  "$FREEZE_VENV/bin/python" -m pip install -r "$BACKEND/requirements.txt" pyinstaller
fi

echo "▶ 1/3  Gel du backend (PyInstaller onedir)…"
( cd "$BACKEND" && "$FREEZE_VENV/bin/pyinstaller" --clean --noconfirm versepro-backend.spec )

echo "▶ 2/3  Embarquement du backend dans les ressources Tauri…"
rm -rf "$HERE/backend"
cp -R "$BACKEND/dist/versepro-backend" "$HERE/backend"

echo "▶ 3/4  Construction de l'application Tauri…"
( cd "$HERE/.." && npm run tauri build -- --bundles app )

echo "▶ 4/4  Création du DMG natif…"
APP="$HERE/target/release/bundle/macos/VersePro.app"
DMG="$HERE/target/release/bundle/dmg/VersePro_2.0.0_aarch64.dmg"
STAGING="$(mktemp -d "${TMPDIR:-/tmp}/versepro-dmg.XXXXXX")"
cleanup() { rm -rf "$STAGING"; }
trap cleanup EXIT
cp -R "$APP" "$STAGING/VersePro.app"
ln -s /Applications "$STAGING/Applications"
mkdir -p "$(dirname "$DMG")"
rm -f "$DMG"
hdiutil create -volname "VersePro" -srcfolder "$STAGING" -ov -format UDZO "$DMG"

echo "✅ Terminé :"
echo "   $APP"
echo "   $DMG"
