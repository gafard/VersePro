"""NemotronService — transcription locale en flux via transcribe.cpp.

Nemotron-3.5-ASR 0.6B (GGUF q8_0), décodé en flux par la bibliothèque native
transcribe.cpp. Accéléré par Metal sur Apple Silicon, CPU ailleurs.

CE QUE CE SERVICE A ÉTÉ. Il visait au départ une API C inventée de toutes
pièces : neuf symboles — parakeet_init, parakeet_create_stream,
parakeet_is_ready… — qui n'existent dans aucune version de la bibliothèque.
Les tests passaient parce qu'ils simulaient exactement cette API imaginaire :
ils validaient une fiction pendant que le moteur était incapable de démarrer.

CE QU'IL EST. transcribe.cpp fournit un binding Python OFFICIEL — ctypes pur,
généré depuis l'en-tête — qui vérifie DEUX FOIS la disposition des structures :
contre ce que libclang a capturé à la génération, puis contre ce que la
bibliothèque effectivement chargée déclare. Un désaccord devient une
ImportError au lieu d'une corruption mémoire silencieuse. C'est ce filet qui
rend l'approche acceptable là où un binding écrit à la main ne l'était pas.

CE QUE LA MESURE A IMPOSÉ. Le flux expose trois vues — `committed` (figé, en
ajout seul), `tentative` (volatil) et `full`. On aurait aimé prendre `committed`
comme final. Mesuré sur 22,9 s de parole avec des pauses nettes : `committed`
reste VIDE jusqu'à `finalize()`. Tout vit dans `tentative`.

Or la cascade de VersePro n'analyse en profondeur que sur un « final ». Sans
découpage, RIEN ne serait détecté avant la fermeture du micro.

D'où la solution, qui utilise ce que le modèle donne de mieux : il PONCTUE.
On coupe sur les fins de phrase, et seulement sur celles qui sont déjà suivies
d'autre texte — preuve que le modèle les a dépassées et ne les révisera plus.

    « …aiment Dieu. Mon frère Jean va… »
                  ↑ ici : la phrase précédente part en final

Mesuré : 10,7 s d'audio traitées en 0,6 s sur Metal, sans lancer un seul
processus. Et la sortie est PONCTUÉE et capitalisée, là où Vosk rend une suite
de mots en minuscules — ce dont le parseur de références profite directement.
"""

from __future__ import annotations

import os
import platform
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
from loguru import logger

from ..core.config import DATA_DIR, settings
from .download_utils import download_file, verify_sha256

# ── Configuration modèle ──────────────────────────────────────────────────
MODEL_REPO = "handy-computer/nemotron-3.5-asr-streaming-0.6b-gguf"
MODEL_FILENAME = "nemotron-3.5-asr-streaming-0.6b-Q8_0.gguf"
MODEL_SHA256 = None  # Validé lors du téléchargement Hugging Face
MODEL_SUBDIR = "nemotron"
MODEL_SIZE_MB = 716

# Le locale COMPLET est obligatoire : le modèle refuse « fr » comme « auto »
# (« run: unsupported language »), il n'accepte que « fr-FR ». Constaté à
# l'exécution — aucune relecture de code n'aurait attrapé ça.
LANGUE = "fr-FR"

# Fins de phrase sur lesquelles on clôt un énoncé. Le modèle ponctue : c'est
# le seul signal fiable de frontière qu'il fournisse.
TERMINAISONS = ".!?…"

# Filet quand le modèle ne ponctue pas. Mesuré : sur une suite de phrases
# séparées par des pauses nettes, il lui arrive de n'écrire aucun point pendant
# quatre phrases d'affilée. Sans ce plafond, aucun final ne partirait, et la
# cascade — qui n'analyse en profondeur que sur un final — resterait muette.
# 300 caractères ≈ 50 mots, soit un peu plus que la fenêtre d'analyse (40).
SEGMENT_MAX_CARACTERES = 300

# CLÔTURE SUR PAUSE — le correctif qui rendait Nemotron inutilisable sans lui.
#
# Mesuré sur 30 minutes de prédication réelle, à découpage identique :
#     Vosk      un final toutes les  4,9 s
#     Nemotron  un final toutes les 35,3 s
#
# Or la cascade ne lance ses étages profonds — sémantique, VerseGraph — que sur
# un final. Nemotron la faisait donc travailler SEPT FOIS moins souvent : un
# verset cité en milieu de phrase attendait jusqu'à trente-cinq secondes avant
# d'être seulement examiné, et le prédicateur était passé à autre chose.
#
# Vosk clôt naturellement sur les silences. On fait pareil : quand l'hypothèse
# cesse de grandir, l'orateur a marqué une pause — l'énoncé est mûr.
#
# LE SEUIL SE DÉDUIT DU DÉCODEUR, il ne se choisit pas. Mesuré : Nemotron ne
# met son hypothèse à jour que toutes les 1,0 à 1,25 s. Un seuil plus court se
# déclenche ENTRE DEUX TICS, alors que le modèle travaille encore — essayé à
# 700 ms, la coupe tombait au milieu d'un mot :
#
#     « Ouvrons ensemble Romain chapitre hu » | « it verset vingt-huit… »
#
# 1,8 s passe confortablement au-dessus du maximum observé, tout en ramenant la
# cadence de 35 s à quelques secondes. Si un jour le modèle change de rythme,
# c'est cette mesure qu'il faut refaire — pas ce nombre qu'il faut deviner.
STABILITE_S = 1.3

# Au-delà de cette longueur d'hypothèse, on referme et rouvre le flux. Sans
# cela, une prédication de deux heures ferait grossir le texte courant sans
# fin — le modèle ne fige jamais de lui-même.
HYPOTHESE_MAX_CARACTERES = 1500


@contextmanager
def suppress_erreurs():
    """Libérer des ressources natives ne doit jamais faire échouer stop()."""
    try:
        yield
    except Exception as exc:  # pragma: no cover - dépend du natif
        logger.debug(f"Nemotron : libération partielle ({exc})")


# ── Service Nemotron ───────────────────────────────────────────────────────
class NemotronService:
    """Transcription locale en flux. Ne bloque jamais le direct en cas d'échec."""

    NAME = "nemotron"
    DISPLAY_NAME = "Nemotron-3.5-ASR 0.6B (Streaming local)"
    SAMPLE_RATE = 16000

    def __init__(self, lib_factory=None) -> None:
        # `lib_factory` permet aux tests d'injecter un faux module de binding.
        self.lib_factory = lib_factory
        self._model_dir = Path(DATA_DIR) / "models" / MODEL_SUBDIR
        self._model_path = self._model_dir / MODEL_FILENAME

        self._modele = None
        self._session = None
        self._flux = None

        self._lock = threading.Lock()
        self._startup_lock = threading.Lock()
        self._running = False
        self.downloading = False
        self.download_progress = 0.0
        self.last_error = ""
        self._runtime_available: Optional[bool] = None

        # Longueur du texte figé DÉJÀ transmis à l'appelant.
        self._fige_emis = 0
        self._tentatif = ""
        self._enonce_fini: Optional[str] = None
        # Dernier instant où l'hypothèse a bougé : sert à repérer les pauses.
        self._dernier_changement = 0.0

    @property
    def resolved_model_path(self) -> Path:
        candidates = [
            self._model_path,
            Path(DATA_DIR) / "models" / MODEL_SUBDIR / MODEL_FILENAME,
            Path(DATA_DIR) / MODEL_SUBDIR / MODEL_FILENAME,
            Path.home() / "Library/Application Support/VersePro/data/models/nemotron" / MODEL_FILENAME,
            Path.home() / "Library/Application Support/app.versepro.regie/models/nemotron" / MODEL_FILENAME,
            Path.home() / "Library/Application Support/app.versepro.regie/data/models/nemotron" / MODEL_FILENAME,
            Path(__file__).resolve().parents[2] / "data" / "models" / MODEL_SUBDIR / MODEL_FILENAME,
        ]
        for cand in candidates:
            if cand.exists() and cand.stat().st_size > 0:
                return cand
        return self._model_path

    @property
    def is_ready(self) -> bool:
        if getattr(self, "downloading", False):
            return False
        path = self.resolved_model_path
        # Le modèle fait ~716 Mo. S'il est plus petit que 700 Mo, c'est qu'il est incomplet.
        return path.exists() and path.stat().st_size > 700 * 1024 * 1024

    @property
    def model_path(self) -> Path:
        return self.resolved_model_path

    @property
    def runtime_available(self) -> bool:
        """Vérifie une fois que le binding Python ET sa bibliothèque native chargent.

        La présence du GGUF seule ne suffit pas : c'était précisément le cas du
        DMG défectueux, qui annonçait « prêt » avec 716 Mo sur disque alors que
        `transcribe_cpp` n'avait pas été embarqué.
        """
        if self._runtime_available is not None:
            return self._runtime_available
        try:
            self._binding()
            self._runtime_available = True
        except Exception:
            self._runtime_available = False
        return self._runtime_available

    def status(self) -> Dict[str, Any]:
        model_installed = self.is_ready
        runtime_ready = self.runtime_available
        return {
            "provider": self.NAME,
            "display_name": self.DISPLAY_NAME,
            "ready": model_installed and runtime_ready,
            "installed": model_installed,
            "runtime_available": runtime_ready,
            "model_path": str(self.resolved_model_path),
            "model_size_mb": MODEL_SIZE_MB,
            "loaded": self._running,
            "downloading": self.downloading and not model_installed,
            "download_progress": 1.0 if model_installed else self.download_progress,
            "last_error": self.last_error,
        }

    def prewarm(self) -> None:
        """Précharge le modèle GGUF et les pipelines GPU en mémoire en arrière-plan au démarrage."""
        with self._startup_lock:
            if not self.is_ready or self._running:
                return
            try:
                chemin = self.resolved_model_path
                transcribe_cpp = self._binding()
                logger.info("🧠 Pré-chargement de Nemotron 3.5-ASR (716 Mo) en mémoire...")
                if self._modele is None:
                    self._modele = transcribe_cpp.Model(str(chemin))
                if not self._modele.capabilities.supports_streaming:
                    raise RuntimeError(
                        f"{self._modele.arch}/{self._modele.variant} ne gère pas le flux"
                    )
                self._session = self._modele.session().__enter__()
                self._flux = self._session.stream(language=LANGUE).__enter__()
                with self._lock:
                    self._fige_emis = 0
                    self._tentatif = ""
                    self._enonce_fini = None
                    self._dernier_changement = time.monotonic()
                self._running = True
                logger.info("✅ Nemotron 3.5-ASR prêt instantanément en mémoire")
            except Exception as exc:
                self._fermer_natif()
                self._running = False
                self.last_error = f"Pré-chargement Nemotron impossible : {exc}"
                logger.warning(self.last_error)

    def prepare(self, allow_download: bool = True) -> bool:
        """Télécharge le GGUF depuis Hugging Face si absent."""
        if self.is_ready:
            if not self.runtime_available:
                # Ne retélécharge pas 716 Mo pour réparer un exécutable auquel
                # il manque le binding natif : seul un paquet d'application
                # corrigé peut résoudre ce cas.
                return False
            logger.info("Modèle Nemotron déjà présent.")
            self.prewarm()
            return True

        if not allow_download:
            self.last_error = "Modèle Nemotron-3.5-ASR non présent sur disque."
            return False

        if self.downloading:
            return True

        self._model_dir.mkdir(parents=True, exist_ok=True)
        self.downloading = True
        self.download_progress = 0.0

        def _download_task():
            def _progression(recus, total):
                if total > 0:
                    self.download_progress = min(0.99, float(recus) / float(total))
                else:
                    self.download_progress = min(0.95, self.download_progress + 0.01)

            try:
                try:
                    url = f"https://huggingface.co/{MODEL_REPO}/resolve/main/{MODEL_FILENAME}"
                    logger.info(f"Téléchargement de Nemotron-3.5-ASR ({MODEL_SIZE_MB} Mo)…")
                    download_file(url, self._model_path, on_progress=_progression)
                except Exception as exc:
                    logger.warning(f"Téléchargement direct impossible ({exc}), repli sur huggingface_hub")
                    from huggingface_hub import hf_hub_download

                    hf_hub_download(
                        repo_id=MODEL_REPO,
                        filename=MODEL_FILENAME,
                        local_dir=str(self._model_dir),
                    )

                self.downloading = False
                self.download_progress = 1.0
                logger.info("✅ Téléchargement Nemotron-3.5-ASR terminé avec succès.")
                self.prewarm()
            except Exception as exc:
                self.downloading = False
                self.last_error = f"Erreur téléchargement Nemotron : {exc}"
                logger.error(self.last_error)
            finally:
                self.downloading = False

        threading.Thread(target=_download_task, daemon=True).start()
        return True

    # ── Session de flux ─────────────────────────────────────────────────────

    def _preparer_bibliotheque(self) -> None:
        """Repli pour un développeur qui compile transcribe.cpp lui-même.

        En temps normal il n'y a rien à faire : la roue `transcribe-cpp-native`
        embarque la bibliothèque compilée pour la plateforme, et le binding la
        trouve seul. Ce repli ne sert qu'à une bibliothèque posée à la main
        dans bin/, et n'écrase jamais un TRANSCRIBE_LIBRARY déjà défini.
        """
        if os.environ.get("TRANSCRIBE_LIBRARY"):
            return
        nom = {"Darwin": "libtranscribe.dylib", "Windows": "transcribe.dll"}.get(
            platform.system(), "libtranscribe.so")
        racine = Path(__file__).resolve().parents[2]
        for dossier in (racine / "bin", racine / "_internal" / "bin", racine.parent / "bin"):
            chemin = dossier / nom
            if chemin.exists():
                os.environ["TRANSCRIBE_LIBRARY"] = str(chemin)
                return

    def _binding(self):
        """Le module de binding, ou une RuntimeError expliquant ce qui manque."""
        if self.lib_factory:
            return self.lib_factory()
        self._preparer_bibliotheque()
        try:
            import transcribe_cpp
        except Exception as exc:
            self.last_error = (
                f"Bibliothèque native transcribe.cpp indisponible : {exc}. "
                "Attendue dans bin/, ou désignée par la variable TRANSCRIBE_LIBRARY."
            )
            raise RuntimeError(self.last_error) from exc
        return transcribe_cpp

    def start(self) -> None:
        """Charge le modèle et ouvre un flux en français.

        Lève une RuntimeError explicite en cas d'échec : l'appelant la remonte
        à la régie sans envoyer silencieusement le son vers un moteur cloud.
        """
        with self._startup_lock:
            self._start_locked()

    def _start_locked(self) -> None:
        if self._running:
            return

        chemin = self.resolved_model_path
        if not (chemin.exists() and chemin.stat().st_size > 0):
            self.last_error = f"Modèle Nemotron introuvable : {chemin}"
            raise RuntimeError(self.last_error)

        transcribe_cpp = self._binding()
        try:
            if self._modele is None:
                logger.info("⚡ Chargement de Nemotron 3.5-ASR en mémoire...")
                self._modele = transcribe_cpp.Model(str(chemin))
            if not self._modele.capabilities.supports_streaming:
                raise RuntimeError(
                    f"{self._modele.arch}/{self._modele.variant} ne gère pas le flux"
                )
            # On entre les gestionnaires de contexte à la main : leur durée de
            # vie est celle de la session micro, pas celle d'un bloc `with`.
            self._session = self._modele.session().__enter__()
            self._flux = self._session.stream(language=LANGUE).__enter__()
        except Exception as exc:
            self._fermer_natif()
            self.last_error = f"Ouverture du flux Nemotron impossible : {exc}"
            raise RuntimeError(self.last_error) from exc

        with self._lock:
            self._fige_emis = 0
            self._tentatif = ""
            self._enonce_fini = None
            self._dernier_changement = time.monotonic()
        self._running = True
        logger.info(
            "✅ Nemotron prêt (%s sur %s, langue %s)",
            self._modele.variant, self._modele.backend, LANGUE,
        )

    def stop(self) -> None:
        """Vide la fin du flux, puis libère flux, session et modèle."""
        if not self._running:
            return
        self._running = False
        if self._flux is not None:
            with suppress_erreurs():
                self._flux.finalize()
                self._recolter(tout=True)
        self._fermer_natif()

    def reset(self) -> None:
        """Repart d'un texte vide SANS rouvrir le flux.

        Le flux conserve son contexte acoustique d'une phrase à l'autre — c'est
        précisément ce qui fait la valeur d'un décodage à cache. On ne remet à
        zéro que le suivi de ce qui a déjà été transmis.
        """
        with self._lock:
            self._tentatif = ""
            self._enonce_fini = None
            self._fige_emis = 0

    def accept_waveform(self, samples: np.ndarray) -> None:
        """Pousse un bloc PCM et récolte ce que le modèle vient de figer.

        Appel bloquant le temps du décodage (quelques dizaines de ms) : à
        exécuter hors de la boucle d'événements, ce que fait le WebSocket audio
        via asyncio.to_thread.
        """
        if not self._running or self._flux is None:
            return

        if samples.dtype == np.int16:
            flottants = samples.astype(np.float32) / 32768.0
        elif samples.dtype != np.float32:
            flottants = samples.astype(np.float32)
        else:
            flottants = samples
        if flottants.ndim > 1:
            flottants = flottants.reshape(-1)
        if flottants.size == 0:
            return

        try:
            maj = self._flux.feed(np.ascontiguousarray(flottants, dtype=np.float32))
        except Exception as exc:
            # Un flux mort ne doit pas faire tomber la session : on s'arrête, et
            # la boucle audio bascule sur un autre moteur au prochain tour.
            self.last_error = f"Flux Nemotron interrompu : {exc}"
            logger.error(self.last_error)
            self._running = False
            return

        if getattr(maj, "committed_changed", True) or getattr(maj, "tentative_changed", True):
            self._recolter()

        # Clôture sur pause : l'hypothèse ne bouge plus, l'orateur a respiré.
        # Sans cela, il fallait attendre une ponctuation ou 300 caractères, et
        # la détection tournait sept fois moins souvent qu'avec Vosk.
        with self._lock:
            en_attente = self._tentatif
            fige_depuis = time.monotonic() - self._dernier_changement
        if en_attente and fige_depuis >= STABILITE_S:
            self._recolter(tout=True)

    def tick_pause(self) -> None:
        """À appeler lors des silences pour permettre la clôture sur pause."""
        if not self._running or self._flux is None:
            return
        with self._lock:
            en_attente = self._tentatif
            fige_depuis = time.monotonic() - self._dernier_changement
        if en_attente and fige_depuis >= STABILITE_S:
            self._recolter(tout=True)

    @staticmethod
    def _fin_de_phrase_sure(texte: str, depuis: int) -> int:
        """Position après la dernière fin de phrase SUIVIE d'autre texte.

        Renvoie `depuis` si aucune frontière sûre n'existe. La condition « suivie
        d'autre texte » est ce qui rend la coupe sûre : tant que le modèle
        n'a rien écrit après le point, il peut encore réviser la phrase.
        """
        for i in range(len(texte) - 1, depuis - 1, -1):
            if texte[i] in TERMINAISONS:
                return i + 1 if texte[i + 1:].strip() else depuis

        # Aucun point : filet de sécurité. Au-delà du plafond, on coupe au
        # dernier espace — jamais au milieu d'un mot, qui rendrait
        # « Romains 8:2|8 » indétectable des deux côtés de la coupure.
        if len(texte) - depuis > SEGMENT_MAX_CARACTERES:
            espace = texte.rfind(" ", depuis, depuis + SEGMENT_MAX_CARACTERES)
            if espace > depuis:
                return espace
        return depuis

    def _recolter(self, tout: bool = False) -> None:
        """Lit le flux, en déduit le partiel, et clôt les phrases terminées.

        `tout=True` (à la fermeture) émet le reste sans attendre de frontière :
        la dernière phrase d'un culte n'est jamais suivie d'autre chose.
        """
        if self._flux is None:
            return
        vues = self._flux.text()
        # `committed` reste vide sur ce modèle : l'hypothèse entière vit dans
        # `tentative`. On prend donc la vue la plus complète des deux.
        courant = (vues.committed or "") + (vues.tentative or "")

        with self._lock:
            coupe = len(courant) if tout else self._fin_de_phrase_sure(courant, self._fige_emis)
            if coupe > self._fige_emis:
                nouveau = courant[self._fige_emis:coupe].strip()
                self._fige_emis = coupe
                if nouveau:
                    self._enonce_fini = (
                        f"{self._enonce_fini} {nouveau}".strip()
                        if self._enonce_fini else nouveau
                    )
            nouveau_tentatif = courant[self._fige_emis:].strip()
            if nouveau_tentatif != self._tentatif:
                self._dernier_changement = time.monotonic()
            self._tentatif = nouveau_tentatif
            trop_long = len(courant) >= HYPOTHESE_MAX_CARACTERES

        # Hors du verrou : rouvrir le flux appelle du natif, qui peut être lent.
        if trop_long and not tout:
            self._rouvrir_flux()

    def _rouvrir_flux(self) -> None:
        """Referme et rouvre le flux pour borner l'hypothèse courante.

        Ne touche ni au modèle ni à la session : seul le flux repart à zéro,
        ce qui coûte quelques millisecondes.
        """
        if self._session is None:
            return
        reste = self._tentatif
        with suppress_erreurs():
            self._flux.finalize()
            self._flux.__exit__(None, None, None)
        self._flux = None
        try:
            self._flux = self._session.stream(language=LANGUE).__enter__()
        except Exception as exc:
            self.last_error = f"Réouverture du flux Nemotron impossible : {exc}"
            logger.error(self.last_error)
            self._running = False
            return
        with self._lock:
            # Ce qui n'était pas encore clos repart comme début de la nouvelle
            # hypothèse : on ne perd pas la phrase en cours.
            self._fige_emis = 0
            self._tentatif = reste
        logger.debug("Nemotron : flux rouvert (hypothèse bornée)")

    def get_result(self) -> str:
        """Le suffixe encore révisable — l'équivalent d'un partiel Vosk."""
        with self._lock:
            return self._tentatif

    def prendre_enonce_fini(self) -> Optional[str]:
        """Renvoie et consomme le texte nouvellement figé, ou None."""
        with self._lock:
            fini, self._enonce_fini = self._enonce_fini, None
            return fini

    def _fermer_natif(self, release_model: bool = False) -> None:
        """Libère flux et session. Le modèle reste en mémoire pour réouverture instantanée."""
        cibles = (self._flux, self._session, self._modele) if release_model else (self._flux, self._session)
        for objet in cibles:
            if objet is None:
                continue
            with suppress_erreurs():
                sortie = getattr(objet, "__exit__", None)
                if sortie is not None:
                    sortie(None, None, None)
                else:
                    objet.close()
        self._flux = None
        self._session = None
        if release_model:
            self._modele = None
