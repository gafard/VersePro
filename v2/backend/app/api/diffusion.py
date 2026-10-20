"""Commande de l'écran : projection, préparation, télécommande, ProPresenter."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from loguru import logger

router = APIRouter()


class AnnotationRequest(BaseModel):
    annotations: list[dict]


@router.post("/projection/annotation")
async def send_projection_annotation(request: AnnotationRequest):
    """
    Envoie les annotations et surlignages en temps réel sur la projection.
    """
    from ..main import broadcast_output_event
    await broadcast_output_event({
        "type": "annotation",
        "annotations": request.annotations
    })
    return {"status": "ok", "count": len(request.annotations)}


@router.get("/propresenter/status")
async def propresenter_status():
    """Récupère le statut de ProPresenter"""
    from ..main import output_manager

    if not output_manager or "propresenter" not in output_manager.outputs:
        raise HTTPException(status_code=503, detail="Service non disponible")

    pp_driver = output_manager.outputs["propresenter"]

    return {
        "connected": await pp_driver.is_connected(),
        "status": {"enabled": pp_driver.enabled},
        "stats": getattr(pp_driver, "stats", {})
    }


@router.post("/propresenter/clear")
async def clear_display():
    """Efface l'affichage ProPresenter"""
    from ..main import output_manager

    if not output_manager or "propresenter" not in output_manager.outputs:
        raise HTTPException(status_code=503, detail="Service non disponible")

    pp_driver = output_manager.outputs["propresenter"]
    cleared = await pp_driver.clear()

    return {
        "success": cleared,
        "message": "Affichage effacé" if cleared else "Échec de l'effacement"
    }


# ── HTTP CONTROL API (STREAM DECK / PHYSICAL CONTROLLERS) ──

class ControlProjectRequest(BaseModel):
    reference: str
    text: Optional[str] = None
    version: Optional[str] = None

@router.post("/control/project")
async def control_project(req: ControlProjectRequest):
    """Projette une référence directement à l'antenne à distance"""
    from ..main import output_manager, verse_parser, broadcast_projection

    parsed = None
    if verse_parser:
        parsed = await verse_parser.parse(req.reference)

    ref_name = parsed.get("reference") if parsed else req.reference
    ref_text = parsed.get("text") if parsed else (req.text or "")
    translations = parsed.get("translations") if parsed else None

    await broadcast_projection(ref_text, ref_name, translations=translations)
    if output_manager:
        await output_manager.project(ref_text, ref_name, translations=translations)

    return {
        "success": True,
        "reference": ref_name,
        "text": ref_text
    }

@router.post("/control/clear")
async def control_clear():
    """Efface toutes les projections de l'écran (black screen)"""
    from ..main import output_manager, broadcast_projection
    await broadcast_projection("", "")
    if output_manager:
        await output_manager.clear()
    return {"success": True}

@router.post("/control/next")
async def control_next():
    """Navigue vers le verset suivant dans le passage en cours"""
    from ..main import output_manager, broadcast_projection, current_projection_slide
    if current_projection_slide and current_projection_slide.get("next_reference"):
        next_ref = current_projection_slide["next_reference"]
        next_text = current_projection_slide["next_text"]
        await broadcast_projection(next_text, next_ref)
        if output_manager:
            await output_manager.project(next_text, next_ref)
        return {"success": True, "reference": next_ref, "text": next_text}
    return {"success": False, "detail": "Aucun verset suivant disponible"}

@router.post("/control/prev")
async def control_prev():
    """Navigue vers le verset précédent dans le passage en cours"""
    from ..main import output_manager, broadcast_projection, current_projection_slide, verse_parser
    ref = current_projection_slide.get("reference")
    if ref and verse_parser:
        try:
            parsed = await verse_parser.parse(ref, skip_text_search=True)
            if parsed and parsed.get("verse_start") is not None:
                prev_v = parsed["verse_start"] - 1
                if prev_v > 0:
                    prev_text = verse_parser.bible_loader.get_verse_text(parsed["book_abbr"], parsed["chapter"], prev_v)
                    if prev_text:
                        # Nom complet, comme partout à l'écran : l'abréviation
                        # affichait « Jn 3:16 » après un retour arrière.
                        from ..services.verse_parser import format_reference
                        prev_ref = format_reference(parsed["book_abbr"], parsed["chapter"], prev_v)
                        await broadcast_projection(prev_text, prev_ref)
                        if output_manager:
                            await output_manager.project(prev_text, prev_ref)
                        return {"success": True, "reference": prev_ref, "text": prev_text}
        except Exception as exc:
            # Une télécommande qui ne fait rien doit au moins laisser une trace.
            logger.warning(f"Verset précédent impossible depuis {ref!r} : {exc}")
    return {"success": False, "detail": "Aucun verset précédent disponible"}


@router.get("/control/status")
async def control_status():
    """Renvoie l'état courant de la projection"""
    from ..main import current_projection_slide
    return {
        "on_air": bool(current_projection_slide.get("reference")),
        "reference": current_projection_slide.get("reference", ""),
        "text": current_projection_slide.get("text", ""),
        "next_reference": current_projection_slide.get("next_reference", ""),
        "next_text": current_projection_slide.get("next_text", "")
    }


# ── Préparation et envoi à l'antenne (preview / program) ─────────────────────
#
# Le geste fondamental d'une régie : monter l'écran suivant, LE VOIR, puis
# l'envoyer. Avant ces routes, valider une détection l'envoyait directement
# devant l'assemblée — l'opérateur découvrait le rendu en même temps qu'elle,
# et n'avait aucun moyen de rattraper un verset mal coupé ou un habillage
# inadapté.

class PreviewRequest(BaseModel):
    reference: str
    text: Optional[str] = None
    version: Optional[str] = None


@router.post("/projection/preview")
async def preparer(request: PreviewRequest):
    """Monte une référence en préparation. N'atteint AUCUN écran de salle."""
    from ..main import preparer_projection, verse_parser

    if not verse_parser:
        raise HTTPException(status_code=503, detail="Parser non disponible")

    parsed = await verse_parser.parse(request.reference, skip_text_search=True)
    if not parsed and not (request.text or "").strip():
        raise HTTPException(
            status_code=422,
            detail=f"Référence biblique invalide : {request.reference}",
        )

    texte = (parsed or {}).get("text") or request.text or ""
    demandee = (request.version or "").strip().upper()
    if demandee and parsed:
        loader = verse_parser.bible_loader
        if demandee not in loader.versions:
            raise HTTPException(status_code=422,
                                detail=f"Version biblique inconnue : {demandee}")
        autre = loader.get_verse_text(parsed.get("book_abbr"), parsed.get("chapter"),
                                      parsed.get("verse_start"), parsed.get("verse_end"),
                                      version_id=demandee)
        if (autre or "").strip():
            texte = autre

    scene = await preparer_projection(
        texte,
        (parsed or {}).get("reference") or request.reference.strip(),
        translations=(parsed or {}).get("translations"),
    )
    return {"success": True, **{k: scene.get(k) for k in ("reference", "text", "verses")}}


@router.get("/projection/preview")
async def lire_preparation():
    """Ce qui est actuellement monté, sans l'envoyer."""
    from ..main import preview_slide
    return preview_slide or {}


@router.post("/projection/take")
async def envoyer_a_l_antenne():
    """Envoie la préparation à l'antenne — le « take » d'une régie."""
    from ..main import envoyer_preparation, preview_slide

    if not (preview_slide.get("reference") or preview_slide.get("text")):
        raise HTTPException(status_code=409, detail="Aucune préparation à envoyer")
    receipts = await envoyer_preparation()
    if not (receipts or {}).get("browser"):
        raise HTTPException(status_code=503,
                            detail="Le moteur d'affichage n'a pas confirmé la scène")
    return {"success": True, "reference": preview_slide.get("reference"),
            "outputs": receipts}
