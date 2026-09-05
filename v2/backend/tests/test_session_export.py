"""Export de fin de culte — compte rendu et diapositives.

Le .pptx est écrit à la main, sans bibliothèque : ces tests sont donc le seul
garde-fou contre un fichier qui s'ouvrirait mal. Ils vérifient la structure
qu'Office exige, pas seulement que la fonction ne lève pas d'exception.
"""

import sys
import zipfile
import xml.dom.minidom
from io import BytesIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.session_export import vers_markdown, vers_pptx, nom_fichier

SESSION = {
    "name": "Culte du dimanche",
    "started_at": "2026-07-26T10:02:00",
    "duration_minutes": 78,
    "summary": "Prédication sur la persévérance.",
    "transcript": "ouvrons ensemble Exode chapitre 17",
}
VERSETS = [
    {"reference": "Exode 17:11", "text": "Lorsque Moïse élevait sa main…",
     "detected_at": "2026-07-26T10:14:05"},
    {"reference": "Jean 11:43", "text": "Il cria d'une voix forte: Lazare, sors!",
     "detected_at": "2026-07-26T11:03:47"},
]


# ── Compte rendu ─────────────────────────────────────────────────────────────

def test_markdown_contient_tout_le_culte():
    md = vers_markdown(SESSION, VERSETS)
    assert "# Culte du dimanche" in md
    assert "Prédication sur la persévérance." in md
    for v in VERSETS:
        assert v["reference"] in md
        assert v["text"] in md
    assert "10:14" in md, "l'horodatage doit être réduit à l'heure du culte"
    assert "## Transcription" in md


def test_markdown_survit_a_une_session_vide():
    """Un culte sans verset détecté ne doit pas casser l'export."""
    md = vers_markdown({"name": "Réunion"}, [])
    assert "# Réunion" in md
    assert "## Versets projetés" not in md


# ── Diapositives ─────────────────────────────────────────────────────────────

def _archive(versets):
    return zipfile.ZipFile(BytesIO(vers_pptx(SESSION, versets)))


def test_pptx_a_les_parts_obligatoires():
    """Office refuse le fichier si une seule de ces parts manque."""
    noms = set(_archive(VERSETS).namelist())
    for part in (
        "[Content_Types].xml",
        "_rels/.rels",
        "ppt/presentation.xml",
        "ppt/_rels/presentation.xml.rels",
        "ppt/theme/theme1.xml",
        "ppt/slideMasters/slideMaster1.xml",
        "ppt/slideMasters/_rels/slideMaster1.xml.rels",
        "ppt/slideLayouts/slideLayout1.xml",
        "ppt/slideLayouts/_rels/slideLayout1.xml.rels",
    ):
        assert part in noms, f"part manquante : {part}"


def test_pptx_une_diapositive_par_verset():
    z = _archive(VERSETS)
    diapos = [n for n in z.namelist() if n.startswith("ppt/slides/slide")
              and n.endswith(".xml")]
    assert len(diapos) == len(VERSETS)
    # Chaque diapositive doit être déclarée ET reliée : une part orpheline
    # ouvre un fichier vide sans message d'erreur.
    types = z.read("[Content_Types].xml").decode()
    rels = z.read("ppt/_rels/presentation.xml.rels").decode()
    for i in range(1, len(VERSETS) + 1):
        assert f"/ppt/slides/slide{i}.xml" in types
        assert f"slides/slide{i}.xml" in rels
        assert f"ppt/slides/_rels/slide{i}.xml.rels" in z.namelist()


def test_pptx_xml_bien_forme_partout():
    z = _archive(VERSETS)
    for nom in z.namelist():
        if nom.endswith((".xml", ".rels")):
            xml.dom.minidom.parseString(z.read(nom))


def test_pptx_identifiants_de_diapositive_au_dessus_de_256():
    """Sous 256, Office rejette la présentation en silence."""
    presentation = _archive(VERSETS).read("ppt/presentation.xml").decode()
    assert '<p:sldId id="256"' in presentation
    assert '<p:sldId id="255"' not in presentation


def test_pptx_echappe_les_caracteres_xml():
    """Un « & » ou un « < » dans un verset ne doit pas casser l'archive."""
    piege = [{"reference": "Test 1:1", "text": "Pierre & Jean <ici>",
              "detected_at": "2026-07-26T10:00:00"}]
    z = _archive(piege)
    contenu = z.read("ppt/slides/slide1.xml").decode()
    assert "Pierre &amp; Jean &lt;ici&gt;" in contenu
    xml.dom.minidom.parseString(contenu)


def test_pptx_sans_verset_reste_ouvrable():
    z = _archive([])
    assert "ppt/slides/slide1.xml" in z.namelist()
    xml.dom.minidom.parseString(z.read("ppt/slides/slide1.xml"))


# ── Nom de fichier ───────────────────────────────────────────────────────────

def test_nom_de_fichier_sans_caractere_dangereux():
    nom = nom_fichier({"name": "Culte / spécial \"2026\"",
                       "started_at": "2026-07-26T10:00:00"}, "pptx")
    assert nom.endswith(".pptx")
    for interdit in ('/', '"', '\\', ' '):
        assert interdit not in nom
