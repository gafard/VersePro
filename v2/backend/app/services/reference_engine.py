"""
Bible Reference Engine
Moteur central de détection de références bibliques. Découplé de l'ASR.
"""

import time
import asyncio
import re
from collections import deque
from typing import Optional, Dict, Any
from loguru import logger
from app.services.ai_service import AIService
from app.services.detection_fusion import (
    best_overlap,
    content_stems,
    fuse as fuse_detection,
    strip_attribution,
)

# Nombre d'énoncés précédents fournis à l'IA. Trois est le réglage que
# SmartVerses expose sous « Prior chunks for AI », et c'est un bon compromis :
# assez pour situer une allusion dans son récit, assez peu pour que le verset
# annoncé cinq minutes plus tôt ne pèse plus sur la phrase courante.
CONTEXTE_ENONCES = 3
DEDUPLICATION_SECONDS = 30.0

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
        # MÉMOIRE DE DÉDUPLICATION À PLUSIEURS ENTRÉES.
        #
        # Elle n'en retenait qu'UNE : la dernière référence annoncée. Or les
        # fenêtres d'analyse se recouvrent largement (96 mots), donc la même
        # référence revient dans plusieurs énoncés consécutifs — et il suffit
        # qu'une autre s'intercale pour que le garde-fou saute. Relevé sur une
        # heure de prédication réelle : 50 détections pour 35 références
        # distinctes, soit 15 cartes en double, dont « Éphésiens 1:19 » quatre
        # fois et « 1 Pierre 2:24 » trois fois.
        self._emis_recemment: Dict[str, float] = {}

        # LE PLAN DE PRÉDICATION, quand le pasteur l'a partagé.
        #
        # Paramètres → Avancé sait déjà coller des notes et en extraire les
        # références ; elles remplissaient le déroulé et s'arrêtaient là, dans
        # le navigateur. Le moteur traitait donc un verset annoncé par écrit
        # exactement comme un verset jamais vu.
        #
        # C'est pourtant la seule information du système qui vienne d'AVANT le
        # culte, et donc la seule qui ne dépende pas de ce que le micro a cru
        # entendre. Elle tranche là où aucun seuil ne peut : entre deux numéros
        # de verset du même chapitre, celui qui est au plan gagne.
        self._plan: set = set()

        # Les derniers énoncés CLOS, donnés à l'IA comme contexte. Une allusion
        # vit dans son fil : « il tenait les bras levés » ne désigne rien seul,
        # précédé de « Moïse était sur la colline » il désigne Exode 17.
        self._contexte_recent: deque[str] = deque(maxlen=CONTEXTE_ENONCES)
        self._ai_last_resort_lock = asyncio.Lock()

    @staticmethod
    def _cle_plan(book_abbr, chapter, verse_start) -> str:
        return f"{book_abbr}_{chapter}_{verse_start}"

    async def definir_plan(self, references) -> int:
        """Enregistre les références annoncées avant le culte. Renvoie le compte."""
        nouveau = set()
        for brute in references or []:
            texte = brute if isinstance(brute, str) else (brute or {}).get("reference")
            if not texte:
                continue
            texte = str(texte).strip()
            analyse = await self.verse_parser.parse(texte, skip_text_search=True)
            if not analyse:
                # « Romains 8 » ne se parse pas seul : les motifs exigent
                # « chapitre » ou un verset. Un plan écrit à la main contient
                # pourtant des chapitres nus — on réessaie sous la forme que
                # le parseur reconnaît plutôt que de les perdre en silence.
                analyse = await self.verse_parser.parse(
                    re.sub(r"^(.*?)\s+(\d+)$", r"\1 chapitre \2", texte),
                    skip_text_search=True,
                )
            if analyse and analyse.get("book_abbr") and analyse.get("chapter"):
                nouveau.add(self._cle_plan(
                    analyse["book_abbr"], analyse["chapter"], analyse.get("verse_start")))
        self._plan = nouveau
        logger.info(f"📋 Plan de prédication : {len(nouveau)} référence(s) attendue(s)")
        return len(nouveau)

    def _dans_le_plan(self, ref: Dict[str, Any]) -> bool:
        if not self._plan:
            return False
        chapitre = self._cle_plan(ref.get("book_abbr"), ref.get("chapter"), None)
        verset = self._cle_plan(
            ref.get("book_abbr"), ref.get("chapter"), ref.get("verse_start"))
        # Le chapitre seul au plan suffit à reconnaître un verset de ce
        # chapitre : « nous lirons Romains 8 » couvre Romains 8:28.
        return verset in self._plan or chapitre in self._plan

    def _contredit_le_plan(self, ref: Dict[str, Any]) -> bool:
        """Le plan couvre ce chapitre, mais avec un AUTRE verset.

        Le pasteur a écrit « Marc 11:23 » ; le micro entend « verset 29 ». Le
        plan ne peut pas trancher tout seul — un prédicateur lit souvent
        autour du verset annoncé — mais il suffit à retirer l'autopilotage :
        la carte s'affiche, le régisseur voit qu'elle s'écarte du plan.

        Ne se déclenche QUE si le plan désigne des versets précis de ce
        chapitre. Un « nous lirons Romains 8 » sans numéro ne contredit rien.
        """
        if not self._plan or self._dans_le_plan(ref):
            return False
        prefixe = self._cle_plan(ref.get("book_abbr"), ref.get("chapter"), "")
        return any(
            cle.startswith(prefixe) and not cle.endswith("_None")
            for cle in self._plan
        )

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

    @staticmethod
    def _same_verse(a: dict | None, b: dict | None) -> bool:
        if not a or not b:
            return False
        return (
            str(a.get("book_abbr") or "").casefold()
            == str(b.get("book_abbr") or "").casefold()
            and int(a.get("chapter") or 0) == int(b.get("chapter") or 0)
            and int(a.get("verse_start") or a.get("verse") or 0)
            == int(b.get("verse_start") or b.get("verse") or 0)
        )

    @staticmethod
    def _inside_anchor(candidate: dict, anchor: dict | None) -> bool:
        if not anchor:
            return True
        return (
            str(candidate.get("book_abbr") or "").casefold()
            == str(anchor.get("book_abbr") or "").casefold()
            and int(candidate.get("chapter") or 0) == int(anchor.get("chapter") or 0)
        )

    async def _hybrid_search(self, query: str, anchor: dict | None = None) -> Optional[Dict[str, Any]]:
        """Recherche lexicale+sémantique, éventuellement bornée à un chapitre.

        Une annonce comme « Jean chapitre 17 » est une ancre, pas une fin de
        recherche : la citation qui suit doit choisir le verset *dans* Jean 17.
        On demande davantage de candidats avant filtrage afin qu'un verset du
        chapitre annoncé ne disparaisse pas derrière des ressemblances globales.
        """
        top_k = max(3, int(self.settings.HYBRID_TOP_K))
        # Un extrait situé au milieu/à la fin d'un long verset peut n'être que
        # 8e sémantiquement (Jean 7:37 en est un cas réel). On récupère un
        # vivier plus large puis le recouvrement lexical tranche ; cela ne
        # relâche aucun seuil de décision.
        candidate_k = min(24, top_k * 4)
        retrieval_k = min(40, top_k * 6) if anchor else candidate_k

        async def decide(window: str) -> dict | None:
            async def lexical_search():
                candidates = await asyncio.to_thread(
                    self.verse_parser.bible_loader.search_candidates, window, retrieval_k
                )
                return [c for c in candidates if self._inside_anchor(c, anchor)][:candidate_k]

            async def semantic_search():
                if not (self.semantic_service and self.semantic_service.initialized):
                    return []
                if anchor and hasattr(self.semantic_service, "search_in_scope"):
                    candidates = await asyncio.to_thread(
                        self.semantic_service.search_in_scope,
                        window,
                        anchor.get("book_abbr"),
                        anchor.get("chapter"),
                        candidate_k,
                        0.0,
                    )
                else:
                    candidates = await asyncio.to_thread(
                        self.semantic_service.search, window, retrieval_k, 0.0
                    )
                return [c for c in candidates if self._inside_anchor(c, anchor)][:candidate_k]

            lexical, semantic = await asyncio.gather(lexical_search(), semantic_search())
            for cand in semantic:
                if "translations" not in cand and cand.get("verse_start") is not None:
                    cand["translations"] = self.verse_parser.bible_loader.translations_for(
                        cand["book_abbr"], cand["chapter"], cand["verse_start"]
                    )
            return fuse_detection(
                lexical,
                semantic,
                window,
                semantic_threshold=(
                    self.semantic_service.active_threshold
                    if self.semantic_service else self.settings.LOCAL_SEMANTIC_THRESHOLD
                ),
                semantic_margin=(
                    self.semantic_service.active_margin
                    if self.semantic_service else self.settings.LOCAL_SEMANTIC_MARGIN
                ),
                overlap_min=self.settings.HYBRID_OVERLAP_MIN,
                top_n=candidate_k,
            )

        decisions = [
            decision
            for decision in await asyncio.gather(
                *[decide(window) for window in self._retrieval_windows(query)]
            )
            if decision
        ]
        if not decisions:
            return None
        decisions.sort(
            key=lambda decision: (
                bool((decision.get("fusion") or {}).get("agreement")),
                float((decision.get("fusion") or {}).get("overlap") or 0),
                float(decision.get("confidence") or 0),
            ),
            reverse=True,
        )
        return decisions[0]

    async def _explicit_conflict(self, spoken: str, explicit: dict) -> Optional[Dict[str, Any]]:
        """Signale une citation quasi certaine qui contredit la référence dite.

        On ne remplace jamais une référence explicite sur une ressemblance
        moyenne. Il faut un accord lexical+sémantique, une citation très couverte
        et presque aucun recouvrement avec le verset annoncé. Le résultat reste
        obligatoirement manuel : l'opérateur voit les deux références.
        """
        query = strip_attribution(self.verse_parser.normalize_spoken(spoken))
        # Les mots de la référence annoncée (« psaume / trois / huit »)
        # diluent la citation et faisaient tomber son recouvrement de 1,00 à
        # 0,67. Le parseur nous donne le segment exact qu'il a reconnu : on le
        # retire uniquement de la requête de comparaison.
        matched_reference = str(explicit.get("matched_reference") or "").strip()
        if matched_reference:
            query = re.sub(re.escape(matched_reference), " ", query, count=1, flags=re.IGNORECASE)
            query = " ".join(query.split())
        if len(content_stems(query)) < 4:
            return None
        if self.semantic_service and not self.semantic_service.initialized and not self.semantic_service.indexing:
            await asyncio.to_thread(self.semantic_service.initialize, False)
        if not (self.semantic_service and self.semantic_service.initialized):
            return None

        candidate = await self._hybrid_search(query)
        if not candidate or self._same_verse(candidate, explicit):
            return None
        fusion = candidate.get("fusion") or {}
        candidate_overlap = float(fusion.get("overlap") or 0)
        explicit_overlap = best_overlap(query, explicit)
        confidence = float(candidate.get("confidence") or 0)
        semantic_score = float(fusion.get("sem_score") or candidate.get("score") or 0)
        semantic_floor = (
            float(self.semantic_service.active_threshold)
            if self.semantic_service else 0.90
        )
        independently_confirmed = bool(fusion.get("agreement")) or (
            candidate_overlap >= 0.90 and semantic_score >= semantic_floor
        )
        if not (
            independently_confirmed
            and candidate_overlap >= 0.72
            and confidence >= 0.94
            and explicit_overlap <= 0.20
        ):
            return None

        corrected = dict(candidate)
        corrected["detection_method"] = "semantic_conflict"
        corrected["requires_review"] = True
        corrected["explicit_conflict"] = {
            "spoken_reference": explicit.get("reference"),
            "spoken_text": explicit.get("text", ""),
            "spoken_overlap": round(explicit_overlap, 3),
            "quoted_reference": corrected.get("reference"),
            "quoted_overlap": round(candidate_overlap, 3),
        }
        return corrected

    async def _run_detection_cascade(self, analysis_text: str, final_state: bool) -> Optional[Dict[str, Any]]:
        if not self.verse_parser:
            return None

        # An explicit spoken correction supersedes earlier references in the
        # same utterance. Ordinary uses of « pardon » are left untouched.
        revisions = list(re.finditer(r"\b(?:pardon|je corrige|je voulais dire|plutôt)\b[\s,:-]*", analysis_text, re.IGNORECASE))
        if revisions:
            revised = analysis_text[revisions[-1].end():]
            parsed_revision = await self.verse_parser.parse(revised, skip_text_search=True)
            if parsed_revision and parsed_revision.get("verse_start") is not None:
                previous = await self.verse_parser.parse(analysis_text[:revisions[-1].start()], skip_text_search=True, collect_all=True)
                superseded = [r["reference"] for r in previous if r.get("reference") != parsed_revision["reference"]]
                return {"superseded_references": superseded, **parsed_revision, "detection_method": "spoken_revision", "requires_review": True,
                        "confidence": .95, "explanation": "Correction orale entendue : le dernier passage remplace la première référence.",
                        "spoken_evidence": revised[:300]}

        if final_state:
            from .local_corrections import lookup
            corrected = lookup(analysis_text)
            if corrected and not await self.verse_parser.parse(analysis_text, skip_text_search=True):
                candidate = await self.verse_parser.parse(corrected, skip_text_search=True)
                if candidate and candidate.get("verse_start"):
                    return {**candidate, "detection_method": "local_correction", "requires_review": True,
                            "explanation": "Phrase déjà corrigée par votre équipe sur cet ordinateur. À valider.", "confidence": .9}

        recent = self._recent_window(analysis_text, self.settings.HYBRID_WINDOW_WORDS)
        # Une citation peut dépasser 40 mots. Conserver une fenêtre plus large
        # pour l'étage explicite empêche la référence prononcée au début de
        # disparaître avant que le final ASR arrive. La recherche sémantique
        # reste, elle, découpée en petites fenêtres dans `_hybrid_search`.
        reference_scope = self._recent_window(
            analysis_text,
            max(96, int(self.settings.HYBRID_WINDOW_WORDS) * 3),
        )

        # ── A. Citation explicite & sauts relatifs ──
        active_ctx = None
        if self.last_detected_ref:
            p_act = await self.verse_parser.parse(self.last_detected_ref, skip_text_search=True)
            if p_act and p_act.get("book_abbr") and p_act.get("chapter"):
                active_ctx = {"book_abbr": p_act["book_abbr"], "chapter": p_act["chapter"]}

        # Sur un ÉNONCÉ CLOS, on récolte toutes les références de la phrase.
        # Sur un partiel, la fenêtre glisse encore : la dernière prononcée
        # reste la bonne réponse, et annoncer les précédentes ferait clignoter
        # la file à chaque mot.
        autres_references: list = []
        if final_state:
            trouvees = await self.verse_parser.parse(
                reference_scope, skip_text_search=True,
                active_context=active_ctx, collect_all=True,
            )
            completes = [r for r in trouvees if r.get("verse_start") is not None]
            if completes:
                # La PREMIÈRE annoncée est celle que le prédicateur va lire :
                # « ouvrons Jean 3:16, puis nous irons en Romains 8 ». Les
                # suivantes attendent dans la file, prêtes en un clic.
                reference = completes[0]
                autres_references = completes[1:]
            else:
                reference = trouvees[0] if trouvees else None
        else:
            reference = await self.verse_parser.parse(
                reference_scope, skip_text_search=True, active_context=active_ctx
            )
        chapter_anchor = reference if reference and reference.get("verse_start") is None else None

        # Une référence complète reste instantanée sur les partiels. Sur un
        # final, on laisse toutefois une citation quasi littérale signaler une
        # contradiction manifeste (« Psaume 3:8 » suivi du texte de Ps 32:8).
        if reference and reference.get("verse_start") is not None:
            if final_state and self.settings.LOCAL_SEMANTIC_ENABLED:
                conflict = await self._explicit_conflict(reference_scope, reference)
                if conflict:
                    return conflict
            if autres_references:
                reference["references_multiples"] = autres_references
            return reference

        # Le chapitre seul s'affiche immédiatement pendant que le prédicateur
        # continue. Une fois l'énoncé clos, il devient une ancre et la cascade
        # poursuit jusqu'au verset au lieu de renvoyer artificiellement :0.
        if not final_state:
            return chapter_anchor

        contextual_candidate = None
        if chapter_anchor:
            contextual = await self.verse_parser.parse(
                reference_scope, skip_text_search=False, active_context=active_ctx
            )
            if contextual and contextual.get("verse_start") is not None:
                contextual["requires_review"] = True
                contextual_candidate = contextual

        if not self.settings.LOCAL_SEMANTIC_ENABLED:
            return contextual_candidate or chapter_anchor

        # Un segment trop court ne peut désigner aucun verset : « j'avais de
        # l'eau » (4 mots) faisait sortir Ézéchiel 47:4. Ce filtre-ci reste.
        if self.sante_transcription:
            if not self.sante_transcription.segment_exploitable(recent):
                return contextual_candidate or chapter_anchor

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
            return contextual_candidate or chapter_anchor

        if self.semantic_service and not self.semantic_service.initialized and not self.semantic_service.indexing:
            await asyncio.to_thread(self.semantic_service.initialize, False)

        # ── B'. VERSEGRAPH ──
        if self.verse_graph and not chapter_anchor:
            ancre = self.verse_graph.resoudre(recent)
            if ancre:
                logger.info(f"⚓ VerseGraph → {ancre['reference']} (score={ancre['confidence']:.4f})")
                return ancre

        # ── B. FUSION SÉMANTIQUE ──
        found = await self._hybrid_search(query, anchor=chapter_anchor)
        if found:
            if chapter_anchor:
                found["chapter_anchor"] = chapter_anchor.get("reference")
            return found

        # Si l'index sémantique n'est pas encore prêt, le meilleur résultat
        # contextuel du parseur vaut mieux que de retomber sur « chapitre :0 ».
        # Il reste toujours en validation manuelle.
        if contextual_candidate:
            return contextual_candidate

        # ── C. DERNIER RECOURS : Arbitrage IA ──
        if not (self.ai_service and self.ai_service.enabled and self.settings.AI_AGENT_ENABLED):
            return chapter_anchor
        if self._ai_last_resort_lock.locked():
            return chapter_anchor
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
                return chapter_anchor

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
                        return chapter_anchor

                    clean_query = intent_res.get("query")
                    if clean_query.lower() in {"none", "null"}:
                        return chapter_anchor

                    logger.info(f"🤖 Intention biblique détectée. Mots-clés extraits : '{clean_query}'")

                # 2. Recherche dans le vivier fermé (RAG Step 2)
                shortlist = await asyncio.to_thread(
                    self.verse_parser.bible_loader.search_candidates, clean_query, 3
                )
                if self.semantic_service and self.semantic_service.initialized:
                    shortlist += await asyncio.to_thread(self.semantic_service.search, clean_query, 3, 0.0)
                if chapter_anchor:
                    shortlist = [
                        candidate for candidate in shortlist
                        if self._inside_anchor(candidate, chapter_anchor)
                    ]

                if not shortlist:
                    if chapter_anchor:
                        return chapter_anchor
                    logger.info("IA RAG : aucun candidat local ; validation directe contre la Bible.")

                # 3. Validation par l'IA (RAG Step 3). Même sans shortlist,
                # l'appel reste autorisé en dernier recours : la référence
                # sera alors validée directement contre la Bible et ne pourra
                # jamais être projetée automatiquement.
                res = await self.ai_service.detect_bible_reference(
                    query, candidates=shortlist, contexte=list(self._contexte_recent),
                    # LE VERROU QUI CONTREDISAIT CE COMMENTAIRE.
                    #
                    # `_validate_candidate_result` rejetait toute suggestion dès
                    # que la shortlist était vide — c'est-à-dire précisément
                    # dans le cas de dernier recours que ce bloc est censé
                    # traiter. L'IA n'avait donc le droit que de REORDONNER ce
                    # que le local avait déjà trouvé, jamais d'apporter ce
                    # qu'il avait manqué.
                    #
                    # Rien ne le justifiait, et trois garde-fous existent déjà
                    # en aval, tous vérifiés : le seuil de confiance, la
                    # vérification de la référence dans la Bible locale
                    # (« écartée : référence introuvable »), et le passage
                    # obligatoire en validation manuelle — une suggestion IA
                    # porte requires_review et sa méthode `ai_semantic` ne
                    # figure dans aucune liste projetable. Elle ne peut donc
                    # JAMAIS aller à l'écran seule, verrouillée deux fois.
                    exiger_candidats=False,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.debug(f"Arbitrage IA hybride indisponible : {exc}")
                return chapter_anchor

        if not res or not res.get("reference"):
            return chapter_anchor

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
                return chapter_anchor

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
            return chapter_anchor

        grounded = await self.verse_parser.parse(res["reference"], skip_text_search=True)
        if not grounded or not grounded.get("text"):
            logger.info(f"🛡️ Suggestion IA écartée (référence introuvable dans la Bible) : {res['reference']!r}")
            return chapter_anchor

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

        `process()` mémorise la dernière référence pendant la fenêtre de
        déduplication. Le mode répétition doit rejouer la MÊME cascade
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

        if method == "chapter_candidate":
            # Une ancre de chapitre aide l'opérateur et VerseGraph pendant que
            # la phrase continue, mais ce n'est pas encore un verset : elle ne
            # doit pas gonfler l'historique ni les statistiques avec un :0.
            ref["transient"] = True

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
        elif ref.get("detection_method") in {"spoken_revision", "local_correction"}:
            explanation = ref.get("explanation") or "Correction à valider par l’opérateur."
        elif ref.get("detection_method") == "semantic_conflict":
            conflict = ref.get("explicit_conflict") or {}
            explanation = (
                f"Le texte cité correspond à {ref.get('reference')} mais la référence "
                f"prononcée était {conflict.get('spoken_reference')}. Validation requise."
            )
        elif ref.get("detection_method") in {"semantic_local", "semantic_anchored"}:
            explanation = (
                "Suggestion locale issue de l'accord lexical et sémantique. "
                f"Recouvrement: {float(fusion.get('overlap') or 0):.2f}."
            )
        elif ref.get("detection_method") == "chapter_candidate":
            explanation = "Chapitre annoncé ; recherche du verset en cours."
        else:
            explanation = "Suggestion IA choisie dans une liste fermée de versets réels. Validation humaine requise."

        ref["explanation"] = explanation
        ref["decision_generation"] = generation

        ref_key = f"{ref.get('book_abbr')}_{ref.get('chapter')}_{ref.get('verse_start')}_{ref.get('verse_end') or ''}"
        now = time.monotonic()

        if self._deja_emis(ref_key, now):
            return None

        # CONTRADICTION DE VERSET : deux numéros différents du MÊME chapitre à
        # quelques secondes d'intervalle. C'est la signature d'un chiffre mal
        # entendu, pas de deux citations.
        #
        # Relevé le 11 août, à la même seconde, sur la même phrase :
        #     « Parlez à votre montagne, Marc chapitre 11 verset 23 »
        #     « Parlez à votre montagne, Marc chapitre 11 verset 29 »
        # et de même Romains 5:14 / Romains 5:4. Les deux passent le seuil
        # d'autopilotage à 0,98 — motif explicite, verset bel et bien prononcé
        # — donc aucun filtre de confiance ne les sépare. L'un des deux est
        # forcément faux, et rien ne dit lequel.
        #
        # On ne tranche donc pas : le second reste une carte à valider. Le
        # premier est déjà à l'écran, le régisseur voit les deux et choisit.
        # Le plan tranche la contradiction que le signal ne peut pas trancher.
        # « Marc 11:23 » et « Marc 11:29 » sortent de la même phrase avec la
        # même confiance ; si le pasteur a écrit 11:23 dans ses notes, la
        # question ne se pose plus.
        ref["au_plan"] = self._dans_le_plan(ref)

        if (self._contredit_recent(ref, now) or self._contredit_le_plan(ref)) \
                and not ref["au_plan"]:
            ref["requires_review"] = True
            ref["verset_conteste"] = True
            ref["explanation"] = (
                f"Un autre verset de {ref.get('book')} {ref.get('chapter')} vient "
                "d'être détecté : un des deux numéros a probablement été mal "
                "entendu. À valider avant projection."
            )
            logger.warning(
                f"⚠️ Verset contesté : {ref.get('reference')} arrive juste après "
                "un autre verset du même chapitre"
            )

        self.last_detected_ref = ref_key
        self.last_detected_at = now
        self._emis_recemment[ref_key] = now

        # Les références supplémentaires de l'énoncé passent par la même
        # mémoire : sans quoi le recouvrement des fenêtres les rejouerait à
        # chaque énoncé suivant.
        supplementaires = []
        for extra in ref.pop("references_multiples", []) or []:
            cle = (
                f"{extra.get('book_abbr')}_{extra.get('chapter')}"
                f"_{extra.get('verse_start')}_{extra.get('verse_end') or ''}"
            )
            if self._deja_emis(cle, now):
                continue
            self._emis_recemment[cle] = now
            extra["decision_generation"] = generation
            extra["explanation"] = (
                "Annoncée dans la même phrase que "
                f"{ref.get('reference')} — à valider avant projection."
            )
            # Jamais projetée d'office : sur plusieurs références enchaînées,
            # une seule peut aller à l'écran, et c'est la première annoncée.
            extra["requires_review"] = True
            extra["annonce_multiple"] = True
            supplementaires.append(extra)
        if supplementaires:
            ref["references_multiples"] = supplementaires

        return {
            "type": "reference_detected",
            "payload": ref
        }

    # Fenêtre de contradiction : au-delà, deux versets du même chapitre sont
    # une lecture suivie (« verset 3 … verset 4 »), pas un chiffre mal entendu.
    CONTRADICTION_SECONDS = 12.0

    def _contredit_recent(self, ref: Dict[str, Any], now: float) -> bool:
        """Un AUTRE verset du même livre et chapitre vient-il d'être annoncé ?"""
        prefixe = f"{ref.get('book_abbr')}_{ref.get('chapter')}_"
        depart = ref.get("verse_start")
        for cle, quand in self._emis_recemment.items():
            if now - quand >= self.CONTRADICTION_SECONDS:
                continue
            if not cle.startswith(prefixe):
                continue
            morceaux = cle[len(prefixe):].split("_")
            if morceaux and morceaux[0] != str(depart):
                return True
        return False

    def _deja_emis(self, ref_key: str, now: float) -> bool:
        """Vrai si cette référence est partie il y a moins de DEDUPLICATION_SECONDS."""
        if self._emis_recemment:
            perimees = [
                cle for cle, quand in self._emis_recemment.items()
                if now - quand >= DEDUPLICATION_SECONDS
            ]
            for cle in perimees:
                del self._emis_recemment[cle]
        vu = self._emis_recemment.get(ref_key)
        return vu is not None and now - vu < DEDUPLICATION_SECONDS
