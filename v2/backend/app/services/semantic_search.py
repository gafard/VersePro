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
        self.bible_loader = bible_loader
        self.model_name = settings.LOCAL_SEMANTIC_MODEL
        self.cache_dir = Path(cache_dir or Path(__file__).resolve().parents[2] / "data" / "semantic")
        self.encoder = encoder
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

    @property
    def _fingerprint(self) -> str:
        version = self.bible_loader.active_version
        corpus = self.bible_loader.versions.get(version, {})
        count = sum(len(verses) for chapters in corpus.values() for verses in chapters.values())
        raw = f"{version}:{count}:{self.model_name}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()[:16]

    @property
    def _index_path(self) -> Path:
        return self.cache_dir / f"index-{self._fingerprint}.npz"

    @property
    def _metadata_path(self) -> Path:
        return self.cache_dir / f"index-{self._fingerprint}.json"

    def _iter_corpus(self) -> Iterable[Dict[str, Any]]:
        version = self.bible_loader.versions.get(self.bible_loader.active_version, {})
        for book_abbr, chapters in version.items():
            if not book_abbr:
                continue
            for chapter, verses in chapters.items():
                for verse, text in verses.items():
                    if text and len(text.strip()) >= 12:
                        yield {
                            "reference": f"{book_abbr} {chapter}:{verse}",
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

    def _encode(self, texts: List[str], kind: str = "passage") -> np.ndarray:
        try:
            vectors = self.encoder.embed(texts, batch_size=256, kind=kind)
        except TypeError:  # encodeurs sans notion requête/passage (Qwen, tests)
            try:
                vectors = self.encoder.embed(texts, batch_size=256)
            except TypeError:
                vectors = self.encoder.embed(texts)
        return self._normalize(np.asarray(list(vectors), dtype=np.float32))

    def _load_encoder(self, allow_download: bool) -> bool:
        if self.encoder is not None:
            return True
        try:
            if self.model_name == "e5-small":
                from .e5_encoder import E5OnnxEncoder
                encoder = E5OnnxEncoder(cache_dir=self.cache_dir / "models" / "e5-small")
            else:
                from .qwen_encoder import QwenOnnxEncoder
                encoder = QwenOnnxEncoder(cache_dir=self.cache_dir / "models" / "qwen3")
            
            if not encoder.is_downloaded:
                if not allow_download:
                    self.last_error = "Modèle Qwen ONNX non téléchargé."
                    return False
                logger.info("Modèle Qwen ONNX manquant, lancement du téléchargement...")
                success = encoder.download_model()
                if not success:
                    self.last_error = f"Échec du téléchargement: {encoder.last_error}"
                    return False
            
            success = encoder.load()
            if not success:
                self.last_error = f"Échec du chargement: {encoder.last_error}"
                return False
                
            self.encoder = encoder
            return True
        except Exception as exc:
            self.last_error = str(exc)
            logger.warning(f"Recherche sémantique locale Qwen indisponible: {exc}")
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
                if self._index_path.exists() and self._metadata_path.exists():
                    archive = np.load(self._index_path)
                    self.matrix = self._normalize(archive["matrix"])
                    self.entries = json.loads(self._metadata_path.read_text(encoding="utf-8"))
                    self.initialized = (
                        bool(self.entries)
                        and len(self.entries) == len(self.matrix)
                        and self._load_encoder(allow_download)
                    )
                    if self.initialized:
                        self.indexed_count = len(self.entries)
                        logger.info(f"Index semantique local charge: {len(self.entries)} versets")
                        return True

                # Au demarrage normal, on ne lance jamais une indexation CPU longue.
                # Elle doit venir du bouton de preparation explicite ou d'un encodeur de test injecte.
                if not allow_download and self.encoder is None:
                    self.last_error = "Index non construit; lancer la preparation depuis Parametres"
                    return False

                if not self._load_encoder(allow_download):
                    return False
                self.entries = list(self._iter_corpus())
                if not self.entries:
                    self.last_error = "Corpus biblique vide"
                    return False

                texts = [entry["text"] for entry in self.entries]
                self.matrix = self._encode(texts)
                self.indexed_count = len(self.entries)
                np.savez_compressed(self._index_path, matrix=self.matrix)
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
            "model": self.model_name,
            "verses_indexed": self.indexed_count if self.indexing else len(self.entries),
            "verses_total": len(self.entries),
            "threshold": settings.LOCAL_SEMANTIC_THRESHOLD,
            "last_error": encoder_error,
        }
