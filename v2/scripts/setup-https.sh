#!/bin/bash
# ─────────────────────────────────────────────────────────────────
# VersePro — HTTPS local de confiance (mkcert)
#
# Pourquoi : les navigateurs n'autorisent le micro (getUserMedia)
# qu'en contexte sécurisé. En local (localhost) tout va bien, mais
# si la console de régie est ouverte depuis UN AUTRE POSTE du réseau
# en http://, le bouton micro sera bloqué par le navigateur.
# Ce script génère des certificats reconnus par les machines locales.
# ─────────────────────────────────────────────────────────────────
set -euo pipefail

cd "$(dirname "$0")/.."
CERT_DIR="certs"

if ! command -v mkcert >/dev/null 2>&1; then
  echo "❌ mkcert n'est pas installé."
  echo "   macOS : brew install mkcert && brew install nss   (nss pour Firefox)"
  echo "   Puis relancez ce script."
  exit 1
fi

mkdir -p "$CERT_DIR"

# Autorité locale de confiance (une seule fois par machine)
mkcert -install

# Détecte l'IP locale pour couvrir l'accès depuis le LAN
LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || hostname -I 2>/dev/null | awk '{print $1}' || echo "")

echo "🔐 Génération des certificats pour : localhost 127.0.0.1 ${LOCAL_IP}"
mkcert -cert-file "$CERT_DIR/versepro.pem" -key-file "$CERT_DIR/versepro-key.pem" \
  localhost 127.0.0.1 ::1 ${LOCAL_IP}

cat <<EOF

✅ Certificats générés dans v2/${CERT_DIR}/

Pour démarrer en HTTPS :

  Backend :
    cd v2/backend && ./venv/bin/python -m uvicorn app.main:app \\
      --host 0.0.0.0 --port 8001 \\
      --ssl-certfile ../certs/versepro.pem --ssl-keyfile ../certs/versepro-key.pem

  Frontend (dev) — ajoutez dans v2/frontend/vite.config.js, section server :
    https: {
      cert: '../certs/versepro.pem',
      key: '../certs/versepro-key.pem'
    }

  Les autres postes du LAN doivent installer l'autorité mkcert une fois :
    mkcert -CAROOT   (copier le rootCA.pem sur le poste, puis l'ajouter au trousseau)

EOF
