#!/usr/bin/env bash
#
# Fabrique VersePro.dmg, prêt à installer.
#
#   ./v2/scripts/build-dmg.sh
#
# Trois étages, dans cet ordre obligé : le backend est gelé en exécutable,
# copié DANS les ressources de l'app, puis Tauri emballe le tout. Inverser
# produit une app sans backend qui s'ouvre sur un écran blanc.
#
# Le DMG atterrit sur le Bureau.

set -euo pipefail

RACINE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND="$RACINE/v2/backend"
FRONTEND="$RACINE/v2/frontend"
BUNDLE="$FRONTEND/src-tauri/target/release/bundle"
VERSION="$(sed -n 's/.*"version": *"\([^"]*\)".*/\1/p' "$FRONTEND/src-tauri/tauri.conf.json" | head -1)"
ARCH="$(uname -m)"
DMG="VersePro_${VERSION}_${ARCH}.dmg"

etape() { printf "\n\033[1m▸ %s\033[0m\n" "$1"; }

# ── 1. Geler le backend Python ───────────────────────────────────────────────
etape "Backend Python → exécutable"
cd "$BACKEND"
[ -x venv/bin/pyinstaller ] || { echo "venv absent : ./v2/install.sh d'abord"; exit 1; }
rm -rf dist/versepro-backend build
./venv/bin/pyinstaller --clean --noconfirm versepro-backend.spec

# PyInstaller sort 0 même quand il n'a rien produit. On vérifie le binaire,
# pas le code de retour.
[ -x dist/versepro-backend/versepro-backend ] || { echo "gel échoué"; exit 1; }
echo "  $(du -sh dist/versepro-backend | cut -f1)"

# ── 2. Placer le backend dans les ressources de l'app ────────────────────────
etape "Backend → ressources Tauri"
rm -rf "$FRONTEND/src-tauri/backend"
cp -R dist/versepro-backend "$FRONTEND/src-tauri/backend"

# ── 3. Interface + emballage ─────────────────────────────────────────────────
etape "Interface React"
cd "$FRONTEND"
npx vite build

etape "Emballage Tauri"
rm -rf "$BUNDLE"
npm run tauri build -- --bundles app
APP="$BUNDLE/macos/VersePro.app"
[ -d "$APP" ] || { echo "app non produite"; exit 1; }

# ── 4. DMG ───────────────────────────────────────────────────────────────────
# Le raccourci /Applications fait le glisser-déposer attendu à l'ouverture.
etape "DMG"
STAGING="$(mktemp -d)"
cp -R "$APP" "$STAGING/"
ln -s /Applications "$STAGING/Applications"
mkdir -p "$BUNDLE/dmg"
hdiutil create -volname "VersePro" -srcfolder "$STAGING" -ov -format UDZO \
               "$BUNDLE/dmg/$DMG" >/dev/null
rm -rf "$STAGING"
hdiutil verify "$BUNDLE/dmg/$DMG" >/dev/null 2>&1 || { echo "DMG corrompu"; exit 1; }

cp "$BUNDLE/dmg/$DMG" "$HOME/Desktop/$DMG"
# Sans ça, macOS met l'image en quarantaine et refuse de l'ouvrir au double-clic.
xattr -dr com.apple.quarantine "$HOME/Desktop/$DMG" 2>/dev/null || true

printf "\n\033[1;32m✓ ~/Desktop/%s\033[0m  (%s)\n" \
       "$DMG" "$(du -h "$HOME/Desktop/$DMG" | cut -f1)"
