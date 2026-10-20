"""
Routes API REST pour VersePro v2 : le point de montage.

Ce fichier dépassait 2 100 lignes. Les routes vivent désormais par domaine,
chacune avec les aides qu'elle est seule à utiliser :

    reglages.py     Lecture et écriture des réglages.
    recherche.py    Références, recherche biblique (locale et IA), plan de prédication, sémantique, répétition.
    moteurs.py      Moteurs de transcription : Vosk, Nemotron, préparation ASR locale.
    habillage.py    Habillages (overlay) et fonds plein écran.
    bibles.py       Bibliothèque des traductions : catalogue, import, téléchargement, suppression.
    systeme.py      Santé, prévol, réseau local, mode panique et mises à jour.
    diffusion.py    Commande de l'écran : projection, préparation, télécommande, ProPresenter.
    historique.py   Historique des versets, sessions de culte, exports et statistiques.

Aucune route ne change : chemins, méthodes, paramètres et réponses sont
identiques (schéma OpenAPI comparé avant/après). Aucun domaine n'en importe
un autre : chaque module se lit seul.
"""
from fastapi import APIRouter

from . import reglages, recherche, moteurs, habillage, bibles, systeme, diffusion, historique

router = APIRouter()
for _domaine in (reglages, recherche, moteurs, habillage, bibles, systeme, diffusion, historique,):
    router.include_router(_domaine.router)
