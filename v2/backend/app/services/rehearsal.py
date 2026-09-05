"""Isolated rehearsal: no output manager, database or cloud client."""
from types import SimpleNamespace
from .reference_engine import BibleReferenceEngine
from .verse_graph import VerseGraphService
from ..core.config import settings

DEMO_LINES = [
    {"text": "Ouvrons Jean chapitre trois verset seize.", "expected": "Jn 3:16"},
    {"text": "Le rendez-vous de l’équipe est à dix-huit heures.", "expected": None},
    {"text": "Lisons le Psaume vingt-trois verset un.", "expected": "Ps 23:1"},
    {"text": "Terminons avec Romains chapitre huit verset vingt-huit.", "expected": "Rm 8:28"},
]

def new_engine(parser, semantic):
    return BibleReferenceEngine(parser, semantic, VerseGraphService(semantic),
                                SimpleNamespace(enabled=False), settings.model_copy(update={"AI_AGENT_ENABLED": False}))

async def detect(engine, text):
    import time
    started = time.perf_counter()
    candidate = await engine.detecter_sans_effet(text, final_state=True)
    return {"text": text, "candidate": candidate, "detection_ms": round((time.perf_counter()-started)*1000, 1)}
