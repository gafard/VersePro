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

Trois étages, dans cet ordre, et un seul a le droit de projeter sans vous :

1. **Référence explicite** — reconnaissance par motif, moins d'une milliseconde.
   Seul étage autorisé à projeter automatiquement, et seulement si la diffusion
   directe est activée.
2. **Fusion hybride** — deux moteurs indépendants (lexical/flou et sémantique
   e5) doivent tomber d'accord, avec confirmation par recouvrement de mots.
   Environ 20 ms, en fin de phrase. Toujours la file à valider.
3. **IA en dernier recours** — seulement quand les deux premiers se taisent.
   Sa réponse est relue contre le texte biblique : elle ne peut pas fabriquer un
   verset inexistant, mais elle peut proposer le mauvais. Elle n'atteint donc
   jamais l'écran sans validation humaine.

Les allusions purement narratives (« Philippe et l'eunuque ») restent le point
faible connu : les moteurs comparent du texte, pas des récits.

## Modèles embarqués

| Composant | Rôle | Poids |
|---|---|---|
| Vosk large `fr-0.22` | transcription hors-ligne française | environ 1,4 Go |
| faster-whisper `tiny`/`base`/`small` | transcription locale robuste, installé à la demande | selon modèle |
| e5-base (ONNX) | recherche sémantique, repli automatique sur e5-small | 265 Mo |

L'index sémantique (31 102 versets) peut être livré pré-calculé avec
l'application. Les modèles absents sont préparés explicitement depuis Paramètres,
jamais téléchargés automatiquement pendant un culte.

## Bibles et droits

Seules des traductions du **domaine public** sont versionnées ici et
distribuées avec l'application : Louis Segond 1910 (`data/bible.json`) et King
James Française (`data/bibles_cache/kjf.json`).

Les versions sous copyright — Semeur, TOB, Nouvelle Segond, Français courant —
sont volontairement **absentes du dépôt et des installeurs**. Elles restent un
cache local, régénérable avec `v2/backend/cache_bibles.py` par qui détient les
droits d'en disposer.

## Construire les installeurs

- **macOS, en local** : `v2/frontend/src-tauri/build-macos.sh` (nécessite le venv
  de gel `v2/backend/.freeze-venv`)
- **macOS + Windows** : onglet *Actions* → workflow « Release (installeurs macOS
  + Windows) » → *Run workflow*, ou pousser un tag `v*`.

Le workflow de publication refuse désormais de produire un installeur public si
les certificats décrits dans [SIGNING.md](SIGNING.md) sont absents. Un build de
développement local reste possible sans certificat.

## État vérifié

Dernière validation complète le 28 juillet 2026 :

- 179 tests backend réussis, 4 scénarios optionnels ignorés;
- 4 tests frontend et 1 test Rust réussis;
- builds Vite et Tauri vérifiés;
- audits npm et Python sans vulnérabilité connue;
- benchmark textuel: 30 cas sur 30, aucun faux positif, p95 à 18,32 ms avec ONNX;
- contrôles visuels desktop, largeur minimale Tauri et mobile sans débordement.

Ces mesures protègent les régressions connues. Elles ne remplacent pas encore un
corpus audio annoté provenant de plusieurs églises, identifié comme la priorité
scientifique de la [feuille de route](v2/ROADMAP_INNOVATIONS.md).
