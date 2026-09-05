# VersePro

VersePro écoute la prédication, reconnaît les versets cités — références
explicites (« Jean 3 verset 16 ») comme passages lus ou paraphrasés — et vous
laisse valider d'un geste ce qui part à l'écran. Application de bureau macOS et
Windows, autonome : aucun terminal à ouvrir, rien à lancer à côté.

Édité par **Selah Studios**. **Gratuit**, don libre — voir
[les conditions d'utilisation](CONDITIONS.md).

---

## Par où commencer

**Vous utilisez VersePro pour un culte** → [Guide d'utilisation (PDF)](docs/GUIDE-UTILISATION.pdf).
Neuf chapitres illustrés, de l'installation au branchement d'OBS, de
ProPresenter et de vMix. Sa dernière page est une **fiche réflexe** conçue pour
être lue en dix secondes quand quelque chose coince en plein direct — imprimez-la
et gardez-la en régie.

**Vous préparez l'équipe du dimanche matin** →
[Kit de démarrage régie et checklist culte](docs/KIT-DEMARRAGE-REGIE.md), avec
sa [version PDF prête à imprimer](output/pdf/VersePro-Kit-Demarrage-Regie.pdf).
Cette fiche courte reprend le pré-vol, les raccourcis, l'arrêt d'urgence et
l'état réel des sorties réseau dans la version 2.1.8.

**Vous développez ou vous intégrez** → les documents techniques ci-dessous. Ils
ne s'adressent pas aux bénévoles : le guide PDF se suffit à lui-même, et rien
dans cette section n'est nécessaire pour faire tourner un culte.

| Document | Sujet |
|---|---|
| [v2/README.md](v2/README.md) | Vue d'ensemble de l'application, lancement en développement |
| [v2/EXPLICATION_ARCHITECTURE.md](v2/EXPLICATION_ARCHITECTURE.md) | Intentions produit et architecture |
| [v2/GUIDE_COMPLET.md](v2/GUIDE_COMPLET.md) | Guide opérateur et dépannage détaillé |
| [v2/IMPLEMENTATION.md](v2/IMPLEMENTATION.md) | État réel des modules et contrats internes |
| [v2/ROADMAP_INNOVATIONS.md](v2/ROADMAP_INNOVATIONS.md) | Améliorations et innovations priorisées |
| [SYNTHESE_EXECUTIVE.md](SYNTHESE_EXECUTIVE.md) | Positionnement, preuves, limites et prochaines décisions |
| [SIGNING.md](SIGNING.md) | Certificats Apple et Windows, secrets CI |
| [CONDITIONS.md](CONDITIONS.md) | Conditions d'utilisation, droits sur les textes bibliques |

---

## Comment la détection décide

Le direct et la recherche manuelle partagent le même corpus, mais pas la même
tolérance au risque :

1. **Référence explicite** — le parseur reconnaît livres, nombres parlés,
   plages et références enchaînées. C'est le seul signal éligible à une
   automatisation, et seulement hors mode dimanche sûr.
2. **Fusion locale** — la recherche lexicale/floue et l'index e5-base ONNX des
   31 102 versets sont fusionnés. VerseGraph peut réordonner les candidats dans
   le passage déjà ouvert. Toute proposition reste à valider.
3. **Santé de transcription** — les segments trop courts ou durablement hachés
   suspendent la recherche sémantique; le parseur explicite reste actif. Cette
   protection évite de transformer musique, prière collective ou paroles mal
   reconnues en faux versets.
4. **IA de dernier recours** — OpenRouter, Gemini ou Ollama peuvent résoudre
   une allusion. La référence proposée doit exister dans la Bible locale et ne
   dispose d'aucun chemin direct vers les sorties.
5. **Recherche manuelle** — à partir de deux caractères, le moteur local
   complète la saisie; à partir de deux mots, e5 et l'assistant peuvent aussi
   chercher en parallèle. `Entrée` projette le candidat sélectionné;
   **Préparer** le place d'abord dans la prévisualisation.

## Modèles embarqués & Moteurs vocaux

| Composant | Rôle | Type / Emplacement |
|---|---|---|
| Nemotron 3.5-ASR (transcribe.cpp) | Transcription vocale locale neuronale temps réel | Local (GGUF quantifié) |
| Deepgram (Nova-2 / Nova-3) | Transcription vocale cloud haute fidélité | Cloud (Clé API) |
| Vosk large `fr-0.22` | Transcription locale continue de secours | Local (~1,4 Go) |
| Multilingual e5-base (ONNX) | Recherche vectorielle sémantique et thématique | Local (265 Mo) |
| Santé de transcription | Suspend les déductions sémantiques lorsque le transcript devient haché | Local, sans modèle supplémentaire |

VersePro n'emploie plus de barrière Silero VAD dans le chemin audio. Les cultes
avec musique sous la prédication ont montré qu'un filtre binaire pouvait rendre
la régie muette précisément lorsqu'elle devait continuer à écouter. Le signal
PCM complet est donc transmis au moteur choisi; les profils audio restent
facultatifs et désactivés par défaut.

## Navigation rapide (10 Versets Voisins)

Sous la barre de recherche manuelle, VersePro affiche en direct un bandeau de **10 versets voisins** autour de la référence projetée :
- 5 versets avant et 5 versets après au milieu du chapitre ;
- 10 versets suivants si le verset 1 est à l'antenne ;
- 10 versets précédents si le dernier verset du chapitre est projeté.  
Un clic sur un numéro de verset le projette instantanément sans ressaisie.

## Écrans et réseau local

- **Écran salle (`/output`)** : sortie autonome plein écran.
- **OBS (`/obs`)** : source navigateur transparente, indépendante de
  ProPresenter.
- **Suivi (`/follow`) et scène (`/stage`)** : pages de lecture disponibles sur
  le serveur local.
- **Limite actuelle** : l'application desktop lie encore le backend à
  `127.0.0.1`. Le QR code sait construire une adresse LAN, mais un téléphone ne
  pourra pas la joindre tant qu'un listener public dédié et protégé n'aura pas
  été livré. Ces pages fonctionnent aujourd'hui sur le poste VersePro.

## Bibles et droits

Seules deux traductions du **domaine public** sont versionnées ici et
distribuées avec l'application : Louis Segond 1910 (`data/bible.json`) et King
James Française (`data/bibles_cache/kjf.json`). Le format d'import accepte aussi
la Bible éwé et d'autres corpus autorisés, mais ces fichiers ne sont pas
distribués par le dépôt.

Les versions sous copyright — Semeur, TOB, Nouvelle Segond, Français courant — sont importables via l'onglet **Paramètres > Bible** ou régénérables localement par qui détient les droits d'en disposer.

## Construire les installeurs

- **macOS, en local** : `v2/frontend/src-tauri/build-macos.sh` (nécessite le venv de gel `v2/backend/.freeze-venv`)
- **macOS + Windows (automatisé)** : pousser un tag `v*` correspondant à la
  version déclenche la fabrication des installeurs et des artefacts de mise à
  jour Tauri. La signature de mise à jour est obligatoire pour une release par
  tag; les signatures Apple et Windows dépendent des certificats externes.

## État vérifié (version 2.1.8, 22 août 2026)

Validation complète :
- **313 tests backend réussis**, 3 ignorés (`pytest tests -q`) ;
- **24 tests frontend réussis** et build Vite valide ;
- benchmark historique : 30/30, précision et rappel à 100 %, p95 33,87 ms ;
- Replay Lab terrain : 43 cas, exactitude 86,1 %, précision 89,3 %, rappel
  80,7 %, p95 29,6 ms ;
- tests et contrôle Rust/Tauri exécutés avec verrouillage des dépendances.

Le benchmark historique mesure des phrases propres. Le Replay Lab, plus
difficile, contient accents, allusions, débit et négatifs issus du terrain. Ses
six cas manqués sont conservés comme dette mesurable, pas masqués par la moyenne.
