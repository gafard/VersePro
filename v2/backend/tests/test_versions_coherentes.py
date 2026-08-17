"""La version du produit est écrite à trois endroits. Ils doivent s'accorder.

CE QUI S'EST PASSÉ. `chore(release): bump version to 2.1.5` a mis à jour
`tauri.conf.json` et `Cargo.toml`, mais pas `Cargo.lock`, qui contient lui
aussi la version du paquet `app`. La CI lance `cargo check --locked` :

    error: cannot update the lock file … because --locked was passed to
    prevent this
    Error: Process completed with exit code 101

Elle est donc restée rouge à chaque poussée depuis le tag. Le workflow de
release, lui, n'utilise pas `--locked` : il régénérait le verrou en silence
et publiait. D'où une version livrée aux églises alors qu'aucune CI n'était
verte — précisément la situation où une régression passe inaperçue.

Ce test vaut moins pour la cohérence des numéros que pour ça : il transforme
un oubli de trois lignes, invisible et bloquant, en un échec qui se lit.
"""

import json
import re
from pathlib import Path

RACINE = Path(__file__).resolve().parents[3]
TAURI = RACINE / "v2" / "frontend" / "src-tauri"


def _version_tauri_conf() -> str:
    return json.loads((TAURI / "tauri.conf.json").read_text(encoding="utf-8"))["version"]


def _version_cargo_toml() -> str:
    for ligne in (TAURI / "Cargo.toml").read_text(encoding="utf-8").splitlines():
        if ligne.startswith("version"):
            return ligne.split("=", 1)[1].strip().strip('"')
    raise AssertionError("aucune version dans Cargo.toml")


def _version_cargo_lock() -> str:
    contenu = (TAURI / "Cargo.lock").read_text(encoding="utf-8")
    trouve = re.search(r'\[\[package\]\]\nname = "app"\nversion = "([^"]+)"', contenu)
    assert trouve, "le paquet `app` est introuvable dans Cargo.lock"
    return trouve.group(1)


def test_les_trois_versions_saccordent():
    conf, toml, lock = _version_tauri_conf(), _version_cargo_toml(), _version_cargo_lock()
    assert conf == toml == lock, (
        "versions désaccordées — la CI échouera sur `cargo check --locked` :\n"
        f"  tauri.conf.json : {conf}\n"
        f"  Cargo.toml      : {toml}\n"
        f"  Cargo.lock      : {lock}\n"
        "Après un changement de version, lancer `cargo check` dans "
        "v2/frontend/src-tauri pour régénérer le verrou, et commiter Cargo.lock."
    )


def test_le_reste_du_produit_annonce_la_meme_version():
    """SEPT fichiers portent le numéro de version, tous édités à la main.

    Le bump vers 2.1.5 en a touché six et oublié Cargo.lock. Rien n'obligeait
    les autres à rester d'accord : un backend qui annonce 2.1.4 dans /health
    pendant que l'updater propose 2.1.5 rend tout diagnostic à distance
    impossible — « quelle version faites-vous tourner ? » n'aurait plus de
    réponse fiable.
    """
    attendue = _version_tauri_conf()
    sources = {
        "package.json": (
            RACINE / "v2" / "frontend" / "package.json",
            r'"version"\s*:\s*"([^"]+)"',
        ),
        "core/config.py (VERSION)": (
            RACINE / "v2" / "backend" / "app" / "core" / "config.py",
            r'VERSION:\s*str\s*=\s*"([^"]+)"',
        ),
        "core/config.py (APP_VERSION)": (
            RACINE / "v2" / "backend" / "app" / "core" / "config.py",
            r'APP_VERSION:\s*str\s*=\s*"([^"]+)"',
        ),
        "main.py (FastAPI)": (
            RACINE / "v2" / "backend" / "app" / "main.py",
            r'version="([^"]+)"',
        ),
    }
    desaccords = {}
    for nom, (chemin, motif) in sources.items():
        trouve = re.search(motif, chemin.read_text(encoding="utf-8"))
        assert trouve, f"version introuvable dans {nom}"
        if trouve.group(1) != attendue:
            desaccords[nom] = trouve.group(1)

    assert not desaccords, (
        f"tauri.conf.json annonce {attendue}, mais :\n"
        + "\n".join(f"  {nom} : {v}" for nom, v in sorted(desaccords.items()))
    )
