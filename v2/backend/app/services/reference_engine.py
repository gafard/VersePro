"""
Bible Reference Engine
Moteur central de détection de références bibliques. Découplé de l'ASR.
"""

import time
import asyncio
from typing import Optional, Dict, Any
from loguru import logger
from app.services.detection_fusion import fuse as fuse_detection, strip_attribution

BIBLE_KEYWORDS = {
    "dieu", "seigneur", "jésus", "jesus", "christ", "esprit", "bible", "écriture",
    "ecriture", "verset", "parole", "évangile", "evangile", "psaume", "apôtre",
    "apotre", "prophète", "prophete", "épître", "epitre", "royaume", "salut",
    "grâce", "grace", "péché", "peche", "foi", "prière", "priere", "alliance",
    "testament", "saint", "messie", "croix", "résurrection", "resurrection",
    "disciple", "éternel", "eternel", "amen", "béni", "beni", "sauveur",
}

class BibleReferenceEngine:
    def __init__(
        self,
        verse_parser,
        semantic_service,
        verse_graph,
        ai_service,
        settings,
        db_service=None,
        sante_transcription=None
    ):
        self.verse_parser = verse_parser
        self.semantic_service = semantic_service
        self.verse_graph = verse_graph
        self.ai_service = ai_service
        self.settings = settings
        self.db_service = db_service
        self.sante_transcription = sante_transcription

        self.last_detected_ref = None
        self.last_detected_at = 0.0
        self._ai_last_resort_lock = asyncio.Lock()

    def _recent_window(self, text: str, word_limit: int = 40) -> str:
        words = text.split()
        return " ".join(words[-word_limit:])

    def _retrieval_windows(self, text: str) -> list[str]:
        return [" ".join(text.split()[-self.settings.HYBRID_WINDOW_WORDS:])]

    async def _run_detection_cascade(self, analysis_text: str, final_state: bool) -> Optional[Dict[str, Any]]:
        if not self.verse_parser:
            return None

        recent = self._recent_window(analysis_text, self.settings.HYBRID_WINDOW_WORDS)

        # ── A. Citation explicite ──
        reference = await self.verse_parser.parse(recent, skip_text_search=True)
        if reference:
            return reference

        if not final_state or not self.settings.LOCAL_SEMANTIC_ENABLED:
            return None

        if self.sante_transcription:
            if not self.sante_transcription.segment_exploitable(recent):
                return None
            if not self.sante_transcription.est_fiable():
                return None

        cleaned = self.verse_parser.normalize_spoken(recent)
        query = strip_attribution(cleaned)
        if len(query.split()) < 4:
            return None

        if self.semantic_service and not self.semantic_service.initialized and not self.semantic_service.indexing:
            await asyncio.to_thread(self.semantic_service.initialize, False)

        # ── B'. VERSEGRAPH ──
        if self.verse_graph:
            ancre = self.verse_graph.resoudre(recent)
            if ancre:
                logger.info(f"⚓ VerseGraph → {ancre['reference']} (score={ancre['confidence']:.4f})")
                return ancre

        # ── B. FUSION SÉMANTIQUE ──
        async def _decide(window: str) -> dict | None:
            async def _lexical():
                return await asyncio.to_thread(
                    self.verse_parser.bible_loader.search_candidates, window, self.settings.HYBRID_TOP_K
                )
            async def _semantic():
                if not (self.semantic_service and self.semantic_service.initialized):
                    return []
                return await asyncio.to_thread(
                    self.semantic_service.search, window, self.settings.HYBRID_TOP_K, 0.0
                )
            lexical, semantic = await asyncio.gather(_lexical(), _semantic())
            for cand in semantic:
                if "translations" not in cand and cand.get("verse_start") is not None:
                    cand["translations"] = self.verse_parser.bible_loader.translations_for(
                        cand["book_abbr"], cand["chapter"], cand["verse_start"]
                    )
            return fuse_detection(
                lexical, semantic, window,
                semantic_threshold=(self.semantic_service.active_threshold if self.semantic_service else self.settings.LOCAL_SEMANTIC_THRESHOLD),
                semantic_margin=(self.semantic_service.active_margin if self.semantic_service else self.settings.LOCAL_SEMANTIC_MARGIN),
                overlap_min=self.settings.HYBRID_OVERLAP_MIN,
                top_n=self.settings.HYBRID_TOP_K,
            )

        windows = self._retrieval_windows(query)
        found = [d for d in await asyncio.gather(*[_decide(w) for w in windows]) if d]
        if found:
            found.sort(
                key=lambda d: (
                    bool((d.get("fusion") or {}).get("agreement")),
                    float((d.get("fusion") or {}).get("overlap") or 0),
                    float(d.get("confidence") or 0),
                ),
                reverse=True,
            )
            return found[0]

        # ── C. DERNIER RECOURS : Arbitrage IA ──
        if not (self.ai_service and self.ai_service.enabled and self.settings.AI_AGENT_ENABLED):
            return None
        if self._ai_last_resort_lock.locked():
            return None
        if self.settings.AI_FILTERING_MODE == "strict" and not any(k in query.lower() for k in BIBLE_KEYWORDS):
            return None

        async with self._ai_last_resort_lock:
            try:
                shortlist = await asyncio.to_thread(
                    self.verse_parser.bible_loader.search_candidates, query, 3
                )
                if self.semantic_service and self.semantic_service.initialized:
                    shortlist += await asyncio.to_thread(self.semantic_service.search, query, 3, 0.0)
                if not shortlist:
                    return None
                res = await self.ai_service.detect_bible_reference(query, candidates=shortlist)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.debug(f"Arbitrage IA de dernier recours indisponible : {exc}")
                return None

        if not res or not res.get("reference"):
            return None

        # Validation stricte du résultat
        selected = next(
            (
                candidate for candidate in shortlist
                if type(self.ai_service)._normalize_reference(candidate.get("reference", ""))
                == type(self.ai_service)._normalize_reference(res.get("reference", ""))
            ),
            None,
        )
        if not selected:
            logger.info("Suggestion IA écartée : référence absente de la liste fermée")
            return None
            
        if not res.get("candidate_validated"):
            raw_confidence = max(0.0, min(100.0, float(res.get("confidence") or 0)))
            try:
                raw_score = selected.get("score")
                if raw_score is None:
                    raw_score = selected.get("semantic_score")
                if raw_score is None:
                    raw_score = selected.get("confidence")
                score = max(0.0, min(1.0, float(raw_score)))
                candidate_confidence = 70.0 + (score * 30.0)
            except (TypeError, ValueError):
                score = None
                candidate_confidence = 85.0
            res = {
                **res,
                "reference": selected["reference"],
                "raw_model_confidence": raw_confidence,
                "confidence": min(raw_confidence, candidate_confidence),
                "candidate_score": score,
                "candidate_validated": True,
            }
            
        confidence = float(res.get("confidence") or 0)
        if confidence < self.settings.AI_CONFIDENCE_THRESHOLD:
            logger.info(f"🛡️ Suggestion IA écartée (confiance {confidence:.0f} % < {self.settings.AI_CONFIDENCE_THRESHOLD} %)")
            return None

        grounded = await self.verse_parser.parse(res["reference"], skip_text_search=True)
        if not grounded or not grounded.get("text"):
            logger.info(f"🛡️ Suggestion IA écartée (référence introuvable dans la Bible) : {res['reference']!r}")
            return None

        grounded["confidence"] = confidence / 100.0
        grounded["detection_method"] = "ai_semantic"
        grounded["requires_review"] = True
        grounded["candidate_validated"] = True
        grounded["candidate_score"] = res.get("candidate_score")
        grounded["raw_model_confidence"] = res.get("raw_model_confidence")
        logger.info(f"🤖 Dernier recours IA → {grounded['reference']} ({confidence:.0f} %)")
        return grounded

    def _is_direct_projection_allowed(self, ref: dict) -> bool:
        method = ref.get("detection_method")
        confidence = float(ref.get("confidence") or 0)
        return (
            method == "explicit"
            and confidence >= 0.95
            and ref.get("verse_start") is not None
            and not ref.get("requires_review")
        )

    async def process(self, analysis_text: str, is_final: bool, generation: int, source_asr: str = "vosk", session_id: str = "local") -> Optional[Dict[str, Any]]:
        # 1. Parsing incrémental rapide (si partiel)
        if not is_final:
            incremental = self.verse_parser.parse_incremental(self._recent_window(analysis_text, 15))
            if incremental:
                return {
                    "type": "incremental_reference",
                    "payload": incremental
                }

        # 2. Cascade de détection profonde
        decision = await self._run_detection_cascade(analysis_text, is_final)
        if not decision:
            return None

        method = decision.get("detection_method")
        source = "local" if method != "ai_semantic" else "ai"
        ref = dict(decision)
        ref["source"] = source
        
        if source != "local":
            ref["detection_method"] = "ai_semantic"
            ref["confidence"] = min(float(ref.get("confidence") or 0.95), 0.95)
            ref["requires_review"] = True
            ref["projection_policy"] = "manual_review"
        else:
            ref.setdefault("requires_review", False)
            direct_allowed = self._is_direct_projection_allowed(ref)
            ref["requires_review"] = not direct_allowed
            ref["projection_policy"] = "autopilot_direct" if direct_allowed else "manual_review"
            
            if self.verse_graph:
                self.verse_graph.ancrer(ref)

        direct_allowed = self._is_direct_projection_allowed(ref)
        ref["auto_projected"] = bool(
            self.settings.PROPRESENTER_AUTO_SEND
            and direct_allowed
            and not self.settings.SUNDAY_SAFE_MODE
            and not self.settings.SHADOW_MODE
        )
        if ref["auto_projected"]:
            ref["projection_policy"] = "autopilot_projected"
        elif self.settings.SHADOW_MODE:
            ref["projection_policy"] = "shadow_only"
        elif self.settings.SUNDAY_SAFE_MODE:
            ref["projection_policy"] = "safe_manual_review"

        fusion = ref.get("fusion") or {}
        if ref.get("detection_method") == "explicit":
            explanation = "Référence biblique prononcée explicitement et vérifiée dans le corpus local."
        elif source == "semantic":
            explanation = (
                "Suggestion locale issue de l'accord lexical et sémantique. "
                f"Recouvrement: {float(fusion.get('overlap') or 0):.2f}."
            )
        else:
            explanation = "Suggestion IA choisie dans une liste fermée de versets réels. Validation humaine requise."
        
        ref["explanation"] = explanation
        ref["decision_generation"] = generation

        ref_key = f"{ref.get('book_abbr')}_{ref.get('chapter')}_{ref.get('verse_start')}_{ref.get('verse_end') or ''}"
        now = time.monotonic()
        
        if ref_key == self.last_detected_ref and now - self.last_detected_at < 8.0:
            return None
            
        self.last_detected_ref = ref_key
        self.last_detected_at = now

        return {
            "type": "reference_detected",
            "payload": ref
        }
