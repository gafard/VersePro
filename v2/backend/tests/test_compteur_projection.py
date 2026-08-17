"""« 50 versets projetés sur 50 détectés » n'était pas une mesure.

`detected_verses.sent_to_propresenter` était déclarée DEFAULT TRUE et AUCUN
code ne l'écrivait jamais. L'écran Historique compte pourtant cette colonne
pour afficher « PROJECTED VERSES » : il rendait donc toujours le total des
lignes. Sur la session du 11 août, 55 lignes portaient toutes l'indicateur à
1 et `validated_manually` à 0 — sans qu'aucun de ces deux chiffres ne
corresponde à quoi que ce soit.

Un rapport de fin de culte remis à un pasteur doit distinguer « VersePro a
reconnu ce verset » de « l'assemblée l'a lu ». C'est ce que ces tests
protègent.
"""

import asyncio

from app.services.database import DatabaseService


VERSET = {
    "reference": "Jean 3:16",
    "book": "Jean",
    "book_abbr": "Jn",
    "chapter": 3,
    "verse_start": 16,
    "text": "Car Dieu a tant aimé le monde…",
    "version": "LSG",
}


def _base(tmp_path):
    service = DatabaseService(str(tmp_path / "essai.db"))
    asyncio.run(service.connect())
    return service


def test_une_detection_n_est_pas_une_projection(tmp_path):
    db = _base(tmp_path)
    asyncio.run(db.add_detected_verse(VERSET, session_id=1))

    lignes = asyncio.run(db.get_recent_verses(limit=10))
    assert len(lignes) == 1
    assert not lignes[0]["sent_to_propresenter"], (
        "un verset détecté et jamais projeté ne doit pas compter comme projeté"
    )
    asyncio.run(db.disconnect())


def test_la_projection_est_enregistree(tmp_path):
    db = _base(tmp_path)
    asyncio.run(db.add_detected_verse(VERSET, session_id=1))

    assert asyncio.run(db.marquer_projete("Jean 3:16", session_id=1)) is True
    lignes = asyncio.run(db.get_recent_verses(limit=10))
    assert lignes[0]["sent_to_propresenter"]
    asyncio.run(db.disconnect())


def test_marquer_une_reference_absente_ne_casse_rien(tmp_path):
    db = _base(tmp_path)
    asyncio.run(db.add_detected_verse(VERSET, session_id=1))

    assert asyncio.run(db.marquer_projete("Romains 8:28", session_id=1)) is False
    lignes = asyncio.run(db.get_recent_verses(limit=10))
    assert not lignes[0]["sent_to_propresenter"]
    asyncio.run(db.disconnect())


def test_seule_la_detection_la_plus_recente_est_marquee(tmp_path):
    """Une même référence revient plusieurs fois dans un culte.

    C'est celle que le régisseur vient de projeter qui compte, pas la
    première fois que le prédicateur l'a citée.
    """
    db = _base(tmp_path)
    premier = asyncio.run(db.add_detected_verse(VERSET, session_id=1))
    second = asyncio.run(db.add_detected_verse(VERSET, session_id=1))

    asyncio.run(db.marquer_projete("Jean 3:16", session_id=1))
    lignes = {l["id"]: l for l in asyncio.run(db.get_recent_verses(limit=10))}
    assert lignes[second]["sent_to_propresenter"]
    assert not lignes[premier]["sent_to_propresenter"]
    asyncio.run(db.disconnect())
