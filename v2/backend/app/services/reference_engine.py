"""
Bible Reference Engine
Moteur central de détection de références bibliques. Découplé de l'ASR.
"""

import time
import asyncio
from collections import deque
from typing import Optional, Dict, Any
from loguru import logger
from app.services.ai_service import AIService
from app.services.detection_fusion import fuse as fuse_detection, strip_attribution

# Nombre d'énoncés précédents fournis à l'IA. Trois est le réglage que
# SmartVerses expose sous « Prior chunks for AI », et c'est un bon compromis :
# assez pour situer une allusion dans son récit, assez peu pour que le verset
# annoncé cinq minutes plus tôt ne pèse plus sur la phrase courante.
CONTEXTE_ENONCES = 3

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
        # Les derniers énoncés CLOS, donnés à l'IA comme contexte. Une allusion
        # vit dans son fil : « il tenait les bras levés » ne désigne rien seul,
        # précédé de « Moïse était sur la colline » il désigne Exode 17.
        self._contexte_recent: deque[str] = deque(maxlen=CONTEXTE_ENONCES)
        self._ai_last_resort_lock = asyncio.Lock()

    def _recent_window(self, text: str, word_limit: int = 40) -> str:
        words = text.split()
        return " ".join(words[-word_limit:])

    def _retrieval_windows(self, text: str) -> list[str]:
        """Construit plusieurs vues courtes de la phrase pour la recherche.

        Une seule fenêtre de 22 mots est rapide, mais elle coupe parfois le
        début d'une paraphrase (« il a promis que… ») ou conserve la fin d'une
        phrase logistique. On interroge donc trois vues complémentaires puis
        la fusion choisit le candidat qui reçoit le meilleur accord lexical /
        sémantique. Cela améliore le rappel sans transformer le contexte entier
        du culte en requête (source classique de faux positifs).
        """
        mots = text.split()
        limite = max(8, int(self.settings.HYBRID_WINDOW_WORDS))
        vues = []

        def ajouter(valeur: str):
            valeur = " ".join(valeur.split()).strip()
            if len(valeur.split()) >= 4 and valeur not in vues:
                vues.append(valeur)

        # Vue principale : le segment le plus récent, celui qui porte le sens.
        ajouter(" ".join(mots[-limite:]))
        # Vue élargie : récupère le sujet quand l'ASR l'a placé juste avant la
        # fenêtre courte (fréquent avec les phrases longues de prédication).
        ajouter(" ".join(mots[-min(len(mots), limite + 14):]))
        # Dernière phrase ponctuée : évite qu'une phrase de transition accolée
        # au texte sacré dilue l'embedding.
        import re
        phrases = [p.strip() for p in re.split(r"[.!?;\n]+", text) if p.strip()]
        if phrases:
            ajouter(" ".join(phrases[-1].split()[-limite:]))
        return vues or [" ".join(mots[-limite:])]

    async def _run_detection_cascade(self, analysis_text: str, final_state: bool) -> Optional[Dict[str, Any]]:
        if not self.verse_parser:
            return None

        recent = self._recent_window(analysis_text, self.settings.HYBRID_WINDOW_WORDS)

        # ── A. Citation explicite & sauts relatifs ──
        active_ctx = None
        if self.last_detected_ref:
            p_act = await self.verse_parser.parse(self.last_detected_ref, skip_text_search=True)
            if p_act and p_act.get("book_abbr") and p_act.get("chapter"):
                active_ctx = {"book_abbr": p_act["book_abbr"], "chapter": p_act["chapter"]}

        reference = await self.verse_parser.parse(recent, skip_text_search=True, active_context=active_ctx)
        if reference:
            return reference

        if not final_state or not self.settings.LOCAL_SEMANTIC_ENABLED:
            return None

        # Un segment trop court ne peut désigner aucun verset : « j'avais de
        # l'eau » (4 mots) faisait sortir Ézéchiel 47:4. Ce filtre-ci reste.
        if self.sante_transcription:
            if not self.sante_transcription.segment_exploitable(recent):
                return None

        # LE FILTRE « SON DIFFICILE » EST RETIRÉ, sur décision de l'utilisateur.
        #
        # Il suspendait toute détection sémantique quand la transcription se
        # hachait — utile contre le bruit, mais il éteignait le logiciel
        # précisément dans les églises qu'il doit servir. Le contexte tranche :
        # ce sont des cultes charismatiques, musique pendant la prédication,
        # donc l'état « difficile » y est la NORME et non l'exception. Un
        # logiciel muet tout le culte n'aide personne, et rater un verset coûte
        # plus cher qu'une proposition de trop dans un panneau qu'on peut
        # ignorer.
        #
        # La mesure, elle, reste calculée et exposée (`etat()`) : elle informe
        # l'opérateur sans plus rien lui interdire.

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

        # Plusieurs fenêtres complémentaires améliorent le rappel sans injecter
        # les énoncés précédents dans le score lexical : le verset proposé doit
        # réellement correspondre à la phrase qui vient d'être prononcée.
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
        # Mode strict : on n'interroge l'IA que si le propos est manifestement
        # religieux, pour ne pas la solliciter sur la parole du quotidien.
        #
        # Mais le mot-clé est cherché dans la PHRASE ET SON CONTEXTE, pas dans
        # la phrase seule — et cette nuance décide de tout. « Tant qu'il tenait
        # les bras levés, le peuple l'emportait » ne contient aucun mot
        # biblique : le filtre l'écartait, comme il écartait la plupart des
        # ALLUSIONS, c'est-à-dire exactement ce que l'IA doit traiter. Précédée
        # de « Moïse était monté sur la colline », la même phrase est
        # évidemment religieuse.
        if self.settings.AI_FILTERING_MODE == "strict":
            fil = " ".join([query, *self._contexte_recent]).lower()
            if not any(k in fil for k in BIBLE_KEYWORDS):
                return None

        async with self._ai_last_resort_lock:
            try:
                # 1. Extraction de l'intention (RAG Step 1). Les doubles de
                # tests et les intégrations tierces plus anciennes peuvent ne
                # pas encore exposer cette méthode : dans ce cas, on conserve
                # le contrat historique et on interroge directement le
                # détecteur avec la même validation locale en aval.
                extract_intent = getattr(self.ai_service, "extract_biblical_intent", None)
                clean_query = query
                if callable(extract_intent):
                    intent_res = await extract_intent(
                        query, contexte=list(self._contexte_recent)
                    )

                    if not intent_res or intent_res.get("intent") != "biblical" or not intent_res.get("query"):
                        logger.debug("IA : Aucune intention biblique détectée ou requête vide.")
                        return None

                    clean_query = intent_res.get("query")
                    if clean_query.lower() in {"none", "null"}:
                        return None

                    logger.info(f"🤖 Intention biblique détectée. Mots-clés extraits : '{clean_query}'")

                # 2. Recherche dans le vivier fermé (RAG Step 2)
                shortlist = await asyncio.to_thread(
                    self.verse_parser.bible_loader.search_candidates, clean_query, 3
                )
                if self.semantic_service and self.semantic_service.initialized:
                    shortlist += await asyncio.to_thread(self.semantic_service.search, clean_query, 3, 0.0)

                if not shortlist:
                    logger.info("IA RAG : aucun candidat local ; validation directe contre la Bible.")

                # 3. Validation par l'IA (RAG Step 3). Même sans shortlist,
                # l'appel reste autorisé en dernier recours : la référence
                # sera alors validée directement contre la Bible et ne pourra
                # jamais être projetée automatiquement.
                res = await self.ai_service.detect_bible_reference(
                    query, candidates=shortlist, contexte=list(self._contexte_recent)
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.debug(f"Arbitrage IA hybride indisponible : {exc}")
                return None

        if not res or not res.get("reference"):
            return None

        # Normalisation stricte de la référence
        normaliser = AIService._normalize_reference
        selected = None
        if shortlist:
            attendu = normaliser(res.get("reference", ""))
            selected = next(
                (c for c in shortlist if normaliser(c.get("reference", "")) == attendu),
                None,
            )

            if not selected:
                logger.info(f"Suggestion IA écartée : '{res.get('reference')}' absente de la shortlist du vivier")
                return None

        # Validation du score. Une suggestion issue d'une shortlist reçoit la
        # confiance du candidat local ; une suggestion libre garde uniquement
        # la confiance brute du modèle et reste obligatoirement manuelle.
        if not res.get("candidate_validated") and selected:
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
        elif not selected:
            raw_confidence = max(0.0, min(100.0, float(res.get("confidence") or 0)))
            res = {
                **res,
                "raw_model_confidence": raw_confidence,
                "confidence": raw_confidence,
                "candidate_score": None,
                "candidate_validated": False,
            }

        confidence = float(res.get("confidence") or 0)
        seuil = (
            self.settings.AI_CONFIDENCE_THRESHOLD
            if selected
            else self.settings.AI_FREE_CONFIDENCE_THRESHOLD
        )
        if confidence < seuil:
            logger.info(f"🛡️ Suggestion IA écartée (confiance {confidence:.0f} % < {seuil} %)")
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
        # Les citations textuelles vérifiées par l'index local sont aussi des
        # matchs exacts. Elles ne doivent pas rester dans « À valider » quand
        # la diffusion directe est activée. Le fuzzy et les propositions IA
        # restent manuels, car ils peuvent viser un mauvais verset.
        exact_methods = {"explicit", "text_phrase", "text_index"}
        minimum = 0.90 if method == "text_index" else 0.95
        return (
            method in exact_methods
            and confidence >= minimum
            and ref.get("verse_start") is not None
            and not ref.get("requires_review")
        )

    async def detecter_sans_effet(self, analysis_text: str, final_state: bool = True) -> Optional[Dict[str, Any]]:
        """La cascade seule, sans toucher à l'état du direct.

        `process()` mémorise la dernière référence pour ne pas la reproposer
        pendant 8 secondes. Le mode répétition doit rejouer la MÊME cascade
        sans polluer cette mémoire, sinon une répétition juste avant le culte
        rendrait le moteur muet sur les premiers versets réellement cités.
        """
        return await self._run_detection_cascade(analysis_text, final_state)

    async def process(self, analysis_text: str, is_final: bool, generation: int, source_asr: str = "vosk", session_id: str = "local") -> Optional[Dict[str, Any]]:
        # 1. Cascade de détection. Sur un PARTIEL elle s'arrête d'elle-même
        #    après l'étage explicite — mais cet étage doit tourner : quand le
        #    prédicateur a fini de dire « Romains chapitre huit verset
        #    vingt-huit », la référence est complète AVANT la fin de l'énoncé,
        #    et l'attendre ajouterait plusieurs secondes de retard à l'écran.
        decision = await self._run_detection_cascade(analysis_text, is_final)

        # 1 bis. Mémoire de contexte. On ne retient QUE les énoncés clos : un
        # partiel change à chaque seconde et remplirait la mémoire de versions
        # successives de la même phrase. On la remplit APRÈS la cascade, sinon
        # la phrase courante figurerait dans son propre contexte.
        if is_final:
            enonce = self._recent_window(analysis_text, self.settings.HYBRID_WINDOW_WORDS).strip()
            if enonce and (not self._contexte_recent or self._contexte_recent[-1] != enonce):
                self._contexte_recent.append(enonce)

        # Un étage « incrémental » annonçait ici le passage vers lequel on se
        # dirigeait (« Recherche en cours : Romains 8… »). Il est retiré, et la
        # mesure explique pourquoi : sur 30 minutes de prédication réelle, il
        # se déclenchait 1 683 fois — une fois toutes les 1,1 seconde — parce
        # que les articles français entrent dans les abréviations de livres
        # (« est » → Esther, « la » → Lamentations, « je » → Jérémie).
        #
        # Depuis que la cascade passe en premier, « Jean chapitre 3 » remonte
        # de toute façon comme chapter_candidate : une vraie détection, qui
        # pose en plus l'ancre VerseGraph. L'étage n'apportait plus rien.
        # `VerseParserService.parse_incremental` reste disponible et testé si
        # l'idée revient — il lui faudra alors une amorce et un filtre de
        # longueur, puis une nouvelle mesure sur du vrai son.
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
