# VersePro V2 - Guide complet

> État de référence : 22 août 2026
> Public : régisseurs, responsables techniques et personnes chargées du déploiement.

VersePro est une application de régie de bureau. Elle écoute la prédication,
transcrit la voix, détecte des références bibliques et prépare la projection.
La configuration se fait dans l'interface : l'opérateur du dimanche n'a pas à
ouvrir un terminal ni à modifier un fichier `.env`.

Le guide illustré prêt à imprimer reste la référence pour les bénévoles :
[`../docs/GUIDE-UTILISATION.pdf`](../docs/GUIDE-UTILISATION.pdf).

## Installer l'application

Les paquets publics doivent être signés par Selah Studios.

### macOS

1. Ouvrir le fichier `.dmg`.
2. Glisser VersePro dans Applications.
3. Ouvrir VersePro normalement et accepter l'accès au microphone.
4. Si macOS signale une signature inconnue ou invalide, ne pas contourner
   l'avertissement : télécharger à nouveau depuis la source officielle.

### Windows

1. Ouvrir le fichier `.msi` ou `.exe` signé.
2. Vérifier que l'éditeur affiché est Selah Studios.
3. Suivre l'installeur puis accepter l'accès au microphone.
4. Si SmartScreen ne reconnaît pas l'éditeur, ne pas forcer l'exécution :
   vérifier l'origine et la signature du paquet.

La procédure de signature et de publication est décrite dans
[`../SIGNING.md`](../SIGNING.md).

## Premier lancement

L'assistant vérifie les composants locaux et permet de préparer les modèles
sans ligne de commande :

- choix et test de l'entrée microphone ;
- préparation de Nemotron 3.5-ASR pour la transcription neuronale locale haute précision ;
- préparation facultative de Vosk français comme moteur continu de secours ;
- préparation de l'index sémantique e5 ONNX des 31 102 versets ;
- saisie facultative d'une clé Deepgram pour la transcription cloud ;
- choix du mode de projection initial.

Les modèles ne sont téléchargés qu'après une action explicite. Les clés API
sont enregistrées dans le gestionnaire de secrets du système d'exploitation.

## Préparer un culte en cinq minutes

1. Ouvrir **Paramètres > Audio**, choisir la source réelle de la console et
   parler pour vérifier le niveau.
2. Ouvrir **Paramètres > Moteurs**, vérifier qu'un moteur local est prêt ou que
   Deepgram est disponible.
3. Ouvrir **Paramètres > Projection**, conserver le mode dimanche sûr pour une
   validation humaine systématique.
4. Contrôler la sortie prévue : écran autonome, OBS, ProPresenter, vMix ou NDI.
5. Dans la régie, démarrer le micro et dire « Jean chapitre trois verset
   seize ». Vérifier la détection, la validation et l'effacement de l'écran.

Le préflight intégré réalise aussi les contrôles bloquants et peut tester
réellement Deepgram lorsque la transcription cloud est sélectionnée.

## Utiliser la régie

### Console audio

Le bouton micro démarre et arrête l'écoute. Le vumètre et l'onde sont calculés
depuis le signal PCM réel ; ils ne sont pas décoratifs. Les filtres audio sont
désactivés par défaut. Deux profils conservateurs restent disponibles dans
Paramètres pour les salles difficiles.

VersePro ne coupe plus la musique ou les silences avec une barrière vocale
binaire. Cette approche pouvait supprimer une prédication accompagnée. Le son
complet est envoyé à l'ASR; si le transcript devient durablement haché, seules
les propositions sémantiques sont suspendues et l'opérateur est prévenu.

### Transcript direct

Le transcript montre ce que le moteur vocal comprend. Il défile
automatiquement pendant l'écoute et reste consultable. Une mauvaise
transcription explique souvent une détection absente ; une bonne transcription
sans proposition oriente plutôt vers le moteur de détection.

### À valider

Les propositions s'affichent dans une file courte et opérationnelle :

- `Espace` projette la proposition sélectionnée ;
- `Échap` l'écarte ;
- `↑` et `↓` changent de proposition ;
- `/` place le focus dans la recherche manuelle.

Les recherches floues, les embeddings et les réponses IA passent toujours par
cette file. Le LLM ne peut choisir que dans une liste fermée de versets déjà
retrouvés localement.

### Recherche manuelle & Autocomplétion intelligente

La barre de recherche manuelle située en bas de la régie offre deux modes d'action clairs :
- **`[ Projeter ]`** (ou touche **`Entrée`**) : envoie immédiatement le verset à l'écran salle ;
- **`[ Préparer ]`** : charge le verset dans le panneau Préparation sans rien
  afficher au public; le bouton **Envoyer à l'antenne** réalise ensuite le
  passage contrôlé.

Dès 2 caractères, la recherche locale complète les références et fragments.
À partir de 2 mots thématiques (*« brebis perdue »*, *« armure de Dieu »*), e5
et l'assistant peuvent aussi chercher en parallèle. Le volet présente jusqu'à
6 propositions avec aperçu du texte. Utilisez **`↑`** et **`↓`** pour naviguer
et **`Entrée`** pour projeter le candidat sélectionné.

Le **Déroulé du culte** est distinct du panneau Préparation. Il conserve les
lectures prévues entre deux lancements. Les références extraites depuis les
notes du sermon dans **Paramètres > Avancé** y sont ajoutées et transmises au
moteur afin de départager des numéros mal entendus. Elles ne sont jamais
projetées sans action de l'opérateur.

### Bandeau de navigation rapide (10 Versets Voisins)

Dès qu'un passage est projeté à l'antenne, VersePro déploie sous la barre de recherche un bandeau de **10 boutons de versets voisins** :
- **5 versets avant & 5 versets après** au milieu d'un chapitre (ex: `11..15`, `17..21` pour *Jean 3:16*) ;
- **10 versets suivants** si le verset 1 est projeté ;
- **10 versets précédents** si le dernier verset du chapitre est affiché.  
Un simple clic sur un numéro projette le verset instantanément, évitant toute ressaisie au clavier si le pasteur saute d'un verset à l'autre.

### À l'antenne

Cette zone montre exactement la scène de projection, avec navigation dans un passage long. Des outils de surlignage live (🟡 Jaune, 🔴 Rouge, 🧹 Effacer) permettent de mettre en valeur les mots importants à l'écran pendant la prédication. **Effacer** rend immédiatement les sorties noires.

### Suivi lecture

Le suivi lecture illumine progressivement les mots du verset en fonction de la
parole détectée. Désactivé, le verset reste statique. Ce mode n'influence ni la
détection ni la décision de projection.

## Modes de sécurité

| Mode | Comportement |
| --- | --- |
| Dimanche sûr | Mode par défaut : toutes les détections demandent une validation humaine. |
| Ombre | Analyse et mesure sans piloter aucune sortie. |
| Diffusion automatique | Seules les références explicites, vérifiées et éligibles peuvent partir directement. |
| Arrêt d'urgence | Coupe le micro, les automatisations et le suivi, puis efface toutes les sorties. |

## Choisir le moteur vocal

| Moteur | Quand l'utiliser | Caractéristiques |
| --- | --- | --- |
| Deepgram | Internet stable, faible latence, direct exigeant | Modèle Nova-2 / Nova-3 cloud ultra-rapide |
| Nemotron 3.5-ASR | Transcription neuronale locale principale | Haute précision vocale, streaming temps réel local |
| Vosk local large | Secours français continu hors-ligne | Léger en ressources CPU |
| Auto | Tente Deepgram, puis Nemotron ou Vosk | Bascule automatique en cas de coupure Internet |

## Sorties & Mobiles

Dans l'application empaquetée, le backend local écoute par défaut sur le port
`17871`. En développement, il écoute généralement sur `8001`.

| Sortie | Adresse ou connexion | Rôle |
| --- | --- | --- |
| Écran autonome salle | `http://127.0.0.1:17871/output` | Vidéoprojecteur public plein écran (`F11`) |
| Source navigateur OBS | `http://127.0.0.1:17871/obs?theme=lower-third&bg=transparent` | Bandeau direct streaming avec transparence |
| Moniteur scène pasteur | `http://127.0.0.1:17871/stage` | Retour pupitre (verset géant + chrono) |
| Suivi lecture | `http://127.0.0.1:17871/follow` | Page locale; accès téléphone LAN encore expérimental |
| ProPresenter | Hôte, port et message dans Paramètres | Télécommande de l'API ProPresenter 7.9+ |
| vMix | API HTTP et entrée titre dans Paramètres | Intégration régie vMix |
| NDI | Sortie native vidéo IP | Flux broadcast temps réel avec canal alpha |

OBS doit utiliser la source navigateur locale sur le même poste. Le pont
ProPresenter peut viser une autre machine du réseau local. Chaque pilote renvoie
un reçu de succès ou d'échec ; un échec n'est pas présenté comme une projection
réussie.

Les pages `/follow` et `/stage` existent et le QR code propose l'adresse des
interfaces Wi-Fi/Ethernet. Dans le paquet desktop 2.1.8, le backend écoute
encore uniquement sur `127.0.0.1` : un téléphone du réseau ne peut donc pas les
joindre de manière garantie. Utilisez-les sur le poste VersePro jusqu'à la
livraison d'un listener public séparé et protégé.

## Incident pendant le direct

1. Cliquer **Arrêt d'urgence** si le comportement est incohérent.
2. Vérifier le vumètre. S'il ne bouge pas, contrôler la source et l'autorisation
   microphone dans Paramètres.
3. Si le transcript est vide, vérifier le moteur ASR et la connexion réseau.
4. Si ProPresenter est indisponible, basculer sur l'écran autonome ou OBS.
5. Réactiver uniquement le micro, puis reprendre en validation manuelle.

Les journaux desktop sont conservés dans `backend-desktop.log` du dossier de
données utilisateur. Un futur paquet de diagnostic anonymisé est prioritaire
dans [`ROADMAP_INNOVATIONS.md`](ROADMAP_INNOVATIONS.md).

## Développement

```bash
# Terminal 1
cd v2/backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8001

# Terminal 2
cd v2/frontend
npm install
VITE_BACKEND_PORT=8001 npm run dev -- --host 127.0.0.1 --port 3001
```

Le backend Tauri empaqueté est authentifié par un jeton cryptographique
différent à chaque lancement. Les routes de commande et les WebSockets refusent
les clients non authentifiés.

## Vérification de référence

```bash
cd v2/backend
venv/bin/python -m pytest tests -q
venv/bin/python benchmarks/run_detection_benchmark.py --fail-below-f1 0.95
venv/bin/python benchmarks/replay_lab.py --corpus corpus/ --sans-audio

cd ../frontend
npm test
npm run build
cd src-tauri
cargo check --locked
```

État vérifié le 22 août 2026 :

- backend : 313 tests réussis, 3 ignorés ;
- frontend : 24 tests réussis et build Vite valide ;
- Rust/Tauri : tests et contrôle réussis avec `--locked` ;
- benchmark historique : 30 cas sur 30, aucun faux positif, p95 à 33,87 ms ;
- Replay Lab terrain : 43 cas, exactitude 86,1 %, précision 89,3 %, rappel
  80,7 %, p95 29,6 ms.

Ces bancs protègent contre les régressions de détection. Ils ne remplacent pas
un corpus audio annoté provenant de plusieurs églises, qui reste
l'investissement prioritaire.

## Documents liés

- [`README.md`](README.md) : démarrage technique et contrats principaux ;
- [`EXPLICATION_ARCHITECTURE.md`](EXPLICATION_ARCHITECTURE.md) : architecture et garanties ;
- [`IMPLEMENTATION.md`](IMPLEMENTATION.md) : carte du code et invariants ;
- [`ROADMAP_INNOVATIONS.md`](ROADMAP_INNOVATIONS.md) : propositions priorisées.
