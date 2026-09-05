# Synthèse exécutive VersePro V2

État vérifié au 22 août 2026, version 2.1.8.

## Décision

VersePro V2 n'est plus un prototype de transcription relié à ProPresenter. C'est
une régie desktop hybride qui possède son propre moteur de sortie, fonctionne en
local ou dans le cloud et impose une politique de validation avant projection.

La priorité stratégique n'est plus d'ajouter rapidement des fonctions. Le Replay
Lab et les premiers cas de terrain existent désormais; il faut les étendre à un
corpus audio multi-églises annoté, puis traiter les six échecs encore visibles.

## Proposition de valeur

VersePro écoute la prédication, détecte les références et citations bibliques,
prépare le texte officiel et laisse l'opérateur décider de ce qui passe à
l'écran.

Le produit se place entre:

- le micro et les moteurs de transcription;
- la compréhension biblique et la politique de sécurité;
- l'opérateur et les sorties OBS, vMix, ProPresenter, NDI ou écran autonome.

Il complète les outils de présentation existants au lieu de chercher à tous les
remplacer.

## Ce qui est livré

### Expérience opérateur

- application macOS et Windows basée sur Tauri;
- démarrage du frontend et du backend sans terminal;
- page Paramètres pour micro, moteurs, modèles, Bibles, sorties et clés;
- régie compacte avec niveau audio réel, file, écran actif et transcript;
- prévisualisation séparée de l'antenne, déroulé persistant et plan transmis au
  moteur de référence;
- recherche manuelle avec autocomplétion, fragments, e5 et assistant concurrents;
- navigation directe dans dix versets voisins;
- préflight avant direct;
- mode sûr par défaut, mode ombre et arrêt d'urgence;
- écran de secours, moniteur scène et source navigateur OBS.

### Intelligence

- parser de références explicites;
- recherche lexicale et floue;
- embeddings e5 ONNX locaux;
- fusion de classements et vérification du recouvrement;
- arbitrage LLM limité à une liste de versets locaux;
- Deepgram, Nemotron 3.5-ASR et Vosk;
- santé de transcription qui suspend les déductions profondes sans couper le
  son ni le parseur explicite;
- VerseGraph contextuel et plan de prédication pour les passages déjà ouverts;
- annulation générationnelle des analyses devenues obsolètes.

### Production

- sorties Web, OBS, vMix, ProPresenter et NDI optionnel;
- scène canonique partagée entre toutes les sorties;
- accusé par sortie avant de marquer une carte comme projetée;
- source navigateur OBS indépendante de ProPresenter;
- watchdog du backend avec reprise;
- session locale authentifiée par jeton aléatoire 256 bits.
- mise à jour Tauri signée, différée lorsque le micro ou l'antenne est actif.

### Sécurité et maintenance

- TLS vérifié;
- modèles Vosk et e5 protégés par empreintes SHA-256;
- téléchargements atomiques et extraction anti-Zip-Slip;
- secrets dans le trousseau système quand il est disponible;
- installeurs publics refusés si les certificats de signature manquent;
- audits de dépendances dans la CI.

## Preuves actuelles

| Contrôle | Résultat |
|---|---|
| Tests backend | 313 réussis, 3 ignorés |
| Tests frontend | 24 réussis, build Vite valide |
| Rust/Tauri | tests et `cargo check --locked` réussis |
| Benchmark historique | 30/30, précision et rappel 100 % |
| Latence historique | p95 33,87 ms avec ONNX |
| Replay Lab terrain | 43 cas, exactitude 86,1 %, précision 89,3 %, rappel 80,7 % |
| Latence Replay Lab | p95 29,6 ms |

Ces chiffres prouvent la non-régression couverte par les tests. Ils ne prouvent
pas encore la performance acoustique dans toutes les églises.

## Forces

### Sécurité opérationnelle

Les références explicites vérifiées sont les seules candidates à
l'automatisation. Les recherches sémantiques et l'IA restent dans la file. Le
mode sûr bloque également l'avance automatique.

### Résilience

VersePro possède plusieurs moteurs ASR et son propre écran. Une panne Internet
ou ProPresenter déconnecté ne rend pas la régie inutilisable si un moteur local
est prêt.

### Intégration

Une seule validation alimente plusieurs sorties. La source OBS est déjà
fonctionnelle sans plugin vidéo propriétaire.

### Architecture mesurable

La cascade de production est appelée directement par le benchmark. Les
décisions, sources et confiances sont persistées pour permettre l'analyse.

## Limites honnêtes

1. Le corpus de 43 cas reste surtout textuel et ne couvre pas plusieurs salles.
2. Six cas du Replay Lab sont encore manqués, notamment des allusions et une
   référence enchaînée.
3. Nemotron dépend d'un runtime natif et d'un modèle de 716 Mo; Vosk large
   demande environ 1,4 Go et du CPU.
4. La santé de transcription repose encore sur la longueur des segments, un
   proxy utile mais incomplet.
5. Les pages `/follow` et `/stage` ne sont pas joignables depuis un téléphone
   dans le paquet lié à `127.0.0.1`, malgré l'URL QR calculée.
6. La notarisation Apple et la réputation Windows nécessitent des certificats
   externes.
7. Le pont OBS fournit la vidéo mais ne contrôle pas encore OBS WebSocket.

## Risques

| Risque | Réponse actuelle | Travail restant |
|---|---|---|
| Mauvais verset projeté | mode sûr et validation | corpus audio terrain |
| Réseau instable | moteurs locaux et backoff | course ASR mesurée |
| Mauvais micro | Paramètres et préflight | calibration par salle |
| Panne difficile à expliquer | logs et états | diagnostic partageable |
| Parc non homogène | CI et Updater Tauri | certificats OS et validation terrain |
| Surcharge CPU | choix des modèles | accélération ONNX par matériel |
| Dérive des seuils | mode ombre | enveloppe de confiance locale |

## Trois investissements prioritaires

### 1. Étendre le Replay Lab au vrai audio

Le laboratoire et 43 cas existent. Il faut maintenant annoter des heures audio
provenant de plusieurs églises, séparer apprentissage et validation, puis mesurer
faux positifs par heure, rappel et délai parole-vers-file.

### 2. Diagnostic et profils de salle

Permettre au bénévole de préparer une salle en quelques minutes et d'exporter un
rapport sans terminal lorsqu'un incident survient.

### 3. Accès mobile local protégé

Exposer uniquement les pages de lecture sur un listener LAN distinct, tester le
pare-feu Windows/macOS et conserver toutes les commandes derrière un jeton
éphémère. Le QR code ne doit être annoncé comme opérationnel qu'après ce test.

## Innovations différenciantes

- jumeau de culte rejouable, déjà amorcé par Replay Lab;
- course ASR cloud/local avec arbitre temporel;
- pont OBS WebSocket 5 avec preuve de visibilité;
- seuils recommandés à partir du mode ombre;
- extension de VerseGraph aux entités et relations bibliques;
- sorties bilingues distinguant Bible officielle et traduction automatique;
- Companion local à jeton éphémère;
- apprentissage local des corrections sans transfert du sermon.

Les critères, garde-fous et phases sont détaillés dans
[v2/ROADMAP_INNOVATIONS.md](v2/ROADMAP_INNOVATIONS.md).

## Recommandation

Ne pas lancer simultanément toutes les innovations. Étendre d'abord Replay Lab,
livrer le diagnostic et résoudre proprement l'accès LAN. Utiliser ensuite les
mesures obtenues pour décider si la course ASR, l'accélération ONNX ou un
VerseGraph plus riche apportent un gain réel.

Le meilleur positionnement de VersePro n'est pas "une IA qui sait tout". C'est
"la couche temps réel qui comprend, sécurise et distribue l'Écriture pendant un
direct".
