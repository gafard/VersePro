"""Santé de la transcription — savoir quand se taire.

Ces seuils ne sortent pas d'une intuition : ils ont été mesurés sur trois
enregistrements réels, dont un culte charismatique où la musique tourne
pendant la prédication et où le parler en langues alterne avec le français.

    prédication au son propre   35 mots/segment    12 détections, ~10 justes
    culte avec musique de fond   4 mots/segment   144 détections, ~90 % fausses

Les tests protègent les deux bords : ne rien perdre quand le son est bon, se
taire quand il ne l'est pas.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.transcription_health import (
    MOTS_MIN_SEGMENT,
    SEGMENTS_MIN_POUR_JUGER,
    SanteTranscription,
)

PROPRE = ("et voilà ce qu'on y lit or le dieu de paix lui même vous sanctifie "
          "entièrement et que tout votre être esprit âme et corps soit conservé")
HACHE = "papa papa papa"


def _remplir(sante, texte, combien):
    for _ in range(combien):
        sante.noter(texte)


# ── Au démarrage, on laisse passer ───────────────────────────────────────────

def test_muet_au_depart_ne_bloque_rien():
    """Sur une statistique vide, mieux vaut écouter que se taire d'office."""
    assert SanteTranscription().est_fiable() is True


def test_un_seul_segment_court_ne_condamne_pas():
    """Une phrase brève isolée arrive dans n'importe quel culte."""
    sante = SanteTranscription()
    sante.noter(HACHE)
    assert sante.est_fiable() is True


# ── Le jugement, une fois assez de matière ───────────────────────────────────

def test_transcription_hachee_devient_non_fiable():
    sante = SanteTranscription()
    _remplir(sante, HACHE, SEGMENTS_MIN_POUR_JUGER + 2)
    assert sante.est_fiable() is False
    assert sante.etat()["message"], "le silence doit être expliqué à l'opérateur"


def test_transcription_fluide_reste_fiable():
    sante = SanteTranscription()
    _remplir(sante, PROPRE, 6)
    assert sante.est_fiable() is True
    assert sante.etat()["message"] == ""


def test_la_sante_se_retablit_quand_le_son_revient():
    """La musique s'arrête, le prédicateur reprend : il faut réécouter.

    Sans cette remontée, un passage de louange condamnerait tout le reste du
    culte au silence."""
    sante = SanteTranscription()
    _remplir(sante, HACHE, 10)
    assert sante.est_fiable() is False
    _remplir(sante, PROPRE, 10)
    assert sante.est_fiable() is True


def test_fenetre_glissante_oublie_le_passe():
    sante = SanteTranscription(fenetre=5)
    _remplir(sante, PROPRE, 20)
    assert sante.etat()["segments_observes"] == 5


def test_reinitialiser_efface_l_historique():
    """Nouveau culte, ou micro rouvert : l'historique ne vaut plus rien."""
    sante = SanteTranscription()
    _remplir(sante, HACHE, 10)
    assert sante.est_fiable() is False
    sante.reinitialiser()
    assert sante.est_fiable() is True


# ── Le segment isolé ─────────────────────────────────────────────────────────

def test_segment_trop_court_est_rejete():
    """« j'avais de l'eau » — 4 mots — faisait sortir Ézéchiel 47:4."""
    assert SanteTranscription.segment_exploitable("j'avais de l'eau") is False
    assert SanteTranscription.segment_exploitable("j'ai déjà été t'aider") is False
    assert SanteTranscription.segment_exploitable("") is False


def test_segment_assez_long_est_accepte():
    """Le seuil garde les vraies expositions : « ta capacité à venu de dieu »
    (6 mots) est la plus courte détection JUSTE observée sur du vrai audio."""
    assert SanteTranscription.segment_exploitable("ta capacité à venu de dieu") is True
    assert SanteTranscription.segment_exploitable(PROPRE) is True


def test_le_seuil_de_segment_reste_au_dessus_du_garde_fou_historique():
    """La cascade se contentait de 4 mots bruts — trop peu, et c'est mesuré."""
    assert MOTS_MIN_SEGMENT > 4
