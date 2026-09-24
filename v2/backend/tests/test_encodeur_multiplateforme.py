"""L'encodeur sémantique doit rendre le même vecteur sur ARM et sur x86.

L'index des versets est calculé une fois et livré à tous ; les requêtes sont
encodées sur le poste de l'église. Avec ORT_ENABLE_ALL, les fusions du niveau
EXTENDED divergent sur x86 (cosinus 0,9919 avec la référence contre 0,9996 sur
ARM) : 1 Corinthiens 13:4 tombait sous le seuil sur Windows et Mac Intel,
et le benchmark de détection passait de 100 % à 96,7 %. BASIC rend un vecteur
identique au bit près sur les deux architectures (mesuré sous Rosetta).

On ne peut pas lancer x86 et ARM dans le même test : on vérifie donc que le
niveau qui garantit l'identité reste celui qui est demandé.
"""

import onnxruntime as ort

from app.services.e5_encoder import E5OnnxEncoder


def test_la_session_est_ouverte_en_optimisation_basic(monkeypatch, tmp_path):
    niveaux = []

    class _Session:
        def __init__(self, chemin, sess_options=None, providers=None):
            niveaux.append(sess_options.graph_optimization_level)

    class _Tokenizer:
        def enable_truncation(self, max_length):
            pass

    encodeur = E5OnnxEncoder(cache_dir=tmp_path)
    for nom in encodeur.REQUIRED_FILES:
        (tmp_path / nom).write_bytes(b"")
    monkeypatch.setattr("app.services.e5_encoder.verify_sha256", lambda *a: None)
    monkeypatch.setattr(ort, "InferenceSession", _Session)
    monkeypatch.setattr("tokenizers.Tokenizer.from_file", lambda _chemin: _Tokenizer())

    assert encodeur.load(), encodeur.last_error
    assert niveaux == [ort.GraphOptimizationLevel.ORT_ENABLE_BASIC]
