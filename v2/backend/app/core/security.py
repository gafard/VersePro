"""
VersePro v2 — Contrôle d'accès réseau

Modèle de sécurité :
- Les clients locaux (127.0.0.1 / ::1) sont de confiance : la console opérateur
  tourne sur la même machine que le backend (proxy Vite).
- Les clients distants (LAN) doivent fournir le jeton API_TOKEN (.env),
  via l'en-tête "Authorization: Bearer <token>" ou le paramètre "?token=".
- L'écran de projection (/projection, /ws/projection) reste public :
  il n'expose que le contenu déjà affiché sur l'écran de l'église.
"""

import hmac
from fastapi import Request, WebSocket
from loguru import logger

from .config import settings

LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}

# Chemins accessibles sans authentification (lecture d'affichage uniquement)
PUBLIC_PATHS = {"/", "/health", "/projection", "/ws/projection"}


def _is_local(host: str | None) -> bool:
    return (host or "") in LOCAL_HOSTS


def _token_valid(token: str | None) -> bool:
    if not settings.API_TOKEN:
        return False
    return hmac.compare_digest(token or "", settings.API_TOKEN)


def _extract_token(headers, query_params) -> str:
    auth = headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return query_params.get("token", "")


def http_request_allowed(request: Request) -> bool:
    """Autorise une requête HTTP : locale, chemin public, ou jeton valide."""
    if request.url.path in PUBLIC_PATHS:
        return True
    host = request.client.host if request.client else None
    if _is_local(host):
        return True
    if _token_valid(_extract_token(request.headers, request.query_params)):
        return True
    logger.warning(f"🚫 Requête HTTP refusée depuis {host} : {request.url.path}")
    return False


def websocket_allowed(websocket: WebSocket) -> bool:
    """Autorise une connexion WebSocket : locale ou jeton valide."""
    host = websocket.client.host if websocket.client else None
    if _is_local(host):
        return True
    if _token_valid(_extract_token(websocket.headers, websocket.query_params)):
        return True
    logger.warning(f"🚫 Connexion WebSocket refusée depuis {host} : {websocket.url.path}")
    return False
