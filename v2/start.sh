#!/bin/bash
# VersePro v2 - one-click launcher for macOS and Linux.

set -u

GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_PORT="${VERSEPRO_BACKEND_PORT:-8001}"
FRONTEND_PORT="${VERSEPRO_FRONTEND_PORT:-3001}"
BACKEND_PID=""
FRONTEND_PID=""

log() {
  echo -e "${BLUE}==>${NC} $1"
}

warn() {
  echo -e "${YELLOW}WARN:${NC} $1"
}

fail() {
  echo -e "${RED}ERREUR:${NC} $1"
  exit 1
}

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

port_busy() {
  lsof -Pi :"$1" -sTCP:LISTEN -t >/dev/null 2>&1
}

url_ok() {
  curl -fsS "$1" >/dev/null 2>&1
}

backend_running() {
  curl -fsS "http://127.0.0.1:$BACKEND_PORT/" 2>/dev/null | grep -q "VersePro v2"
}

wait_for_url() {
  local url="$1"
  local label="$2"
  for _ in $(seq 1 45); do
    if url_ok "$url"; then
      return 0
    fi
    sleep 0.4
  done
  fail "$label ne repond pas encore. Consulte les logs dans $DIR/logs."
}

find_frontend_port() {
  local port="$FRONTEND_PORT"
  while port_busy "$port"; do
    warn "Le port frontend $port est occupe, essai du port suivant."
    port=$((port + 1))
    if [ "$port" -gt 3010 ]; then
      fail "Aucun port frontend libre entre $FRONTEND_PORT et 3010."
    fi
  done
  FRONTEND_PORT="$port"
}

open_browser() {
  local url="$1"
  if [[ "${OSTYPE:-}" == darwin* ]]; then
    open "$url"
  elif [[ "${OSTYPE:-}" == linux-gnu* ]]; then
    xdg-open "$url" >/dev/null 2>&1 || sensible-browser "$url" >/dev/null 2>&1 || true
  fi
}

cleanup() {
  echo
  log "Arret de VersePro..."
  if [ -n "$FRONTEND_PID" ]; then
    kill "$FRONTEND_PID" >/dev/null 2>&1 || true
  fi
  if [ -n "$BACKEND_PID" ]; then
    kill "$BACKEND_PID" >/dev/null 2>&1 || true
  fi
  echo -e "${GREEN}Serveurs lances par ce terminal arretes.${NC}"
}

trap cleanup SIGINT SIGTERM EXIT

clear
echo -e "${BLUE}====================================================${NC}"
echo -e "${BLUE}    🔵 PREPARATION DE VOTRE CONSOLE VERSEPRO V2      ${NC}"
echo -e "${BLUE}====================================================${NC}"
echo -e "  Veuillez patienter pendant le démarrage automatique...\n"

mkdir -p "$DIR/logs"
echo "--- Lancement du $(date) ---" > "$DIR/logs/install.log"

fail_friendly() {
  echo -e "\n${RED}🛑 Oups ! Nous avons rencontré une difficulté lors du lancement.${NC}"
  echo -e "Pas de panique ! Voici comment débloquer la situation :"
  echo -e " 1. Vérifiez que votre ordinateur est connecté à Internet."
  echo -e " 2. Fermez cette fenêtre et relancez VersePro."
  echo -e " 3. Si le problème persiste, le détail de l'erreur se trouve dans :"
  echo -e "    ${YELLOW}$DIR/logs/install.log${NC}"
  echo -e "    Vous pouvez aussi consulter le guide 'Dépannage d'urgence' dans le README.md."
  exit 1
}

# Étape 1 : Analyse Système
echo -e "${BLUE}[1/3]${NC} Analyse des composants système..."
command_exists python3 || fail_friendly "Python 3 n'est pas détecté. Veuillez l'installer."
command_exists node || fail_friendly "Node.js n'est pas détecté. Veuillez l'installer."
command_exists npm || fail_friendly "npm (Node Package Manager) n'est pas détecté."
echo -e "      👉 Composants système vérifiés avec succès."

# Étape 2 : Préparation du moteur (Backend)
echo -e "${BLUE}[2/3]${NC} Préparation du moteur VersePro... (Veuillez patienter)"
cd "$DIR/backend" || fail_friendly "Dossier backend introuvable."

if [ ! -x "venv/bin/python3" ]; then
  python3 -m venv venv >> "$DIR/logs/install.log" 2>&1 || fail_friendly
fi

if [ ! -f "venv/.versepro_deps_installed" ] || [ "requirements.txt" -nt "venv/.versepro_deps_installed" ]; then
  ./venv/bin/python3 -m pip install --upgrade pip >> "$DIR/logs/install.log" 2>&1
  ./venv/bin/python3 -m pip install -r requirements.txt >> "$DIR/logs/install.log" 2>&1 || fail_friendly
  touch "venv/.versepro_deps_installed"
fi

BACKEND_URL="http://127.0.0.1:$BACKEND_PORT/health"
if backend_running; then
  echo -e "      👉 Moteur VersePro déjà actif sur le port $BACKEND_PORT."
elif port_busy "$BACKEND_PORT"; then
  fail_friendly "Le port de communication $BACKEND_PORT est actuellement occupé."
else
  ./venv/bin/python3 -m uvicorn app.main:app --host 127.0.0.1 --port "$BACKEND_PORT" > "$DIR/logs/backend.log" 2>&1 &
  BACKEND_PID=$!
  wait_for_url "$BACKEND_URL" "Backend" >> "$DIR/logs/install.log" 2>&1 || fail_friendly
  echo -e "      👉 Moteur démarré avec succès."
fi

# Étape 3 : Préparation de l'interface (Frontend)
echo -e "${BLUE}[3/3]${NC} Lancement de l'interface visuelle..."
cd "$DIR/frontend" || fail_friendly "Dossier frontend introuvable."

if [ ! -d "node_modules" ]; then
  npm install >> "$DIR/logs/install.log" 2>&1 || fail_friendly
fi

find_frontend_port
FRONTEND_URL="http://127.0.0.1:$FRONTEND_PORT"

VITE_BACKEND_PORT="$BACKEND_PORT" npm run dev -- --host 127.0.0.1 --port "$FRONTEND_PORT" > "$DIR/logs/frontend.log" 2>&1 &
FRONTEND_PID=$!
wait_for_url "$FRONTEND_URL" "Frontend" >> "$DIR/logs/install.log" 2>&1 || fail_friendly

open_browser "$FRONTEND_URL"

echo -e "\n${GREEN}====================================================${NC}"
echo -e "${GREEN}  🟢 VERSEPRO EST PRET ET EN COURS D'EXECUTION !      ${NC}"
echo -e "  Adresse de la console : $FRONTEND_URL"
echo -e "  Logs d'exécution      : $DIR/logs"
echo -e "  Ne fermez pas cette fenêtre pour maintenir l'application active."
echo -e "${GREEN}====================================================${NC}"

while true; do
  sleep 1
done
