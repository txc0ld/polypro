"""Static assets for the zero-dependency POLYFLOW operations dashboard."""

INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="dark">
  <title>POLYFLOW Ops Console</title>
  <link rel="stylesheet" href="/dashboard.css">
</head>
<body>
  <a class="skip-link" href="#main">Skip to main content</a>

  <header class="topbar" role="banner">
    <div class="brand-block">
      <p class="eyebrow">POLYFLOW</p>
      <h1>Real-Time Operations Console</h1>
    </div>
    <div class="status-strip" aria-label="Runtime status">
      <div class="status-card">
        <span>Stream</span>
        <strong id="stream-status" aria-live="polite">Connecting</strong>
      </div>
      <div class="status-card">
        <span>Heartbeat</span>
        <strong id="heartbeat-status" aria-live="polite">Unknown</strong>
      </div>
      <div class="status-card">
        <span>Snapshot</span>
        <strong id="snapshot-time">Pending</strong>
      </div>
    </div>
  </header>

  <main id="main" class="workspace" tabindex="-1">
    <section class="metric-grid" aria-label="Runtime metrics">
      <article class="metric accent-cyan">
        <span>Watching</span>
        <strong id="metric-watching">0</strong>
        <small>approved market candidates</small>
      </article>
      <article class="metric accent-green">
        <span>Open Positions</span>
        <strong id="metric-positions">0</strong>
        <small id="metric-market-value">$0.00 market value</small>
      </article>
      <article class="metric accent-amber">
        <span>Bankroll At Risk</span>
        <strong id="metric-risk">$0.00</strong>
        <small>max loss exposure</small>
      </article>
      <article class="metric accent-violet">
        <span>Open Orders</span>
        <strong id="metric-open-orders">0</strong>
        <small id="metric-orders-placed">0 placed orders</small>
      </article>
      <article class="metric accent-green">
        <span>Automation Sources</span>
        <strong id="metric-automation">0/0</strong>
        <small>pinned repo readiness</small>
      </article>
      <article class="metric accent-cyan">
        <span>Avg Signal Score</span>
        <strong id="metric-score">0.00</strong>
        <small id="metric-signal-count">0 recent signals</small>
      </article>
      <article class="metric accent-amber">
        <span>Kill Switch</span>
        <strong id="metric-kill">0</strong>
        <small id="metric-rejected">0 rejected orders</small>
      </article>
    </section>

    <section class="command-band" aria-labelledby="operator-intents-title">
      <div>
        <p class="eyebrow">Read-mostly controls</p>
        <h2 id="operator-intents-title">Operator Intents</h2>
      </div>
      <div id="intent-list" class="intent-list" aria-live="polite"></div>
    </section>

    <section class="grid-layout" aria-label="Operations workspace">
      <article class="panel panel-wide">
        <div class="panel-head">
          <div>
            <p class="eyebrow">Probability engine</p>
            <h2>Signals</h2>
          </div>
          <span id="signals-count">0 rows</span>
        </div>
        <div class="table-wrap" tabindex="0" aria-label="Recent signals table">
          <table>
            <thead>
              <tr>
                <th scope="col">Strategy</th>
                <th scope="col">Status</th>
                <th scope="col">Score</th>
                <th scope="col">Market</th>
                <th scope="col">Evidence</th>
                <th scope="col">Updated</th>
              </tr>
            </thead>
            <tbody id="signals-body"></tbody>
          </table>
        </div>
      </article>

      <article class="panel">
        <div class="panel-head">
          <div>
            <p class="eyebrow">Exposure</p>
            <h2>Positions</h2>
          </div>
          <span id="positions-count">0 rows</span>
        </div>
        <div id="positions-list" class="stack-list" aria-live="polite"></div>
      </article>

      <article class="panel">
        <div class="panel-head">
          <div>
            <p class="eyebrow">CLOB sync</p>
            <h2>Orders</h2>
          </div>
          <span id="orders-count">0 rows</span>
        </div>
        <div id="orders-list" class="stack-list" aria-live="polite"></div>
      </article>

      <article class="panel panel-wide">
        <div class="panel-head">
          <div>
            <p class="eyebrow">Scanner</p>
            <h2>Markets Watching</h2>
          </div>
          <span id="markets-count">0 rows</span>
        </div>
        <div id="markets-list" class="market-grid" aria-live="polite"></div>
      </article>

      <article class="panel">
        <div class="panel-head">
          <div>
            <p class="eyebrow">Source memory</p>
            <h2>Reliability</h2>
          </div>
          <span id="reliability-count">0 rows</span>
        </div>
        <div id="reliability-list" class="stack-list" aria-live="polite"></div>
      </article>

      <article class="panel">
        <div class="panel-head">
          <div>
            <p class="eyebrow">Automation</p>
            <h2>Reference Repos</h2>
          </div>
          <span id="automation-count">0 rows</span>
        </div>
        <div id="automation-list" class="stack-list" aria-live="polite"></div>
      </article>

      <article class="panel">
        <div class="panel-head">
          <div>
            <p class="eyebrow">Immutable trail</p>
            <h2>Audit Tail</h2>
          </div>
          <span id="log-count">0 rows</span>
        </div>
        <div id="log-list" class="audit-list" aria-live="polite"></div>
      </article>
    </section>
  </main>

  <div id="toast" class="toast" role="status" aria-live="polite" aria-atomic="true"></div>
  <script src="/dashboard.js"></script>
</body>
</html>
"""


DASHBOARD_CSS = r"""
:root {
  color-scheme: dark;
  --bg: #0b0d0e;
  --surface: #111416;
  --surface-2: #171b1e;
  --surface-3: #1d2327;
  --line: #2b343a;
  --line-strong: #3b4850;
  --text: #edf2f3;
  --muted: #9ba8ad;
  --dim: #748086;
  --amber: #f0b44c;
  --cyan: #64d8df;
  --green: #78d68b;
  --violet: #b59cff;
  --red: #ff6f6f;
  --shadow: 0 18px 48px rgba(0, 0, 0, .34);
}

* { box-sizing: border-box; }

html { min-width: 320px; }

body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font: 14px/1.45 ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  letter-spacing: 0;
}

button, input, select, textarea { font: inherit; }
button { color: inherit; }

.skip-link {
  position: absolute;
  left: 12px;
  top: -56px;
  z-index: 100;
  padding: 10px 12px;
  border-radius: 6px;
  background: var(--amber);
  color: #161100;
  font-weight: 800;
}

.skip-link:focus { top: 12px; }

.topbar {
  position: sticky;
  top: 0;
  z-index: 20;
  display: flex;
  align-items: stretch;
  justify-content: space-between;
  gap: 18px;
  padding: 14px clamp(14px, 2.3vw, 30px);
  border-bottom: 1px solid var(--line);
  background: rgba(11, 13, 14, .94);
  backdrop-filter: blur(14px);
}

.brand-block {
  display: grid;
  align-content: center;
  min-width: 210px;
}

.eyebrow {
  margin: 0 0 4px;
  color: var(--muted);
  font-size: .68rem;
  font-weight: 900;
  text-transform: uppercase;
}

h1, h2, p { margin: 0; }
h1 { font-size: clamp(1.25rem, 2vw, 1.75rem); line-height: 1.1; }
h2 { font-size: .98rem; line-height: 1.18; }

.status-strip {
  display: grid;
  grid-template-columns: repeat(3, minmax(132px, 1fr));
  gap: 10px;
  width: min(620px, 100%);
}

.status-card {
  display: grid;
  align-content: center;
  min-height: 54px;
  padding: 9px 11px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--surface);
}

.status-card span,
.metric span,
.metric small,
.panel-head span,
.row-meta,
.empty-state {
  color: var(--muted);
}

.status-card span,
.metric span {
  font-size: .68rem;
  font-weight: 900;
  text-transform: uppercase;
}

.status-card strong {
  margin-top: 2px;
  font-size: .92rem;
  overflow-wrap: anywhere;
}

.status-ok { color: var(--green); }
.status-warn { color: var(--amber); }
.status-bad { color: var(--red); }
.status-info { color: var(--cyan); }

.workspace {
  padding: 16px clamp(14px, 2.3vw, 30px) 32px;
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(128px, 1fr));
  gap: 10px;
  margin-bottom: 12px;
}

.metric,
.panel,
.command-band {
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--surface);
  box-shadow: var(--shadow);
}

.metric {
  position: relative;
  min-height: 96px;
  display: grid;
  align-content: space-between;
  gap: 8px;
  padding: 12px;
  overflow: hidden;
}

.metric::before {
  content: "";
  position: absolute;
  inset: 0 auto 0 0;
  width: 3px;
  background: var(--line-strong);
}

.metric strong {
  font-size: clamp(1.35rem, 2vw, 1.95rem);
  line-height: 1;
  overflow-wrap: anywhere;
}

.metric small {
  min-height: 18px;
  font-size: .78rem;
  overflow-wrap: anywhere;
}

.accent-cyan::before { background: var(--cyan); }
.accent-green::before { background: var(--green); }
.accent-amber::before { background: var(--amber); }
.accent-violet::before { background: var(--violet); }

.command-band {
  display: grid;
  grid-template-columns: minmax(180px, 240px) 1fr;
  gap: 14px;
  align-items: center;
  margin-bottom: 12px;
  padding: 12px;
  background: var(--surface-2);
}

.intent-list {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.intent {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 8px 10px;
  align-items: center;
  min-height: 78px;
  padding: 10px;
  border: 1px solid var(--line);
  border-radius: 7px;
  background: var(--surface);
}

.intent strong,
.row-item strong,
.market-card strong {
  font-size: .88rem;
  overflow-wrap: anywhere;
}

.intent code {
  grid-column: 1 / -1;
  color: var(--muted);
  font-family: ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", monospace;
  font-size: .76rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.intent button {
  min-width: 108px;
  min-height: 36px;
  padding: 7px 10px;
  border: 1px solid rgba(240, 180, 76, .58);
  border-radius: 7px;
  background: transparent;
  color: var(--amber);
  cursor: pointer;
  font-weight: 900;
}

.intent button:hover { background: rgba(240, 180, 76, .1); }

.grid-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.25fr) minmax(300px, .88fr) minmax(300px, .88fr);
  gap: 12px;
  align-items: start;
}

.panel {
  min-height: 254px;
  overflow: hidden;
}

.panel-wide { grid-column: span 2; }

.panel-head {
  min-height: 58px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  border-bottom: 1px solid var(--line);
  background: var(--surface-2);
}

.panel-head span {
  font-size: .78rem;
  font-weight: 800;
  white-space: nowrap;
}

.table-wrap {
  overflow: auto;
  max-height: 460px;
}

table {
  width: 100%;
  min-width: 820px;
  border-collapse: collapse;
}

th,
td {
  padding: 10px 12px;
  border-bottom: 1px solid var(--line);
  text-align: left;
  vertical-align: top;
}

th {
  position: sticky;
  top: 0;
  z-index: 1;
  background: var(--surface);
  color: var(--muted);
  font-size: .68rem;
  font-weight: 900;
  text-transform: uppercase;
}

td {
  color: var(--text);
  font-size: .84rem;
}

.mono {
  font-family: ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", monospace;
  font-size: .78rem;
}

.tag {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  max-width: 220px;
  padding: 3px 7px;
  border: 1px solid var(--line-strong);
  border-radius: 6px;
  background: var(--surface-3);
  color: var(--cyan);
  font-size: .73rem;
  font-weight: 900;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tag.green { color: var(--green); }
.tag.amber { color: var(--amber); }
.tag.red { color: var(--red); }
.tag.violet { color: var(--violet); }

.stack-list,
.audit-list,
.market-grid {
  display: grid;
  gap: 8px;
  padding: 10px;
}

.audit-list {
  max-height: 430px;
  overflow: auto;
}

.market-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.row-item,
.market-card,
.empty-state {
  display: grid;
  gap: 6px;
  min-height: 76px;
  padding: 10px;
  border: 1px solid var(--line);
  border-radius: 7px;
  background: var(--surface-2);
}

.row-line {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  color: var(--muted);
  font-size: .78rem;
}

.row-line span,
.row-meta,
.market-card span {
  overflow-wrap: anywhere;
}

.risk-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  margin-top: 2px;
}

.risk-row span {
  min-height: 34px;
  display: grid;
  align-content: center;
  padding: 6px 7px;
  border-radius: 6px;
  background: var(--surface);
  color: var(--muted);
  font-size: .72rem;
}

.empty-state {
  place-items: center start;
  min-height: 100px;
  font-size: .88rem;
}

.toast {
  position: fixed;
  right: 18px;
  bottom: 18px;
  z-index: 40;
  max-width: min(440px, calc(100vw - 36px));
  padding: 12px 14px;
  border: 1px solid var(--line-strong);
  border-radius: 8px;
  background: var(--surface-3);
  color: var(--text);
  box-shadow: var(--shadow);
  opacity: 0;
  transform: translateY(8px);
  transition: opacity 160ms ease, transform 160ms ease;
}

.toast.show {
  opacity: 1;
  transform: translateY(0);
}

:focus-visible {
  outline: 3px solid var(--cyan);
  outline-offset: 3px;
}

@media (max-width: 1260px) {
  .metric-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .grid-layout { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .panel-wide { grid-column: span 2; }
  .intent-list { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

@media (max-width: 820px) {
  .topbar,
  .command-band {
    grid-template-columns: 1fr;
  }

  .topbar {
    display: grid;
    position: static;
  }

  .status-strip,
  .metric-grid,
  .grid-layout,
  .intent-list,
  .market-grid {
    grid-template-columns: 1fr;
  }

  .panel-wide { grid-column: span 1; }
  .intent { grid-template-columns: 1fr; }
  .intent button { width: 100%; }
}

@media (max-width: 520px) {
  body { font-size: 13px; }
  .workspace { padding-inline: 10px; }
  .topbar { padding-inline: 10px; }
  .metric { min-height: 84px; }
  .risk-row { grid-template-columns: 1fr; }
}

@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    transition: none !important;
    scroll-behavior: auto !important;
  }
}
"""


DASHBOARD_JS = r"""
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const nf = new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 });
  const moneyFmt = new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2
  });

  let toastTimer = null;
  let fallbackTimer = null;
  let lastSnapshotAt = 0;

  function value(v, fallback = "n/a") {
    return v === null || v === undefined || v === "" ? fallback : String(v);
  }

  function number(v, digits = 2) {
    const n = Number(v);
    if (!Number.isFinite(n)) return "0";
    return n.toLocaleString(undefined, { maximumFractionDigits: digits });
  }

  function money(v) {
    const n = Number(v);
    return moneyFmt.format(Number.isFinite(n) ? n : 0);
  }

  function compactTime(v) {
    if (!v) return "n/a";
    const d = new Date(v);
    if (Number.isNaN(d.getTime())) return value(v);
    return d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  }

  function fullTime(v) {
    if (!v) return "n/a";
    const d = new Date(v);
    if (Number.isNaN(d.getTime())) return value(v);
    return d.toLocaleString();
  }

  function clearNode(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  function textNode(tag, className, text) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    el.textContent = value(text);
    return el;
  }

  function setText(id, text) {
    const node = $(id);
    if (node) node.textContent = value(text);
  }

  function setStatus(id, label, state) {
    const node = $(id);
    if (!node) return;
    node.textContent = label;
    node.className = state ? `status-${state}` : "";
  }

  function showToast(message) {
    const toast = $("toast");
    if (!toast) return;
    toast.textContent = message;
    toast.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove("show"), 2400);
  }

  function empty(message) {
    const el = document.createElement("div");
    el.className = "empty-state";
    el.textContent = message;
    return el;
  }

  function tag(text, tone) {
    const el = document.createElement("span");
    el.className = tone ? `tag ${tone}` : "tag";
    el.textContent = value(text);
    return el;
  }

  function appendLine(parent, left, right) {
    const row = document.createElement("div");
    row.className = "row-line";
    row.append(textNode("span", "", left), textNode("span", "mono", right));
    parent.appendChild(row);
  }

  function field(obj, names, fallback = "") {
    for (const name of names) {
      if (obj && obj[name] !== undefined && obj[name] !== null && obj[name] !== "") return obj[name];
    }
    return fallback;
  }

  function evidenceList(signal) {
    const raw = field(signal, ["evidence_refs", "evidence", "sources"], []);
    if (Array.isArray(raw)) return raw.slice(0, 3).map(value).join(" | ");
    if (typeof raw !== "string") return value(raw, "");
    try {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) return parsed.slice(0, 3).map(value).join(" | ");
    } catch (_) {
      return raw;
    }
    return raw;
  }

  function renderMetrics(data) {
    const s = data.summary || {};
    const markets = data.markets || {};
    const watching = Array.isArray(markets.watching) ? markets.watching : [];
    const positions = Array.isArray(data.positions) ? data.positions : [];
    const orders = Array.isArray(data.orders) ? data.orders : [];
    const signals = Array.isArray(data.signals) ? data.signals : [];

    setText("metric-watching", field(s, ["watching_markets"], watching.length));
    setText("metric-positions", field(s, ["open_positions"], positions.length));
    setText("metric-market-value", `${money(s.market_value)} market value`);
    setText("metric-risk", money(s.bankroll_at_risk));
    setText("metric-open-orders", field(s, ["open_orders"], orders.length));
    setText("metric-orders-placed", `${number(s.placed_orders, 0)} placed orders`);
    setText("metric-automation", `${number(s.automation_sources_ready, 0)}/${number(s.automation_sources_total, 0)}`);
    setText("metric-score", number(s.average_signal_score));
    setText("metric-signal-count", `${signals.length} recent signals`);
    setText("metric-kill", number(s.kill_switch_events, 0));
    setText("metric-rejected", `${number(s.rejected_orders, 0)} rejected orders`);
  }

  function renderHeader(data, transport) {
    const hb = data.heartbeat || {};
    const age = Number(hb.age_seconds);
    const fresh = Boolean(hb.fresh);
    const heartbeatLabel = fresh ? `Live ${number(age, 0)}s` : (hb.last_seen ? `Stale ${number(age, 0)}s` : "Missing");
    setStatus("heartbeat-status", heartbeatLabel, fresh ? "ok" : "bad");
    setStatus("stream-status", transport, transport === "SSE live" ? "ok" : "warn");
    setText("snapshot-time", compactTime(data.generated_at || Date.now()));
  }

  function renderSignals(signals) {
    const body = $("signals-body");
    if (!body) return;
    clearNode(body);
    setText("signals-count", `${signals.length} rows`);
    if (!signals.length) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = 6;
      td.textContent = "No recent signals persisted.";
      tr.appendChild(td);
      body.appendChild(tr);
      return;
    }

    for (const signal of signals) {
      const score = Number(field(signal, ["score"], 0));
      const status = value(field(signal, ["status"], "unknown")).toLowerCase();
      const tr = document.createElement("tr");

      const strategy = document.createElement("td");
      strategy.appendChild(tag(field(signal, ["strategy", "strategy_name"], "unknown"), status.includes("approved") ? "green" : "cyan"));

      const statusCell = document.createElement("td");
      statusCell.appendChild(tag(status, status.includes("reject") ? "red" : status.includes("watch") ? "amber" : "violet"));

      const scoreCell = textNode("td", "mono", number(score));
      const marketCell = textNode("td", "mono", field(signal, ["market_id", "condition_id", "event_id"], "n/a"));
      const evidenceCell = textNode("td", "", evidenceList(signal) || "n/a");
      const updatedCell = textNode("td", "mono", compactTime(field(signal, ["created_at", "updated_at", "ts"], "")));

      tr.append(strategy, statusCell, scoreCell, marketCell, evidenceCell, updatedCell);
      body.appendChild(tr);
    }
  }

  function renderPositions(positions) {
    const list = $("positions-list");
    if (!list) return;
    clearNode(list);
    setText("positions-count", `${positions.length} rows`);
    if (!positions.length) {
      list.appendChild(empty("No open exposure stored."));
      return;
    }

    for (const p of positions) {
      const item = document.createElement("div");
      item.className = "row-item";
      item.appendChild(textNode("strong", "", `${value(field(p, ["outcome", "side"], "position"))} / ${value(field(p, ["market_id"], "unknown market"))}`));
      item.appendChild(textNode("div", "row-meta mono", value(field(p, ["token_id", "asset_id"], "token n/a"))));
      const risk = document.createElement("div");
      risk.className = "risk-row";
      risk.append(
        textNode("span", "", `Size ${number(field(p, ["size", "quantity"], 0))}`),
        textNode("span", "", `Avg ${number(field(p, ["avg_price", "price"], 0))}`),
        textNode("span", "", `Max loss ${money(field(p, ["max_loss"], 0))}`)
      );
      item.appendChild(risk);
      list.appendChild(item);
    }
  }

  function renderOrders(orders) {
    const list = $("orders-list");
    if (!list) return;
    clearNode(list);
    setText("orders-count", `${orders.length} rows`);
    if (!orders.length) {
      list.appendChild(empty("No open CLOB orders stored."));
      return;
    }

    for (const o of orders) {
      const item = document.createElement("div");
      item.className = "row-item";
      const side = value(field(o, ["side"], "order")).toUpperCase();
      item.appendChild(textNode("strong", "", `${side} / ${value(field(o, ["market_id"], "unknown market"))}`));
      item.appendChild(textNode("div", "row-meta mono", value(field(o, ["exchange_order_id", "order_id", "id"], "order id n/a"))));
      appendLine(item, "Price", number(field(o, ["price"], 0), 4));
      appendLine(item, "Size", number(field(o, ["size", "quantity"], 0)));
      appendLine(item, "Status", field(o, ["status"], "open"));
      list.appendChild(item);
    }
  }

  function renderMarkets(markets) {
    const list = $("markets-list");
    if (!list) return;
    clearNode(list);
    setText("markets-count", `${markets.length} rows`);
    if (!markets.length) {
      list.appendChild(empty("No scanner-approved watching markets."));
      return;
    }

    for (const m of markets.slice(0, 12)) {
      const card = document.createElement("div");
      card.className = "market-card";
      card.appendChild(textNode("strong", "", field(m, ["question", "title", "market_id"], "unknown market")));
      card.appendChild(textNode("span", "row-meta mono", field(m, ["market_id", "condition_id"], "id n/a")));
      const risk = document.createElement("div");
      risk.className = "risk-row";
      risk.append(
        textNode("span", "", `Quality ${number(field(m, ["market_quality", "quality_score"], 0))}`),
        textNode("span", "", `Resolve ${number(field(m, ["resolution_risk"], 0))}`),
        textNode("span", "", `Liquidity ${money(field(m, ["liquidity_usd", "liquidity"], 0))}`)
      );
      card.appendChild(risk);
      list.appendChild(card);
    }
  }

  function renderReliability(rows) {
    const list = $("reliability-list");
    if (!list) return;
    clearNode(list);
    setText("reliability-count", `${rows.length} rows`);
    if (!rows.length) {
      list.appendChild(empty("No source reliability records yet."));
      return;
    }

    for (const r of rows) {
      const item = document.createElement("div");
      item.className = "row-item";
      item.appendChild(textNode("strong", "", field(r, ["source_name", "source"], "source")));
      appendLine(item, "Hits", number(field(r, ["hits"], 0), 0));
      appendLine(item, "Misses", number(field(r, ["misses"], 0), 0));
      appendLine(item, "Brier", number(field(r, ["brier_sum", "brier"], 0), 4));
      list.appendChild(item);
    }
  }

  function renderAutomation(rows) {
    const list = $("automation-list");
    if (!list) return;
    clearNode(list);
    setText("automation-count", `${rows.length} rows`);
    if (!rows.length) {
      list.appendChild(empty("Reference repo monitor has not checked sources yet."));
      return;
    }

    for (const source of rows) {
      const item = document.createElement("div");
      item.className = "row-item";
      const ok = Boolean(field(source, ["ok"], false));
      item.appendChild(textNode("strong", "", field(source, ["name"], "source")));
      item.appendChild(tag(field(source, ["status"], "unknown"), ok ? "green" : "amber"));
      appendLine(item, "Mode", field(source, ["integration_mode"], "n/a"));
      appendLine(item, "Pinned", value(field(source, ["pinned_commit"], "")).slice(0, 12) || "n/a");
      appendLine(item, "Detected", value(field(source, ["detected_commit"], "")).slice(0, 12) || "n/a");
      const reasons = field(source, ["reason_codes"], []);
      const warnings = field(source, ["warning_codes"], []);
      const notes = Array.isArray(reasons) && reasons.length ? reasons : warnings;
      item.appendChild(textNode(
        "div",
        "row-meta mono",
        Array.isArray(notes) && notes.length ? notes.slice(0, 3).join(" | ") : "ready"
      ));
      list.appendChild(item);
    }
  }

  function renderLog(rows) {
    const list = $("log-list");
    if (!list) return;
    clearNode(list);
    setText("log-count", `${rows.length} rows`);
    if (!rows.length) {
      list.appendChild(empty("Immutable log tail is empty."));
      return;
    }

    for (const r of rows.slice().reverse()) {
      const item = document.createElement("div");
      item.className = "row-item";
      item.appendChild(textNode("strong", "", `${field(r, ["actor"], "system")} / ${field(r, ["action"], "event")}`));
      item.appendChild(textNode("div", "row-meta mono", fullTime(field(r, ["ts", "created_at"], ""))));
      appendLine(item, "Market", field(r, ["market_id", "event_id"], "n/a"));
      list.appendChild(item);
    }
  }

  async function copyCommand(command, label) {
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(command);
      } else {
        const input = document.createElement("textarea");
        input.value = command;
        input.setAttribute("readonly", "");
        input.style.position = "fixed";
        input.style.left = "-9999px";
        document.body.appendChild(input);
        input.select();
        document.execCommand("copy");
        input.remove();
      }
      showToast(`${label} command copied. No live action was executed.`);
    } catch (_) {
      showToast("Copy failed. Select the command text manually.");
    }
  }

  function renderIntents(intents) {
    const list = $("intent-list");
    if (!list) return;
    clearNode(list);
    if (!intents.length) {
      list.appendChild(empty("No operator intents exposed by the runtime."));
      return;
    }

    for (const intent of intents) {
      const command = value(field(intent, ["command"], ""));
      const label = value(field(intent, ["label", "id"], "Intent"));
      const item = document.createElement("div");
      item.className = "intent";
      item.appendChild(textNode("strong", "", label));
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = "Copy only";
      button.setAttribute("aria-label", `Copy ${label} command to clipboard`);
      button.addEventListener("click", () => copyCommand(command, label));
      item.appendChild(button);
      const code = document.createElement("code");
      code.textContent = command || "No command supplied";
      item.appendChild(code);
      list.appendChild(item);
    }
  }

  function render(data, transport) {
    const snapshot = data || {};
    lastSnapshotAt = Date.now();
    renderHeader(snapshot, transport);
    renderMetrics(snapshot);
    renderSignals(Array.isArray(snapshot.signals) ? snapshot.signals : []);
    renderPositions(Array.isArray(snapshot.positions) ? snapshot.positions : []);
    renderOrders(Array.isArray(snapshot.orders) ? snapshot.orders : []);
    renderMarkets(snapshot.markets && Array.isArray(snapshot.markets.watching) ? snapshot.markets.watching : []);
    renderReliability(Array.isArray(snapshot.source_reliability) ? snapshot.source_reliability : []);
    renderAutomation(Array.isArray(snapshot.automation_sources) ? snapshot.automation_sources : []);
    renderLog(Array.isArray(snapshot.log_tail) ? snapshot.log_tail : []);
    renderIntents(Array.isArray(snapshot.operator_intents) ? snapshot.operator_intents : []);
  }

  async function fetchSnapshot(transport) {
    const res = await fetch("/api/state", {
      cache: "no-store",
      headers: { "Accept": "application/json" }
    });
    if (!res.ok) throw new Error(`state ${res.status}`);
    render(await res.json(), transport);
  }

  function startFetchFallback() {
    clearInterval(fallbackTimer);
    fetchSnapshot("Fetch poll").catch(() => setStatus("stream-status", "Offline", "bad"));
    fallbackTimer = setInterval(() => {
      fetchSnapshot("Fetch poll").catch(() => setStatus("stream-status", "Offline", "bad"));
    }, 2500);
  }

  function connectStream() {
    if (!("EventSource" in window)) {
      startFetchFallback();
      return;
    }

    const es = new EventSource("/api/stream");
    es.addEventListener("open", () => setStatus("stream-status", "SSE live", "ok"));
    es.addEventListener("snapshot", (event) => {
      try {
        render(JSON.parse(event.data), "SSE live");
      } catch (_) {
        setStatus("stream-status", "Bad snapshot", "bad");
      }
    });
    es.onerror = () => {
      es.close();
      setStatus("stream-status", "Reconnecting", "warn");
      if (Date.now() - lastSnapshotAt > 5000) startFetchFallback();
      setTimeout(connectStream, 3000);
    };
  }

  connectStream();
})();
"""
