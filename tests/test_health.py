"""Health HTTP server tests."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from polyflow.health import HealthServer
from polyflow.incident import IncidentManager
from polyflow.subagents.heartbeat import Heartbeat


async def _request(host: str, port: int, path: str) -> tuple[int, dict]:
    reader, writer = await asyncio.open_connection(host, port)
    writer.write(f"GET {path} HTTP/1.1\r\nHost: x\r\n\r\n".encode())
    await writer.drain()
    raw = b""
    while True:
        chunk = await reader.read(1024)
        if not chunk:
            break
        raw += chunk
    writer.close()
    try:
        await writer.wait_closed()
    except Exception:  # noqa: BLE001
        pass

    head, _, body = raw.partition(b"\r\n\r\n")
    status_line = head.split(b"\r\n", 1)[0]
    status = int(status_line.split(b" ")[1])
    payload = json.loads(body) if body else {}
    return status, payload


@pytest.mark.asyncio
async def test_healthz_ok_when_healthy() -> None:
    srv = HealthServer(incidents=IncidentManager(), port=0)
    await srv.start()
    try:
        port = srv._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]
        status, body = await _request("127.0.0.1", port, "/healthz")
    finally:
        await srv.stop()
    assert status == 200
    assert body["ok"] is True


@pytest.mark.asyncio
async def test_healthz_503_when_killed() -> None:
    incidents = IncidentManager()
    incidents.trip_killed(code="X")
    srv = HealthServer(incidents=incidents, port=0)
    await srv.start()
    try:
        port = srv._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]
        status, body = await _request("127.0.0.1", port, "/healthz")
    finally:
        await srv.stop()
    assert status == 503
    assert body["ok"] is False


@pytest.mark.asyncio
async def test_readyz_requires_fresh_heartbeat(tmp_path: Path) -> None:
    incidents = IncidentManager()
    hb = Heartbeat(tmp_path / "hb.json")
    await hb.tick()
    srv = HealthServer(incidents=incidents, heartbeat=hb, port=0, max_heartbeat_age_s=10.0)
    await srv.start()
    try:
        port = srv._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]
        status, body = await _request("127.0.0.1", port, "/readyz")
    finally:
        await srv.stop()
    assert status == 200
    assert body["ready"] is True


@pytest.mark.asyncio
async def test_404() -> None:
    srv = HealthServer(incidents=IncidentManager(), port=0)
    await srv.start()
    try:
        port = srv._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]
        status, _ = await _request("127.0.0.1", port, "/nope")
    finally:
        await srv.stop()
    assert status == 404
