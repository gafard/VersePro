"""Import d'une traduction fournie par l'église.

La validation est volontairement stricte : un fichier à moitié valide qui
s'installerait en silence produirait des versets manquants un dimanche matin,
sans que personne comprenne pourquoi. Chaque refus doit dire CE qui cloche.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.services.bible_import as bible_import
from app.services.bible_import import BibleInvalide


@pytest.fixture(autouse=True)
def _dossier_isole(tmp_path, monkeypatch):
    monkeypatch.setattr(bible_import, "IMPORT_DIR", tmp_path / "bibles_cache")


def _bible(livres=1, versets=1, **extra):
    return {
        "version": "TST", "language": "fr",
        "books": [
            {
                "name": "Jean", "abbreviation": "Jn",
                "chapters": [{"chapter": 3, "verses": [
                    {"verse": v + 1, "text": f"verset {v + 1}"} for v in range(versets)
                ]}],
            }
            for _ in range(livres)
        ],
        **extra,
    }


# ── Validation ───────────────────────────────────────────────────────────────

def test_un_fichier_conforme_est_accepte():
    resume = bible_import.valider(_bible(versets=3))
    assert resume["books"] == 1 and resume["verses"] == 3 and resume["language"] == "fr"


def test_une_liste_a_la_racine_est_refusee():
    with pytest.raises(BibleInvalide, match="objet JSON"):
        bible_import.valider([{"name": "Jean"}])


def test_sans_livres_le_fichier_est_refuse():
    with pytest.raises(BibleInvalide, match="Aucun livre"):
        bible_import.valider({"books": []})


def test_un_livre_sans_chapitre_est_signale_par_son_nom():
    """Le message doit nommer le livre fautif, pas dire « fichier invalide »."""
    mauvais = _bible()
    mauvais["books"][0]["chapters"] = []
    with pytest.raises(BibleInvalide, match="Jean"):
        bible_import.valider(mauvais)


def test_un_verset_sans_texte_est_refuse():
    mauvais = _bible()
    mauvais["books"][0]["chapters"][0]["verses"] = [{"verse": 1}]
    with pytest.raises(BibleInvalide, match="text"):
        bible_import.valider(mauvais)


def test_un_livre_sans_nom_ni_abreviation_est_refuse():
    mauvais = _bible()
    mauvais["books"][0]["name"] = ""
    mauvais["books"][0]["abbreviation"] = ""
    with pytest.raises(BibleInvalide, match="sans nom"):
        bible_import.valider(mauvais)


# ── Sigle ────────────────────────────────────────────────────────────────────

def test_le_sigle_du_fichier_sert_par_defaut():
    assert bible_import.normaliser_sigle("", {"version": "SEM"}) == "SEM"


def test_un_sigle_propose_prime():
    assert bible_import.normaliser_sigle("nbs21", {"version": "SEM"}) == "NBS21"


def test_un_sigle_malforme_est_refuse():
    for mauvais in ("A", "trop-long-vraiment", "AB CD", "É"):
        with pytest.raises(BibleInvalide, match="sigle"):
            bible_import.normaliser_sigle(mauvais, {})


def test_les_sigles_livres_sont_proteges():
    """Écraser LSG ferait disparaître le corpus de référence de la détection."""
    for reserve in ("LSG", "KJF"):
        with pytest.raises(BibleInvalide, match="livré"):
            bible_import.normaliser_sigle(reserve, {})


# ── Installation ─────────────────────────────────────────────────────────────

def test_importer_puis_lister():
    resume = bible_import.importer(json.dumps(_bible(versets=2)), "SEM")
    assert resume["id"] == "SEM" and resume["verses"] == 2
    liste = bible_import.lister()
    assert [v["id"] for v in liste] == ["SEM"]
    assert liste[0]["verses"] == 2


def test_un_json_illisible_est_refuse_avec_sa_raison():
    with pytest.raises(BibleInvalide, match="JSON illisible"):
        bible_import.importer("{ceci n'est pas du json", "SEM")


def test_un_fichier_trop_lourd_est_refuse(monkeypatch):
    monkeypatch.setattr(bible_import, "MAX_BIBLE_BYTES", 32)
    with pytest.raises(BibleInvalide, match="trop lourd"):
        bible_import.importer(json.dumps(_bible()), "SEM")


def test_rien_nest_ecrit_quand_le_fichier_est_refuse():
    """Un refus ne doit pas laisser de bible à moitié installée."""
    with pytest.raises(BibleInvalide):
        bible_import.importer(json.dumps({"books": []}), "SEM")
    assert bible_import.lister() == []


def test_les_bibles_livrees_ne_sont_pas_listees_comme_importees(tmp_path):
    """En développement, le dossier est partagé avec les traductions livrées :
    seules celles qui ont leur fiche sont des imports."""
    bible_import.IMPORT_DIR.mkdir(parents=True, exist_ok=True)
    (bible_import.IMPORT_DIR / "kjf.json").write_text("{}", encoding="utf-8")
    bible_import.importer(json.dumps(_bible()), "SEM")
    assert [v["id"] for v in bible_import.lister()] == ["SEM"]


def test_la_fiche_daccompagnement_nest_pas_prise_pour_une_bible():
    bible_import.importer(json.dumps(_bible()), "SEM")
    assert all(not v["id"].endswith(".META") for v in bible_import.lister())


def test_supprimer_une_version_importee():
    bible_import.importer(json.dumps(_bible()), "SEM")
    bible_import.supprimer("SEM")
    assert bible_import.lister() == []


def test_une_version_livree_ne_peut_pas_etre_supprimee():
    with pytest.raises(BibleInvalide, match="livrée"):
        bible_import.supprimer("LSG")
