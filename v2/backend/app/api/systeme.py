"""Santé, prévol, réseau local, mode panique et mises à jour."""

# `Request` sert à l'annotation de get_network_info (QR Code mobile) et
# n'était pas importé. Python 3.14 n'évalue plus les annotations à la
# définition (PEP 649), donc l'oubli passait inaperçu ici — mais la CI et le
# gel PyInstaller tournent en 3.12, où l'annotation est évaluée tout de suite :
#
#     File "app/api/routes.py", line 322, in <module>
#       async def get_network_info(request: Request):
#     NameError: name 'Request' is not defined
#
# L'intégration est rouge depuis, et six fichiers de tests ne se collectent
# même plus. Un développement fait sur une version de Python plus récente que
# celle qui construit le produit ne voit pas ce genre d'erreur.
from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import Dict
import asyncio
import re

router = APIRouter()


class HealthResponse(BaseModel):
    """Réponse de santé"""
    status: str
    version: str
    services: Dict[str, bool]


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Endpoint de santé"""
    from ..main import output_manager, deepgram_service, verse_parser

    propresenter_connected = False
    if output_manager and "propresenter" in output_manager.outputs:
        propresenter_connected = await output_manager.outputs["propresenter"].is_connected()

    return {
        "status": "healthy",
        "version": "2.2.1",
        "services": {
            "deepgram": deepgram_service is not None,
            "propresenter": propresenter_connected,
            "parser": verse_parser is not None
        }
    }


@router.get("/preflight")
async def preflight_check(probe_cloud: bool = False):
    """Contrôle opérationnel avant le direct, sans déclencher de téléchargement."""
    import asyncio
    import shutil
    from ..core.config import DATA_DIR, settings
    from ..main import (
        db_service,
        deepgram_service,
        output_manager,
        semantic_service,
        verse_parser,
        vosk_service,
        nemotron_service,
    )
    from ..services.secret_store import secret_store

    disk = shutil.disk_usage(DATA_DIR)
    local_asr = bool(
        (nemotron_service and nemotron_service.is_ready and nemotron_service.runtime_available)
        or (vosk_service and vosk_service.initialized)
    )
    cloud_configured = bool(settings.DEEPGRAM_API_KEY)
    cloud_verified = False
    cloud_error = ""
    if probe_cloud and cloud_configured and deepgram_service and deepgram_service.client:
        session = None
        async def ignore_probe_message(_):
            return None
        try:
            session = await asyncio.wait_for(
                deepgram_service.create_session(ignore_probe_message),
                timeout=5.0,
            )
            cloud_verified = bool(session.is_active)
        except Exception as exc:
            cloud_error = type(exc).__name__
        finally:
            if session:
                await session.close()

    browser = output_manager.outputs.get("browser") if output_manager else None
    browser_output = False
    browser_clients = 0
    if browser:
        try:
            browser_output = bool(browser.enabled)
            browser_clients = len(browser.connections)
        except Exception:
            browser_output = False

    configured_outputs = []
    if output_manager:
        for name, output in output_manager.outputs.items():
            if name == "browser" or not output.enabled:
                continue
            try:
                connected = bool(await output.is_connected())
            except Exception:
                connected = False
            configured_outputs.append((name, connected))

    cloud_ready = cloud_verified if probe_cloud else cloud_configured
    models_need_space = not local_asr or not bool(semantic_service and semantic_service.initialized)
    required_free = (4 if models_need_space else 1) * 1024 ** 3
    cloud_detail = (
        "Deepgram vérifié"
        if cloud_verified
        else f"Deepgram inaccessible ({cloud_error})"
        if probe_cloud and cloud_configured
        else "Deepgram configuré, test au démarrage du micro"
        if cloud_configured
        else ""
    )
    rendered_clients = browser.delivery_status()["rendered"] if browser and hasattr(browser, "delivery_status") else 0
    output_detail = (
        f"Moteur prêt · {browser_clients} écran(s) connecté(s) · {rendered_clients} rendu(s) confirmé(s)"
        if browser_output
        else "Le moteur d'affichage ne répond pas"
    )
    if configured_outputs:
        summary = ", ".join(f"{name}: {'prêt' if ok else 'indisponible'}" for name, ok in configured_outputs)
        output_detail = f"{output_detail} · {summary}"

    checks = [
        {"id": "database", "label": "Base locale", "ok": bool(db_service and db_service.db), "critical": True},
        {"id": "bible", "label": "Corpus biblique", "ok": bool(verse_parser and verse_parser.bible_loader.versions), "critical": True},
        {"id": "asr", "label": "Transcription", "ok": cloud_ready or local_asr, "critical": True,
         "detail": cloud_detail or ("Nemotron/Vosk prêt" if local_asr else "Préparer Nemotron/Vosk ou ajouter une clé Deepgram")},
        {"id": "output", "label": "Moteur de sortie", "ok": browser_output, "critical": True,
         "detail": output_detail},
        {"id": "configured_outputs", "label": "Sorties activées",
         "ok": all(ok for _, ok in configured_outputs), "critical": False,
         "detail": "Toutes prêtes" if all(ok for _, ok in configured_outputs) else "Une sortie optionnelle est indisponible"},
        {"id": "semantic", "label": "Recherche sémantique locale", "ok": bool(semantic_service and semantic_service.initialized), "critical": False},
        {"id": "disk", "label": "Espace disque", "ok": disk.free >= required_free, "critical": True,
         "detail": f"{disk.free / (1024 ** 3):.1f} Go libres · {required_free / (1024 ** 3):.0f} Go requis"},
        {"id": "secrets", "label": "Trousseau système", "ok": secret_store.available, "critical": False},
    ]
    return {
        "ready": all(item["ok"] for item in checks if item["critical"]),
        "checks": checks,
        "safety": {
            "sunday_safe_mode": settings.SUNDAY_SAFE_MODE,
            "shadow_mode": settings.SHADOW_MODE,
            "auto_send": settings.PROPRESENTER_AUTO_SEND,
        },
    }


def _get_all_local_ips() -> list[str]:
    """Renvoie la liste des adresses IP locales de la machine (LAN/Wi-Fi)."""
    import socket
    import re
    import subprocess
    
    ips = []
    
    # 1. Socket UDP vers broadcast / passerelle (fonctionne même sans connexion internet)
    for target in ('10.255.255.255', '192.168.1.255', '8.8.8.8'):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.3)
            s.connect((target, 80))
            ip = s.getsockname()[0]
            s.close()
            if ip and not ip.startswith("127.") and ip not in ips:
                ips.append(ip)
        except Exception:
            pass

    # 2. Hostname interfaces
    try:
        hostname = socket.gethostname()
        for ip in socket.gethostbyname_ex(hostname)[2]:
            if not ip.startswith("127.") and not ip.startswith("169.254.") and ip not in ips:
                ips.append(ip)
    except Exception:
        pass

    # 3. Interfaces système ifconfig
    try:
        res = subprocess.run(["ifconfig"], capture_output=True, text=True, timeout=1)
        matches = re.findall(r"inet\s+(192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+|172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+)", res.stdout)
        for cand in matches:
            if cand not in ips:
                ips.append(cand)
    except Exception:
        pass

    return ips or ["127.0.0.1"]


def _get_local_ip() -> str:
    """Détecte l'adresse IP locale LAN principale de la machine."""
    ips = _get_all_local_ips()
    return ips[0] if ips else "127.0.0.1"


@router.get("/network/info")
async def get_network_info(request: Request):
    """Renvoie les coordonnées réseau locales pour la connexion des téléphones mobiles (/follow, /stage)."""
    from ..core.config import settings
    all_ips = _get_all_local_ips()
    ip = all_ips[0] if all_ips else "127.0.0.1"
    
    # Résolution du port réel d'écoute :
    # 1. request.url.port (si présent)
    # 2. VERSEPRO_PORT env var (ex: 17871 dans l'application Tauri)
    # 3. settings.PORT si défini
    # 4. Repli 17871
    port = request.url.port or int(os.environ.get("VERSEPRO_PORT", getattr(settings, "PORT", 17871)))
    base_url = f"http://{ip}:{port}"
    return {
        "local_ip": ip,
        "available_ips": all_ips,
        "port": port,
        "base_url": base_url,
        "follow_url": f"{base_url}/follow",
        "stage_url": f"{base_url}/stage",
        "output_url": f"{base_url}/output",
    }


@router.post("/safety/panic")
async def activate_panic_mode():
    """Coupe les automatismes et efface immédiatement toutes les sorties."""
    from ..core.config import settings
    from ..services.database import get_database
    from ..main import broadcast_projection
    settings.PROPRESENTER_AUTO_SEND = False
    settings.SUNDAY_SAFE_MODE = True
    settings.SHADOW_MODE = False
    db = get_database()
    await db.set_setting("auto_send", False)
    await db.set_setting("sunday_safe_mode", True)
    await db.set_setting("shadow_mode", False)
    receipts = await broadcast_projection("", "")
    return {
        "status": "safe",
        "auto_send": False,
        "sunday_safe_mode": True,
        "shadow_mode": False,
        "screen_cleared": bool(receipts.get("browser")),
        "outputs": receipts,
    }


@router.get("/session/current")
async def get_current_session():
    """ID de la session de culte en cours (pour restaurer la file après un rechargement)"""
    from .. import main as main_module
    return {"session_id": main_module.current_session_id}

@router.get("/update/check")
async def update_check():
    """État de mise à jour. Renvoie toujours 200, même hors ligne : ce contrôle
    est un confort, jamais une condition pour utiliser l'application."""
    from ..services.update_check import check_for_update
    return await check_for_update()
