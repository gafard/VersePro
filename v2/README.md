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
- Le bouton d'arrêt d'urgence coupe le micro, les automatisations, l'avance de lecture et efface les sorties.

## Transcription

| Moteur | Usage | Latence typique |
| --- | --- | --- |
| Deepgram | Cloud rapide, recommandé avec Internet stable | sous-seconde selon réseau |
| Nemotron 3.5-ASR | Moteur principal local rapide & précis | streaming neuronal temps réel |
| Vosk local large | Secours français hors ligne | flux continu, CPU modéré |

`Nemotron 3.5-ASR` (transcribe.cpp) est le moteur principal local de VersePro V2. Le modèle est préparé explicitement dans Paramètres. En mode `auto`, VersePro tente Deepgram, puis Nemotron ou un modèle local prêt.

Le navigateur envoie du PCM mono 16 kHz. Le filtre est désactivé par défaut; deux profils conservateurs sont proposés dans Paramètres. L'onde de la régie est dessinée depuis 64 crêtes du buffer PCM réel.

### Windows

Le backend fonctionne sous Windows x64 avec Python 3.13 ou 3.14. Le micro est capturé par le navigateur puis envoyé en PCM par WebSocket : PyAudio n'est donc pas requis et n'est plus installé. Python 3.13 reste recommandé pour la meilleure compatibilité avec les bibliothèques audio optionnelles. Le lancement local se fait avec `start.bat`.

## Détection & Recherche Parallélisée

1. Le parser local traite les références explicites en moins d'une milliseconde.
2. En fin de phrase orale ou dès 2 mots tapés en recherche manuelle, les trois voies s'exécutent **en parallèle immédiat (`asyncio.gather`)** :
   - Voie lexicale locale rapide (inversion d'index BM25) ;
   - Voie sémantique vectorielle (modèle Multilingual e5-base ONNX) ;
   - Voie IA Assistant SmartVerses (détection des allusions narratives : *« fils prodigue »*, *« sang sur les linteaux »*).
3. La fusion canonise les références, vérifie l'accord des moteurs et valide obligatoirement l'existence du verset dans la Bible locale avant toute proposition (anti-hallucination stricte).
4. La barre de saisie manuelle intègre une **autocomplétion interactive** avec prévisualisation des textes et navigation clavier (`↑`/`↓` + `Entrée`).
5. Un bandeau de **10 versets voisins** (5 avant / 5 après, 10 suivants au verset 1, 10 précédents au dernier verset) permet de suivre les sauts de lecture du pasteur en 1 clic.

## Sorties & Mobiles

- Écran autonome salle : `http://127.0.0.1:17871/output`
- Source navigateur OBS : `http://127.0.0.1:17871/obs?theme=lower-third&bg=transparent`
- Moniteur scène pasteur : `http://127.0.0.1:17871/stage`
- Suivi assemblée sur mobile : `http://<IP-LAN>:17871/follow` (accessible via scan du QR Code)
- ProPresenter : pilote backend dédié (API 7.9+ ou protocole v6/v7)
- vMix : API HTTP
- NDI : flux vidéo broadcast natif avec transparence alpha

## Paramètres et secrets

La page Paramètres s'organise en accordéons dépliables par catégorie (Général, Audio, Moteurs, Projection, Sorties, Avancé). Elle rassemble la configuration d'entrée micro, la barrière vocale anti-musique (Silero VAD), les moteurs ASR, l'extraction automatique des notes du sermon (onglet Avancé), les modèles locaux, l'atelier d'habillage, la gestion des Bibles et les sorties (NDI, ProPresenter).

Les clés Deepgram, OpenRouter et Gemini sont stockées dans le gestionnaire de secrets de l'OS via `keyring` (Trousseau macOS). Les anciennes clés SQLite ne sont supprimées qu'après confirmation du transfert. Si le trousseau est indisponible, elles restent dans la base locale plutôt que d'être perdues au lancement suivant. L'API ne renvoie que des indicateurs masqués. Gemini reçoit sa clé dans l'en-tête `x-goog-api-key`, jamais dans l'URL.

## Application desktop

Le paquet Tauri embarque le frontend et le backend PyInstaller. Au lancement:

1. l'animation de logo joue avec son son dans Tauri et reste muette dans le navigateur;
2. le backend démarre sur `127.0.0.1:17871`;
3. un watchdog le relance avec backoff s'il tombe;
4. les journaux desktop vont dans `backend-desktop.log` du dossier de données utilisateur;
5. une CSP restrictive limite le WebView au backend local et aux ressources de l'application.
6. un jeton cryptographique différent à chaque lancement authentifie toutes les commandes locales.

La signature Apple/Windows et la publication des mises à jour exigent les certificats décrits dans [`../SIGNING.md`](../SIGNING.md). Le workflow Release échoue volontairement si un certificat manque : aucun installeur public non signé n'est publié.

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

État de référence au 28 juillet 2026: 179 tests backend réussis, 4 ignorés, 4 tests frontend réussis et 1 test Rust réussi. Les audits npm et Python ne signalent aucune vulnérabilité connue.

## API opérationnelle

- `GET /api/v1/health`: disponibilité du backend
- `GET /api/v1/preflight?probe_cloud=true`: contrôle bloquant avec test réel de Deepgram
- `POST /api/v1/safety/panic`: mode sûr, arrêt des automatismes et effacement des sorties
- `GET|POST /api/v1/settings`: configuration runtime
- `GET /api/v1/asr/status`: préparation Whisper/Vosk
- `POST /api/v1/asr/prepare`: préparation explicite de Whisper
- `POST /api/v1/semantic/prepare`: préparation explicite de l'index ONNX
- `WS /ws/audio`: PCM et événements de transcription
- `WS /ws/output`: scène de projection pour écran et OBS

Voir [`EXPLICATION_ARCHITECTURE.md`](EXPLICATION_ARCHITECTURE.md) pour les contrats internes et [`ROADMAP_INNOVATIONS.md`](ROADMAP_INNOVATIONS.md) pour les améliorations proposées, leurs risques et leurs critères de validation.
