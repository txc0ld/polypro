"""Dashboard HTTP route tests."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from polyflow.dashboard import DashboardServer
from polyflow.logger import ImmutableLogger
from polyflow.persistence import SQLiteStore
from polyflow.subagents.heartbeat import Heartbeat
from polyflow.types import Market, Outcome, Position, Side, Signal, Strategy


async def _request(host: str, port: int, path: str) -> tuple[int, dict[str, str], bytes]:
    reader, writer = await asyncio.open_connection(host, port)
    writer.write(f"GET {path} HTTP/1.1\r\nHost: x\r\n\r\n".encode("ascii"))
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
    header_lines = head.split(b"\r\n")
    status = int(header_lines[0].split(b" ")[1])
    headers: dict[str, str] = {}
    for line in header_lines[1:]:
        key, _, value = line.decode("ascii").partition(":")
        headers[key.lower()] = value.strip()
    return status, headers, body


def _market() -> Market:
    return Market(
        id="m-dashboard",
        event_id="e-dashboard",
        question="Will dashboard tests pass?",
        category="testing",
        close_time=datetime.now(timezone.utc) + timedelta(hours=6),
        resolution_rules="Resolved by CI outcome.",
        liquidity_usd=100_000.0,
        volume_24h_usd=125_000.0,
        spread_pct=1.5,
        yes_token_id="token-yes",
        no_token_id="token-no",
        tick_size=0.01,
        min_order_size=5.0,
        fee_rate_bps=200.0,
        neg_risk=False,
        market_quality=0.9,
        resolution_risk=0.05,
    )


def _signal() -> Signal:
    sig = Signal(
        market_id="m-dashboard",
        event_id="e-dashboard",
        token_id="token-yes",
        outcome=Outcome.YES,
        side=Side.BUY,
        strategy=Strategy.FOUR_LAYER_ALIGNMENT,
        market_price=0.52,
        model_probability=0.61,
        uncertainty=0.04,
        effective_edge=0.03,
        market_quality=0.9,
        resolution_risk=0.05,
        liquidity_score=0.8,
        confidence=0.7,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        evidence_refs=["unit-test"],
    )
    sig.score = 88.0
    sig.status = "candidate"
    return sig


async def _seed_paths(tmp_path: Path) -> tuple[Path, Path, Path]:
    db_path = tmp_path / "polyflow.db"
    log_path = tmp_path / "immutable.jsonl"
    heartbeat_path = tmp_path / "heartbeat.json"

    store = SQLiteStore(db_path)
    try:
        store.upsert_market(_market(), status="watching")
        store.insert_signal(_signal())
        store.upsert_position(
            Position(
                market_id="m-dashboard",
                token_id="token-yes",
                outcome=Outcome.YES,
                size=12.0,
                avg_price=0.52,
                market_value=6.48,
                max_loss=6.24,
            )
        )
        store.upsert_open_order(
            exchange_order_id="order-dashboard",
            client_order_id="client-dashboard",
            market_id="m-dashboard",
            token_id="token-yes",
            side="BUY",
            price=0.51,
            size=5.0,
            status="OPEN",
        )
        store.upsert_automation_source(
            {
                "name": "poly_data",
                "repo_url": "https://github.com/warproxxx/poly_data",
                "purpose": "Historical trade data",
                "integration_mode": "historical_backtest_data",
                "enabled": True,
                "pinned_commit": "b7c1d1703d6a3d1dfaa5f49c9ef7b4b899775392",
                "local_path": "/tmp/poly_data",
                "detected_commit": "b7c1d1703d6a3d1dfaa5f49c9ef7b4b899775392",
                "status": "ready",
                "reason_codes": [],
                "warning_codes": [],
                "required_files": ["update_all.py"],
                "commands": [],
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    finally:
        store.close()

    logger = ImmutableLogger(log_path)
    logger.log(
        actor="clob_adapter",
        action="place_order",
        market_id="m-dashboard",
        event_id="e-dashboard",
        payload={"order_id": "order-dashboard"},
    )
    await Heartbeat(heartbeat_path).tick()
    return db_path, log_path, heartbeat_path


@pytest.mark.asyncio
async def test_get_root_returns_html(tmp_path: Path) -> None:
    db_path, log_path, heartbeat_path = await _seed_paths(tmp_path)
    srv = DashboardServer(
        db_path=db_path,
        log_path=log_path,
        heartbeat_path=heartbeat_path,
        port=0,
    )
    await srv.start()
    try:
        port = srv._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]
        status, headers, body = await _request("127.0.0.1", port, "/")
    finally:
        await srv.stop()

    assert status == 200
    assert headers["content-type"].startswith("text/html")
    assert b"<!doctype html>" in body
    assert b"Operations Console" in body


@pytest.mark.asyncio
async def test_get_api_state_returns_dashboard_snapshot(tmp_path: Path) -> None:
    db_path, log_path, heartbeat_path = await _seed_paths(tmp_path)
    srv = DashboardServer(
        db_path=db_path,
        log_path=log_path,
        heartbeat_path=heartbeat_path,
        port=0,
    )
    await srv.start()
    try:
        port = srv._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]
        status, headers, body = await _request("127.0.0.1", port, "/api/state")
    finally:
        await srv.stop()

    payload = json.loads(body)
    assert status == 200
    assert headers["content-type"].startswith("application/json")
    assert set(payload) >= {
        "summary",
        "signals",
        "positions",
        "orders",
        "heartbeat",
        "automation_sources",
    }
    assert payload["summary"]["total_records"] == 1
    assert payload["summary"]["placed_orders"] == 1
    assert payload["summary"]["watching_markets"] == 1
    assert payload["heartbeat"]["fresh"] is True
    assert payload["signals"][0]["market_id"] == "m-dashboard"
    assert payload["positions"][0]["market_id"] == "m-dashboard"
    assert payload["orders"][0]["exchange_order_id"] == "order-dashboard"
    assert payload["summary"]["automation_sources_ready"] == 1
    assert payload["automation_sources"][0]["name"] == "poly_data"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "content_type", "needle"),
    [
        ("/dashboard.css", "text/css", b":root"),
        ("/dashboard.js", "application/javascript", b"connectStream"),
    ],
)
async def test_static_assets_return_200(
    tmp_path: Path, path: str, content_type: str, needle: bytes
) -> None:
    db_path, log_path, heartbeat_path = await _seed_paths(tmp_path)
    srv = DashboardServer(
        db_path=db_path,
        log_path=log_path,
        heartbeat_path=heartbeat_path,
        port=0,
    )
    await srv.start()
    try:
        port = srv._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]
        status, headers, body = await _request("127.0.0.1", port, path)
    finally:
        await srv.stop()

    assert status == 200
    assert headers["content-type"].startswith(content_type)
    assert needle in body


@pytest.mark.asyncio
async def test_unknown_route_returns_404(tmp_path: Path) -> None:
    db_path, log_path, heartbeat_path = await _seed_paths(tmp_path)
    srv = DashboardServer(
        db_path=db_path,
        log_path=log_path,
        heartbeat_path=heartbeat_path,
        port=0,
    )
    await srv.start()
    try:
        port = srv._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]
        status, headers, body = await _request("127.0.0.1", port, "/missing")
    finally:
        await srv.stop()

    payload = json.loads(body)
    assert status == 404
    assert headers["content-type"].startswith("application/json")
    assert payload == {"error": "not_found", "path": "/missing"}
