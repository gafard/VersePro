import asyncio

import numpy as np

from app.services.ai_service import AIService
from app.services.semantic_search import LocalSemanticService


class FakeEncoder:
    def embed(self, texts):
        vectors = {
            "Dieu a tant aime le monde": [1.0, 0.0, 0.0],
            "Le Seigneur est mon berger": [0.0, 1.0, 0.0],
        }
        for text in texts:
            lower = text.lower()
            if "monde" in lower or "aime" in lower:
                yield np.array(vectors["Dieu a tant aime le monde"], dtype=np.float32)
            elif "berger" in lower:
                yield np.array(vectors["Le Seigneur est mon berger"], dtype=np.float32)
            else:
                yield np.array([0.0, 0.0, 1.0], dtype=np.float32)


class FakeBibleLoader:
    active_version = "LSG"
    versions = {
        "LSG": {
            "Jn": {3: {16: "Dieu a tant aime le monde qu'il a donne son Fils unique."}},
            "Ps": {23: {1: "Le Seigneur est mon berger, je ne manquerai de rien."}},
        }
    }


def test_local_semantic_search_ranks_real_verse(tmp_path):
    service = LocalSemanticService(FakeBibleLoader(), encoder=FakeEncoder(), cache_dir=tmp_path)
    assert service.initialize(allow_download=False)

    results = service.search("Il a tellement aime le monde qu'il a donne son fils", top_k=2)

    assert results[0]["reference"] == "Jean 3:16"
    assert results[0]["requires_review"] is True
    assert results[0]["detection_method"] == "semantic_local"


def test_ai_rejects_reference_outside_local_candidates():
    service = AIService.__new__(AIService)
    candidate = {"reference": "Jn 3:16", "text": "Dieu a tant aime le monde", "score": 0.81}

    rejected = service._validate_candidate_result(
        {"reference": "Apocalypse 22:21", "confidence": 99}, [candidate]
    )
    accepted = service._validate_candidate_result(
        {"reference": "Jn 3:16", "confidence": 92}, [candidate]
    )

    assert rejected is None
    assert accepted["reference"] == "Jn 3:16"
    assert accepted["candidate_validated"] is True


