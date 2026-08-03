"""NemotronService — transcription locale via le binaire natif transcribe-cli.

Ces tests remplacent une série qui simulait une API C inventée : neuf symboles
— parakeet_init, parakeet_create_stream, parakeet_is_ready… — qui n'existent
dans aucune version de la bibliothèque. Les tests passaient donc en validant
une fiction, pendant que le service était incapable de démarrer en production.

La leçon est portée ici : on ne simule plus l'API du moteur, on simule le
BINAIRE. Sa frontière est un contrat observable — arguments de ligne de
commande, code de retour, ligne « text: » — au lieu d'une disposition mémoire
que rien ne vérifie.
"""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services import nemotron_service as N
from app.services.nemotron_service import LANGUE, MODEL_FILENAME, NemotronService


@pytest.fixture
def service(tmp_path, monkeypatch):
    """Un service dont le modèle et le binaire existent, sans rien exécuter."""
    svc = NemotronService()
    dossier = tmp_path / "models" / "nemotron"
    dossier.mkdir(parents=True)
    modele = dossier / MODEL_FILENAME
    modele.write_bytes(b"gguf-factice")
    monkeypatch.setattr(svc, "_model_dir", dossier)
    monkeypatch.setattr(svc, "_model_path", modele)
    monkeypatch.setattr(type(svc), "resolved_model_path", property(lambda self: self._model_path))

    faux_binaire = tmp_path / "transcribe-cli"
    faux_binaire.write_text("#!/bin/sh\nexit 0\n")
    faux_binaire.chmod(0o755)
    monkeypatch.setattr(N, "_find_transcribe_cli_binary", lambda: faux_binaire)
    return svc


def _bruit(secondes: float, fort: bool) -> np.ndarray:
    """Un bloc PCM au-dessus ou en dessous du seuil de silence."""
    n = int(N.NemotronService.SAMPLE_RATE * secondes)
    amplitude = 0.2 if fort else 0.0
    return np.full(n, amplitude, dtype=np.float32)


def _faire_repondre(monkeypatch, service, texte):
    """Court-circuite l'appel au binaire par une réponse fixe."""
    appels = []

    def _faux(wav):
        appels.append(Path(wav).exists())
        return texte

    monkeypatch.setattr(service, "_transcrire", _faux)
    return appels


# ── Disponibilité ────────────────────────────────────────────────────────────

def test_modele_absent_signale_et_ne_demarre_pas(tmp_path, monkeypatch):
    svc = NemotronService()
    monkeypatch.setattr(type(svc), "resolved_model_path",
                        property(lambda self: tmp_path / "absent.gguf"))
    monkeypatch.setattr(N, "_find_transcribe_cli_binary", lambda: tmp_path / "cli")
    assert svc.is_ready is False
    with pytest.raises(RuntimeError):
        svc.start()


def test_binaire_absent_donne_un_message_exploitable(service, monkeypatch):
    """Sans binaire, l'échec doit être lisible : l'appelant se rabat sur Vosk."""
    monkeypatch.setattr(N, "_find_transcribe_cli_binary", lambda: None)
    with pytest.raises(RuntimeError):
        service.start()
    assert "transcribe-cli" in service.last_error


def test_start_et_stop(service):
    service.start()
    assert service._running is True
    assert service.status()["loaded"] is True
    service.stop()
    assert service._running is False


# ── Découpage sur les silences ───────────────────────────────────────────────

def test_un_enonce_sort_apres_le_silence(service, monkeypatch):
    """Parole, puis silence : l'énoncé est transcrit une fois, complet."""
    appels = _faire_repondre(monkeypatch, service, "Ouvrons Romains chapitre huit.")
    service.start()

    service.accept_waveform(_bruit(1.2, fort=True))
    assert service.prendre_enonce_fini() is None, "rien tant que l'orateur parle"

    service.accept_waveform(_bruit(0.8, fort=False))
    assert service.prendre_enonce_fini() == "Ouvrons Romains chapitre huit."
    assert appels == [True], "le WAV doit exister au moment de l'appel"


def test_un_silence_seul_ne_declenche_rien(service, monkeypatch):
    """Une salle qui se tait ne doit pas lancer le moteur pour rien."""
    appels = _faire_repondre(monkeypatch, service, "ne devrait pas sortir")
    service.start()
    service.accept_waveform(_bruit(3.0, fort=False))
    assert service.prendre_enonce_fini() is None
    assert appels == []


def test_une_parole_trop_brève_est_ignorée(service, monkeypatch):
    """Un « euh » isolé n'est pas une phrase."""
    appels = _faire_repondre(monkeypatch, service, "euh")
    service.start()
    service.accept_waveform(_bruit(0.2, fort=True))
    service.accept_waveform(_bruit(0.8, fort=False))
    assert service.prendre_enonce_fini() is None
    assert appels == []


def test_un_orateur_sans_pause_est_quand_meme_decoupe(service, monkeypatch):
    """Le plafond évite que le tampon enfle sans fin sur un débit continu."""
    _faire_repondre(monkeypatch, service, "phrase interminable")
    service.start()
    for _ in range(int(N.ENONCE_MAX_S) + 1):
        service.accept_waveform(_bruit(1.0, fort=True))
    assert service.prendre_enonce_fini() == "phrase interminable"


def test_stop_transcrit_ce_qui_reste(service, monkeypatch):
    """Le micro se ferme en plein milieu : la dernière phrase n'est pas perdue."""
    _faire_repondre(monkeypatch, service, "dernière phrase")
    service.start()
    service.accept_waveform(_bruit(1.5, fort=True))
    service.stop()
    assert service.prendre_enonce_fini() == "dernière phrase"


def test_reset_vide_les_tampons(service, monkeypatch):
    _faire_repondre(monkeypatch, service, "à jeter")
    service.start()
    service.accept_waveform(_bruit(1.5, fort=True))
    service.reset()
    service.accept_waveform(_bruit(0.8, fort=False))
    assert service.prendre_enonce_fini() is None


# ── Conversion des échantillons ──────────────────────────────────────────────

def test_les_entiers_16_bits_sont_convertis(service, monkeypatch):
    """Le WebSocket envoie de l'int16 ; le seuil d'énergie attend du flottant.

    Sans la division par 32768, un signal fort serait vu comme une énergie
    absurde — et un silence numérique comme de la parole."""
    _faire_repondre(monkeypatch, service, "converti")
    service.start()
    fort = np.full(N.NemotronService.SAMPLE_RATE, 6000, dtype=np.int16)
    service.accept_waveform(fort)
    service.accept_waveform(np.zeros(int(0.8 * N.NemotronService.SAMPLE_RATE), dtype=np.int16))
    assert service.prendre_enonce_fini() == "converti"


def test_un_bloc_vide_ne_casse_rien(service):
    service.start()
    service.accept_waveform(np.array([], dtype=np.int16))
    assert service.prendre_enonce_fini() is None


# ── Contrat d'appel du binaire ───────────────────────────────────────────────

def test_la_langue_passee_au_binaire_est_le_locale_complet():
    """Le modèle REFUSE « fr » et « auto » : il exige « fr-FR ».

    Constaté à l'exécution — « run: unsupported language » — et c'est le genre
    de détail qu'aucune relecture de code n'attrape."""
    assert LANGUE == "fr-FR"
