# Corpus de rejeu — conditions réelles d'église

Ce corpus existe parce que les 30 phrases propres du banc historique ne disent
rien de ce qui arrive quand un prédicateur parle vite, avec de la réverbération,
un micro saturé ou de la musique sous la voix. De vrais enregistrements ont déjà
révélé plusieurs défauts; leurs extraits textuels sont devenus des cas
permanents. La prochaine étape est de diversifier les salles et d'annoter un jeu
audio de validation séparé.

Chaque cas ajouté ici devient un test permanent : ce qui a échoué une fois ne
peut plus échouer en silence.

État vérifié le 22 août 2026 : 43 cas, 86,1 % d'exactitude, 89,3 % de
précision, 80,7 % de rappel et six cas manqués en rejeu texte avec e5-base.

---

## Consentement et vie privée — à lire avant d'enregistrer

Un enregistrement de culte capte **la voix du prédicateur et celle de
l'assemblée**. Ce n'est pas un fichier technique anodin.

- **Demandez l'accord explicite** du prédicateur avant tout enregistrement, et
  informez l'assemblée. Un accord verbal du pasteur ne vaut pas pour les
  personnes qui interviennent depuis la salle.
- **N'ajoutez au corpus que l'extrait utile** — quelques secondes autour de la
  citation — jamais la prédication entière.
- **Aucun audio n'est versionné dans git.** Les `.wav` sont ignorés
  (voir `.gitignore`) : ils restent sur la machine qui les a produits. Seuls
  les fichiers `cas.json` — texte transcrit et référence attendue — sont
  partagés.
- **Anonymisez** : pas de nom de personne dans les identifiants de cas ni dans
  les champs `conditions`.
- En cas de doute, **le cas texte suffit**. Un transcript sans audio éprouve
  déjà toute la cascade de détection.

---

## Structure

```
corpus/
  cas/
    <identifiant>/
      cas.json      obligatoire
      audio.wav     facultatif — mono 16 bits, non versionné
```

### `cas.json`

```json
{
  "text": "ouvrons ensemble Romains chapitre huit verset vingt-huit",
  "expected": "Rm 8:28",
  "kind": "explicite",
  "conditions": {
    "accent": "afrique de l'ouest",
    "debit": "rapide",
    "acoustique": "reverberation forte",
    "fond": "musique douce",
    "micro": "sature"
  }
}
```

- `text` — la transcription attendue. Pour un cas audio, elle sert de repère :
  c'est l'ASR qui produira le texte réellement analysé.
- `expected` — la référence qui **devait** être détectée. `null` est une valeur
  légitime et précieuse : elle décrit un passage où VersePro ne doit **rien**
  projeter (mention d'un prénom biblique, expression courante, chiffre isolé).
- `kind` — `explicite`, `paraphrase`, `allusion`, `negatif`, `garde`, `incident`.
- `ancre` — facultatif : le passage que le prédicateur venait d'ouvrir
  (« Exode 17 »). Le rejeu le fait passer par l'étage explicite avant de
  jouer le cas, exactement comme le direct. C'est ce qui permet de mesurer
  VerseGraph. Trois usages, et il faut les trois pour que la mesure soit
  honnête : une allusion au passage ouvert (doit être trouvée), une phrase
  de culte ordinaire pendant que le passage est ouvert (ne doit **rien**
  proposer), et une citation d'un **autre** livre (l'ancre ne doit pas la
  masquer — c'est le `kind: garde`).
- `conditions` — champs libres, mais restez cohérent d'un cas à l'autre : ce
  sont eux qui permettront de dire « on échoue surtout en réverbération forte »
  plutôt que « on échoue parfois ».

---

## Ce qu'il faut collecter en priorité

Par ordre d'utilité décroissante :

1. **Les négatifs.** Un faux positif projeté devant l'assemblée coûte plus cher
   qu'une détection manquée. Les phrases où il ne faut RIEN projeter sont
   sous-représentées partout, et ce sont les plus révélatrices.
2. **Les accents francophones** — Afrique de l'Ouest, Centrale, Antilles,
   Québec, Europe. Les modèles sont entraînés majoritairement sur du français
   hexagonal.
3. **Le débit rapide et les reprises** — hésitations, répétitions, phrases
   inachevées : la prédication réelle n'est pas de la dictée.
4. **Les conditions dégradées** — réverbération d'un grand volume, musique de
   fond, micro saturé, coupure réseau.
5. **Les paraphrases et allusions**, qui sont le vrai terrain de la recherche
   sémantique.

---

## Utilisation

```bash
# Rejeu rapide, texte seul — convient à l'intégration continue
python3 benchmarks/replay_lab.py --corpus corpus/ --sans-audio --sortie run.json

# Rejeu complet, audio traversant Vosk comme un dimanche matin
python3 benchmarks/replay_lab.py --corpus corpus/ --sortie run.json

# Comparer deux versions : sort en code 1 s'il y a une régression
python3 benchmarks/replay_lab.py --comparer avant.json apres.json

# Figer un raté observé en culte
python3 benchmarks/replay_lab.py --capturer "ce qui a été dit" --attendu "Rm 8:28"
```

Un cas audio est **ignoré**, non compté en échec, si Vosk n'est pas installé :
un modèle absent n'est pas une régression de détection, et les confondre
fausserait toutes les mesures.
