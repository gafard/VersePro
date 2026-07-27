"""Habillage personnalisé : import du PNG et nettoyage des zones.

Les zones finissent en styles inline sur l'écran de projection ; ce qui vient
du réseau doit donc être borné et validé avant d'être stocké, jamais après.
"""

import json
import struct
import sys
import zlib
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.services.overlay_store as overlay_store


def _png(width: int = 320, height: int = 180) -> bytes:
    """PNG minimal valide, construit sans dépendance d'image."""
    def chunk(nom: bytes, donnees: bytes) -> bytes:
        corps = nom + donnees
        return struct.pack(">I", len(donnees)) + corps + struct.pack(">I", zlib.crc32(corps))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    brut = b"".join(b"\x00" + b"\x00\x00\x00\x00" * width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(brut)) + chunk(b"IEND", b""))


@pytest.fixture(autouse=True)
def _dossier_isole(tmp_path, monkeypatch):
    """Aucun test n'écrit dans le dossier de données réel."""
    monkeypatch.setattr(overlay_store, "OVERLAY_DIR", tmp_path / "overlay")
    monkeypatch.setattr(overlay_store, "IMAGE_PATH", tmp_path / "overlay" / "habillage.png")
    monkeypatch.setattr(overlay_store, "LIBRARY_DIR", tmp_path / "overlay" / "bibliotheque")


# ── Bibliothèque d'habillages ────────────────────────────────────────────────

def test_un_nom_devient_un_identifiant_de_dossier_sur():
    assert overlay_store.slugify("Bandeau Agoé-Logopé 2026 !") == "bandeau-agoe-logope-2026"


def test_un_nom_vide_reste_utilisable():
    assert overlay_store.slugify("") == "habillage"


def test_une_remontee_de_chemin_reste_dans_la_bibliotheque():
    """L'identifiant vient du réseau : il ne doit jamais désigner un dossier
    en dehors de la bibliothèque."""
    racine = overlay_store.LIBRARY_DIR.resolve()
    for hostile in ("../../etc/passwd", "/etc/shadow", "..\\..\\windows"):
        assert str(overlay_store._dossier_preset(hostile)).startswith(str(racine))


def test_enregistrer_puis_relire_un_habillage():
    overlay_store.save_preset("Mon Bandeau", "Bandeaux",
                              overlay_store.DEFAULT_ZONES, overlay_store.DEFAULT_SHAPES)
    liste = overlay_store.list_presets()
    assert [p["name"] for p in liste] == ["Mon Bandeau"]
    assert liste[0]["category"] == "Bandeaux"
    charge = overlay_store.load_preset("mon-bandeau")
    assert charge["shapes"][0]["fill"] == "#ffffff"


def test_reenregistrer_le_meme_nom_ecrase_sans_doublon():
    overlay_store.save_preset("Bandeau", "Bandeaux", overlay_store.DEFAULT_ZONES, [])
    overlay_store.save_preset("Bandeau", "Annonces", overlay_store.DEFAULT_ZONES, [])
    liste = overlay_store.list_presets()
    assert len(liste) == 1 and liste[0]["category"] == "Annonces"


def test_un_habillage_enregistre_est_nettoye_comme_les_autres():
    """Ce qui entre dans la bibliothèque subit le même contrôle que l'actif."""
    overlay_store.save_preset("Sale", "Test", overlay_store.DEFAULT_ZONES,
                              [{"fill": "url(javascript:0)", "x": 9999}])
    assert overlay_store.load_preset("sale")["shapes"][0]["fill"] == "#ffffff"


def test_supprimer_un_habillage():
    overlay_store.save_preset("Temporaire", "Test", overlay_store.DEFAULT_ZONES, [])
    overlay_store.delete_preset("temporaire")
    assert overlay_store.list_presets() == []


def test_un_style_designe_un_habillage_de_la_bibliotheque():
    assert overlay_store.style_slug("habillage:mon-bandeau") == "mon-bandeau"
    assert overlay_store.style_slug("filet") is None
    assert overlay_store.style_slug(None) is None


def test_resolution_prefere_lhabillage_designe_par_le_style():
    overlay_store.save_preset("Rouge", "Test", overlay_store.DEFAULT_ZONES,
                              [{"x": 10, "y": 10, "w": 20, "h": 20, "fill": "#ff0000"}])
    resolu = overlay_store.resolve_overlay("habillage:rouge", "", "")
    assert resolu["preset"] == "rouge"
    assert resolu["shapes"][0]["fill"] == "#ff0000"


def test_un_habillage_introuvable_retombe_sur_lactif():
    """Un préréglage supprimé ne doit pas laisser l'écran vide un dimanche."""
    resolu = overlay_store.resolve_overlay("habillage:disparu", "", "")
    assert resolu["preset"] is None
    assert len(resolu["shapes"]) == len(overlay_store.DEFAULT_SHAPES)


def test_sans_preset_la_resolution_donne_lhabillage_en_cours():
    resolu = overlay_store.resolve_overlay("filet", "", "[]")
    assert resolu["preset"] is None and resolu["shapes"] == []


# ── Import de l'image ────────────────────────────────────────────────────────

def test_les_dimensions_sont_lues_dans_len_tete():
    assert overlay_store.png_dimensions(_png(640, 360)) == (640, 360)


def test_un_fichier_qui_nest_pas_un_png_est_refuse():
    with pytest.raises(ValueError, match="pas un PNG"):
        overlay_store.png_dimensions(b"GIF89a" + b"\x00" * 40)


def test_une_data_url_est_acceptee():
    import base64
    charge = "data:image/png;base64," + base64.b64encode(_png()).decode()
    assert overlay_store.decode_upload(charge).startswith(b"\x89PNG")


def test_une_image_trop_lourde_est_refusee(monkeypatch):
    """Un fichier aberrant ne doit remplir ni le disque ni la mémoire d'une régie."""
    import base64
    charge = base64.b64encode(_png(200, 200)).decode()
    # Seuil placé sous la taille réelle du PNG : un transparent uni se compresse
    # très bien, une borne « réaliste » ne prouverait rien ici.
    monkeypatch.setattr(overlay_store, "MAX_IMAGE_BYTES", 32)
    with pytest.raises(ValueError, match="trop lourde"):
        overlay_store.decode_upload(charge)


def test_enregistrement_puis_statut():
    etat = overlay_store.save_image(_png(1920, 1080))
    assert etat["installed"] is True
    assert (etat["width"], etat["height"]) == (1920, 1080)
    assert overlay_store.status()["installed"] is True
    overlay_store.delete_image()
    assert overlay_store.status()["installed"] is False


def test_aucun_fichier_partiel_apres_un_echec():
    """L'écriture est atomique : pas de PNG à moitié écrit sur l'écran."""
    with pytest.raises(ValueError):
        overlay_store.save_image(b"pas un png")
    restes = list(overlay_store.OVERLAY_DIR.glob("*")) if overlay_store.OVERLAY_DIR.exists() else []
    assert restes == []


# ── Nettoyage des zones ──────────────────────────────────────────────────────

def test_zones_absentes_retombent_sur_les_valeurs_de_depart():
    zones = overlay_store.parse_zones("")
    assert set(zones) == {"text", "reference"}
    assert zones["text"] == overlay_store.DEFAULT_ZONES["text"]


def test_json_illisible_ne_fait_pas_tomber_lecran():
    assert overlay_store.parse_zones("{ceci n'est pas du json")["text"]["size"] == 5.0


def test_une_couleur_hostile_est_rejetee():
    """La couleur part en style inline : elle ne doit pas transporter de CSS."""
    sale = json.dumps({"text": {"color": "red; background:url(//pirate)"}})
    assert overlay_store.parse_zones(sale)["text"]["color"] == "#1d2b63"


def test_une_couleur_hexadecimale_valide_passe():
    assert overlay_store.parse_zones(json.dumps({"text": {"color": "#AABBCC"}}))["text"]["color"] == "#AABBCC"


def test_les_positions_sont_bornees():
    sale = json.dumps({"text": {"x": 9999, "y": -9999, "w": 0, "size": 500}})
    zone = overlay_store.parse_zones(sale)["text"]
    assert zone["x"] == 120 and zone["y"] == -20
    assert zone["w"] == 1 and zone["size"] == 30


def test_un_alignement_inconnu_retombe_sur_le_defaut():
    sale = json.dumps({"reference": {"align": "'; drop table", "valign": "ailleurs", "font": "comic"}})
    zone = overlay_store.parse_zones(sale)["reference"]
    assert zone["align"] == "center" and zone["valign"] == "middle" and zone["font"] == "sans"


# ── Formes construites dans VersePro ─────────────────────────────────────────

def test_formes_absentes_donnent_le_bandeau_de_depart():
    formes = overlay_store.parse_shapes("")
    assert len(formes) == 2
    assert formes[0]["fill"] == "#ffffff"


def test_une_liste_vide_signifie_aucune_forme():
    """Distinct de « non configuré » : l'opérateur a le droit de tout retirer."""
    assert overlay_store.parse_shapes("[]") == []


def test_le_nombre_de_formes_est_borne():
    """Une charge fabriquée ne doit pas faire rendre des milliers d'éléments."""
    sale = json.dumps([{"x": 1, "y": 1, "w": 5, "h": 5}] * 500)
    assert len(overlay_store.parse_shapes(sale)) == overlay_store.MAX_SHAPES


def test_une_couleur_de_forme_hostile_est_rejetee():
    sale = json.dumps([{"fill": "#fff; background-image:url(//pirate)"}])
    assert overlay_store.parse_shapes(sale)[0]["fill"] == "#ffffff"


def test_opacite_et_rayon_sont_bornes():
    sale = json.dumps([{"opacity": 40, "radius": -12}])
    forme = overlay_store.parse_shapes(sale)[0]
    assert forme["opacity"] == 1.0 and forme["radius"] == 0.0


def test_une_forme_qui_nest_pas_un_objet_est_ignoree():
    assert overlay_store.parse_shapes(json.dumps(["texte", 42, None])) == []


def test_les_formes_stockees_sont_deja_nettoyees():
    stocke = json.loads(overlay_store.dump_shapes([{"fill": "url(javascript:0)", "w": 9999}]))
    assert stocke[0]["fill"] == "#ffffff" and stocke[0]["w"] == 140


def test_ce_qui_est_stocke_est_deja_nettoye():
    """dump_zones sérialise APRÈS nettoyage : la base ne contient rien d'hostile."""
    stocke = json.loads(overlay_store.dump_zones({"text": {"color": "javascript:alert(1)", "x": 5000}}))
    assert stocke["text"]["color"] == "#1d2b63"
    assert stocke["text"]["x"] == 120
