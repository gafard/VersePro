"""La sortie NDI doit être LIVRÉE, pas demandée à l'utilisateur.

CE QUI S'EST PASSÉ. Le workflow de release retirait `ndi-python` de
requirements.txt avant de geler le backend, au motif — écrit dans un
commentaire — que « le spec exclut NDIlib » et qu'il n'existait « pas de roue
fiable en 3.12 ». Les deux étaient devenus faux : le spec ne l'excluait plus,
et PyPI publie des roues de cp310 à cp314.

L'application livrée n'avait donc AUCUN module NDIlib. `NDI_AVAILABLE` valait
False pour toujours, et l'écran Paramètres affichait « Runtime NDI non
détecté — installez-le ». Le régisseur installait le NDI Core Suite de Vizrt,
redémarrait, et lisait le même message : ce runtime ne fournit pas le binding
Python, il ne pouvait rien y faire.

CE QUI REND LA CORRECTION SÛRE. La roue ndi-python embarque le binding ET le
runtime (libndi.dylib sur macOS, Processing.NDI.Lib.x64.dll sur Windows,
~30 Mo). Vérifié sur un Mac sans aucune installation Vizrt : `ndi.initialize()`
répond True et `send_create()` réussit. Il n'y a donc rien à installer côté
église — à condition que le paquet soit dans le gel.

Ces tests gardent cette chaîne, dont aucun maillon ne se voit à l'exécution
sur une machine de développement, où ndi-python est installé de toute façon.
"""

from pathlib import Path

RACINE = Path(__file__).resolve().parents[3]
BACKEND = Path(__file__).resolve().parents[1]
WORKFLOW = RACINE / ".github" / "workflows" / "release.yml"


def test_ndi_python_est_declare():
    exigences = (BACKEND / "requirements.txt").read_text(encoding="utf-8")
    assert "ndi-python" in exigences


def test_le_workflow_de_release_ne_retire_plus_ndi_python():
    """Le gel doit embarquer NDI, pas le laisser à la charge de l'église."""
    contenu = WORKFLOW.read_text(encoding="utf-8")
    # On cherche le filtre qui réécrit requirements.txt avant l'installation.
    lignes_filtre = [
        ligne for ligne in contenu.split("\n")
        if "startswith" in ligne and "pyaudio" in ligne
    ]
    assert lignes_filtre, "le filtre des dépendances CI a disparu ou changé de forme"
    for ligne in lignes_filtre:
        assert "ndi-python" not in ligne, (
            "ndi-python est de nouveau retiré du gel : la sortie NDI sera "
            "absente de l'application livrée, et aucun runtime installé par "
            "l'utilisateur ne pourra la rétablir"
        )


def test_le_spec_collecte_ndilib():
    spec = (BACKEND / "versepro-backend.spec").read_text(encoding="utf-8")
    assert 'collect_all("NDIlib")' in spec


def test_le_gel_verifie_la_presence_du_runtime_ndi():
    """Une vérification à la construction, pas une découverte un dimanche."""
    contenu = WORKFLOW.read_text(encoding="utf-8")
    assert "libndi" in contenu and "Processing.NDI.Lib" in contenu


def test_l_ecran_reglages_ne_reclame_plus_le_runtime_vizrt():
    """Le message envoyait télécharger 200 Mo qui n'y changeaient rien."""
    reglages = (RACINE / "v2" / "frontend" / "src" / "components" / "Settings.jsx")
    contenu = reglages.read_text(encoding="utf-8")
    assert "ndi-core-suite" not in contenu, (
        "le panneau NDI renvoie de nouveau vers le Runtime Vizrt, qui ne "
        "fournit pas le module Python et ne peut donc pas débloquer la sortie"
    )
    assert "vous n'avez rien à installer" in contenu
