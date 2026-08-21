"""Trouver un verset qu'on ne sait que DÉCRIRE.

LE CAS QUI DÉCIDE DE LA VALEUR DU PRODUIT. Un opérateur ProPresenter à qui
l'on dit « le peuple de Dieu a mis du sang sur les linteaux des portes »
tape la phrase dans Google, trouve Exode 12, recopie le verset : quinze
secondes. VersePro ne trouvait rien du tout — donc perdait la comparaison
face à une méthode manuelle.

CE QUI L'EN EMPÊCHAIT, MESURÉ :

    « sang sur les linteaux des portes »            -> Exode 12:7
    « a mis du sang sur les linteaux des portes »   -> RIEN
    « le peuple de dieu a mis du sang sur … »       -> RIEN

Plus la phrase portait d'information, moins elle trouvait — l'inverse du
comportement attendu. Trois causes empilées :

  1. la sélection des candidats exigeait que TOUS les mots coexistent dans un
     même verset, ce qu'une phrase naturelle ne fait jamais ;
  2. le score exigeait que la MOITIÉ des mots figurent dans le verset, alors
     que « linteau » seul suffit à désigner Exode 12 dans toute la Bible ;
  3. l'index tenait « linteaux » et « linteau » pour deux mots étrangers.

Ces tests protègent les trois, et le refus du bruit qui va avec : une
recherche qui répond à tout ne vaut pas mieux qu'une qui ne répond à rien.
"""

import pytest

from app.services.verse_parser import VerseParserService


@pytest.fixture(scope="module")
def loader():
    return VerseParserService().bible_loader


@pytest.mark.parametrize(
    ("description", "attendu"),
    [
        ("le peuple de dieu a mis du sang sur les linteaux des portes", "Exode 12"),
        ("a mis du sang sur les linteaux des portes", "Exode 12"),
        ("david a tue goliath avec une fronde", "1 Samuel 17"),
        ("daniel dans la fosse aux lions", "Daniel 6"),
    ],
)
def test_une_description_grossiere_trouve_le_passage(loader, description, attendu):
    resultats = loader.search_manual_candidates(description, 5)
    assert resultats, f"aucun résultat pour {description!r}"
    livres = {r["reference"].rsplit(":", 1)[0] for r in resultats[:5]}
    assert attendu in livres, (description, [r["reference"] for r in resultats[:5]])


def test_plus_de_contexte_ne_doit_jamais_nuire(loader):
    """Le symptôme d'origine : la phrase longue rendait moins que la courte."""
    court = loader.search_manual_candidates("sang sur les linteaux des portes", 5)
    long = loader.search_manual_candidates(
        "le peuple de dieu a mis du sang sur les linteaux des portes", 5)
    assert court and long, "une des deux formulations ne rend rien"
    assert any(r["reference"].startswith("Exode 12") for r in long), (
        "ajouter du contexte a fait perdre le passage"
    )


def test_le_pluriel_rejoint_le_singulier(loader):
    """Le verset dit « linteau », l'opérateur écrit « linteaux ».

    Le repli est vérifié à la source ET sur une phrase complète. Sur deux ou
    trois mots seulement, un autre passage peut légitimement l'emporter : avec
    huit traductions installées, l'une d'elles contient « linteaux » au pluriel
    littéral et coiffe la LSG. Ce n'est pas un défaut — c'est ce que fait un
    index multilingue — mais ça ne se teste pas sur un fragment nu.
    """
    from app.services.manual_search import radical

    assert radical("linteaux") == "linteau"
    assert radical("portes") == "porte"
    assert radical("fils") == "fils", "les mots courts restent intacts"

    resultats = loader.search_manual_candidates(
        "on a mis du sang sur les linteaux des portes des maisons", 5)
    assert any(r["reference"].startswith("Exode 12") for r in resultats), (
        [r["reference"] for r in resultats]
    )


@pytest.mark.parametrize("bruit", [
    "reunion planning projecteur cable hdmi",
    "le cafe est pret dans la salle apres la repetition",
    "il reste trois bouteilles d eau sur la table",
])
def test_une_conversation_de_regie_ne_donne_aucun_verset(loader, bruit):
    """Une recherche qui répond à tout ne vaut pas mieux qu'une muette."""
    assert loader.search_manual_candidates(bruit, 5) == [], bruit
