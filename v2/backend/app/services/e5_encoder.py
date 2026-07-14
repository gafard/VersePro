"""
Encodeur sémantique léger : intfloat/multilingual-e5-small quantisé ONNX.

Le « petit frère » de l'encodeur Qwen3 (~118 Mo contre ~640 Mo, dim 384
contre 1024) : qualité de recherche multilingue excellente, inférence CPU
5 à 10 fois plus rapide — le bon défaut pour le MacBook d'un bénévole.
Même interface que QwenOnnxEncoder (is_downloaded / download_model / load /
embed) pour être interchangeable dans LocalSemanticService.

Spécification e5 : préfixes « query: » / « passage: » obligatoires,
mean pooling masqué, normalisation L2.
"""

import os
import threading
import urllib.request
from pathlib import Path
from typing import List, Optional

import numpy as np
from loguru import logger


class E5OnnxEncoder:
    REPO_URL = "https://huggingface.co/Xenova/multilingual-e5-small/resolve/main"
    REQUIRED_FILES = {
        "model_quantized.onnx": "onnx/model_quantized.onnx",
        "tokenizer.json": "tokenizer.json",
    }

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or Path(__file__).resolve().parents[2] / "data" / "semantic" / "models" / "e5-small"
        self.model_path = self.cache_dir / "model_quantized.onnx"
        self.tokenizer_path = self.cache_dir / "tokenizer.json"

        self.session = None
        self.tokenizer = None
        self._lock = threading.Lock()
        self.initialized = False
        self.downloading = False
        self.download_progress = 0.0
        self.last_error = ""

    @property
    def is_downloaded(self) -> bool:
        return self.model_path.exists() and self.tokenizer_path.exists()

    def download_model(self, force: bool = False) -> bool:
        if self.is_downloaded and not force:
            return True
        self.downloading = True
        self.download_progress = 0.0
        self.last_error = ""
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            total = len(self.REQUIRED_FILES)
            for idx, (local_name, remote_path) in enumerate(self.REQUIRED_FILES.items()):
                dest = self.cache_dir / local_name
                if not dest.exists():
                    logger.info(f"📥 Téléchargement e5-small : {local_name}")
                    
                    def progress_hook(count, block_size, total_size):
                        if total_size > 0:
                            percent = min(100.0, count * block_size * 100.0 / total_size)
                            # Division de la progression globale sur le nombre de fichiers
                            self.download_progress = (idx * (100.0 / total)) + (percent / total)
                        else:
                            self.download_progress = (idx * (100.0 / total))
                            
                    urllib.request.urlretrieve(
                        f"{self.REPO_URL}/{remote_path}", 
                        str(dest) + ".part",
                        reporthook=progress_hook
                    )
                    os.replace(str(dest) + ".part", dest)
                self.download_progress = (idx + 1) / total * 100
            logger.info("✅ Modèle e5-small téléchargé")
            return True
        except Exception as e:
            self.last_error = str(e)
            logger.error(f"❌ Téléchargement e5-small échoué : {e}")
            return False
        finally:
            self.downloading = False

    def load(self) -> bool:
        if self.initialized:
            return True
        if not self.is_downloaded:
            self.last_error = "Modèle non téléchargé."
            return False
        with self._lock:
            if self.initialized:
                return True
            try:
                import onnxruntime as ort
                from tokenizers import Tokenizer

                self.tokenizer = Tokenizer.from_file(str(self.tokenizer_path))
                self.tokenizer.enable_truncation(max_length=192)

                opts = ort.SessionOptions()
                opts.intra_op_num_threads = max(1, min(os.cpu_count() or 1, 8))
                opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
                self.session = ort.InferenceSession(
                    str(self.model_path), sess_options=opts, providers=["CPUExecutionProvider"]
                )
                self.initialized = True
                logger.info("🧠 Encodeur e5-small chargé")
                return True
            except Exception as e:
                self.last_error = str(e)
                logger.error(f"❌ Chargement e5-small impossible : {e}")
                return False

    def embed(self, texts: List[str], batch_size: int = 64, kind: str = "passage") -> np.ndarray:
        """Vecteurs normalisés. `kind` ∈ {query, passage} — préfixe e5 obligatoire."""
        if not self.initialized and not self.load():
            raise RuntimeError(f"Encodeur non initialisé: {self.last_error}")

        prefix = "query: " if kind == "query" else "passage: "
        session_inputs = [i.name for i in self.session.get_inputs()]
        pad_id = self.tokenizer.token_to_id("<pad>") or 0
        out = []

        for i in range(0, len(texts), batch_size):
            encs = self.tokenizer.encode_batch([prefix + t for t in texts[i:i + batch_size]])
            max_len = max(len(e.ids) for e in encs)
            ids = np.full((len(encs), max_len), pad_id, dtype=np.int64)
            mask = np.zeros((len(encs), max_len), dtype=np.int64)
            for row, e in enumerate(encs):
                ids[row, :len(e.ids)] = e.ids
                mask[row, :len(e.ids)] = e.attention_mask

            feeds = {"input_ids": ids, "attention_mask": mask}
            if "token_type_ids" in session_inputs:
                feeds["token_type_ids"] = np.zeros_like(ids)

            hidden = self.session.run(None, feeds)[0]
            m = np.expand_dims(mask, -1).astype(np.float32)
            pooled = (hidden * m).sum(axis=1) / np.clip(m.sum(axis=1), 1e-9, None)
            norms = np.linalg.norm(pooled, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            out.append(pooled / norms)

        return np.vstack(out).astype(np.float32)
