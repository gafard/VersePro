# Kit de démarrage régie et checklist culte - VersePro

> Guide opérateur vérifié pour VersePro 2.1.8, le 23 août 2026.
> À imprimer ou à garder ouvert sur l'ordinateur de régie.

## 1. Checklist pré-vol - 30 minutes avant le culte

### 1. Écrans et sorties

- [ ] Brancher le vidéoprojecteur et choisir le mode **Bureau étendu** sur macOS
  ou Windows.
- [ ] Dans **Régie en direct > Avant le culte**, ouvrir **Écran Secours**.
- [ ] Glisser cette fenêtre sur le vidéoprojecteur puis utiliser le plein écran du
  navigateur (`F11` sous Windows, ou le raccourci plein écran du navigateur sur
  macOS).
- [ ] Si OBS ou vMix est utilisé, ouvrir **Source OBS/vMix** et vérifier la source
  navigateur locale avant le direct.
- [ ] Si NDI est utilisé, l'activer dans **Paramètres > Sorties** et vérifier la
  source nommée par défaut **VersePro**. NDI est optionnel et désactivé par
  défaut.

### 2. Entrée audio

- [ ] Dans **Paramètres > Audio > Entrée micro**, sélectionner l'entrée reliée à
  la table de mixage, à la carte son USB ou au réseau audio.
- [ ] Choisir le prétraitement adapté : **Signal brut**, **Parole** ou
  **Église avec musique**.
- [ ] Demander un test de voix. Les LED du vu-mètre doivent bouger et rester
  principalement vertes ou jaunes. Une zone rouge allumée en continu indique un
  niveau trop élevé.
- [ ] Vérifier qu'aucune alerte **AUCUN signal depuis 8 s** n'apparaît.
- [ ] Dans **Paramètres > Moteurs**, vérifier que Deepgram est disponible ou
  qu'un moteur local Nemotron/Vosk est prêt.

> Le vu-mètre de VersePro affiche un niveau relatif en pourcentage. Il ne doit
> pas être documenté comme un instrument calibré en dBFS.

### 3. Plan de prédication et Bible

- [ ] Si les notes du pasteur sont disponibles, ouvrir
  **Paramètres > Avancé > Notes du sermon et extraction**.
- [ ] Coller les notes, cliquer sur **Extraire les versets**, puis sur
  **Ajouter tous au déroulé**.
- [ ] Vérifier le compteur **Plan** dans la régie et l'ordre des références sous
  **Déroulé du culte**.
- [ ] Vérifier la version biblique installée. LSG et KJF sont distribuées avec
  le projet ; les autres versions apparaissent seulement si elles ont été
  importées ou installées.

> Dans la recherche manuelle, `Entrée` projette par défaut. Le bouton
> **Préparer** charge l'aperçu de sortie ; il n'ajoute pas la référence au
> déroulé du culte.

### 4. Contrôle de sécurité

- [ ] Ouvrir **Avant le culte > Contrôle avant direct** et résoudre les éléments
  bloquants.
- [ ] Garder le **Mode sûr** activé si chaque projection doit être validée par
  l'opérateur.
- [ ] Projeter un verset de test, puis utiliser **Effacer**.
- [ ] Repérer le bouton **Arrêt d'urgence**, placé dans la colonne gauche sous
  le contrôle du micro.
- [ ] Confirmer qu'une sortie locale reste disponible si ProPresenter est
  déconnecté.

## 2. Fiche réflexe pendant la prédication

| Situation | Réaction de VersePro | Action du régisseur |
| --- | --- | --- |
| Le pasteur annonce une référence claire, par exemple « Jean 3:16 ». | Le parser explicite ajoute la référence à la file. | En mode sûr, relire puis cliquer sur **Projeter**. En diffusion automatique, contrôler immédiatement l'écran public. |
| Le pasteur avance ou recule dans le chapitre. | Jusqu'à dix numéros voisins apparaissent sous la recherche quand un verset est à l'antenne. | Cliquer sur le numéro voulu. L'envoi est immédiat. |
| Le pasteur paraphrase ou raconte un passage sans référence. | L'index sémantique ou l'IA peut proposer une référence avec un badge de suggestion. Ce résultat n'est pas garanti. | Relire le texte biblique avant de projeter. Rechercher manuellement en cas de doute. |
| Une recherche manuelle est nécessaire. | La recherche locale commence dès deux caractères ; la recherche sémantique à partir de deux mots. | Utiliser `↑` et `↓`, puis `Entrée` pour projeter la proposition sélectionnée, ou cliquer sur **Projeter**. |
| Une référence est déjà dans le déroulé. | Elle apparaît dans la colonne gauche avec son état. | Cliquer sur la ligne préparée pour la projeter. |
| ProPresenter est déconnecté. | VersePro signale **Projection locale active**. | Continuer avec **Écran Secours** et diagnostiquer ProPresenter après le culte si nécessaire. |

## 3. Raccourcis clavier vérifiés

| Contexte | Raccourci | Action |
| --- | --- | --- |
| Partout | `Cmd+K` / `Ctrl+K` | Ouvre ou ferme la palette biblique unifiée. |
| Partout, hors champ de saisie | `Cmd+Z` / `Ctrl+Z` | Restaure la projection précédente ou efface l'écran si nécessaire. |
| File de validation | `↑` / `↓` | Déplace la sélection dans les cartes en attente. |
| File de validation | `Espace` ou `Entrée` | Projette la carte sélectionnée. |
| File de validation | `Échap` ou `Retour arrière` | Rejette la carte sélectionnée. |
| File de validation | `P` | Monte la carte sélectionnée dans l'aperçu. |
| Aperçu | `T` | Envoie l'aperçu à l'antenne. |
| Régie | `/` | Place le curseur dans la recherche manuelle. |
| Recherche | `↑` / `↓` | Navigue dans les suggestions. |
| Recherche | `Entrée` | Projette la suggestion sélectionnée ou la référence saisie. |
| Recherche | `Échap` | Ferme les suggestions sans projeter. |

## 4. Sécurité et urgences

### Arrêt d'urgence

Le bouton **Arrêt d'urgence** :

1. arrête l'enregistrement et le micro local ;
2. désactive la diffusion automatique ;
3. active le mode sûr ;
4. coupe l'avance automatique de lecture ;
5. efface les sorties de projection.

Le service reste ouvert pour permettre au régisseur de reprendre après le
diagnostic.

### Mode sûr

Le **Mode sûr** empêche la diffusion automatique et l'avance automatique de la
lecture vivante. Chaque référence doit être validée manuellement. L'activation
de **Diffusion en direct** désactive ce mode, car les deux comportements sont
incompatibles.

### Sortie de secours

Si ProPresenter, NDI ou vMix ne répond plus, utiliser l'écran navigateur local :

```text
http://127.0.0.1:17871/output
```

## 5. Sorties et adresses utiles

| Usage | Adresse ou source | État dans le paquet 2.1.8 |
| --- | --- | --- |
| Console opérateur | Application VersePro | Opérationnel |
| Écran public local | `http://127.0.0.1:17871/output` | Opérationnel sur l'ordinateur VersePro |
| Retour scène local | `http://127.0.0.1:17871/stage` | Opérationnel sur l'ordinateur VersePro |
| Source navigateur OBS/vMix | `http://127.0.0.1:17871/obs?theme=lower-third&bg=transparent` | Opérationnel sur le même ordinateur |
| NDI | Source `VersePro` | Optionnel, dépend du runtime NDI et doit être activé |
| Suivi assemblée | `/follow` | Page présente, accès téléphone non livré dans le paquet 2.1.8 |
| Retour scène distant | `/stage` par IP locale | Page présente, accès téléphone non livré dans le paquet 2.1.8 |

### Avertissement réseau

Le backend de l'application desktop 2.1.8 écoute sur `127.0.0.1`. Remplacer
`127.0.0.1` par l'adresse IP du PC ou scanner le QR code ne rend donc pas encore
la page accessible depuis un smartphone. Le QR mobile doit être considéré comme
**expérimental** jusqu'à la livraison d'un listener LAN séparé et protégé par un
jeton.

---

VersePro 2.1.8 - Selah Studios - État documentaire vérifié le 23 août 2026.
