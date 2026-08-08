"""Santé de la transcription — savoir quand se taire.

VersePro filtrait sur la confiance de DÉTECTION, jamais sur la qualité de ce
qu'il avait entendu. Une prédication réelle de 2 h 14 en a montré le prix :
144 propositions, une toutes les 56 secondes, dont 99 références distinctes
proposées une seule fois — là où un culte en cite une dizaine.

La cause n'était pas la détection. C'était la transcription. Dans une église
charismatique, la musique tourne PENDANT la prédication et le parler en
langues alterne avec le français. Vosk n'échoue pas au sens habituel : il
rend consciencieusement en français ce qui n'en est pas — « papa papa papa »,
« laver laver laver ». La recherche sémantique trouve alors de vrais versets
dans du charabia, et les propose avec aplomb.

CE QUI MESURE CET ÉTAT, et la mesure a surpris : ce n'est pas la confiance
que Vosk s'accorde. Les vraies citations et les fausses y sont toutes deux à
1,00. C'est la LONGUEUR DES SEGMENTS. Quand le son est propre, le moteur
produit de longues phrases fluides ; quand il lutte, il hache.

    prédication au son propre   35 mots/segment   0 % de fenêtres sous 10
    culte avec musique de fond   4 mots/segment  89 % de fenêtres sous 10

Un facteur neuf, et presque aucun recouvrement. C'est un signal gratuit :
il n'exige aucun calcul, seulement de compter ce qui arrive déjà.

CE QU'ON EN FAIT — se dégrader proprement, pas s'éteindre. En conditions
difficiles, les citations ANNONCÉES continuent de passer : « ouvrons Romains
chapitre huit verset vingt-huit » est un texte vérifiable, que l'analyse par
expressions régulières reconnaît sans rien deviner. Ce qui est suspendu, ce
sont les propositions sémantiques — celles qui devinent.

L'opérateur, lui, doit savoir pourquoi le logiciel s'est tu. Un outil
silencieux sans explication passe pour cassé ; c'est à ça que sert `etat()`.
"""

from __future__ import annotations

from collections import deque
from typing import Any, Deque, Dict

# Fenêtre glissante : assez longue pour ne pas réagir à une phrase courte
# isolée, assez courte pour suivre un culte qui passe de la louange à la
# prédication.
FENETRE_SEGMENTS = 10

# Sous cette moyenne de mots par segment, la transcription est jugée hachée.
# Mesuré : le son propre ne descend jamais sous 30 ; le culte avec musique de
# fond y passe 89 % de son temps.
MOTS_MOYENS_MIN = 10.0

# Un segment plus court que ceci ne peut pas désigner un verset, même quand
# tout va bien. Mesuré sur deux enregistrements : à 6 mots, on garde les 12
# détections de la prédication au son propre ET les 8 expositions justes du
# culte, tout en supprimant un tiers du bruit. Le garde-fou existant de la
# cascade était à 4 — « j'avais de l'eau » en fait exactement 4.
MOTS_MIN_SEGMENT = 6

# Avant d'avoir vu ce nombre de segments, on ne juge pas : au démarrage, mieux
# vaut laisser passer que rester muet sur une statistique vide.
SEGMENTS_MIN_POUR_JUGER = 3


class SanteTranscription:
    """Compte les mots par segment et dit si l'on peut encore deviner."""

    def __init__(self, fenetre: int = FENETRE_SEGMENTS):
        self._longueurs: Deque[int] = deque(maxlen=fenetre)

    def noter(self, texte: str) -> None:
        """À appeler pour CHAQUE transcription finale, détection ou non."""
        if texte and texte.strip():
            self._longueurs.append(len(texte.split()))

    def reinitialiser(self) -> None:
        """Nouveau culte, ou micro rouvert : l'historique ne vaut plus."""
        self._longueurs.clear()

    @property
    def mots_moyens(self) -> float:
        if not self._longueurs:
            return 0.0
        return sum(self._longueurs) / len(self._longueurs)

    def est_fiable(self) -> bool:
        """Peut-on encore faire confiance aux propositions sémantiques ?"""
        if len(self._longueurs) < SEGMENTS_MIN_POUR_JUGER:
            return True
        return self.mots_moyens >= MOTS_MOYENS_MIN

    @staticmethod
    def segment_exploitable(texte: str) -> bool:
        """Ce segment-ci porte-t-il assez de matière pour désigner un verset ?"""
        return bool(texte) and len(texte.split()) >= MOTS_MIN_SEGMENT

    def etat(self) -> Dict[str, Any]:
        """De quoi expliquer le silence à l'opérateur, plutôt que le subir."""
        fiable = self.est_fiable()
        return {
            "fiable": fiable,
            "mots_moyens": round(self.mots_moyens, 1),
            "segments_observes": len(self._longueurs),
            "message": (
                "Transcription hachée : vérifiez le micro ou réduisez la musique de fond."
                if not fiable else ""
            ),
        }
