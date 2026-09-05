# VersePro — bilan des améliorations intégrées

État du travail : code intégré dans la copie locale, avec validation automatisée et essais de parcours. Les téléchargements publics v2.1.8 n’ont pas été remplacés. L’architecture existante est conservée.

La signature des installateurs, la notarisation et les essais sur machines propres sont exclus, conformément à la demande du porteur du projet.

## Ce qui change pour le bénévole

| Avant | Maintenant dans le projet |
|---|---|
| Réglages techniques avant de voir une réussite | « Première projection » : ouvrir un écran et envoyer Jean 3:16, puis préparer l’écoute |
| Préparation dispersée | Espace « Préparer mon culte » avec dossier, notes, références ordonnées et habillage |
| Notes parfois réduites à une seule référence par phrase | Extraction de toutes les références explicites dans leur ordre |
| Entraînement surtout destiné aux développeurs | Répétition guidée, audio inclus, import d’un extrait local, validation isolée et bilan exportable |
| Correction peu explicite | Cartes avec explication, correction orale et mémoire locale de phrases corrigées, exportable et réinitialisable |
| Connexion assimilée à une projection visible | Accusés de rendu par scène, expiration des états anciens et compteur dans la régie |
| Partage mobile construit sur un serveur local inaccessible depuis le Wi-Fi | Compagnon sur un serveur séparé, ouvert volontairement, avec lecture seule ou télécommande et expiration des accès |
| Préparation de modèles répétée sur chaque poste | Kit ZIP de modèles avec manifeste, empreintes vérifiées, import atomique et refus d’écraser un modèle différent |
| Export surtout technique | Carnet HTML des passages envoyés, lisible sur téléphone et imprimable |
| Démonstration du site peu interactive | Simulation nommée comme telle : référence, paraphrase, annonce, validation et effacement |

Les nouvelles pages reprennent les couleurs, les typographies et les surfaces de la régie. Le premier assistant ne bloque plus la découverte. Son choix hybride enregistre désormais le mode automatique réel ; le choix local conserve un moteur local.

## Limites précises des fonctions

- **Répétition :** l’exercice guidé teste le moteur biblique sur quatre phrases connues. L’audio utilise une instance Nemotron indépendante ; aucun passage de cet espace n’est envoyé à la salle. Le temps de traitement d’un fichier n’est pas une latence de direct. Un extrait non annoté ne permet pas de calculer les versets manqués.
- **Corrections :** les phrases sont normalisées et rapprochées exactement. Il ne s’agit pas d’un entraînement du modèle vocal. Une correction orale n’écarte que les candidats encore en attente, explicitement remplacés dans la même phrase et âgés de moins de trente secondes ; elle ne réécrit pas une projection passée.
- **Écrans :** « rendu confirmé » signifie que la page a mis à jour son contenu. Cela ne prouve pas que le vidéoprojecteur est allumé ou que la source OBS est dans le programme final. La mire prévoit une confirmation humaine de lisibilité.
- **Compagnon :** accès limité à huit heures, renouvellement et arrêt depuis la régie. L’administration du poste et ses clés ne sont pas exposées par ce serveur. Les traductions proposées sont celles déjà disponibles pour le passage ; ce n’est pas une transcription vocale de l’éwé.
- **Dossiers :** références, notes, date, salle, traduction et habillage sont portables. Les clés, les périphériques propres à un ordinateur et les corpus bibliques ne le sont pas. Le destinataire doit disposer de la traduction demandée.
- **Kit :** il transporte les modèles de données autorisés par le format. Le moteur natif doit déjà être présent dans l’application. Un lien d’export ne sert qu’une fois et expire après quinze minutes. Les fichiers temporaires sont nettoyés à expiration ou à la fermeture.
- **Carnet :** il reprend les entrées de l’historique marquées comme envoyées. Il ne certifie pas une visibilité physique et ne publie rien automatiquement.

## Vérifications réalisées

- Suite backend : **349 réussites, 3 ignorés**, avant les deux derniers tests de découverte ; trois avertissements de dépréciation de dépendances.
- Après les dernières corrections : **28 tests ciblés de lancement réussis** ; **39 tests de lancement et de moteur réussis** sur le lot immédiatement précédent. Ces chiffres se recouvrent et ne s’additionnent pas.
- Frontend : **27 tests réussis** et compilation de production réussie.
- Parcours navigateur : extraction de Jean 3:16 et Romains 8:28, préparation du déroulé, répétition guidée, validation isolée, projection réelle de Jean 3:16 et remontée de deux accusés de rendu, mire et absence d’erreur console sur la sortie.
- Site : affichage contrôlé sur ordinateur et aux largeurs 320, 375, 414 et 768 pixels, sans débordement horizontal ; validation de la démonstration et abstention sur l’annonce.
- Kit réel : archive d’environ **751 Mo**, import d’un modèle vérifié, second import sans duplication ; fichiers temporaires du contrôle supprimés.
- Audio : le dernier WAV synthétique de 20,49 secondes traverse le vrai moteur local. Jean 3:16, Psaumes 23:1 et Romains 8:28 ont été retrouvés, dont deux passages dans un même énoncé. Le bilan conserve désormais ces propositions multiples ; une ponctuation finale isolée ne masque plus le dernier résultat. L’identifiant de scène publique reste inchangé. Ces résultats ne constituent pas un benchmark de salle.

Le contrôle navigateur du lien LAN du compagnon a été bloqué par la règle de sécurité de l’outil. Le démarrage/arrêt du serveur et les règles de rôle, de jeton, d’origine et d’expiration ont été testés ; la validation sur un téléphone physique du même Wi-Fi reste à effectuer par l’équipe pilote.

## Ce qui demande encore le terrain ou une itération distincte

Le socle des huit axes de l’audit est présent. La simulation d’une panne du fournisseur cloud, la comparaison de deux propositions ambiguës côte à côte, la visibilité effective d’une source dans le programme OBS et la reconnaissance orale bilingue restent des prolongements techniques. Le corpus audio représentatif, les mesures de réutilisation et les cinq églises pilotes ne peuvent pas être remplacés par des données inventées.

Le [programme pilotes](PROGRAMME-PILOTES.md) fournit le déroulé d’essai, les mesures, le format de retour et un brouillon d’invitation non envoyé. Il permet de transformer les prochains défauts observés en cas de non-régression avec les outils de corpus déjà présents.

## Provenance des modèles

L’empreinte Q8_0 du kit est fixée à celle publiée par [le distributeur GGUF](https://huggingface.co/handy-computer/nemotron-3.5-asr-streaming-0.6b-gguf/tree/6d44e540bc31b0de1dbe174a3cea87f53a7f22fb). Le manifeste conserve les sources et révisions des fichiers. La carte du modèle vocal indique OpenMDW-1.1 ; la carte du [modèle E5 de base](https://huggingface.co/intfloat/multilingual-e5-base) indique MIT. Les références de sources accompagnent le paquet et ne modifient pas les termes des modèles originaux.
