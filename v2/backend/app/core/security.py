"""
VersePro v2 — Contrôle d'accès réseau

Modèle de sécurité :
- L'application Tauri génère un secret aléatoire à chaque lancement. Même un
  client local doit le présenter pour piloter la régie.
- API_TOKEN reste disponible pour les contrôleurs LAN explicitement autorisés.
- En développement sans jeton, seules les origines frontend déclarées sont
  acceptées. Une page web quelconque ne peut donc pas piloter localhost.
- L'écran de projection (/projection, /obs, /ws/projection) reste public :
  il n'expose que le contenu déjà affiché sur l'écran de l'église.
"""

import hmac
import os
from fastapi import Request, WebSocket
from loguru import logger

from .config import settings

LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}

# Chemins accessibles sans authentification (lecture d'affichage et métadonnées publiques)
PUBLIC_PATHS = {
    "/", "/health", "/projection", "/output", "/obs", "/follow", "/stage",
    "/ws/projection", "/ws/output",
    "/api/v1/bibles", "/api/v1/bibles/catalogue", "/api/v1/bibles/imported"
}


def _is_local(host: str | None) -> bool:
    return (host or "") in LOCAL_HOSTS


def _configured_tokens() -> tuple[str, ...]:
    return tuple(
        token for token in (
            os.environ.get("VERSEPRO_SESSION_TOKEN", "").strip(),
            settings.API_TOKEN.strip(),
        )
        if token
    )


def _token_valid(token: str | None) -> bool:
    candidate = token or ""
    return any(hmac.compare_digest(candidate, expected) for expected in _configured_tokens())


def _extract_token(headers, query_params) -> str:
    auth = headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    query_token = query_params.get("token", "")
    if query_token:
        return query_token
    # Le navigateur ne permet pas d'ajouter Authorization au handshake
    # WebSocket. Le secret voyage donc dans un sous-protocole, jamais dans l'URL.
    protocols = headers.get("sec-websocket-protocol", "")
    for protocol in protocols.split(","):
        protocol = protocol.strip()
        if protocol.startswith("versepro.auth."):
            return protocol.removeprefix("versepro.auth.")
    return ""


def _trusted_origin(headers) -> bool:
    origin = (headers.get("origin") or "").rstrip("/")
    return bool(origin and origin in {item.rstrip("/") for item in settings.cors_origins})


def http_request_allowed(request: Request) -> bool:
    """Autorise l'affichage public ou une commande authentifiée et locale."""
    if request.url.path in PUBLIC_PATHS or request.url.path.startswith("/api/v1/bibles/"):
        return True
    if request.method == "OPTIONS":
        return _trusted_origin(request.headers)
    if _token_valid(_extract_token(request.headers, request.query_params)):
        return True
    host = request.client.host if request.client else None
    if _is_local(host) and (_trusted_origin(request.headers) or not request.headers.get("origin")):
        return True
    logger.warning(f"🚫 Requête HTTP refusée depuis {host} : {request.url.path}")
    return False


def websocket_allowed(websocket: WebSocket) -> bool:
    """Autorise une connexion WebSocket authentifiée, ou le mode dev local."""
    if _token_valid(_extract_token(websocket.headers, websocket.query_params)):
        return True
    host = websocket.client.host if websocket.client else None
    if _is_local(host) and not _configured_tokens() and (
        _trusted_origin(websocket.headers) or not websocket.headers.get("origin")
    ):
        return True
    logger.warning(f"🚫 Connexion WebSocket refusée depuis {host} : {websocket.url.path}")
    return False


def websocket_subprotocol(websocket: WebSocket) -> str | None:
    """Sous-protocole sûr à confirmer dans la réponse WebSocket.

    L'application Tauri transmet le jeton dans un sous-protocole séparé, mais
    expose aussi le protocole public ``versepro``. Chromium tolère souvent que
    le serveur n'en confirme aucun ; WebView2 sous Windows peut alors refuser
    le canal après que l'API HTTP a déjà été déclarée prête. On confirme donc
    explicitement le protocole public, sans jamais renvoyer celui qui contient
    le secret de session.
    """
    requested = {
        protocol.strip()
        for protocol in websocket.headers.get("sec-websocket-protocol", "").split(",")
        if protocol.strip()
    }
    return "versepro" if "versepro" in requested else None
