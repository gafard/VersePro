"""Import d'une traduction biblique fournie par l'église.

VersePro ne distribue que le domaine public (LSG, KJF). Une église qui possède
les droits d'une autre traduction peut l'ajouter elle-même : le fichier reste
sur son poste, VersePro ne le rediffuse à personne. Voir CONDITIONS.md — la
responsabilité de ce qui est ajouté appartient à qui l'ajoute.

Le format attendu est celui du corpus de VersePro, pour qu'un fichier valide
soit vérifiable immédiatement contre bible.json :

    {
      "version": "SEM",
      "language": "fr",
      "books": [
        {"name": "Genèse", "abbreviation": "Gen",
         "chapters": [{"chapter": 1, "verses": [{"verse": 1, "text": "…"}]}]}
      ]
    }

La validation est délibérément stricte et bavarde : un fichier à moitié valide
qui s'installerait en silence produirait des versets manquants un dimanche
matin, sans que personne comprenne pourquoi.
"""

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Tuple

from loguru import logger

from ..core.config import DATA_DIR

# Les bibles importées vivent dans le dossier INSCRIPTIBLE, jamais dans le
# paquet : celui-ci est en lecture seule une fois l'application installée.
IMPORT_DIR = Path(DATA_DIR) / "bibles_cache"

# Un corpus complet en français pèse ~5 Mo ; la borne laisse largement la place
# à une bible annotée sans permettre qu'un fichier aberrant sature la mémoire.
MAX_BIBLE_BYTES = 80 * 1024 * 1024
MIN_LIVRES = 1
# Sigles réservés par les versions livrées : les écraser ferait disparaître le
# corpus de référence, sur lequel s'appuie la détection.
SIGLES_RESERVES = {"LSG", "KJF"}
_SIGLE = re.compile(r"^[A-Z0-9]{2,8}$")


class BibleInvalide(ValueError):
    """Fichier refusé, avec une raison présentable à un bénévole."""


STANDARD_66_BOOKS = [
    "Genèse", "Exode", "Lévitique", "Nombres", "Deutéronome", "Josué", "Juges", "Ruth",
    "1 Samuel", "2 Samuel", "1 Rois", "2 Rois", "1 Chroniques", "2 Chroniques", "Esdras", "Néhémie",
    "Esther", "Job", "Psaumes", "Proverbes", "Ecclésiaste", "Cantique des cantiques", "Ésaïe", "Jérémie",
    "Lamentations", "Ézéchiel", "Daniel", "Osée", "Joël", "Amos", "Abdias", "Jonas", "Michée",
    "Nahum", "Habacuc", "Sophonie", "Aggée", "Zacharie", "Malachie",
    "Matthieu", "Marc", "Luc", "Jean", "Actes", "Romains", "1 Corinthiens", "2 Corinthiens",
    "Galates", "Éphésiens", "Philippiens", "Colossiens", "1 Thessaloniciens", "2 Thessaloniciens",
    "1 Timothée", "2 Timothée", "Tite", "Philémon", "Hébreux", "Jacques",
    "1 Pierre", "2 Pierre", "1 Jean", "2 Jean", "3 Jean", "Jude", "Apocalypse"
]


def _normaliser_liste_livres(livres_raw: list) -> list:
    """Standardise les clés des livres, chapitres et versets (ex: Text -> text, ID -> chapter/verse, etc.)"""
    livres = []
    for idx, b in enumerate(livres_raw):
        if not isinstance(b, dict):
            continue
        nom = str(b.get("name") or b.get("Text") or b.get("title") or b.get("bname") or b.get("nom") or b.get("abbreviation") or (STANDARD_66_BOOKS[idx] if idx < len(STANDARD_66_BOOKS) else f"Livre {idx+1}")).strip()
        abbr = str(b.get("abbreviation") or b.get("abbr") or b.get("sigle") or "").strip()
        
        chapitres_raw = b.get("chapters") or b.get("Chapters") or b.get("chapitres") or []
        chapitres = []
        if isinstance(chapitres_raw, list):
            for ch_idx, c in enumerate(chapitres_raw):
                if not isinstance(c, dict):
                    continue
                ch_num = c.get("chapter") or c.get("num") or c.get("ID") or c.get("c") or (ch_idx + 1)
                versets_raw = c.get("verses") or c.get("Verses") or c.get("versets") or []
                versets = []
                if isinstance(versets_raw, list):
                    for v_idx, v in enumerate(versets_raw):
                        if isinstance(v, dict):
                            v_num = v.get("verse") or v.get("num") or v.get("ID") or v.get("v") or (v_idx + 1)
                            v_text = str(v.get("text") or v.get("Text") or v.get("texte") or v.get("content") or "").strip()
                            if v_text:
                                versets.append({"verse": int(v_num), "text": v_text})
                        elif isinstance(v, str) and v.strip():
                            versets.append({"verse": v_idx + 1, "text": v.strip()})
                if versets:
                    chapitres.append({"chapter": int(ch_num), "verses": versets})
        if chapitres:
            item = {"name": nom, "chapters": chapitres}
            if abbr:
                item["abbreviation"] = abbr
            livres.append(item)
    return livres


def normaliser_structure_bible(donnees: Any) -> Dict[str, Any]:
    """Normalise n'importe quelle structure JSON de Bible vers le schéma officiel VersePro {"books": [...]}"""
    if isinstance(donnees, str) and donnees.strip().startswith("<"):
        return _parse_xml_bible(donnees.strip())

    if isinstance(donnees, list):
        return {"books": _normaliser_liste_livres(donnees)}

    if not isinstance(donnees, dict):
        raise BibleInvalide("Le fichier doit être un objet JSON ou une liste de livres.")

    # Format racine "bible", "data", "corpus"
    for key in ("bible", "data", "corpus"):
        if key in donnees and isinstance(donnees[key], (dict, list)):
            sub = normaliser_structure_bible(donnees[key])
            if "version" not in sub and "version" in donnees:
                sub["version"] = donnees["version"]
            return sub

    # Format avec "Testaments"
    testaments = donnees.get("Testaments") or donnees.get("testaments") or donnees.get("TESTAMENTS")
    if isinstance(testaments, list):
        livres = []
        for t in testaments:
            if isinstance(t, dict):
                b_list = t.get("Books") or t.get("books") or t.get("LIVRES") or t.get("livres") or []
                if isinstance(b_list, list):
                    livres.extend(b_list)
        return {"version": donnees.get("version"), "books": _normaliser_liste_livres(livres)}

    # Clef "livres", "book", "books_list", "LIVRES", "books"
    livres_raw = (
        donnees.get("books")
        or donnees.get("livres")
        or donnees.get("book")
        or donnees.get("LIVRES")
        or donnees.get("books_list")
    )
    if isinstance(livres_raw, list):
        return {"version": donnees.get("version"), "books": _normaliser_liste_livres(livres_raw)}

    # Format indexé par livres 1-66 (ex: {"1": {"1": {"1": "text"}}})
    if "1" in donnees and isinstance(donnees["1"], dict):
        livres = []
        for b_idx_str in sorted(donnees.keys(), key=lambda x: int(x) if x.isdigit() else 999):
            if not b_idx_str.isdigit():
                continue
            b_idx = int(b_idx_str) - 1
            b_name = STANDARD_66_BOOKS[b_idx] if 0 <= b_idx < len(STANDARD_66_BOOKS) else f"Livre {b_idx_str}"
            chapters_dict = donnees[b_idx_str]
            chapitres = []
            if isinstance(chapters_dict, dict):
                for ch_str in sorted(chapters_dict.keys(), key=lambda x: int(x) if x.isdigit() else 999):
                    if not ch_str.isdigit():
                        continue
                    ch_num = int(ch_str)
                    verses_dict = chapters_dict[ch_str]
                    versets = []
                    if isinstance(verses_dict, dict):
                        for v_str in sorted(verses_dict.keys(), key=lambda x: int(x) if x.isdigit() else 999):
                            if not v_str.isdigit():
                                continue
                            v_num = int(v_str)
                            v_text = str(verses_dict[v_str]).strip()
                            if v_text:
                                versets.append({"verse": v_num, "text": v_text})
                    if versets:
                        chapitres.append({"chapter": ch_num, "verses": versets})
            if chapitres:
                livres.append({"name": b_name, "chapters": chapitres})
        if livres:
            return {"version": donnees.get("version"), "books": livres}

    return donnees


def _parse_xml_bible(contenu: str) -> Dict[str, Any]:
    """Parse un fichier XML (Zefania, OSIS, OpenSong, OpenBible) vers la structure VersePro"""
    try:
        import xml.etree.ElementTree as ET
        root = ET.fromstring(contenu)
    except Exception as exc:
        raise BibleInvalide(f"Fichier XML invalide : {exc}") from exc

    version_title = root.attrib.get("biblename") or root.attrib.get("name") or root.attrib.get("id") or "XML"
    livres = []
    
    # Détecter si la racine est un livre ou contient des livres
    if "BOOK" in root.tag.upper() or "LIVRE" in root.tag.upper():
        book_nodes = [root]
    else:
        book_nodes = (
            root.findall(".//BIBLEBOOK")
            or root.findall(".//book")
            or root.findall(".//Book")
            or root.findall(".//livre")
            or root.findall(".//Livre")
            or root.findall(".//div[@type='book']")
        )
    
    for idx, b_node in enumerate(book_nodes):
        name = b_node.attrib.get("bname") or b_node.attrib.get("name") or b_node.attrib.get("n")
        if not name and idx < len(STANDARD_66_BOOKS):
            name = STANDARD_66_BOOKS[idx]
        
        chapitres = []
        ch_nodes = b_node.findall(".//CHAPTER") or b_node.findall(".//chapter") or b_node.findall(".//c")
        for ch_idx, c_node in enumerate(ch_nodes):
            ch_num = int(c_node.attrib.get("cnumber") or c_node.attrib.get("n") or (ch_idx + 1))
            versets = []
            v_nodes = c_node.findall(".//VERS") or c_node.findall(".//verse") or c_node.findall(".//v")
            for v_idx, v_node in enumerate(v_nodes):
                v_num = int(v_node.attrib.get("vnumber") or v_node.attrib.get("n") or (v_idx + 1))
                v_text = "".join(v_node.itertext()).strip()
                if v_text:
                    versets.append({"verse": v_num, "text": v_text})
            if versets:
                chapitres.append({"chapter": ch_num, "verses": versets})
        if chapitres:
            livres.append({"name": name or f"Livre {idx+1}", "chapters": chapitres})
            
    if not livres:
        raise BibleInvalide("Aucun livre extrait du fichier XML.")
        
    return {"version": version_title, "books": livres}


def valider(donnees: Any) -> Dict[str, Any]:
    """Vérifie la structure et retourne un résumé (sigle, langue, comptages)."""
    # Une structure déjà canonique doit être validée telle quelle. La
    # normalisation des formats externes filtre volontairement les entrées
    # incomplètes ; l'appliquer ici masquerait alors le nom du livre ou du
    # verset fautif derrière un vague « aucun livre ».
    structure = (
        donnees
        if isinstance(donnees, dict) and isinstance(donnees.get("books"), list)
        else normaliser_structure_bible(donnees)
    )
    if not isinstance(structure, dict):
        raise BibleInvalide("Le fichier doit contenir une structure de Bible valide.")
    livres = structure.get("books")
    if not isinstance(livres, list) or len(livres) < MIN_LIVRES:
        raise BibleInvalide("Aucun livre trouvé dans le fichier importé.")

    nb_chapitres = 0
    nb_versets = 0
    sans_nom: List[int] = []
    for index, livre in enumerate(livres):
        if not isinstance(livre, dict):
            raise BibleInvalide(f"Le livre n°{index + 1} n'est pas un objet.")
        nom = str(livre.get("name") or "").strip()
        abbr = str(livre.get("abbreviation") or "").strip()
        if not nom and not abbr:
            sans_nom.append(index + 1)
            continue
        chapitres = livre.get("chapters")
        if not isinstance(chapitres, list) or not chapitres:
            raise BibleInvalide(f"« {nom or abbr} » n'a aucun chapitre.")
        for chapitre in chapitres:
            if not isinstance(chapitre, dict):
                raise BibleInvalide(f"Un chapitre de « {nom or abbr} » n'est pas un objet.")
            versets = chapitre.get("verses")
            if not isinstance(versets, list):
                raise BibleInvalide(
                    f"Le chapitre {chapitre.get('chapter')} de « {nom or abbr} » n'a pas de liste « verses »."
                )
            nb_chapitres += 1
            for verset in versets:
                if not isinstance(verset, dict) or "text" not in verset:
                    raise BibleInvalide(
                        f"Un verset de « {nom or abbr} » {chapitre.get('chapter')} n'a pas de champ « text »."
                    )
                nb_versets += 1

    if sans_nom:
        raise BibleInvalide(
            f"{len(sans_nom)} livre(s) sans nom ni abréviation (n° {', '.join(map(str, sans_nom[:5]))})."
        )
    if not nb_versets:
        raise BibleInvalide("Le fichier ne contient aucun verset.")

    return {
        "version": str(structure.get("version") or "").strip().upper(),
        "language": str(structure.get("language") or "").strip() or "fr",
        "books": len(livres),
        "chapters": nb_chapitres,
        "verses": nb_versets,
    }


def normaliser_sigle(propose: str, resume: Dict[str, Any]) -> str:
    """Sigle sous lequel la version apparaîtra (le nom de fichier en dérive)."""
    sigle = (propose or resume.get("version") or "").strip().upper()
    if not _SIGLE.match(sigle):
        raise BibleInvalide(
            "Le sigle doit faire 2 à 8 caractères, en lettres majuscules ou chiffres (ex. SEM, NBS21)."
        )
    if sigle in SIGLES_RESERVES:
        raise BibleInvalide(
            f"« {sigle} » est un sigle livré avec VersePro ; choisissez-en un autre."
        )
    return sigle


def lister() -> List[Dict[str, Any]]:
    """Versions importées par l'église, distinctes de celles livrées."""
    if not IMPORT_DIR.is_dir():
        return []
    versions = []
    for fichier in sorted(IMPORT_DIR.glob("*.json")):
        if fichier.name.endswith(".meta.json"):
            continue  # fiche d'accompagnement, pas une bible
        fiche = IMPORT_DIR / f"{fichier.stem}.meta.json"
        # Seule une bible IMPORTÉE possède sa fiche. C'est ce qui la distingue
        # des traductions livrées avec VersePro, qui partagent ce dossier en
        # développement — et qu'il ne faut surtout pas proposer à la suppression.
        if not fiche.is_file():
            continue
        try:
            resume = json.loads(fiche.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            resume = {}
        versions.append({
            "id": fichier.stem.upper(),
            "books": resume.get("books"),
            "verses": resume.get("verses"),
            "language": resume.get("language", "fr"),
            "bytes": fichier.stat().st_size,
        })
    return versions


# ── Catalogue des traductions ────────────────────────────────────────────────
#
# La console proposait six pastilles de version — LSG, NBS, SEM, TOB, FC, KJF —
# alors que l'application installée n'en embarque que DEUX. Sur le poste de
# développement les six fichiers existent, donc tout paraissait fonctionner ;
# chez l'église, le pasteur demandait la Semeur, l'opérateur cliquait « SEM »,
# et rien ne changeait à l'écran.
#
# Ce catalogue dit la vérité : ce qui est là, ce qui ne l'est pas, et pourquoi.
# VersePro ne distribue que le domaine public. Une traduction sous droits reste
# à la charge de l'église qui en possède l'usage.

PUBLIC_DOWNLOAD_URLS = {
    "DBY": "https://raw.githubusercontent.com/scrollmapper/bible_databases/master/formats/json/FreJND.json",
    "MAR": "https://raw.githubusercontent.com/scrollmapper/bible_databases/master/formats/json/FreBDM1744.json",
    "CRA": "https://raw.githubusercontent.com/scrollmapper/bible_databases/master/formats/json/FreCrampon.json",
    "OST": "https://raw.githubusercontent.com/scrollmapper/bible_databases/master/formats/json/FreBBB.json",
}

CATALOGUE = [
    # Livrées avec VersePro — domaine public, toujours présentes.
    {"id": "LSG", "nom": "Louis Segond", "annee": 1910,
     "licence": "domaine-public", "origine": "livree"},
    {"id": "KJF", "nom": "King James Française", "annee": 2006,
     "licence": "domaine-public", "origine": "livree"},

    # Domaine public, non embarquées pour ne pas alourdir le paquet : sept Mo
    # chacune, pour des traductions que peu d'églises emploient au culte.
    {"id": "DBY", "nom": "Darby", "annee": 1885,
     "licence": "domaine-public", "origine": "publique", "download_url": PUBLIC_DOWNLOAD_URLS["DBY"]},
    {"id": "OST", "nom": "Ostervald", "annee": 1867,
     "licence": "domaine-public", "origine": "publique", "download_url": PUBLIC_DOWNLOAD_URLS["OST"]},
    {"id": "MAR", "nom": "Martin", "annee": 1744,
     "licence": "domaine-public", "origine": "publique", "download_url": PUBLIC_DOWNLOAD_URLS["MAR"]},
    {"id": "CRA", "nom": "Crampon", "annee": 1904,
     "licence": "domaine-public", "origine": "publique", "download_url": PUBLIC_DOWNLOAD_URLS["CRA"]},

    # Sous droits : l'église doit posséder le fichier. VersePro ne le fournit
    # pas et ne le rediffuse pas.
    {"id": "SEM", "nom": "Bible du Semeur", "annee": 2015,
     "licence": "sous-droits", "editeur": "Biblica", "origine": "tierce"},
    {"id": "NBS", "nom": "Nouvelle Bible Segond", "annee": 2002,
     "licence": "sous-droits", "editeur": "Société biblique française", "origine": "tierce"},
    {"id": "TOB", "nom": "Traduction œcuménique", "annee": 2010,
     "licence": "sous-droits", "editeur": "Cerf / SBF", "origine": "tierce"},
    {"id": "FC", "nom": "Français courant", "annee": 1997,
     "licence": "sous-droits", "editeur": "Société biblique française", "origine": "tierce"},
    {"id": "S21", "nom": "Segond 21", "annee": 2007,
     "licence": "sous-droits", "editeur": "Société biblique de Genève", "origine": "tierce"},
    {"id": "PDV", "nom": "Parole de Vie", "annee": 2000,
     "licence": "sous-droits", "editeur": "Société biblique française", "origine": "tierce"},
]


def catalogue(installees: List[str]) -> Dict[str, Any]:
    """État réel de chaque traduction : présente, ou absente et pourquoi.

    `installees` vient du moteur de lecture — la seule source qui fasse foi.
    Une version listée ici mais absente de cet ensemble n'est PAS utilisable,
    et l'interface doit le montrer plutôt que d'offrir un bouton mort.
    """
    presentes = {str(v).upper() for v in installees}
    fiches = {f["id"]: f for f in lister()}

    entrees = []
    for fiche in CATALOGUE:
        sigle = fiche["id"]
        importee = sigle in fiches
        entrees.append({
            **fiche,
            "installee": sigle in presentes,
            "importee": importee,
            "amovible": importee,          # seul un import se retire
            "versets": fiches.get(sigle, {}).get("verses"),
        })

    # Une église peut installer une traduction absente du catalogue (un sigle
    # à elle). Elle doit apparaître, sinon elle serait invisible et impossible
    # à retirer depuis l'interface.
    connus = {f["id"] for f in CATALOGUE}
    for sigle, fiche in fiches.items():
        if sigle not in connus:
            entrees.append({
                "id": sigle, "nom": f"Traduction « {sigle} »", "annee": None,
                "licence": "inconnue", "origine": "tierce",
                "installee": sigle in presentes, "importee": True,
                "amovible": True, "versets": fiche.get("verses"),
            })

    return {
        "versions": entrees,
        "dossier": str(IMPORT_DIR),
        "installees": sorted(presentes),
    }


def importer(contenu: str, sigle_propose: str = "") -> Dict[str, Any]:
    """Valide puis installe une traduction. Écriture atomique."""
    if len(contenu.encode("utf-8")) > MAX_BIBLE_BYTES:
        raise BibleInvalide(
            f"Fichier trop lourd ; maximum {MAX_BIBLE_BYTES // (1024 * 1024)} Mo."
        )
    
    clean_content = contenu.strip()
    if clean_content.startswith("<"):
        donnees = _parse_xml_bible(clean_content)
    else:
        try:
            donnees_raw = json.loads(clean_content)
        except ValueError as exc:
            raise BibleInvalide(f"Fichier JSON illisible : {exc}") from exc
        donnees = normaliser_structure_bible(donnees_raw)

    resume = valider(donnees)
    sigle = normaliser_sigle(sigle_propose, resume)

    IMPORT_DIR.mkdir(parents=True, exist_ok=True)
    cible = IMPORT_DIR / f"{sigle.lower()}.json"
    handle, temporaire = tempfile.mkstemp(dir=str(IMPORT_DIR), suffix=".part")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as fichier:
            json.dump(donnees, fichier, ensure_ascii=False)
        os.replace(temporaire, cible)
    except Exception:
        Path(temporaire).unlink(missing_ok=True)
        raise
    (IMPORT_DIR / f"{sigle.lower()}.meta.json").write_text(
        json.dumps({**resume, "id": sigle}, ensure_ascii=False), encoding="utf-8")

    logger.info(
        f"📖 Bible « {sigle} » importée : {resume['books']} livres, "
        f"{resume['verses']} versets ({resume['language']})."
    )
    return {"id": sigle, **resume}


def supprimer(sigle: str) -> None:
    """Retire une version importée. Les versions livrées ne sont pas touchées."""
    propre = (sigle or "").strip().upper()
    if propre in SIGLES_RESERVES:
        raise BibleInvalide(f"« {propre} » est livrée avec VersePro et ne peut pas être retirée.")
    if not _SIGLE.match(propre):
        raise BibleInvalide("Sigle invalide.")
    for suffixe in (".json", ".meta.json"):
        (IMPORT_DIR / f"{propre.lower()}{suffixe}").unlink(missing_ok=True)
    logger.info(f"📖 Bible « {propre} » retirée.")
