"""NemotronService — transcription locale en flux via transcribe.cpp.

Ces tests remplacent une série qui simulait une API C inventée : neuf symboles
qui n'existaient dans aucune version de la bibliothèque. Ils passaient donc en
validant une fiction, pendant que le moteur était incapable de démarrer.

La leçon est portée ici. On ne simule plus des signatures natives, on simule le
CONTRAT du binding officiel — un flux qui rend `committed` / `tentative` — et
on éprouve la seule chose que VersePro ajoute par-dessus : le découpage en
énoncés. C'est là qu'est notre logique, donc c'est là que doivent être les
tests.
"""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services import nemotron_service as N
from app.services.nemotron_service import LANGUE, MODEL_FILENAME, NemotronService


class FauxFlux:
    """Un flux dont on pilote le texte, comme le vrai binding le rendrait."""

    def __init__(self):
        self.texte = ""
        self.finalise = 0
        self.blocs = 0

    def feed(self, pcm):
        self.blocs += 1
        return type("MAJ", (), {"committed_changed": True, "tentative_changed": True})()

    def text(self):
        # Ce modèle ne fige rien avant finalize : tout vit dans `tentative`.
        return type("Vues", (), {"committed": "", "tentative": self.texte, "full": self.texte})()

    def finalize(self):
        self.finalise += 1

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FauxSession:
    def __init__(self, flux):
        self._flux = flux
        self.flux_ouverts = 0

    def stream(self, language=None):
        self.langue = language
        self.flux_ouverts += 1
        return self._flux

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FauxModele:
    arch, variant, backend = "parakeet", "nemotron-3.5", "MTL0"

    def __init__(self, chemin, flux, streaming=True):
        self.chemin = chemin
        self._session = FauxSession(flux)
        self.capabilities = type("Caps", (), {"supports_streaming": streaming})()

    def session(self):
        return self._session

    def __exit__(self, *a):
        return False


def _binding(flux, streaming=True):
    """Un faux module `transcribe_cpp` exposant juste ce que le service utilise."""
    return type("Binding", (), {"Model": lambda chemin: FauxModele(chemin, flux, streaming)})


@pytest.fixture
def flux():
    return FauxFlux()


@pytest.fixture
def service(tmp_path, monkeypatch, flux):
    svc = NemotronService(lib_factory=lambda: _binding(flux))
    dossier = tmp_path / "models" / "nemotron"
    dossier.mkdir(parents=True)
    modele = dossier / MODEL_FILENAME
    modele.write_bytes(b"gguf-factice")
    monkeypatch.setattr(svc, "_model_path", modele)
    monkeypatch.setattr(type(svc), "resolved_model_path", property(lambda self: self._model_path))
    return svc


def _pousser(service, flux, texte):
    """Le modèle a maintenant entendu `texte` ; on pousse un bloc audio."""
    flux.texte = texte
    service.accept_waveform(np.zeros(4000, dtype=np.int16))


# ── Disponibilité ────────────────────────────────────────────────────────────

def test_modele_absent_ne_demarre_pas(tmp_path, monkeypatch, flux):
    svc = NemotronService(lib_factory=lambda: _binding(flux))
    monkeypatch.setattr(type(svc), "resolved_model_path",
                        property(lambda self: tmp_path / "absent.gguf"))
    assert svc.is_ready is False
    with pytest.raises(RuntimeError):
        svc.start()
    assert "introuvable" in svc.last_error


def test_modele_sans_flux_est_refuse(service, monkeypatch, flux):
    """Un GGUF non-streaming ne doit pas être ouvert en flux."""
    monkeypatch.setattr(service, "lib_factory", lambda: _binding(flux, streaming=False))
    with pytest.raises(RuntimeError):
        service.start()
    assert service._running is False


def test_start_ouvre_le_flux_dans_la_bonne_langue(service, flux):
    service.start()
    assert service._running is True
    assert service._session.langue == LANGUE
    assert service.status()["loaded"] is True


def test_le_locale_complet_est_exige():
    """Le modèle REFUSE « fr » et « auto » — constaté à l'exécution.

    « run: unsupported language ». Aucune relecture de code n'attrape ça."""
    assert LANGUE == "fr-FR"


# ── Découpage en énoncés ─────────────────────────────────────────────────────

def test_rien_ne_sort_avant_une_frontiere_sure(service, flux):
    """Une phrase en cours reste un partiel : le modèle peut encore la réviser."""
    service.start()
    _pousser(service, flux, "Ouvrons ensemble Romains chapitre huit")
    assert service.prendre_enonce_fini() is None
    assert service.get_result() == "Ouvrons ensemble Romains chapitre huit"


def test_une_phrase_suivie_de_texte_part_en_final(service, flux):
    """Le point ne suffit pas : il faut du texte APRÈS, preuve du dépassement."""
    service.start()
    _pousser(service, flux, "Ouvrons Romains huit.")
    assert service.prendre_enonce_fini() is None, "point en fin : encore révisable"

    _pousser(service, flux, "Ouvrons Romains huit. Nous savons")
    assert service.prendre_enonce_fini() == "Ouvrons Romains huit."
    assert service.get_result() == "Nous savons"


def test_les_enonces_ne_se_repetent_pas(service, flux):
    """Ce qui est parti ne doit jamais repartir : l'opérateur verrait double."""
    service.start()
    _pousser(service, flux, "Première phrase. Deuxième")
    assert service.prendre_enonce_fini() == "Première phrase."
    _pousser(service, flux, "Première phrase. Deuxième phrase. Troisième")
    assert service.prendre_enonce_fini() == "Deuxième phrase."
    _pousser(service, flux, "Première phrase. Deuxième phrase. Troisième")
    assert service.prendre_enonce_fini() is None


def test_sans_ponctuation_le_filet_finit_par_couper(service, flux):
    """Mesuré : le modèle peut rester quatre phrases sans écrire un seul point.

    Sans ce filet, aucun final ne partirait — et la cascade, qui n'analyse en
    profondeur que sur un final, resterait muette tout le culte."""
    service.start()
    long_texte = "et puis " * 60          # ~480 caractères, aucun point
    _pousser(service, flux, long_texte)
    sorti = service.prendre_enonce_fini()
    assert sorti, "le plafond doit forcer une coupure"
    assert len(sorti) <= N.SEGMENT_MAX_CARACTERES


def test_le_filet_coupe_entre_les_mots(service, flux):
    """Couper « Romains 8:2|8 » rendrait la référence introuvable des deux côtés."""
    service.start()
    _pousser(service, flux, "alpha " * 80)
    sorti = service.prendre_enonce_fini()
    assert sorti
    assert not sorti.endswith("alph"), "coupure au milieu d'un mot"
    assert sorti.split()[-1] == "alpha"


def test_stop_emet_la_derniere_phrase(service, flux):
    """La dernière phrase d'un culte n'est jamais suivie d'autre chose."""
    service.start()
    _pousser(service, flux, "Ouvrons Romains huit. Une dernière phrase sans suite")
    service.prendre_enonce_fini()
    service.stop()
    assert service.prendre_enonce_fini() == "Une dernière phrase sans suite"
    assert flux.finalise == 1


def test_reset_repart_a_zero(service, flux):
    service.start()
    _pousser(service, flux, "Première phrase. Deuxième")
    service.reset()
    assert service.prendre_enonce_fini() is None
    assert service.get_result() == ""


# ── Robustesse ───────────────────────────────────────────────────────────────

def test_les_entiers_16_bits_sont_convertis(service, flux):
    """Le WebSocket envoie de l'int16 ; le natif attend du flottant normalisé."""
    service.start()
    recu = {}
    flux.feed = lambda pcm: recu.setdefault("pcm", np.asarray(pcm)) or type(
        "MAJ", (), {"committed_changed": True, "tentative_changed": True})()
    service.accept_waveform(np.full(100, 16384, dtype=np.int16))
    assert recu["pcm"].dtype == np.float32
    assert 0.4 < float(recu["pcm"][0]) < 0.6


def test_un_bloc_vide_ne_casse_rien(service):
    service.start()
    service.accept_waveform(np.array([], dtype=np.int16))
    assert service.prendre_enonce_fini() is None


def test_un_flux_qui_tombe_arrete_le_service_sans_lever(service, flux):
    """Le direct ne doit pas mourir avec le moteur : la boucle audio bascule."""
    service.start()
    def _casse(pcm):
        raise RuntimeError("flux natif perdu")
    flux.feed = _casse
    service.accept_waveform(np.zeros(4000, dtype=np.int16))
    assert service._running is False
    assert "interrompu" in service.last_error


def test_hypothese_trop_longue_rouvre_le_flux(service, flux):
    """Le modèle ne fige jamais : sans réouverture, le texte grossirait sans fin."""
    service.start()
    assert service._session.flux_ouverts == 1
    _pousser(service, flux, "x" * (N.HYPOTHESE_MAX_CARACTERES + 10))
    assert service._session.flux_ouverts == 2
    assert flux.finalise == 1


# ── Clôture sur pause : la cadence qui décide si on rate les versets ─────────

def test_une_pause_clot_l_enonce_sans_attendre_de_ponctuation(service, flux, monkeypatch):
    """Sans cela, Nemotron faisait travailler la cascade SEPT FOIS moins souvent.

    Mesuré sur 30 minutes de prédication réelle, à découpage identique :
    Vosk clôturait toutes les 4,9 s, Nemotron toutes les 35,3 s. Or les étages
    profonds — sémantique, VerseGraph — ne tournent que sur un final : un verset
    cité en milieu de phrase attendait une demi-minute avant d'être examiné.
    """
    horloge = {"t": 1000.0}
    monkeypatch.setattr(N.time, "monotonic", lambda: horloge["t"])
    service.start()

    _pousser(service, flux, "Ouvrons Romains chapitre huit")
    assert service.prendre_enonce_fini() is None, "l'orateur parle encore"

    # L'hypothèse ne bouge plus : il a marqué une pause.
    horloge["t"] += N.STABILITE_S + 0.1
    _pousser(service, flux, "Ouvrons Romains chapitre huit")
    assert service.prendre_enonce_fini() == "Ouvrons Romains chapitre huit"


def test_le_seuil_de_stabilite_depasse_la_periode_du_decodeur():
    """Le seuil se DÉDUIT du décodeur, il ne se choisit pas.

    Nemotron ne met son hypothèse à jour que toutes les 1,0 à 1,25 s. Un seuil
    plus court se déclenche entre deux tics, pendant que le modèle travaille
    encore — essayé à 700 ms, la coupe tombait au milieu d'un mot :
    « …chapitre hu » | « it verset vingt-huit… ».
    """
    PERIODE_MAX_OBSERVEE = 1.25
    assert N.STABILITE_S > PERIODE_MAX_OBSERVEE, (
        f"{N.STABILITE_S}s clôturerait pendant que le décodeur travaille"
    )


def test_une_pause_sur_un_tampon_vide_ne_declenche_rien(service, flux, monkeypatch):
    """Le silence avant le premier mot ne doit pas produire d'énoncé vide."""
    horloge = {"t": 2000.0}
    monkeypatch.setattr(N.time, "monotonic", lambda: horloge["t"])
    service.start()
    horloge["t"] += N.STABILITE_S * 3
    _pousser(service, flux, "")
    assert service.prendre_enonce_fini() is None
