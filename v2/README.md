# VersePro V2

VersePro est une régie biblique de bureau. Elle transcrit la prédication, détecte les références explicites et les citations proches du texte biblique, puis les place dans une file contrôlée par l'opérateur. La V2 peut piloter ProPresenter et fournir ses propres sorties web pour écran, OBS et vMix.

Pour préparer une équipe bénévole, consulter le
[kit de démarrage régie et checklist culte](../docs/KIT-DEMARRAGE-REGIE.md),
ainsi que sa
[version PDF prête à imprimer](../output/pdf/VersePro-Kit-Demarrage-Regie.pdf).

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
| Nemotron 3.5-ASR | Moteur principal local | streaming GGUF via `transcribe.cpp` |
| Vosk local large | Secours français hors ligne | flux continu, CPU modéré |

`Nemotron 3.5-ASR` est le moteur principal local. Le modèle est préparé
explicitement dans Paramètres. En mode `auto`, VersePro tente Deepgram, puis
Nemotron et enfin Vosk si ces moteurs locaux sont déjà prêts. Aucun modèle
lourd n'est téléchargé pendant un direct.

Le navigateur envoie du PCM mono 16 kHz. Le filtre est désactivé par défaut;
deux profils conservateurs sont proposés dans Paramètres. L'onde de la régie
est dessinée depuis 64 crêtes du buffer PCM réel. Il n'existe plus de barrière
Silero VAD : le terrain a montré qu'elle pouvait couper une prédication
accompagnée de musique. La santé du transcript suspend plutôt les déductions
sémantiques lorsqu'il devient durablement haché, sans bloquer l'audio.

### Windows

Le backend fonctionne sous Windows x64 avec Python 3.13 ou 3.14. Le micro est capturé par le navigateur puis envoyé en PCM par WebSocket : PyAudio n'est donc pas requis et n'est plus installé. Python 3.13 reste recommandé pour la meilleure compatibilité avec les bibliothèques audio optionnelles. Le lancement local se fait avec `start.bat`.

## Détection & Recherche Parallélisée

1. Le parser local traite les références explicites en moins d'une milliseconde.
2. En fin de phrase orale, les voies locales recherchent le verset dans des
   fenêtres récentes. Dans la recherche manuelle, le moteur lexical répond dès
   2 caractères; e5 et l'assistant sont ajoutés dès 2 mots. Ces voies
   s'exécutent en parallèle avec un budget de 5 secondes pour l'IA :
   - Voie lexicale locale rapide (inversion d'index BM25) ;
   - Voie sémantique vectorielle (modèle Multilingual e5-base ONNX) ;
   - Voie IA Assistant SmartVerses (détection des allusions narratives : *« fils prodigue »*, *« sang sur les linteaux »*).
3. La fusion canonise les références, vérifie l'accord des moteurs et valide obligatoirement l'existence du verset dans la Bible locale avant toute proposition (anti-hallucination stricte).
4. La barre de saisie manuelle intègre une **autocomplétion interactive** avec
   prévisualisation des textes et navigation clavier (`↑`/`↓` + `Entrée`).
   `Entrée` projette; le bouton **Préparer** charge la prévisualisation sans
   toucher à la sortie publique.
5. Un bandeau de **10 versets voisins** (5 avant / 5 après, 10 suivants au verset 1, 10 précédents au dernier verset) permet de suivre les sauts de lecture du pasteur en 1 clic.
6. Le **déroulé du culte** est persisté dans le navigateur et transmis au
   moteur. Il sert de contexte pour départager deux numéros de verset du même
   chapitre; il ne rend jamais une suggestion probabiliste automatique.

## Sorties & Mobiles

- Écran autonome salle : `http://127.0.0.1:17871/output`
- Source navigateur OBS : `http://127.0.0.1:17871/obs?theme=lower-third&bg=transparent`
- Moniteur scène pasteur : `http://127.0.0.1:17871/stage`
- Suivi lecture : `http://127.0.0.1:17871/follow`
- ProPresenter : pilote backend dédié (API 7.9+ ou protocole v6/v7)
- vMix : API HTTP
- NDI : flux vidéo broadcast natif avec transparence alpha

`/follow` et `/stage` existent et le QR code détecte les interfaces réseau,
mais le backend desktop 2.1.8 écoute encore uniquement sur `127.0.0.1`. L'accès
depuis un téléphone du LAN n'est donc pas une garantie livrée; il exige encore
un listener public séparé et protégé.

## Paramètres et secrets

La page Paramètres s'organise en catégories (Général, Audio, Moteurs,
Projection, Sorties, Avancé). Elle rassemble l'entrée micro, les profils audio,
les moteurs ASR, l'extraction des références depuis les notes du sermon, les
modèles locaux, l'atelier d'habillage, la gestion des Bibles et les sorties.

Les clés Deepgram, OpenRouter et Gemini sont stockées dans le gestionnaire de secrets de l'OS via `keyring` (Trousseau macOS). Les anciennes clés SQLite ne sont supprimées qu'après confirmation du transfert. Si le trousseau est indisponible, elles restent dans la base locale plutôt que d'être perdues au lancement suivant. L'API ne renvoie que des indicateurs masqués. Gemini reçoit sa clé dans l'en-tête `x-goog-api-key`, jamais dans l'URL.

## Application desktop

Le paquet Tauri embarque le frontend et le backend PyInstaller. Au lancement:

1. l'animation de logo joue avec son son dans Tauri et reste muette dans le navigateur;
2. le backend démarre sur `127.0.0.1:17871`;
3. un watchdog le relance avec backoff s'il tombe;
4. les journaux desktop vont dans `backend-desktop.log` du dossier de données utilisateur;
5. une CSP restrictive limite le WebView au backend local et aux ressources de l'application;
6. un jeton cryptographique différent à chaque lancement authentifie les commandes locales;
7. l'Updater Tauri vérifie les nouvelles versions signées et refuse toute
   installation pendant que le micro ou une sortie est actif.

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
venv/bin/python -m pytest tests -q
venv/bin/python benchmarks/run_detection_benchmark.py --fail-below-f1 0.95
venv/bin/python benchmarks/replay_lab.py --corpus corpus/ --sans-audio
```

La suite couvre le parser, la fusion, l'IA fermée, Nemotron, Vosk, les
téléchargements sûrs, la projection web, OBS et un flux audio WebSocket distant
avec jeton.

État vérifié le 22 août 2026 : 313 tests backend réussis et 3 ignorés, 24 tests
frontend réussis, build Vite valide. Le benchmark historique passe 30/30; le
Replay Lab terrain obtient 86,1 % d'exactitude, 89,3 % de précision et 80,7 %
de rappel sur 43 cas. Ces métriques ne sont pas interchangeables.

## API opérationnelle

- `GET /api/v1/health`: disponibilité du backend
- `GET /api/v1/preflight?probe_cloud=true`: contrôle bloquant avec test réel de Deepgram
- `POST /api/v1/safety/panic`: mode sûr, arrêt des automatismes et effacement des sorties
- `GET|POST /api/v1/settings`: configuration runtime
- `GET /api/v1/asr/status`: état de Nemotron et Vosk
- `POST /api/v1/asr/prepare`: préparation explicite d'un moteur local
- `POST /api/v1/semantic/prepare`: préparation explicite de l'index ONNX
- `GET /api/v1/bible/search`: recherche manuelle unifiée, sans projection
- `POST /api/v1/plan`: transmet le déroulé préparé au moteur de référence
- `GET /api/v1/network/info`: interfaces et URL proposées pour les écrans
- `WS /ws/audio`: PCM et événements de transcription
- `WS /ws/output`: scène de projection pour écran et OBS

Voir [`EXPLICATION_ARCHITECTURE.md`](EXPLICATION_ARCHITECTURE.md) pour les contrats internes et [`ROADMAP_INNOVATIONS.md`](ROADMAP_INNOVATIONS.md) pour les améliorations proposées, leurs risques et leurs critères de validation.
