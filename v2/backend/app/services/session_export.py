"""Export de fin de culte — le compte rendu, et les diapositives.

Tout est déjà en base à la fin d'un culte : la transcription, le résumé, et
chaque verset projeté avec son horodatage. Rien n'en sortait. Ce module rend
ça exploitable, et il le fait entièrement hors ligne.

Deux formats, deux usages distincts :

  • MARKDOWN — le compte rendu. Il s'archive, il se relit, il se transmet. Et
    c'est lui qu'on dépose dans un outil de synthèse (NotebookLM ou autre) si
    l'église veut en tirer un podcast ou une vidéo. VersePro n'envoie rien
    nulle part : il produit un fichier, l'église décide de son sort.

  • PPTX — les versets du culte en diapositives, réutilisables pour une étude
    biblique, un rappel en semaine, ou l'écran de secours d'un autre logiciel.

Le .pptx est écrit à la main. Un fichier PowerPoint n'est qu'une archive ZIP
de XML, et il n'en faut qu'une mise en page : ajouter une dépendance de
plusieurs mégaoctets au gel PyInstaller pour un seul gabarit coûterait plus
cher que ces quelques dizaines de lignes.

Aucun appel réseau, aucune clé d'API. Un poste sans internet produit les
mêmes fichiers qu'un poste connecté.
"""

from __future__ import annotations

import io
import zipfile
from datetime import datetime
from typing import Any, Dict, List, Optional
from xml.sax.saxutils import escape

# Charte reprise de l'écran de projection : ardoise profonde, blanc cassé
# chaud, laiton pour la référence. Les diapositives sortent avec l'allure du
# logiciel, pas celle d'un gabarit générique.
FOND = "111418"
TEXTE = "F2EFE9"
LAITON = "C8A055"

# 12 192 000 × 6 858 000 EMU = 16:9. L'EMU est l'unité interne d'Office.
LARGEUR, HAUTEUR = 12192000, 6858000


def _horodatage(valeur: Any) -> str:
    """« 2026-07-28T10:14:05 » → « 10:14 ». Tolère l'absence et le format libre."""
    if not valeur:
        return ""
    texte = str(valeur)
    for gabarit in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(texte[:19], gabarit).strftime("%H:%M")
        except ValueError:
            continue
    return ""


# ── Compte rendu ─────────────────────────────────────────────────────────────

def vers_markdown(session: Dict[str, Any], versets: List[Dict[str, Any]]) -> str:
    """Le culte en un document lisible — et déposable dans un outil de synthèse."""
    nom = session.get("name") or "Culte"
    debut = str(session.get("started_at") or "")[:10]
    lignes: List[str] = [f"# {nom}", ""]
    if debut:
        lignes.append(f"*{debut}*")
        lignes.append("")

    duree = session.get("duration_minutes")
    if duree:
        lignes.append(f"Durée : {duree} min · {len(versets)} verset(s) projeté(s)")
        lignes.append("")

    resume = (session.get("summary") or "").strip()
    if resume:
        lignes += ["## Résumé", "", resume, ""]

    if versets:
        lignes += ["## Versets projetés", ""]
        for v in versets:
            heure = _horodatage(v.get("detected_at"))
            tete = f"### {v.get('reference', '?')}"
            lignes.append(f"{tete}  ·  {heure}" if heure else tete)
            lignes.append("")
            texte = (v.get("text") or "").strip()
            if texte:
                lignes += [f"> {texte}", ""]

    transcription = (session.get("transcript") or "").strip()
    if transcription:
        # En dernier : c'est la partie la plus longue, et la moins relue.
        # Elle reste indispensable à un outil de synthèse, qui a besoin du
        # discours entier et pas seulement des versets.
        lignes += ["## Transcription", "", transcription, ""]

    return "\n".join(lignes)


# ── Diapositives ─────────────────────────────────────────────────────────────

def _zone(identifiant: int, nom: str, x: int, y: int, cx: int, cy: int,
          contenu: str, taille: int, couleur: str, gras: bool = False,
          centre: bool = False, italique: bool = False) -> str:
    """Un bloc de texte DrawingML. `taille` est en centièmes de point."""
    alignement = ' algn="ctr"' if centre else ""
    paragraphes = []
    for bloc in (contenu or "").split("\n"):
        paragraphes.append(
            f'<a:p><a:pPr{alignement}/><a:r><a:rPr lang="fr-FR" sz="{taille}" '
            f'b="{1 if gras else 0}" i="{1 if italique else 0}" dirty="0">'
            f'<a:solidFill><a:srgbClr val="{couleur}"/></a:solidFill>'
            f'<a:latin typeface="Helvetica Neue"/></a:rPr>'
            f'<a:t>{escape(bloc)}</a:t></a:r></a:p>'
        )
    return (
        f'<p:sp><p:nvSpPr><p:cNvPr id="{identifiant}" name="{nom}"/>'
        f'<p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>'
        f'<p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
        f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>'
        f'<p:txBody><a:bodyPr wrap="square" anchor="ctr"/><a:lstStyle/>'
        f'{"".join(paragraphes)}</p:txBody></p:sp>'
    )


def _diapositive(reference: str, texte: str, pied: str) -> str:
    """Une diapositive : le verset au centre, sa référence en laiton dessous."""
    corps = _zone(2, "Verset", 914400, 1600200, LARGEUR - 1828800, 2800000,
                  texte, 3200, TEXTE, centre=True)
    ref = _zone(3, "Reference", 914400, 4600000, LARGEUR - 1828800, 700000,
                reference, 2000, LAITON, gras=True, centre=True)
    bas = _zone(4, "Pied", 914400, 5900000, LARGEUR - 1828800, 400000,
                pied, 1100, "6B7280", centre=True, italique=True) if pied else ""
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
        '<p:cSld><p:bg><p:bgPr><a:solidFill>'
        f'<a:srgbClr val="{FOND}"/>'
        '</a:solidFill><a:effectLst/></p:bgPr></p:bg>'
        '<p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/>'
        '</p:nvGrpSpPr><p:grpSpPr/>'
        f'{corps}{ref}{bas}'
        '</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>'
    )


_RELS_RACINE = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
    'relationships/officeDocument" Target="ppt/presentation.xml"/></Relationships>'
)

_THEME = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="VersePro">'
    '<a:themeElements><a:clrScheme name="VersePro">'
    '<a:dk1><a:sysClr val="windowText" lastClr="000000"/></a:dk1>'
    '<a:lt1><a:sysClr val="window" lastClr="FFFFFF"/></a:lt1>'
    '<a:dk2><a:srgbClr val="111418"/></a:dk2><a:lt2><a:srgbClr val="F2EFE9"/></a:lt2>'
    '<a:accent1><a:srgbClr val="C8A055"/></a:accent1><a:accent2><a:srgbClr val="C8A055"/></a:accent2>'
    '<a:accent3><a:srgbClr val="C8A055"/></a:accent3><a:accent4><a:srgbClr val="C8A055"/></a:accent4>'
    '<a:accent5><a:srgbClr val="C8A055"/></a:accent5><a:accent6><a:srgbClr val="C8A055"/></a:accent6>'
    '<a:hlink><a:srgbClr val="C8A055"/></a:hlink><a:folHlink><a:srgbClr val="C8A055"/></a:folHlink>'
    '</a:clrScheme>'
    '<a:fontScheme name="VersePro">'
    '<a:majorFont><a:latin typeface="Helvetica Neue"/><a:ea typeface=""/><a:cs typeface=""/></a:majorFont>'
    '<a:minorFont><a:latin typeface="Helvetica Neue"/><a:ea typeface=""/><a:cs typeface=""/></a:minorFont>'
    '</a:fontScheme>'
    '<a:fmtScheme name="VersePro">'
    '<a:fillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
    '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
    '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:fillStyleLst>'
    '<a:lnStyleLst>'
    '<a:ln w="6350"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln>'
    '<a:ln w="12700"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln>'
    '<a:ln w="19050"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln>'
    '</a:lnStyleLst>'
    '<a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle>'
    '<a:effectStyle><a:effectLst/></a:effectStyle>'
    '<a:effectStyle><a:effectLst/></a:effectStyle></a:effectStyleLst>'
    '<a:bgFillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
    '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
    '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:bgFillStyleLst>'
    '</a:fmtScheme></a:themeElements></a:theme>'
)

_MASTER = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<p:sldMaster xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
    'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
    '<p:cSld><p:bg><p:bgPr><a:solidFill>'
    f'<a:srgbClr val="{FOND}"/>'
    '</a:solidFill><a:effectLst/></p:bgPr></p:bg>'
    '<p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
    '<p:grpSpPr/></p:spTree></p:cSld>'
    '<p:clrMap bg1="dk1" tx1="lt1" bg2="dk2" tx2="lt2" accent1="accent1" accent2="accent2" '
    'accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" '
    'folHlink="folHlink"/>'
    '<p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst>'
    '</p:sldMaster>'
)

_LAYOUT = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<p:sldLayout xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
    'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" type="blank" preserve="1">'
    '<p:cSld name="Verset"><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/>'
    '<p:nvPr/></p:nvGrpSpPr><p:grpSpPr/></p:spTree></p:cSld>'
    '<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>'
)


def vers_pptx(session: Dict[str, Any], versets: List[Dict[str, Any]]) -> bytes:
    """Une diapositive par verset projeté. Renvoie l'archive .pptx complète."""
    nom = session.get("name") or "Culte"
    date = str(session.get("started_at") or "")[:10]
    pied_commun = f"{nom} · {date}".strip(" ·")

    diapos: List[str] = []
    if not versets:
        diapos.append(_diapositive(pied_commun, "Aucun verset projeté", ""))
    for v in versets:
        texte = (v.get("text") or "").strip() or "(texte indisponible)"
        heure = _horodatage(v.get("detected_at"))
        pied = f"{pied_commun} · {heure}" if heure else pied_commun
        diapos.append(_diapositive(str(v.get("reference") or ""), texte, pied))

    n = len(diapos)
    # Les identifiants de diapositive doivent être ≥ 256 : Office rejette
    # silencieusement le fichier en dessous.
    ids = "".join(
        f'<p:sldId id="{256 + i}" r:id="rId{i + 2}"/>' for i in range(n)
    )
    presentation = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
        '<p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>'
        f'<p:sldIdLst>{ids}</p:sldIdLst>'
        f'<p:sldSz cx="{LARGEUR}" cy="{HAUTEUR}"/>'
        f'<p:notesSz cx="{HAUTEUR}" cy="{LARGEUR}"/>'
        '</p:presentation>'
    )
    rels_presentation = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
        'relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/>'
        + "".join(
            f'<Relationship Id="rId{i + 2}" Type="http://schemas.openxmlformats.org/'
            f'officeDocument/2006/relationships/slide" Target="slides/slide{i + 1}.xml"/>'
            for i in range(n)
        )
        + f'<Relationship Id="rId{n + 2}" Type="http://schemas.openxmlformats.org/'
          'officeDocument/2006/relationships/theme" Target="theme/theme1.xml"/>'
        '</Relationships>'
    )
    types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-'
        'officedocument.presentationml.presentation.main+xml"/>'
        '<Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.'
        'openxmlformats-officedocument.presentationml.slideMaster+xml"/>'
        '<Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.'
        'openxmlformats-officedocument.presentationml.slideLayout+xml"/>'
        '<Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-'
        'officedocument.theme+xml"/>'
        + "".join(
            f'<Override PartName="/ppt/slides/slide{i + 1}.xml" ContentType="application/vnd.'
            'openxmlformats-officedocument.presentationml.slide+xml"/>' for i in range(n)
        )
        + '</Types>'
    )

    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", types)
        z.writestr("_rels/.rels", _RELS_RACINE)
        z.writestr("ppt/presentation.xml", presentation)
        z.writestr("ppt/_rels/presentation.xml.rels", rels_presentation)
        z.writestr("ppt/theme/theme1.xml", _THEME)
        z.writestr("ppt/slideMasters/slideMaster1.xml", _MASTER)
        z.writestr(
            "ppt/slideMasters/_rels/slideMaster1.xml.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
            'relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
            'relationships/theme" Target="../theme/theme1.xml"/></Relationships>',
        )
        z.writestr("ppt/slideLayouts/slideLayout1.xml", _LAYOUT)
        z.writestr(
            "ppt/slideLayouts/_rels/slideLayout1.xml.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
            'relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/></Relationships>',
        )
        for i, diapo in enumerate(diapos):
            z.writestr(f"ppt/slides/slide{i + 1}.xml", diapo)
            z.writestr(
                f"ppt/slides/_rels/slide{i + 1}.xml.rels",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/'
                '2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>'
                '</Relationships>',
            )
    return tampon.getvalue()


def nom_fichier(session: Dict[str, Any], extension: str) -> str:
    """« culte-2026-07-28.pptx » — sûr pour un en-tête HTTP et un disque."""
    base = str(session.get("name") or "culte").lower()
    base = "".join(c if c.isalnum() else "-" for c in base).strip("-") or "culte"
    date = str(session.get("started_at") or "")[:10]
    return f"{base}-{date}.{extension}" if date else f"{base}.{extension}"
