# Design — VersePro

Système de design verrouillé pour cette application. Chaque redesign de page
lit ce fichier avant d'émettre du code. Ne pas régénérer par page — étendre ou
amender ce fichier quand le système doit grandir.

## Genre
atmospheric — l'outil vit dans le noir d'une cabine de régie ; la landing
partage cette obscurité d'instrument.

## Macrostructure family
- Marketing (LandingPage) : **Marquee Hero**, variante Lumen canonique —
  surface produit VersePro à droite du hero, titre bas-de-casse à gauche,
  bande-mètre sous le pli. Le logiciel est le visuel marketing : pas
  d'illustration IA, pas de faux chrome navigateur.
- App (LiveDetection, History, Statistics, Settings) : **Workbench** —
  la fonction porte la page. AUCUN enrichissement. Panneaux hairline,
  densité d'outil.
- Écrans de diffusion (/output, /stage, /follow) : typographie seule,
  noir absolu, accents du thème.

## Theme — Lumen · Night Foundry
- `--color-paper`      oklch(13% 0.014 265)  — studio de nuit, tirant violet
- `--color-paper-2`    oklch(16% 0.015 265)
- `--color-paper-3`    oklch(19% 0.016 265)
- `--color-ink`        oklch(96% 0.006 262)  — titres presque blancs
- `--color-ink-2`      oklch(78% 0.010 262)  — corps
- `--color-muted`      oklch(58% 0.012 262)
- `--color-rule`       oklch(96% 0.006 262 / 0.08)
- `--color-rule-2`     oklch(96% 0.006 262 / 0.16)
- `--color-accent`     oklch(76% 0.17 50)    — laiton en fusion (émission)
- `--color-accent-ink` oklch(18% 0.05 50)
- `--color-accent-2`   oklch(68% 0.16 18)    — corde corail (verbe-repère)
- `--color-glow`       oklch(80% 0.16 50 / 0.42)
- `--color-paper-emit` oklch(76% 0.17 50 / 0.04)
- `--rule-blueprint`   oklch(96% 0.006 262 / 0.04)
- `--color-focus`      oklch(76% 0.17 50)

### Statuts fonctionnels de l'app (hors registre marketing)
La console signale des états opérationnels ; ces teintes sont des données,
pas de la décoration : ok `oklch(70% 0.12 155)` · danger `oklch(62% 0.19 25)`
· ia = corde corail `--color-accent-2`.

## Typography
- Display : Space Grotesk 600 (grotesk fort, registre « régie broadcast »),
  **bas-de-casse** sur toute prose marketing. Remplace l'ancien serif éditorial
  (Instrument Serif) jugé trop « plateforme IA ».
- Body : Geist Sans 400/500/600
- Mono (labels) : JetBrains Mono 400/500 — SEULE surface en MAJUSCULES
  (eyebrows `01 · RÉGIE`, callouts, labels de mètre, labels de stats)
- Display tracking : -0.02em (grotesk : moins serré que l'ancien serif)
- Ancre d'échelle : --text-display = clamp(2.75rem, 6vw + 1rem, 5.5rem)
- Polices AUTO-HÉBERGÉES via @fontsource (contrainte produit : l'application
  doit fonctionner sans internet le dimanche). Jamais de CDN de polices.

### Registre deux-casses — portée
Le bas-de-casse total (titres, corps, boutons, nav, marque) s'applique à la
**landing** et aux titres de sections marketing. Dans l'**app**, les données
utilisateur (références bibliques « Jn 3:16 », texte des versets, noms de
sessions) gardent leur casse naturelle — ce sont des données, pas de la prose.
Les labels de panneaux de l'app utilisent le registre mono-MAJUSCULES.

## Spacing
Échelle 4 pt nommée (tokens.css). Les pages utilisent les tokens nommés
(`var(--space-md)`), jamais de valeurs brutes.

## Motion
- Easings : `--ease-out: cubic-bezier(0.16, 1, 0.3, 1)` ·
  `--ease-soft: cubic-bezier(0.25, 0.1, 0.25, 1)`
- Appareil (Night) : pulsation 3 % sur 4 s. Ne tourne JAMAIS.
- Verbe-repère : souligné 1px qui se trace en 320 ms (délai 900 ms), une fois.
- Cartes : translateY(-4px) + éclat interne au survol, 220 ms.
- Reveal : opacité + 12 px, 600 ms, stagger 60 ms. Pas de slide latéral.
- prefers-reduced-motion : tout s'effondre à l'état final.

## Microinteractions stance
- Succès silencieux (toasts sobres existants) ; jamais de célébration.
- Optimistic update + Annuler plutôt que dialogues de confirmation.
- Tooltip : délai 800 ms au survol, 0 ms au focus.

## CTA voice
- Primaire : fond `--color-accent`, texte `--color-accent-ink`, rayon 10 px,
  bas-de-casse sur la landing (« ouvrir la régie »), casse normale dans l'app.
- Secondaire : hairline `--color-rule-2`, texte ink, fond transparent.

## Per-page allowances
- Landing : UNE surface produit en miniature, grille blueprint 4 %, bande-mètre,
  rangée de 3 preuves vérifiables. Aucun chiffre non confirmé.
- App : AUCUN enrichissement. Fonction d'abord.
- Settings : les réglages durables (entrée micro, clés, moteurs, sorties) vivent
  ici ; le Live ne garde que les commandes nécessaires pendant le direct.
- Écrans de diffusion : lisibilité absolue ; accents laiton/corail seulement.

## What pages MUST share
- Le logotype bas-de-casse : `versepro` (Space Grotesk) — plus de carré « VP ».
- L'accent laiton et sa discipline (≤ 5 % de la surface par viewport).
- Space Grotesk + Geist + JetBrains Mono.
- La voix CTA (formes, rayons, rythme de padding).
- Le motif eyebrow mono `NN · RÔLE`.

## What pages MAY differ on
- Macrostructure à l'intérieur de la famille de leur type de page.
- Densité (la console est dense, la landing respire).

## Interdits (rappel Lumen)
Aucun orbe lumineux · aucun italique · aucun dégradé sur du texte · aucun
glassmorphism · aucune métrique inventée · aucune casse de titre sur la
landing · jamais deux mots accentués par titre · l'appareil ne tourne pas.

## Exports

### tokens.css
Voir `v2/frontend/src/tokens.css` — source de vérité, importée avant index.css.
