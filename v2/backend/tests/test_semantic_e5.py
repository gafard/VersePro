import pytest
import numpy as np
from unittest.mock import MagicMock
from app.services.e5_encoder import E5OnnxEncoder
from app.services.semantic_search import LocalSemanticService
from app.services.verse_parser import BibleLoader

class MockEncoder:
    """Mock léger de QwenOnnxEncoder pour éviter les téléchargements lourds en test unitaire."""
    def __init__(self):
        self.initialized = True
        self.downloading = False
        self.download_progress = 100.0
        self.last_error = ""

    def is_downloaded(self) -> bool:
        return True

    def load(self) -> bool:
        return True

    def embed(self, texts: list[str], batch_size: int = 32) -> np.ndarray:
        # Générer des embeddings de taille fixe (ex: 1536)
        # Pour simuler une recherche sémantique cohérente, on fait en sorte que
        # "marcher sur les eaux" et "marcher sur la mer" aient des vecteurs proches.
        np.random.seed(42)
        dim = 1536
        vectors = []
        for text in texts:
            vec = np.random.randn(dim)
            if "mer" in text or "eaux" in text or "eau" in text:
                # Injecter un signal commun pour le concept de marcher sur l'eau
                vec[0] = 5.0
            vec = vec / np.linalg.norm(vec)
            vectors.append(vec)
        return np.vstack(vectors)

@pytest.fixture
def mock_bible_loader():
    loader = MagicMock(spec=BibleLoader)
    loader.active_version = "LSG"
    loader.versions = {
        "LSG": {
            "Mt": {
                "14": {
                    "25": "À la quatrième veille de la nuit, Jésus alla vers eux, marchant sur la mer."
                }
            },
            "Jn": {
                "3": {
                    "16": "Car Dieu a tant aimé le monde qu'il a donné son Fils unique afin que quiconque croit en lui ne périsse point mais qu'il ait la vie éternelle."
                }
            }
        }
    }
    return loader

def test_semantic_service_initialization_with_mock(mock_bible_loader, tmp_path):
    encoder = MockEncoder()
    service = LocalSemanticService(mock_bible_loader, encoder=encoder, cache_dir=tmp_path)
    
    # Act
    success = service.initialize(allow_download=False)
    
    # Assert
    assert success is True
    assert service.initialized is True
    assert service.indexed_count == 2
    assert len(service.entries) == 2
    assert service.matrix.shape == (2, 1536)

def test_semantic_service_search_similarity(mock_bible_loader, tmp_path):
    encoder = MockEncoder()
    service = LocalSemanticService(mock_bible_loader, encoder=encoder, cache_dir=tmp_path)
    service.initialize(allow_download=False)
    
    # Recherche sémantique
    query = "Jésus marchant sur les eaux"
    results = service.search(query, top_k=2)
    
    # Devrait retourner Matthieu 14:25 en premier à cause du mot "eaux" simulant le concept d'eau/mer
    assert len(results) > 0
    assert results[0]["reference"] == "Matthieu 14:25"
    assert results[0]["score"] > 0.0
    assert "mer" in results[0]["text"]

def test_e5_encoder_download_methods():
    # Tester que les propriétés de téléchargement renvoient des valeurs cohérentes pour E5OnnxEncoder
    encoder = E5OnnxEncoder()
    assert isinstance(encoder.is_downloaded, bool)
    assert encoder.downloading is False
