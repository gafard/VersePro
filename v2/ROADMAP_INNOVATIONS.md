# Feuille de route VersePro V2

État de référence : 22 août 2026, version 2.1.8.

Ce document sépare les améliorations nécessaires pour fiabiliser le produit des
innovations qui peuvent réellement différencier VersePro. Une idée n'entre pas
dans la feuille de route parce qu'elle paraît spectaculaire: elle doit réduire
la charge mentale du bénévole, augmenter la continuité du direct ou améliorer
une mesure vérifiable.

## Cap produit

VersePro ne doit pas devenir un logiciel généraliste de présentation. Son rôle
est plus précis:

> comprendre la parole en temps réel, préparer la bonne Écriture et livrer une
> scène sûre à tous les outils de régie.

Les principes non négociables restent:

1. une suggestion probabiliste ne se projette jamais seule;
2. toute automatisation peut être coupée en un geste;
3. le fonctionnement dégradé doit rester utile sans Internet;
4. aucun téléchargement, entraînement ou mise à jour lourde ne démarre pendant
   un culte;
5. les gains sont mesurés sur de l'audio réel, pas seulement sur des phrases
   écrites;
6. la confidentialité du sermon et de l'assemblée est le défaut.

## Point de départ

La V2 possède déjà:

- un paquet desktop Tauri avec backend surveillé;
- Deepgram, Nemotron 3.5-ASR local et Vosk local;
- une cascade explicite, lexicale, sémantique ONNX et IA fermée;
- un mode sûr, un mode ombre et un arrêt d'urgence;
- des sorties Web, OBS, vMix, ProPresenter et NDI optionnel;
- une source navigateur OBS autonome;
- un préflight et une page Paramètres;
- une file transactionnelle qui attend l'accusé du moteur d'affichage;
- une prévisualisation distincte de l'antenne, un déroulé persistant et un plan
  de prédication transmis au moteur;
- l'autocomplétion manuelle, la recherche parallèle et dix versets voisins;
- un Replay Lab de 43 cas et un corpus extensible par incident;
- VerseGraph pour le passage ouvert et la détection de contradictions de verset;
- un Updater Tauri signé, bloqué pendant le direct;
- 313 tests backend, 24 tests frontend et les contrôles Rust/Tauri réussis;
- un benchmark historique de 30 cas à 100 %, p95 33,87 ms;
- un Replay Lab à 86,1 % d'exactitude, 89,3 % de précision et 80,7 % de rappel.

La principale dette n'est donc plus l'absence de fonctions. C'est le manque de
preuve audio multi-églises, les six cas encore manqués dans Replay Lab, le
diagnostic automatique et l'accès LAN mobile encore annoncé avant d'être
réellement exposé par le paquet desktop.

## Priorités

| Priorité | Initiative | État | Valeur principale | Complexité |
|---|---|---|---|---|
| P0 | Corpus audio multi-églises | Replay Lab livré, collecte à étendre | prouver la robustesse réelle | élevée |
| P0 | Rapport diagnostic partageable | à faire | résoudre une panne sans terminal | moyenne |
| P0 | Accès LAN public séparé | QR présent, listener absent | rendre `/follow` réellement mobile | moyenne |
| P0 | Profils de salle et calibration | à faire | démarrage fiable en cinq minutes | moyenne |
| P0 | Chaîne de mise à jour signée | code livré, certificats/terrain à valider | corriger le parc sans réinstaller | moyenne |
| P1 | Pont OBS WebSocket 5 | à faire | contrôler et vérifier OBS nativement | moyenne |
| P1 | Course ASR cloud/local | à faire | continuité et meilleur délai utile | élevée |
| P1 | Santé audio composite | proxy longueur livré | réduire les silences et faux positifs | élevée |
| P1 | Accélération ONNX par matériel | à faire | réduire CPU, chauffe et latence | moyenne |
| P2 | VerseGraph enrichi | base livrée | mieux traiter récits et enchaînements | élevée |
| P2 | Sorties bilingues synchronisées | partiel | servir les assemblées multilingues | élevée |
| P2 | Companion local sécurisé | lecture seule partielle | validation depuis tablette | moyenne |
| P2 | Apprentissage local des corrections | à faire | s'adapter à chaque église | élevée |

## P0 - Fiabilité démontrable

### 1. Corpus audio multi-églises et Replay Lab

**État livré**

`benchmarks/replay_lab.py` charge les dossiers `corpus/cas`, rejoue le texte ou
un fichier audio local, capture un incident et compare deux rapports. Le corpus
compte 43 cas, dont des accents, allusions, débits et négatifs issus du terrain.
La mesure actuelle est volontairement imparfaite : 86,1 % d'exactitude, 89,3 %
de précision et 80,7 % de rappel, avec six cas manqués.

**Travail restant**

Étendre le laboratoire au trajet complet et à un jeu de validation séparé :

- importer un enregistrement autorisé;
- rejouer le PCM à vitesse réelle ou accélérée dans le même WebSocket que le
  direct;
- afficher transcript, détections, latences, moteur choisi et sorties;
- annoter les références attendues et les faux positifs;
- comparer deux versions de VersePro sur le même culte, fonction déjà amorcée;
- exporter un rapport JSON anonymisable.

**Valeur différenciante**

Le "jumeau de culte" transforme un incident du dimanche en test de non-régression
rejouable. C'est plus défendable qu'une promesse générale d'IA révolutionnaire.

**Critères de validation**

- au moins 20 heures autorisées provenant de 8 salles différentes;
- accents francophones variés, musique de fond et débit rapide;
- mesure du rappel, de la précision, du délai parole-vers-file et du délai
  validation-vers-écran;
- aucun faux positif projeté en mode sûr;
- rapport reproductible en CI sur un sous-corpus libre de droits.

### 2. Rapport diagnostic partageable

**Problème**

Un bénévole voit "serveur déconnecté" ou "PP manuel", mais le développeur a
besoin de connaître les versions, ports, périphériques, sorties et dernières
erreurs sans demander d'ouvrir un terminal.

**Proposition**

Ajouter dans Paramètres un bouton `Créer un diagnostic` qui produit une archive:

- santé des services et résultat du préflight;
- versions VersePro, OS, Tauri, moteurs et modèles;
- périphérique audio sélectionné, sans enregistrer l'audio;
- état des sorties et latences de connexion;
- derniers journaux expurgés des secrets;
- identifiant aléatoire de diagnostic, jamais une identité utilisateur.

**Critères de validation**

- aucune clé, aucun transcript et aucun chemin personnel dans l'archive;
- diagnostic généré même si le backend principal est indisponible;
- lecture claire par une personne non technique avant l'envoi.

### 3. Mise à jour signée intégrée

**État livré**

Le plugin Updater Tauri, la clé publique, l'endpoint GitHub Releases, les
artefacts signés et le dialogue opérateur sont câblés. L'installation est
refusée côté interface et côté Rust lorsque le micro ou l'antenne est actif.

**Travail restant**

Valider la chaîne de publication réelle :

- artefacts de mise à jour signés;
- endpoint HTTPS;
- certificats Apple et Windows configurés;
- canal stable testé sur deux versions successives;
- canal bêta explicite si le parc le justifie;
- téléchargement hors culte uniquement;
- installation après confirmation, jamais pendant une session active;
- retour arrière documenté au niveau des données.

La mise à jour n'est donc plus une innovation à développer, mais une chaîne de
distribution à exercer et superviser.

**Critères de validation**

- signature invalide refusée;
- mise à jour différée quand une session est active;
- migration et retour arrière testés avec une copie de la base;
- test réel macOS et Windows avant ouverture du canal stable.

### Accès LAN public séparé

**Problème**

Le QR code calcule correctement l'adresse Wi-Fi/Ethernet, mais le sidecar Tauri
écoute sur `127.0.0.1`. Le téléphone reçoit donc une URL que le paquet desktop
n'expose pas sur le réseau.

**Proposition**

- conserver l'API de commande sur loopback avec le jeton éphémère;
- ouvrir un second listener LAN limité aux pages `/follow`, `/stage`, aux
  polices et au WebSocket de lecture;
- afficher l'état du pare-feu et tester réellement l'URL avant de montrer le QR;
- permettre de désactiver complètement l'écoute LAN.

**Critères de validation**

- téléphone réel testé sur macOS et Windows;
- aucune route de commande joignable sans jeton depuis le LAN;
- changement de réseau et adresses multiples gérés sans redémarrage;
- extinction du listener à la fermeture de VersePro.

### 4. Profils de salle et calibration

**Problème**

Le bon micro, le filtre et le moteur dépendent du lieu. Les régler chaque
dimanche augmente le risque.

**Proposition**

Créer des profils `Sanctuaire`, `Salle des jeunes`, `Répétition` contenant:

- entrée audio et mode de filtre;
- moteur ASR et modèle local de secours;
- sortie principale, thème, version biblique et mode sûr;
- seuils recommandés issus du mode ombre;
- test de dix secondes qui mesure niveau, bruit, saturation et délai réseau.

Le système propose un réglage; il ne modifie jamais silencieusement un profil
validé.

**Critères de validation**

- sélection du profil et préflight en moins de cinq minutes;
- restauration exacte du dernier profil connu;
- aucun changement automatique pendant le direct.

## P1 - Différenciation opérationnelle

### 5. Pont OBS WebSocket 5

La source navigateur fournit déjà la vidéo. Le pont natif ajouterait le contrôle
et la preuve d'état:

- vérifier que la source VersePro existe et qu'elle est visible;
- détecter la scène programme et la scène prévisualisation;
- afficher le statut stream/enregistrement dans le préflight;
- activer ou masquer le bandeau par lot synchronisé;
- mettre la source en sécurité pendant un changement de collection.

OBS WebSocket 5 est intégré à OBS 28 et plus, utilise par défaut le port 4455 et
recommande l'authentification:
[obs-websocket officiel](https://github.com/obsproject/obs-websocket).

**Garde-fou**

VersePro ne démarre ni n'arrête un stream automatiquement. Ces commandes restent
des actions importantes avec confirmation.

### 6. Course ASR cloud/local

**Concept**

Pendant les passages difficiles, lancer deux voies:

- voie rapide: Deepgram en streaming;
- voie résiliente: Nemotron ou Vosk local;
- arbitre: stabilité des mots, confiance, retard et continuité;
- fusion: garder les segments finalisés compatibles et signaler les divergences.

Deepgram expose notamment résultats intermédiaires, endpointing, événements VAD,
multicanal et keyterms:
[API Live Audio](https://developers.deepgram.com/reference/speech-to-text/listen-streaming).

**Pourquoi ce n'est pas un simple fallback**

Le fallback attend l'échec. La course mesure en permanence quelle voie fournit
le meilleur résultat utile sans casser la chronologie.

**Garde-fous**

- aucun mélange mot à mot sans alignement temporel;
- budget CPU et coût cloud visibles;
- activation automatique seulement sur machines qualifiées par benchmark;
- retour instantané à une voie unique.

### 7. Accélération ONNX par matériel

**Proposition**

Détecter les fournisseurs ONNX disponibles puis choisir une priorité sûre:

- CoreML/Neural Engine sur Mac compatible;
- DirectML ou WinML sur Windows;
- OpenVINO sur certains processeurs Intel;
- CPU comme repli universel.

ONNX Runtime expose ces accélérateurs derrière la même API:
[Execution Providers](https://onnxruntime.ai/docs/execution-providers/).

Tester aussi la quantification avec corpus de calibration. La documentation
ONNX avertit qu'une quantification peut réduire la précision et parfois ralentir
un ancien matériel:
[Quantification ONNX](https://onnxruntime.ai/docs/performance/model-optimizations/quantization.html).

**Critères de validation**

- gain minimal de 25 % sur p95 ou consommation CPU pour activer un fournisseur;
- perte de rappel inférieure à 0,5 point sur le corpus audio;
- repli CPU automatique après erreur d'initialisation.

### 8. Santé audio composite et enveloppe de confiance

**Concept**

La version actuelle utilise déjà un signal simple : longueur des segments
finaux. Il a fortement réduit les faux positifs sur un culte difficile, mais il
peut confondre prière lente, appel-réponse et mauvais son. La prochaine version
combine, sans enregistrer le contenu :

- longueur et cadence des segments;
- répétitions et diversité lexicale;
- stabilité entre partiels et final;
- saturation, niveau et continuité du signal;
- dérive par rapport aux cultes précédents.

Le réglage devient une recommandation expliquée: "le seuil actuel aurait produit
12 propositions et 0 projection automatique", plutôt qu'un curseur abstrait.

**Garde-fou**

L'enveloppe ne peut jamais élargir seule les droits d'automatisation. Elle peut
seulement proposer un changement à l'administrateur.

## P2 - Innovations de compréhension et de collaboration

### 9. VerseGraph contextuel

**Base livrée**

VerseGraph ancre un chapitre annoncé, recherche dans ce passage et compare le
meilleur verset ancré au meilleur candidat global. Le plan de prédication et la
mémoire des contradictions complètent ce contexte.

**Extension proposée**

Enrichir le graphe local avec:

- versets voisins;
- citations internes;
- personnages, lieux et événements;
- thème du sermon et références déjà validées;
- plan de culte importé.

Le graphe ne remplace pas e5. Il réordonne le top-k local pour comprendre des
allusions comme "Philippe et l'eunuque" ou anticiper le verset suivant d'une
lecture continue.

**Garde-fou**

Une proposition issue du contexte reste manuelle, avec la raison visible:
`même récit que la référence validée il y a 40 secondes`.

### 10. Sorties bilingues synchronisées

Produire une scène canonique contenant:

- texte source;
- traduction validée;
- alignement phrase ou mot;
- règles de longueur par sortie;
- version biblique affichée séparément.

Usages:

- grand écran en français et moniteur scène en anglais;
- bandeau OBS bilingue;
- téléphone de l'assemblée dans sa langue;
- traduction de la prédication distincte du texte biblique officiel.

**Garde-fou**

Ne jamais présenter une traduction générée comme une version biblique éditée.
L'interface doit distinguer `Bible officielle` et `traduction automatique`.

### 11. Companion local sécurisé

Créer une PWA locale à usage limité:

- scanner un QR éphémère depuis la régie;
- voir les suggestions;
- valider, ignorer ou effacer;
- afficher la santé et le compte à rebours;
- expiration automatique à la fin de la session.

Le jeton doit être rotatif, limité aux actions choisies et révocable depuis la
console principale.

### 12. Apprentissage local des corrections

Enregistrer uniquement les décisions:

- suggestion acceptée;
- suggestion rejetée;
- référence remplacée;
- moteur à l'origine;
- caractéristiques de score non textuelles.

Produire des "packs de vocabulaire" locaux: noms bibliques prononcés dans la
région, abréviations et habitudes du prédicateur.

**Interdit par défaut**

- envoyer l'audio ou le sermon vers un service d'entraînement;
- mutualiser des corrections entre églises sans consentement explicite;
- réentraîner en direct;
- modifier les seuils d'automatisation sans validation.

## Séquencement proposé

### Cycle 1 - Preuve et maintenance

1. étendre Replay Lab à plusieurs églises et figer un jeu de validation;
2. corriger les six cas terrain encore manqués sans dégrader les négatifs;
3. diagnostic partageable;
4. listener LAN public séparé et testable;
5. exercer l'Updater signé sur macOS et Windows;
6. profils de salle.

### Cycle 2 - Régie connectée

1. pont OBS WebSocket en lecture seule;
2. contrôle de visibilité avec confirmation;
3. détection des Execution Providers ONNX;
4. benchmark automatique par machine;
5. enveloppe de confiance en mode ombre.

### Cycle 3 - Intelligence contextuelle

1. prototype de course ASR;
2. VerseGraph enrichi en entités et relations;
3. sorties bilingues;
4. Companion local;
5. apprentissage local des corrections.

## Indicateurs de décision

| Mesure | Objectif avant diffusion stable |
|---|---|
| Faux verset projeté en mode sûr | 0 |
| Crash ou blocage sur 100 relectures de deux heures | 0 |
| Reprise backend après crash | moins de 15 s |
| Préparation d'un nouveau poste | moins de 5 min hors téléchargement |
| Délai parole -> file, cloud p95 | moins de 1 s |
| Délai validation -> écran p95 | moins de 150 ms en local |
| Détections explicites manquées | moins de 1 % sur corpus terrain |
| Secrets présents dans diagnostic | 0 |
| Mise à jour non signée acceptée | 0 |

Ces valeurs sont des portes de sortie, pas des statistiques déjà atteintes.

## Idées à ne pas poursuivre maintenant

- un chatbot généraliste dans la régie;
- la projection entièrement autonome de paraphrases;
- la génération de "versets" ou la réécriture créative du texte biblique;
- un remplacement complet de ProPresenter, OBS ou vMix;
- l'enregistrement permanent de tous les cultes;
- des animations plus spectaculaires au détriment de la lecture;
- une marketplace de thèmes avant la preuve audio et la mise à jour signée.

## Décision recommandée

Le meilleur prochain investissement n'est pas un modèle plus gros. Replay Lab
existe; il faut maintenant lui donner un corpus audio multi-églises annoté et
un jeu de validation qui ne sert jamais au réglage. Ce socle rendra chaque
innovation mesurable : nouvelle ASR, accélération ONNX, santé composite,
VerseGraph enrichi ou traduction. En parallèle, le listener LAN et le
diagnostic doivent transformer les promesses visibles dans l'interface en
capacités réellement vérifiables sur le poste d'une église.
