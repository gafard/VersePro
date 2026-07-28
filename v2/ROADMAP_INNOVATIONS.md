# Feuille de route VersePro V2

État de référence: 28 juillet 2026.

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
- Deepgram, Whisper local et Vosk local;
- une cascade explicite, lexicale, sémantique ONNX et IA fermée;
- un mode sûr, un mode ombre et un arrêt d'urgence;
- des sorties Web, OBS, vMix, ProPresenter et NDI optionnel;
- une source navigateur OBS autonome;
- un préflight et une page Paramètres;
- une file transactionnelle qui attend l'accusé du moteur d'affichage;
- 179 tests backend, 4 tests frontend et 1 test Rust réussis;
- un benchmark textuel de 30 cas, sans faux positif, p95 à 18,32 ms.

La principale dette n'est donc plus l'absence de fonctions. C'est le manque de
preuve audio multi-églises et de diagnostic automatique quand les conditions
réelles changent.

## Priorités

| Priorité | Initiative | Valeur principale | Complexité | Risque direct |
|---|---|---|---|---|
| P0 | Corpus audio et Replay Lab | prouver la robustesse réelle | élevée | faible |
| P0 | Rapport diagnostic partageable | résoudre une panne sans terminal | moyenne | faible |
| P0 | Mise à jour signée Tauri | corriger le parc sans réinstaller | moyenne | moyen |
| P0 | Profils de salle et calibration | démarrage fiable en cinq minutes | moyenne | faible |
| P1 | Pont OBS WebSocket 5 | contrôler et vérifier OBS nativement | moyenne | moyen |
| P1 | Course ASR cloud/local | continuité et meilleur délai utile | élevée | moyen |
| P1 | Accélération ONNX par matériel | réduire CPU, chauffe et latence | moyenne | faible |
| P1 | Enveloppe de confiance locale | adapter les seuils sans improviser | élevée | moyen |
| P2 | VerseGraph contextuel | mieux traiter allusions et enchaînements | élevée | moyen |
| P2 | Sorties bilingues synchronisées | servir les assemblées multilingues | élevée | moyen |
| P2 | Companion local sécurisé | validation depuis tablette ou Stream Deck | moyenne | moyen |
| P2 | Apprentissage local des corrections | s'adapter à chaque église | élevée | élevé |

## P0 - Fiabilité démontrable

### 1. Corpus audio multi-églises et Replay Lab

**Problème**

Le benchmark actuel mesure la cascade textuelle, pas le trajet complet depuis le
micro. Il ne couvre pas encore les accents, la réverbération, les nappes de
clavier, les chants rapides, les micros saturés ou les coupures réseau.

**Proposition**

Créer un laboratoire de relecture déterministe:

- importer un enregistrement autorisé;
- rejouer le PCM à vitesse réelle ou accélérée dans le même WebSocket que le
  direct;
- afficher transcript, détections, latences, moteur choisi et sorties;
- annoter les références attendues et les faux positifs;
- comparer deux versions de VersePro sur le même culte;
- exporter un rapport JSON anonymisable.

**Innovation**

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

**Problème**

Les installeurs sont protégés, mais corriger un parc de machines exige encore de
télécharger et réinstaller une version.

**Proposition**

Intégrer le plugin updater Tauri avec:

- artefacts de mise à jour signés;
- endpoint HTTPS;
- canal stable par défaut et canal bêta explicite;
- téléchargement hors culte uniquement;
- installation après confirmation, jamais pendant une session active;
- retour arrière documenté au niveau des données.

La documentation Tauri exige une clé publique, des artefacts signés et applique
HTTPS en production:
[Tauri Updater](https://v2.tauri.app/plugin/updater/).

**Critères de validation**

- signature invalide refusée;
- mise à jour différée quand une session est active;
- migration et retour arrière testés avec une copie de la base;
- test réel macOS et Windows avant ouverture du canal stable.

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
- voie résiliente: Vosk ou Whisper local;
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

### 8. Enveloppe de confiance locale

**Concept**

Le mode ombre apprend la distribution des scores d'une salle sans enregistrer le
contenu. Il produit une enveloppe:

- zone sûre;
- zone à validation;
- zone bruit probable;
- dérive par rapport aux cultes précédents.

Le réglage devient une recommandation expliquée: "le seuil actuel aurait produit
12 propositions et 0 projection automatique", plutôt qu'un curseur abstrait.

**Garde-fou**

L'enveloppe ne peut jamais élargir seule les droits d'automatisation. Elle peut
seulement proposer un changement à l'administrateur.

## P2 - Innovations de compréhension et de collaboration

### 9. VerseGraph contextuel

Construire un graphe local reliant:

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

1. Replay Lab minimal;
2. format d'annotation et premiers cultes autorisés;
3. diagnostic partageable;
4. updater signé;
5. profils de salle.

### Cycle 2 - Régie connectée

1. pont OBS WebSocket en lecture seule;
2. contrôle de visibilité avec confirmation;
3. détection des Execution Providers ONNX;
4. benchmark automatique par machine;
5. enveloppe de confiance en mode ombre.

### Cycle 3 - Intelligence contextuelle

1. prototype de course ASR;
2. VerseGraph sur corpus biblique local;
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

Le meilleur prochain investissement n'est pas un modèle plus gros. C'est le
couple `Replay Lab + corpus audio multi-églises`. Il rend ensuite chaque autre
innovation mesurable: nouvelle ASR, accélération ONNX, seuil adaptatif,
VerseGraph ou traduction. Sans ce socle, les améliorations resteront des
impressions; avec lui, VersePro peut démontrer exactement ce qu'il fait mieux.
