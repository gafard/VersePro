"""Tests du retrieval sémantique local (embeddings ONNX via fastembed).

Deux niveaux :
- logique pure (encodeur factice injecté) — tourne partout, y compris en CI ;
- intégration réelle — sautée si le modèle ONNX n'est pas installé localement.
"""

import numpy as np
import pytest

from app.services.semantic_search import LocalSemanticService
from app.services.verse_parser import VerseParserService


class _FakeEncoder:
    """Encodeur déterministe : vecteur = sac de caractères normalisé.
    Suffisant pour vérifier tri, seuils et format de sortie sans modèle."""

    DIM = 64

    def embed(self, texts, batch_size=None):
        for text in texts:
            vec = np.zeros(self.DIM, dtype=np.float32)
            for ch in text.lower():
                vec[ord(ch) % self.DIM] += 1.0
            yield vec


def test_semantic_logic_with_fake_encoder(tmp_path):
    parser = VerseParserService()
    service = LocalSemanticService(parser.bible_loader, encoder=_FakeEncoder(), cache_dir=tmp_path)

    assert service.initialize(allow_download=False) is True
    assert service.initialized and len(service.entries) > 25000

    # Requête = texte exact d'un verset connu -> il doit sortir premier
    verse_text = "Car Dieu a tant aimé le monde qu'il a donné son Fils unique"
    results = service.search(verse_text, top_k=3)
    assert results, "Le retrieval doit renvoyer des candidats"
    top = results[0]
    assert top["detection_method"] == "semantic_local"
    assert top["requires_review"] is True
    assert top["book_abbr"].lower() == "jn" and top["chapter"] == 3 and top["verse_start"] == 16

    # Les requêtes trop courtes sont refusées (ambiguïté)
    assert service.search("dieu est bon") == []

    # Dans la palette manuelle, deux mots sont acceptés : ils n'activent
    # aucune sortie et restent une simple liste de candidats.
    manual = service.search_manual("Dieu amour", top_k=3)
    assert manual
    assert manual[0]["detection_method"] == "manual_semantic"
    assert manual[0]["requires_review"] is True


def test_semantic_real_model_paraphrase():
    """Intégration réelle : nécessite le modèle ONNX préparé (Paramètres -> Préparer)."""
    parser = VerseParserService()
    service = LocalSemanticService(parser.bible_loader)

    if not service.initialize(allow_download=False):
        pytest.skip(f"Modèle sémantique non préparé : {service.last_error}")

    # Paraphrase sans aucun mot-clé de référence : l'étage embeddings doit
    # remonter le récit de la marche sur l'eau dans ses candidats.
    results = service.search("jésus marchait sur la mer pour rejoindre ses disciples dans la barque", top_k=8)
    assert results, "Aucun candidat sémantique"
    refs = {(r["book_abbr"].lower(), r["chapter"]) for r in results}
    assert refs & {("mt", 14), ("mc", 6), ("jn", 6)}, f"Candidats inattendus : {results[:3]}"


def test_e5_encoder_embeddings_are_normalized_and_meaningful():
    """Encodeur léger e5-small : vecteurs normalisés, sémantique cohérente."""
    import numpy as np
    import pytest
    from app.services.e5_encoder import E5OnnxEncoder

    enc = E5OnnxEncoder()
    if not enc.is_downloaded:
        pytest.skip("Modèle e5-small non téléchargé")

    passages = enc.embed(["Dieu est amour.", "L'Éternel est mon berger: je ne manquerai de rien."], kind="passage")
    assert passages.shape[1] == 384
    assert abs(float(np.linalg.norm(passages[0])) - 1.0) < 1e-3

    # Une paraphrase de berger doit être plus proche du Ps 23 que de 1 Jn 4:8
    query = enc.embed(["le seigneur prend soin de moi comme un berger"], kind="query")[0]
    sims = passages @ query
    assert sims[1] > sims[0]


def test_semantic_index_paraphrases_end_to_end():
    """Sur l'index réel (si construit) : les paraphrases célèbres sortent en tête,
    la parole du quotidien reste sous le plancher. La calibration suit l'encodeur
    réellement actif (Qwen ou e5, échelles de scores différentes)."""
    import pytest
    from app.services.verse_parser import VerseParserService
    from app.services.semantic_search import LocalSemanticService

    parser = VerseParserService()
    svc = LocalSemanticService(parser.bible_loader)
    if not svc.initialize(allow_download=False):
        pytest.skip("Index sémantique non construit")

    # Seuils du modèle actif, pas des constantes globales.
    threshold = svc.active_threshold
    floor = svc.active_floor

    top = svc.search("pierre est sorti de la barque et il a marché sur l'eau vers jésus", top_k=1)[0]
    assert top["reference"].lower() == "matthieu 14:29" and top["score"] >= threshold

    top = svc.search("je peux tout faire grâce à celui qui me donne la force", top_k=1)[0]
    assert top["reference"].lower() == "philippiens 4:13"

    # Parole libre : sous le plancher -> jamais projetée ni envoyée à l'arbitre
    noise = svc.search("la réunion de l'équipe technique est prévue mardi prochain à quinze heures", top_k=1)
    assert not noise or noise[0]["score"] < floor
