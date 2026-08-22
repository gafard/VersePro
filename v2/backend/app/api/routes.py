"""
Routes API REST pour VersePro v2
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from loguru import logger
from contextlib import suppress
import asyncio
import re

router = APIRouter()


SECRET_SETTING_KEYS = {"deepgram_api_key", "openrouter_api_key", "gemini_api_key"}


def _mask_secret(value: str) -> str:
    """Expose only a short hint so API keys never leave the backend in clear text."""
    if not value:
        return ""
    if len(value) <= 8:
        return "configured"
    return f"{value[:4]}...{value[-4:]}"


def _redact_update(update: Dict[str, Any]) -> Dict[str, Any]:
    """Keep settings logs useful without leaking credentials."""
    redacted = dict(update)
    for key in SECRET_SETTING_KEYS:
        if key in redacted:
            redacted[key] = _mask_secret(str(redacted[key] or ""))
    return redacted


# Modèles Pydantic
class ReferenceRequest(BaseModel):
    """Requête d'envoi de référence"""
    reference: str = Field(..., max_length=200)
    text: Optional[str] = Field(None, max_length=5000)
    version: Optional[str] = Field(None, max_length=50)


class ParseRequest(BaseModel):
    text: str = Field(..., max_length=5000)
    skip_text_search: bool = False


class SettingsUpdate(BaseModel):
    auto_send: Optional[bool] = None
    bible_version: Optional[str] = None
    propresenter_host: Optional[str] = None
    propresenter_port: Optional[int] = None
    propresenter_message_name: Optional[str] = None
    overlay_zones: Optional[Any] = None
    overlay_shapes: Optional[Any] = None
    ndi_enabled: Optional[bool] = None
    ndi_source_name: Optional[str] = None
    deepgram_model: Optional[str] = None
    deepgram_language: Optional[str] = None
    ai_agent_enabled: Optional[bool] = None
    deepgram_api_key: Optional[str] = None
    openrouter_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    ai_confidence_threshold: Optional[int] = None
    ai_filtering_mode: Optional[str] = None
    asr_default_engine: Optional[str] = None
    local_semantic_enabled: Optional[bool] = None
    local_semantic_threshold: Optional[float] = None
    projection_theme: Optional[str] = None
    projection_style: Optional[str] = None
    show_bible_version: Optional[bool] = None
    dual_translations: Optional[str] = None
    sunday_safe_mode: Optional[bool] = None
    shadow_mode: Optional[bool] = None


class PrepareModelRequest(BaseModel):
    model: Optional[str] = None


class SemanticSearchRequest(BaseModel):
    text: str = Field(..., max_length=5000)
    top_k: int = 5


class OverlayImageRequest(BaseModel):
    """PNG de l'habillage, en data-URL ou base64 nu."""
    data: str


class BibleImportRequest(BaseModel):
    """Contenu JSON d'une traduction, et le sigle sous lequel l'installer."""
    content: str = Field(..., max_length=10_000_000)  # max ~10MB JSON string
    version_id: Optional[str] = Field("", max_length=50)


class OverlayPresetRequest(BaseModel):
    """Enregistrement d'un habillage dans la bibliothèque."""
    name: str = Field(..., max_length=100)
    category: Optional[str] = Field("Mes habillages", max_length=100)
    # Absents : on enregistre l'habillage tel qu'il est déjà en base.
    zones: Optional[Any] = None
    shapes: Optional[Any] = None


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


class HealthResponse(BaseModel):
    """Réponse de santé"""
    status: str
    version: str
    services: Dict[str, bool]


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Endpoint de santé"""
    from ..main import output_manager, deepgram_service, verse_parser

    propresenter_connected = False
    if output_manager and "propresenter" in output_manager.outputs:
        propresenter_connected = await output_manager.outputs["propresenter"].is_connected()

    return {
        "status": "healthy",
        "version": "2.1.8",
        "services": {
            "deepgram": deepgram_service is not None,
            "propresenter": propresenter_connected,
            "parser": verse_parser is not None
        }
    }


@router.get("/preflight")
async def preflight_check(probe_cloud: bool = False):
    """Contrôle opérationnel avant le direct, sans déclencher de téléchargement."""
    import asyncio
    import shutil
    from ..core.config import DATA_DIR, settings
    from ..main import (
        db_service,
        deepgram_service,
        output_manager,
        semantic_service,
        verse_parser,
        vosk_service,
        nemotron_service,
    )
    from ..services.secret_store import secret_store

    disk = shutil.disk_usage(DATA_DIR)
    local_asr = bool(
        (nemotron_service and nemotron_service.is_ready and nemotron_service.runtime_available)
        or (vosk_service and vosk_service.initialized)
    )
    cloud_configured = bool(settings.DEEPGRAM_API_KEY)
    cloud_verified = False
    cloud_error = ""
    if probe_cloud and cloud_configured and deepgram_service and deepgram_service.client:
        session = None
        async def ignore_probe_message(_):
            return None
        try:
            session = await asyncio.wait_for(
                deepgram_service.create_session(ignore_probe_message),
                timeout=5.0,
            )
            cloud_verified = bool(session.is_active)
        except Exception as exc:
            cloud_error = type(exc).__name__
        finally:
            if session:
                await session.close()

    browser = output_manager.outputs.get("browser") if output_manager else None
    browser_output = False
    browser_clients = 0
    if browser:
        try:
            browser_output = bool(await browser.send_scene(dict(browser.current_scene)))
            browser_clients = len(browser.connections)
        except Exception:
            browser_output = False

    configured_outputs = []
    if output_manager:
        for name, output in output_manager.outputs.items():
            if name == "browser" or not output.enabled:
                continue
            try:
                connected = bool(await output.is_connected())
            except Exception:
                connected = False
            configured_outputs.append((name, connected))

    cloud_ready = cloud_verified if probe_cloud else cloud_configured
    models_need_space = not local_asr or not bool(semantic_service and semantic_service.initialized)
    required_free = (4 if models_need_space else 1) * 1024 ** 3
    cloud_detail = (
        "Deepgram vérifié"
        if cloud_verified
        else f"Deepgram inaccessible ({cloud_error})"
        if probe_cloud and cloud_configured
        else "Deepgram configuré, test au démarrage du micro"
        if cloud_configured
        else ""
    )
    output_detail = (
        f"Moteur prêt · {browser_clients} écran(s) connecté(s)"
        if browser_output
        else "Le moteur d'affichage ne répond pas"
    )
    if configured_outputs:
        summary = ", ".join(f"{name}: {'prêt' if ok else 'indisponible'}" for name, ok in configured_outputs)
        output_detail = f"{output_detail} · {summary}"

    checks = [
        {"id": "database", "label": "Base locale", "ok": bool(db_service and db_service.db), "critical": True},
        {"id": "bible", "label": "Corpus biblique", "ok": bool(verse_parser and verse_parser.bible_loader.versions), "critical": True},
        {"id": "asr", "label": "Transcription", "ok": cloud_ready or local_asr, "critical": True,
         "detail": cloud_detail or ("Nemotron/Vosk prêt" if local_asr else "Préparer Nemotron/Vosk ou ajouter une clé Deepgram")},
        {"id": "output", "label": "Moteur de sortie", "ok": browser_output, "critical": True,
         "detail": output_detail},
        {"id": "configured_outputs", "label": "Sorties activées",
         "ok": all(ok for _, ok in configured_outputs), "critical": False,
         "detail": "Toutes prêtes" if all(ok for _, ok in configured_outputs) else "Une sortie optionnelle est indisponible"},
        {"id": "semantic", "label": "Recherche sémantique locale", "ok": bool(semantic_service and semantic_service.initialized), "critical": False},
        {"id": "disk", "label": "Espace disque", "ok": disk.free >= required_free, "critical": True,
         "detail": f"{disk.free / (1024 ** 3):.1f} Go libres · {required_free / (1024 ** 3):.0f} Go requis"},
        {"id": "secrets", "label": "Trousseau système", "ok": secret_store.available, "critical": False},
    ]
    return {
        "ready": all(item["ok"] for item in checks if item["critical"]),
        "checks": checks,
        "safety": {
            "sunday_safe_mode": settings.SUNDAY_SAFE_MODE,
            "shadow_mode": settings.SHADOW_MODE,
            "auto_send": settings.PROPRESENTER_AUTO_SEND,
        },
    }


def _get_local_ip() -> str:
    """Détecte l'adresse IP locale LAN de la machine pour le partage de l'écran mobile."""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


@router.get("/network/info")
async def get_network_info():
    """Renvoie les coordonnées réseau locales pour la connexion des téléphones mobiles (/follow, /stage)."""
    from ..core.config import settings
    ip = _get_local_ip()
    port = getattr(settings, "PORT", 8000)
    base_url = f"http://{ip}:{port}"
    return {
        "local_ip": ip,
        "port": port,
        "base_url": base_url,
        "follow_url": f"{base_url}/follow",
        "stage_url": f"{base_url}/stage",
        "output_url": f"{base_url}/output",
    }


@router.post("/safety/panic")
async def activate_panic_mode():
    """Coupe les automatismes et efface immédiatement toutes les sorties."""
    from ..core.config import settings
    from ..services.database import get_database
    from ..main import broadcast_projection
    settings.PROPRESENTER_AUTO_SEND = False
    settings.SUNDAY_SAFE_MODE = True
    settings.SHADOW_MODE = False
    db = get_database()
    await db.set_setting("auto_send", False)
    await db.set_setting("sunday_safe_mode", True)
    await db.set_setting("shadow_mode", False)
    receipts = await broadcast_projection("", "")
    return {
        "status": "safe",
        "auto_send": False,
        "sunday_safe_mode": True,
        "shadow_mode": False,
        "screen_cleared": bool(receipts.get("browser")),
        "outputs": receipts,
    }


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


@router.get("/bible/search")
async def bible_search(q: str, limit: int = 6):
    """
    Recherche unifiée pour la palette de commande :
    référence explicite (Jn 3:16, "rom 8 28"), début de texte, citation approximative.
    Renvoie plusieurs candidats avec texte et score, sans rien projeter.
    """
    from ..main import verse_parser, semantic_service

    if not verse_parser or not q or not q.strip():
        return {"results": []}

    limit = min(max(int(limit), 1), 20)
    query = (re.sub(r"^[^\w\s]+", "", q.strip()).strip() or q.strip())[:5000]
    results = []
    seen = set()

    # 1. Référence explicite (avec texte du verset)
    explicit = await verse_parser.parse(query, skip_text_search=True)
    if explicit:
        key = explicit["reference"]
        seen.add(key)
        results.append(explicit)
        # Propose aussi les 2 versets suivants (lecture de passage)
        if explicit.get("verse_start") is not None:
            for offset in (1, 2):
                v = explicit["verse_start"] + offset
                text = verse_parser.bible_loader.get_verse_text(explicit["book_abbr"], explicit["chapter"], v)
                if text:
                    adjacent = {
                        "reference": f"{explicit['book_abbr']} {explicit['chapter']}:{v}",
                        "book_abbr": explicit["book_abbr"],
                        "chapter": explicit["chapter"],
                        "verse_start": v,
                        "text": text,
                        "detection_method": "adjacent",
                        "confidence": 0.5,
                    }
                    seen.add(adjacent["reference"])
                    results.append(adjacent)

    # 2. Recherche concurrente en parallèle : Lexical local + Sémantique ONNX + IA Assistant
    # Deux lettres suffisent pour lancer la recherche locale ;
    # Dès 2 mots, l'IA et l'index sémantique s'exécutent en parallèle immédiat sans attendre.
    if len(query) >= 2:
        from ..main import ai_service

        manual_task = asyncio.to_thread(
            verse_parser.bible_loader.search_manual_candidates, query, max(limit * 2, 12)
        )
        semantic_task = None
        if semantic_service and semantic_service.initialized and len(query.split()) >= 2:
            semantic_task = asyncio.to_thread(
                semantic_service.search_manual, query, max(limit * 2, 12)
            )

        ai_task = None
        if ai_service and getattr(ai_service, "enabled", False) and len(query.split()) >= 2:
            ai_task = ai_service.detect_bible_reference(
                query,
                candidates=None,
                exiger_candidats=False,
            )

        async def run_ai():
            if not ai_task:
                return None
            try:
                return await asyncio.wait_for(ai_task, timeout=5.0)
            except Exception:
                return None

        manual_res, semantic_res, ai_suggestion = await asyncio.gather(
            manual_task,
            semantic_task if semantic_task else asyncio.sleep(0, result=[]),
            run_ai(),
            return_exceptions=True,
        )

        manual_candidates = manual_res if isinstance(manual_res, list) else []
        semantic_candidates = semantic_res if isinstance(semantic_res, list) else []
        ai_suggestion = ai_suggestion if isinstance(ai_suggestion, dict) else None

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

        # Intégration de la proposition IA (concurrente, vérifiée dans la Bible locale)
        if ai_suggestion:
            ref_ia = (ai_suggestion or {}).get("reference")
            if ref_ia and ref_ia not in seen:
                confirme = await verse_parser.parse(ref_ia, skip_text_search=True)
                if confirme and confirme.get("verse_start") is not None:
                    confirme = dict(confirme)
                    confirme["detection_method"] = "ai_suggestion"
                    confirme["source"] = "ai"
                    confirme["requires_review"] = True
                    confirme["confidence"] = min(
                        float(ai_suggestion.get("confidence") or 0.7), 0.95
                    )
                    confirme["explanation"] = (
                        "Proposition de l'assistant, vérifiée dans la Bible locale. "
                        "À relire avant projection."
                    )
                    seen.add(confirme["reference"])
                    # Si les résultats locaux étaient faibles (< 0.75), l'IA prend le devant
                    if not results or float(results[0].get("score") or results[0].get("confidence") or 0) < 0.75:
                        results.insert(0, confirme)
                    else:
                        results.append(confirme)

    return {"results": results[:limit]}


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

    lines = [line.strip() for line in request.text.split("\n") if line.strip()]
    for line in lines:
        ref = await verse_parser.parse(line, skip_text_search=True)
        if ref and ref.get("reference") and ref["reference"] not in seen:
            seen.add(ref["reference"])
            extracted.append(ref)
        else:
            parts = re.split(r'[.;,!?]', line)
            for part in parts:
                part = part.strip()
                if len(part) >= 4:
                    ref_p = await verse_parser.parse(part, skip_text_search=True)
                    if ref_p and ref_p.get("reference") and ref_p["reference"] not in seen:
                        seen.add(ref_p["reference"])
                        extracted.append(ref_p)

    return {"references": extracted, "count": len(extracted)}


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


@router.get("/session/current")
async def get_current_session():
    """ID de la session de culte en cours (pour restaurer la file après un rechargement)"""
    from .. import main as main_module
    return {"session_id": main_module.current_session_id}


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



@router.get("/vosk/status")
async def get_vosk_status():
    """Récupère le statut du modèle Vosk local"""
    from ..main import vosk_service
    if not vosk_service:
        return {"installed": False, "downloading": False, "model_name": "", "model_type": ""}

    installed = vosk_service.initialized or vosk_service.is_installed()
    return {
        "installed": installed,
        "downloading": vosk_service.downloading and not installed,
        "download_progress": getattr(vosk_service, "download_progress", 0.0),
        "download_status": getattr(vosk_service, "download_status", ""),
        "model_name": vosk_service.model_name,
        "model_type": vosk_service.model_type,
        "last_error": getattr(vosk_service, "last_error", "")
    }


@router.get("/nemotron/status")
async def get_nemotron_status():
    """Récupère le statut du modèle Nemotron 3.5-ASR local"""
    from ..main import nemotron_service
    if not nemotron_service:
        return {"installed": False, "downloading": False, "model_name": "nemotron-3.5-asr-streaming-0.6b-Q8_0.gguf"}
    return {
        **nemotron_service.status(),
        "model_name": "nemotron-3.5-asr-streaming-0.6b-Q8_0.gguf",
    }


@router.post("/nemotron/download")
async def download_nemotron_model():
    """Démarre le téléchargement explicite du modèle Nemotron 3.5 ASR GGUF (716 Mo)."""
    # `asyncio` s'importe fonction par fonction dans ce module ; celle-ci
    # l'avait oublié, et levait NameError. Résultat : l'assistant de premier
    # lancement demandait le téléchargement, recevait une erreur 500, et le
    # bénévole restait devant une barre qui ne démarrait jamais.
    import asyncio

    from ..main import nemotron_service
    if not nemotron_service:
        raise HTTPException(status_code=503, detail="Service Nemotron indisponible")

    # `prepare` rend la main tout de suite : il lance son propre thread de
    # téléchargement. On l'appelle quand même hors de la boucle d'événements —
    # il crée des dossiers et vérifie le disque avant de déléguer.
    lance = await asyncio.to_thread(nemotron_service.prepare, True)
    if not lance:
        raise HTTPException(
            status_code=503,
            detail=nemotron_service.last_error or "Téléchargement impossible",
        )
    return {
        "status": "started",
        "message": "Téléchargement du modèle Nemotron 3.5-ASR démarré en arrière-plan",
        **nemotron_service.status(),
    }


@router.get("/overlay/status")
async def get_overlay_status():
    """Habillage personnalisé : image installée et zones de texte."""
    from ..services import overlay_store
    from ..core.config import settings
    return {
        **overlay_store.status(),
        "zones": overlay_store.parse_zones(settings.OVERLAY_ZONES),
        "shapes": overlay_store.parse_shapes(settings.OVERLAY_SHAPES),
    }


@router.post("/overlay/image")
async def upload_overlay_image(request: OverlayImageRequest):
    """Reçoit le PNG en base64 : évite la dépendance python-multipart, que le
    backend figé n'embarque pas."""
    import asyncio
    from ..services import overlay_store
    try:
        raw = overlay_store.decode_upload(request.data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    try:
        return await asyncio.to_thread(overlay_store.save_image, raw)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Écriture impossible : {exc}")


@router.delete("/overlay/image")
async def remove_overlay_image():
    from ..services import overlay_store
    overlay_store.delete_image()
    return overlay_store.status()


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


@router.get("/bibles/catalogue")
async def bible_catalogue():
    """Ce qui est réellement utilisable, et ce qui ne l'est pas.

    L'état vient du moteur de lecture, pas d'une liste écrite en dur : c'est ce
    qui empêche l'interface de proposer une version que le paquet n'embarque
    pas — le pasteur demandait la Semeur et le clic ne faisait rien.
    """
    from ..main import verse_parser
    from ..services import bible_import
    chargees = list(verse_parser.bible_loader.versions.keys()) if verse_parser else []
    return bible_import.catalogue(chargees)


@router.get("/bibles/imported")
async def list_imported_bibles():
    """Traductions ajoutées par l'église, distinctes de celles livrées."""
    from ..services import bible_import
    return {"versions": bible_import.lister(), "reserved": sorted(bible_import.SIGLES_RESERVES)}


@router.post("/bibles/import")
async def import_bible(request: BibleImportRequest):
    """Installe une traduction au format du corpus VersePro.

    Le fichier reste sur le poste de l'église : VersePro ne le rediffuse pas.
    La responsabilité des droits appartient à qui l'ajoute (voir CONDITIONS.md).
    """
    import asyncio
    from ..services import bible_import
    try:
        resume = await asyncio.to_thread(bible_import.importer, request.content, request.version_id or "")
    except bible_import.BibleInvalide as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {**resume, "restart_required": True}


@router.post("/bibles/download_public/{version_id}")
async def download_public_bible(version_id: str):
    """Télécharge et installe automatiquement une Bible du domaine public."""
    import asyncio
    import urllib.request
    from ..services import bible_import
    version_id = version_id.upper().strip()
    url = bible_import.PUBLIC_DOWNLOAD_URLS.get(version_id)
    if not url:
        raise HTTPException(status_code=400, detail=f"Aucun lien de téléchargement direct pour '{version_id}'")

    def _fetch_and_install():
        req = urllib.request.Request(url, headers={"User-Agent": "VersePro/2.0"})
        with urllib.request.urlopen(req) as resp:
            content = resp.read().decode("utf-8")
        return bible_import.importer(content, version_id)

    try:
        resume = await asyncio.to_thread(_fetch_and_install)
        return {**resume, "restart_required": True}
    except bible_import.BibleInvalide as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Échec du téléchargement direct : {exc}")


@router.delete("/bibles/imported/{version_id}")
async def delete_imported_bible(version_id: str):
    from ..services import bible_import
    try:
        bible_import.supprimer(version_id)
    except bible_import.BibleInvalide as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"versions": bible_import.lister(), "restart_required": True}


@router.get("/overlay/library")
async def list_overlay_presets():
    """Habillages enregistrés, pour le menu des styles."""
    from ..services import overlay_store
    return {"presets": overlay_store.list_presets()}


@router.post("/overlay/library")
async def save_overlay_preset(request: OverlayPresetRequest):
    """Enregistre l'habillage courant sous un nom, dans sa catégorie."""
    from ..core.config import settings
    from ..services import overlay_store
    if not request.name.strip():
        raise HTTPException(status_code=400, detail="Un nom est requis.")
    try:
        return overlay_store.save_preset(
            request.name, request.category,
            request.zones if request.zones is not None else settings.OVERLAY_ZONES,
            request.shapes if request.shapes is not None else settings.OVERLAY_SHAPES,
            overlay_store.IMAGE_PATH if overlay_store.IMAGE_PATH.is_file() else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/overlay/library/{slug}/apply")
async def apply_overlay_preset(slug: str):
    """Recopie un habillage enregistré dans l'habillage en cours d'édition."""
    import shutil
    from ..core.config import settings
    from ..services import overlay_store
    from ..services.database import get_database
    preset = overlay_store.load_preset(slug)
    if not preset:
        raise HTTPException(status_code=404, detail="Habillage introuvable.")
    db = get_database()
    settings.OVERLAY_ZONES = overlay_store.dump_zones(preset["zones"])
    settings.OVERLAY_SHAPES = overlay_store.dump_shapes(preset["shapes"])
    # Un preset chargé est un style à part entière, comme « bandeau » ou
    # « filet ». Avant cette affectation, il était copié dans l'atelier mais
    # la sortie restait sur l'ancien style : l'habillage semblait enregistré
    # puis ne réapparaissait jamais dans le rendu.
    settings.PROJECTION_THEME = "broadcast"
    settings.PROJECTION_STYLE = f"habillage:{preset['slug']}"
    await db.set_setting("overlay_zones", settings.OVERLAY_ZONES)
    await db.set_setting("overlay_shapes", settings.OVERLAY_SHAPES)
    await db.set_setting("projection_theme", settings.PROJECTION_THEME)
    await db.set_setting("projection_style", settings.PROJECTION_STYLE)
    if preset["image_path"]:
        overlay_store.OVERLAY_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(preset["image_path"], overlay_store.IMAGE_PATH)
    else:
        overlay_store.delete_image()
    return {"applied": preset["slug"], **overlay_store.status()}


@router.delete("/overlay/library/{slug}")
async def remove_overlay_preset(slug: str):
    from ..services import overlay_store
    overlay_store.delete_preset(slug)
    return {"presets": overlay_store.list_presets()}


@router.post("/vosk/download")
async def download_vosk_model():
    """Déclenche le téléchargement du modèle Vosk en tâche de fond"""
    from ..main import vosk_service
    if not vosk_service:
        raise HTTPException(status_code=503, detail="Service Vosk non disponible")

    import os
    import asyncio
    if os.path.exists(vosk_service.model_dir) and vosk_service.initialized:
        return {"status": "already_installed", "message": "Le modèle Vosk est déjà installé"}

    if vosk_service.downloading:
        return {"status": "downloading", "message": "Téléchargement déjà en cours"}

    # Déclenche l'initialisation (téléchargement en arrière-plan, ou chargement du
    # modèle déjà présent — potentiellement long, donc hors event loop)
    await asyncio.to_thread(vosk_service.initialize, True)
    return {"status": "started", "message": "Téléchargement du modèle Vosk démarré en arrière-plan"}


@router.get("/asr/status")
async def get_asr_status():
    """Capacites locales et recommandation adaptee a la machine."""
    from ..main import vosk_service, nemotron_service
    from ..core.config import settings

    return {
        "default_engine": settings.ASR_DEFAULT_ENGINE,
        "vosk": {
            "available": bool(vosk_service and vosk_service.initialized),
            "model": getattr(vosk_service, "model_name", ""),
        },
        "nemotron": nemotron_service.status() if nemotron_service else {"installed": False, "ready": False},
    }


@router.post("/asr/prepare")
async def prepare_local_asr(request: Optional[PrepareModelRequest] = None):
    """Prépare explicitement le moteur local; rien n'est téléchargé au démarrage."""
    from ..main import nemotron_service
    if not nemotron_service:
        raise HTTPException(status_code=503, detail="Service ASR local indisponible")
    if nemotron_service.is_ready and nemotron_service.runtime_available:
        return {"status": "ready", **nemotron_service.status()}
    if nemotron_service.is_ready and not nemotron_service.runtime_available:
        raise HTTPException(
            status_code=503,
            detail=nemotron_service.last_error or "Moteur natif Nemotron absent de l'application",
        )
    if not nemotron_service.downloading:
        import threading
        threading.Thread(
            target=nemotron_service.prepare,
            kwargs={"allow_download": True},
            daemon=True,
        ).start()
    return {"status": "preparing", **nemotron_service.status()}


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


@router.get("/settings")
async def get_settings():
    """Récupère la configuration"""
    from ..core.config import settings
    from ..main import ai_service, output_manager, semantic_service, nemotron_service
    from ..services.secret_store import secret_store
    from ..services import overlay_store

    propresenter_connected = False
    if output_manager and "propresenter" in output_manager.outputs:
        propresenter_connected = await output_manager.outputs["propresenter"].is_connected()

    return {
        "deepgram_model": settings.DEEPGRAM_MODEL,
        "deepgram_language": settings.DEEPGRAM_LANGUAGE,
        "propresenter_host": settings.PROPRESENTER_HOST,
        "propresenter_port": settings.PROPRESENTER_PORT,
        "propresenter_message_name": settings.PROPRESENTER_MESSAGE_NAME,
        "overlay_zones": overlay_store.parse_zones(settings.OVERLAY_ZONES),
        "overlay_shapes": overlay_store.parse_shapes(settings.OVERLAY_SHAPES),
        "ndi": (output_manager.outputs["ndi"].status()
                if output_manager and "ndi" in output_manager.outputs
                else {"available": False, "enabled": False, "sending": False,
                      "source_name": settings.NDI_SOURCE_NAME, "last_error": "sortie absente"}),
        "auto_send": settings.PROPRESENTER_AUTO_SEND,
        "sunday_safe_mode": settings.SUNDAY_SAFE_MODE,
        "shadow_mode": settings.SHADOW_MODE,
        "bible_version": settings.BIBLE_VERSION,
        "ai_agent_enabled": settings.AI_AGENT_ENABLED,
        "ai_available": bool(ai_service and ai_service.enabled),
        "ai_status": ai_service.status() if ai_service else {},
        "secret_storage_secure": secret_store.available,
        "propresenter_connected": propresenter_connected,
        "deepgram_api_key_configured": bool(settings.DEEPGRAM_API_KEY),
        "openrouter_api_key_configured": bool(settings.OPENROUTER_API_KEY),
        "gemini_api_key_configured": bool(settings.GEMINI_API_KEY),
        "deepgram_api_key_hint": _mask_secret(settings.DEEPGRAM_API_KEY),
        "openrouter_api_key_hint": _mask_secret(settings.OPENROUTER_API_KEY),
        "gemini_api_key_hint": _mask_secret(settings.GEMINI_API_KEY),
        "ai_confidence_threshold": settings.AI_CONFIDENCE_THRESHOLD,
        "ai_filtering_mode": settings.AI_FILTERING_MODE,
        "asr_default_engine": settings.ASR_DEFAULT_ENGINE,
        "nemotron_status": nemotron_service.status() if nemotron_service else {},
        "local_semantic_enabled": settings.LOCAL_SEMANTIC_ENABLED,
        "local_semantic_threshold": semantic_service.active_threshold if semantic_service else settings.LOCAL_SEMANTIC_THRESHOLD,
        "local_semantic_model": settings.LOCAL_SEMANTIC_MODEL,
        "semantic_status": semantic_service.status() if semantic_service else {},
        "projection_theme": settings.PROJECTION_THEME,
        "projection_style": settings.PROJECTION_STYLE,
        "show_bible_version": settings.SHOW_BIBLE_VERSION,
        "dual_translations": settings.DUAL_TRANSLATIONS,
    }


@router.post("/settings")
async def update_settings(settings_update: SettingsUpdate):
    """Met à jour la configuration et la persiste dans SQLite"""
    from ..core.config import settings
    from ..main import output_manager, verse_parser, ai_service, deepgram_service, semantic_service
    from ..services.database import get_database
    from ..services.secret_store import secret_store

    db = get_database()
    update = settings_update.model_dump(exclude_unset=True)
    logger.info(f"Mise à jour settings: {_redact_update(update)}")

    reconnect_propresenter = False

    if "auto_send" in update:
        settings.PROPRESENTER_AUTO_SEND = bool(update["auto_send"])
        await db.set_setting("auto_send", settings.PROPRESENTER_AUTO_SEND)

    if "sunday_safe_mode" in update:
        settings.SUNDAY_SAFE_MODE = bool(update["sunday_safe_mode"])
        await db.set_setting("sunday_safe_mode", settings.SUNDAY_SAFE_MODE)

    # La diffusion automatique et le mode dimanche sûr sont incompatibles :
    # le premier envoie une détection sans validation, le second l'interdit.
    # La règle est appliquée après les deux champs pour qu'un formulaire qui
    # envoie simultanément auto_send=true et sunday_safe_mode=true reste sûr.
    if settings.PROPRESENTER_AUTO_SEND and settings.SUNDAY_SAFE_MODE:
        settings.SUNDAY_SAFE_MODE = False
        await db.set_setting("sunday_safe_mode", False)

    if "shadow_mode" in update:
        settings.SHADOW_MODE = bool(update["shadow_mode"])
        await db.set_setting("shadow_mode", settings.SHADOW_MODE)

    if update.get("bible_version"):
        version = update["bible_version"].upper()
        settings.BIBLE_VERSION = version
        await db.set_setting("bible_version", settings.BIBLE_VERSION)
        if verse_parser and verse_parser.bible_loader and version in verse_parser.bible_loader.versions:
            verse_parser.bible_loader.active_version = version
            if semantic_service:
                semantic_service.reset()
                import threading
                threading.Thread(
                    target=semantic_service.initialize,
                    kwargs={"allow_download": False},
                    daemon=True,
                ).start()

    if update.get("propresenter_host"):
        settings.PROPRESENTER_HOST = update["propresenter_host"]
        await db.set_setting("propresenter_host", settings.PROPRESENTER_HOST)
        if output_manager and "propresenter" in output_manager.outputs:
            output_manager.outputs["propresenter"].host = settings.PROPRESENTER_HOST
            reconnect_propresenter = True

    if update.get("propresenter_port") is not None:
        settings.PROPRESENTER_PORT = int(update["propresenter_port"])
        await db.set_setting("propresenter_port", settings.PROPRESENTER_PORT)
        if output_manager and "propresenter" in output_manager.outputs:
            output_manager.outputs["propresenter"].port = settings.PROPRESENTER_PORT
            reconnect_propresenter = True

    if update.get("overlay_zones") is not None:
        from ..services import overlay_store
        # Nettoyage AVANT stockage : les zones finissent en styles inline sur
        # l'écran de projection, elles ne doivent jamais transporter n'importe quoi.
        settings.OVERLAY_ZONES = overlay_store.dump_zones(update["overlay_zones"])
        await db.set_setting("overlay_zones", settings.OVERLAY_ZONES)

    if update.get("ndi_source_name"):
        settings.NDI_SOURCE_NAME = update["ndi_source_name"].strip()[:60]
        await db.set_setting("ndi_source_name", settings.NDI_SOURCE_NAME)

    if update.get("ndi_enabled") is not None:
        settings.NDI_ENABLED = bool(update["ndi_enabled"])
        await db.set_setting("ndi_enabled", settings.NDI_ENABLED)
        if output_manager and "ndi" in output_manager.outputs:
            pilote = output_manager.outputs["ndi"]
            pilote.source_name = settings.NDI_SOURCE_NAME
            pilote.enabled = settings.NDI_ENABLED
            # Éteindre doit libérer la source tout de suite : un mélangeur qui
            # voit encore « VersePro » alors que la sortie est coupée ferait
            # perdre du temps à l'opérateur.
            if not settings.NDI_ENABLED:
                pilote.stop_sending()

    if update.get("overlay_shapes") is not None:
        from ..services import overlay_store
        settings.OVERLAY_SHAPES = overlay_store.dump_shapes(update["overlay_shapes"])
        await db.set_setting("overlay_shapes", settings.OVERLAY_SHAPES)

    if update.get("propresenter_message_name"):
        settings.PROPRESENTER_MESSAGE_NAME = update["propresenter_message_name"].strip()
        await db.set_setting("propresenter_message_name", settings.PROPRESENTER_MESSAGE_NAME)
        if output_manager and "propresenter" in output_manager.outputs:
            # Le message cible change : on oublie celui résolu, il sera recherché
            # à nouveau au prochain envoi.
            output_manager.outputs["propresenter"]._message_id = None
            reconnect_propresenter = True

    if update.get("deepgram_model"):
        settings.DEEPGRAM_MODEL = update["deepgram_model"]
        await db.set_setting("deepgram_model", settings.DEEPGRAM_MODEL)

    if update.get("deepgram_language"):
        settings.DEEPGRAM_LANGUAGE = update["deepgram_language"]
        await db.set_setting("deepgram_language", settings.DEEPGRAM_LANGUAGE)

    if "ai_agent_enabled" in update:
        settings.AI_AGENT_ENABLED = bool(update["ai_agent_enabled"])
        await db.set_setting("ai_agent_enabled", settings.AI_AGENT_ENABLED)
        if ai_service:
            ai_service.refresh_availability()

    if "deepgram_api_key" in update:
        settings.DEEPGRAM_API_KEY = str(update["deepgram_api_key"] or "").strip()
        await secret_store.set("deepgram_api_key", settings.DEEPGRAM_API_KEY)
        if deepgram_service:
            deepgram_service.api_key = settings.DEEPGRAM_API_KEY
            if settings.DEEPGRAM_API_KEY:
                deepgram_service._init_client()

    if "openrouter_api_key" in update:
        settings.OPENROUTER_API_KEY = str(update["openrouter_api_key"] or "").strip()
        await secret_store.set("openrouter_api_key", settings.OPENROUTER_API_KEY)
        if ai_service:
            ai_service.openrouter_key = settings.OPENROUTER_API_KEY
            ai_service.refresh_availability()

    if "gemini_api_key" in update:
        settings.GEMINI_API_KEY = str(update["gemini_api_key"] or "").strip()
        await secret_store.set("gemini_api_key", settings.GEMINI_API_KEY)
        if ai_service:
            ai_service.api_key = settings.GEMINI_API_KEY
            ai_service.refresh_availability()

    if "ai_confidence_threshold" in update:
        settings.AI_CONFIDENCE_THRESHOLD = int(update["ai_confidence_threshold"])
        await db.set_setting("ai_confidence_threshold", settings.AI_CONFIDENCE_THRESHOLD)

    if "ai_filtering_mode" in update:
        settings.AI_FILTERING_MODE = str(update["ai_filtering_mode"])
        await db.set_setting("ai_filtering_mode", settings.AI_FILTERING_MODE)


    if update.get("asr_default_engine"):
        engine = str(update["asr_default_engine"])
        if engine not in {"auto", "deepgram", "nemotron", "vosk", "local_auto"}:
            raise HTTPException(status_code=400, detail="Moteur ASR invalide")
        settings.ASR_DEFAULT_ENGINE = engine
        await db.set_setting("asr_default_engine", engine)

    if "local_semantic_enabled" in update:
        settings.LOCAL_SEMANTIC_ENABLED = bool(update["local_semantic_enabled"])
        await db.set_setting("local_semantic_enabled", settings.LOCAL_SEMANTIC_ENABLED)

    if "local_semantic_threshold" in update:
        threshold = float(update["local_semantic_threshold"])
        if not 0.4 <= threshold <= 0.98:
            raise HTTPException(status_code=400, detail="Seuil semantique hors limites")
        # Le curseur agit sur le modèle réellement actif (Qwen ou e5), chacun
        # ayant sa propre échelle de scores. Ainsi le réglage suit l'encodeur.
        active = (semantic_service.active_model if semantic_service else None) or settings.LOCAL_SEMANTIC_MODEL
        settings.LOCAL_SEMANTIC_CALIBRATION.setdefault(active, {})["threshold"] = threshold
        settings.LOCAL_SEMANTIC_THRESHOLD = threshold
        await db.set_setting(f"local_semantic_threshold_{active}", threshold)

    if "projection_theme" in update:
        theme = str(update["projection_theme"])
        settings.PROJECTION_THEME = theme
        await db.set_setting("projection_theme", theme)

    if "projection_style" in update:
        style = str(update["projection_style"])
        settings.PROJECTION_STYLE = style
        await db.set_setting("projection_style", style)

    if "show_bible_version" in update:
        show_ver = bool(update["show_bible_version"])
        settings.SHOW_BIBLE_VERSION = show_ver
        await db.set_setting("show_bible_version", settings.SHOW_BIBLE_VERSION)

    if "dual_translations" in update:
        dual_trans = str(update["dual_translations"])
        settings.DUAL_TRANSLATIONS = dual_trans
        await db.set_setting("dual_translations", dual_trans)

    if reconnect_propresenter and output_manager and "propresenter" in output_manager.outputs:
        pp_driver = output_manager.outputs["propresenter"]
        await pp_driver.disconnect()
        if settings.PROPRESENTER_AUTO_CONNECT:
            await pp_driver.connect()

    return await get_settings()


# ============================================
# Routes Historique & Statistiques
# ============================================

@router.get("/history/verses")
async def get_history(limit: int = 50, session_id: Optional[int] = None):
    """Récupère l'historique des versets détectés"""
    from ..services.database import get_database

    db = get_database()
    if not db.db:
        raise HTTPException(status_code=503, detail="Base de données non connectée")

    verses = await db.get_recent_verses(limit=limit, session_id=session_id)

    return {
        "verses": verses,
        "total": len(verses)
    }


@router.get("/history/verses/{verse_id}")
async def get_verse(verse_id: int):
    """Récupère un verset spécifique"""
    from ..services.database import get_database

    db = get_database()
    verse = await db.get_verse_by_id(verse_id)

    if not verse:
        raise HTTPException(status_code=404, detail="Verset non trouvé")

    return verse


@router.delete("/history/verses/{verse_id}")
async def delete_verse(verse_id: int):
    """Supprime un verset de l'historique"""
    from ..services.database import get_database

    db = get_database()
    await db.delete_verse(verse_id)

    return {"success": True, "message": "Verset supprimé"}


@router.post("/history/verses/{verse_id}/validate")
async def validate_verse(verse_id: int, validated: bool = True):
    """Valide manuellement un verset"""
    from ..services.database import get_database

    db = get_database()
    await db.update_verse_validation(verse_id, validated)

    return {"success": True}


@router.get("/history/sessions")
async def get_sessions(limit: int = 10):
    """Récupère l'historique des sessions"""
    from ..services.database import get_database

    db = get_database()
    sessions = await db.get_recent_sessions(limit=limit)

    return {
        "sessions": sessions,
        "total": len(sessions)
    }


@router.post("/history/sessions/start")
async def start_session(name: Optional[str] = None):
    """Démarre une nouvelle session"""
    from ..services.database import get_database

    db = get_database()
    session_id = await db.create_session(name)

    return {"success": True, "session_id": session_id}


@router.post("/history/sessions/{session_id}/end")
async def end_session(session_id: int):
    """Termine une session"""
    from ..services.database import get_database

    db = get_database()
    await db.end_session(session_id)

    return {"success": True}


@router.get("/history/sessions/{session_id}")
async def get_session_detail(session_id: int):
    """Récupère une session spécifique avec sa transcription et son résumé"""
    from ..services.database import get_database

    db = get_database()
    session = await db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session non trouvée")

    return session


async def _session_et_versets(session_id: int):
    """Session + versets projetés dans l'ORDRE DU CULTE.

    `get_recent_verses` trie du plus récent au plus ancien, ce qui convient à
    un panneau d'historique mais inverserait un compte rendu. On remet dans
    l'ordre où l'assemblée les a vus.
    """
    from ..services.database import get_database

    db = get_database()
    session = await db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session non trouvée")
    versets = await db.get_recent_verses(limit=1000, session_id=session_id)
    return session, list(reversed(versets))


@router.get("/history/sessions/{session_id}/export.md")
async def export_session_markdown(session_id: int):
    """Le compte rendu du culte : résumé, versets horodatés, transcription.

    Produit hors ligne, sans clé d'API. C'est aussi le fichier à déposer dans
    un outil de synthèse (NotebookLM ou autre) si l'église veut en tirer un
    podcast ou une vidéo — VersePro n'envoie rien lui-même.
    """
    from fastapi.responses import Response
    from ..services.session_export import vers_markdown, nom_fichier

    session, versets = await _session_et_versets(session_id)
    contenu = vers_markdown(session, versets)
    nom = nom_fichier(session, "md")
    return Response(
        content=contenu.encode("utf-8"),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nom}"'},
    )


@router.get("/history/sessions/{session_id}/export.pptx")
async def export_session_pptx(session_id: int):
    """Les versets du culte en diapositives, réutilisables en semaine."""
    from fastapi.responses import Response
    from ..services.session_export import vers_pptx, nom_fichier

    session, versets = await _session_et_versets(session_id)
    archive = vers_pptx(session, versets)
    nom = nom_fichier(session, "pptx")
    return Response(
        content=archive,
        media_type=("application/vnd.openxmlformats-officedocument"
                    ".presentationml.presentation"),
        headers={"Content-Disposition": f'attachment; filename="{nom}"'},
    )


@router.get("/history/sessions/{session_id}/export-recap.pptx")
async def export_session_recap_pptx(session_id: int):
    """Export du deck de synthèse, entièrement local une fois le résumé créé."""
    from fastapi.responses import Response
    from ..services.session_export import recap_pptx, nom_fichier

    session, versets = await _session_et_versets(session_id)
    resume = (session.get("summary") or "").strip()
    if not resume:
        raise HTTPException(status_code=409, detail="Générez d'abord le résumé de cette session.")
    archive = recap_pptx(session, resume, versets)
    nom = nom_fichier(session, "recap.pptx")
    return Response(
        content=archive,
        media_type=("application/vnd.openxmlformats-officedocument"
                    ".presentationml.presentation"),
        headers={"Content-Disposition": f'attachment; filename="{nom}"'},
    )


@router.post("/history/sessions/{session_id}/summary")
async def generate_session_summary(session_id: int):
    """Génère le résumé d'une session par l'IA et l'enregistre"""
    from ..services.database import get_database
    from ..main import ai_service

    if ai_service and hasattr(ai_service, "refresh_availability"):
        ai_service.refresh_availability()
    if not ai_service or not ai_service.enabled:
         raise HTTPException(status_code=503, detail="Agent IA non configuré ou inactif")

    db = get_database()
    session = await db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session non trouvée")

    transcript = session.get("transcript")
    if not transcript or not transcript.strip():
        raise HTTPException(status_code=400, detail="La transcription de cette session est vide. Impossible de résumer.")

    # Génération du résumé par l'Agent IA
    summary = await ai_service.generate_sermon_summary(transcript)
    if not summary:
        # La raison précise vaut mieux qu'un « échec » muet : clé absente,
        # quota dépassé, délai expiré ne se corrigent pas de la même façon.
        raison = getattr(ai_service, "last_summary_error", "") or "cause inconnue"
        raise HTTPException(status_code=502, detail=f"Résumé impossible — {raison}")

    # Enregistrement
    await db.update_session_summary(session_id, summary)

    return {
        "success": True,
        "summary": summary,
        "provider": getattr(ai_service, "last_summary_provider", "") or "ia",
        "offline": getattr(ai_service, "last_summary_provider", "") == "ollama",
    }


@router.get("/statistics")
async def get_statistics(days: int = 30):
    """Récupère les statistiques complètes"""
    from ..services.database import get_database

    db = get_database()
    if not db.db:
        raise HTTPException(status_code=503, detail="Base de données non connectée")

    stats = await db.get_statistics(days=days)

    return stats


@router.get("/statistics/books")
async def get_book_statistics(days: int = 30):
    """Statistiques par livre de la Bible"""
    from ..services.database import get_database

    db = get_database()
    books = await db.get_book_statistics(days=days)

    return {"books": books}


@router.get("/statistics/daily/{date}")
async def get_daily_stats(date: str):
    """Statistiques pour un jour spécifique (YYYY-MM-DD)"""
    from ..services.database import get_database

    db = get_database()
    stats = await db.get_daily_stats(date)

    return stats


@router.post("/history/export/csv")
async def export_csv(session_id: Optional[int] = None):
    """Exporte l'historique en CSV"""
    from ..services.database import get_database
    from fastapi.responses import FileResponse
    from starlette.background import BackgroundTask
    import tempfile
    import os

    db = get_database()

    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        output_path = f.name

    await db.export_to_csv(output_path, session_id=session_id)

    return FileResponse(
        output_path,
        media_type="text/csv",
        filename="versepro_export.csv",
        background=BackgroundTask(os.remove, output_path)
    )


@router.post("/history/export/json")
async def export_json(session_id: Optional[int] = None):
    """Exporte l'historique en JSON"""
    from ..services.database import get_database
    from fastapi.responses import FileResponse
    from starlette.background import BackgroundTask
    import tempfile
    import os

    db = get_database()

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        output_path = f.name

    await db.export_to_json(output_path, session_id=session_id)

    return FileResponse(
        output_path,
        media_type="application/json",
        filename="versepro_export.json",
        background=BackgroundTask(os.remove, output_path)
    )


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
                        prev_ref = f"{parsed['book_abbr']} {parsed['chapter']}:{prev_v}"
                        await broadcast_projection(prev_text, prev_ref)
                        if output_manager:
                            await output_manager.project(prev_text, prev_ref)
                        return {"success": True, "reference": prev_ref, "text": prev_text}
        except Exception:
            pass
    return {"success": False, "detail": "Aucun verset précédent disponible"}

@router.get("/update/check")
async def update_check():
    """État de mise à jour. Renvoie toujours 200, même hors ligne : ce contrôle
    est un confort, jamais une condition pour utiliser l'application."""
    from ..services.update_check import check_for_update
    return await check_for_update()


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
