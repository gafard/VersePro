"""Le secours Vosk charge la variante réellement présente sur le disque.

Le téléchargement est une action explicite. Sans repli entre les variantes,
une machine existante ne possédant que l'autre modèle perdrait silencieusement
son secours local hors-ligne.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.services.vosk_service as vosk_module
from app.services.vosk_service import VoskService


def _service(tmp_path, monkeypatch, model_type, present):
    monkeypatch.setattr(vosk_module, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(vosk_module.settings, "VOSK_MODEL_TYPE", model_type)
    for name in present:
        (tmp_path / name).mkdir()
    return VoskService()


def test_falls_back_to_large_when_only_large_installed(tmp_path, monkeypatch):
    """Configuré small, mais seul le grand modèle est sur le disque → large."""
    service = _service(tmp_path, monkeypatch, "small", ["vosk-model-fr-0.22"])
    assert service.model_type == "large"
    assert service.model_dir.endswith("vosk-model-fr-0.22")


def test_configured_variant_wins_when_installed(tmp_path, monkeypatch):
    """Les deux variantes présentes → la configuration garde la main."""
    service = _service(
        tmp_path, monkeypatch, "small",
        ["vosk-model-small-fr-0.22", "vosk-model-fr-0.22"],
    )
    assert service.model_type == "small"
    assert service.model_dir.endswith("vosk-model-small-fr-0.22")


def test_no_model_keeps_configuration_for_future_download(tmp_path, monkeypatch):
    """Aucun modèle installé → la configuration et son URL restent intactes."""
    service = _service(tmp_path, monkeypatch, "small", [])
    assert service.model_type == "small"
    assert service.url.endswith("vosk-model-small-fr-0.22.zip")


def test_unknown_type_degrades_to_small(tmp_path, monkeypatch):
    """Une valeur de configuration inconnue retombe proprement sur small."""
    service = _service(tmp_path, monkeypatch, "gigantesque", [])
    assert service.model_type == "small"
