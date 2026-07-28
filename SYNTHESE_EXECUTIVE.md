# Synthèse exécutive VersePro V2

État au 28 juillet 2026.

## Décision

VersePro V2 n'est plus un prototype de transcription relié à ProPresenter. C'est
une régie desktop hybride qui possède son propre moteur de sortie, fonctionne en
local ou dans le cloud et impose une politique de validation avant projection.

La priorité stratégique n'est plus d'ajouter rapidement des fonctions. Elle est
de démontrer la robustesse sur un corpus audio multi-églises, puis de transformer
les incidents réels en tests reproductibles.

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
- préflight avant direct;
- mode sûr par défaut, mode ombre et arrêt d'urgence;
- écran de secours, moniteur scène et source navigateur OBS.

### Intelligence

- parser de références explicites;
- recherche lexicale et floue;
- embeddings e5 ONNX locaux;
- fusion de classements et vérification du recouvrement;
- arbitrage LLM limité à une liste de versets locaux;
- Deepgram, faster-whisper et Vosk;
- annulation générationnelle des analyses devenues obsolètes.

### Production

- sorties Web, OBS, vMix, ProPresenter et NDI optionnel;
- scène canonique partagée entre toutes les sorties;
- accusé par sortie avant de marquer une carte comme projetée;
- source navigateur OBS indépendante de ProPresenter;
- watchdog du backend avec reprise;
- session locale authentifiée par jeton aléatoire 256 bits.

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
| Tests backend | 179 réussis, 4 ignorés |
| Tests frontend | 4 réussis |
| Test Rust | 1 réussi |
| Audit npm | aucune vulnérabilité connue |
| Audit Python | aucune vulnérabilité connue |
| Benchmark textuel | 30/30, aucun faux positif |
| Latence cascade textuelle | p95 18,32 ms avec ONNX |
| Contrôle visuel | desktop, largeur minimale Tauri et mobile sans débordement |

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

1. Le corpus principal de non-régression reste textuel.
2. Whisper CPU ajoute environ une fenêtre de latence.
3. Vosk large demande environ 1,4 Go et du CPU.
4. Les allusions narratives restent difficiles sans contexte structuré.
5. NDI dépend d'un runtime externe.
6. La signature nécessite des certificats Apple et Windows externes.
7. La mise à jour signée intégrée n'est pas encore livrée.
8. Le pont OBS actuel fournit la vidéo mais ne contrôle pas encore OBS via son
   WebSocket.

## Risques

| Risque | Réponse actuelle | Travail restant |
|---|---|---|
| Mauvais verset projeté | mode sûr et validation | corpus audio terrain |
| Réseau instable | moteurs locaux et backoff | course ASR mesurée |
| Mauvais micro | Paramètres et préflight | calibration par salle |
| Panne difficile à expliquer | logs et états | diagnostic partageable |
| Parc non homogène | CI et installeurs signés | updater signé |
| Surcharge CPU | choix des modèles | accélération ONNX par matériel |
| Dérive des seuils | mode ombre | enveloppe de confiance locale |

## Trois investissements prioritaires

### 1. Replay Lab et corpus audio

Rejouer un culte dans le pipeline réel, annoter les références attendues et
comparer les versions. C'est le socle scientifique de toutes les optimisations.

### 2. Diagnostic et profils de salle

Permettre au bénévole de préparer une salle en quelques minutes et d'exporter un
rapport sans terminal lorsqu'un incident survient.

### 3. Mise à jour signée

Distribuer les correctifs avec vérification cryptographique et installation
différée hors session active.

## Innovations différenciantes

- jumeau de culte rejouable;
- course ASR cloud/local avec arbitre temporel;
- pont OBS WebSocket 5 avec preuve de visibilité;
- seuils recommandés à partir du mode ombre;
- VerseGraph contextuel pour récits et enchaînements;
- sorties bilingues distinguant Bible officielle et traduction automatique;
- Companion local à jeton éphémère;
- apprentissage local des corrections sans transfert du sermon.

Les critères, garde-fous et phases sont détaillés dans
[v2/ROADMAP_INNOVATIONS.md](v2/ROADMAP_INNOVATIONS.md).

## Recommandation

Ne pas lancer simultanément toutes les innovations. Livrer d'abord le Replay
Lab, le diagnostic et la mise à jour signée. Ensuite seulement, utiliser les
mesures obtenues pour décider si la course ASR, l'accélération ONNX ou
VerseGraph apportent un gain réel.

Le meilleur positionnement de VersePro n'est pas "une IA qui sait tout". C'est
"la couche temps réel qui comprend, sécurise et distribue l'Écriture pendant un
direct".
