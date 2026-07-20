"""Recherche semantique biblique locale via embeddings ONNX optionnels."""

from __future__ import annotations

import hashlib
import json
import os
import threading
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import numpy as np
from loguru import logger

from ..core.config import settings


class LocalSemanticService:
    """Index vectoriel local; le LLM n'intervient qu'apres ce retrieval."""

    def __init__(self, bible_loader, encoder: Any = None, cache_dir: Optional[Path] = None):
        from ..core.config import DATA_DIR
        self.bible_loader = bible_loader
        self.model_name = settings.LOCAL_SEMANTIC_MODEL
        self.active_model: Optional[str] = None if encoder is None else self.model_name
        # Dossier inscriptible (modèle e5 + index téléchargés/construits au 1er lancement).
        self.cache_dir = Path(cache_dir or (DATA_DIR / "semantic"))
        self.encoder = encoder
        self._injected_encoder = encoder is not None  # encodeur de test fourni au constructeur
        self.entries: List[Dict[str, Any]] = []
        self.matrix = np.zeros((0, 0), dtype=np.float32)
        self.initialized = False
        self.indexing = False
        self.indexed_count = 0
        self.last_error = ""
        self._lock = threading.Lock()

    @property
    def _model_cache_dir(self) -> Path:
        return self.cache_dir / "models"

    # Version du schéma d'index : à INCRÉMENTER quand le contenu/format des
    # entrées change à nombre de versets constant (ex. correction « Actes »
    # rangé sous une clé vide, passage aux références en nom complet). Force la
    # reconstruction chez tous les postes, même si le compte n'a pas bougé.
    INDEX_SCHEMA = 2

    def _fingerprint_for(self, model_name: str) -> str:
        version = self.bible_loader.active_version
        corpus = self.bible_loader.versions.get(version, {})
        count = sum(len(verses) for chapters in corpus.values() for verses in chapters.values())
        raw = f"{version}:{count}:{model_name}:s{self.INDEX_SCHEMA}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()[:16]

    @property
    def _index_path(self) -> Path:
        return self.cache_dir / f"index-{self._fingerprint_for(self.model_name)}.npz"

    @property
    def _metadata_path(self) -> Path:
        return self.cache_dir / f"index-{self._fingerprint_for(self.model_name)}.json"

    def _has_index(self, model_name: str) -> bool:
        fp = self._fingerprint_for(model_name)
        return (self.cache_dir / f"index-{fp}.npz").exists() and (self.cache_dir / f"index-{fp}.json").exists()

    # ── Calibration active : chaque encodeur a sa propre échelle de scores ──
    @property
    def active_threshold(self) -> float:
        cal = settings.LOCAL_SEMANTIC_CALIBRATION.get(self.active_model or self.model_name, {})
        return float(cal.get("threshold", settings.LOCAL_SEMANTIC_THRESHOLD))

    @property
    def active_margin(self) -> float:
        cal = settings.LOCAL_SEMANTIC_CALIBRATION.get(self.active_model or self.model_name, {})
        return float(cal.get("margin", settings.LOCAL_SEMANTIC_MARGIN))

    @property
    def active_floor(self) -> float:
        return max(0.45, self.active_threshold - 0.03)

    def _iter_corpus(self) -> Iterable[Dict[str, Any]]:
        version = self.bible_loader.versions.get(self.bible_loader.active_version, {})
        from .verse_parser import format_reference
        for book_abbr, chapters in version.items():
            if not book_abbr:
                continue
            for chapter, verses in chapters.items():
                for verse, text in verses.items():
                    if text and len(text.strip()) >= 12:
                        yield {
                            "reference": format_reference(book_abbr, chapter, verse),
                            "book_abbr": book_abbr,
                            "chapter": int(chapter),
                            "verse_start": int(verse),
                            "verse_end": None,
                            "text": text.strip(),
                        }

    @staticmethod
    def _normalize(matrix: np.ndarray) -> np.ndarray:
        matrix = np.asarray(matrix, dtype=np.float32)
        if matrix.ndim == 1:
            matrix = matrix.reshape(1, -1)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return matrix / norms

    def _encode(self, texts: List[str], kind: str = "passage", progress=None) -> np.ndarray:
        # Sonde de signature : progression (indexation) et kind (query/passage)
        # sont optionnels selon l'encodeur (Qwen/e5 les gèrent, les mocks non).
        for kwargs in (
            {"batch_size": 64, "kind": kind, "progress": progress},
            {"batch_size": 64, "kind": kind},
            {"batch_size": 64},
            {},
        ):
            try:
                vectors = self.encoder.embed(texts, **kwargs)
                break
            except TypeError:
                continue
        return self._normalize(np.asarray(list(vectors), dtype=np.float32))

    def _seed_bundled_index(self) -> None:
        """Copie l'index sémantique livré avec l'application (ressources en
        lecture seule) vers le dossier utilisateur, s'il n'y est pas déjà.

        L'empreinte du nom de fichier (corpus + modèle + schéma) fait foi : un
        index embarqué qui ne correspond plus (autre Bible, autre modèle) est
        simplement ignoré au chargement, et l'indexation locale reprend la main."""
        if self._injected_encoder:
            return  # encodeur de test : l'index embarqué (e5 réel) le contredirait
        try:
            from ..core.config import RESOURCE_DIR
            bundled = RESOURCE_DIR / "data" / "semantic"
            if not bundled.is_dir() or bundled.resolve() == self.cache_dir.resolve():
                return
            import shutil
            for src in bundled.glob("index-*"):
                dst = self.cache_dir / src.name
                if not dst.exists():
                    shutil.copy2(src, dst)
                    logger.info(f"📦 Index sémantique pré-calculé installé : {src.name}")
        except Exception as exc:  # jamais bloquant : au pire on réindexe
            logger.debug(f"Seed d'index embarqué ignoré : {exc}")

    def _make_encoder(self, model_name: str) -> Any:
        if model_name.startswith("arctic"):
            from .arctic_encoder import ArcticOnnxEncoder
            return ArcticOnnxEncoder(cache_dir=self._model_cache_dir / model_name, variant=model_name)
        from .e5_encoder import E5OnnxEncoder
        variant = model_name if model_name in E5OnnxEncoder.VARIANTS else "e5-small"
        return E5OnnxEncoder(cache_dir=self._model_cache_dir / variant, variant=variant)

    def _resolve_encoder(self, allow_download: bool) -> bool:
        """Choisit l'encodeur actif : Qwen préféré, e5-small en secours.

        - encodeur injecté (tests) : conservé tel quel.
        - démarrage sans téléchargement : on privilégie le modèle dont l'INDEX est
          déjà prêt (l'index dépend du modèle : dim 1024 Qwen vs 384 e5, jamais
          interchangeables) ; à défaut, un modèle simplement téléchargé.
        - préparation explicite (allow_download) : on télécharge le préféré, puis
          on bascule sur le secours si le préféré échoue.
        """
        if self.encoder is not None and getattr(self.encoder, "initialized", True):
            return True

        preferred = settings.LOCAL_SEMANTIC_MODEL
        fallback = getattr(settings, "LOCAL_SEMANTIC_FALLBACK", "e5-small")
        order = [preferred] + ([fallback] if fallback and fallback != preferred else [])
        errors: List[str] = []

        # Démarrage : ne réveiller que ce qui est déjà indexé (index + modèle présents).
        if not allow_download:
            for model in order:
                try:
                    enc = self._make_encoder(model)
                except Exception as exc:
                    errors.append(f"{model}: {exc}")
                    continue
                if enc.is_downloaded and self._has_index(model):
                    self.encoder, self.model_name, self.active_model = enc, model, model
                    if enc.load():
                        logger.info(f"🧠 Encodeur sémantique actif : {model} (index prêt)")
                        return True
                    errors.append(f"{model}: chargement échoué ({enc.last_error})")
                    self.encoder = None
            self.last_error = " ; ".join(errors) or "Aucun index sémantique construit ; lancer la préparation."
            return False

        # Préparation explicite : télécharger/charger le préféré, sinon le secours.
        for model in order:
            try:
                enc = self._make_encoder(model)
            except Exception as exc:
                errors.append(f"{model}: {exc}")
                continue
            self.encoder, self.model_name, self.active_model = enc, model, model
            if not enc.is_downloaded:
                logger.info(f"Modèle sémantique {model} manquant, téléchargement…")
                if not enc.download_model():
                    errors.append(f"{model}: téléchargement échoué ({enc.last_error})")
                    self.encoder = None
                    continue
            if enc.load():
                logger.info(f"🧠 Encodeur sémantique actif : {model}")
                return True
            errors.append(f"{model}: chargement échoué ({enc.last_error})")
            self.encoder = None

        self.last_error = " ; ".join(errors) or "Aucun encodeur sémantique disponible."
        return False

    def initialize(self, allow_download: bool = False) -> bool:
        if self.initialized:
            return True
        if not settings.LOCAL_SEMANTIC_ENABLED:
            self.last_error = "Desactive dans les parametres"
            return False
        with self._lock:
            if self.initialized:
                return True
            self.indexing = True
            self.last_error = ""
            try:
                self.cache_dir.mkdir(parents=True, exist_ok=True)

                # 0. Index PRÉ-CALCULÉ livré avec l'application : copié une fois
                #    vers le dossier utilisateur. L'index est identique pour tous
                #    (même Bible, même modèle) — le recalculer sur chaque poste
                #    coûtait ~7,5 min d'onboarding pour rien.
                self._seed_bundled_index()

                # 1. Choix de l'encodeur actif AVANT tout : il fixe self.model_name,
                #    donc le chemin d'index (chaque modèle a son propre index).
                if not self._resolve_encoder(allow_download):
                    return False

                # 2. Index déjà construit pour ce modèle : on le recharge.
                if self._index_path.exists() and self._metadata_path.exists():
                    archive = np.load(self._index_path)
                    self.matrix = self._normalize(archive["matrix"])
                    self.entries = json.loads(self._metadata_path.read_text(encoding="utf-8"))
                    self.initialized = bool(self.entries) and len(self.entries) == len(self.matrix)
                    if self.initialized:
                        self.indexed_count = len(self.entries)
                        logger.info(f"Index semantique local charge: {len(self.entries)} versets ({self.active_model})")
                        return True

                # 3. Au demarrage normal, on ne lance jamais une indexation CPU longue.
                #    Elle vient du bouton de preparation (allow_download) ou d'un encodeur de test.
                if not allow_download and not self._injected_encoder:
                    self.last_error = "Index non construit; lancer la preparation depuis Parametres"
                    return False

                self.entries = list(self._iter_corpus())
                if not self.entries:
                    self.last_error = "Corpus biblique vide"
                    return False

                texts = [entry["text"] for entry in self.entries]
                self.indexed_count = 0

                def _on_progress(done, total):
                    self.indexed_count = done

                self.matrix = self._encode(texts, progress=_on_progress)
                self.indexed_count = len(self.entries)
                # Stocké en float16 : les vecteurs sont normalisés, la demi-précision
                # suffit largement. Mesuré sur l'index e5-base (31 102 × 768) :
                # écart max sur un score 0,0001 — 50 fois moins que notre marge de
                # séparation (0,0051) —, 0/200 changement de meilleur candidat,
                # 200/200 top-5 identiques. Et le fichier passe de 84 à 42 Mo.
                # Au chargement, _normalize repasse en float32.
                np.savez_compressed(self._index_path, matrix=self.matrix.astype(np.float16))
                self._metadata_path.write_text(
                    json.dumps(self.entries, ensure_ascii=False), encoding="utf-8"
                )
                self.initialized = True
                logger.info(f"Index semantique ONNX construit: {len(self.entries)} versets")
                return True
            except Exception as exc:
                self.last_error = str(exc)
                logger.exception("Construction de l'index semantique impossible")
                return False
            finally:
                self.indexing = False

    def search(self, query: str, top_k: Optional[int] = None, min_score: float = 0.0) -> List[Dict[str, Any]]:
        if not self.initialized or self.encoder is None or not query or len(query.split()) < 4:
            return []
        query_vector = self._encode([query], kind="query")[0]
        scores = self.matrix @ query_vector
        count = max(1, min(int(top_k or settings.LOCAL_SEMANTIC_TOP_K), len(scores)))
        indexes = np.argpartition(scores, -count)[-count:]
        indexes = indexes[np.argsort(scores[indexes])[::-1]]
        results = []
        for index in indexes:
            score = float(scores[index])
            if score < min_score:
                continue
            results.append({
                **self.entries[int(index)],
                "score": round(score, 4),
                "confidence": round(score, 4),
                "detection_method": "semantic_local",
                "requires_review": True,
            })
        return results

    def reset(self) -> None:
        """Invalide l'index actif apres un changement de version biblique."""
        self.entries = []
        self.matrix = np.zeros((0, 0), dtype=np.float32)
        self.initialized = False
        self.indexed_count = 0
        self.last_error = "Index a recharger"

    def status(self) -> Dict[str, Any]:
        downloading = False
        download_progress = 0.0
        encoder_error = self.last_error
        
        if self.encoder is not None:
            downloading = getattr(self.encoder, "downloading", False)
            download_progress = getattr(self.encoder, "download_progress", 0.0)
            encoder_error = getattr(self.encoder, "last_error", "") or self.last_error
            
        return {
            "enabled": settings.LOCAL_SEMANTIC_ENABLED,
            "installed": self.initialized,
            "indexing": self.indexing or downloading,
            "downloading": downloading,
            "download_progress": download_progress,
            "model": self.active_model or self.model_name,
            "preferred_model": settings.LOCAL_SEMANTIC_MODEL,
            "using_fallback": bool(self.active_model) and self.active_model != settings.LOCAL_SEMANTIC_MODEL,
            "verses_indexed": self.indexed_count if self.indexing else len(self.entries),
            "verses_total": len(self.entries),
            "threshold": self.active_threshold,
            "last_error": encoder_error,
        }
