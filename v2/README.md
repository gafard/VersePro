# VersePro V2

VersePro est une régie biblique de bureau. Elle transcrit la prédication, détecte les références explicites et les citations proches du texte biblique, puis les place dans une file contrôlée par l'opérateur. La V2 peut piloter ProPresenter et fournir ses propres sorties web pour écran, OBS et vMix.

## Garanties de direct

- Une référence explicite vérifiée est le seul signal éligible à une projection automatique.
- Le mode dimanche sûr, activé par défaut, bloque même cette automatisation.
- Le mode ombre mesure les détections sans piloter aucune sortie.
- Les recherches floues, embeddings et réponses LLM vont toujours en validation manuelle.
- Le LLM choisit dans une liste fermée de versets locaux; toute autre référence est rejetée.
- Chaque nouveau transcript invalide et annule l'analyse précédente. Un résultat ancien ne peut plus projeter.
- Les files transcript et persistance sont bornées pour résister à un débit prolongé.
- Le bouton d'arrêt d'urgence coupe le micro et toutes les automatisations.

## Transcription

| Moteur | Usage | Latence typique |
| --- | --- | --- |
| Deepgram | Cloud rapide, recommandé avec Internet stable | sous-seconde selon réseau |
| Whisper local | Accents, multilingue, débit rapide, bruit | fenêtres de 2,4 s par défaut |
| Vosk local small | Secours léger et références explicites | flux continu, faible CPU |

`Whisper` est un vrai chemin `faster-whisper`, plus un alias de Vosk. Le modèle est choisi selon la mémoire de la machine (`tiny`, `base` ou `small`) et n'est téléchargé qu'après une action explicite dans Paramètres. Vosk small est également préparé explicitement. En mode `auto`, VersePro tente Deepgram, puis un modèle local déjà prêt.

Le navigateur envoie du PCM mono 16 kHz. Le filtre est désactivé par défaut; deux profils conservateurs sont proposés dans Paramètres. L'onde de la régie est dessinée depuis 64 crêtes du buffer PCM réel.

## Détection

1. Le parser local traite les références explicites en moins d'une milliseconde.
2. En fin de phrase, le moteur lexical/flou et l'encodeur e5 ONNX recherchent dans le corpus réel.
3. La fusion canonise les références, vérifie l'accord des moteurs et le recouvrement des mots.
4. Si la chaîne locale reste muette, l'IA peut départager un top-k local. Sa confiance est recalibrée par le score du candidat et ne vient jamais seule du modèle.

Le benchmark de production utilise exactement cette cascade:

```bash
cd v2/backend
venv/bin/python benchmarks/run_detection_benchmark.py --fail-below-f1 0.95
```

Corpus de contrôle actuel: 30 cas, 100 % exacts, 0 faux positif, p95 mesuré à 99 ms sur le poste de développement avec ONNX actif. Ce corpus est un test de non-régression textuel, pas une preuve de performance sur toutes les acoustiques d'église. Un corpus audio réel plus large reste nécessaire avant toute revendication commerciale.

## Sorties

- Écran autonome: `http://127.0.0.1:8001/projection`
- Source navigateur OBS: `http://127.0.0.1:8001/obs?theme=lower-third&bg=transparent`
- Moniteur scène: `http://127.0.0.1:8001/stage`
- ProPresenter: pilote backend dédié
- vMix: API HTTP si activée

La source OBS écoute le même flux de projection que l'écran autonome et ne dépend pas de ProPresenter.

## Paramètres et secrets

La page Paramètres contient l'entrée micro, le prétraitement audio, les moteurs ASR, les modèles locaux, les versions bibliques, le rendu, les sorties et les fournisseurs IA. Ces éléments n'encombrent pas la régie live.

Les clés Deepgram, OpenRouter et Gemini sont stockées dans le gestionnaire de secrets de l'OS via `keyring` (Trousseau macOS). Les anciennes clés SQLite sont migrées puis supprimées. Sans gestionnaire sécurisé, une clé saisie reste seulement en mémoire pour la session. L'API ne renvoie que des indicateurs masqués. Gemini reçoit sa clé dans l'en-tête `x-goog-api-key`, jamais dans l'URL.

## Application desktop

Le paquet Tauri embarque le frontend et le backend PyInstaller. Au lancement:

1. l'animation de logo reste toujours muette;
2. le backend démarre sur `127.0.0.1:17871`;
3. un watchdog le relance avec backoff s'il tombe;
4. les journaux desktop vont dans `backend-desktop.log` du dossier de données utilisateur;
5. une CSP restrictive limite le WebView au backend local et aux ressources de l'application.

La signature Apple/Windows et la publication des mises à jour exigent les certificats décrits dans [`../SIGNING.md`](../SIGNING.md). Aucun logiciel ne peut produire une signature de confiance sans ces secrets externes.

## Développement

```bash
# backend
cd v2/backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8001

# frontend, dans un autre terminal
cd v2/frontend
npm install
VITE_BACKEND_PORT=8001 npm run dev -- --host 127.0.0.1 --port 3001
```

Lanceurs de développement: `Lancer VersePro.command`, `start.sh` et `start.bat`.

## Vérification

```bash
cd v2/frontend
npm test
npm run build
cd src-tauri && cargo check --locked

cd ../../backend
venv/bin/python -m pytest -q
venv/bin/python benchmarks/run_detection_benchmark.py --fail-below-f1 0.95
```

La suite couvre le parser, la fusion, l'IA fermée, Whisper, les téléchargements sûrs, la projection web, OBS et un flux audio WebSocket distant avec jeton.

## API opérationnelle

- `GET /api/v1/health`: disponibilité du backend
- `GET /api/v1/preflight`: contrôle bloquant avant direct
- `POST /api/v1/safety/panic`: arrêt des automatisations
- `GET|POST /api/v1/settings`: configuration runtime
- `GET /api/v1/asr/status`: préparation Whisper/Vosk
- `POST /api/v1/asr/prepare`: préparation explicite de Whisper
- `POST /api/v1/semantic/prepare`: préparation explicite de l'index ONNX
- `WS /ws/audio`: PCM et événements de transcription
- `WS /ws/output`: scène de projection pour écran et OBS

Voir [`EXPLICATION_ARCHITECTURE.md`](EXPLICATION_ARCHITECTURE.md) pour les contrats internes.
