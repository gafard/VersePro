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

Quatre étages rapides et complémentaires, dans cet ordre :

1. **Référence explicite** — reconnaissance par motif ultra-rapide (moins d'une milliseconde).
   Seul étage autorisé à projeter automatiquement si la diffusion directe est activée.
2. **Fusion hybride (Lexicale & Sémantique e5 ONNX)** — les moteurs recherchent dans l'index vectoriel des 31 102 versets et le corpus lexical local en parallèle.
3. **Recherche manuelle & Autocomplétion dynamique** — dès 2 lettres ou mots tapés dans la barre du régisseur, un volet d'autocomplétion interactif propose les meilleurs versets avec prévisualisation et raccourcis clavier (`↑`/`↓` + `Entrée`).
4. **IA Assistant (SmartVerses)** — résout les allusions bibliques et récits narratifs libres (*« le fils prodigue »*, *« sang sur les linteaux »*, *« murailles de Jéricho »*). La proposition est systématiquement vérifiée dans la Bible locale avant d'être soumise à validation manuelle en régie (anti-hallucination stricte).

## Modèles embarqués & Moteurs vocaux

| Composant | Rôle | Type / Emplacement |
|---|---|---|
| Nemotron 3.5-ASR (transcribe.cpp) | Transcription vocale locale neuronale temps réel | Local (GGUF quantifié) |
| Deepgram (Nova-2 / Nova-3) | Transcription vocale cloud haute fidélité | Cloud (Clé API) |
| Vosk large `fr-0.22` | Transcription locale continue de secours | Local (~1,4 Go) |
| Multilingual e5-base (ONNX) | Recherche vectorielle sémantique et thématique | Local (265 Mo) |
| VoiceGate (Silero VAD) | Barrière vocale filtrant la musique d'ambiance et les silences | Local (ONNX) |

## Navigation rapide (10 Versets Voisins)

Sous la barre de recherche manuelle, VersePro affiche en direct un bandeau de **10 versets voisins** autour de la référence projetée :
- 5 versets avant et 5 versets après au milieu du chapitre ;
- 10 versets suivants si le verset 1 est à l'antenne ;
- 10 versets précédents si le dernier verset du chapitre est projeté.  
Un clic sur un numéro de verset le projette instantanément sans ressaisie.

## Écrans Mobiles & Réseau Local (/follow et /stage)

- **Suivi Assemblée (`/follow`)** : L'assemblée scanne le QR code pour lire en temps réel les versets projetés sur smartphone dans la traduction de son choix.
- **Moniteur Scène (`/stage`)** : Écran retour pour le pupitre ou la tablette du pasteur (verset courant en gros caractères, chrono, notes).
- **Résolution réseau automatique** : Détection multi-interfaces (Wi-Fi / Ethernet) et port dynamique `17871`.

## Bibles et droits

Seules des traductions du **domaine public** sont versionnées ici et distribuées avec l'application : Louis Segond 1910 (`data/bible.json`), King James Française (`data/bibles_cache/kjf.json`) et Bible Éwé (`data/bibles_cache/ewe.json`).

Les versions sous copyright — Semeur, TOB, Nouvelle Segond, Français courant — sont importables via l'onglet **Paramètres > Bible** ou régénérables localement par qui détient les droits d'en disposer.

## Construire les installeurs

- **macOS, en local** : `v2/frontend/src-tauri/build-macos.sh` (nécessite le venv de gel `v2/backend/.freeze-venv`)
- **macOS + Windows (Automatisé)** : Pousser un tag `v*` (ex: `v2.1.8`) déclenche GitHub Actions pour fabriquer et signer les installeurs `.dmg` (Mac) et `.exe` / `.msi` (Windows).

## État vérifié (Version 2.1.8)

Validation complète :
- **313 tests backend réussis** (100 % passés sous pytest) ;
- **24 tests frontend réussis** (100 % passés sous Node Test Runner) ;
- Builds Vite et Tauri vérifiés sans erreur ;
- Recherche parallélisée et autocomplétion testées avec succès.
