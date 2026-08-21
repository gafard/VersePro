"""Index de recherche manuelle de fragments bibliques.

La détection live doit rester prudente : une conversation ordinaire ne doit
jamais partir à l'antenne parce qu'elle partage trois mots avec un verset. La
recherche manuelle répond à un autre besoin. L'opérateur demande explicitement
à fouiller la Bible ; elle peut donc accepter un fragment court, situé au
milieu d'un verset, et afficher plusieurs réponses sans rien projeter.

L'index ci-dessous est entièrement local. Il couvre toutes les traductions
installées, les fragments exacts, les petites erreurs de frappe/ASR et les
fragments qui traversent la frontière entre deux versets consécutifs.
"""

from __future__ import annotations

from array import array
from collections import Counter
from difflib import SequenceMatcher
import re
import unicodedata
from typing import Any, Dict, List

from loguru import logger


# Nombre maximal de versets réellement scorés en passe 2. Au-delà, le coût
# explose sans rien apporter : la liste est déjà ordonnée par pertinence.
CANDIDATS_SCORES_MAX = 400

# Mots examinés au plus par seau de préfixe lors de la recherche floue.
VOISINS_FLOUS_MAX = 600


def normalize_fragment(text: str) -> str:
    """Normalisation commune aux requêtes et aux textes bibliques."""
    value = (text or "").lower().replace("’", "'").replace("`", "'")
    value = "".join(
        char
        for char in unicodedata.normalize("NFD", value)
        if unicodedata.category(char) != "Mn"
    )
    # Une apostrophe sépare deux mots en français ("l'Éternel" ->
    # "l eternel"). La conserver créait deux vocabulaires incompatibles selon
    # que l'utilisateur la tapait ou non.
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def _ordered_coverage(query_words: List[str], text_words: List[str]) -> float:
    """Part des mots de la requête retrouvés dans le bon ordre."""
    if not query_words or not text_words:
        return 0.0
    cursor = 0
    found = 0
    for wanted in query_words:
        while cursor < len(text_words) and text_words[cursor] != wanted:
            cursor += 1
        if cursor >= len(text_words):
            break
        found += 1
        cursor += 1
    return found / len(query_words)


def _best_window_ratio(query: str, query_size: int, text_words: List[str]) -> float:
    """Similarité avec la meilleure fenêtre locale, pas le verset entier."""
    if not query or not text_words:
        return 0.0
    best = 0.0
    lower = max(1, query_size - 1)
    upper = min(len(text_words), query_size + 2)
    for size in range(lower, upper + 1):
        for start in range(0, len(text_words) - size + 1):
            candidate = " ".join(text_words[start : start + size])
            ratio = SequenceMatcher(None, query, candidate).ratio()
            if ratio > best:
                best = ratio
                if best >= 0.995:
                    return best
    return best


class ManualVerseIndex:
    """Index inversé compact, partagé par toutes les recherches manuelles."""

    def __init__(self, versions: Dict[str, dict], active_version: str = "LSG"):
        self.active_version = active_version
        self.entries: List[Dict[str, Any]] = []
        self._key_to_id: Dict[tuple, int] = {}
        self._postings: Dict[str, array] = {}
        self._words_by_prefix: Dict[str, List[str]] = {}
        self._build(versions)

    def _build(self, versions: Dict[str, dict]) -> None:
        # LSG d'abord : à score égal, l'édition active/public reste le résultat
        # naturel. Les autres traductions enrichissent ensuite le même verset.
        ordered_versions = sorted(
            versions.items(), key=lambda item: (0 if item[0] == self.active_version else 1, item[0])
        )
        posting_count = 0
        for version_id, version in ordered_versions:
            for book_abbr, chapters in version.items():
                for chapter, verses in chapters.items():
                    for verse, text in verses.items():
                        if not text:
                            continue
                        key = (book_abbr.casefold(), int(chapter), int(verse))
                        doc_id = self._key_to_id.get(key)
                        if doc_id is None:
                            doc_id = len(self.entries)
                            self._key_to_id[key] = doc_id
                            self.entries.append({
                                "book_abbr": book_abbr,
                                "chapter": int(chapter),
                                "verse": int(verse),
                                "texts": {},
                                "normalized": {},
                            })

                        normalized = normalize_fragment(text)
                        if not normalized:
                            continue
                        entry = self.entries[doc_id]
                        entry["texts"][version_id] = text
                        entry["normalized"][version_id] = normalized

                        # Une seule occurrence par mot, verset et traduction.
                        # array('I') évite plusieurs dizaines de Mo d'objets int.
                        for word in set(normalized.split()):
                            if len(word) < 2:
                                continue
                            posting = self._postings.get(word)
                            if posting is None:
                                posting = array("I")
                                self._postings[word] = posting
                                if len(word) >= 3:
                                    self._words_by_prefix.setdefault(word[:3], []).append(word)
                            posting.append(doc_id)
                            posting_count += 1

        logger.info(
            "🔍 Index de fragments manuels prêt : {} versets, {} mots, {:.1f} Mo de postings",
            len(self.entries),
            len(self._postings),
            posting_count * 4 / 1_000_000,
        )

    def _candidate_ids(self, words: List[str], max_candidates: int = 3000) -> List[int]:
        unique_words = list(dict.fromkeys(word for word in words if len(word) >= 2))
        available = []
        for word in unique_words:
            posting = self._postings.get(word)
            if posting:
                available.append((word, set(posting)))
                continue

            # Petite erreur de frappe ou d'ASR : « rugisant » doit retrouver
            # « rugissant ». Le vocabulaire est rangé par préfixe lors de la
            # construction, donc aucune exploration des 43 000 mots à chaque
            # frappe clavier.
            if len(word) >= 4:
                # BORNE SUR LA RECHERCHE FLOUE. Chaque mot introuvable fait
                # calculer un ratio de similarité contre TOUT le vocabulaire
                # partageant son préfixe. Avec huit traductions, certains seaux
                # comptent des milliers de mots, et une phrase en contient
                # plusieurs d'introuvables : c'est là que passaient les
                # dizaines de secondes.
                #
                # Les seaux sont remplis dans l'ordre de lecture de la Bible,
                # donc tronquer ne privilégie rien ; et un mot qui ne
                # ressemble à aucun des premiers n'en sauvera pas la requête.
                seau = self._words_by_prefix.get(word[:3], [])
                close_words = sorted(
                    (
                        (SequenceMatcher(None, word, candidate).ratio(), candidate)
                        for candidate in seau[:VOISINS_FLOUS_MAX]
                    ),
                    reverse=True,
                )
                close_sets = []
                for ratio, candidate in close_words[:4]:
                    if ratio < 0.72:
                        continue
                    close_sets.append(set(self._postings[candidate]))
                if close_sets:
                    available.append((word, set().union(*close_sets)))
        if not available:
            return []

        # Les mots rares sont les plus discriminants. Une intersection trouve
        # instantanément les fragments exacts, où qu'ils soient dans le verset.
        available.sort(key=lambda item: len(item[1]))
        intersection = set(available[0][1])
        for _, posting_set in available[1:]:
            intersection.intersection_update(posting_set)
            if not intersection:
                break
        if intersection:
            return list(intersection)[:max_candidates]

        # Une faute peut faire disparaître un mot de l'index. On garde alors
        # l'union des quatre mots les plus rares, classée par recouvrement.
        counts: Counter[int] = Counter()
        for _, posting_set in available[:4]:
            counts.update(posting_set)
        return [doc_id for doc_id, _ in counts.most_common(max_candidates)]

    def _next_entry(self, entry: Dict[str, Any]) -> Dict[str, Any] | None:
        next_id = self._key_to_id.get((
            str(entry["book_abbr"]).casefold(),
            int(entry["chapter"]),
            int(entry["verse"]) + 1,
        ))
        return self.entries[next_id] if next_id is not None else None

    @staticmethod
    def _score(query: str, query_words: List[str], candidate: str) -> float:
        if not candidate:
            return 0.0
        if query == candidate or f" {query} " in f" {candidate} ":
            return 1.0

        candidate_words = candidate.split()
        if len(query_words) == 1:
            # Pour un seul mot, seuls les mots entiers exacts sont assez sûrs.
            return 0.98 if query_words[0] in candidate_words else 0.0

        query_set = set(query_words)
        candidate_set = set(candidate_words)
        lexical = len(query_set & candidate_set) / max(1, len(query_set))
        # Ne pas lancer des milliers de comparaisons de fenêtres lorsqu'une
        # phrase de trois mots n'en partage même pas la moitié avec le verset.
        # Les vraies paraphrases passent par l'index sémantique ; ce chemin-ci
        # est destiné aux fragments textuels et petites fautes.
        if len(query_words) >= 3 and lexical < 0.5:
            return 0.0
        if len(query_words) == 2 and lexical == 0.0:
            return 0.0
        ordered = _ordered_coverage(query_words, candidate_words)
        window = _best_window_ratio(query, len(query_words), candidate_words)

        # La fenêtre locale capture les fautes ("rugisant"), le recouvrement
        # protège contre une ressemblance orthographique fortuite, et l'ordre
        # départage les versets faits des mêmes mots.
        return 0.50 * window + 0.32 * lexical + 0.18 * ordered

    def _rank_hits(self, hits: Dict[tuple, Dict[str, Any]], top_k: int) -> List[Dict[str, Any]]:
        ranked = sorted(
            hits.values(),
            key=lambda item: (
                item["score"],
                1 if item["matched_version"] == self.active_version else 0,
                -int(item["chapter"]),
            ),
            reverse=True,
        )
        return ranked[: max(1, int(top_k))]

    def search(self, query: str, top_k: int = 12) -> List[Dict[str, Any]]:
        normalized_query = normalize_fragment(query)
        query_words = normalized_query.split()
        if not normalized_query or not query_words:
            return []

        candidate_ids = self._candidate_ids(query_words)

        # Passe 1 — sous-chaîne exacte. C'est le cas normal de la recherche
        # manuelle et il doit répondre pendant la frappe. L'ancienne boucle
        # calculait aussi des milliers de ratios flous pour les autres versets,
        # alors qu'ils ne peuvent de toute façon pas battre un score exact.
        hits: Dict[tuple, Dict[str, Any]] = {}
        padded_query = f" {normalized_query} "
        for doc_id in candidate_ids:
            entry = self.entries[doc_id]
            next_entry = self._next_entry(entry)
            for version_id, normalized_text in entry["normalized"].items():
                if padded_query in f" {normalized_text} ":
                    hits[(doc_id, None)] = {
                        "book_abbr": entry["book_abbr"],
                        "chapter": entry["chapter"],
                        "verse": entry["verse"],
                        "verse_end": None,
                        "score": 1.0,
                        "matched_version": version_id,
                        "matched_text": entry["texts"].get(version_id, ""),
                        "detection_method": "manual_exact",
                    }
                    break
                if next_entry and version_id in next_entry["normalized"]:
                    joined = f"{normalized_text} {next_entry['normalized'][version_id]}"
                    if padded_query in f" {joined} ":
                        end_verse = int(next_entry["verse"])
                        hits[(doc_id, end_verse)] = {
                            "book_abbr": entry["book_abbr"],
                            "chapter": entry["chapter"],
                            "verse": entry["verse"],
                            "verse_end": end_verse,
                            "score": 1.0,
                            "matched_version": version_id,
                            "matched_text": (
                                f"{entry['texts'].get(version_id, '')} "
                                f"{next_entry['texts'].get(version_id, '')}"
                            ).strip(),
                            "detection_method": "manual_cross_verse",
                        }
                        break

        if hits:
            return self._rank_hits(hits, top_k)

        # Passe 2 — seulement en l'absence totale de texte exact : petites
        # fautes de frappe/ASR. Les paraphrases pures sont prises en charge par
        # l'index neuronal appelé en parallèle par la route HTTP.
        #
        # BORNE DE TRAVAIL. Sans elle, une phrase sans correspondance exacte
        # fait scorer jusqu'à trois mille candidats sur huit traductions, avec
        # une fenêtre glissante pour chacun. Mesuré sur des descriptions
        # ordinaires : 29 s pour « les murailles de Jéricho sont tombées »,
        # 56 s pour « le peuple de Dieu a mis du sang sur les linteaux des
        # portes ». Une barre de recherche qui répond à la frappe ne survit pas
        # à ça — et c'est exactement le genre de phrase qu'un régisseur tape.
        #
        # Les candidats arrivent déjà classés par recouvrement de mots rares :
        # ce qui n'est pas dans les premières centaines ne remontera pas.
        for doc_id in candidate_ids[:CANDIDATS_SCORES_MAX]:
            entry = self.entries[doc_id]
            next_entry = self._next_entry(entry)
            for version_id, normalized_text in entry["normalized"].items():
                score = self._score(normalized_query, query_words, normalized_text)
                end_verse = None
                method = "manual_exact" if score >= 0.999 else "manual_approx"
                matched_text = entry["texts"].get(version_id, "")

                # Un fragment peut commencer à la fin d'un verset et continuer
                # au suivant. On renvoie alors un passage paginé, pas un faux
                # verset unique.
                if score < 0.999 and next_entry and version_id in next_entry["normalized"]:
                    joined = f"{normalized_text} {next_entry['normalized'][version_id]}"
                    joined_score = self._score(normalized_query, query_words, joined)
                    if joined_score > score + 0.005:
                        score = joined_score
                        end_verse = int(next_entry["verse"])
                        method = "manual_cross_verse" if score >= 0.999 else "manual_approx"
                        matched_text = f"{matched_text} {next_entry['texts'].get(version_id, '')}".strip()

                # Une approximation manuelle doit partager suffisamment de
                # matière avec le texte. Les correspondances exactes courtes
                # restent acceptées ; les conversations ordinaires non.
                threshold = 0.98 if len(query_words) == 1 else 0.64
                if score < threshold:
                    continue

                hit_key = (doc_id, end_verse)
                previous = hits.get(hit_key)
                if previous and previous["score"] >= score:
                    continue
                hits[hit_key] = {
                    "book_abbr": entry["book_abbr"],
                    "chapter": entry["chapter"],
                    "verse": entry["verse"],
                    "verse_end": end_verse,
                    "score": round(min(1.0, score), 4),
                    "matched_version": version_id,
                    "matched_text": matched_text,
                    "detection_method": method,
                }

                # Un fragment exact ne peut pas être mieux classé dans une
                # autre traduction. On évite six comparaisons coûteuses.
                if score >= 0.999:
                    break

        return self._rank_hits(hits, top_k)
