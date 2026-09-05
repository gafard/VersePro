"""
Traqueur de lecture — aligne la parole du prédicateur sur le verset projeté.

C'est le moteur de la « Lecture vivante » : pendant que le prédicateur lit,
la position de lecture avance mot à mot dans le verset affiché, et l'écran
de projection illumine le texte au rythme de la voix. Aucun concurrent ne
peut le faire : eux projettent des diapositives, VersePro écoute.

L'alignement est tolérant aux réalités du direct :
- erreurs ASR (« bergé » ≈ « berger ») via correspondance de préfixes ;
- mots sautés ou reformulés (fenêtre d'avance de 3 mots) ;
- transcriptions partielles répétées (l'appelant ne transmet que les mots nouveaux).
"""

import re
import unicodedata
from typing import List


def _norm_token(token: str) -> str:
    """Normalise UN token affiché : minuscules, sans accents, sans ponctuation.
    « L'Éternel » -> « leternel » (l'apostrophe est fusionnée, pas coupée),
    pour rester aligné 1:1 avec les mots affichés à l'écran."""
    token = token.lower()
    token = "".join(c for c in unicodedata.normalize("NFD", token) if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]", "", token)


def _verse_tokens(text: str) -> List[str]:
    """Tokens du verset, EXACTEMENT au même découpage que l'affichage (split espaces).
    Un token de pure ponctuation devient une chaîne vide (traversé par la fenêtre d'avance)."""
    return [_norm_token(t) for t in (text or "").split()]


def _spoken_tokens(text: str) -> List[str]:
    """Tokens prononcés. Les lettres isolées de l'ASR (« l eternel ») sont
    fusionnées avec le mot suivant pour matcher la forme affichée (« leternel »)."""
    raw = [_norm_token(t) for t in (text or "").split()]
    merged: List[str] = []
    for token in raw:
        if not token:
            continue
        if merged and len(merged[-1]) == 1:
            merged[-1] = merged[-1] + token
        else:
            merged.append(token)
    return merged


def _words_match(spoken: str, verse: str) -> bool:
    if spoken == verse:
        return True
    # Tolérance ASR : mêmes 4 premières lettres sur les mots assez longs
    if len(spoken) >= 4 and len(verse) >= 4 and spoken[:4] == verse[:4]:
        return True
    return False


class ReadingTracker:
    """Position de lecture dans le verset couramment projeté."""

    # Fenêtre d'avance : autorise jusqu'à 2 mots du verset sautés/reformulés
    LOOKAHEAD = 3
    # Les mots-outils très courts ne font pas foi (trop fréquents dans la parole libre)
    MIN_ANCHOR_LEN = 3

    def __init__(self):
        self.words: List[str] = []
        self.position = 0

    @property
    def active(self) -> bool:
        return len(self.words) > 0

    @property
    def total(self) -> int:
        return len(self.words)

    @property
    def completed(self) -> bool:
        return self.active and self.position >= len(self.words)

    def set_verse(self, text: str):
        """Nouveau verset projeté : repart de zéro."""
        self.words = _verse_tokens(text)
        self.position = 0

    def clear(self):
        self.words = []
        self.position = 0

    def feed(self, new_spoken_text: str) -> bool:
        """
        Consomme les NOUVEAUX mots prononcés et avance la position de lecture.
        Retourne True si la position a progressé.

        Garde-fou : la position n'avance que sur des mots-ancres (≥ 3 lettres)
        retrouvés dans la fenêtre d'avance — une parole libre sans rapport
        avec le verset ne fait pas défiler le surlignage.
        """
        if not self.active or self.position >= len(self.words):
            return False

        moved = False
        for spoken in _spoken_tokens(new_spoken_text):
            if len(spoken) < self.MIN_ANCHOR_LEN:
                # Mot trop court pour servir d'ancre, mais s'il correspond
                # exactement au mot attendu, on le consomme (fluidité).
                if self.position < len(self.words) and spoken == self.words[self.position]:
                    self.position += 1
                    moved = True
                continue

            window = self.words[self.position:self.position + self.LOOKAHEAD]
            for offset, verse_word in enumerate(window):
                if _words_match(spoken, verse_word):
                    self.position += offset + 1
                    moved = True
                    break

        return moved
