"""Historique des versets, sessions de culte, exports et statistiques."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from loguru import logger

router = APIRouter()


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


class SessionStartRequest(BaseModel):
    name: Optional[str] = None


@router.post("/history/sessions/start")
async def start_session(payload: Optional[SessionStartRequest] = None, name: Optional[str] = None):
    """Démarre une nouvelle session"""
    from ..services.database import get_database
    from .. import main as main_module

    session_name = (payload.name if payload else None) or name or ""
    db = get_database()
    if main_module.current_session_id:
        try:
            await db.end_session(main_module.current_session_id)
        except Exception as exc:
            # La nouvelle session démarre quand même ; l'ancienne resterait
            # ouverte dans l'historique, il faut pouvoir le comprendre.
            logger.warning(f"Session {main_module.current_session_id} non clôturée : {exc}")
    session_id = await db.create_session(session_name)
    main_module.current_session_id = session_id

    return {"success": True, "session_id": session_id}


@router.post("/history/sessions/{session_id}/end")
async def end_session(session_id: int):
    """Termine une session"""
    from ..services.database import get_database
    from .. import main as main_module

    db = get_database()
    await db.end_session(session_id)
    if main_module.current_session_id == session_id:
        main_module.current_session_id = None

    return {"success": True}


@router.get("/history/sessions/{session_id}")
async def get_session_detail(session_id: int):
    """Récupère une session spécifique avec sa transcription, son résumé et ses versets"""
    from ..services.database import get_database

    db = get_database()
    session = await db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session non trouvée")

    versets = await db.get_recent_verses(limit=1000, session_id=session_id)
    session["verses"] = list(reversed(versets))
    session["verse_count"] = len(versets)

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
