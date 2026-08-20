"""La barrière vocale doit ENTENDRE, pas seulement refuser.

CE QUI EST ARRIVÉ. L'export ONNX de Silero v5 attend 576 échantillons — 64 de
contexte repris de la trame précédente, puis 512 nouveaux. Le service ne lui
en donnait que 512. Le modèle ne refusait alors rien : il répondait presque
zéro à tout.

    fenêtre 512 : probabilité moyenne 0,0014 sur de la parole française claire
    fenêtre 576 : probabilité moyenne 0,9538 sur le même signal

Sur 30 minutes de prédication réelle, la porte bloquait 100 % des blocs. Le
jour où VOICE_GATE_ENABLED est passé à True par défaut, VersePro devenait
sourd dans toutes les églises à la fois : aucun mot transcrit, aucune
détection, aucun message d'erreur.

POURQUOI RIEN NE L'A SIGNALÉ. La vérification de non-régression, en CI comme
ici, tenait en une ligne :

    assert gate.accept(silence) is False

Une porte qui bloque TOUT la passe admirablement. C'est le même motif que le
banc d'essai mort et le compteur de projections constant : un instrument qui
dit « ça va » sans rien mesurer.

Ces tests ferment les deux côtés : le contrat d'entrée du modèle, et le fait
que la porte s'ouvre effectivement sur de la parole.
"""

import numpy as np

from app.services import vad_service
from app.services.vad_service import CONTEXTE_SIZE, FRAME_SIZE, VoiceGate


def test_le_modele_recoit_la_fenetre_qu_il_attend():
    """576 = 64 de contexte + 512 nouveaux. C'est le contrat de Silero v5."""
    assert CONTEXTE_SIZE + FRAME_SIZE == 576


def test_chaque_appel_nourrit_le_modele_de_576_echantillons():
    """Vérifié à la source, sans audio : la CI n'embarque pas d'enregistrement."""
    vues = []

    class SessionEspion:
        def run(self, _sorties, entrees):
            vues.append(entrees["input"].shape)
            return np.array([[0.9]], dtype=np.float32), np.zeros((2, 1, 128), dtype=np.float32)

    gate = VoiceGate.__new__(VoiceGate)
    gate.session = SessionEspion()
    gate.sample_rate = 16000
    gate._state = np.zeros((2, 1, 128), dtype=np.float32)
    gate._sr = np.array(16000, dtype=np.int64)
    gate._contexte = np.zeros(CONTEXTE_SIZE, dtype=np.float32)

    for _ in range(3):
        gate._frame_prob(np.zeros(FRAME_SIZE, dtype=np.float32))

    assert vues, "le modèle n'a jamais été appelé"
    assert all(forme == (1, 576) for forme in vues), vues


def test_le_contexte_reprend_la_fin_de_la_trame_precedente():
    """Sans report, chaque trame repart d'un contexte nul et le flux se hache."""
    gate = VoiceGate.__new__(VoiceGate)
    gate.session = type("S", (), {"run": lambda self, a, b: (
        np.array([[0.5]], dtype=np.float32), np.zeros((2, 1, 128), dtype=np.float32))})()
    gate._state = np.zeros((2, 1, 128), dtype=np.float32)
    gate._sr = np.array(16000, dtype=np.int64)
    gate._contexte = np.zeros(CONTEXTE_SIZE, dtype=np.float32)

    trame = np.arange(FRAME_SIZE, dtype=np.float32)
    gate._frame_prob(trame)
    assert np.array_equal(gate._contexte, trame[-CONTEXTE_SIZE:])


def test_une_porte_qui_bloque_tout_est_une_porte_en_panne():
    """Le garde-fou qui manquait.

    Refuser le silence ne prouve rien — c'est ce que fait une porte morte.
    On exige donc qu'un signal reconnu comme parole ouvre la porte.
    """
    class SessionParlante:
        def run(self, _sorties, entrees):
            assert entrees["input"].shape == (1, 576)
            return np.array([[0.95]], dtype=np.float32), np.zeros((2, 1, 128), dtype=np.float32)

    gate = VoiceGate.__new__(VoiceGate)
    gate.session = SessionParlante()
    gate.sample_rate = 16000
    gate._state = np.zeros((2, 1, 128), dtype=np.float32)
    gate._sr = np.array(16000, dtype=np.int64)
    gate._contexte = np.zeros(CONTEXTE_SIZE, dtype=np.float32)
    gate._hangover = 0
    gate._leftover = np.empty(0, dtype=np.float32)
    gate.chunks_total = gate.chunks_passed = 0

    parole = (np.random.randn(FRAME_SIZE * 2) * 0.2).astype(np.float32)
    pcm = (parole * 32767).astype(np.int16).tobytes()
    assert gate.accept(pcm) is True, "la porte reste fermée sur de la parole"
    assert gate.stats()["chunks_blocked"] == 0
