"""POLYFLOW real-time operations dashboard.

The dashboard is intentionally read-mostly. It observes SQLite, immutable logs,
and heartbeat state, then streams compact snapshots to the browser via
Server-Sent Events. It does not place, cancel, or mutate live orders.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .persistence import SQLiteStore
from .replay import iter_log, summarize
from .subagents.heartbeat import Heartbeat


def _json_default(obj: object) -> str:
    return str(obj)


def _json_response(status: str, body: dict) -> bytes:
    payload = json.dumps(body, default=_json_default).encode("utf-8")
    headers = (
        f"HTTP/1.1 {status}\r\n"
        "Content-Type: application/json; charset=utf-8\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "Cache-Control: no-store\r\n"
        "Connection: close\r\n"
        "\r\n"
    ).encode("ascii")
    return headers + payload


def _text_response(status: str, body: str, content_type: str) -> bytes:
    payload = body.encode("utf-8")
    headers = (
        f"HTTP/1.1 {status}\r\n"
        f"Content-Type: {content_type}; charset=utf-8\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "Cache-Control: no-store\r\n"
        "Connection: close\r\n"
        "\r\n"
    ).encode("ascii")
    return headers + payload


def _tail_log(path: Path, limit: int = 30) -> list[dict]:
    records = list(iter_log(path))
    out: list[dict] = []
    for r in records[-limit:]:
        out.append(
            {
                "ts": r.ts,
                "actor": r.actor,
                "action": r.action,
                "market_id": r.market_id,
                "event_id": r.event_id,
                "payload": r.payload,
            }
        )
    return out


@dataclass(frozen=True)
class DashboardSnapshot:
    db_path: Path
    log_path: Path
    heartbeat_path: Path

    def build(self) -> dict:
        store = SQLiteStore(self.db_path)
        try:
            replay = summarize(self.log_path)
            heartbeat = Heartbeat(self.heartbeat_path).last_seen()
            now = datetime.now(timezone.utc)
            heartbeat_age = (
                (now - heartbeat).total_seconds()
                if heartbeat is not None
                else None
            )

            watching = store.get_markets_by_status("watching")
            skipped = store.get_markets_by_status("skipped")
            resolved = store.get_markets_by_status("resolved")
            open_positions = store.get_open_positions()
            open_orders = store.get_open_orders()
            recent_signals = store.get_recent_signals(25)
            calibration = store.calibration_buckets()
            avg_clv = store.average_clv_bps()
            source_reliability = store.all_source_reliabilities()[:12]
            signal_counts = store.signal_counts_by_strategy()

            bankroll_at_risk = sum(float(p.get("max_loss") or 0.0) for p in open_positions)
            market_value = sum(float(p.get("market_value") or 0.0) for p in open_positions)
            avg_score = (
                sum(float(s.get("score") or 0.0) for s in recent_signals) / len(recent_signals)
                if recent_signals
                else 0.0
            )

            return {
                "generated_at": now.isoformat(),
                "paths": {
                    "db": str(self.db_path),
                    "log": str(self.log_path),
                    "heartbeat": str(self.heartbeat_path),
                },
                "heartbeat": {
                    "last_seen": heartbeat.isoformat() if heartbeat else None,
                    "age_seconds": heartbeat_age,
                    "fresh": heartbeat_age is not None and heartbeat_age <= 60.0,
                },
                "summary": {
                    "total_records": replay.total_records,
                    "placed_orders": replay.placed_orders,
                    "rejected_orders": replay.rejected_orders,
                    "kill_switch_events": replay.kill_switch_events,
                    "watching_markets": len(watching),
                    "open_positions": len(open_positions),
                    "open_orders": len(open_orders),
                    "bankroll_at_risk": bankroll_at_risk,
                    "market_value": market_value,
                    "average_signal_score": avg_score,
                    "average_clv_bps": avg_clv,
                    "calibration_buckets": len(calibration),
                },
                "markets": {
                    "watching": watching[:20],
                    "skipped_count": len(skipped),
                    "resolved_count": len(resolved),
                },
                "positions": open_positions,
                "orders": open_orders,
                "signals": recent_signals,
                "signal_counts": signal_counts,
                "source_reliability": source_reliability,
                "calibration": calibration,
                "log_tail": _tail_log(self.log_path, 30),
                "operator_intents": [
                    {
                        "id": "lockdown",
                        "label": "Lockdown",
                        "command": "set configs/policy.yaml mode: lockdown, then redeploy",
                    },
                    {
                        "id": "promotion",
                        "label": "Promotion Gate",
                        "command": "polyflow promotion-status --db logs/polyflow.db --log logs/immutable.jsonl",
                    },
                    {
                        "id": "reconcile",
                        "label": "Reconcile",
                        "command": "polyflow reconcile",
                    },
                ],
            }
        finally:
            store.close()


class DashboardServer:
    def __init__(
        self,
        *,
        db_path: str | Path = "logs/polyflow.db",
        log_path: str | Path = "logs/immutable.jsonl",
        heartbeat_path: str | Path | None = None,
        host: str = "127.0.0.1",
        port: int = 8643,
        stream_interval_s: float = 2.0,
    ) -> None:
        self.db_path = Path(db_path)
        self.log_path = Path(log_path)
        self.heartbeat_path = Path(heartbeat_path) if heartbeat_path else self.log_path.parent / "heartbeat.json"
        self.host = host
        self.port = port
        self.stream_interval_s = stream_interval_s
        self._server: asyncio.base_events.Server | None = None

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, self.host, self.port)

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def serve_forever(self) -> None:
        await self.start()
        if self._server is None:
            return
        async with self._server:
            await self._server.serve_forever()

    async def _handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            request_line = await reader.readline()
            if not request_line:
                return
            try:
                method, target, _ = request_line.decode("ascii", errors="replace").split(" ", 2)
            except ValueError:
                method, target = "GET", "/"
            while True:
                line = await reader.readline()
                if line in (b"\r\n", b"\n", b""):
                    break

            parsed = urlsplit(target)
            path = parsed.path
            query = parse_qs(parsed.query)

            if method.upper() != "GET":
                writer.write(_json_response("405 Method Not Allowed", {"error": "method_not_allowed"}))
                await writer.drain()
                return
            if path == "/api/stream":
                await self._stream(writer, query)
                return
            writer.write(self._dispatch(path))
            await writer.drain()
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:  # noqa: BLE001
                pass

    def _dispatch(self, path: str) -> bytes:
        if path in ("/", "/index.html"):
            return _text_response("200 OK", ASSET_INDEX_HTML, "text/html")
        if path == "/dashboard.css":
            return _text_response("200 OK", ASSET_DASHBOARD_CSS, "text/css")
        if path == "/dashboard.js":
            return _text_response("200 OK", ASSET_DASHBOARD_JS, "application/javascript")
        if path == "/api/state":
            return _json_response("200 OK", self._snapshot())
        return _json_response("404 Not Found", {"error": "not_found", "path": path})

    async def _stream(
        self, writer: asyncio.StreamWriter, query: dict[str, list[str]]
    ) -> None:
        try:
            limit = int(query.get("limit", ["0"])[0])
        except ValueError:
            limit = 0
        if limit <= 0:
            limit = 120
        header = (
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: text/event-stream; charset=utf-8\r\n"
            "Cache-Control: no-cache\r\n"
            "Connection: keep-alive\r\n"
            "\r\n"
        ).encode("ascii")
        writer.write(header)
        await writer.drain()
        for _ in range(limit):
            data = json.dumps(self._snapshot(), default=_json_default)
            writer.write(f"event: snapshot\ndata: {data}\n\n".encode("utf-8"))
            await writer.drain()
            await asyncio.sleep(self.stream_interval_s)

    def _snapshot(self) -> dict:
        return DashboardSnapshot(
            db_path=self.db_path,
            log_path=self.log_path,
            heartbeat_path=self.heartbeat_path,
        ).build()


def escaped_json_for_html(data: dict) -> str:
    return escape(json.dumps(data, default=_json_default), quote=True)


INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>POLYFLOW Ops</title>
  <link rel="stylesheet" href="/dashboard.css">
</head>
<body>
  <a class="skip-link" href="#main">Skip to main content</a>
  <header class="topbar">
    <div>
      <p class="eyebrow">POLYFLOW</p>
      <h1>Operations Console</h1>
    </div>
    <div class="runtime-pill" id="heartbeat-pill" aria-live="polite">Waiting</div>
  </header>

  <main id="main" class="shell">
    <section class="metric-grid" aria-label="Runtime metrics">
      <article class="metric"><span>Records</span><strong id="metric-records">0</strong></article>
      <article class="metric"><span>Orders</span><strong id="metric-orders">0</strong></article>
      <article class="metric"><span>Rejected</span><strong id="metric-rejected">0</strong></article>
      <article class="metric"><span>Risk</span><strong id="metric-risk">$0</strong></article>
      <article class="metric"><span>CLV</span><strong id="metric-clv">n/a</strong></article>
      <article class="metric"><span>Score</span><strong id="metric-score">0</strong></article>
    </section>

    <section class="layout">
      <article class="panel panel-large">
        <div class="panel-head">
          <h2>Signals</h2>
          <span id="signal-count">0</span>
        </div>
        <div class="table-wrap">
          <table>
            <thead><tr><th>Strategy</th><th>Status</th><th>Score</th><th>Market</th><th>Evidence</th></tr></thead>
            <tbody id="signals-body"></tbody>
          </table>
        </div>
      </article>

      <article class="panel">
        <div class="panel-head">
          <h2>Controls</h2>
          <span>Intent only</span>
        </div>
        <div id="intent-list" class="intent-list"></div>
      </article>

      <article class="panel">
        <div class="panel-head">
          <h2>Positions</h2>
          <span id="position-count">0</span>
        </div>
        <div id="positions-list" class="stack-list"></div>
      </article>

      <article class="panel">
        <div class="panel-head">
          <h2>Orders</h2>
          <span id="order-count">0</span>
        </div>
        <div id="orders-list" class="stack-list"></div>
      </article>

      <article class="panel">
        <div class="panel-head">
          <h2>Markets</h2>
          <span id="market-count">0</span>
        </div>
        <div id="markets-list" class="stack-list"></div>
      </article>

      <article class="panel">
        <div class="panel-head">
          <h2>Learning</h2>
          <span id="learning-count">0</span>
        </div>
        <div id="learning-list" class="stack-list"></div>
      </article>

      <article class="panel panel-large">
        <div class="panel-head">
          <h2>Audit Log</h2>
          <span id="log-count">0</span>
        </div>
        <div id="log-list" class="audit-list"></div>
      </article>
    </section>
  </main>

  <div id="toast" class="toast" role="status" aria-live="polite"></div>
  <script src="/dashboard.js"></script>
</body>
</html>
"""


DASHBOARD_CSS = r"""
:root {
  color-scheme: dark;
  --bg: #101312;
  --panel: #181d1b;
  --panel-2: #202620;
  --text: #f4f7f2;
  --muted: #a8b2a9;
  --line: #334039;
  --amber: #f2b84b;
  --cyan: #66d9d0;
  --green: #7fd18c;
  --red: #ff6b6b;
  --violet: #bda4ff;
  --shadow: 0 18px 50px rgba(0,0,0,.35);
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font: 16px/1.5 ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  letter-spacing: 0;
}
button, a { color: inherit; }
button { cursor: pointer; }
.skip-link {
  position: absolute;
  left: 12px;
  top: -48px;
  padding: 10px 12px;
  background: var(--amber);
  color: #171200;
  z-index: 50;
}
.skip-link:focus { top: 12px; }
.topbar {
  position: sticky;
  top: 0;
  z-index: 20;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  padding: 18px clamp(16px, 3vw, 34px);
  background: rgba(16,19,18,.92);
  border-bottom: 1px solid var(--line);
  backdrop-filter: blur(12px);
}
.eyebrow {
  margin: 0 0 2px;
  color: var(--amber);
  font-size: .72rem;
  font-weight: 800;
  text-transform: uppercase;
}
h1, h2 { margin: 0; line-height: 1.12; }
h1 { font-size: clamp(1.45rem, 2.5vw, 2.1rem); }
h2 { font-size: 1rem; }
.runtime-pill {
  min-width: 132px;
  min-height: 44px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--line);
  background: var(--panel);
  color: var(--muted);
  border-radius: 7px;
  font-weight: 800;
}
.runtime-pill.ok { border-color: rgba(127,209,140,.55); color: var(--green); }
.runtime-pill.warn { border-color: rgba(255,107,107,.55); color: var(--red); }
.shell { padding: 20px clamp(16px, 3vw, 34px) 36px; }
.metric-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(130px, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}
.metric, .panel {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  box-shadow: var(--shadow);
}
.metric {
  min-height: 92px;
  padding: 14px;
  display: grid;
  align-content: space-between;
}
.metric span { color: var(--muted); font-size: .78rem; font-weight: 700; text-transform: uppercase; }
.metric strong { font-size: clamp(1.35rem, 2vw, 2rem); }
.layout {
  display: grid;
  grid-template-columns: 1.4fr .9fr .9fr;
  gap: 16px;
  align-items: start;
}
.panel {
  min-height: 220px;
  overflow: hidden;
}
.panel-large { grid-column: span 2; }
.panel-head {
  min-height: 54px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 16px;
  border-bottom: 1px solid var(--line);
}
.panel-head span { color: var(--muted); font-size: .82rem; font-weight: 700; }
.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; min-width: 760px; }
th, td {
  padding: 12px 14px;
  border-bottom: 1px solid var(--line);
  text-align: left;
  vertical-align: top;
  font-size: .9rem;
}
th { color: var(--muted); font-size: .74rem; text-transform: uppercase; }
.tag {
  display: inline-flex;
  align-items: center;
  min-height: 26px;
  padding: 3px 8px;
  border-radius: 6px;
  border: 1px solid var(--line);
  color: var(--cyan);
  background: var(--panel-2);
  font-weight: 800;
  font-size: .76rem;
}
.stack-list, .audit-list, .intent-list {
  display: grid;
  gap: 10px;
  padding: 14px;
}
.row-item, .intent {
  display: grid;
  gap: 5px;
  padding: 10px;
  background: var(--panel-2);
  border: 1px solid var(--line);
  border-radius: 7px;
}
.row-item strong, .intent strong { font-size: .9rem; overflow-wrap: anywhere; }
.row-item span, .intent span { color: var(--muted); font-size: .8rem; overflow-wrap: anywhere; }
.intent button {
  min-height: 44px;
  margin-top: 6px;
  border: 1px solid rgba(242,184,75,.5);
  border-radius: 7px;
  background: transparent;
  color: var(--amber);
  font-weight: 800;
}
.audit-list { max-height: 460px; overflow: auto; }
.toast {
  position: fixed;
  right: 18px;
  bottom: 18px;
  max-width: min(420px, calc(100vw - 36px));
  padding: 12px 14px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--panel-2);
  color: var(--text);
  box-shadow: var(--shadow);
  opacity: 0;
  transform: translateY(8px);
  transition: opacity 180ms ease, transform 180ms ease;
}
.toast.show { opacity: 1; transform: translateY(0); }
:focus-visible { outline: 3px solid var(--cyan); outline-offset: 3px; }
@media (max-width: 1120px) {
  .metric-grid { grid-template-columns: repeat(3, 1fr); }
  .layout { grid-template-columns: 1fr 1fr; }
  .panel-large { grid-column: span 2; }
}
@media (max-width: 720px) {
  .topbar { align-items: flex-start; flex-direction: column; }
  .metric-grid, .layout { grid-template-columns: 1fr; }
  .panel-large { grid-column: span 1; }
  .runtime-pill { width: 100%; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { transition: none !important; scroll-behavior: auto !important; }
}
"""


DASHBOARD_JS = r"""
const $ = (id) => document.getElementById(id);
const money = (n) => `$${Number(n || 0).toLocaleString(undefined, {maximumFractionDigits: 2})}`;
const num = (n) => Number(n || 0).toLocaleString(undefined, {maximumFractionDigits: 2});
const text = (value) => value === null || value === undefined || value === "" ? "n/a" : String(value);
let toastTimer;

function esc(value) {
  return text(value).replace(/[&<>"']/g, (m) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m]));
}

function showToast(message) {
  const toast = $("toast");
  toast.textContent = message;
  toast.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("show"), 2200);
}

function smallItem(title, detail, meta = "") {
  return `<div class="row-item"><strong>${esc(title)}</strong><span>${esc(detail)}</span>${meta ? `<span>${esc(meta)}</span>` : ""}</div>`;
}

function render(data) {
  const s = data.summary || {};
  $("metric-records").textContent = num(s.total_records);
  $("metric-orders").textContent = num(s.placed_orders);
  $("metric-rejected").textContent = num(s.rejected_orders);
  $("metric-risk").textContent = money(s.bankroll_at_risk);
  $("metric-clv").textContent = s.average_clv_bps === null || s.average_clv_bps === undefined ? "n/a" : `${num(s.average_clv_bps)} bps`;
  $("metric-score").textContent = num(s.average_signal_score);

  const pill = $("heartbeat-pill");
  const hb = data.heartbeat || {};
  pill.textContent = hb.fresh ? "Heartbeat live" : "Heartbeat stale";
  pill.className = `runtime-pill ${hb.fresh ? "ok" : "warn"}`;

  const signals = data.signals || [];
  $("signal-count").textContent = signals.length;
  $("signals-body").innerHTML = signals.map((sig) => {
    let refs = [];
    try { refs = JSON.parse(sig.evidence_refs || "[]"); } catch (_) { refs = []; }
    return `<tr>
      <td><span class="tag">${esc(sig.strategy)}</span></td>
      <td>${esc(sig.status)}</td>
      <td>${num(sig.score)}</td>
      <td>${esc(sig.market_id)}</td>
      <td>${esc(refs.slice(0, 2).join(" | "))}</td>
    </tr>`;
  }).join("") || `<tr><td colspan="5">No recent signals</td></tr>`;

  const positions = data.positions || [];
  $("position-count").textContent = positions.length;
  $("positions-list").innerHTML = positions.map((p) =>
    smallItem(`${p.outcome} ${p.market_id}`, `Size ${num(p.size)} at ${num(p.avg_price)}`, `Value ${money(p.market_value)} | Max loss ${money(p.max_loss)}`)
  ).join("") || smallItem("No open positions", "Runtime has no stored open exposure");

  const orders = data.orders || [];
  $("order-count").textContent = orders.length;
  $("orders-list").innerHTML = orders.map((o) =>
    smallItem(`${o.side} ${o.market_id}`, `Price ${num(o.price)} | Size ${num(o.size)}`, `Order ${o.exchange_order_id}`)
  ).join("") || smallItem("No open orders", "Order sync has no stored open orders");

  const markets = (data.markets && data.markets.watching) || [];
  $("market-count").textContent = markets.length;
  $("markets-list").innerHTML = markets.slice(0, 8).map((m) =>
    smallItem(m.question, `Quality ${num(m.market_quality)} | Risk ${num(m.resolution_risk)}`, `Liquidity ${money(m.liquidity_usd)}`)
  ).join("") || smallItem("No watched markets", "Scanner has not persisted watched markets");

  const learning = data.source_reliability || [];
  $("learning-count").textContent = `${learning.length} sources`;
  $("learning-list").innerHTML = learning.map((r) =>
    smallItem(r.source_name, `Hits ${num(r.hits)} | Misses ${num(r.misses)}`, `Prior ${num(r.prior)} | Brier ${num(r.brier_sum)}`)
  ).join("") || smallItem("No source reliability yet", `${num(s.calibration_buckets)} calibration buckets stored`);

  const intents = data.operator_intents || [];
  $("intent-list").innerHTML = intents.map((intent) =>
    `<div class="intent"><strong>${esc(intent.label)}</strong><span>${esc(intent.command)}</span><button type="button" data-command="${esc(intent.command)}">Copy Command</button></div>`
  ).join("");
  document.querySelectorAll("[data-command]").forEach((button) => {
    button.onclick = async () => {
      await navigator.clipboard.writeText(button.dataset.command);
      showToast("Command copied");
    };
  });

  const logs = data.log_tail || [];
  $("log-count").textContent = logs.length;
  $("log-list").innerHTML = logs.slice().reverse().map((r) =>
    smallItem(`${r.actor} / ${r.action}`, r.market_id || r.event_id || "system", r.ts)
  ).join("") || smallItem("No audit records", "Immutable log is empty or missing");
}

async function loadOnce() {
  const res = await fetch("/api/state", {cache: "no-store"});
  render(await res.json());
}

function connectStream() {
  if (!window.EventSource) {
    setInterval(loadOnce, 2000);
    loadOnce();
    return;
  }
  const es = new EventSource("/api/stream");
  es.addEventListener("snapshot", (event) => render(JSON.parse(event.data)));
  es.onerror = () => {
    es.close();
    setTimeout(connectStream, 2000);
  };
}

connectStream();
"""

# Keep the server logic in this module and the polished UI in a separate asset
# module so frontend iteration does not touch the HTTP/snapshot code.
from .dashboard_assets import (  # noqa: E402
    DASHBOARD_CSS as ASSET_DASHBOARD_CSS,
    DASHBOARD_JS as ASSET_DASHBOARD_JS,
    INDEX_HTML as ASSET_INDEX_HTML,
)
