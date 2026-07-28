"""Formes orales que le corpus de rejeu a révélées manquantes.

Deux tournures courantes en chaire n'étaient pas comprises, et le banc
historique — bâti sur des phrases écrites proprement — les ignorait :

  • « au psaume vingt-trois, PREMIER VERSET » : seule « verset un » passait ;
  • « JUDE verset vingt-quatre » : un livre à chapitre unique se cite sans
    chapitre, personne ne dit « Jude chapitre un verset vingt-quatre ».

Les garde-fous comptent autant que les corrections : un livre à plusieurs
chapitres ne doit JAMAIS se voir attribuer le chapitre 1 par défaut.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.verse_parser import VerseParserService

_parser = VerseParserService()


def _ref(texte: str):
    resultat = asyncio.run(_parser.parse(texte, skip_text_search=True))
    return resultat.get("reference") if resultat else None


# ── Ordinaux de rang : « premier verset » ────────────────────────────────────

def test_premier_verset():
    assert _ref("ouvrons le psaume vingt-trois premier verset") == "Psaumes 23:1"


def test_ordinal_avec_accent_ou_sans():
    assert _ref("psaume vingt-trois deuxieme verset") == "Psaumes 23:2"
    assert _ref("psaume vingt-trois deuxième verset") == "Psaumes 23:2"


def test_ordinal_eleve():
    assert _ref("Romains chapitre huit quinzième verset") == "Romains 8:15"


def test_un_livre_ordinal_reste_un_livre():
    """« première épître de Jean » ne doit pas devenir un rang de verset."""
    assert _ref("première épître de Jean chapitre quatre verset huit") == "1 Jean 4:8"


# ── Livres à chapitre unique ─────────────────────────────────────────────────

def test_jude_sans_chapitre():
    assert _ref("dans Jude verset vingt-quatre il est écrit") == "Jude 1:24"


def test_philemon_sans_chapitre():
    assert _ref("Philémon verset six") == "Philémon 1:6"


def test_livre_multi_chapitres_refuse_le_raccourci():
    """Le garde-fou : Jean a 21 chapitres, « Jean verset seize » reste ambigu.

    Sans cette borne, la commodité offerte à Jude inventerait un chapitre 1
    pour tout le reste de la Bible — et projetterait un verset faux."""
    assert _ref("Jean verset seize") is None
    assert _ref("Romains verset vingt-huit") is None
    assert _ref("Psaumes verset vingt-trois") is None


# ── Ce qui doit continuer de ne RIEN déclencher ──────────────────────────────

def test_les_pieges_du_corpus_restent_muets():
    """Un faux positif devant l'assemblée coûte plus cher qu'un manque."""
    for phrase in (
        "mon frère Jean va nous conduire dans la prière",
        "reprenons tous ensemble le cantique numéro cent vingt-huit",
        "le rendez-vous est fixé au trois du mois à seize heures",
        "nos frères de Corinthe nous ont envoyé un message",
    ):
        assert _ref(phrase) is None, f"faux positif sur : {phrase}"
