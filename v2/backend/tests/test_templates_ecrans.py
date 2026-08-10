"""Garde-fous sur les gabarits HTML des écrans de diffusion.

POURQUOI CE FICHIER EXISTE. Les trois gabarits ont été extraits de main.py, où
ils vivaient dans des chaînes Python triple-guillemets. Dans ce contexte, un
antislash-s s'écrit avec DEUX antislashs : Python en consomme un, le navigateur
reçoit le bon. L'extraction a recopié les lignes telles quelles, personne ne
servant plus de filtre : le double antislash est arrivé jusqu'au navigateur, où
il ne désigne plus un espace mais un antislash suivi de « s ».

Conséquence, invisible à la relecture et muette à l'exécution : le découpage
mot à mot ne coupait plus rien. Le verset entier devenait UN seul `.w`. La
lecture vivante s'allumait d'un bloc, et surtout, surligner trois mots
marquait le verset en entier — le repli « cible introuvable » s'appliquait à
chaque fois, puisqu'aucun mot ne pouvait plus être retrouvé.

Ces tests relisent les gabarits comme le navigateur les reçoit.
"""

from pathlib import Path

import pytest

GABARITS = Path(__file__).resolve().parents[1] / "app" / "templates"
NOMS = ("output.html", "stage.html", "follow.html")


@pytest.mark.parametrize("nom", NOMS)
def test_aucun_echappement_python_residuel(nom):
    """Un double antislash dans un gabarit servi tel quel est toujours une erreur.

    Ces fichiers ne passent par AUCUN traitement Python : `read_text` puis
    `HTMLResponse`. Un double antislash n'y a donc jamais le sens qu'il avait
    dans la chaîne Python d'origine.
    """
    contenu = (GABARITS / nom).read_text(encoding="utf-8")
    fautives = [
        (numero, ligne.strip())
        for numero, ligne in enumerate(contenu.split("\n"), 1)
        if "\\\\" in ligne
    ]
    assert not fautives, (
        f"{nom} contient des échappements Python résiduels : {fautives}"
    )


@pytest.mark.parametrize("nom", ("output.html", "stage.html"))
def test_decoupage_mot_a_mot_intact(nom):
    """Sans ce découpage, aucun marquage partiel n'est possible."""
    contenu = (GABARITS / nom).read_text(encoding="utf-8")
    assert "split(/\\s+/)" in contenu


def test_selection_introuvable_ne_marque_pas_tout():
    """Une sélection de la régie qui ne se retrouve pas ne marque RIEN.

    Le repli « tout le verset » ne vaut que pour une référence, jamais pour
    une sélection de mots : marquer l'écran entier là où l'opérateur avait
    désigné trois mots ne se distingue pas d'une panne.
    """
    contenu = (GABARITS / "output.html").read_text(encoding="utf-8")
    assert "if (debut < 0 && !estReference) return;" in contenu


def test_marquage_sans_requestanimationframe():
    """Un écran de projection n'est presque jamais la fenêtre au premier plan.

    Le navigateur gèle les rAF des fenêtres masquées : y accrocher la pose des
    annotations, c'est ne jamais les afficher sur le seul écran qui compte.
    """
    contenu = (GABARITS / "output.html").read_text(encoding="utf-8")
    debut = contenu.index("function appliquerAnnotations()")
    fin = contenu.index("function placerAnnotations()")
    assert "requestAnimationFrame(" not in contenu[debut:fin]
