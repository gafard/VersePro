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
from .download_utils import download_file, verify_sha256
from pathlib import Path
from typing import List, Optional

import numpy as np
from loguru import logger


class E5OnnxEncoder:
    # Variantes de la MÊME famille e5 (mêmes préfixes query:/passage:, même mean
    # pooling masqué) : seule la capacité change. Permet de comparer à variable
    # isolée — small (118 Mo, dim 384) vs base (265 Mo, dim 768).
    VARIANTS = {
        "e5-small": {
            "url": "https://huggingface.co/Xenova/multilingual-e5-small/resolve/761b726dd34fb83930e26aab4e9ac3899aa1fa78",
            "sha256": {
                "model_quantized.onnx": "f80102d3f2a1229f387d3c81909990d8945513e347b0eab049f7de3c6f98c193",
                "tokenizer.json": "0b44a9d7b51c3c62626640cda0e2c2f70fdacdc25bbbd68038369d14ebdf4c39",
            },
        },
        "e5-base": {
            "url": "https://huggingface.co/Xenova/multilingual-e5-base/resolve/1ec9243030a27d1a115d5c340572074c125b58b2",
            "sha256": {
                "model_quantized.onnx": "df7a9a29309e3ad491e1783adf8baee710262cc06079c7cbab63c630277fac94",
                "tokenizer.json": "62c24cdc13d4c9952d63718d6c9fa4c287974249e16b7ade6d5a85e7bbb75626",
            },
        },
    }
    REPO_URL = VARIANTS["e5-small"]["url"]
    REQUIRED_FILES = {
        "model_quantized.onnx": "onnx/model_quantized.onnx",
        "tokenizer.json": "tokenizer.json",
    }

    def __init__(self, cache_dir: Optional[Path] = None, variant: str = "e5-small"):
        self.variant = variant if variant in self.VARIANTS else "e5-small"
        self.REPO_URL = self.VARIANTS[self.variant]["url"]
        self.HASHES = self.VARIANTS[self.variant]["sha256"]
        self.cache_dir = cache_dir or Path(__file__).resolve().parents[2] / "data" / "semantic" / "models" / self.variant
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
                valid_existing = False
                if dest.exists() and not force:
                    try:
                        verify_sha256(dest, self.HASHES[local_name])
                        valid_existing = True
                    except ValueError:
                        logger.warning(
                            f"⚠️ Fichier {self.variant}/{local_name} invalide, remplacement sécurisé"
                        )

                if not valid_existing:
                    logger.info(f"📥 Téléchargement {self.variant} : {local_name}")

                    def progress_hook(received, total_size):
                        if total_size > 0:
                            percent = min(100.0, received * 100.0 / total_size)
                            # Division de la progression globale sur le nombre de fichiers
                            self.download_progress = (idx * (100.0 / total)) + (percent / total)
                        else:
                            self.download_progress = (idx * (100.0 / total))

                    partial = Path(str(dest) + ".part")
                    try:
                        download_file(
                            f"{self.REPO_URL}/{remote_path}",
                            partial,
                            progress_hook,
                        )
                        verify_sha256(partial, self.HASHES[local_name])
                        os.replace(partial, dest)
                    finally:
                        partial.unlink(missing_ok=True)

                self.download_progress = (idx + 1) / total * 100
            logger.info(f"✅ Modèle {self.variant} téléchargé et vérifié")
            return True
        except Exception as e:
            self.last_error = str(e)
            logger.error(f"❌ Téléchargement {self.variant} échoué : {e}")
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
                for local_name in self.REQUIRED_FILES:
                    verify_sha256(self.cache_dir / local_name, self.HASHES[local_name])
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
                logger.info(f"🧠 Encodeur {self.variant} chargé")
                return True
            except Exception as e:
                self.last_error = str(e)
                logger.error(f"❌ Chargement {self.variant} impossible : {e}")
                return False

    def embed(self, texts: List[str], batch_size: int = 64, kind: str = "passage", progress=None) -> np.ndarray:
        """Vecteurs normalisés. `kind` ∈ {query, passage} — préfixe e5 obligatoire.
        `progress(done, total)` est rappelé après chaque lot (barre d'indexation)."""
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
            if progress:
                progress(min(i + batch_size, len(texts)), len(texts))

        return np.vstack(out).astype(np.float32)
