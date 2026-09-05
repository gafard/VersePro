<!-- Hallmark · pre-emit critique: P5 H4 E4 S5 R4 V4 · auto-évaluation du rapport, pas une note du produit -->

# VersePro — proposition de lancement et d’évolution

Analyse du 5 septembre 2026. Périmètre : dépôt local, site public versepro.live, publication GitHub v2.1.8 et sites officiels de concurrents. Les constats de code portent sur la copie locale, qui comporte déjà de nombreuses modifications ; ils ne prouvent pas que chaque comportement est identique dans les installateurs publiés.

## La décision que je recommande

Positionner VersePro comme **le compagnon de régie biblique des églises francophones** : préparer un culte, retrouver les passages pendant la prédication, garder la maîtrise de l’écran et repartir avec les références réellement utilisées.

La promesse proposée : **« Les bons versets. Au bon moment. Vous gardez la main. »**

L’ambition est de devenir l’outil que l’équipe ose utiliser chaque dimanche. Pour y parvenir, je privilégierais une première expérience remarquable, la preuve de fonctionnement sur du vrai son et une continuité entre préparation et direct. La détection IA, le hors-ligne et la gratuité existent déjà ailleurs : ils restent essentiels, mais ne suffisent pas à différencier le produit.

Commencer par des équipes francophones utilisant Windows et OBS ou un projecteur simple, puis élargir selon les premiers utilisateurs. C’est une hypothèse de marché à valider, pas une donnée d’usage déjà établie. Conserver la version Apple Silicon existante.

## Ce que le projet fait déjà bien

| Acquis | Pourquoi le conserver | Évolution utile |
|---|---|---|
| Application Tauri, React/Zustand et backend Python | Une application autonome, avec interface et moteur distincts | Fiabiliser installation et premier démarrage |
| Parseur biblique, recherche floue et e5 local | Plusieurs voies pour retrouver une référence | Les mesurer séparément sur de vrais enregistrements |
| Prévisualisation, mode sûr, mode ombre, arrêt d’urgence | La maîtrise du direct est une vraie qualité de produit | Rendre ces états immédiatement compréhensibles |
| Moteurs locaux et cloud | Adaptation à l’équipement et au réseau | Aligner les choix proposés sur le comportement réel |
| Écran autonome, OBS, autres sorties | Permet de compléter une régie existante | Documenter et tester chaque intégration promise |
| Plan, historique, export Markdown/PPTX, résumé | Le produit dépasse déjà le seul instant de projection | Les réunir dans un parcours avant/pendant/après |
| Tests, Replay Lab, protections de téléchargement | Une base pour progresser sans casser les acquis | Étendre les preuves à l’audio et aux installateurs |
| Identité sombre, accent chaud, vocabulaire de régie | Un univers identifiable et cohérent avec le contexte | Réduire la décoration des écrans utilitaires |
| Gratuité et dons sans déblocage de fonctions | Positionnement clair et accueillant | Demander le soutien après la démonstration de valeur |

Le plan de prédication, les exports, le moniteur scène et la recherche sémantique ne sont donc pas à « inventer ». Ils existent. La prochaine version doit surtout les rendre plus faciles à découvrir et plus fiables à utiliser ensemble.

## Les constats prioritaires, avec leurs preuves

### 1. L’installation impose trop tôt un effort de confiance

Le [site public](https://versepro.live/) affiche une procédure Gatekeeper, une commande Terminal et une procédure SmartScreen. Il indique explicitement que l’installateur Windows n’est pas encore signé. Pour une équipe découvrant un éditeur, c’est un obstacle plausible à l’adoption ; son impact réel doit être mesuré.

Le workflow local émet des avertissements si les certificats OS manquent, alors que la synthèse existante affirme que les installateurs publics sont refusés dans ce cas. Voir `.github/workflows/release.yml:75` et `SYNTHESE_EXECUTIVE.md:75`. La signature des mises à jour et celle des exécutables OS sont deux mécanismes différents.

**Proposition :** signer et notariser les paquets adaptés à chaque plateforme, vérifier la provenance des artefacts et faire tester l’installation sur des machines propres. Mettre les procédures exceptionnelles dans l’aide. Mesurer les avertissements encore rencontrés : une signature ne garantit pas à elle seule leur disparition immédiate sur tous les postes.

### 2. La détection du Mac est trop affirmative

`landing/script.js:14` reconnaît « mac », puis `:34` annonce « macOS Apple Silicon détecté » et sélectionne systématiquement le DMG ARM. Il ne vérifie pas le processeur. Un Mac Intel peut donc être orienté vers un fichier incompatible. Un iPad se présentant comme un Mac mérite également un contrôle spécifique.

**Proposition :** afficher explicitement « Mac avec puce Apple » et permettre de choisir le système. Sur téléphone, proposer la démonstration et un lien à copier pour l’ordinateur. Ne pas déclarer une architecture détectée si elle est seulement supposée.

### 3. Le choix hybride ne correspond pas au réglage enregistré

Dans `v2/frontend/src/components/FirstRunWizard.jsx:125`, les modes hybride et hors-ligne enregistrent tous deux `nemotron`. Pourtant l’interface promet Deepgram avec secours local. Le backend, `v2/backend/app/main.py:978`, traite explicitement `nemotron` comme un choix local sans cloud.

**Proposition :** enregistrer `auto` pour le mode hybride, conserver une sélection strictement locale pour le mode hors-ligne et montrer les prérequis manquants. Tester choix → persistance → redémarrage → moteur réellement démarré. L’utilisateur doit voir « local prêt », « cloud disponible » ou « configuration incomplète » sans comprendre les noms des modèles.

### 4. Le QR code ne suffit pas à rendre le téléphone opérationnel

`v2/frontend/src/components/FollowModal.jsx` construit une adresse LAN, mais le démarrage Tauri impose `VERSEPRO_HOST=127.0.0.1` dans `v2/frontend/src-tauri/src/main.rs:65`. La limite est déjà reconnue dans le README.

**Proposition :** commencer par un accès local de lecture aux écrans assemblée/scène, sur un listener séparé et limité. Ajouter ensuite la télécommande avec appairage, expiration et révocation de session. Vérifier depuis un vrai téléphone les réseaux invités, pare-feu et reconnexions. Tant que ce parcours n’est pas livré, l’interface doit expliquer que l’accès est limité au poste.

### 5. « Projeté » ne prouve pas que quelqu’un voit le verset

`v2/backend/app/outputs/browser.py:115` retourne un succès même sans client connecté. Il retourne aussi un succès après une diffusion dont les erreurs sont absorbées. Cela peut convenir pour mémoriser une scène, mais ne constitue pas un accusé de rendu.

**Proposition :** séparer les états « scène préparée », « envoyée », « reçue » et « rendu confirmé ». Utiliser un identifiant de scène et un accusé du client après rendu. Une intégration OBS peut ensuite indiquer si la source appartient à la scène programme. Aucun de ces signaux ne garantit physiquement qu’un projecteur est allumé : garder une confirmation visuelle pendant le prévol.

### 6. Le site montre une ambiance, mais trop peu l’usage réel

Le site a été ouvert dans le navigateur en 1280 × 720 et 375 × 812. La photographie et la marque occupent beaucoup de place ; sur le petit écran testé, le premier bouton arrive au bas de la vue. Sur desktop, le lien « découvrir l’expérience » se superpose aux caractéristiques sous le bouton.

La démo est un exemple fixe : `landing/script.js` change seulement le libellé du bouton en « à l’antenne ✓ ». Le passage est déjà visible avant validation. Le libellé « fiche réflexe » du premier écran renvoie au guide complet, alors qu’une vraie fiche courte est accessible plus bas.

**Proposition :** garder l’atmosphère et montrer la véritable interface, le geste de validation et son effet sur l’écran. Corriger le chevauchement et le lien PDF. Réduire le mot-symbole répété au profit de la démonstration. Nommer clairement les simulations.

### 7. La performance de détection n’est pas encore une preuve de direct

Les documents du 22 août mentionnent 43 cas, 86,1 % d’exactitude, 89,3 % de précision et 80,7 % de rappel. Ce sont des résultats historiques documentés, pas un benchmark relancé durant cet audit. Aucun fichier WAV n’a été trouvé dans le corpus local inspecté.

Le Replay Lab dispose d’un chemin audio Vosk, mais son chronomètre commence après transcription, autour de `detecter_sans_effet` (`v2/backend/benchmarks/replay_lab.py:193`). Ses millisecondes ne mesurent donc pas le délai entre la parole et l’affichage. Le moteur local principal annoncé étant Nemotron, son chemin doit être couvert lui aussi.

**Proposition :** chronométrer séparément fin de référence prononcée → transcription → candidat disponible → validation humaine → rendu. Publier les résultats par moteur, matériel, langue et conditions audio. Compter aussi les faux candidats par heure et les corrections nécessaires.

### 8. L’absence d’utilisateurs reste à caractériser

L’API GitHub publique indiquait, au moment du contrôle, trois téléchargements du DMG et un de l’EXE v2.1.8. Ces compteurs peuvent inclure le développeur, des tests et des répétitions. Ils ne prouvent ni installations réussies ni utilisateurs actifs.

Aucune instrumentation d’activation explicite n’a été trouvée dans les fichiers frontend/backend et landing recherchés. Cela ne permet pas de conclure sur les statistiques éventuellement disponibles chez l’hébergeur.

**Proposition :** distinguer visite, clic de téléchargement, premier lancement, première projection, premier culte et retour au deuxième culte. Pour les pilotes, un suivi manuel suffit d’abord. Toute télémétrie produit ultérieure doit être minimale et explicite, sans audio ni contenu de prédication par défaut.

## Ce que propose déjà le marché

Lecture des pages officielles le 5 septembre 2026 ; les fonctions ci-dessous sont annoncées par les éditeurs, sans benchmark comparatif de leurs logiciels.

| Produit | Offre annoncée pertinente | Conséquence pour VersePro |
|---|---|---|
| [ProPresenter](https://www.renewedvision.com/propresenter) | Production et présentation, couches et sorties multiples | S’intégrer aux régies équipées, concentrer l’effort sur l’assistance biblique |
| [Vies](https://vies.live/) | Détection locale, plusieurs niveaux de moteur, NDI, synchronisation et partage LAN | Le local et la connexion aux autres outils sont déjà concurrentiels |
| [EasyVerse](https://www.theeasyverse.com/) | Détection, commandes vocales, télécommande QR, langues dont éwé et twi, offre gratuite et Pro | Le bilingue et le QR doivent apporter une expérience supérieure mesurable |
| [TajiCast](https://tajicast.com/) | Gratuité, détection hors-ligne, téléphone, archives et notes de sermon | Le gratuit et le résumé automatique ne constituent pas seuls une distinction |

**Notre possibilité de différenciation :** réussir particulièrement bien le français de prédication, les régies bénévoles et les connexions intermittentes, puis le prouver sur un corpus représentatif. C’est une direction à construire ; je n’affirme pas que VersePro surpasse aujourd’hui ces concurrents.

## Les innovations que je développerais

### A. « Répéter mon dimanche » — la fonction signature

Le responsable ouvre une répétition. VersePro joue un extrait de démonstration inclus ou un enregistrement local choisi par l’équipe. Les références arrivent comme en direct. Le bénévole prépare, valide, corrige et efface. Une coupure réseau simulée permet de vérifier le secours sans modifier la connexion de l’ordinateur.

À la fin : références trouvées/manquées, temps de réaction, état des sorties et actions à régler avant le culte. Avec un enregistrement non annoté, ne pas prétendre connaître tous les versets manqués : demander une annotation ou limiter le bilan aux événements observés.

**Ce qui existe :** Replay Lab, mode ombre, prévol et sorties. **Ce qu’on ajoute :** une interface de répétition, un audio inclus, un adaptateur vers le vrai pipeline audio et un bilan intelligible. Isoler strictement la session de répétition de la diffusion publique.

**Valeur :** une même fonction rassure le futur utilisateur, forme le bénévole, valide son matériel et produit des cas de non-régression. C’est mon premier investissement différenciant.

### B. « Première projection » avant les réglages avancés

Au premier lancement, trois actions guidées : choisir où afficher, projeter un verset de démonstration, puis préparer l’écoute. Le bénévole voit une réussite sans attendre le téléchargement d’un gros modèle ni créer une clé cloud. Afficher clairement qu’il s’agit d’une projection manuelle de découverte.

Remplacer le choix technique initial par « Découvrir », « Préparer le hors-ligne » et « Configurer ma régie ». Le logiciel conserve ensuite un profil de salle : entrée audio, sortie, traduction, taille de texte et mode vocal.

**Objectif proposé :** une première projection de découverte en moins de trois minutes après ouverture, à mesurer sur les postes pilotes. Ce délai n’inclut pas téléchargement et préparation des modèles.

### C. Le dossier du culte, transportable entre bénévoles

Une page « Préparer le culte » regroupe nom, date, passages, habillage et profil de salle. Les notes collées deviennent des références à confirmer. L’opérateur peut répéter le déroulé, puis transférer un fichier `.versepro` à un autre poste.

Le paquet contient le plan et les réglages portables, sans clés API ni périphériques spécifiques. Les Bibles sous licence restent des références à un corpus disponible sur le poste destinataire. Valider le format et sa version à l’import.

**Ce qui existe :** extraction de notes dans Paramètres, déroulé et plan transmis au moteur. **L’innovation :** les rendre centraux et partageables. Le plan prépare des candidats mais ne remplace jamais l’écoute d’un changement de passage.

### D. Une détection qui explique et révise sa proposition

Une carte indique « référence entendue », « citation rapprochée » ou « passage suggéré », avec les mots qui l’ont déclenchée. Une paraphrase incertaine peut montrer deux candidats avec leur différence, sans multiplier la file.

Scénarios à éprouver : « Jean trois… pardon, Jean quatorze », « reprenons le verset précédent », puis passage d’une lecture à un commentaire. La référence se stabilise dans la prévisualisation ; une correction orale retire le candidat devenu caduc. Pour une phrase ambiguë, le logiciel peut s’abstenir.

**Ce qui existe :** contexte, VerseGraph, suivi de lecture, annulation des analyses obsolètes. **L’apport :** une politique d’intention cohérente et visible, mesurée sur des séquences continues. Les scores internes ne doivent pas être présentés comme des probabilités scientifiques sans calibration.

### E. Le français des églises, puis le bilingue réellement utile

Construire un corpus de validation avec plusieurs prédicateurs et salles : français ouest-africain et central, autres variétés francophones, musique de fond, changements de débit. Séparer les locuteurs d’entraînement/réglage et de validation.

Pour le bilingue, commencer par une même référence affichée en français et en éwé depuis deux corpus autorisés. Puis explorer l’alternance des langues à l’oral. Afficher du texte éwé et comprendre une prédication en éwé sont deux capacités différentes.

**Innovation durable :** un lexique local corrigeable par l’équipe et une mémoire des confusions validées, exportable et réinitialisable. Les corrections influencent le classement, sans modifier le texte biblique ni autoriser des projections automatiques. Tester toute adaptation contre les cas négatifs pour éviter le surapprentissage.

### F. Un tableau de contrôle qui dit ce que voient les écrans

Afficher des états précis par destination : « Salle connectée », « Dernier rendu : Jean 3:16 », « OBS : source hors programme », « Retour scène déconnecté ». Les intégrations qui ne fournissent pas une preuve suffisante restent indiquées comme « envoi confirmé ».

Un contrôle avant culte fait apparaître une mire simple sur la destination choisie. Le bénévole confirme sa visibilité et sa lisibilité depuis le fond de la salle. Pendant le direct, une déconnexion propose une action claire tout en conservant le dernier contenu valide quand le client le permet.

**Ce qui existe :** scène canonique et retours des pilotes. **L’apport :** des accusés de rendu, de la fraîcheur et un diagnostic utile. Une connexion WebSocket ne doit plus être assimilée à une projection vue par l’assemblée.

### G. Le kit hors-ligne d’église

Préparer un paquet de modèles depuis un poste connecté, puis l’importer sur d’autres postes via une clé USB. Afficher sa taille, ses langues, sa version et l’espace réellement nécessaire. Ajouter reprise des téléchargements et vérification d’intégrité du paquet.

**Valeur :** une équipe ne retélécharge pas les mêmes gros modèles sur chaque ordinateur. Les mécanismes atomiques et les empreintes existants sont un bon socle ; la distribution du paquet doit aussi vérifier les licences des modèles inclus.

À valider d’abord avec les pilotes : si la préparation des modèles est un obstacle fréquent, ce chantier passe devant des fonctions IA supplémentaires.

### H. Le carnet des passages après le culte

Un document lisible sur téléphone rassemble les références validées, leur ordre et, lorsque disponibles, leurs repères temporels. L’équipe relit le résumé avant export. Une version à imprimer et une version partageable sont proposées sans publication automatique.

**Ce qui existe :** historique, résumé et exports. **L’apport :** un parcours éditorial simple et une distinction nette entre ce qui a été entendu, suggéré et réellement projeté. La première version peut être un fichier local ; une page web partageable est un chantier ultérieur.

Cette fonction donne une raison de réutiliser VersePro au-delà de la régie, mais elle vient après la fiabilité du direct.

## Le site que je proposerais

Conserver le noir, l’accent chaud et une présence humaine. Réduire la photographie au profit d’une capture réelle de la régie et d’une courte démonstration.

**Texte principal proposé :** « Les bons versets. Au bon moment. »

**Explication :** « VersePro écoute la prédication, retrouve les passages et les prépare pour votre écran. Vous validez. Le mode local fonctionne sans Internet après préparation. »

**Actions :** « Voir la démonstration » et « Télécharger gratuitement ». Sur mobile, la démonstration devient prioritaire ; le choix Windows/Mac reste explicite.

La démonstration de 45 à 60 secondes montre une référence explicite, une paraphrase à confirmer, puis une perte de connexion avec moteur local déjà prêt. Les séquences doivent provenir du logiciel réel ; une simulation interactive doit être nommée comme telle. Ne pas la présenter comme un benchmark.

Le reste de la page répond à cinq questions : ce que voit le régisseur, ce que voit l’assemblée, compatibilité avec la régie, installation réelle, aide disponible. Remplacer « 2 + 7 » par une liste claire des traductions livrées et des possibilités d’import. Aligner les URL structurées encore orientées vers le domaine Vercel sur le domaine canonique.

Mettre en évidence un programme « Églises pilotes » avec accompagnement et retour d’expérience. Publier les témoignages seulement après usage réel et accord. Garder le don accessible après la preuve de valeur et dans le pied de page.

## Audit visuel ciblé selon Hallmark

La sévérité ci-dessous est celle de la cohérence visuelle, indépendante de la priorité fonctionnelle du lancement. Le diagnostic s’appuie sur `design.md`, le code et les deux vues navigateur ; il ne constitue pas une certification de tous les breakpoints ou de l’accessibilité.

| Sévérité | Écart nommé | Localisation | Correction |
|---|---|---|---|
| Critique | Design-system drift | `FirstRunWizard.jsx:255–303` | Remplacer les accents cyan/indigo, orbes et verre par les surfaces et statuts du système de régie |
| Majeure | Hiérarchie / collision de positionnement | `landing/styles.css:280–289`, `:336–345` | Remettre le lien de découverte dans le flux pour éviter son chevauchement constaté en 1280 × 720 |
| Majeure | Primauté de la décoration sur l’usage | `landing/index.html:74–114` | Réduire le mot-symbole et l’emprise de la photo, montrer l’action opérateur et l’écran |
| Mineure | Mid-render token improvisation | `landing/styles.css:276–278`, `landing/index.html:256` | Rattacher couleurs de survol et encarts aux tokens existants |

1 critique · 2 majeures · 1 mineure. Conserver la charte, corriger les écarts ; une refonte totale n’est pas justifiée par cet audit.

## Ordre de réalisation

Les fourchettes ci-dessous sont des estimations de travail pour un développeur connaissant le projet, hors délais externes et recrutement des pilotes. Elles ne sont pas un engagement de calendrier.

| Lot | Livrable concret | Effort indicatif | Condition de réussite |
|---|---|---|---|
| 1 — vérité du parcours | Choix hybride corrigé, téléchargements explicites, bon PDF, textes cohérents, collision visuelle supprimée | 3–5 jours | Aucun écart entre choix affiché et moteur enregistré ; parcours vérifié sur les plateformes visées |
| 2 — installation | Paquets signés, notarisation applicable, essais sur machines propres, besoins disque/mémoire mesurés | 3–6 jours + délais externes | Installation documentée réussie sur la matrice supportée |
| 3 — découverte | Première projection guidée, profil de salle, vraie démo du site | 5–8 jours | Des bénévoles atteignent la projection sans assistance technique |
| 4 — répétition | Audio inclus, rejeu via moteur principal, bilan et isolation des sorties | 8–15 jours | Démonstration répétable et mesure parole → candidat sur matériel réel |
| 5 — pilotes | Cinq équipes, deux cultes chacune, suivi des obstacles | 3–4 semaines de terrain | Décision d’élargissement fondée sur usage et retour au second culte |
| 6 — différenciation | Dossier portable, accès LAN et accusés de rendu selon retours | À chiffrer après pilotes | Résoudre les obstacles observés avant d’ouvrir plus de fonctions |

Le prochain jalon public devrait contenir les lots 1–3 et une première version de la répétition si elle est prête. Les pilotes peuvent commencer avec un périmètre réduit clairement annoncé. Un objectif à 30/60/90 jours doit rester ajustable selon les installateurs et le terrain.

## Comment décider si le lancement est prêt

Objectifs proposés pour les pilotes, à ajuster avec les premières mesures :

- Cinq équipes installent et réalisent chacune deux cultes ; noter chaque intervention d’assistance nécessaire.
- Au moins quatre réutilisent volontairement le produit pour leur second culte.
- Première projection de découverte en moins de trois minutes après ouverture sur au moins quatre postes sur cinq.
- Aucune projection automatique issue d’une paraphrase en mode sûr ; vérifier cet invariant dans les tests et la répétition.
- Sur un corpus de références explicites annotées et des matériels nommés : viser au moins 95 % de rappel et un p95 inférieur à deux secondes entre fin de référence et candidat. Ce sont des cibles, pas des résultats acquis.
- Publier les faux candidats par heure, les erreurs acceptées par l’opérateur et les déconnexions séparément ; aucune moyenne unique ne doit masquer un problème de salle ou de moteur.
- Valider une session prolongée, une déconnexion réseau et une déconnexion de sortie sur les postes supportés.

L’indicateur principal devient **le nombre d’équipes qui réussissent un culte et reviennent au suivant**. Les visites et téléchargements servent à comprendre le parcours, pas à déclarer une adoption.

## Architecture : faire évoluer sans réécriture

Conserver Tauri, React, Zustand, Python et les services existants. Le découpage ASR → moteur biblique → sorties est pertinent. L’extraction de responsabilités doit accompagner les chantiers : `LiveDetection.jsx` compte 1 990 lignes, `Settings.jsx` 1 551 et `routes.py` 2 027 dans la copie inspectée.

Pour les nouveaux travaux, isoler la session de répétition, le dossier du culte, l’état des destinations et le diagnostic. Utiliser des identifiants stables d’événement et de scène pour relier proposition, validation, diffusion et rendu. Garder les tests de mode sûr et de non-régression comme barrières de publication.

Un diagnostic exportable doit inclure version, moteur, matériel, états de sortie et erreurs récentes, avec masquage des secrets ; transcript et audio restent exclus par défaut. Cela aide le support et réduit la dépendance au développeur.

## Ce que je reporterais

Un éditeur vidéo complet, une bibliothèque de chants exhaustive, un réseau social, une place de marché et une automatisation libre du culte disperseraient le lancement. La course parallèle entre moteurs cloud et local mérite un prototype seulement si les mesures démontrent un gain suffisant au regard de la charge CPU et du coût. Ajouter un gros modèle sans mesurer les échecs actuels ne constitue pas une stratégie.

Conserver le cœur gratuit et les dons. Si l’usage le justifie plus tard, tester de l’accompagnement, de la formation ou des services de synchronisation, avec une économie explicitée ; aucun abonnement supplémentaire n’est nécessaire pour apprendre des premiers utilisateurs.

## Vérifications de cet audit

- Site public chargé et inspecté dans un navigateur desktop et à une largeur de 375 px ; bouton de démonstration actionné.
- Publication GitHub v2.1.8 et liste de ses artefacts consultées via l’API publique, sans télécharger les installateurs.
- 24 tests frontend réussis ; build Vite réussi le 5 septembre 2026.
- 323 tests backend réussis, 3 ignorés, en 130,48 secondes ; trois avertissements de dépréciation de dépendances. Exécution le 5 septembre 2026 avec le venv existant, données de tests isolées par le conftest du projet.
- Lecture du code de configuration, onboarding, moteurs, sortie navigateur, accès mobile, exports et Replay Lab.
- Capture de régie déjà présente dans le guide examinée comme document existant ; pas assimilée à une capture nouvelle de l’application.
- Pas d’installation Windows/macOS sur machine propre, pas d’essai micro en salle, pas de benchmark audio concurrentiel et pas de relance des benchmarks historiques pendant cet audit.

## Sources et points d’entrée

- [Site public VersePro](https://versepro.live/)
- [Release v2.1.8](https://github.com/gafard/VersePro/releases/tag/v2.1.8)
- [Métadonnées de la dernière release](https://api.github.com/repos/gafard/VersePro/releases/latest)
- [ProPresenter](https://www.renewedvision.com/propresenter), [Vies](https://vies.live/), [EasyVerse](https://www.theeasyverse.com/), [TajiCast](https://tajicast.com/)
- Documents locaux consultés : README, SYNTHESE_EXECUTIVE, design.md, documentation v2, documentation du corpus et sources citées dans le rapport.

Les chiffres commerciaux des concurrents n’ont pas été retenus comme preuves de performance ou d’adoption vérifiée. Les délais, objectifs et innovations de ce dossier sont des propositions, distinctes des fonctions observées.
