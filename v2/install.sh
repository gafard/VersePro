#!/bin/bash

# VersePro v2 - Script d'Installation Automatique
# Usage: ./install.sh

set -e

echo "🚀 Installation de VersePro v2..."
echo ""

# Couleurs
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Vérifier Python
echo -e "${BLUE}📦 Vérification de Python...${NC}"
if ! command -v python3 &> /dev/null; then
    echo -e "${YELLOW}⚠️  Python3 non trouvé. Veuillez l'installer.${NC}"
    exit 1
fi
python3 --version
echo ""

# Vérifier Node.js
echo -e "${BLUE}📦 Vérification de Node.js...${NC}"
if ! command -v node &> /dev/null; then
    echo -e "${YELLOW}⚠️  Node.js non trouvé. Veuillez l'installer.${NC}"
    exit 1
fi
node --version
echo ""

# Installation Backend
echo -e "${BLUE}🔧 Installation du Backend...${NC}"
cd backend

if [ ! -d "venv" ]; then
    echo "  Création de l'environnement virtuel..."
    python3 -m venv venv
fi

echo "  Activation du venv..."
source venv/bin/activate

echo "  Installation des dépendances Python..."
pip install --upgrade pip
pip install -r requirements.txt

if [ ! -f ".env" ]; then
    echo "  Création du fichier .env..."
    cp .env.example .env
    echo -e "${YELLOW}⚠️  N'oublie pas d'éditer backend/.env avec ta clé Deepgram !${NC}"
fi

cd ..
echo -e "${GREEN}✅ Backend installé${NC}"
echo ""

# Installation Frontend
echo -e "${BLUE}🔧 Installation du Frontend...${NC}"
cd frontend

if [ ! -d "node_modules" ]; then
    echo "  Installation des dépendances Node.js..."
    npm install
fi

cd ..
echo -e "${GREEN}✅ Frontend installé${NC}"
echo ""

# Résumé
echo "=================================="
echo -e "${GREEN}🎉 Installation terminée !${NC}"
echo "=================================="
echo ""
echo "📋 Prochaines étapes:"
echo ""
echo "1. Édite le fichier backend/.env avec ta clé Deepgram:"
echo -e "   ${YELLOW}nano backend/.env${NC}"
echo ""
echo "2. Lance le backend:"
echo -e "   ${YELLOW}cd backend && source venv/bin/activate && python3 -m app.main${NC}"
echo ""
echo "3. Dans un autre terminal, lance le frontend:"
echo -e "   ${YELLOW}cd frontend && npm run dev${NC}"
echo ""
echo "4. Ouvre ton navigateur sur:"
echo -e "   ${BLUE}http://localhost:3000${NC}"
echo ""
echo "📖 Documentation complète: v2/GUIDE_COMPLET.md"
echo ""
