"""VerseGraph — relie ce qui est dit au passage qui vient d'être ouvert.

Le problème, mesuré avant d'écrire une ligne : quand un prédicateur fait
allusion à un récit sans le citer (« tant qu'il tenait les bras levés… »),
la recherche sémantique globale échoue. Exode 17:11 n'apparaît même pas dans
les 60 premiers résultats sur 31 102 versets — noyé par des versets qui
partagent des mots mais pas l'histoire.

Trois pistes ont été essayées et mesurées :

  • réordonner sur la corroboration lexicale du voisinage  → échec ;
  • réordonner sur le voisinage dans l'espace des vecteurs → échec ;
  • restreindre la recherche au chapitre ouvert            → 8 cas sur 8.

La raison de l'échec des deux premières est la même, et elle est structurelle :
sur le modèle e5, une bonne allusion et une phrase de culte quelconque sont
séparées par moins de 0,01 de similarité cosinus. Aucune pondération ne
survit à une marge pareille. Restreindre l'espace, si.

D'où cette règle : VerseGraph ne se déclenche QUE lorsqu'une référence
explicite a été confirmée peu avant. C'est cette confirmation — humaine et
vérifiable — qui autorise la suite. Sans ancre, le service se tait.

    « ouvrons Exode chapitre 17 »        → ancre posée (étage A, explicite)
    « tant qu'il tenait les bras levés » → Exode 17:11 proposé

Deux verrous décident, et ils sont indépendants :

  • le SCORE du meilleur verset du chapitre (≥ ANCRE_SCORE_MIN) ;
  • l'ÉCART entre le premier et le deuxième (≥ ANCRE_ECART_MIN).

Une allusion à un verset précis fait un pic ; une phrase générique prononcée
pendant que le chapitre est ouvert fait un plateau. Sur 16 cas mesurés,
chacun des deux verrous arrête un piège que l'autre laisserait passer.

Enfin, VerseGraph ne projette JAMAIS. Ses résultats portent
`requires_review = True` et une méthode qui n'est pas « explicit » : la
cascade les envoie au panneau de l'opérateur, jamais à l'écran. Une
proposition fausse coûte une ligne ignorée, pas un verset faux devant
l'assemblée. C'est ce qui rend l'étage acceptable malgré sa marge étroite.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# Durée de validité d'une ancre. Une prédication expositive reste dans son
# passage un long moment ; au-delà, mieux vaut se taire que de proposer des
# versets d'un chapitre que l'orateur a quitté.
ANCRE_DUREE_S = 600.0

# Les deux verrous. Calibrés sur 16 cas ancrés (8 allusions justes, 8 phrases
# de culte pièges) : justes = score 0,819 à 0,904 et écart 0,015 à 0,083 ;
# pièges = score ≤ 0,815 et écart ≤ 0,034, jamais les deux à la fois.
# L'échantillon est petit — le corpus de rejeu est là pour l'agrandir, et ces
# deux constantes sont les premières à revoir quand il aura grossi.
ANCRE_SCORE_MIN = 0.81
ANCRE_ECART_MIN = 0.012

# En dessous, la phrase est trop courte pour porter une allusion : « il est
# fidèle » ne désigne aucun verset en particulier, même chapitre ouvert.
ANCRE_MOTS_MIN = 5


class VerseGraphService:
    """Recherche restreinte au passage ouvert. Ne projette jamais."""

    def __init__(self, semantic_service: Any, duree_s: float = ANCRE_DUREE_S):
        self.semantic = semantic_service
        self.duree_s = duree_s
        self._ancre: Optional[Tuple[str, int]] = None
        self._ancre_libelle: str = ""
        self._ancre_pose_a: float = 0.0
        self._index: Optional[Dict[Tuple[str, int], List[int]]] = None
        self._index_taille: int = -1

    # ── Ancre ────────────────────────────────────────────────────────────────

    def ancrer(self, reference: Optional[Dict[str, Any]]) -> bool:
        """Retient le chapitre d'une référence explicite confirmée.

        Renvoie True si une ancre a été posée. Refuse tout ce qui n'est pas
        une citation explicite : c'est la confirmation par l'étage A qui donne
        à VerseGraph le droit de parler ensuite.
        """
        if not reference or reference.get("detection_method") != "explicit":
            return False
        livre = reference.get("book_abbr")
        chapitre = reference.get("chapter")
        if not livre or not chapitre:
            return False
        # On joint sur le NOM du livre, pas sur l'abréviation : le parseur et
        # l'index sémantique utilisent deux nomenclatures différentes
        # (« Ex »/« ex », « Gn »/« gen »). Le nom complet, lui, est le même
        # des deux côtés puisqu'il vient de la même Bible chargée.
        libelle = str(reference.get("reference") or "").rsplit(":", 1)[0]
        nom_livre = libelle.rsplit(" ", 1)[0] if " " in libelle else ""
        if not nom_livre:
            return False
        self._ancre = (nom_livre, int(chapitre))
        self._ancre_libelle = libelle
        self._ancre_pose_a = time.monotonic()
        return True

    def oublier(self) -> None:
        """Le culte est fini, ou l'opérateur a repris la main."""
        self._ancre = None
        self._ancre_libelle = ""
        self._ancre_pose_a = 0.0

    def _ancre_valide(self) -> Optional[Tuple[str, int]]:
        if not self._ancre:
            return None
        if time.monotonic() - self._ancre_pose_a > self.duree_s:
            return None
        return self._ancre

    # ── Index par chapitre ───────────────────────────────────────────────────

    def _chapitres(self) -> Dict[Tuple[str, int], List[int]]:
        """Carte chapitre → lignes de la matrice, reconstruite si l'index change.

        La taille de l'index sert de signature : un changement de version
        biblique la modifie, ce qui invalide la carte sans avoir à câbler un
        signal entre les deux services.
        """
        entrees = getattr(self.semantic, "entries", []) or []
        if self._index is None or self._index_taille != len(entrees):
            carte: Dict[Tuple[str, int], List[int]] = {}
            for i, e in enumerate(entrees):
                # « 1 Samuel 17:40 » → (« 1 Samuel », 17). Passer par la
                # référence affichée évite de dépendre de l'abréviation
                # interne de l'index, qui n'est pas celle du parseur.
                ref = str(e.get("reference") or "")
                tete = ref.rsplit(":", 1)[0]
                chap = e.get("chapter")
                if " " in tete and chap:
                    carte.setdefault((tete.rsplit(" ", 1)[0], int(chap)), []).append(i)
            self._index = carte
            self._index_taille = len(entrees)
        return self._index

    # ── Résolution ───────────────────────────────────────────────────────────

    def resoudre(self, texte: str) -> Optional[Dict[str, Any]]:
        """Cherche l'allusion dans le seul chapitre ancré. None si rien de sûr."""
        ancre = self._ancre_valide()
        if not ancre or not texte or len(texte.split()) < ANCRE_MOTS_MIN:
            return None
        if not getattr(self.semantic, "initialized", False):
            return None

        lignes = self._chapitres().get(ancre)
        # Un chapitre d'un seul verset ne permet aucun écart : le deuxième
        # score n'existe pas, donc le verrou d'écart ne peut pas juger.
        if not lignes or len(lignes) < 2:
            return None

        try:
            vecteur = self.semantic._encode([texte], kind="query")[0]
            scores = self.semantic.matrix[lignes] @ vecteur
        except Exception as exc:  # pragma: no cover - dépend de l'encodeur
            logger.debug("VerseGraph : encodage impossible (%s)", exc)
            return None

        ordre = np.argsort(scores)[::-1]
        meilleur = float(scores[ordre[0]])
        ecart = meilleur - float(scores[ordre[1]])
        if meilleur < ANCRE_SCORE_MIN or ecart < ANCRE_ECART_MIN:
            return None

        entree = self.semantic.entries[lignes[int(ordre[0])]]
        return {
            **entree,
            "score": round(meilleur, 4),
            "confidence": round(meilleur, 4),
            "detection_method": "semantic_anchored",
            # Verrou explicite, en plus de celui de la cascade : cet étage ne
            # doit jamais pouvoir projeter, quelle que soit la confiance.
            "requires_review": True,
            "projection_policy": "manual_review",
            "verse_graph": {
                "ancre": self._ancre_libelle,
                "ecart": round(ecart, 4),
                "depuis_s": round(time.monotonic() - self._ancre_pose_a, 1),
                # De quoi expliquer la proposition à l'opérateur : « dans
                # Exode 17, ouvert il y a 4 min ».
                "raison": f"allusion à {self._ancre_libelle}, ouvert plus tôt",
            },
        }

    def etat(self) -> Dict[str, Any]:
        ancre = self._ancre_valide()
        return {
            "ancre": self._ancre_libelle if ancre else None,
            "depuis_s": round(time.monotonic() - self._ancre_pose_a, 1) if ancre else None,
            "duree_s": self.duree_s,
        }
