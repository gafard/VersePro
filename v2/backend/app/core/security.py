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
    "/api/v1/offline-kit/download",
    "/api/v1/bibles", "/api/v1/bibles/catalogue", "/api/v1/bibles/imported"
}

# Ressources en LECTURE SEULE que les pages publiques chargent elles-mêmes.
#
# Les écrans de diffusion sont ouverts sur le vidéoprojecteur, dans un onglet
# qui n'a jamais vu le jeton de session — il n'existe que dans la fenêtre de
# la régie. Tout ce qu'ils réclament doit donc passer sans jeton, sinon la
# page s'affiche amputée : sans /fonts, la projection tombe en police système
# et les bandeaux perdent l'identité du produit.
#
# Un préfixe ici n'ouvre qu'un GET sur des fichiers déjà destinés à l'écran de
# l'église. Ce n'est pas une exemption pour l'API de pilotage.
PUBLIC_PREFIXES = ("/api/v1/bibles/", "/fonts/", "/assets/")


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
    if request.url.path in PUBLIC_PATHS or request.url.path.startswith(PUBLIC_PREFIXES):
        return True
    if request.method == "OPTIONS":
        return _trusted_origin(request.headers)
    if _token_valid(_extract_token(request.headers, request.query_params)):
        return True
    host = request.client.host if request.client else None
    # `not _configured_tokens()` EST LA GARDE, et elle avait disparu.
    #
    # Sans elle, tout appel local sans en-tête Origin passait — même avec un
    # jeton de session configuré, c'est-à-dire dans l'application empaquetée,
    # où Tauri en génère un à chaque lancement. Le jeton était donc exigé de
    # personne : n'importe quel programme de la machine pouvait lire et écrire
    # /api/v1/settings, piloter la projection, vider l'historique. Vérifié :
    # /api/v1/control/status et /api/v1/settings répondaient 200 sans jeton.
    #
    # Elle est tombée en réparant l'accès au catalogue de bibles (d7832fd),
    # parce que les pages de diffusion chargent des ressources sans jeton. Ce
    # besoin-là est réel, mais il se traite par PUBLIC_PREFIXES — une liste de
    # GET en lecture seule — et non en désarmant l'authentification entière.
    #
    # La branche subsiste pour le DÉVELOPPEMENT, où aucun jeton n'est
    # configuré : la console doit continuer d'y parler au backend sans rien
    # présenter.
    if _is_local(host) and not _configured_tokens() and (
        _trusted_origin(request.headers) or not request.headers.get("origin")
    ):
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
