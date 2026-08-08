import json
import httpx
import asyncio
import re
import unicodedata
from typing import Optional, Dict, Any, List
from loguru import logger
from ..core.config import settings

class AIService:
    """Service d'Agent IA pour la détection sémantique et l'analyse via Google Gemini, OpenRouter ou Ollama Local"""

    def __init__(self, api_key: str = "", openrouter_key: str = ""):
        self.openrouter_key = openrouter_key or settings.OPENROUTER_API_KEY
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.ollama_url = settings.OLLAMA_URL
        self.ollama_model = settings.OLLAMA_MODEL
        self.openrouter_model = settings.OPENROUTER_MODEL
        self.gemini_model = settings.GEMINI_MODEL

        self.ollama_active = False
        self.ollama_reachable = False
        # Dernière raison d'échec d'un résumé, remontée telle quelle à l'écran.
        self.last_summary_error = ""
        self.last_summary_provider = ""
        self.ollama_model_available = False
        # Caches bornés (FIFO) : sans plafond, un culte de 2h avec traduction simultanée
        # ferait croître la mémoire indéfiniment (une entrée par phrase finale)
        self._cache_max_entries = 500
        self._reference_cache: Dict[str, Optional[Dict[str, Any]]] = {}
        self._translation_cache: Dict[str, Optional[str]] = {}
        self._summary_cache: Dict[str, Optional[str]] = {}

        # Une URL Ollama configurée ne prouve pas qu'un serveur ou un modèle est
        # disponible. L'état passe à actif seulement après le contrôle réseau.
        self.enabled = settings.AI_AGENT_ENABLED and (bool(self.openrouter_key) or bool(self.api_key))

        # Tente de détecter Ollama en tâche de fond
        if settings.AI_AGENT_ENABLED and self.ollama_url:
            asyncio.create_task(self._detect_ollama())

    def _cache_put(self, cache: Dict[str, Any], key: str, value: Any):
        """Insère dans un cache en évinçant les entrées les plus anciennes au-delà du plafond"""
        cache[key] = value
        while len(cache) > self._cache_max_entries:
            cache.pop(next(iter(cache)))

    def _normalize_cache_key(self, text: str, extra: str = "") -> str:
        normalized = text.lower().strip()
        normalized = "".join(c for c in unicodedata.normalize("NFD", normalized) if unicodedata.category(c) != "Mn")
        normalized = re.sub(r"\s+", " ", normalized)
        return f"{extra}:{normalized[:1200]}"

    def _decode_json_payload(self, content: str) -> Dict[str, Any]:
        """Parse du JSON brut ou extrait le premier objet JSON d'une réponse trop bavarde."""
        if not content:
            return {}
        try:
            return json.loads(content)
        except Exception:
            match = re.search(r"\{.*\}", content, flags=re.S)
            if not match:
                return {}
            try:
                return json.loads(match.group(0))
            except Exception:
                return {}

    async def _detect_ollama(self):
        """Vérifie Ollama sans lancer de téléchargement implicite de plusieurs Go."""
        self.ollama_reachable = False
        self.ollama_model_available = False
        self.ollama_active = False
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(f"{self.ollama_url}/api/tags")
                if response.status_code == 200:
                    self.ollama_reachable = True

                    data = response.json()
                    models = [m.get("name") for m in data.get("models", [])]
                    self.ollama_model_available = any(
                        m and (self.ollama_model in m or m in self.ollama_model)
                        for m in models
                    )
                    self.ollama_active = self.ollama_model_available
                    self.enabled = settings.AI_AGENT_ENABLED and (
                        bool(self.openrouter_key) or bool(self.api_key) or self.ollama_active
                    )
                    if not self.ollama_model_available:
                        logger.warning(
                            f"Ollama répond, mais le modèle {self.ollama_model} n'est pas installé. "
                            "Installez-le explicitement depuis Paramètres."
                        )
                    else:
                        logger.info(f"Ollama prêt avec le modèle {self.ollama_model}")
        except Exception as exc:
            self.enabled = settings.AI_AGENT_ENABLED and (
                bool(self.openrouter_key) or bool(self.api_key)
            )
            logger.debug(f"Ollama indisponible : {exc}")

    def refresh_availability(self) -> bool:
        self.enabled = settings.AI_AGENT_ENABLED and (
            bool(self.openrouter_key) or bool(self.api_key) or self.ollama_active
        )
        return self.enabled

    def status(self) -> Dict[str, Any]:
        return {
            "enabled": self.refresh_availability(),
            "openrouter": bool(self.openrouter_key),
            "gemini": bool(self.api_key),
            "ollama_reachable": self.ollama_reachable,
            "ollama_model_available": self.ollama_model_available,
            "provider": (
                "openrouter" if self.openrouter_key else
                "gemini" if self.api_key else
                "ollama" if self.ollama_active else None
            ),
        }

    async def _pull_ollama_model(self, model_name: str):
        """Télécharge automatiquement le modèle Ollama en tâche de fond"""
        try:
            async with httpx.AsyncClient(timeout=600.0) as client:
                logger.info(f"⚙️ [Ollama] Début du pull du modèle {model_name} (peut prendre quelques minutes)...")
                response = await client.post(
                    f"{self.ollama_url}/api/pull",
                    json={"name": model_name, "stream": False}
                )
                if response.status_code == 200:
                    logger.info(f"✅ [Ollama] Le modèle {model_name} a été téléchargé avec succès et est prêt !")
                else:
                    logger.error(f"❌ [Ollama] Échec du pull du modèle {model_name} (Statut: {response.status_code})")
        except Exception as e:
            logger.error(f"❌ [Ollama] Erreur lors du téléchargement automatique d'Ollama: {e}")

    @staticmethod
    def _normalize_reference(reference: str) -> str:
        normalized = "".join(
            c for c in unicodedata.normalize("NFD", str(reference or "").lower())
            if unicodedata.category(c) != "Mn"
        )
        return re.sub(r"[^a-z0-9]", "", normalized)

    def _build_detection_prompt(self, text: str, candidates: Optional[List[Dict[str, Any]]] = None,
                                contexte: Optional[List[str]] = None) -> str:
        # CE QUI PRÉCÈDE compte autant que la phrase elle-même. « Il tenait les
        # bras levés » ne désigne rien tout seul ; précédé de « Moïse était sur
        # la colline », il désigne Exode 17. Une allusion vit dans son fil, et
        # l'analyser hors contexte revient à juger une phrase sortie d'un livre.
        #
        # Le contexte est donné pour COMPRENDRE, jamais pour être cité : la
        # réponse doit porter sur la phrase courante, sinon un verset annoncé
        # deux minutes plus tôt reviendrait à l'écran indéfiniment.
        contexte_block = ""
        if contexte:
            contexte_block = (
                "\n\nCE QUI VIENT D'ETRE DIT (contexte, a ne PAS analyser) :\n"
                + "\n".join(f"- {c}" for c in contexte[-3:])
            )

        candidate_block = ""
        if candidates:
            lines = []
            for candidate in candidates[:8]:
                reference = candidate.get("reference", "")
                verse_text = str(candidate.get("text", ""))[:320]
                lines.append(f'- "{reference}" : {verse_text}')
            candidate_block = (
                "\n\nCANDIDATS AUTORISES (liste fermee):\n"
                + "\n".join(lines)
                + "\nChoisis exactement une reference de cette liste, ou null. "
                  "N'invente et ne reformule aucune reference."
            )

        return (
            "Analyse cette transcription de sermon. Identifie une citation ou paraphrase biblique "
            "uniquement si le lien est suffisamment net.\n\n"
            f'Phrase a analyser: "{text}"'
            f"{contexte_block}"
            f"{candidate_block}\n\n"
            "Reponds uniquement avec un objet JSON valide: "
            '{"reference": "Jean 3:16" ou null, "confidence": entier de 0 a 100}.'
        )

    def _validate_candidate_result(
        self,
        result: Optional[Dict[str, Any]],
        candidates: Optional[List[Dict[str, Any]]],
    ) -> Optional[Dict[str, Any]]:
        if not result or not candidates:
            return None
        by_reference = {
            self._normalize_reference(candidate.get("reference", "")): candidate
            for candidate in candidates
        }
        selected = by_reference.get(self._normalize_reference(result.get("reference", "")))
        if not selected:
            logger.warning("Suggestion IA rejetee: reference absente de la liste locale de candidats")
            return None
        raw_confidence = max(0, min(100, int(result.get("confidence") or 0)))
        raw_score = selected.get("score")
        if raw_score is None:
            raw_score = selected.get("semantic_score")
        if raw_score is None:
            raw_score = selected.get("confidence")
        try:
            normalized_score = max(0.0, min(1.0, float(raw_score)))
            candidate_confidence = 70.0 + (normalized_score * 30.0)
        except (TypeError, ValueError):
            normalized_score = None
            candidate_confidence = 85.0
        calibrated_confidence = int(round(min(raw_confidence, candidate_confidence)))
        return {
            **result,
            "reference": selected["reference"],
            "raw_model_confidence": raw_confidence,
            "confidence": calibrated_confidence,
            "candidate_score": normalized_score,
            "candidate_validated": True,
        }

    async def detect_bible_reference(
        self,
        text: str,
        candidates: Optional[List[Dict[str, Any]]] = None,
        contexte: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Analyse sémantiquement le texte pour détecter une référence biblique (implicite ou explicite).
        Ordre de priorité:
        1. OpenRouter (si clé configurée)
        2. Gemini Direct (si clé configurée et OpenRouter échoue/absent)
        3. Ollama local (si détecté actif)

        Returns:
            Dictionnaire {"reference": "Jean 3:16", "confidence": 95} ou None
        """
        if not self.enabled or not text or len(text.strip()) < 10:
            return None

        candidate_key = ",".join(candidate.get("reference", "") for candidate in (candidates or []))
        cache_key = self._normalize_cache_key(text, f"reference:{candidate_key}")
        if cache_key in self._reference_cache:
            return self._reference_cache[cache_key]

        # 1. OpenRouter
        if self.openrouter_key:
            ref = self._validate_candidate_result(await self._call_openrouter(text, candidates, contexte), candidates)
            if ref:
                self._cache_put(self._reference_cache, cache_key, ref)
                return ref

        # 2. Gemini Direct
        if self.api_key:
            ref = self._validate_candidate_result(await self._call_gemini_direct(text, candidates, contexte), candidates)
            if ref:
                self._cache_put(self._reference_cache, cache_key, ref)
                return ref

        # 3. Ollama Local
        if self.ollama_active:
            ref = self._validate_candidate_result(await self._call_ollama_local(text, candidates, contexte), candidates)
            if ref:
                self._cache_put(self._reference_cache, cache_key, ref)
                return ref

        self._cache_put(self._reference_cache, cache_key, None)
        return None

    async def extract_biblical_intent(
        self,
        text: str,
        contexte: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Analyse sémantiquement le texte pour détecter si l'orateur a l'intention
        de citer ou de faire allusion à la Bible.

        Returns:
            Dictionnaire {"intent": "biblical", "query": "mots clés nettoyés"} ou None
        """
        logger.info(f"🔍 [Intent Extractor] START for text: '{text}', enabled: {self.enabled}")
        if not self.enabled or not text or len(text.strip()) < 10:
            logger.info("🔍 [Intent Extractor] Bypassed because not enabled or text too short.")
            return None

        cache_key = self._normalize_cache_key(text, "intent")
        if cache_key in self._reference_cache:
            return self._reference_cache[cache_key]

        contexte_block = ""
        if contexte:
            contexte_block = (
                "\n\nCE QUI VIENT D'ETRE DIT (contexte pour t'aider a comprendre de quoi il parle) :\n"
                + "\n".join(f"- {c}" for c in contexte[-3:])
            )

        prompt = (
            f'Phrase a analyser: "{text}"'
            f"{contexte_block}\n\n"
        )

        system_prompt = (
            "Tu es un moteur d'extraction biblique. Ton but est de dire si la phrase prononcée "
            "cite ou fait allusion à la Bible. Si oui, tu dois extraire UNIQUEMENT les mots-clés de l'allusion "
            "présents DANS LA PHRASE, en retirant le bruit de conversation (ex: 'On va lire dans...', 'Le pasteur a dit...'). "
            "N'INVENTE AUCUN MOT. La `query` doit être extraite directement du texte fourni. "
            "Si l'orateur ne fait que mentionner un livre ou donne juste l'heure, c'est 'none'. "
            "Reponds UNIQUEMENT avec un objet JSON valide :\n"
            '{"intent": "biblical" ou "none", "query": "mots-clés extraits ou null"}'
        )

        res = None
        logger.info(f"🔍 [Intent Extractor] Keys: openrouter={bool(self.openrouter_key)}, gemini={bool(self.api_key)}, ollama={self.ollama_active}")
        # 1. OpenRouter
        if self.openrouter_key:
            res = await self._call_openrouter(text, None, contexte, prompt_override=prompt, system_override=system_prompt)
        # 2. Gemini Direct
        elif self.api_key:
            res = await self._call_gemini_direct(text, None, contexte, prompt_override=prompt, system_override=system_prompt)
        # 3. Ollama Local
        elif self.ollama_active:
            res = await self._call_ollama_local(text, None, contexte, prompt_override=prompt, system_override=system_prompt)

        logger.info(f"🤖 [Intent Extractor] Résultat brut IA : {res}")

        return res

    async def _call_openrouter(self, text: str, candidates: Optional[List[Dict[str, Any]]] = None, contexte: Optional[List[str]] = None,
                               prompt_override: Optional[str] = None, system_override: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Appelle l'API OpenRouter pour détecter le verset avec score de confiance"""
        url = "https://openrouter.ai/api/v1/chat/completions"

        prompt = prompt_override or self._build_detection_prompt(text, candidates, contexte)
        system_instruction = system_override or (
            "Tu es un assistant théologique de régie d'église. Analyse le texte et "
            "renvoie la référence biblique correspondante au format français, ainsi qu'un score de confiance "
            "de 0 à 100. Sois très rigoureux. Si le texte ne contient aucune citation ou paraphrase, "
            "renvoie 'reference': null et 'confidence': 0. "
            "Renvoie UNIQUEMENT du JSON valide, sans balise de code markdown."
        )

        headers = {
            "Authorization": f"Bearer {self.openrouter_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:3001",
            "X-Title": "VersePro"
        }

        payload = {
            "model": self.openrouter_model,
            "messages": [
                {
                    "role": "system",
                    "content": system_instruction
                },
                {"role": "user", "content": prompt}
            ],
            "response_format": {"type": "json_object"},
            # La réponse attendue est un JSON minuscule ({"reference","confidence"}).
            # Sans cette borne, OpenRouter réserve le MAXIMUM du modèle (65 535
            # jetons) : le contrôle de crédit refusait la requête (HTTP 402) alors
            # qu'il n'y avait rien à générer, et chaque appel était facturé large.
            "max_tokens": 200,
        }

        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                response = await client.post(url, json=payload, headers=headers)
                if response.status_code == 200:
                    res_json = response.json()
                    choices = res_json.get("choices", [])
                    if choices:
                        content = choices[0].get("message", {}).get("content", "")
                        if content:
                            data = self._decode_json_payload(content)
                            if "intent" in data:
                                return data

                            ref = data.get("reference")
                            conf = data.get("confidence", 95)
                            if ref and ref.strip() and ref.lower() != "null":
                                logger.info(f"🤖 [Agent IA - OpenRouter] Référence détectée: '{ref}' (Confiance: {conf}%)")
                                return {"reference": ref.strip(), "confidence": int(conf)}
                else:
                    logger.error(f"❌ Erreur OpenRouter: HTTP {response.status_code} - {response.text}")
        except Exception as e:
            logger.error(f"❌ Erreur lors de l'appel à OpenRouter: {e}")

        return None

    async def _call_gemini_direct(self, text: str, candidates: Optional[List[Dict[str, Any]]] = None, contexte: Optional[List[str]] = None,
                                  prompt_override: Optional[str] = None, system_override: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Appelle l'API Gemini directe de Google avec score de confiance"""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.gemini_model}:generateContent"
        headers = {"x-goog-api-key": self.api_key, "Content-Type": "application/json"}

        prompt = prompt_override or self._build_detection_prompt(text, candidates, contexte)
        system_instruction = system_override or (
            "Tu es un assistant théologique de régie d'église. Analyse le texte et "
            "renvoie la référence biblique correspondante au format français, ainsi qu'un score de confiance "
            "de 0 à 100. Sois très rigoureux. Si le texte ne contient aucune citation ou paraphrase, "
            "renvoie 'reference': null et 'confidence': 0. "
            "Renvoie UNIQUEMENT du JSON valide, sans balise de code markdown."
        )

        schema = {
            "type": "OBJECT",
            "properties": {
                "reference": {
                    "type": "STRING",
                    "description": "La référence biblique détectée au format standard français, ex: 'Jean 3:16' ou 'Genèse 12:1-3'. Doit être null ou vide si aucune écriture ou histoire biblique n'est citée."
                },
                "confidence": {
                    "type": "INTEGER",
                    "description": "Un score de certitude théologique de 0 à 100 estimant la justesse théologique de la référence (ex: 95)."
                }
            },
            "required": ["reference", "confidence"]
        }

        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }],
            "systemInstruction": {
                "parts": [{"text": system_instruction}]
            },
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": schema
            }
        }

        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                response = await client.post(url, json=payload, headers=headers)
                if response.status_code == 200:
                    res_json = response.json()
                    candidates = res_json.get("candidates", [])
                    if candidates:
                        text_res = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                        if text_res:
                            data = self._decode_json_payload(text_res)
                            if "intent" in data:
                                return data

                            ref = data.get("reference")
                            conf = data.get("confidence", 95)
                            if ref and ref.strip() and ref.lower() != "null":
                                logger.info(f"🤖 [Agent IA - Gemini Direct] Référence détectée: '{ref}' (Confiance: {conf}%)")
                                return {"reference": ref.strip(), "confidence": int(conf)}
                else:
                    logger.error(f"❌ Erreur API Gemini: HTTP {response.status_code} - {response.text}")
        except Exception as e:
            logger.error(f"❌ Erreur lors de l'appel à l'API Gemini directe: {e}")

        return None

    async def _call_ollama_local(self, text: str, candidates: Optional[List[Dict[str, Any]]] = None,
                                 contexte: Optional[List[str]] = None, prompt_override: Optional[str] = None, system_override: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Appelle l'API Ollama locale pour détecter le verset avec score de confiance de façon 100% hors-ligne"""
        url = f"{self.ollama_url}/api/generate"

        prompt = prompt_override or self._build_detection_prompt(text, candidates, contexte)

        system_instruction = system_override or (
            "Tu es un assistant théologique de régie d'église. Analyse le texte et "
            "renvoie la référence biblique correspondante au format français, avec son score de confiance. "
            "Sois très précis. Si le texte ne contient aucune citation, paraphrase "
            "ou référence à une histoire de la Bible, renvoie la propriété 'reference' comme null et 'confidence' comme 0. "
            "Renvoie uniquement du JSON brut, pas de markdown, pas de texte d'explication."
        )

        payload = {
            "model": self.ollama_model,
            "prompt": prompt,
            "system": system_instruction,
            "stream": False,
            "format": "json"
        }

        try:
            # Un modèle local 8B met 10–15 s à répondre (chargement + génération),
            # bien plus que les 6 s d'origine : TOUS les appels expiraient et
            # l'arbitrage local ne rendait jamais rien. Il tourne en tâche de fond,
            # en dernier recours, et sa suggestion part en validation manuelle —
            # il peut donc prendre son temps.
            async with httpx.AsyncClient(timeout=settings.OLLAMA_TIMEOUT) as client:
                response = await client.post(url, json=payload)
                if system_override:
                    logger.info(f"🤖 [Ollama] Status: {response.status_code}, Raw response: {response.text}")
                if response.status_code == 200:
                    res_json = response.json()
                    response_text = res_json.get("response", "")
                    data = self._decode_json_payload(response_text)
                    if "intent" in data:
                        return data

                    ref = data.get("reference")
                    conf = data.get("confidence", 95)
                    if ref and ref.strip() and ref.lower() != "null":
                        logger.info(f"🤖 [Agent IA - Ollama Local] Référence détectée: '{ref}' (Confiance: {conf}%)")
                        return {"reference": ref.strip(), "confidence": int(conf)}
        except Exception as e:
            logger.error(f"❌ Erreur lors de l'appel à Ollama local ({self.ollama_model}): {e}")

        return None

    async def translate_text(self, text: str, target_lang: str) -> Optional[str]:
        """
        Traduit simultanément un segment de texte dans la langue cible spécifiée (en texte brut).
        """
        if not self.enabled or not text or not text.strip() or not target_lang or target_lang.lower() == "fr":
            return None

        cache_key = self._normalize_cache_key(text, f"translate:{target_lang}")
        if cache_key in self._translation_cache:
            return self._translation_cache[cache_key]

        prompt = (
            f"Traduis le texte français suivant (issu d'une prédication orale) en langue '{target_lang}'. "
            "Garde le ton oral, respectueux et conserve la terminologie religieuse/biblique standard. "
            "Réponds UNIQUEMENT avec la traduction, sans aucun commentaire ni balise.\n\n"
            f"Texte: {text}"
        )

        # 1. Utilisation de l'API OpenRouter (si active)
        if self.openrouter_key:
            url = "https://openrouter.ai/api/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.openrouter_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "http://localhost:3001",
                "X-Title": "VersePro"
            }
            payload = {
                "model": self.openrouter_model,
                "messages": [
                    {"role": "system", "content": f"Tu es un traducteur simultané d'église. Traduis le texte fourni en '{target_lang}'. Renvoie UNIQUEMENT la traduction brute, aucun commentaire."},
                    {"role": "user", "content": prompt}
                ]
            }
            try:
                async with httpx.AsyncClient(timeout=3.0) as client:
                    response = await client.post(url, json=payload, headers=headers)
                    if response.status_code == 200:
                        content = response.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                        if content:
                            translated = content.strip()
                            self._cache_put(self._translation_cache, cache_key, translated)
                            return translated
            except Exception as e:
                logger.error(f"❌ Erreur traduction OpenRouter: {e}")

        # 2. Utilisation de l'API Gemini directe
        if self.api_key:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.gemini_model}:generateContent"
            headers = {"x-goog-api-key": self.api_key, "Content-Type": "application/json"}
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "systemInstruction": {"parts": [{"text": f"Tu es un traducteur simultané d'église. Traduis en '{target_lang}' et renvoie uniquement la traduction brute."}]}
            }
            try:
                async with httpx.AsyncClient(timeout=3.0) as client:
                    response = await client.post(url, json=payload, headers=headers)
                    if response.status_code == 200:
                        text_res = response.json().get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                        if text_res:
                            translated = text_res.strip()
                            self._cache_put(self._translation_cache, cache_key, translated)
                            return translated
            except Exception as e:
                logger.error(f"❌ Erreur traduction Gemini Direct: {e}")

        # 3. Fallback sur Ollama local
        if self.ollama_active:
            url = f"{self.ollama_url}/api/generate"
            payload = {
                "model": self.ollama_model,
                "prompt": prompt,
                "system": f"Tu es un traducteur simultané d'église. Traduis en '{target_lang}' et renvoie uniquement la traduction brute.",
                "stream": False
            }
            try:
                async with httpx.AsyncClient(timeout=4.0) as client:
                    response = await client.post(url, json=payload)
                    if response.status_code == 200:
                        response_text = response.json().get("response", "")
                        if response_text:
                            translated = response_text.strip()
                            self._cache_put(self._translation_cache, cache_key, translated)
                            return translated
            except Exception as e:
                logger.error(f"❌ Erreur traduction Ollama: {e}")

        self._cache_put(self._translation_cache, cache_key, None)
        return None

    async def generate_sermon_summary(self, transcript: str) -> Optional[str]:
        """
        Génère un résumé structuré en Markdown d'une transcription de sermon complet (en texte brut).
        """
        self.last_summary_error = ""
        self.last_summary_provider = ""
        # L'état Ollama peut changer après l'initialisation asynchrone ;
        # recalculer ici évite qu'un modèle local prêt soit encore considéré
        # comme « IA désactivée » au premier clic sur Résumer.
        self.refresh_availability()
        if not self.enabled:
            self.last_summary_error = (
                "Aucun moteur IA disponible : renseignez une clé OpenRouter ou Gemini "
                "dans les Paramètres, ou installez Ollama en local."
            )
            return None
        if not transcript or len(transcript.strip()) < 50:
            self.last_summary_error = "Transcription trop courte pour être résumée."
            return None

        cache_key = self._normalize_cache_key(transcript, "summary")
        # On ne relit le cache QUE s'il contient un vrai résumé. Auparavant les
        # échecs y étaient mémorisés eux aussi : une seule panne réseau
        # condamnait définitivement cette transcription, chaque nouvel essai
        # renvoyant l'échec sans même appeler l'IA. Un bouton « Générer » qui ne
        # peut plus jamais aboutir, sans que rien ne l'explique.
        cached = self._summary_cache.get(cache_key)
        if cached:
            return cached

        # Chaque moteur ajoute ici la raison de son échec : sans cela
        # l'opérateur ne voit qu'un « échec de génération » muet.
        echecs: List[str] = []

        prompt = (
            "À partir de la transcription brute suivante d'une prédication de culte, génère un résumé structuré et édifiant "
            "en français au format Markdown. "
            "Le résumé doit être articulé de la façon suivante :\n"
            "1. **Titre** : Un titre inspirant le thème principal.\n"
            "2. **Points clés** : 3 ou 4 idées directrices expliquées brièvement.\n"
            "3. **Versets phares** : Les principaux textes bibliques abordés et leur apport au sermon.\n"
            "4. **Application pratique** : Une recommandation concrète pour la vie quotidienne.\n\n"
            f"Transcription de la prédication :\n\"\"\"\n{transcript}\n\"\"\"\n\n"
            "Réponds en écrivant uniquement le texte rédigé en Markdown standard, sans encapsuler dans du JSON."
        )

        # 1. Moteur local en priorité : une clé cloud ne doit pas faire sortir
        #    une transcription du poste lorsqu'Ollama est prêt. Gemini et
        #    OpenRouter restent des replis explicites, utiles quand l'utilisateur
        #    a choisi le cloud ou quand le modèle local est indisponible.
        if self.ollama_active:
            url = f"{self.ollama_url}/api/generate"
            payload = {
                "model": self.ollama_model,
                "prompt": prompt,
                "system": "Tu es un théologien et rédacteur d'église. Rédige un résumé d'un sermon sous forme de Markdown.",
                "stream": False,
            }
            try:
                async with httpx.AsyncClient(timeout=300.0) as client:
                    response = await client.post(url, json=payload)
                    if response.status_code == 200:
                        response_text = response.json().get("response", "")
                        if response_text:
                            summary = response_text.strip()
                            self.last_summary_provider = "ollama"
                            self._cache_put(self._summary_cache, cache_key, summary)
                            return summary
                        echecs.append("Ollama : réponse vide")
                    else:
                        echecs.append(f"Ollama : HTTP {response.status_code}")
            except Exception as e:
                logger.error(f"❌ Erreur résumé Ollama: {e}")
                echecs.append(f"Ollama : {type(e).__name__}")

        # 2. Utilisation de Gemini Direct (si une clé est renseignée).
        if self.api_key:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.gemini_model}:generateContent"
            headers = {"x-goog-api-key": self.api_key, "Content-Type": "application/json"}
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "systemInstruction": {"parts": [{"text": "Tu es un théologien et rédacteur d'église. Rédige un résumé édifiant et structuré d'un sermon sous forme de Markdown."}]}
            }
            try:
                async with httpx.AsyncClient(timeout=90.0) as client:
                    response = await client.post(url, json=payload, headers=headers)
                    if response.status_code == 200:
                        text_res = response.json().get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                        if text_res:
                            summary = text_res.strip()
                            self.last_summary_provider = "gemini"
                            self._cache_put(self._summary_cache, cache_key, summary)
                            return summary
                        echecs.append("Gemini : réponse vide")
                    else:
                        echecs.append(f"Gemini : HTTP {response.status_code}")
            except Exception as e:
                logger.error(f"❌ Erreur résumé Gemini Direct: {e}")
                echecs.append(f"Gemini : {type(e).__name__}")

        # 3. OpenRouter (dernier recours cloud).
        if self.openrouter_key:
            url = "https://openrouter.ai/api/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.openrouter_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "http://localhost:3001",
                "X-Title": "VersePro"
            }
            payload = {
                "model": self.openrouter_model,
                "messages": [
                    {"role": "system", "content": "Tu es un théologien et rédacteur d'église. Rédige un résumé édifiant et structuré d'un sermon sous forme de Markdown. Ne renvoie aucun autre texte."},
                    {"role": "user", "content": prompt}
                ]
            }
            try:
                # Résumer une prédication entière est une génération longue :
                # 15 s suffisaient à peine, et le délai expirait avant la
                # réponse — ce qui passait ensuite pour une panne définitive.
                async with httpx.AsyncClient(timeout=90.0) as client:
                    response = await client.post(url, json=payload, headers=headers)
                    if response.status_code == 200:
                        content = response.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                        if content:
                            summary = content.strip()
                            self.last_summary_provider = "openrouter"
                            self._cache_put(self._summary_cache, cache_key, summary)
                            return summary
                        echecs.append("OpenRouter : réponse vide")
                    else:
                        echecs.append(f"OpenRouter : HTTP {response.status_code}")
            except Exception as e:
                logger.error(f"❌ Erreur résumé OpenRouter: {e}")
                echecs.append(f"OpenRouter : {type(e).__name__}")

        # Aucun échec n'est mis en cache : la panne d'aujourd'hui ne doit pas
        # interdire la tentative de demain.
        self.last_summary_error = (
            " · ".join(echecs) if echecs
            else "Aucun moteur n'a répondu. Vérifiez la clé API et la connexion."
        )
        logger.warning(f"Résumé impossible — {self.last_summary_error}")
        return None
