import os
import shutil
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional
import numpy as np
from loguru import logger

class QwenOnnxEncoder:
    """
    Encodeur sémantique local utilisant le modèle Qwen3-Embedding-0.6B quantifié au format ONNX.
    Fonctionne 100% hors-ligne après téléchargement initial.
    """
    
    REPO_ID = "onnx-community/Qwen3-Embedding-0.6B-ONNX"
    REQUIRED_FILES = [
        "onnx/model_quantized.onnx",
        "tokenizer.json",
        "tokenizer_config.json",
        "special_tokens_map.json"
    ]

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or Path(__file__).resolve().parents[2] / "data" / "semantic" / "models" / "qwen3"
        self.model_path = self.cache_dir / "onnx" / "model_quantized.onnx"
        self.tokenizer_path = self.cache_dir / "tokenizer.json"
        
        self.session = None
        self.tokenizer = None
        self._lock = threading.Lock()
        self.initialized = False
        self.download_progress = 0.0
        self.downloading = False
        self.last_error = ""

    @property
    def is_downloaded(self) -> bool:
        """Vérifie si tous les fichiers requis sont présents en local."""
        return self.model_path.exists() and self.tokenizer_path.exists()

    def download_model(self, force: bool = False) -> bool:
        """Télécharge les fichiers du modèle depuis Hugging Face Hub."""
        if self.is_downloaded and not force:
            logger.info("Les fichiers du modèle Qwen ONNX sont déjà présents en local.")
            return True

        self.downloading = True
        self.download_progress = 0.0
        self.last_error = ""
        logger.info(f"Début du téléchargement du modèle Qwen ONNX depuis {self.REPO_ID}...")

        try:
            from huggingface_hub import hf_hub_download
            
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            
            total_files = len(self.REQUIRED_FILES)
            for idx, filename in enumerate(self.REQUIRED_FILES):
                logger.info(f"Téléchargement de {filename}...")
                hf_hub_download(
                    repo_id=self.REPO_ID,
                    filename=filename,
                    local_dir=str(self.cache_dir),
                    local_dir_use_symlinks=False
                )
                self.download_progress = (idx + 1) / total_files * 100
                
            logger.info("Téléchargement du modèle Qwen ONNX terminé avec succès.")
            self.downloading = False
            return True
        except Exception as e:
            self.last_error = str(e)
            logger.error(f"Erreur lors du téléchargement du modèle Qwen ONNX: {e}")
            self.downloading = False
            return False

    def load(self) -> bool:
        """Charge le tokenizer et la session ONNX Runtime."""
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
                
                logger.info("Chargement du tokenizer Qwen...")
                self.tokenizer = Tokenizer.from_file(str(self.tokenizer_path))
                
                # Configuration optimisée pour l'inférence CPU
                opts = ort.SessionOptions()
                opts.intra_op_num_threads = max(1, min(os.cpu_count() or 1, 8))
                opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
                
                logger.info(f"Chargement de la session ONNX Runtime ({self.model_path})...")
                self.session = ort.InferenceSession(
                    str(self.model_path),
                    sess_options=opts,
                    providers=['CPUExecutionProvider']
                )
                self.initialized = True
                logger.info("Modèle Qwen ONNX chargé avec succès.")
                return True
            except Exception as e:
                self.last_error = str(e)
                logger.error(f"Erreur d'initialisation de l'encodeur sémantique Qwen: {e}")
                return False

    def embed(self, texts: List[str], batch_size: int = 32) -> np.ndarray:
        """Calcule les vecteurs d'embeddings pour une liste de phrases."""
        if not self.initialized and not self.load():
            raise RuntimeError(f"Encodeur non initialisé: {self.last_error}")

        all_embeddings = []
        
        # Obtenir les noms des entrées attendues
        session_inputs = [i.name for i in self.session.get_inputs()]
        
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i:i+batch_size]
            
            # Encoder les textes avec le tokenizer
            encodings = [self.tokenizer.encode(t) for t in batch_texts]
            
            # Déterminer la longueur maximale du lot pour le padding
            max_len = max(len(enc.ids) for enc in encodings)
            
            # Construire les tenseurs d'entrée avec padding manuel
            batch_ids = []
            batch_mask = []
            
            for enc in encodings:
                pad_len = max_len - len(enc.ids)
                batch_ids.append(enc.ids + [self.tokenizer.token_to_id("<|endoftext|>") or 0] * pad_len)
                batch_mask.append(enc.attention_mask + [0] * pad_len)
                
            input_ids = np.array(batch_ids, dtype=np.int64)
            attention_mask = np.array(batch_mask, dtype=np.int64)
            
            inputs = {
                'input_ids': input_ids,
                'attention_mask': attention_mask
            }
            
            if 'token_type_ids' in session_inputs:
                inputs['token_type_ids'] = np.zeros_like(input_ids)
                
            # Exécuter l'inférence
            outputs = self.session.run(None, inputs)
            last_hidden_state = outputs[0]  # Shape: (batch, seq_len, hidden)
            
            # Mean pooling pondéré par l'attention_mask
            attention_mask_expanded = np.expand_dims(attention_mask, axis=-1)
            sum_embeddings = np.sum(last_hidden_state * attention_mask_expanded, axis=1)
            sum_mask = np.clip(np.sum(attention_mask_expanded, axis=1), a_min=1e-9, a_max=None)
            mean_embeddings = sum_embeddings / sum_mask
            
            # Normalisation L2
            norms = np.linalg.norm(mean_embeddings, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            normalized = mean_embeddings / norms
            
            all_embeddings.append(normalized)
            
        return np.vstack(all_embeddings)
