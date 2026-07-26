"""
Encodeur sémantique Snowflake Arctic Embed 2.0 (m-v2.0) quantisé ONNX.

Candidat évalué face à e5-base. Contrairement à Qwen3 (génératif détourné, qui
faisait PIRE qu'e5-small), c'est un vrai modèle de RECHERCHE, entraîné pour le
multilingue et mesuré fort sur le français (CLEF, MIRACL). Apache 2.0.

Deux différences de contrat avec e5 — s'y tromper ruine la qualité :
  • pooling CLS (premier jeton), et non mean pooling masqué ;
  • préfixe « query: » sur la REQUÊTE uniquement, rien sur les passages
    (e5 préfixe les deux côtés).

Même interface que E5OnnxEncoder (is_downloaded / download_model / load /
embed(kind=…)) pour rester interchangeable dans LocalSemanticService.
"""

import os
import threading
import urllib.request
from pathlib import Path
from typing import List, Optional

import numpy as np
from loguru import logger


class ArcticOnnxEncoder:
    REPO_URL = "https://huggingface.co/Snowflake/snowflake-arctic-embed-m-v2.0/resolve/main"
    REQUIRED_FILES = {
        "model_quantized.onnx": "onnx/model_quantized.onnx",
        "tokenizer.json": "tokenizer.json",
    }

    def __init__(self, cache_dir: Optional[Path] = None, variant: str = "arctic-m-v2"):
        self.variant = variant
        self.cache_dir = cache_dir or Path(__file__).resolve().parents[2] / "data" / "semantic" / "models" / variant
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
                    logger.info(f"📥 Téléchargement {self.variant} : {local_name}")

                    def progress_hook(count, block_size, total_size):
                        if total_size > 0:
                            pct = min(100.0, count * block_size * 100.0 / total_size)
                            self.download_progress = (idx * (100.0 / total)) + (pct / total)

                    try:
                        urllib.request.urlretrieve(
                            f"{self.REPO_URL}/{remote_path}", str(dest) + ".part", reporthook=progress_hook
                        )
                    except Exception as ssl_err:
                        logger.warning(f"Tentative de secours SSL pour arctic : {ssl_err}")
                        import ssl
                        ctx = ssl.create_default_context()
                        ctx.check_hostname = False
                        ctx.verify_mode = ssl.CERT_NONE
                        opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))
                        urllib.request.install_opener(opener)
                        urllib.request.urlretrieve(
                            f"{self.REPO_URL}/{remote_path}", str(dest) + ".part", reporthook=progress_hook
                        )
                    os.replace(str(dest) + ".part", dest)

                self.download_progress = (idx + 1) / total * 100
            logger.info(f"✅ Modèle {self.variant} téléchargé")
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

    def embed(self, texts: List[str], batch_size: int = 32, kind: str = "passage", progress=None) -> np.ndarray:
        """Vecteurs normalisés (dim 768). Pooling CLS ; préfixe sur la requête seule."""
        if not self.initialized and not self.load():
            raise RuntimeError(f"Encodeur non initialisé: {self.last_error}")

        prefix = "query: " if kind == "query" else ""
        # 305 M paramètres : des lots trop gros font exploser les activations et
        # le processus se fait tuer sans trace (constaté à 64). On borne.
        batch_size = max(1, min(batch_size, 12))
        input_names = {i.name for i in self.session.get_inputs()}
        pad_id = self.tokenizer.token_to_id("<pad>")
        if pad_id is None:
            pad_id = self.tokenizer.token_to_id("[PAD]") or 0
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
            if "token_type_ids" in input_names:
                feeds["token_type_ids"] = np.zeros_like(ids)

            hidden = self.session.run(None, feeds)[0]
            # Pooling CLS : le premier jeton porte la représentation de phrase.
            pooled = hidden[:, 0].astype(np.float32)
            norms = np.linalg.norm(pooled, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            out.append(pooled / norms)
            if progress:
                progress(min(i + batch_size, len(texts)), len(texts))

        return np.vstack(out).astype(np.float32)
