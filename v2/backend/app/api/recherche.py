"""Références, recherche biblique (locale et IA), plan de prédication, sémantique, répétition."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List
from loguru import logger
from contextlib import suppress
import asyncio
from collections import OrderedDict
import re

router = APIRouter()


# Modèles Pydantic
class ReferenceRequest(BaseModel):
    """Requête d'envoi de référence"""
    reference: str = Field(..., max_length=200)
    text: Optional[str] = Field(None, max_length=5000)
    version: Optional[str] = Field(None, max_length=50)


class ParseRequest(BaseModel):
    text: str = Field(..., max_length=5000)
    skip_text_search: bool = False


class SemanticSearchRequest(BaseModel):
    text: str = Field(..., max_length=5000)
    top_k: int = 5


class ReferenceResponse(BaseModel):
    """Réponse de référence"""
    success: bool
    reference: str
    message: Optional[str] = None


class TranscriptResponse(BaseModel):
    """Réponse de transcription"""
    text: str
    language: str = "fr"
    confidence: Optional[float] = None


@router.post("/references/send")
async def send_reference(request: ReferenceRequest):
    """
    Envoie manuellement une référence vers TOUS les canaux de projection :
    l'écran autonome local (broadcast WebSocket) et ProPresenter si connecté.

    Utile pour:
    - Validation manuelle avant envoi
    - Correction de référence détectée
    - Envoi direct sans détection audio
    """
    from ..main import output_manager, verse_parser, broadcast_projection

    # Nettoie la ponctuation parasite en début de saisie (ex: ": car Dieu a tant aimé...")
    clean_ref = re.sub(r"^[^\w\s]+", "", request.reference.strip()).strip() or request.reference.strip()

    # Si la saisie est un simple numéro (ex: "21" ou "v.21") et qu'un verset est à l'antenne (ex: Jean 3:16)
    number_match = re.match(r"^(?:v\.?\s*)?(\d+)(?:\s*-\s*(\d+))?$", clean_ref, re.IGNORECASE)
    if number_match and output_manager:
        current_ref = output_manager.get_current_projection().get("reference")
        if current_ref:
            v_match = re.match(r"^(.+?)\s+(\d+):(\d+)", current_ref)
            if v_match:
                book_chap = f"{v_match.group(1)} {v_match.group(2)}"
                start_v = number_match.group(1)
                end_v = number_match.group(2)
                clean_ref = f"{book_chap}:{start_v}-{end_v}" if end_v else f"{book_chap}:{start_v}"

    # Résout la référence pour récupérer le texte du verset
    parsed = None
    if verse_parser:
        parsed = await verse_parser.parse(clean_ref, skip_text_search=True)
        if not parsed and verse_parser.bible_loader:
            # Fallback : si l'utilisateur saisit une citation textuelle ("car Dieu a tant aimé le monde")
            parsed = await asyncio.to_thread(verse_parser.bible_loader.search_by_text, clean_ref)

    if not parsed and not (request.text or "").strip():
        raise HTTPException(
            status_code=422,
            detail=f"Référence biblique invalide : {request.reference}",
        )

    reference = parsed or {
        "reference": request.reference.strip(),
        "text": request.text.strip(),
        "version": request.version,
    }
    projected_text = reference.get("text") or request.text or ""

    # Version demandée explicitement — « le pasteur veut la Semeur ».
    #
    # `parse()` rend TOUJOURS le texte de la version active : sans ce bloc, le
    # champ `version` était accepté puis ignoré. Le panneau de comparaison
    # affichait bien la Semeur, l'opérateur cliquait, l'interface marquait
    # « ★ À l'antenne » — et l'assemblée continuait de lire la Segond. Une
    # fonction qui affirme le contraire de ce qu'elle fait est pire qu'absente.
    demandee = (request.version or "").strip().upper()
    if demandee and verse_parser and parsed:
        loader = verse_parser.bible_loader
        if demandee not in loader.versions:
            raise HTTPException(
                status_code=422,
                detail=f"Version biblique inconnue : {demandee}",
            )
        if demandee != loader.active_version:
            texte_demande = loader.get_verse_text(
                parsed.get("book_abbr"), parsed.get("chapter"),
                parsed.get("verse_start"), parsed.get("verse_end"),
                version_id=demandee,
            )
            # Un verset absent d'une traduction (numérotation différente) ne
            # doit pas vider l'écran : on garde le texte déjà résolu.
            if (texte_demande or "").strip():
                projected_text = texte_demande
                reference = {**reference, "text": texte_demande, "version": demandee}

    if not projected_text.strip():
        raise HTTPException(status_code=422, detail="Aucun texte à projeter")

    active_v = demandee or (reference.get("version") if isinstance(reference, dict) else None)

    # OutputManager diffuse une seule fois vers chaque sortie et renvoie leurs
    # accusés. L'ancienne route envoyait ProPresenter une deuxième fois.
    receipts = await broadcast_projection(
        projected_text,
        reference.get("reference", request.reference),
        translations=reference.get("translations") if isinstance(reference, dict) else None,
        version=active_v,
    )
    browser_sent = bool(receipts.get("browser"))
    if not browser_sent:
        raise HTTPException(status_code=503, detail="Le moteur d'affichage n'a pas confirmé la scène")
    sent_propresenter = bool(receipts.get("propresenter"))

    # ICI, et nulle part ailleurs, un verset devient « projeté ».
    #
    # L'indicateur n'était écrit par aucun code : il valait TRUE parce que
    # c'était le défaut de la colonne. Le rapport de fin de culte annonçait
    # donc autant de projections que de détections — un chiffre que personne
    # n'avait relevé. On l'écrit maintenant au seul moment où il a un sens :
    # quand l'écran a confirmé avoir affiché la scène.
    import app.main as main_module
    if main_module.db_service:
        with suppress(Exception):
            await main_module.db_service.marquer_projete(
                reference.get("reference", request.reference),
                session_id=main_module.current_session_id,
            )

    return {
        "success": browser_sent,
        "reference": reference.get("reference", request.reference),
        "text": projected_text,
        "propresenter_sent": sent_propresenter,
        "outputs": receipts,
        "message": "Verset projeté" + (" (+ ProPresenter)" if sent_propresenter else " (écran autonome)"),
    }


@router.post("/references/parse")
async def parse_reference(request: ParseRequest):
    """
    Parse un texte pour extraire une référence biblique

    Utile pour tester le parser sans audio
    """
    from ..main import verse_parser

    if not verse_parser:
        raise HTTPException(status_code=503, detail="Service parser non disponible")

    reference = await verse_parser.parse(request.text, skip_text_search=request.skip_text_search)

    if reference:
        return {
            "success": True,
            "reference": reference,
            "input_text": request.text
        }
    else:
        return {
            "success": False,
            "reference": None,
            "input_text": request.text,
            "message": "Aucune référence détectée"
        }


# Dernières recherches locales, reprises par /bible/search/ia pour ne pas
# refaire deux fois le même calcul quand la palette demande l'avis de l'IA.
_RECHERCHES_RECENTES: "OrderedDict[tuple, list]" = OrderedDict()


def _normaliser_requete(q: str) -> str:
    return (re.sub(r"^[^\w\s]+", "", q.strip()).strip() or q.strip())[:5000]


@router.get("/bible/search")
async def bible_search(q: str, limit: int = 6):
    """
    Recherche unifiée pour la palette de commande :
    référence explicite (Jn 3:16, "rom 8 28"), début de texte, citation approximative.
    Renvoie plusieurs candidats avec texte et score, sans rien projeter.

    JAMAIS D'IA ICI. Cette route sert aussi à relire le texte d'un verset avant
    de le projeter ou de l'ajouter au déroulé (« Jean 3:16 », limit=1). Elle
    attendait l'assistant jusqu'à 5 s à chaque appel — mesuré : 3,15 s pour
    « Jean 3:16 » avec une IA qui répond en 3 s, et 4 à 5 s quand les crédits
    OpenRouter sont épuisés. Pire : sa réponse était ajoutée APRÈS une liste
    locale d'au moins douze résultats, puis coupée à `limit`. Même pour
    « zzz qwx blorp », elle n'a jamais été affichée. On attendait pour rien.
    L'avis de l'IA passe désormais par /bible/search/ia, demandé à part.
    """
    from ..main import verse_parser, semantic_service
    from ..services.verse_parser import format_reference

    if not verse_parser or not q or not q.strip():
        return {"results": []}

    limit = min(max(int(limit), 1), 20)
    query = _normaliser_requete(q)
    results = []
    seen = set()

    # 1. Référence explicite (avec texte du verset)
    explicit = await verse_parser.parse(query, skip_text_search=True)
    if explicit:
        key = explicit["reference"]
        seen.add(key)
        results.append(explicit)
        # « Samuel 16 7 » : 1 Samuel en tête, 2 Samuel juste dessous.
        for alternative in explicit.get("alternatives") or []:
            autre = await verse_parser.parse(alternative, skip_text_search=True)
            if autre and autre["reference"] not in seen:
                autre["confidence"] = explicit["confidence"]
                seen.add(autre["reference"])
                results.append(autre)
        # Propose aussi les 2 versets suivants (lecture de passage)
        if explicit.get("verse_start") is not None:
            for offset in (1, 2):
                v = explicit["verse_start"] + offset
                text = verse_parser.bible_loader.get_verse_text(explicit["book_abbr"], explicit["chapter"], v)
                if text:
                    adjacent = {
                        "reference": format_reference(explicit["book_abbr"], explicit["chapter"], v),
                        "book_abbr": explicit["book_abbr"],
                        "chapter": explicit["chapter"],
                        "verse_start": v,
                        "text": text,
                        "detection_method": "adjacent",
                        "confidence": 0.5,
                    }
                    seen.add(adjacent["reference"])
                    results.append(adjacent)

    # 2. Lexical local + sémantique ONNX, en parallèle. Deux lettres suffisent.
    if len(query) >= 2:
        manual_task = asyncio.to_thread(
            verse_parser.bible_loader.search_manual_candidates, query, max(limit * 2, 12)
        )
        semantic_task = None
        if semantic_service and semantic_service.initialized and len(query.split()) >= 2:
            index_manuel = getattr(verse_parser.bible_loader, "manual_index", None)
            if index_manuel is not None:
                # Cosinus + mots rares : voir services/recherche_description.py.
                from ..services.recherche_description import classeur_pour
                semantic_task = asyncio.to_thread(
                    classeur_pour(semantic_service, index_manuel).classer, query, max(limit * 2, 12)
                )
            else:
                semantic_task = asyncio.to_thread(
                    semantic_service.search_manual, query, max(limit * 2, 12)
                )

        manual_res, semantic_res = await asyncio.gather(
            manual_task,
            semantic_task if semantic_task else asyncio.sleep(0, result=[]),
            return_exceptions=True,
        )

        manual_candidates = manual_res if isinstance(manual_res, list) else []
        semantic_candidates = semantic_res if isinstance(semantic_res, list) else []

        # LE CLASSEMENT SE FAIT AU SCORE, PAS À LA PROVENANCE.
        fusion = sorted(
            [*manual_candidates, *semantic_candidates],
            key=lambda c: float(c.get("score") or c.get("confidence") or 0),
            reverse=True,
        )
        for cand in fusion:
            key = cand.get("reference") or (
                f"{cand.get('book_abbr')} {cand.get('chapter')}:{cand.get('verse_start') or cand.get('verse')}"
            )
            if key in seen:
                continue
            if not cand.get("reference") and cand.get("verse") is not None:
                from ..services.verse_parser import format_reference
                cand = dict(cand)
                cand["verse_start"] = cand.get("verse")
                cand["reference"] = format_reference(
                    cand.get("book_abbr"), cand.get("chapter"), cand.get("verse")
                )
                cand["translations"] = verse_parser.bible_loader.translations_for(
                    cand.get("book_abbr"), cand.get("chapter"), cand.get("verse")
                )
            elif not cand.get("translations") and cand.get("verse_start") is not None:
                cand = dict(cand)
                cand["translations"] = verse_parser.bible_loader.translations_for(
                    cand.get("book_abbr"), cand.get("chapter"), cand.get("verse_start")
                )
            seen.add(cand["reference"])
            results.append(cand)

    _RECHERCHES_RECENTES[(query, limit)] = results[:limit]
    _RECHERCHES_RECENTES.move_to_end((query, limit))
    while len(_RECHERCHES_RECENTES) > 32:
        _RECHERCHES_RECENTES.popitem(last=False)
    return {"results": results[:limit]}


def fusionner_suggestion_ia(resultats: list, suggestion: Optional[dict], limit: int) -> list:
    """Place la proposition vérifiée de l'IA EN TÊTE, sans rien perdre du local.

    En tête parce qu'elle a été mesurée plus juste que le premier résultat local
    sur les descriptions (40/45 contre 36/45) ; déjà présente dans la liste,
    elle y remonte et le local la confirme. Le reste garde son ordre.
    """
    if not suggestion:
        return resultats[:limit]
    reference = suggestion["reference"]
    deja = next((r for r in resultats if r.get("reference") == reference), None)
    tete = dict(deja) if deja else dict(suggestion)
    tete["ia_confirme"] = bool(deja)
    reste = [r for r in resultats if r.get("reference") != reference]
    return [tete, *reste][:limit]


@router.get("/bible/search/ia")
async def bible_search_ia(q: str, limit: int = 6):
    """L'avis de l'assistant sur une DESCRIPTION, demandé à part par la palette.

    La palette affiche d'abord /bible/search (instantané), puis remplace la
    liste par celle-ci quand elle arrive. Une référence explicite n'a pas
    besoin d'IA ; la proposition est toujours relue dans la Bible locale, et
    un verset inexistant est écarté.
    """
    from ..main import verse_parser, ai_service

    limit = min(max(int(limit), 1), 20)
    query = _normaliser_requete(q or "")
    if not verse_parser or not query:
        return {"results": [], "ia": "indisponible"}
    locaux = _RECHERCHES_RECENTES.get((query, limit))
    if locaux is None:
        locaux = (await bible_search(query, limit))["results"]
    if await verse_parser.parse(query, skip_text_search=True):
        return {"results": locaux, "ia": "inutile"}
    if not ai_service or not getattr(ai_service, "enabled", False) or len(query.split()) < 2:
        return {"results": locaux, "ia": "indisponible"}

    try:
        # Rien n'attend cette réponse à l'écran : la palette montre déjà le
        # local. 12 s laissent un modèle 8B se charger au premier appel.
        proposition = await asyncio.wait_for(ai_service.trouver_passage_decrit(query), timeout=12.0)
    except Exception as exc:
        logger.warning(f"Recherche IA sans réponse pour {query!r} : {exc}")
        return {"results": locaux, "ia": "sans_reponse"}

    verifiee = None
    if proposition and proposition.get("reference"):
        lue = await verse_parser.parse(proposition["reference"], skip_text_search=True)
        if lue and lue.get("verse_start") is not None and (lue.get("text") or "").strip():
            verifiee = dict(lue)
            verifiee.update({
                "detection_method": "ai_suggestion",
                "source": "ai",
                "requires_review": True,
                # L'IA répond de 0 à 100. `min(40, 0.95)` affichait 95 % pour
                # une proposition donnée à 40 %.
                "confidence": round(min(max(float(proposition.get("confidence") or 0), 0.0), 95.0) / 100, 2),
                "explanation": "Proposition de l'assistant, vérifiée dans la Bible locale. À relire avant projection.",
            })
    return {
        "results": fusionner_suggestion_ia(locaux, verifiee, limit),
        "ia": "proposee" if verifiee else "aucune",
    }


class ExtractReferencesRequest(BaseModel):
    text: str


class PlanRequest(BaseModel):
    references: List[str] = Field(default_factory=list)


@router.post("/plan")
async def definir_plan_predication(request: PlanRequest):
    """Transmet au moteur le déroulé préparé avant le culte.

    Ce déroulé existait déjà — Paramètres → Avancé extrait les références des
    notes du pasteur — mais il restait dans le navigateur. Le moteur traitait
    donc un verset annoncé par écrit comme un verset jamais vu.

    C'est pourtant la seule information du système antérieure au culte, donc
    la seule qui ne dépende pas de ce que le micro a cru entendre.
    """
    from ..main import reference_engine
    if not reference_engine:
        raise HTTPException(status_code=503, detail="Moteur de détection indisponible")
    compte = await reference_engine.definir_plan(request.references)
    return {"status": "ok", "count": compte}


@router.post("/bibles/extract_references")
async def extract_references_from_text(request: ExtractReferencesRequest):
    """
    Extrait toutes les références bibliques d'un texte (ex: notes de sermon du pasteur).
    Scanne le texte ligne par ligne et par sous-phrases.
    """
    from ..main import verse_parser
    import re
    if not verse_parser or not request.text:
        return {"references": [], "count": 0}

    extracted = []
    seen = set()
    for line in request.text.splitlines():
        references = await verse_parser.parse(line, skip_text_search=True, collect_all=True)
        for ref in references:
            if ref.get("verse_start") and ref["reference"] not in seen:
                seen.add(ref["reference"])
                extracted.append(ref)

    return {"references": extracted, "count": len(extracted)}


class RehearseRequest(BaseModel):
    transcript: str


@router.post("/rehearse")
async def rehearse(request: RehearseRequest):
    """
    Mode répétition : rejoue un transcript complet dans la chaîne de détection
    (fenêtres glissantes de mots, comme en direct) SANS rien projeter.
    Permet de valider la reconnaissance avant le culte.
    """
    # La cascade vit désormais dans BibleReferenceEngine : on passe par le
    # moteur pour rejouer EXACTEMENT ce que fait le direct, VerseGraph et
    # mesure de santé compris. Un rejeu qui court-circuiterait le moteur ne
    # vaudrait rien comme répétition.
    from ..main import verse_parser, reference_engine

    if not verse_parser:
        raise HTTPException(status_code=503, detail="Parser non disponible")
    if not reference_engine:
        raise HTTPException(status_code=503, detail="Moteur de détection non disponible")

    words = request.transcript.split()
    detections = []
    seen = set()

    # Rejoue EXACTEMENT la cascade du direct (explicite + fusion hybride des
    # paraphrases), fenêtre par fenêtre. Chaque fin de fenêtre est un « final ».
    for end in range(6, len(words) + 1, 3):
        window = " ".join(words[max(0, end - 40):end])
        ref = await reference_engine.detecter_sans_effet(window, final_state=True)
        if ref and ref["reference"] not in seen:
            seen.add(ref["reference"])
            detections.append({
                "reference": ref["reference"],
                "text": ref.get("text", ""),
                "detection_method": ref.get("detection_method"),
                "confidence": ref.get("confidence"),
                "fusion": ref.get("fusion"),
                "window": window[-90:],
            })

    return {"detections": detections, "total": len(detections)}


@router.get("/bible/chapter")
async def lire_chapitre(q: str, version: str = ""):
    """Renvoie tous les versets d'un chapitre, avec leur nombre.

    ChapterModal appelait déjà cette route — qui n'existait pas. Elle prenait
    un 404 et retombait silencieusement sur /bible/search, c'est-à-dire sur
    une recherche plafonnée à 50 résultats au lieu du chapitre demandé.

    Le nombre de versets est ce qui permet de savoir qu'on est au DERNIER
    verset d'un chapitre : sans lui, une bande de contexte ne peut pas se
    décaler quand elle bute sur la fin.
    """
    from ..main import verse_parser
    if not verse_parser or not q:
        raise HTTPException(status_code=503, detail="Parseur indisponible")

    analyse = await verse_parser.parse(q, skip_text_search=True)
    if not analyse:
        # « Jean 3 » ne se parse pas seul : les motifs exigent « chapitre » ou
        # un verset. C'est pourtant la forme naturelle pour demander un
        # chapitre — on réessaie sous celle que le parseur reconnaît.
        analyse = await verse_parser.parse(
            re.sub(r"^(.*?)\s+(\d+)$", r"\1 chapitre \2", q.strip()),
            skip_text_search=True,
        )
    if not analyse or not analyse.get("book_abbr") or not analyse.get("chapter"):
        raise HTTPException(status_code=404, detail=f"Chapitre introuvable : {q}")

    loader = verse_parser.bible_loader
    version_id = (version or loader.active_version or "").upper()
    edition = loader.versions.get(version_id) or loader.versions.get(loader.active_version)
    if not edition:
        raise HTTPException(status_code=503, detail="Aucune édition biblique chargée")

    livre = edition.get(analyse["book_abbr"].lower()) or {}
    versets = livre.get(analyse["chapter"]) or {}
    if not versets:
        raise HTTPException(
            status_code=404,
            detail=f"{analyse['book_abbr']} {analyse['chapter']} absent de {version_id}",
        )

    return {
        "book": analyse.get("book"),
        "book_abbr": analyse.get("book_abbr"),
        "chapter": analyse["chapter"],
        "version": version_id,
        "count": len(versets),
        "verses": [
            {"verse": int(num), "text": texte}
            for num, texte in sorted(versets.items(), key=lambda kv: int(kv[0]))
        ],
    }


@router.get("/semantic/status")
async def get_semantic_status():
    from ..main import semantic_service
    return semantic_service.status() if semantic_service else {"enabled": False, "installed": False}


@router.post("/semantic/prepare")
async def prepare_semantic_index():
    """Installe le modele ONNX et indexe le corpus biblique en arriere-plan."""
    from ..main import semantic_service
    if not semantic_service:
        raise HTTPException(status_code=503, detail="Service semantique indisponible")
    import threading
    if not semantic_service.indexing:
        threading.Thread(
            target=semantic_service.initialize,
            kwargs={"allow_download": True},
            daemon=True,
        ).start()
    return {"status": "preparing", **semantic_service.status()}


@router.post("/semantic/search")
async def semantic_search(request: SemanticSearchRequest):
    from ..main import semantic_service
    if not semantic_service or not semantic_service.initialized:
        raise HTTPException(status_code=503, detail="Index semantique non prepare")
    import asyncio
    results = await asyncio.to_thread(semantic_service.search, request.text, min(max(request.top_k, 1), 10))
    return {"results": results}
