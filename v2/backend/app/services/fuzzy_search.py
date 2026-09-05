"""
Recherche floue locale de versets — sans réseau, sans modèle externe.

Principe : chaque verset est projeté dans un vecteur de dimension fixe par
hachage signé de ses traits lexicaux (mots significatifs + tri-grammes de
caractères). Les tri-grammes rendent la mesure robuste aux erreurs de
transcription vocale (« berger » ≈ « bergé ») ; les mots, pondérés par leur
rareté dans le corpus (IDF), portent le sens — « racheté » pèse plus que
« monde ». La similarité cosinus sur la matrice pré-calculée répond en
quelques millisecondes sur ~31 000 versets.

Ce n'est pas un modèle sémantique neuronal : il retrouve les citations
approximatives et partielles, pas les pures paraphrases (celles-ci restent
du ressort de l'agent IA). Toute détection passe en validation manuelle.
"""

import math
import re
import unicodedata
import zlib
from collections import Counter
from typing import Dict, Any, List, Tuple

import numpy as np
from loguru import logger

DIM = 512
TRIGRAM_WEIGHT = 0.6

# Mots-outils français exclus des traits lexicaux (gardés dans les tri-grammes)
STOP_WORDS = {
    "il", "y", "a", "de", "le", "la", "les", "car", "je", "tu", "vous", "nous",
    "est", "un", "une", "dans", "en", "pour", "ce", "ces", "cette", "mon", "ma",
    "mes", "ton", "ta", "tes", "son", "sa", "ses", "et", "ou", "mais", "donc",
    "or", "ni", "que", "qui", "quoi", "ne", "pas", "plus", "tout", "tous",
    "comme", "avec", "sur", "par", "aux", "au", "des", "du", "lui", "leur",
    "leurs", "moi", "toi", "se", "on", "ils", "elles", "l", "d", "c", "s", "n",
    "j", "m", "t", "qu",
}


def _normalize(text: str) -> str:
    text = text.lower()
    text = "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return " ".join(text.split())


def _significant_words(text: str) -> List[str]:
    return [w for w in _normalize(text).split() if w not in STOP_WORDS and len(w) >= 3]


def _hash_feature(feature: str) -> Tuple[int, float]:
    h = zlib.crc32(feature.encode("utf-8"))
    return h % DIM, (1.0 if (h >> 16) & 1 else -1.0)


class FuzzyVerseIndex:
    """Index vectoriel en mémoire d'une version de la Bible, pondéré par IDF."""

    def __init__(self, version: Dict[str, Dict[int, Dict[int, str]]]):
        raw: List[Tuple[str, int, int, str]] = []
        for book_abbr, chapters in version.items():
            if not book_abbr:
                continue  # livre sans abréviation mappée : référence inutilisable
            for ch_num, verses in chapters.items():
                for v_num, text in verses.items():
                    if text and len(text) >= 15:
                        raw.append((book_abbr, ch_num, v_num, text))

        # Passe 1 : fréquence documentaire des mots (pour l'IDF)
        df = Counter()
        for _, _, _, text in raw:
            df.update(set(_significant_words(text)))
        n_docs = max(1, len(raw))
        self._idf = {w: math.log((n_docs + 1) / (count + 1)) for w, count in df.items()}
        self._max_idf = math.log(n_docs + 1)

        # Passe 2 : vectorisation
        self.entries: List[Tuple[str, int, int, str]] = []
        vectors: List[np.ndarray] = []
        for book_abbr, ch, v, text in raw:
            vec = self._vectorize(text)
            if vec is not None:
                self.entries.append((book_abbr, ch, v, text))
                vectors.append(vec)

        self.matrix = np.stack(vectors) if vectors else np.zeros((0, DIM), dtype=np.float32)
        logger.info(f"🔎 Index flou local prêt : {len(self.entries)} versets, {self.matrix.nbytes / 1e6:.0f} Mo")

    def _word_weight(self, word: str) -> float:
        # IDF adouci (racine carrée) : les mots rares comptent plus, sans écraser
        # le reste ni laisser un mot absent du verset dominer la requête.
        idf = self._idf.get(word, self._max_idf * 0.6)
        return 1.0 + math.sqrt(max(0.0, idf))

    def _vectorize(self, text: str) -> np.ndarray | None:
        norm = _normalize(text)
        words = norm.split()
        if not words:
            return None

        vec = np.zeros(DIM, dtype=np.float32)
        for w in words:
            if w not in STOP_WORDS and len(w) >= 3:
                idx, sign = _hash_feature(f"w:{w}")
                vec[idx] += sign * self._word_weight(w)
            padded = f"^{w}$"
            for i in range(len(padded) - 2):
                idx, sign = _hash_feature(f"g:{padded[i:i + 3]}")
                vec[idx] += sign * TRIGRAM_WEIGHT

        length = np.linalg.norm(vec)
        if length == 0:
            return None
        return vec / length

    def search(self, query: str, top_k: int = 3, min_score: float = 0.55) -> List[Dict[str, Any]]:
        """Renvoie les meilleurs versets [{book_abbr, chapter, verse, text, score}]"""
        if self.matrix.shape[0] == 0:
            return []
        # Trop court = trop ambigu : on exige au moins 4 mots significatifs
        if len(_significant_words(query)) < 4:
            return []

        q = self._vectorize(query)
        if q is None:
            return []

        scores = self.matrix @ q
        order = np.argsort(scores)[::-1][:top_k]
        results = []
        for idx in order:
            score = float(scores[idx])
            if score < min_score:
                break
            book_abbr, ch, v, text = self.entries[idx]
            results.append({
                "book_abbr": book_abbr,
                "chapter": ch,
                "verse": v,
                "text": text,
                "score": round(score, 3),
            })
        return results
