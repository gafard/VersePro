# VersePro V2 - Guide complet

> État de référence : 28 juillet 2026  
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
- préparation de Whisper local pour les accents, le multilingue et le bruit ;
- préparation de Vosk français large comme moteur continu de secours ;
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

### À l'antenne

Cette zone montre exactement la scène de projection, avec navigation dans un
passage long. Elle peut défiler pour garder tous les versets lisibles.
**Effacer** rend immédiatement les sorties noires.

### Déroulé préparé

Dans la barre de recherche, saisir une référence puis appuyer sur `Entrée`
ajoute le passage au **Déroulé du culte** sans le projeter. Les passages restent
dans l'ordre de préparation et sont conservés entre deux lancements.

Cliquer sur un passage préparé le projette ; le bouton **Projeter** placé près
du champ garde l'envoi immédiat pour les besoins du direct. Un passage peut être
retiré individuellement ou toute la préparation peut être vidée avec annulation.

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

Pour une première installation, utiliser le mode ombre pendant un culte, puis
le mode dimanche sûr. L'automatisation n'est à activer qu'après validation sur
des enregistrements représentatifs de la salle.

## Choisir le moteur vocal

| Moteur | Quand l'utiliser | Limite principale |
| --- | --- | --- |
| Deepgram | Internet stable, faible latence, direct exigeant | Dépend du réseau et d'une clé API |
| Whisper local | Accents, multilingue, musique ou bruit, confidentialité | Traitement par fenêtres de 2,4 s par défaut |
| Vosk local large | Secours français continu, CPU modéré | Moins robuste que Whisper sur les accents et environnements complexes |
| Auto | Deepgram puis moteur local déjà préparé | La qualité du repli dépend du modèle téléchargé |

La rapidité réelle dépend du poste, du réseau et de la salle. Elle doit être
mesurée avec le préflight et des extraits audio du lieu, pas déduite du seul nom
du moteur.

## Sorties

Dans l'application empaquetée, le backend local écoute par défaut sur le port
`17871`. En développement, il écoute généralement sur `8001`.

| Sortie | Adresse ou connexion |
| --- | --- |
| Écran autonome | `http://127.0.0.1:17871/projection` |
| Source navigateur OBS | `http://127.0.0.1:17871/obs?theme=lower-third&bg=transparent` |
| Moniteur scène | `http://127.0.0.1:17871/stage` |
| ProPresenter | Hôte, port et message configurés dans Paramètres |
| vMix | API HTTP et entrée titre configurées dans Paramètres |
| NDI | Sortie native facultative si le runtime NDI est installé |

OBS doit utiliser la source navigateur locale sur le même poste. Le pont
ProPresenter peut viser une autre machine du réseau local. Chaque pilote renvoie
un reçu de succès ou d'échec ; un échec n'est pas présenté comme une projection
réussie.

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
venv/bin/python -m pytest -q
venv/bin/python benchmarks/run_detection_benchmark.py --fail-below-f1 0.95

cd ../frontend
npm test
npm run build
cd src-tauri
cargo check --locked
```

État vérifié le 28 juillet 2026 :

- backend : 179 tests réussis, 4 ignorés ;
- frontend : 4 tests réussis ;
- Rust : 1 test réussi ;
- audits npm et Python : aucune vulnérabilité connue ;
- corpus textuel : 30 cas sur 30, aucun faux positif, p95 à 18,32 ms.

Ce benchmark textuel protège contre les régressions de détection. Il ne remplace
pas un corpus audio multi-églises, qui reste le prochain investissement
prioritaire.

## Documents liés

- [`README.md`](README.md) : démarrage technique et contrats principaux ;
- [`EXPLICATION_ARCHITECTURE.md`](EXPLICATION_ARCHITECTURE.md) : architecture et garanties ;
- [`IMPLEMENTATION.md`](IMPLEMENTATION.md) : carte du code et invariants ;
- [`ROADMAP_INNOVATIONS.md`](ROADMAP_INNOVATIONS.md) : propositions priorisées.
