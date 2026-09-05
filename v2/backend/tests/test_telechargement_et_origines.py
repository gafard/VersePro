"""Deux pannes constatées sur des postes réels, verrouillées par des tests.

1. Windows : la fenêtre Tauri 2 est servie depuis « http://tauri.localhost ».
   Cette origine absente du CORS, toutes les requêtes HTTP étaient refusées
   alors que le moteur tournait — les WebSockets, eux, passaient (le CORS ne
   s'y applique pas), d'où un « serveur injoignable » trompeur.

2. macOS et Windows : l'application figée n'embarquait pas ses autorités de
   certification, et tout téléchargement de modèle mourait en
   CERTIFICATE_VERIFY_FAILED.
"""

import http.server
import ssl
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings
from app.services.download_utils import download_file, ssl_context


# ── 1. Origines autorisées ───────────────────────────────────────────────────

def test_origine_windows_de_tauri_2_est_autorisee():
    """http://tauri.localhost : la fenêtre Windows de Tauri 2."""
    assert "http://tauri.localhost" in settings.cors_origins


def test_origine_macos_de_tauri_reste_autorisee():
    """tauri://localhost : la fenêtre macOS, en Tauri 1 comme en Tauri 2."""
    assert "tauri://localhost" in settings.cors_origins


def test_origine_windows_de_tauri_1_reste_toleree():
    """https://tauri.localhost : un poste encore en Tauri 1 ne doit pas tomber."""
    assert "https://tauri.localhost" in settings.cors_origins


def test_serveur_de_developpement_reste_autorise():
    assert "http://localhost:3000" in settings.cors_origins


# ── 2. Vérification TLS des téléchargements ──────────────────────────────────

def test_le_contexte_tls_verifie_toujours_les_certificats():
    """Un modèle est du code exécuté à l'église : jamais de CERT_NONE."""
    contexte = ssl_context()
    assert contexte.verify_mode == ssl.CERT_REQUIRED
    assert contexte.check_hostname is True


def test_le_contexte_charge_des_autorites():
    """Sans autorité chargée, tout téléchargement échouerait."""
    assert len(ssl_context().get_ca_certs()) > 0


def test_certifi_est_present_pour_lapplication_figee():
    """PyInstaller doit pouvoir embarquer cacert.pem."""
    import certifi
    assert Path(certifi.where()).is_file()


# ── 3. Le téléchargeur lui-même ──────────────────────────────────────────────

class _Serveur(http.server.BaseHTTPRequestHandler):
    CONTENU = b"x" * 5000

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Length", str(len(self.CONTENU)))
        self.end_headers()
        self.wfile.write(self.CONTENU)

    def log_message(self, *args):
        pass


def test_telechargement_ecrit_le_fichier_et_suit_la_progression(tmp_path):
    serveur = http.server.HTTPServer(("127.0.0.1", 0), _Serveur)
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    try:
        cible = tmp_path / "modele.bin"
        etapes = []
        download_file(
            f"http://127.0.0.1:{serveur.server_port}/modele.bin",
            cible,
            lambda recu, total: etapes.append((recu, total)),
        )
        assert cible.read_bytes() == _Serveur.CONTENU
        assert etapes, "la progression doit être rapportée"
        recu_final, total = etapes[-1]
        assert recu_final == len(_Serveur.CONTENU)
        assert total == len(_Serveur.CONTENU)
    finally:
        serveur.shutdown()


def test_une_erreur_reseau_remonte_au_lieu_detre_avalee(tmp_path):
    """Le service appelant doit pouvoir afficher la vraie cause."""
    import urllib.error
    try:
        download_file("http://127.0.0.1:1/introuvable", tmp_path / "x.bin", timeout=2)
    except Exception as exc:
        assert isinstance(exc, (urllib.error.URLError, OSError))
    else:
        raise AssertionError("une connexion impossible doit lever")
