"""Recherche par description : un mot rare doit l'emporter sur un cosinus plat.

Mesures d'origine (benchmarks/run_description_benchmark.py) : top 3 à 80 %
sur le jeu de réglage, 53 % sur le jeu de contrôle ; Exode 12:7 absent pour
« le peuple de Dieu a mis du sang sur les linteaux des portes ». Avec le bonus
de mots rares : 93 % et 80 %.

L'encodeur est remplacé par des vecteurs choisis : on teste le classement,
pas le modèle.
"""

import numpy as np

from app.services.manual_search import ManualVerseIndex
from app.services.recherche_description import ClasseurDescriptions

VERSETS = {
    ("Neh", 10, 21): "Meschézabeel, Tsadok, Jaddua,",
    ("Ex", 12, 7): "On prendra de son sang, et on en mettra sur les deux poteaux "
                   "et sur le linteau de la porte des maisons où on le mangera.",
    ("Lv", 9, 18): "Il égorgea le bœuf et le bélier ; les fils d'Aaron lui présentèrent "
                   "le sang, et il le répandit sur l'autel tout autour.",
    ("Ps", 24, 7): "Portes, élevez vos linteaux ; élevez-vous, portes éternelles !",
}
# Cosinus « plats », comme mesurés : la liste de noms arrive en tête.
COSINUS = {("Neh", 10, 21): 0.835, ("Lv", 9, 18): 0.820, ("Ps", 24, 7): 0.818, ("Ex", 12, 7): 0.812}


class _Semantique:
    """Index sémantique minimal : chaque verset reçoit exactement son cosinus."""

    def __init__(self):
        cles = list(VERSETS)
        self.initialized, self.encoder = True, object()
        self.entries = [
            {"reference": f"{b} {c}:{v}", "book_abbr": b.lower(), "chapter": c,
             "verse_start": v, "verse_end": None, "text": VERSETS[(b, c, v)]}
            for b, c, v in cles
        ]
        # Requête = e0 ; verset i = cos·e0 + sin·e_(i+1) → produit scalaire = cos.
        self.matrix = np.zeros((len(cles), len(cles) + 1), dtype=np.float32)
        for i, cle in enumerate(cles):
            self.matrix[i, 0] = COSINUS[cle]
            self.matrix[i, i + 1] = np.sqrt(1 - COSINUS[cle] ** 2)

    def _encode(self, textes, kind):
        vecteur = np.zeros(self.matrix.shape[1], dtype=np.float32)
        vecteur[0] = 1.0
        return [vecteur for _ in textes]


def _index():
    livres = {}
    for (b, c, v), texte in VERSETS.items():
        livres.setdefault(b, {}).setdefault(c, {})[v] = texte
    return ManualVerseIndex({"LSG": livres})


def test_un_mot_rare_depasse_une_liste_de_noms():
    classeur = ClasseurDescriptions(_Semantique(), _index())

    resultats = classeur.classer("le peuple de Dieu a mis du sang sur les linteaux des portes", 4)

    ordre = [r["reference"] for r in resultats]
    assert ordre.index("Ex 12:7") < ordre.index("Neh 10:21"), ordre
    assert ordre.index("Ps 24:7") < ordre.index("Neh 10:21"), ordre


def test_les_terminaisons_sont_tolerees():
    """« linteaux » dans la requête doit retrouver « linteau » dans le texte."""
    classeur = ClasseurDescriptions(_Semantique(), _index())

    racines = classeur._racines("les linteaux")

    documents = set().union(*(docs for _, docs in racines))
    entrees = classeur.index.entries
    assert {(entrees[d]["book_abbr"], entrees[d]["chapter"]) for d in documents} == {("Ex", 12), ("Ps", 24)}


def test_la_confiance_affichee_reste_le_cosinus():
    """Le bonus sert au tri ; il ne gonfle pas le pourcentage montré au régisseur."""
    classeur = ClasseurDescriptions(_Semantique(), _index())

    exode = next(r for r in classeur.classer("du sang sur les linteaux", 4) if r["reference"] == "Ex 12:7")

    assert exode["confidence"] == round(COSINUS[("Ex", 12, 7)], 4)
    assert exode["score"] > exode["confidence"]


def test_sans_mot_porteur_le_classement_reste_semantique():
    classeur = ClasseurDescriptions(_Semantique(), _index())

    ordre = [r["reference"] for r in classeur.classer("que dit la", 4)]

    assert ordre == ["Neh 10:21", "Lv 9:18", "Ps 24:7", "Ex 12:7"]
