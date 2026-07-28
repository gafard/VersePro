"""Le résumé de prédication doit pouvoir être RÉESSAYÉ après un échec.

Défaut corrigé : le service mettait les échecs en cache au même titre que les
réussites. Une seule panne — coupure réseau, délai expiré — condamnait
définitivement la transcription concernée : chaque nouvel essai renvoyait
l'échec mémorisé sans même appeler l'IA. Le bouton « Générer le résumé » ne
pouvait plus jamais aboutir, et rien ne l'expliquait à l'opérateur.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.ai_service import AIService

TRANSCRIPT = (
    "Bien-aimés, ouvrons nos Bibles au livre de l'Exode, chapitre dix-sept. "
    "Lorsque Moïse élevait sa main, Israël était le plus fort. " * 3
)


def _service() -> AIService:
    """Service isolé de la configuration de la machine.

    Le constructeur retombe sur les clés du fichier .env quand on ne lui en
    passe pas : sans ce nettoyage, le test appellerait un vrai fournisseur et
    son résultat dépendrait du crédit restant sur le compte.
    """
    async def creer():
        service = AIService(api_key="", openrouter_key="")
        service.openrouter_key = ""
        service.api_key = ""
        service.ollama_active = False
        service.enabled = True
        return service
    return asyncio.run(creer())


def test_un_echec_nest_pas_mis_en_cache():
    """C'est le cœur du défaut : réessayer doit rappeler l'IA."""
    service = _service()
    # Aucun moteur configuré : la génération échoue.
    assert asyncio.run(service.generate_sermon_summary(TRANSCRIPT)) is None
    cle = service._normalize_cache_key(TRANSCRIPT, "summary")
    assert cle not in service._summary_cache, "l'échec ne doit pas être mémorisé"


def test_une_reussite_est_mise_en_cache():
    """Le cache garde son intérêt : ne pas repayer un résumé déjà obtenu."""
    service = _service()
    cle = service._normalize_cache_key(TRANSCRIPT, "summary")
    service._cache_put(service._summary_cache, cle, "# Un résumé")
    assert asyncio.run(service.generate_sermon_summary(TRANSCRIPT)) == "# Un résumé"


def test_la_raison_de_lechec_est_exposee():
    """L'opérateur doit savoir POURQUOI : clé absente et délai expiré ne se
    corrigent pas de la même façon."""
    service = _service()
    asyncio.run(service.generate_sermon_summary(TRANSCRIPT))
    assert service.last_summary_error
    assert "moteur" in service.last_summary_error.lower() or "clé" in service.last_summary_error.lower()


def test_moteur_absent_le_dit_clairement():
    service = _service()
    service.enabled = False
    assert asyncio.run(service.generate_sermon_summary(TRANSCRIPT)) is None
    assert "OpenRouter" in service.last_summary_error or "Ollama" in service.last_summary_error


def test_transcription_trop_courte_est_signalee():
    """Message distinct : ce n'est pas une panne, il n'y a rien à résumer."""
    service = _service()
    assert asyncio.run(service.generate_sermon_summary("Trop court.")) is None
    assert "courte" in service.last_summary_error.lower()


def test_une_transcription_vide_ne_plante_pas():
    service = _service()
    assert asyncio.run(service.generate_sermon_summary("")) is None
    assert service.last_summary_error
