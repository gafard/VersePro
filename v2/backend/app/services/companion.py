"""Opt-in LAN listener. This app never mounts the private control API."""
import asyncio
import hmac
import secrets
import socket
import time
from urllib.parse import urlsplit
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse

class Companion:
    def __init__(self):
        self.server = None
        self.task = None
        self.port = None
        self.token = ""
        self.expires = 0
        self.role = "viewer"
        self.clients = set()
        self.lock = asyncio.Lock()
        self.app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
        self.app.add_api_route("/", self.page, methods=["GET"])
        self.app.add_api_websocket_route("/stream", self.stream)

    async def page(self):
        from ..main import _get_template_path
        return HTMLResponse(_get_template_path("companion.html").read_text(), headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})

    def valid(self, token):
        return bool(self.token and time.time() < self.expires and hmac.compare_digest(token, self.token))

    def status(self):
        active = bool(self.server and self.server.started and time.time() < self.expires)
        return {"active": active, "port": self.port, "expires_at": self.expires, "role": self.role, "clients": len(self.clients)}

    async def start(self, role):
        async with self.lock:
            await self.stop()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("0.0.0.0", 0))
                sock.listen(128)
                self.port = sock.getsockname()[1]
                self.token = secrets.token_urlsafe(32)
                self.role = role
                self.expires = time.time() + 8 * 3600
                self.server = uvicorn.Server(uvicorn.Config(self.app, log_level="error", access_log=False, lifespan="off", ws_max_size=4096))
                self.server.install_signal_handlers = lambda: None
                self.task = asyncio.create_task(self.server.serve(sockets=[sock]))
                for _ in range(100):
                    if self.server.started:
                        return {**self.status(), "token": self.token}
                    if self.task.done():
                        raise RuntimeError("Le partage local n’a pas pu démarrer.")
                    await asyncio.sleep(.02)
                raise RuntimeError("Le partage local ne répond pas.")
            except BaseException:
                sock.close()
                await self.stop()
                raise

    async def stop(self):
        self.token = ""
        self.expires = 0
        for client in list(self.clients):
            try:
                await client.close(code=1008, reason="Partage arrêté")
            except Exception:
                pass
        self.clients.clear()
        if self.server:
            self.server.should_exit = True
        if self.task:
            try:
                await asyncio.wait_for(asyncio.shield(self.task), 3)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self.task.cancel()
                await asyncio.gather(self.task, return_exceptions=True)
        self.task = self.server = None

    async def stream(self, ws: WebSocket):
        protocols = ws.headers.get("sec-websocket-protocol", "").split(",")
        token = next((p.strip()[len("versepro.auth."):] for p in protocols if p.strip().startswith("versepro.auth.")), "")
        origin = ws.headers.get("origin", "")
        if not self.valid(token) or (origin and urlsplit(origin).netloc != ws.headers.get("host")):
            await ws.close(code=1008)
            return
        await ws.accept(subprotocol="versepro")
        from ..main import output_manager, verse_parser, broadcast_projection, current_projection_slide
        driver = output_manager.outputs.get("browser") if output_manager else None
        if not driver:
            await ws.close(code=1011)
            return
        self.clients.add(ws)
        await ws.send_json({"type": "permissions", "role": self.role})
        await driver.register_connection(ws)
        last_command = 0
        try:
            while self.valid(token):
                try:
                    data = await asyncio.wait_for(ws.receive_json(), timeout=min(20, max(0.1, self.expires-time.time())))
                except asyncio.TimeoutError:
                    continue
                if not isinstance(data, dict):
                    continue
                if data.get("type") == "rendered":
                    driver.acknowledge(ws, data)
                    continue
                if self.role != "operator" or time.monotonic()-last_command < .4:
                    continue
                last_command = time.monotonic()
                command = data.get("type")
                if command == "clear":
                    await broadcast_projection("", "")
                elif command == "project":
                    ref = str(data.get("reference", ""))[:200]
                    parsed = await verse_parser.parse(ref, skip_text_search=True)
                    if parsed and parsed.get("verse_start"):
                        await broadcast_projection(parsed["text"], parsed["reference"], translations=parsed.get("translations"))
                    else:
                        await ws.send_json({"type": "error", "message": "Référence introuvable."})
                elif command in {"next", "prev"}:
                    from .. import main
                    parsed = await verse_parser.parse(main.current_projection_slide.get("reference", ""), skip_text_search=True)
                    if parsed and parsed.get("verse_start"):
                        n = parsed["verse_start"] + (1 if command == "next" else -1)
                        text = verse_parser.bible_loader.get_verse_text(parsed["book_abbr"], parsed["chapter"], n) if n > 0 else ""
                        if text:
                            await broadcast_projection(text, f"{parsed['book_abbr']} {parsed['chapter']}:{n}")
        except (WebSocketDisconnect, ValueError, RuntimeError):
            pass
        finally:
            self.clients.discard(ws)
            driver.unregister_connection(ws)
            try:
                await ws.close(code=1008)
            except Exception:
                pass

companion = Companion()
