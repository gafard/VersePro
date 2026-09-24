"""Recherche par description : « le sang sur les linteaux des portes ».

LE SÉMANTIQUE SEUL NE DÉPARTAGE PAS LES RÉCITS.

Mesuré sur benchmarks/description_cases.json : pour une description, les
scores cosinus des huit premiers versets tiennent entre 0,81 et 0,84. L'écart
entre le bon verset et un verset quelconque est plus petit que le bruit de
l'encodeur. Exode 12:7 n'apparaissait pas dans le top 8 de « le peuple de Dieu
a mis du sang sur les linteaux des portes », battu par Hébreux 13:12 et
Lévitique 9:18 — et des listes de noms (Néhémie 10:21, 1 Chroniques 11:47)
remontaient pour presque n'importe quelle requête.

Or le régisseur tape presque toujours UN mot qui désigne le récit : linteaux,
Goliath, Babel, sycomore. « linteaux » figure dans trois versets de toute la
Bible. Ce mot seul vaut plus que toute la similarité vectorielle.

Le classement ajoute donc au cosinus un bonus de mots rares : la part de
l'information de la requête (IDF, toutes traductions confondues) que le
verset contient. « Dieu » ou « peuple » ne pèsent presque rien ; « linteaux »
pèse lourd. Les terminaisons sont tolérées (linteau/linteaux,
marché/marchait), parce qu'une description ne conjugue jamais comme le texte.
Tous les versets sont candidats : un verset absent du top sémantique peut
remonter grâce à ses mots.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

import numpy as np

from .manual_search import MOTS_OUTILS, normalize_fragment

# Poids du bonus de mots rares face au cosinus (réglé sur
# benchmarks/description_cases.json, vérifié sur description_cases_controle.json).
POIDS_MOTS_RARES = 0.05

# Une racine présente dans plus de 5 % des versets ne désigne aucun récit.
PART_RACINE_BANALE = 0.05


def _racine(mot: str) -> str:
    """Préfixe assez long pour garder le sens, assez court pour la conjugaison."""
    return mot if len(mot) <= 4 else mot[: max(4, len(mot) - 2)]


class ClasseurDescriptions:
    """Cosinus e5 + bonus IDF des mots rares, sur tous les versets."""

    def __init__(self, semantique: Any, index_manuel: Any):
        self.semantique = semantique
        self.index = index_manuel
        self._cle_cache: Optional[tuple] = None
        self._doc_vers_rangee: Optional[np.ndarray] = None

    def _correspondance(self) -> np.ndarray:
        """doc_id de l'index manuel -> rangée de la matrice sémantique (-1 si absent)."""
        cle = (id(self.index), len(self.index.entries), id(self.semantique.entries))
        if self._cle_cache != cle:
            rangees = {
                (str(e.get("book_abbr") or "").casefold(), int(e.get("chapter") or 0),
                 int(e.get("verse_start") or 0)): i
                for i, e in enumerate(self.semantique.entries)
            }
            table = np.full(len(self.index.entries), -1, dtype=np.int64)
            for doc_id, entree in enumerate(self.index.entries):
                table[doc_id] = rangees.get(
                    (str(entree["book_abbr"]).casefold(), int(entree["chapter"]), int(entree["verse"])),
                    -1,
                )
            self._doc_vers_rangee, self._cle_cache = table, cle
        return self._doc_vers_rangee

    def _racines(self, requete: str) -> List[tuple]:
        """(idf, doc_ids) pour chaque mot porteur connu de la requête."""
        total = max(1, len(self.index.entries))
        # Plancher de 50 : sans effet sur la Bible (5 % = 1 555 versets), il
        # évite qu'un petit corpus déclare banal le moindre mot.
        plafond = max(50, total * PART_RACINE_BANALE)
        vues, resultat = set(), []
        for mot in normalize_fragment(requete).split():
            if len(mot) < 3 or mot in MOTS_OUTILS:
                continue
            racine = _racine(mot)
            if racine in vues:
                continue
            vues.add(racine)
            voisins = [
                m for m in self.index._words_by_prefix.get(racine[:3], ())
                if m.startswith(racine)
            ]
            if mot in self.index._postings and mot not in voisins:
                voisins.append(mot)
            docs = set()
            for voisin in voisins:
                docs.update(self.index._postings[voisin])
            if not docs or len(docs) > plafond:
                continue
            resultat.append((math.log(total / len(docs)), docs))
        return resultat

    def classer(self, requete: str, top_k: int = 12) -> List[Dict[str, Any]]:
        sem = self.semantique
        if not sem.initialized or sem.encoder is None or len(requete.split()) < 2:
            return []
        cosinus = sem.matrix @ sem._encode([requete], kind="query")[0]

        bonus = np.zeros(len(cosinus), dtype=np.float32)
        racines = self._racines(requete)
        information = sum(idf for idf, _ in racines)
        if information:
            table = self._correspondance()
            for idf, docs in racines:
                rangees = table[np.fromiter(docs, dtype=np.int64)]
                rangees = np.unique(rangees[rangees >= 0])
                bonus[rangees] += idf / information

        final = cosinus + POIDS_MOTS_RARES * bonus
        nombre = max(1, min(int(top_k), len(final)))
        meilleurs = np.argpartition(final, -nombre)[-nombre:]
        meilleurs = meilleurs[np.argsort(final[meilleurs])[::-1]]
        return [{
            **sem.entries[int(i)],
            # Le tri de la route se fait sur « score » ; la confiance affichée
            # reste le cosinus, sans bonus, pour ne pas promettre plus qu'il n'y a.
            "score": round(float(final[i]), 4),
            "confidence": round(float(cosinus[i]), 4),
            "detection_method": "manual_semantic",
            "requires_review": True,
        } for i in meilleurs]


_classeur: Optional[ClasseurDescriptions] = None


def classeur_pour(semantique: Any, index_manuel: Any) -> ClasseurDescriptions:
    """Un classeur partagé : sa table de correspondance coûte ~30 ms à bâtir."""
    global _classeur
    if _classeur is None or _classeur.semantique is not semantique or _classeur.index is not index_manuel:
        _classeur = ClasseurDescriptions(semantique, index_manuel)
    return _classeur
