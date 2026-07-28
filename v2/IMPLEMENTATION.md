# VersePro V2 - Carte d'implémentation

> État de référence : 28 juillet 2026  
> Ce document décrit le code livré. Les travaux futurs sont isolés dans
> [`ROADMAP_INNOVATIONS.md`](ROADMAP_INNOVATIONS.md).

## Vue d'ensemble

```text
Microphone
   |
   v
Web Audio API -> PCM mono 16 kHz -> WebSocket authentifié
   |
   v
ASR Deepgram / Whisper / Vosk
   |
   v
Parser explicite -> recherche lexicale -> e5 ONNX -> LLM fermé
   |
   v
Politique de sûreté -> file de validation -> scène canonique
   |
   +-> Écran web / OBS / moniteur scène
   +-> ProPresenter
   +-> vMix
   +-> NDI
```

Le frontend React est une console de régie. FastAPI porte les pipelines audio,
les règles métier, la persistance et les pilotes de sortie. Tauri lance les deux
composants comme une application desktop signable.

## Modules principaux

| Responsabilité | Emplacement |
| --- | --- |
| Application FastAPI et cycle de vie | `backend/app/main.py` |
| API REST et WebSockets | `backend/app/api/routes.py` |
| Configuration validée | `backend/app/core/config.py` |
| Authentification locale | `backend/app/core/security.py` |
| Transcription cloud | `backend/app/services/deepgram_service.py` |
| Transcription Whisper | `backend/app/services/whisper_service.py` |
| Transcription Vosk | `backend/app/services/vosk_service.py` |
| Parser et recherche de versets | `backend/app/services/verse_parser.py` |
| Embeddings e5 ONNX | `backend/app/services/e5_encoder.py` |
| Fournisseurs LLM | `backend/app/services/llm_service.py` |
| Orchestration des sorties | `backend/app/outputs/manager.py` |
| Écran, OBS et scène | `backend/app/outputs/web.py` |
| ProPresenter, vMix et NDI | `backend/app/outputs/` |
| Base SQLite | `backend/app/services/database.py` |
| Secrets système | `backend/app/services/secret_store.py` |
| Téléchargements vérifiés | `backend/app/services/download_utils.py` |
| Console React | `frontend/src/components/LiveDetection.jsx` |
| Paramètres | `frontend/src/components/Settings.jsx` |
| État global | `frontend/src/store.js` |
| Shell desktop | `frontend/src-tauri/src/main.rs` |

## Démarrage desktop

1. Tauri génère un jeton de session cryptographique.
2. Le backend PyInstaller démarre sur `127.0.0.1:17871` avec ce jeton.
3. Le frontend récupère le jeton par commande Tauri et l'ajoute aux requêtes
   locales ainsi qu'aux WebSockets.
4. Le watchdog contrôle le processus et le relance avec backoff en cas de chute.
5. Les journaux sont écrits dans `backend-desktop.log` du dossier de données.
6. La CSP limite le WebView aux ressources de l'application et au backend local.

Une page web externe ouverte sur le même poste ne peut donc pas envoyer une
commande de projection sans connaître le jeton éphémère.

## Pipeline audio et ASR

Le navigateur demande explicitement l'accès au microphone, sélectionne la
source enregistrée dans Paramètres et convertit le signal en PCM mono 16 kHz.
Chaque paquet alimente :

- le vumètre et les 64 crêtes visuelles de l'onde ;
- le WebSocket audio authentifié ;
- le moteur ASR sélectionné ;
- les événements de transcript intermédiaire et final.

Le filtre audio est désactivé par défaut. Les profils proposés évitent un
traitement agressif qui supprimerait une partie de la voix. Le mode `auto`
essaie Deepgram puis un moteur local déjà préparé ; il ne télécharge jamais un
modèle silencieusement pendant un culte.

## Pipeline de détection

### 1. Référence explicite

Le parser normalise les livres, abréviations, chapitres et plages de versets,
puis vérifie la référence dans le corpus local. C'est le seul type de signal
éligible à l'automatisation, et seulement lorsque le mode dimanche sûr est
désactivé.

### 2. Recherche locale

En fin de phrase, deux voies recherchent dans le texte biblique :

- correspondance lexicale et floue ;
- embedding multilingue e5 exécuté par ONNX Runtime.

La fusion canonise les références, mesure l'accord des moteurs et vérifie le
recouvrement des mots. Les index proviennent du corpus biblique local réel.

### 3. IA de dernier recours

Le LLM ne reçoit pas la Bible entière et ne peut pas inventer une référence. Il
choisit dans un top-k local fermé. Une référence hors liste est rejetée et la
confiance finale est recalibrée avec le score du candidat local.

### 4. Protection asynchrone

Chaque nouveau transcript augmente la génération courante et annule l'analyse
précédente. Une réponse tardive d'un embedding ou d'un LLM ne peut donc ni
écraser la file ni déclencher une projection devenue obsolète.

## Politique de direct

| Signal | Mode dimanche sûr | Mode manuel | Automatisation autorisée |
| --- | --- | --- | --- |
| Référence explicite vérifiée | File | File | Oui, si activée |
| Citation ou paraphrase locale | File | File | Non |
| Proposition LLM | File | File | Non |
| Mode ombre | Journal seulement | Journal seulement | Non |

L'arrêt d'urgence force le mode sûr, arrête le microphone et le suivi lecture,
annule les automatismes et efface la scène canonique.

## Scène et pilotes de sortie

La scène canonique contient la référence, le texte, la version biblique, la
position dans un passage et l'état du suivi lecture. L'écran autonome, OBS et le
moniteur scène consomment le même WebSocket, ce qui évite trois vérités
différentes.

Les pilotes ProPresenter, vMix et NDI sont orchestrés séparément. Chacun renvoie
un reçu structuré. Une sortie en échec ne valide pas globalement la projection ;
la régie peut signaler le problème et conserver une sortie locale fonctionnelle.

Adresses empaquetées :

```text
http://127.0.0.1:17871/projection
http://127.0.0.1:17871/obs?theme=lower-third&bg=transparent
http://127.0.0.1:17871/stage
```

## Configuration, secrets et modèles

- Les réglages non sensibles sont persistés dans SQLite.
- Deepgram, OpenRouter et Gemini utilisent le trousseau du système via
  `keyring`.
- L'API ne renvoie que l'état présent/absent des secrets.
- Gemini reçoit sa clé dans l'en-tête `x-goog-api-key`.
- Les migrations ne suppriment une ancienne clé SQLite qu'après transfert
  confirmé.
- Les téléchargements refusent les redirections non sûres et vérifient
  taille, type et empreinte lorsque celle-ci est connue.
- Whisper, Vosk et e5 ne sont préparés qu'après une action utilisateur.

## Files et persistance

Les files de transcript, de détection et d'écriture sont bornées. La
persistance lente ne doit pas bloquer la boucle audio. Les événements
opérationnels conservent assez de contexte pour diagnostiquer le direct sans
enregistrer automatiquement l'audio du culte.

## Contrats d'extension

Une nouvelle sortie doit :

1. recevoir la scène canonique ;
2. implémenter projection, effacement et santé ;
3. retourner un reçu explicite ;
4. respecter les délais et annulations ;
5. posséder des tests de succès, panne et reprise.

Un nouveau moteur ASR doit :

1. accepter le PCM mono 16 kHz ou documenter sa conversion ;
2. émettre transcript intermédiaire, final et erreurs ;
3. exposer un état de préparation ;
4. ne déclencher aucun téléchargement implicite ;
5. être testable avec un flux WebSocket distant.

Un nouveau moteur sémantique doit :

1. rechercher uniquement dans le corpus local versionné ;
2. retourner référence, score et provenance ;
3. passer par la fusion et la politique de sûreté ;
4. ne jamais disposer d'un chemin direct vers les sorties.

## Tests et seuils

```bash
cd v2/backend
venv/bin/python -m pytest -q
venv/bin/python benchmarks/run_detection_benchmark.py --fail-below-f1 0.95

cd ../frontend
npm test
npm run build

cd src-tauri
cargo test --locked
cargo check --locked
```

La couverture inclut le parser, les références orales, les allusions, la fusion,
le LLM fermé, Whisper, Vosk, les téléchargements, les secrets, la scène web, OBS,
NDI, les commandes de sécurité et le streaming audio WebSocket distant.

Référence vérifiée le 28 juillet 2026 :

- 179 tests backend réussis, 4 ignorés ;
- 4 tests frontend réussis ;
- 1 test Rust réussi ;
- benchmark textuel : 30/30, 0 faux positif, p95 18,32 ms ;
- audits npm et Python : aucune vulnérabilité connue.

## Publication

Le workflow Release construit le frontend, le backend et les paquets Tauri. Il
échoue si les certificats de signature requis ne sont pas disponibles. Les
procédures macOS et Windows sont centralisées dans
[`../SIGNING.md`](../SIGNING.md).

La prochaine étape de distribution est un canal de mise à jour signé. Elle est
définie avec ses critères d'acceptation dans
[`ROADMAP_INNOVATIONS.md`](ROADMAP_INNOVATIONS.md).
