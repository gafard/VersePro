"""Contrôle de mise à jour de secours pour l'interface navigateur.

L'application de bureau utilise l'Updater Tauri signé et installe la nouvelle
version après confirmation. Ce service reste utile en développement navigateur :
si une URL est renseignée, il compare la version à un manifeste simplifié et
affiche un lien de téléchargement.

Sans URL configurée, aucun appel réseau n'est émis. C'est le défaut : un outil
d'église doit pouvoir tourner sans jamais sortir du bâtiment.

Manifeste attendu :
    {"version": "2.1.0", "url": "https://…/telecharger", "notes": "…"}
"""
from typing import Any, Dict, Optional

import httpx
from loguru import logger

from ..core.config import settings


def parse_version(raw: str) -> tuple:
    """« 2.10.1 » -> (2, 10, 1). Les segments non numériques sont ignorés.

    Comparer des chaînes donnerait « 2.9.0 » > « 2.10.0 » ; on compare donc des
    entiers. Un suffixe (« 2.1.0-beta ») est tronqué à sa partie numérique.
    """
    parts = []
    for chunk in (raw or "").strip().lstrip("vV").split("."):
        digits = ""
        for char in chunk:
            if char.isdigit():
                digits += char
            else:
                break
        parts.append(int(digits) if digits else 0)
    return tuple(parts) or (0,)


def is_newer(candidate: str, current: str) -> bool:
    """Vrai si `candidate` est strictement postérieure à `current`."""
    a, b = parse_version(candidate), parse_version(current)
    longueur = max(len(a), len(b))
    a += (0,) * (longueur - len(a))
    b += (0,) * (longueur - len(b))
    return a > b


async def check_for_update() -> Dict[str, Any]:
    """Interroge le manifeste. N'échoue jamais bruyamment : hors ligne le
    dimanche matin, l'absence de réponse ne doit rien changer au culte."""
    current = settings.APP_VERSION
    resultat: Dict[str, Any] = {
        "current": current,
        "latest": None,
        "update_available": False,
        "url": None,
        "notes": None,
        "checked": False,
    }

    if not settings.UPDATE_CHECK_URL:
        return resultat

    try:
        async with httpx.AsyncClient(timeout=settings.UPDATE_CHECK_TIMEOUT) as client:
            reponse = await client.get(settings.UPDATE_CHECK_URL)
            reponse.raise_for_status()
            manifeste = reponse.json()
    except Exception as exc:
        # Réseau coupé, manifeste illisible, serveur absent : on se tait.
        logger.debug(f"Contrôle de mise à jour indisponible : {exc}")
        return resultat

    latest = str(manifeste.get("version") or "").strip()
    if not latest:
        logger.debug("Manifeste de mise à jour sans champ « version »")
        return resultat

    resultat.update({
        "latest": latest,
        "update_available": is_newer(latest, current),
        "url": manifeste.get("url"),
        "notes": manifeste.get("notes"),
        "checked": True,
    })
    return resultat
