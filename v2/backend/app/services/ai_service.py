import json
import httpx
import asyncio
import re
import unicodedata
from typing import Optional, Dict, Any
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
        # Caches bornés (FIFO) : sans plafond, un culte de 2h avec traduction simultanée
        # ferait croître la mémoire indéfiniment (une entrée par phrase finale)
        self._cache_max_entries = 500
        self._reference_cache: Dict[str, Optional[Dict[str, Any]]] = {}
        self._translation_cache: Dict[str, Optional[str]] = {}
        self._summary_cache: Dict[str, Optional[str]] = {}
        
        # L'agent est activé si on a l'une des clés ou si on a Ollama configuré
        self.enabled = settings.AI_AGENT_ENABLED and (bool(self.openrouter_key) or bool(self.api_key) or bool(self.ollama_url))
        
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
        """Vérifie si Ollama est actif localement"""
        try:
            async with httpx.AsyncClient(timeout=1.0) as client:
                response = await client.get(f"{self.ollama_url}/api/tags")
                if response.status_code == 200:
                    self.ollama_active = True
                    logger.info(f"🤖 [Ollama] Détecté localement sur {self.ollama_url}. Modèle par défaut: {self.ollama_model}")
                    # S'assure que le service est activé
                    self.enabled = True
        except Exception:
            # Silencieux si absent, ce n'est qu'un fallback
            pass

    async def detect_bible_reference(self, text: str) -> Optional[Dict[str, Any]]:
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

        cache_key = self._normalize_cache_key(text, "reference")
        if cache_key in self._reference_cache:
            return self._reference_cache[cache_key]
            
        # 1. OpenRouter
        if self.openrouter_key:
            ref = await self._call_openrouter(text)
            if ref:
                self._cache_put(self._reference_cache, cache_key, ref)
                return ref
                
        # 2. Gemini Direct
        if self.api_key:
            ref = await self._call_gemini_direct(text)
            if ref:
                self._cache_put(self._reference_cache, cache_key, ref)
                return ref
                
        # 3. Ollama Local
        if self.ollama_active:
            ref = await self._call_ollama_local(text)
            if ref:
                self._cache_put(self._reference_cache, cache_key, ref)
                return ref

        self._cache_put(self._reference_cache, cache_key, None)
        return None
        
    async def _call_openrouter(self, text: str) -> Optional[Dict[str, Any]]:
        """Appelle l'API OpenRouter pour détecter le verset avec score de confiance"""
        url = "https://openrouter.ai/api/v1/chat/completions"
        
        prompt = (
            "Analyse la transcription suivante d'un sermon oral et détermine si l'orateur cite, "
            "paraphrase ou fait référence de manière évidente à un livre, chapitre ou verset de la Bible. "
            "Extrais uniquement le passage le plus précis mentionné ou sous-entendu.\n\n"
            f"Transcription: \"{text}\"\n\n"
            "Réponds UNIQUEMENT sous forme d'un objet JSON valide contenant :\n"
            "- 'reference': la référence biblique (ex: 'Jean 3:16') ou null si aucune,\n"
            "- 'confidence': un score entier de 0 à 100 de certitude théologique (ex: 98)."
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
                    "content": (
                        "Tu es un assistant théologique de régie d'église. Analyse le texte et "
                        "renvoie la référence biblique correspondante au format français, ainsi qu'un score de confiance "
                        "de 0 à 100. Sois très rigoureux. Si le texte ne contient aucune citation ou paraphrase, "
                        "renvoie 'reference': null et 'confidence': 0. "
                        "Renvoie UNIQUEMENT du JSON valide, sans balise de code markdown."
                    )
                },
                {"role": "user", "content": prompt}
            ],
            "response_format": {"type": "json_object"}
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
        
    async def _call_gemini_direct(self, text: str) -> Optional[Dict[str, Any]]:
        """Appelle l'API Gemini directe de Google avec score de confiance"""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.gemini_model}:generateContent?key={self.api_key}"
        
        prompt = (
            "Analyse la transcription suivante d'un sermon oral et détermine si l'orateur cite, "
            "paraphrase ou fait référence de manière évidente à un livre, chapitre ou verset de la Bible. "
            "Extrais uniquement le passage le plus précis mentionné ou sous-entendu.\n\n"
            f"Transcription: \"{text}\""
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
                "parts": [{"text": (
                    "Tu es un assistant théologique de régie d'église. Analyse le texte et "
                    "renvoie la référence biblique correspondante au format français, ainsi qu'un score de confiance "
                    "de 0 à 100. Sois très rigoureux. Si le texte ne contient aucune citation, paraphrase "
                    "ou référence à une histoire de la Bible, renvoie la propriété 'reference' comme null et 'confidence' comme 0."
                )}]
            },
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": schema
            }
        }
        
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                response = await client.post(url, json=payload)
                if response.status_code == 200:
                    res_json = response.json()
                    candidates = res_json.get("candidates", [])
                    if candidates:
                        text_res = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                        if text_res:
                            data = self._decode_json_payload(text_res)
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

    async def _call_ollama_local(self, text: str) -> Optional[Dict[str, Any]]:
        """Appelle l'API Ollama locale pour détecter le verset avec score de confiance de façon 100% hors-ligne"""
        url = f"{self.ollama_url}/api/generate"
        
        prompt = (
            "Analyse la transcription suivante d'un sermon oral et détermine si l'orateur cite, "
            "paraphrase ou fait référence de manière évidente à un livre, chapitre ou verset de la Bible. "
            "Extrais uniquement le passage le plus précis mentionné ou sous-entendu.\n\n"
            f"Transcription: \"{text}\"\n\n"
            "Réponds uniquement sous forme d'un objet JSON valide contenant :\n"
            "- 'reference': la référence biblique (ex: 'Jean 3:16') ou null,\n"
            "- 'confidence': un score entier de 0 à 100 de certitude théologique (ex: 95)."
        )
        
        system_instruction = (
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
            async with httpx.AsyncClient(timeout=6.0) as client:
                response = await client.post(url, json=payload)
                if response.status_code == 200:
                    res_json = response.json()
                    response_text = res_json.get("response", "")
                    if response_text:
                        data = self._decode_json_payload(response_text)
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
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.gemini_model}:generateContent?key={self.api_key}"
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "systemInstruction": {"parts": [{"text": f"Tu es un traducteur simultané d'église. Traduis en '{target_lang}' et renvoie uniquement la traduction brute."}]}
            }
            try:
                async with httpx.AsyncClient(timeout=3.0) as client:
                    response = await client.post(url, json=payload)
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
        if not self.enabled or not transcript or len(transcript.strip()) < 50:
            return None

        cache_key = self._normalize_cache_key(transcript, "summary")
        if cache_key in self._summary_cache:
            return self._summary_cache[cache_key]

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
                    {"role": "system", "content": "Tu es un théologien et rédacteur d'église. Rédige un résumé édifiant et structuré d'un sermon sous forme de Markdown. Ne renvoie aucun autre texte."},
                    {"role": "user", "content": prompt}
                ]
            }
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    response = await client.post(url, json=payload, headers=headers)
                    if response.status_code == 200:
                        content = response.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                        if content:
                            summary = content.strip()
                            self._cache_put(self._summary_cache, cache_key, summary)
                            return summary
            except Exception as e:
                logger.error(f"❌ Erreur résumé OpenRouter: {e}")

        # 2. Utilisation de l'API Gemini directe
        if self.api_key:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.gemini_model}:generateContent?key={self.api_key}"
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "systemInstruction": {"parts": [{"text": "Tu es un théologien et rédacteur d'église. Rédige un résumé édifiant et structuré d'un sermon sous forme de Markdown."}]}
            }
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    response = await client.post(url, json=payload)
                    if response.status_code == 200:
                        text_res = response.json().get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                        if text_res:
                            summary = text_res.strip()
                            self._cache_put(self._summary_cache, cache_key, summary)
                            return summary
            except Exception as e:
                logger.error(f"❌ Erreur résumé Gemini Direct: {e}")

        # 3. Fallback sur Ollama local
        if self.ollama_active:
            url = f"{self.ollama_url}/api/generate"
            payload = {
                "model": self.ollama_model,
                "prompt": prompt,
                "system": "Tu es un théologien et rédacteur d'église. Rédige un résumé d'un sermon sous forme de Markdown.",
                "stream": False
            }
            try:
                async with httpx.AsyncClient(timeout=20.0) as client:
                    response = await client.post(url, json=payload)
                    if response.status_code == 200:
                        response_text = response.json().get("response", "")
                        if response_text:
                            summary = response_text.strip()
                            self._cache_put(self._summary_cache, cache_key, summary)
                            return summary
            except Exception as e:
                logger.error(f"❌ Erreur résumé Ollama: {e}")

        self._cache_put(self._summary_cache, cache_key, None)
        return None
