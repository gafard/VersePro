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


def valider(donnees: Any) -> Dict[str, Any]:
    """Vérifie la structure et retourne un résumé (sigle, langue, comptages)."""
    if not isinstance(donnees, dict):
        raise BibleInvalide("Le fichier doit contenir un objet JSON, pas une liste.")
    livres = donnees.get("books")
    if not isinstance(livres, list) or len(livres) < MIN_LIVRES:
        raise BibleInvalide("Aucun livre trouvé : la clé « books » doit être une liste non vide.")

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
        "version": str(donnees.get("version") or "").strip().upper(),
        "language": str(donnees.get("language") or "").strip() or "fr",
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


def importer(contenu: str, sigle_propose: str = "") -> Dict[str, Any]:
    """Valide puis installe une traduction. Écriture atomique."""
    if len(contenu.encode("utf-8")) > MAX_BIBLE_BYTES:
        raise BibleInvalide(
            f"Fichier trop lourd ; maximum {MAX_BIBLE_BYTES // (1024 * 1024)} Mo."
        )
    try:
        donnees = json.loads(contenu)
    except ValueError as exc:
        raise BibleInvalide(f"JSON illisible : {exc}") from exc

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
