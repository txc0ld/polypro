"""Minimal HTTP health server.

Exposes ``GET /healthz`` and ``GET /readyz`` for an external watchdog
(systemd, k8s liveness probe, or a uptime monitor). The server is async and
uses only ``asyncio`` from the standard library — no FastAPI dependency.

  - ``/healthz`` — returns 200 if the runtime hasn't tripped the kill switch
  - ``/readyz`` — returns 200 if heartbeat is fresh (within ``max_heartbeat_age_s``)
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from .incident import IncidentManager, State
from .subagents.heartbeat import Heartbeat


class HealthServer:
    def __init__(
        self,
        *,
        incidents: IncidentManager,
        heartbeat: Heartbeat | None = None,
        host: str = "127.0.0.1",
        port: int = 8642,
        max_heartbeat_age_s: float = 60.0,
    ) -> None:
        self.incidents = incidents
        self.heartbeat = heartbeat
        self.host = host
        self.port = port
        self.max_heartbeat_age_s = max_heartbeat_age_s
        self._server: asyncio.base_events.Server | None = None

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, self.host, self.port)

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def _handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            request_line = await reader.readline()
            if not request_line:
                return
            try:
                method, path, _ = request_line.decode("ascii", errors="replace").split(" ", 2)
            except ValueError:
                method, path = "GET", "/"
            # drain headers
            while True:
                line = await reader.readline()
                if line in (b"\r\n", b"\n", b""):
                    break

            status, body = self._dispatch(method.upper(), path.split("?")[0])
            payload = json.dumps(body).encode("utf-8")
            response = (
                f"HTTP/1.1 {status}\r\n"
                f"Content-Type: application/json\r\n"
                f"Content-Length: {len(payload)}\r\n"
                f"Connection: close\r\n"
                f"\r\n"
            ).encode("ascii") + payload
            writer.write(response)
            await writer.drain()
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:  # noqa: BLE001
                pass

    def _dispatch(self, method: str, path: str) -> tuple[str, dict]:
        if method != "GET":
            return "405 Method Not Allowed", {"error": "method_not_allowed"}
        if path == "/healthz":
            ok = self.incidents.state is not State.KILLED
            return ("200 OK" if ok else "503 Service Unavailable"), {
                "ok": ok, "state": self.incidents.state.value,
            }
        if path == "/readyz":
            hb = self.heartbeat.last_seen() if self.heartbeat else None
            if hb is None:
                return "503 Service Unavailable", {"ready": False, "reason": "no_heartbeat"}
            age = (datetime.now(timezone.utc) - hb).total_seconds()
            ok = age <= self.max_heartbeat_age_s and self.incidents.state is not State.KILLED
            return ("200 OK" if ok else "503 Service Unavailable"), {
                "ready": ok,
                "heartbeat_age_seconds": age,
                "state": self.incidents.state.value,
            }
        return "404 Not Found", {"error": "not_found", "path": path}
