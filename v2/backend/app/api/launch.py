"""Preparation, rehearsal and delivery diagnostics. Control stays local."""
import asyncio
import json
import platform
import time
import uuid
from pathlib import Path
from typing import Literal

import numpy as np
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi import Request
from starlette.background import BackgroundTask
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field, ConfigDict
from ..core.config import DATA_DIR, RESOURCE_DIR, settings
from ..core.security import websocket_allowed, websocket_subprotocol
from ..services.rehearsal import DEMO_LINES, new_engine, detect

router = APIRouter()
audio_rehearsal_lock = asyncio.Lock()
kit_lock = asyncio.Lock()
kit_downloads = {}
screen_test = None
screen_test_lock = asyncio.Lock()


@router.post("/discovery/project")
async def discovery_project():
    from ..main import output_manager
    from .routes import ReferenceRequest, send_reference
    driver = output_manager.outputs.get("browser") if output_manager else None
    if not driver:
        raise HTTPException(503, "Le moteur d’écran n’est pas prêt.")
    if audio_rehearsal_lock.locked() or driver.current_scene.get("reference"):
        raise HTTPException(409, "Un passage ou une écoute est actif. Ouvrez la régie pour continuer.")
    return await send_reference(ReferenceRequest(reference="Jean 3:16"))


@router.post("/projection/test")
async def start_screen_test():
    from ..main import output_manager
    global screen_test
    driver = output_manager.outputs.get("browser") if output_manager else None
    if not driver:
        raise HTTPException(503, "Le moteur d’écran n’est pas prêt.")
    async with screen_test_lock:
        if audio_rehearsal_lock.locked() or driver.current_scene.get("reference"):
            raise HTTPException(409, "Effacez le passage et arrêtez l’écoute avant la mire.")
        previous = dict(driver.current_scene)
        await driver.send_scene({**previous, "reference": "TEST ÉCRAN", "text": "VersePro · contrôle avant culte\nLisez cette phrase depuis le fond de la salle.\nVérifiez les quatre bords de l’image.", "translations": {}})
        screen_test = {"scene_id": driver.current_scene["scene_id"], "previous": previous}
        return {"scene_id": screen_test["scene_id"]}


class ScreenTestFinish(BaseModel):
    scene_id: str = Field(..., max_length=64)


@router.post("/projection/test/finish")
async def finish_screen_test(data: ScreenTestFinish):
    from ..main import output_manager
    global screen_test
    driver = output_manager.outputs.get("browser") if output_manager else None
    async with screen_test_lock:
        if not screen_test or screen_test["scene_id"] != data.scene_id:
            return {"restored": False}
        restored = bool(driver and driver.current_scene.get("scene_id") == data.scene_id)
        if restored:
            await driver.send_scene(screen_test["previous"])
        screen_test = None
        return {"restored": restored}

async def native_operation(function, *args):
    """Wait for native work before cancellation can release its model memory."""
    task = asyncio.create_task(asyncio.to_thread(function, *args))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        await task
        raise


def expire_kit(key):
    import shutil
    entry = kit_downloads.pop(key, None)
    if entry:
        asyncio.create_task(asyncio.to_thread(shutil.rmtree, entry[0].parent, ignore_errors=True))


async def cleanup_kits():
    import shutil
    paths = [entry[0].parent for entry in kit_downloads.values()]
    kit_downloads.clear()
    for path in paths:
        await asyncio.to_thread(shutil.rmtree, path, ignore_errors=True)


@router.post("/offline-kit/prepare-export")
async def prepare_kit_export():
    from ..services.offline_kit import export_kit
    import secrets
    import shutil
    if kit_lock.locked():
        raise HTTPException(409, "Un kit est déjà en cours de préparation.")
    async with kit_lock:
        for key, (path, expiry) in list(kit_downloads.items()):
            if expiry < time.time():
                shutil.rmtree(path.parent, ignore_errors=True)
                kit_downloads.pop(key, None)
        if len(kit_downloads) >= 2:
            raise HTTPException(409, "Deux kits sont déjà prêts. Téléchargez-les ou attendez leur expiration.")
        try:
            path = await asyncio.to_thread(export_kit)
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        key = secrets.token_urlsafe(32)
        kit_downloads[key] = (path, time.time()+900)
        asyncio.get_running_loop().call_later(900, expire_kit, key)
    return {"download": f"/api/v1/offline-kit/download?key={key}", "bytes": path.stat().st_size}

@router.get("/offline-kit/download")
async def download_kit(key: str):
    import shutil
    entry = kit_downloads.pop(key, None)
    if not entry:
        raise HTTPException(404, "Lien de téléchargement expiré.")
    path, expiry = entry
    if expiry < time.time():
        shutil.rmtree(path.parent, ignore_errors=True)
        raise HTTPException(410, "Lien de téléchargement expiré.")
    return FileResponse(path, filename="versepro-offline.zip", media_type="application/zip", background=BackgroundTask(shutil.rmtree, path.parent, ignore_errors=True))

@router.get("/offline-kit")
async def kit_status():
    from ..services.offline_kit import inventory
    return await asyncio.to_thread(inventory)

@router.get("/offline-kit/export")
async def kit_export():
    from ..services.offline_kit import export_kit
    import shutil
    if kit_lock.locked():
        raise HTTPException(409, "Un kit est déjà en cours de traitement.")
    async with kit_lock:
        try:
            path = await asyncio.to_thread(export_kit)
        except ValueError as exc:
            raise HTTPException(422, str(exc))
    return FileResponse(path, filename="versepro-offline.zip", media_type="application/zip", background=BackgroundTask(shutil.rmtree, path.parent, ignore_errors=True))

@router.post("/offline-kit/import")
async def kit_import(request: Request):
    import tempfile
    import os
    import zipfile
    from ..services.offline_kit import import_kit, MAX_BYTES
    from ..main import nemotron_service
    if kit_lock.locked() or audio_rehearsal_lock.locked() or (nemotron_service and nemotron_service._running):
        raise HTTPException(409, "Arrêtez l’écoute et attendez la fin des opérations locales.")
    async with kit_lock:
        fd, name = tempfile.mkstemp(prefix="versepro-kit-upload-", suffix=".zip")
        total = 0
        try:
            with os.fdopen(fd, "wb") as stream:
                async for chunk in request.stream():
                    total += len(chunk)
                    if total > MAX_BYTES:
                        raise HTTPException(413, "Kit limité à 1,6 Go.")
                    await asyncio.to_thread(stream.write, chunk)
            return await asyncio.to_thread(import_kit, name)
        except (ValueError, KeyError, TypeError, zipfile.BadZipFile) as exc:
            raise HTTPException(422, str(exc)[:250])
        finally:
            Path(name).unlink(missing_ok=True)

class SharingRequest(BaseModel):
    role: Literal["viewer", "operator"] = "viewer"

@router.get("/companion")
async def companion_status():
    from ..services.companion import companion
    return companion.status()

@router.post("/companion/start")
async def companion_start(data: SharingRequest):
    from ..services.companion import companion
    from .routes import _get_all_local_ips
    try:
        result = await companion.start(data.role)
    except (OSError, RuntimeError) as exc:
        raise HTTPException(503, str(exc))
    ips = _get_all_local_ips()
    return {**result, "ips": ips, "url": f"http://{ips[0]}:{result['port']}/#token={result['token']}"}

@router.post("/companion/stop")
async def companion_stop():
    from ..services.companion import companion
    await companion.stop()
    return companion.status()

class ServiceFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format: Literal["versepro-service"] = "versepro-service"
    schema_version: Literal[1] = 1
    name: str = Field("Culte du dimanche", min_length=1, max_length=120)
    date: str = Field("", max_length=10, pattern=r"^(\d{4}-\d{2}-\d{2})?$")
    notes: str = Field("", max_length=50000)
    references: list[str] = Field(default_factory=list, max_length=100)
    bible_version: str = Field("LSG", max_length=30, pattern=r"^[\w-]+$")
    room_name: str = Field("", max_length=120)
    projection_theme: Literal["presentation", "classic", "minimal", "cinema", "lower-third"] = "presentation"

def service_directory():
    path = Path(DATA_DIR) / "services"
    path.mkdir(parents=True, exist_ok=True)
    return path

@router.get("/services")
async def services():
    result = []
    for path in sorted(service_directory().glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:100]:
        try:
            result.append({"id": path.stem, **ServiceFile.model_validate_json(path.read_text()).model_dump()})
        except (ValueError, OSError):
            continue
    return {"services": result}

@router.post("/services")
async def save_service(data: ServiceFile):
    from ..main import verse_parser
    if not verse_parser:
        raise HTTPException(503, "Le moteur biblique démarre encore.")
    canonical, invalid = [], []
    for reference in data.references:
        parsed = await verse_parser.parse(reference[:200], skip_text_search=True)
        if not parsed or not parsed.get("verse_start"):
            invalid.append(reference[:200])
        elif parsed["reference"] not in canonical:
            canonical.append(parsed["reference"])
    if invalid:
        raise HTTPException(422, "Références à corriger : " + ", ".join(invalid))
    data.references = canonical
    ident = uuid.uuid4().hex
    path = service_directory() / (ident + ".json")
    temp = path.with_suffix(".tmp")
    temp.write_text(data.model_dump_json(indent=2), encoding="utf-8")
    temp.replace(path)
    return {"id": ident, **data.model_dump()}

@router.get("/delivery")
async def delivery():
    from ..main import output_manager
    driver = output_manager.outputs.get("browser") if output_manager else None
    return driver.delivery_status() if driver else {"connected": 0, "rendered": 0, "clients": [], "reference": ""}

@router.get("/diagnostic")
async def diagnostic():
    from ..main import semantic_service, nemotron_service, output_manager
    # Whitelist only. No settings dump, tokens, paths, transcript or audio.
    return {"format": "versepro-diagnostic", "version": settings.VERSION,
            "generated_at": time.time(), "system": platform.system(), "architecture": platform.machine(),
            "asr_mode": settings.ASR_DEFAULT_ENGINE, "safe_mode": settings.SUNDAY_SAFE_MODE,
            "local_model_present": bool(nemotron_service and nemotron_service.is_ready),
            "semantic_ready": bool(semantic_service and semantic_service.initialized),
            "outputs": [{"name": name, "enabled": bool(driver.enabled)} for name, driver in (output_manager.outputs.items() if output_manager else [])],
            "display_clients": (await delivery())["connected"]}

@router.get("/rehearsal/demo")
async def demo():
    return {"lines": DEMO_LINES, "audio_url": "/api/v1/rehearsal/demo.wav", "voice": "Voix de synthèse française · exercice inclus"}

@router.get("/rehearsal/demo.wav")
async def demo_audio():
    path = Path(RESOURCE_DIR) / "data" / "rehearsal" / "demo-fr.wav"
    if not path.is_file():
        raise HTTPException(404, "Audio de démonstration absent de ce paquet.")
    return FileResponse(path, media_type="audio/wav")

class PracticeText(BaseModel):
    text: str = Field(..., min_length=2, max_length=5000)

class CorrectionRequest(BaseModel):
    text: str = Field(..., min_length=12, max_length=1000)
    reference: str = Field(..., min_length=3, max_length=200)


class CorrectionFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format: Literal["versepro-corrections"]
    schema_version: Literal[1]
    corrections: list[CorrectionRequest] = Field(..., max_length=200)


@router.get("/learning/corrections")
async def export_corrections():
    from ..services.local_corrections import read
    return {"format": "versepro-corrections", "schema_version": 1,
            "corrections": [{"text": text, "reference": ref} for text, ref in read().items()]}


@router.post("/learning/import")
async def import_corrections(data: CorrectionFile):
    from ..main import verse_parser
    from ..services.local_corrections import read, write, normalized
    if not verse_parser:
        raise HTTPException(503, "Le moteur biblique démarre encore.")
    validated = {}
    for row in data.corrections:
        key = normalized(row.text)
        parsed = await verse_parser.parse(row.reference, skip_text_search=True)
        if len(key.split()) < 4 or not parsed or not parsed.get("verse_start"):
            raise HTTPException(422, "Une correction est incomplète ou sa référence est invalide.")
        validated[key] = parsed["reference"]
    rows = {**read(), **validated}
    if len(rows) > 200:
        raise HTTPException(422, "La mémoire est limitée à 200 phrases. Réinitialisez-la avant cet import.")
    write(rows)
    return {"count": len(rows)}

@router.post("/learning/corrections")
async def remember_correction(data: CorrectionRequest):
    from ..main import verse_parser
    from ..services.local_corrections import remember
    if not verse_parser:
        raise HTTPException(503, "Le moteur biblique démarre encore.")
    parsed = await verse_parser.parse(data.reference, skip_text_search=True)
    if not parsed or not parsed.get("verse_start"):
        raise HTTPException(422, "Référence introuvable dans la Bible locale.")
    try:
        count = remember(data.text, parsed["reference"])
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return {"reference": parsed["reference"], "count": count}

@router.post("/learning/reset")
async def reset_corrections():
    from ..services.local_corrections import write
    write({})
    return {"count": 0}

@router.post("/rehearsal/detect")
async def practice_text(data: PracticeText):
    from ..main import verse_parser, semantic_service
    if not verse_parser:
        raise HTTPException(503, "Le moteur biblique démarre encore.")
    return await detect(new_engine(verse_parser, semantic_service), data.text)

@router.websocket("/rehearsal/audio")
async def practice_audio(ws: WebSocket):
    if not websocket_allowed(ws):
        await ws.close(code=1008)
        return
    await ws.accept(subprotocol=websocket_subprotocol(ws))
    from ..main import verse_parser, semantic_service, nemotron_service
    from ..services.nemotron_service import NemotronService
    if audio_rehearsal_lock.locked() or kit_lock.locked() or (nemotron_service and nemotron_service._running):
        await ws.send_json({"type": "error", "message": "Arrêtez l’écoute en direct ou la répétition précédente."})
        await ws.close()
        return
    if not nemotron_service or not nemotron_service.is_ready or not nemotron_service.runtime_available:
        await ws.send_json({"type": "error", "message": "Préparez le moteur local dans Paramètres. L’exercice guidé reste disponible."})
        await ws.close()
        return
    async with audio_rehearsal_lock:
        engine = new_engine(verse_parser, semantic_service)
        model = NemotronService()
        total, started = 0, time.perf_counter()
        try:
            await native_operation(model.start)
            await ws.send_json({"type": "ready"})
            while True:
                message = await asyncio.wait_for(ws.receive(), timeout=60)
                if message["type"] == "websocket.disconnect":
                    break
                if message.get("text"):
                    if message["text"] != "finish":
                        raise ValueError("Commande audio inconnue.")
                    # Let the streaming decoder consume its acoustic look-ahead.
                    # Synthetic silence is excluded from the source duration.
                    if total:
                        for _ in range(4):
                            await native_operation(model.accept_waveform, np.zeros(8000, dtype=np.int16))
                    await native_operation(model.stop)
                    final = model.prendre_enonce_fini()
                    if final:
                        await ws.send_json({"type": "result", **await detect(engine, final), "audio_seconds": total / 32000})
                    await ws.send_json({"type": "done", "audio_seconds": total / 32000, "processing_seconds": round(time.perf_counter()-started, 2)})
                    break
                chunk = message.get("bytes", b"")
                total += len(chunk)
                if len(chunk) > 64000 or len(chunk) % 2 or total > 32000 * 600:
                    raise ValueError("Audio limité à 10 minutes, PCM mono 16 kHz, blocs de 2 secondes maximum.")
                await native_operation(model.accept_waveform, np.frombuffer(chunk, dtype="<i2"))
                if model.last_error:
                    raise ValueError("Le moteur local a interrompu le décodage.")
                final = model.prendre_enonce_fini()
                if final:
                    await ws.send_json({"type": "result", **await detect(engine, final), "audio_seconds": total / 32000})
                await ws.send_json({"type": "ready", "partial": model.get_result(), "audio_seconds": total / 32000})
        except (WebSocketDisconnect, asyncio.CancelledError):
            pass
        except Exception as exc:
            try:
                await ws.send_json({"type": "error", "message": str(exc) if isinstance(exc, (ValueError, asyncio.TimeoutError)) else "Impossible de décoder cet audio avec le moteur local."})
            except Exception:
                pass
        finally:
            await native_operation(model.stop)
            await native_operation(model._fermer_natif, True)
            try:
                await ws.close()
            except Exception:
                pass

@router.get("/history/sessions/{session_id}/carnet.html")
async def carnet(session_id: int):
    from .routes import _session_et_versets
    from ..services.session_export import vers_carnet
    session, verses = await _session_et_versets(session_id)
    return Response(vers_carnet(session, verses), media_type="text/html", headers={"Content-Disposition": 'attachment; filename="carnet-du-culte.html"'})
