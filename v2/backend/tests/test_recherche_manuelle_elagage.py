"""L'élagage de la recherche manuelle doit être exact, pas approximatif.

La fenêtre glissante de `_best_window_ratio` coûtait 2 s sur une description
ordinaire (« le peuple de dieu a mis du sang sur les linteaux des portes »)
et 14 s sur « que dit la parole ». Elle écarte désormais, sans les calculer,
les fenêtres qui ne peuvent ni battre le meilleur score ni atteindre le
plancher utile.

Ces bornes sont des majorants mathématiques (real_quick_ratio ≥ quick_ratio
≥ ratio). Si l'une d'elles était mal employée, la recherche deviendrait plus
rapide ET silencieusement moins bonne. Ce fichier compare donc l'algorithme
élagué à l'algorithme d'origine, recopié ici tel quel, sur des paires réelles
tirées de la Bible, fautes de frappe comprises.
"""

import random
from difflib import SequenceMatcher

import pytest

from app.services import manual_search
from app.services.manual_search import (
    SOUS_LE_PLANCHER,
    ManualVerseIndex,
    _best_window_ratio,
    normalize_fragment,
)
from app.services.verse_parser import BibleLoader


def _reference(query, query_size, text_words):
    """L'algorithme d'avant l'élagage, sans aucune optimisation."""
    if not query or not text_words:
        return 0.0
    best = 0.0
    for size in range(max(1, query_size - 1), min(len(text_words), query_size + 2) + 1):
        for start in range(0, len(text_words) - size + 1):
            ratio = SequenceMatcher(None, query, " ".join(text_words[start:start + size])).ratio()
            if ratio > best:
                best = ratio
                if best >= 0.995:
                    return best
    return best


def _abimer(mots, hasard):
    """Une faute de frappe ou d'ASR sur un mot sur trois."""
    sortie = []
    for mot in mots:
        if len(mot) > 3 and hasard.random() < 0.33:
            i = hasard.randrange(len(mot))
            mot = mot[:i] + mot[i + 1:]
        sortie.append(mot)
    return sortie


@pytest.fixture(scope="module")
def paires():
    lsg = BibleLoader().versions.get("LSG")
    if not lsg:
        pytest.skip("Bible LSG absente")
    versets = [
        normalize_fragment(texte)
        for chapitres in lsg.values()
        for versets_ in chapitres.values()
        for texte in versets_.values()
        if texte
    ]
    hasard = random.Random(20260924)
    resultat = []
    for _ in range(250):
        source = hasard.choice(versets).split()
        cible = hasard.choice(versets).split()
        taille = hasard.randint(2, min(8, len(source)))
        debut = hasard.randrange(len(source) - taille + 1)
        requete = _abimer(source[debut:debut + taille], hasard)
        # Une fois sur deux, la cible contient réellement le fragment.
        if hasard.random() < 0.5:
            cible = source
        resultat.append((" ".join(requete), len(requete), cible))
    return resultat


def test_sans_plancher_le_score_est_identique(paires):
    for requete, taille, mots in paires:
        assert _best_window_ratio(requete, taille, mots) == _reference(requete, taille, mots), requete


@pytest.mark.parametrize("plancher", [0.3, 0.55, 0.72, 0.9])
def test_avec_plancher_le_score_utile_est_identique(paires, plancher):
    """Au-dessus du plancher : la valeur exacte. En dessous : le signal, jamais un faux score."""
    for requete, taille, mots in paires:
        attendu = _reference(requete, taille, mots)
        obtenu = _best_window_ratio(requete, taille, mots, plancher)
        if attendu >= plancher:
            assert obtenu == attendu, requete
        else:
            assert obtenu == SOUS_LE_PLANCHER, requete


def test_l_elagage_evite_l_essentiel_des_calculs(paires, monkeypatch):
    """Garde-fou de performance, déterministe : on compte, on ne chronomètre pas."""
    appels = {"ratio": 0}
    origine = SequenceMatcher.ratio

    def compter(self):
        appels["ratio"] += 1
        return origine(self)

    monkeypatch.setattr(manual_search.SequenceMatcher, "ratio", compter)
    fenetres = 0
    for requete, taille, mots in paires:
        fenetres += sum(
            max(0, len(mots) - size + 1)
            for size in range(max(1, taille - 1), min(len(mots), taille + 2) + 1)
        )
        _best_window_ratio(requete, taille, mots, 0.55)

    # Mesuré sur ces 250 paires : 89 % des fenêtres passaient par ratio()
    # sans élagage, 38 % avec.
    assert appels["ratio"] < fenetres * 0.5, (appels["ratio"], fenetres)


def test_le_passage_sur_deux_versets_reste_trouve():
    """Le plancher du verset seul (seuil − 0,005) ne doit pas masquer un passage."""
    index = ManualVerseIndex({"LSG": {"Jn": {3: {
        16: "Car Dieu a tant aimé le monde qu'il a donné son Fils unique, afin que "
            "quiconque croit en lui ne périsse point, mais qu'il ait la vie éternelle.",
        17: "Dieu, en effet, n'a pas envoyé son Fils dans le monde pour qu'il juge "
            "le monde, mais pour que le monde soit sauvé par lui.",
    }}}})

    # Faute de frappe : aucune correspondance exacte, passe 2 obligatoire.
    resultats = index.search("vie eternele Dieu en effet", top_k=3)

    assert resultats and resultats[0]["verse"] == 16 and resultats[0]["verse_end"] == 17
