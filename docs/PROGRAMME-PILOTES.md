# VersePro — les premiers dimanches pilotes

Ce document prépare les essais. Aucune église n’a été inscrite ou contactée automatiquement. Les seuils ci-dessous sont des objectifs de décision, pas des performances déjà mesurées.

## Le groupe de départ

Inviter cinq équipes volontaires, avec un responsable de régie identifié dans chacune. Chercher des situations différentes : petite salle, son réverbérant, musique sous la voix, prédication rapide, usage français/éwé pour l’affichage. Commencer par une répétition sur leur matériel habituel.

La signature des installateurs, la notarisation et les essais sur machines propres sont exclus de ce chantier à la demande du porteur du projet.

## Une séance de 35 minutes

1. **Découvrir — 5 min.** Ouvrir VersePro, afficher Jean 3:16 sans configurer de clé cloud. Mesurer le temps entre l’ouverture de la fenêtre et le passage visible. Séparer le temps d’installation et de préparation des modèles.
2. **Préparer — 5 min.** Coller des notes contenant trois références, vérifier leur ordre, enregistrer le dossier et préparer la régie. Exporter le fichier `.versepro` pour le bénévole suivant.
3. **Répéter — 10 min.** Faire l’exercice guidé, puis analyser un extrait personnel autorisé de deux minutes. Valider, ignorer, corriger. Exporter le bilan. Le fichier de démonstration est synthétique : il ne mesure pas la qualité en salle.
4. **Voir depuis la salle — 5 min.** Ouvrir la sortie, afficher la mire, vérifier les bords et la lisibilité au fond de la salle. Confirmer le rendu dans VersePro et vérifier séparément le projecteur ou la source réellement visible dans OBS.
5. **Transmettre — 5 min.** Tester le compagnon sur un téléphone du même réseau, d’abord en lecture seule. Tester une seconde traduction uniquement si son corpus est autorisé et installé. Fermer le partage à la fin.
6. **Débriefer — 5 min.** Demander où l’équipe a hésité, ce qu’elle ferait sans aide et ce qui l’empêcherait d’utiliser VersePro dimanche prochain.

## Fiche à remplir après chaque séance

| Observation | Valeur à renseigner |
|---|---|
| Identifiant anonyme de l’équipe | P01…P05 |
| Version et système | Version, Windows/Mac, mémoire disponible |
| Première projection | Durée hors installation et modèles ; aide nécessaire oui/non |
| Préparation du déroulé | Références attendues / extraites / corrigées |
| Audio | Synthétique ou réel autorisé ; durée ; moteur utilisé |
| Références sur l’extrait annoté | Correctes, manquées, fausses propositions |
| Salle | Rendu confirmé ; visibilité réelle confirmée par l’opérateur |
| Compagnon | Téléphone, navigateur, réseau, rôle ; résultat |
| Incident principal | Geste déclencheur, attendu, obtenu |
| Réutilisation | Prêt à l’utiliser au prochain culte ? Motif concret |

Ne pas confondre téléchargement, première ouverture, première projection et réutilisation. Les journaux techniques exportés par VersePro excluent les secrets et la transcription. Le bilan de répétition contient le texte entendu : il reste local jusqu’au partage volontaire par l’équipe.

## Construire le corpus francophone

Réutiliser `v2/backend/corpus/` et les outils de `v2/backend/benchmarks/` au lieu de créer un second format. Transformer les ratés en cas de rejeu avec référence attendue ; conserver aussi les annonces, prénoms et chiffres qui ne doivent rien produire. Prévoir un groupe de locuteurs réservé à la validation, jamais utilisé pour régler les seuils ou mémoriser des corrections.

Avant de conserver un extrait réel, appliquer les règles de consentement et d’anonymisation de [corpus/README.md](../v2/backend/corpus/README.md). Les extraits vocaux personnels ne sont pas versionnés. L’exception `.gitignore` du nouvel exemple concerne uniquement l’audio de synthèse inclus.

L’affichage d’une Bible éwé n’est pas une reconnaissance vocale de l’éwé. Éprouver ces deux capacités séparément. Le test audio intégré utilise actuellement le français de Nemotron.

## Décider du lancement

Objectifs initiaux à discuter avec les équipes : quatre équipes sur cinq réussissent la première projection en moins de trois minutes hors installation ; aucune projection involontaire pendant les répétitions ; trois équipes au moins réutilisent VersePro au culte suivant. Pour les extraits annotés, publier précision et rappel avec le nombre de cas et les conditions, jamais un pourcentage isolé.

Un incident qui peut envoyer un mauvais passage sans validation en mode sûr suspend l’élargissement du pilote. Un problème d’ergonomie devient une correction prioritaire avec son geste de reproduction. Garder l’autopilote facultatif.

## Invitation prête à adapter

> Bonjour, nous préparons le lancement de VersePro, une régie qui écoute la prédication et propose les passages bibliques à valider. Nous cherchons quelques équipes média francophones pour une répétition de 35 minutes sur leur matériel habituel. L’objectif est de préparer un premier dimanche et de comprendre les difficultés réelles. Seriez-vous disponibles pour un essai accompagné ?

Ce texte est un brouillon ; aucun message n’a été envoyé. Le site propose déjà une entrée « participer aux essais » qui ouvre un courriel à rédiger par le visiteur.
