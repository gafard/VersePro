"""Fusion hybride de la détection de versets.

La détection en direct dispose de trois récupérateurs INDÉPENDANTS :

  1. citation explicite (regex)      — précision quasi parfaite, instantanée
  2. lexical / flou (verse_parser)   — accroches connues + signatures floues
  3. sémantique e5 (embeddings ONNX) — sens, paraphrases

Les stratégies « le premier qui répond gagne » ratent des versets (un seul
récupérateur voit la paraphrase) OU laissent passer des faux (un récupérateur
s'emballe sur un mot isolé). La fusion règle les deux :

  • Reciprocal Rank Fusion (RRF) agrège les classements des récupérateurs.
  • L'ACCORD entre récupérateurs indépendants est le signal le plus fort :
    un vrai verset ressort du lexical ET du sémantique ; un bruit (« j'achète du
    pain ») ne touche qu'un seul récupérateur, sur un seul mot.
  • Un recouvrement lexical de CONFIRMATION (mots du verset réellement
    prononcés, tolérant à la morphologie française) tue les faux positifs sans
    durcir les seuils.

Ce module est pur (aucune I/O) pour être testable et rapide (< 1 ms).
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Optional

# ── Encadrement d'attribution : « Paul dit… », « David a écrit… », « il est
#    écrit… ». Le prédicateur attribue le verset avant de le (para)phraser ; ces
#    mots diluent l'embedding et attirent des versets contenant le nom. On les
#    retire de la REQUÊTE de récupération (jamais du chemin explicite). ──
_ATTR_NAMES = (
    r"paul|jean|pierre|jacques|matthieu|marc|luc|david|moïse|moise|salomon|"
    r"[ée]sa[ïi]e|j[ée]r[ée]mie|[ée]z[ée]chiel|daniel|timoth[ée]e|tite|abraham|"
    r"isaac|jacob|joseph|samuel|[ée]lie|[ée]lis[ée]e|josu[ée]|n[ée]h[ée]mie"
)
_ATTR_VERBS = (
    r"dit|a dit|disait|[ée]crit|a [ée]crit|[ée]crivait|rappelle|nous rappelle|"
    r"d[ée]clare|affirme|enseigne|nous enseigne|proclame|nous dit"
)
_ATTR_RE = re.compile(
    rf"\b(?:l['e ]?ap[oô]tre |le roi |le proph[èe]te |saint |l['e ]?[ée]vang[ée]liste )?"
    rf"(?:{_ATTR_NAMES})\b(?:\s+(?:nous|vous))?\s+(?:{_ATTR_VERBS})\b[ ,:]*",
    re.IGNORECASE,
)
_GENERIC_ATTR_RE = re.compile(
    r"\b(?:comme )?(?:il est [ée]crit|il est dit|il a [ée]t[ée] dit|"
    r"l['e ][ée]criture (?:dit|d[ée]clare)|la parole (?:dit|nous dit)|la bible dit)\b[ ,:]*",
    re.IGNORECASE,
)


def strip_attribution(text: str) -> str:
    """Retire l'encadrement d'attribution d'une requête (accents préservés)."""
    text = _ATTR_RE.sub(" ", text)
    text = _GENERIC_ATTR_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def recent_window(text: str, max_words: int) -> str:
    """Fenêtre de détection = DERNIÈRE PHRASE (Deepgram ponctue ses finaux).

    Isoler la phrase courante évite qu'une phrase voisine (un autre verset, une
    remarque logistique) pollue la requête. Complète avec la phrase précédente si
    la dernière est trop courte, plafonne à max_words, et retombe sur les derniers
    mots si le flux n'a aucune ponctuation (cas Vosk)."""
    segments = [s.strip() for s in re.split(r"[.!?;\n]+", text) if s.strip()]
    if not segments:
        return " ".join(text.split()[-max_words:])
    chosen = segments[-1]
    if len(chosen.split()) < 4 and len(segments) >= 2:
        chosen = segments[-2] + " " + chosen
    return " ".join(chosen.split()[-max_words:])

# Mots-outils français : exclus du recouvrement lexical même s'ils sont longs.
_STOPWORDS = {
    "dans", "pour", "avec", "cette", "comme", "mais", "donc", "elle", "ils",
    "nous", "vous", "leur", "leurs", "dont", "tout", "tous", "toute", "toutes",
    "plus", "très", "aussi", "alors", "quand", "parce", "afin", "ainsi", "sans",
    "sous", "chez", "entre", "vers", "depuis", "pendant", "avant", "après",
    "encore", "toujours", "jamais", "être", "était", "étaient", "sont", "avez",
    "avons", "font", "fait", "faire", "cela", "celui", "celle", "ceux", "que",
    "qui", "quoi", "est", "les", "des", "une", "aux", "son", "ses", "mes",
    "tes", "nos", "vos", "car", "ne", "pas", "lui", "eux", "moi", "toi",
    "voici", "voilà", "puis", "ici", "là",
}

# Radicaux FAIBLES : trop répandus pour confirmer un verset précis. Deux familles.
#
# 1. Noms d'auteurs / personnages, employés en ENCADREMENT (« Paul dit… »).
# 2. Vocabulaire religieux ultra-courant : « la parole de Dieu », « le Seigneur »
#    traversent des centaines de versets. Sans cette exclusion, « tout n'est pas
#    évident dans la parole de Dieu » se faisait confirmer par 1 Timothée 4:5
#    (« sanctifiée par la parole de Dieu ») sur deux mots creux.
#
# Les versets où ces mots comptent vraiment gardent assez de mots distinctifs
# (« au commencement / créa / cieux / terre » pour Genèse 1:1).
# Radicaux tronqués à 5 caractères — au-delà, ils ne peuvent jamais s'apparier.
_WEAK_STEMS = {
    # personnages
    "paul", "jean", "pierr", "jacqu", "matth", "marc", "luc", "david",
    "moise", "salom", "esaie", "jerem", "ezech", "danie", "timot", "tite",
    "phile", "abrah", "isaac", "jacob", "josep", "samue", "elie", "elise",
    "apotr", "proph", "disci", "frere",
    # vocabulaire religieux passe-partout
    "dieu", "seign", "jesus", "chris", "espri", "parol", "saint",
}


def _strip_accents(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def content_stems(text: str) -> set:
    """Radicaux des mots de contenu (accents retirés, mots-outils écartés).

    Radical = 5 premières lettres — un stemming grossier qui rapproche les
    formes françaises (« marché »/« marcha », « eau »/« eaux », pluriels,
    conjugaisons) sans dépendance externe."""
    out = set()
    for raw in _strip_accents(text.lower()).replace("'", " ").replace("-", " ").split():
        word = "".join(ch for ch in raw if ch.isalnum())
        if len(word) < 4 or word in _STOPWORDS:
            continue
        stem = word[:5]
        if stem in _WEAK_STEMS:  # trop répandu pour confirmer un verset précis
            continue
        out.add(stem)
    return out


# En dessous de ce nombre de radicaux prononcés, un taux de couverture ne
# prouve rien. Une prédication réelle de 2 h 14 l'a montré : « est-ce que tu
# as fait quelque chose à quelqu'un ici » se réduit à DEUX radicaux —
# « chose » et « quelq » — tous deux présents dans Philémon 1:18. Le
# recouvrement valait donc 1,00, et comme la confiance fusionnée prend le
# maximum des trois signaux, la proposition sortait à 1,00 : la note la plus
# haute du système, sur la locution la plus banale du français.
#
# Sur 31 102 versets, deux radicaux génériques se retrouvent quelque part avec
# une quasi-certitude. Ce n'est pas une confirmation, c'est une coïncidence.
RADICAUX_MIN_QUASI_CITATION = 4


def lexical_overlap(spoken: str, verse_text: str) -> float:
    """Part des mots de contenu PRONONCÉS que l'on retrouve dans le verset.

    Orienté « la parole confirme-t-elle ce verset ? » : coverage des radicaux
    prononcés présents dans le verset. Robuste aux versets longs (on ne divise
    pas par la longueur du verset).

    Le rapport reste brut : c'est aux règles de déclenchement de tenir compte
    du nombre de radicaux, car un même taux ne vaut pas la même chose selon
    qu'il porte sur deux mots ou sur huit."""
    sw = content_stems(spoken)
    if not sw:
        return 0.0
    vw = content_stems(verse_text)
    if not vw:
        return 0.0
    return len(sw & vw) / len(sw)


def _cand_texts(cand: Dict[str, Any]) -> List[str]:
    """Toutes les formulations connues du verset : version active + traductions.
    Le prédicateur peut paraphraser n'importe quelle version — on confirme donc
    le recouvrement lexical contre la MEILLEURE d'entre elles."""
    texts = [cand.get("text", "")]
    texts.extend((cand.get("translations") or {}).values())
    return [t for t in texts if t]


def best_overlap(spoken: str, cand: Dict[str, Any]) -> float:
    return max((lexical_overlap(spoken, t) for t in _cand_texts(cand)), default=0.0)


def _ref_key(cand: Dict[str, Any]) -> str:
    verse = cand.get("verse_start", cand.get("verse"))
    # Les deux index ne garantissent pas la même casse ni les mêmes accents
    # d'abréviation ("Ph"/"ph", "És"/"és"). Sans canonisation, un véritable
    # accord était interprété comme deux références distinctes.
    book = _strip_accents(str(cand.get("book_abbr") or "")).casefold()
    return f"{book}|{cand.get('chapter')}|{verse}"


def _reciprocal_rank(ranked_keys: List[str], k: int = 60) -> Dict[str, float]:
    return {key: 1.0 / (k + rank) for rank, key in enumerate(ranked_keys)}


def fuse(
    lexical: List[Dict[str, Any]],
    semantic: List[Dict[str, Any]],
    spoken: str,
    *,
    semantic_threshold: float,
    semantic_margin: float,
    overlap_min: float,
    top_n: int = 5,
) -> Optional[Dict[str, Any]]:
    """Fusionne les candidats lexicaux et sémantiques et décide s'il faut
    proposer un verset. Renvoie le candidat retenu (enrichi de métadonnées de
    décision) ou None. Ne projette jamais seul : le résultat va en validation.
    """
    lexical = lexical[:top_n]
    semantic = semantic[:top_n]
    if not lexical and not semantic:
        return None

    lex_keys = [_ref_key(c) for c in lexical]
    sem_keys = [_ref_key(c) for c in semantic]
    lex_set, sem_set = set(lex_keys), set(sem_keys)

    rrf = _reciprocal_rank(lex_keys)
    for key, score in _reciprocal_rank(sem_keys).items():
        rrf[key] = rrf.get(key, 0.0) + score

    # Meilleur score sémantique brut + dauphin (pour la marge d'ambiguïté).
    sem_scores = [float(c.get("score") or c.get("confidence") or 0) for c in semantic]
    sem_top = sem_scores[0] if sem_scores else 0.0
    sem_runner = sem_scores[1] if len(sem_scores) > 1 else 0.0

    # Table des candidats par référence (on garde le dict le plus riche en texte).
    by_key: Dict[str, Dict[str, Any]] = {}
    for cand in semantic + lexical:  # sémantique d'abord : texte du verset garanti
        by_key.setdefault(_ref_key(cand), cand)

    scored = []
    for key, cand in by_key.items():
        in_lex, in_sem = key in lex_set, key in sem_set
        overlap = best_overlap(spoken, cand)
        sem_score = 0.0
        if in_sem:
            i = sem_keys.index(key)
            sem_score = float(semantic[i].get("score") or semantic[i].get("confidence") or 0)
        lex_score = 0.0
        if in_lex:
            i = lex_keys.index(key)
            lex_score = float(lexical[i].get("confidence") or 0)
        scored.append({
            "cand": cand, "key": key, "agreement": in_lex and in_sem,
            "in_lex": in_lex, "in_sem": in_sem, "overlap": overlap,
            "sem_score": sem_score, "lex_score": lex_score, "rrf": rrf.get(key, 0.0),
            "curated": in_lex and cand.get("detection_method") == "text_phrase" and lex_score >= 0.95,
        })

    # Tri : accord d'abord, puis RECOUVREMENT, puis RRF en départage.
    # Le recouvrement prime sur le rang : un récupérateur peut classer premier un
    # verset ADJACENT qui partage une tournure (Jn 3:15 vs 3:16 — « afin que
    # quiconque croit en lui »). Les mots réellement prononcés tranchent mieux
    # que le rang. Arrondi à 2 décimales pour laisser le RRF départager les ex æquo.
    scored.sort(key=lambda s: (s["agreement"], round(s["overlap"], 2), s["rrf"]), reverse=True)
    best = scored[0]

    # ── Règles de décision (proposer un verset en validation) ──
    surfaced = False
    reason = ""
    # 1. Accord des deux récupérateurs indépendants + confirmation lexicale souple.
    if best["agreement"] and best["overlap"] >= overlap_min * 0.6:
        surfaced, reason = True, "accord lexical+sémantique"
    # 2. Accroche connue (phrase curée, vérifiée à la main) : substring exact.
    elif best["curated"]:
        surfaced, reason = True, "accroche curée"
    # 3. Sémantique forte confirmée par le recouvrement lexical. Le recouvrement
    #    lève l'ambiguïté à la place de la marge sémantique (trop fragile quand le
    #    prédicateur paraphrase une autre traduction que la version indexée).
    elif (best["in_sem"] and best["sem_score"] >= semantic_threshold
          and best["overlap"] >= overlap_min):
        surfaced, reason = True, "sémantique forte + recouvrement"
    # 4. Citation presque littérale classée un peu sous le seuil sémantique.
    # Un extrait pris au milieu d'un long verset est parfois moins bien classé
    # que les débuts de versets (Jean 7:37 arrivait 8e à 0,830 pour un seuil
    # de 0,8385), alors que tous ses mots distinctifs correspondaient. Cette
    # porte exige quatre radicaux ET 90 % de couverture : elle ne transforme
    # donc pas une vague proximité de sens en détection.
    elif (
        best["in_sem"]
        and best["sem_score"] >= max(0.0, semantic_threshold - 0.03)
        and best["overlap"] >= 0.90
        and len(content_stems(spoken)) >= RADICAUX_MIN_QUASI_CITATION
    ):
        surfaced, reason = True, "quasi-citation sémantique"
    # 5. Quasi-citation repérée au lexical : forte couverture des mots prononcés
    #    (near-verbatim). Le récupérateur lexical seul suffit alors — même si le
    #    sémantique s'est égaré et si le score flou est modeste.
    #
    #    Cette règle AFFIRME une citation quasi littérale ; elle exige donc
    #    d'avoir assez de mots pour le dire. Une prédication réelle de 2 h 14
    #    l'a montré : « est-ce que tu as fait quelque chose à quelqu'un ici »
    #    ne laisse que deux radicaux — « chose » et « quelq » — tous deux
    #    présents dans Philémon 1:18. Recouvrement 1,00, confiance 1,00, sur
    #    la locution la plus banale du français. Sur 31 102 versets, deux
    #    radicaux génériques se retrouvent quelque part à coup sûr : ce n'est
    #    pas une citation, c'est une coïncidence.
    #
    #    Les autres règles ne sont pas touchées : elles s'appuient sur l'accord
    #    des deux récupérateurs ou sur un score sémantique fort, qui gardent
    #    leur sens sur un énoncé court (« Pierre a marché sur l'eau », un seul
    #    radical utile, reste détecté par la règle 3).
    elif (best["in_lex"] and best["overlap"] >= 0.55
          and len(content_stems(spoken)) >= RADICAUX_MIN_QUASI_CITATION):
        surfaced, reason = True, "quasi-citation lexicale"
    # 6. Flou lexical fort confirmé par le recouvrement minimal.
    elif best["in_lex"] and best["lex_score"] >= 0.8 and best["overlap"] >= overlap_min:
        surfaced, reason = True, "flou fort + recouvrement"

    if not surfaced:
        return None

    result = dict(best["cand"])
    # Confiance fusionnée lisible (0..1) : plancher au score sémantique, bonus d'accord.
    #
    # Le recouvrement ne compte que s'il porte sur assez de mots. Sinon
    # « Pierre a marché sur l'eau vers Jésus » — un seul radical utile, les
    # autres mots étant écartés comme trop répandus — sortait à 1,00, la note
    # maximale du système. La détection était juste, la note ne l'était pas :
    # l'opérateur lit ce chiffre pour décider s'il projette sans relire.
    signaux = [best["sem_score"], best["lex_score"]]
    if len(content_stems(spoken)) >= RADICAUX_MIN_QUASI_CITATION:
        signaux.append(best["overlap"])
    confidence = max(signaux)
    if best["agreement"]:
        confidence = min(0.99, confidence + 0.08)
    result["confidence"] = round(confidence, 4)
    result["detection_method"] = "semantic_local"
    result["requires_review"] = True
    result["fusion"] = {
        "reason": reason, "agreement": best["agreement"], "overlap": round(best["overlap"], 3),
        "sem_score": round(best["sem_score"], 3), "lex_score": round(best["lex_score"], 3),
    }
    return result
