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

  <header class="terminal-topbar" role="banner">
    <div class="brand">
      <span class="brand-mark" aria-hidden="true"></span>
      <div>
        <p>POLYFLOW // HERMES</p>
        <h1>Operations Console</h1>
      </div>
    </div>
    <div class="top-status" aria-label="Runtime status">
      <span><b id="stream-status">CONNECTING</b> / stream</span>
      <span><b id="heartbeat-status">UNKNOWN</b> / heartbeat</span>
      <span><b id="automation-status">0/0</b> / sources</span>
      <span><b id="snapshot-time">--:--:--</b> / utc</span>
    </div>
  </header>

  <main id="main" class="terminal-shell" tabindex="-1">
    <section class="left-rail" aria-label="Market scanner and process telemetry">
      <article class="terminal-panel scanner-panel">
        <div class="panel-head">
          <span class="panel-index">01</span>
          <div>
            <p>MARKET SCANNER</p>
            <h2 id="scanner-subtitle">0 markets / 0 signals / cross-market diff</h2>
          </div>
          <div class="panel-kpis">
            <span><b id="metric-watching">0</b> watched</span>
            <span><b id="metric-signals">0</b> signals</span>
            <span><b id="metric-kill">0</b> kills</span>
          </div>
        </div>
        <div class="flow-canvas-wrap">
          <canvas id="market-flow" width="960" height="620" aria-label="Live market signal topology"></canvas>
        </div>
      </article>

      <div class="lower-grid">
        <article class="terminal-panel">
          <div class="panel-head compact">
            <div>
              <p>CORE PROCESSES</p>
              <h2>runtime lanes</h2>
            </div>
            <span id="process-count">0 lanes</span>
          </div>
          <div id="process-list" class="process-list" aria-live="polite"></div>
        </article>

        <article class="terminal-panel">
          <div class="panel-head compact">
            <div>
              <p>SCANNER LOG</p>
              <h2>stdout / ring 256</h2>
            </div>
            <span id="log-count">0 rows</span>
          </div>
          <div id="log-list" class="terminal-log" aria-live="polite"></div>
        </article>
      </div>
    </section>

    <section class="signal-bus" aria-hidden="true">
      <span>SIGNAL BUS</span>
      <i></i><i></i><i></i><i></i><i></i>
    </section>

    <section class="right-rail" aria-label="Execution flow and trading telemetry">
      <article class="terminal-panel execution-panel">
        <div class="panel-head">
          <span class="panel-index">02</span>
          <div>
            <p>EXECUTION BOT</p>
            <h2 id="execution-subtitle">read-only live order flow</h2>
          </div>
          <div class="panel-kpis">
            <span><b id="metric-orders">0</b> open</span>
            <span><b id="metric-risk">$0</b> risk</span>
            <span><b id="metric-clv">0</b> clv bps</span>
          </div>
        </div>

        <div class="execution-metrics" aria-label="Execution metrics">
          <div><span>score</span><b id="metric-score">0.00</b><i data-bar="score"></i></div>
          <div><span>market value</span><b id="metric-market-value">$0</b><i data-spark="value"></i></div>
          <div><span>automation</span><b id="metric-automation">0/0</b><i data-bars="automation"></i></div>
          <div><span>position size</span><b id="metric-positions">0</b><i data-leds="positions"></i></div>
          <div><span>clv signal</span><b id="metric-pnl">0 bps</b><i data-bars="pnl"></i></div>
        </div>

        <div class="execution-chart-wrap">
          <canvas id="execution-flow" width="1160" height="610" aria-label="Live execution throughput area chart"></canvas>
        </div>
      </article>

      <div class="bottom-grid">
        <article class="terminal-panel">
          <div class="panel-head compact">
            <div>
              <p>EXECUTION LOG</p>
              <h2>live order flow</h2>
            </div>
            <span id="exec-count">0 rows</span>
          </div>
          <div id="exec-list" class="terminal-log" aria-live="polite"></div>
        </article>

        <article class="terminal-panel">
          <div class="panel-head compact">
            <div>
              <p>TRADE TAPE</p>
              <h2>last 12 fills</h2>
            </div>
            <span id="tape-count">0 rows</span>
          </div>
          <div id="tape-list" class="trade-tape" aria-live="polite"></div>
        </article>
      </div>
    </section>
  </main>

  <script src="/dashboard.js"></script>
</body>
</html>
"""


DASHBOARD_CSS = r"""
:root {
  color-scheme: dark;
  --bg: #120604;
  --bg-2: #1a0805;
  --panel: rgba(50, 17, 10, .78);
  --panel-strong: rgba(78, 27, 13, .82);
  --line: rgba(232, 102, 42, .24);
  --line-strong: rgba(255, 154, 72, .46);
  --text: #ffd9ab;
  --muted: #9f6d52;
  --dim: #6d3b2c;
  --amber: #ffb84d;
  --orange: #ff6f35;
  --red: #ff4e32;
  --green: #92e071;
  --cyan: #72d7d7;
  --violet: #c29bff;
  --shadow: 0 18px 60px rgba(0, 0, 0, .48);
}

* { box-sizing: border-box; }
html { min-width: 320px; background: var(--bg); }

body {
  margin: 0;
  min-height: 100vh;
  overflow-x: hidden;
  color: var(--text);
  background:
    linear-gradient(rgba(255, 111, 53, .045) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 111, 53, .045) 1px, transparent 1px),
    radial-gradient(circle at 50% -20%, rgba(255, 92, 31, .18), transparent 42%),
    var(--bg);
  background-size: 24px 24px, 24px 24px, auto, auto;
  font: 13px/1.35 "Fira Code", "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  letter-spacing: 0;
}

body::before {
  content: "";
  position: fixed;
  inset: 0;
  z-index: -1;
  pointer-events: none;
  background: linear-gradient(180deg, rgba(255,255,255,.045), transparent 2px);
  background-size: 100% 5px;
  opacity: .18;
}

button, input, select, textarea { font: inherit; }
h1, h2, p { margin: 0; }

.skip-link {
  position: absolute;
  left: 12px;
  top: -64px;
  z-index: 100;
  padding: 10px 12px;
  border: 1px solid var(--amber);
  border-radius: 4px;
  background: #2c0f07;
  color: var(--amber);
  font-weight: 800;
}
.skip-link:focus { top: 12px; }

.terminal-topbar {
  min-height: 58px;
  display: grid;
  grid-template-columns: minmax(260px, 1fr) minmax(420px, 2fr);
  align-items: center;
  gap: 18px;
  padding: 10px 18px;
  border-bottom: 1px solid var(--line);
  background: rgba(25, 7, 4, .92);
  box-shadow: var(--shadow);
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.brand-mark {
  width: 28px;
  height: 28px;
  flex: 0 0 auto;
  border: 2px solid var(--amber);
  border-radius: 4px;
  box-shadow: 0 0 16px rgba(255, 127, 45, .7), inset 0 0 10px rgba(255, 127, 45, .32);
}

.brand p,
.panel-head p {
  color: var(--amber);
  font-size: .74rem;
  font-weight: 900;
  text-transform: uppercase;
}

.brand h1 {
  color: var(--muted);
  font-size: .78rem;
  font-weight: 800;
  text-transform: uppercase;
  overflow-wrap: anywhere;
}

.top-status {
  display: grid;
  grid-template-columns: repeat(4, minmax(120px, 1fr));
  gap: 10px;
}

.top-status span {
  min-height: 32px;
  display: grid;
  align-content: center;
  padding: 6px 10px;
  border: 1px solid var(--line);
  background: rgba(42, 14, 8, .58);
  color: var(--muted);
  text-transform: uppercase;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.top-status b { color: var(--text); }
.status-ok { color: var(--green) !important; }
.status-warn { color: var(--amber) !important; }
.status-bad { color: var(--red) !important; }

.terminal-shell {
  display: grid;
  grid-template-columns: minmax(420px, .9fr) 58px minmax(560px, 1.12fr);
  gap: 12px;
  min-height: calc(100vh - 58px);
  padding: 14px;
}

.left-rail,
.right-rail {
  min-width: 0;
  display: grid;
  gap: 12px;
  align-content: start;
}

.terminal-panel {
  position: relative;
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: 4px;
  background: var(--panel);
  box-shadow: var(--shadow), inset 0 0 0 1px rgba(255, 184, 77, .05);
}

.terminal-panel::after {
  content: "";
  position: absolute;
  inset: 0;
  pointer-events: none;
  background: radial-gradient(circle at 50% 0%, rgba(255, 184, 77, .10), transparent 38%);
}

.panel-head {
  position: relative;
  z-index: 1;
  min-height: 58px;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  gap: 10px;
  align-items: center;
  padding: 10px 12px;
  border-bottom: 1px solid var(--line);
  background: rgba(33, 10, 6, .66);
}

.panel-head.compact {
  min-height: 44px;
  grid-template-columns: minmax(0, 1fr) auto;
}

.panel-index {
  min-width: 38px;
  min-height: 30px;
  display: grid;
  place-items: center;
  border: 2px solid var(--amber);
  color: var(--amber);
  font-weight: 900;
}

.panel-head h2 {
  margin-top: 2px;
  color: var(--muted);
  font-size: .78rem;
  font-weight: 800;
  text-transform: lowercase;
  overflow-wrap: anywhere;
}

.panel-kpis {
  display: flex;
  flex-wrap: wrap;
  justify-content: end;
  gap: 10px 18px;
  color: var(--muted);
  text-transform: uppercase;
}

.panel-kpis b {
  display: block;
  color: var(--amber);
  font-size: 1rem;
}

.scanner-panel { min-height: min(65vh, 690px); }
.execution-panel { min-height: min(65vh, 690px); }

.flow-canvas-wrap,
.execution-chart-wrap {
  position: relative;
  z-index: 1;
  height: clamp(380px, 58vh, 620px);
}

canvas {
  display: block;
  width: 100%;
  height: 100%;
}

.signal-bus {
  display: grid;
  grid-template-rows: 1fr auto 1fr;
  place-items: center;
  min-height: 100%;
  color: var(--muted);
}

.signal-bus span {
  writing-mode: vertical-rl;
  transform: rotate(180deg);
  letter-spacing: .32em;
  font-size: .68rem;
  font-weight: 900;
}

.signal-bus i {
  width: 8px;
  height: 8px;
  margin: 18px 0;
  border-radius: 50%;
  background: var(--amber);
  box-shadow: 0 0 12px var(--amber);
}

.lower-grid,
.bottom-grid {
  display: grid;
  grid-template-columns: minmax(260px, .48fr) minmax(320px, .52fr);
  gap: 12px;
}

.bottom-grid { grid-template-columns: minmax(320px, 1fr) minmax(320px, .92fr); }

.process-list,
.terminal-log,
.trade-tape {
  position: relative;
  z-index: 1;
  min-height: 250px;
  max-height: 310px;
  overflow: auto;
  padding: 10px;
}

.process-row {
  display: grid;
  grid-template-columns: 92px 1fr 48px;
  gap: 10px;
  align-items: center;
  min-height: 34px;
  color: var(--muted);
  text-transform: uppercase;
}

.meter {
  height: 7px;
  border: 1px solid rgba(255, 184, 77, .18);
  background: rgba(16, 4, 2, .8);
}

.meter i {
  display: block;
  height: 100%;
  width: 0;
  background: linear-gradient(90deg, var(--orange), var(--amber));
  box-shadow: 0 0 12px rgba(255, 184, 77, .42);
}

.log-row,
.tape-row {
  display: grid;
  grid-template-columns: 82px 42px minmax(0, 1fr);
  gap: 8px;
  min-height: 24px;
  align-items: center;
  border-bottom: 1px solid rgba(255, 111, 53, .08);
  color: var(--muted);
}

.log-row b,
.tape-row b { color: var(--amber); }
.log-row span,
.tape-row span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.trade-tape .tape-row {
  grid-template-columns: 46px minmax(0, 1fr) 58px 58px;
}

.side-buy { color: var(--green) !important; }
.side-sell { color: var(--red) !important; }
.side-sig { color: var(--amber) !important; }

.execution-metrics {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: repeat(5, minmax(110px, 1fr));
  gap: 12px;
  padding: 12px 12px 0;
}

.execution-metrics > div {
  min-height: 88px;
  display: grid;
  align-content: start;
  gap: 6px;
  border-bottom: 1px solid var(--line);
}

.execution-metrics span {
  color: var(--muted);
  font-size: .66rem;
  font-weight: 900;
  text-transform: uppercase;
}

.execution-metrics b {
  color: var(--amber);
  font-size: clamp(1rem, 1.8vw, 1.45rem);
  line-height: 1;
  overflow-wrap: anywhere;
}

[data-bar],
[data-spark],
[data-bars],
[data-leds] {
  display: block;
  height: 28px;
  background-repeat: no-repeat;
}

@media (max-width: 1180px) {
  .terminal-shell {
    grid-template-columns: 1fr;
  }
  .signal-bus { display: none; }
  .scanner-panel,
  .execution-panel { min-height: 520px; }
  .flow-canvas-wrap,
  .execution-chart-wrap { height: 440px; }
}

@media (max-width: 760px) {
  body { font-size: 12px; }
  .terminal-topbar,
  .top-status,
  .lower-grid,
  .bottom-grid,
  .execution-metrics {
    grid-template-columns: 1fr;
  }
  .terminal-shell { padding: 8px; }
  .panel-head { grid-template-columns: auto minmax(0, 1fr); }
  .panel-kpis { grid-column: 1 / -1; justify-content: start; }
  .scanner-panel,
  .execution-panel { min-height: 480px; }
}

@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    scroll-behavior: auto !important;
    transition: none !important;
    animation: none !important;
  }
}

:focus-visible {
  outline: 3px solid var(--cyan);
  outline-offset: 3px;
}
"""


DASHBOARD_JS = r"""
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const marketCanvas = $("market-flow");
  const execCanvas = $("execution-flow");
  const marketCtx = marketCanvas ? marketCanvas.getContext("2d") : null;
  const execCtx = execCanvas ? execCanvas.getContext("2d") : null;
  const moneyFmt = new Intl.NumberFormat(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 0 });
  const reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  let pollTimer = null;
  let frameId = null;
  let snapshot = {};
  let transportLabel = "FETCH";
  let chartSeries = [];
  let lastChartSnapshot = "";
  let pulse = 0;

  function n(v, defaultValue = 0) {
    const out = Number(v);
    return Number.isFinite(out) ? out : defaultValue;
  }

  function money(v) {
    return moneyFmt.format(n(v));
  }

  function text(v, defaultValue = "n/a") {
    return v === null || v === undefined || v === "" ? defaultValue : String(v);
  }

  function field(obj, names, defaultValue = "") {
    for (const name of names) {
      if (obj && obj[name] !== undefined && obj[name] !== null && obj[name] !== "") return obj[name];
    }
    return defaultValue;
  }

  function compactTime(v) {
    const d = v ? new Date(v) : new Date();
    if (Number.isNaN(d.getTime())) return "--:--:--";
    return d.toISOString().slice(11, 19);
  }

  function setText(id, value) {
    const node = $(id);
    if (node) node.textContent = text(value);
  }

  function setStatus(id, label, tone) {
    const node = $(id);
    if (!node) return;
    node.textContent = label;
    node.className = tone ? `status-${tone}` : "";
  }

  function clear(node) {
    if (!node) return;
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  function fitCanvas(canvas, ctx) {
    if (!canvas || !ctx) return;
    const rect = canvas.getBoundingClientRect();
    const dpr = Math.max(1, Math.min(2, window.devicePixelRatio || 1));
    const width = Math.max(320, Math.floor(rect.width * dpr));
    const height = Math.max(260, Math.floor(rect.height * dpr));
    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
    }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  function derivedMarkets() {
    const markets = snapshot.markets && Array.isArray(snapshot.markets.watching) ? snapshot.markets.watching : [];
    const signals = Array.isArray(snapshot.signals) ? snapshot.signals : [];
    const rows = [];
    for (const market of markets.slice(0, 10)) {
      rows.push([
        field(market, ["question", "market_id", "id"], "watching market"),
        `QUICK ${strategyLabel(field(market, ["strategy_candidates"], []), field(market, ["category"], "MARKET"))}`,
        Math.round(n(field(market, ["quickfire_score", "market_quality"], 0)) * 100),
        Math.max(.28, n(field(market, ["liquidity_usd"], 0)) / 250000),
        0.18 + (rows.length % 4) * .2,
        0.25 + (rows.length % 3) * .22
      ]);
    }
    for (const sig of signals.slice(0, 10 - rows.length)) {
      rows.push([
        field(sig, ["market_id"], "signal"),
        field(sig, ["strategy"], "SIGNAL"),
        Math.round(n(field(sig, ["score"], 0))),
        Math.max(.28, n(field(sig, ["score"], 0)) / 100),
        0.18 + (rows.length % 4) * .2,
        0.25 + (rows.length % 3) * .22
      ]);
    }
    return rows;
  }

  function strategyLabel(value, category) {
    if (Array.isArray(value) && value.length) return String(value[0]).toUpperCase();
    if (typeof value === "string" && value.trim()) {
      try {
        const parsed = JSON.parse(value);
        if (Array.isArray(parsed) && parsed.length) return String(parsed[0]).toUpperCase();
      } catch (_err) {
        return value.toUpperCase();
      }
    }
    return String(category || "MARKET").toUpperCase();
  }

  function drawMarketFlow() {
    if (!marketCanvas || !marketCtx) return;
    fitCanvas(marketCanvas, marketCtx);
    const rect = marketCanvas.getBoundingClientRect();
    const w = rect.width;
    const h = rect.height;
    const ctx = marketCtx;
    ctx.clearRect(0, 0, w, h);
    drawGrid(ctx, w, h, 24, 0.06);

    const compact = w < 520;
    const compactPositions = [
      [0.30, 0.22], [0.70, 0.22], [0.24, 0.48], [0.72, 0.48],
      [0.34, 0.74], [0.70, 0.76]
    ];
    const rows = derivedMarkets().slice(0, compact ? compactPositions.length : 10);
    if (!rows.length) {
      drawEmptyCanvasMessage(ctx, w, h, "NO LIVE MARKETS OR SIGNALS", "scanner data will appear after runtime ticks");
      return;
    }
    const nodes = rows.map((row, i) => {
      const jitter = Math.sin(pulse / 40 + i) * 8;
      const px = compact ? compactPositions[i][0] : row[4];
      const py = compact ? compactPositions[i][1] : row[5];
      const radius = compact ? 28 + Math.min(20, row[3] * 22) : 34 + Math.min(58, row[3] * 58);
      return {
        label: row[0],
        category: row[1],
        prob: row[2],
        weight: row[3],
        x: px * w + (compact ? jitter * .35 : jitter),
        y: py * h + Math.cos(pulse / 45 + i) * (compact ? 2 : 6),
        r: radius
      };
    });

    ctx.save();
    ctx.strokeStyle = "rgba(255, 132, 52, .18)";
    ctx.lineWidth = 1;
    for (let i = 0; i < nodes.length; i += 1) {
      const a = nodes[i];
      const b = nodes[(i + 1) % nodes.length];
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.stroke();
    }
    ctx.restore();

    for (const [i, node] of nodes.entries()) {
      const glow = 8 + Math.sin(pulse / 12 + i) * 5;
      const intensity = Math.max(.28, Math.min(1, node.weight));
      const fill = `rgba(208, ${Math.round(62 + 72 * intensity)}, 34, ${0.24 + intensity * .34})`;
      ctx.save();
      ctx.shadowColor = "rgba(255, 145, 55, .9)";
      ctx.shadowBlur = glow + node.r * .18;
      ctx.fillStyle = fill;
      ctx.strokeStyle = i % 3 === 0 ? "rgba(255, 190, 77, .92)" : "rgba(255, 105, 53, .68)";
      ctx.lineWidth = i % 3 === 0 ? 2 : 1;
      ctx.beginPath();
      ctx.arc(node.x, node.y, node.r, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
      ctx.shadowBlur = 0;
      ctx.fillStyle = "#ffd9ab";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.font = compact ? "700 8px Fira Code, monospace" : "700 11px Fira Code, monospace";
      wrapCanvasText(
        ctx,
        node.label,
        node.x,
        node.y - (compact ? 8 : 10),
        node.r * (compact ? 1.35 : 1.25),
        compact ? 10 : 13,
        compact ? 2 : 3
      );
      ctx.fillStyle = "#ffb84d";
      ctx.font = compact ? "900 14px Fira Code, monospace" : "900 18px Fira Code, monospace";
      ctx.fillText(`${node.prob}c`, node.x, node.y + (compact ? 16 : 22));
      ctx.fillStyle = "rgba(255, 217, 171, .52)";
      ctx.font = compact ? "700 7px Fira Code, monospace" : "700 9px Fira Code, monospace";
      ctx.fillText(
        String(node.category).slice(0, compact ? 10 : 14).toUpperCase(),
        node.x,
        node.y + (compact ? 29 : 40)
      );
      ctx.restore();
    }
  }

  function drawExecutionFlow() {
    if (!execCanvas || !execCtx) return;
    fitCanvas(execCanvas, execCtx);
    const rect = execCanvas.getBoundingClientRect();
    const w = rect.width;
    const h = rect.height;
    const ctx = execCtx;
    ctx.clearRect(0, 0, w, h);
    drawGrid(ctx, w, h, 28, 0.05);

    const pad = { l: 54, r: 18, t: 26, b: 42 };
    const plotW = w - pad.l - pad.r;
    const plotH = h - pad.t - pad.b;
    if (chartSeries.length < 2) {
      drawEmptyCanvasMessage(ctx, w, h, "AWAITING LIVE EXECUTION FLOW", "chart starts after two runtime snapshots");
      return;
    }

    const max = Math.max(1, ...chartSeries) * 1.18;
    ctx.save();
    ctx.strokeStyle = "rgba(255, 184, 77, .28)";
    ctx.fillStyle = "rgba(255, 184, 77, .55)";
    ctx.font = "700 10px Fira Code, monospace";
    const ticks = buildTicks(max);
    for (const val of ticks) {
      const y = pad.t + plotH - (val / max) * plotH;
      if (y < pad.t || y > pad.t + plotH) continue;
      ctx.globalAlpha = .55;
      ctx.beginPath();
      ctx.moveTo(pad.l, y);
      ctx.lineTo(w - pad.r, y);
      ctx.stroke();
      ctx.globalAlpha = 1;
      ctx.fillText(String(Math.round(val)), 8, y + 4);
    }

    const pts = chartSeries.map((v, i) => [
      pad.l + (i / (chartSeries.length - 1)) * plotW,
      pad.t + plotH - (v / max) * plotH
    ]);
    ctx.beginPath();
    pts.forEach((p, i) => i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1]));
    ctx.strokeStyle = "#ffb84d";
    ctx.lineWidth = 2;
    ctx.shadowColor = "rgba(255, 184, 77, .8)";
    ctx.shadowBlur = 14;
    ctx.stroke();

    ctx.lineTo(pad.l + plotW, pad.t + plotH);
    ctx.lineTo(pad.l, pad.t + plotH);
    ctx.closePath();
    ctx.fillStyle = "rgba(255, 95, 42, .24)";
    ctx.shadowBlur = 0;
    ctx.fill();

    const idx = Math.max(0, pts.length - 16);
    const marker = pts[idx];
    ctx.strokeStyle = "rgba(255, 184, 77, .45)";
    ctx.setLineDash([4, 5]);
    ctx.beginPath();
    ctx.moveTo(marker[0], pad.t);
    ctx.lineTo(marker[0], pad.t + plotH);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = "rgba(70, 24, 12, .92)";
    ctx.strokeStyle = "rgba(255, 184, 77, .8)";
    ctx.lineWidth = 1;
    ctx.fillRect(marker[0] - 56, marker[1] - 44, 128, 34);
    ctx.strokeRect(marker[0] - 56, marker[1] - 44, 128, 34);
    ctx.fillStyle = "#ffb84d";
    ctx.font = "800 10px Fira Code, monospace";
    ctx.fillText("LIVE SNAPSHOT", marker[0] - 46, marker[1] - 30);
    ctx.fillStyle = "#9f6d52";
    ctx.fillText(`score ${Math.round(chartSeries[idx])}`, marker[0] - 46, marker[1] - 16);

    ctx.fillStyle = "rgba(255, 217, 171, .48)";
    ctx.font = "700 10px Fira Code, monospace";
    for (let i = 1; i <= 8; i += 1) {
      ctx.fillText(`M${i}`, pad.l + (i - 1) / 7 * plotW, h - 16);
    }
    ctx.restore();
  }

  function buildTicks(max) {
    const step = Math.max(1, Math.ceil(max / 4));
    return [step, step * 2, step * 3, step * 4].filter((v) => v <= max);
  }

  function drawEmptyCanvasMessage(ctx, w, h, title, detail) {
    ctx.save();
    ctx.fillStyle = "rgba(255, 184, 77, .82)";
    ctx.font = "900 13px Fira Code, monospace";
    ctx.textAlign = "center";
    ctx.fillText(title, w / 2, h / 2 - 10);
    ctx.fillStyle = "rgba(255, 217, 171, .48)";
    ctx.font = "700 11px Fira Code, monospace";
    ctx.fillText(detail, w / 2, h / 2 + 12);
    ctx.restore();
  }

  function drawGrid(ctx, w, h, size, alpha) {
    ctx.save();
    ctx.strokeStyle = `rgba(255, 111, 53, ${alpha})`;
    ctx.lineWidth = 1;
    for (let x = 0; x <= w; x += size) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, h);
      ctx.stroke();
    }
    for (let y = 0; y <= h; y += size) {
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(w, y);
      ctx.stroke();
    }
    ctx.restore();
  }

  function wrapCanvasText(ctx, value, x, y, maxWidth, lineHeight, maxLines) {
    const words = text(value).split(/\s+/);
    const lines = [];
    let line = "";
    for (const word of words) {
      const trial = line ? `${line} ${word}` : word;
      if (ctx.measureText(trial).width > maxWidth && line) {
        lines.push(line);
        line = word;
      } else {
        line = trial;
      }
      if (lines.length === maxLines) break;
    }
    if (line && lines.length < maxLines) lines.push(line);
    lines.slice(0, maxLines).forEach((l, i) => ctx.fillText(l, x, y + i * lineHeight));
  }

  function renderMetrics() {
    const s = snapshot.summary || {};
    const signals = Array.isArray(snapshot.signals) ? snapshot.signals : [];
    const orders = Array.isArray(snapshot.orders) ? snapshot.orders : [];
    const positions = Array.isArray(snapshot.positions) ? snapshot.positions : [];
    const ready = n(s.automation_sources_ready);
    const total = n(s.automation_sources_total);

    setText("metric-watching", n(s.watching_markets));
    setText("metric-signals", signals.length);
    setText("metric-kill", n(s.kill_switch_events));
    setText("metric-orders", n(s.open_orders, orders.length));
    setText("metric-risk", money(s.bankroll_at_risk));
    setText("metric-clv", n(s.average_clv_bps).toFixed(1));
    setText("metric-score", n(s.average_signal_score).toFixed(2));
    setText("metric-market-value", money(s.market_value));
    setText("metric-automation", `${ready}/${total}`);
    setText("metric-positions", n(s.open_positions, positions.length));
    setText("metric-pnl", `${n(s.average_clv_bps).toFixed(1)} bps`);
    setText("metric-orders", n(s.open_orders));
    setText("scanner-subtitle", `${n(s.watching_markets)} markets / ${signals.length} signals / cross-market diff`);
    setText("execution-subtitle", `${n(s.total_records)} audit records / ${n(s.placed_orders)} placed / ${n(s.rejected_orders)} rejected`);
    setText("metric-automation", `${ready}/${total}`);
    setStatus("automation-status", `${ready}/${total}`, total && ready === total ? "ok" : "warn");

    const hb = snapshot.heartbeat || {};
    const fresh = Boolean(hb.fresh);
    setStatus("heartbeat-status", fresh ? "LIVE" : "MISSING", fresh ? "ok" : "bad");
    setStatus("stream-status", transportLabel, transportLabel === "SSE" ? "ok" : "warn");
    setText("snapshot-time", compactTime(snapshot.generated_at));
    updateInlineMicrocharts(s);
  }

  function updateInlineMicrocharts(s) {
    const score = Math.max(0, Math.min(100, n(s.average_signal_score)));
    const scoreNode = document.querySelector("[data-bar='score']");
    if (scoreNode) {
      scoreNode.style.backgroundImage = `linear-gradient(90deg, #ff6f35 ${score}%, rgba(255,111,53,.14) ${score}%)`;
    }
    const valueNode = document.querySelector("[data-spark='value']");
    if (valueNode) {
      valueNode.style.backgroundImage = "linear-gradient(135deg, transparent 10%, rgba(255,184,77,.22) 11%, transparent 12%), linear-gradient(90deg, rgba(255,111,53,.2), rgba(255,184,77,.65))";
      valueNode.style.backgroundSize = "18px 18px, 100% 7px";
      valueNode.style.backgroundPosition = "0 8px, 0 18px";
    }
    const autoNode = document.querySelector("[data-bars='automation']");
    if (autoNode) {
      const ready = n(s.automation_sources_ready);
      autoNode.style.backgroundImage = `repeating-linear-gradient(90deg, #ffb84d 0 18px, transparent 18px 24px)`;
      autoNode.style.opacity = String(Math.max(.25, ready / Math.max(1, n(s.automation_sources_total))));
    }
    const ledNode = document.querySelector("[data-leds='positions']");
    if (ledNode) {
      const positions = n(s.open_positions);
      ledNode.style.backgroundImage = positions
        ? "repeating-linear-gradient(90deg, #ff6f35 0 5px, rgba(255,111,53,.15) 5px 10px)"
        : "linear-gradient(90deg, rgba(255,111,53,.12), rgba(255,111,53,.12))";
    }
    const pnlNode = document.querySelector("[data-bars='pnl']");
    if (pnlNode) {
      const clv = Math.min(100, Math.abs(n(s.average_clv_bps)));
      pnlNode.style.backgroundImage = `linear-gradient(90deg, rgba(146,224,113,.55) ${clv}%, rgba(255,111,53,.12) ${clv}%)`;
    }
  }

  function renderProcesses() {
    const sources = Array.isArray(snapshot.automation_sources) ? snapshot.automation_sources : [];
    const s = snapshot.summary || {};
    const sourceReady = n(s.automation_sources_ready);
    const sourceTotal = Math.max(1, n(s.automation_sources_total));
    const rows = [
      ["sse stream", transportLabel === "SSE" ? 100 : 0],
      ["heartbeat", snapshot.heartbeat && snapshot.heartbeat.fresh ? 100 : 0],
      ["source pins", (sourceReady / sourceTotal) * 100],
      ["watchlist", Math.min(100, n(s.watching_markets) * 10)],
      ["signals", Math.min(100, (Array.isArray(snapshot.signals) ? snapshot.signals.length : 0) * 10)],
      ["audit log", Math.min(100, n(s.total_records) * 10)]
    ];
    const list = $("process-list");
    clear(list);
    setText("process-count", `${rows.length} live lanes`);
    for (const [label, pct] of rows) {
      const row = document.createElement("div");
      row.className = "process-row";
      const name = document.createElement("span");
      name.textContent = label;
      const meter = document.createElement("div");
      meter.className = "meter";
      const bar = document.createElement("i");
      bar.style.width = `${pct}%`;
      meter.appendChild(bar);
      const val = document.createElement("b");
      val.textContent = `${Math.round(pct)}%`;
      row.append(name, meter, val);
      list.appendChild(row);
    }
  }

  function renderLogs() {
    const rows = Array.isArray(snapshot.log_tail) ? snapshot.log_tail.slice(-16).reverse() : [];
    const scanner = rows.filter((r) => String(field(r, ["actor"], "")).includes("scanner") || String(field(r, ["action"], "")).includes("check"));
    const exec = rows.filter((r) => !scanner.includes(r));
    renderLogList("log-list", "log-count", scanner.length ? scanner : rows.slice(0, 12));
    renderLogList("exec-list", "exec-count", exec.length ? exec : rows.slice(0, 12));
    renderTape();
  }

  function renderLogList(id, countId, rows) {
    const list = $(id);
    clear(list);
    setText(countId, `${rows.length} rows`);
    if (!rows.length) {
      const row = document.createElement("div");
      row.className = "log-row";
      row.innerHTML = "<b>--:--:--</b><b>WAIT</b><span>awaiting immutable records</span>";
      list.appendChild(row);
      return;
    }
    for (const r of rows) {
      const actor = field(r, ["actor"], "sys");
      const action = field(r, ["action"], "event");
      const row = document.createElement("div");
      row.className = "log-row";
      row.append(cell("b", compactTime(field(r, ["ts"], ""))));
      row.append(cell("b", String(action).slice(0, 4).toUpperCase(), toneFor(action)));
      row.append(cell("span", `${actor} ${action} ${field(r, ["market_id", "event_id"], "")}`));
      list.appendChild(row);
    }
  }

  function renderTape() {
    const rows = tradeTapeRows();
    const list = $("tape-list");
    clear(list);
    setText("tape-count", `${Math.min(12, rows.length)} rows`);
    if (!rows.length) {
      const row = document.createElement("div");
      row.className = "tape-row";
      row.append(cell("b", "WAIT", "side-sig"));
      row.append(cell("span", "awaiting live orders or signals"));
      row.append(cell("b", "--"));
      row.append(cell("span", "--"));
      list.appendChild(row);
      return;
    }
    for (const r of rows.slice(0, 12)) {
      const row = document.createElement("div");
      row.className = "tape-row";
      row.append(cell("b", r.kind, tapeTone(r.kind)));
      row.append(cell("span", r.label));
      row.append(cell("b", r.value));
      row.append(cell("span", r.detail));
      list.appendChild(row);
    }
  }

  function tradeTapeRows() {
    const rows = [];
    const orders = Array.isArray(snapshot.orders) ? snapshot.orders : [];
    const signals = Array.isArray(snapshot.signals) ? snapshot.signals : [];
    const markets = snapshot.markets && Array.isArray(snapshot.markets.watching) ? snapshot.markets.watching : [];
    const logs = Array.isArray(snapshot.log_tail) ? snapshot.log_tail : [];

    for (const order of orders) {
      const side = String(field(order, ["side"], "ORD")).toUpperCase().slice(0, 4);
      rows.push({
        ts: field(order, ["observed_at", "created_at", "ts"], ""),
        kind: side || "ORD",
        label: `${field(order, ["market_id"], "order")} ${field(order, ["token_id"], "")}`,
        value: formatPrice(field(order, ["price"], "")),
        detail: `${field(order, ["status"], "OPEN")} ${formatSize(field(order, ["size"], ""))}`.trim(),
        rank: 3
      });
    }

    for (const signal of signals) {
      const side = String(field(signal, ["side"], "SIG")).toUpperCase().slice(0, 4);
      rows.push({
        ts: field(signal, ["created_at", "updated_at", "ts"], ""),
        kind: side || "SIG",
        label: `${field(signal, ["strategy"], "strategy")} ${field(signal, ["market_id"], "")}`.trim(),
        value: formatPrice(field(signal, ["market_price"], "")),
        detail: `${field(signal, ["status"], "signal")} score ${Math.round(n(field(signal, ["score"], 0)))}`.trim(),
        rank: 2 + n(field(signal, ["score"], 0)) / 100
      });
    }

    for (const market of markets) {
      rows.push({
        ts: field(snapshot, ["generated_at"], field(market, ["created_at", "close_time"], "")),
        kind: "CAND",
        label: field(market, ["question", "id"], "quickfire candidate"),
        value: `${Math.round(n(field(market, ["quickfire_score"], 0)) * 100)}`,
        detail: strategyLabel(field(market, ["strategy_candidates"], []), "strategy"),
        rank: 1 + n(field(market, ["quickfire_score"], 0))
      });
    }

    for (const log of logs) {
      const actor = String(field(log, ["actor"], ""));
      const action = String(field(log, ["action"], ""));
      if (!isTradeTapeLog(actor, action)) continue;
      const payload = field(log, ["payload"], {});
      const strategies = strategyLabel(field(payload, ["strategy_candidates"], []), action);
      const approved = field(payload, ["approved"], null);
      if (actor === "market_scanner" && approved !== true) continue;
      rows.push({
        ts: field(log, ["ts"], ""),
        kind: action.toUpperCase().slice(0, 4) || "LOG",
        label: `${actor} ${field(log, ["market_id", "event_id"], "")}`.trim(),
        value: "--",
        detail: actor === "market_scanner" ? `${approved ? "approved" : "checked"} ${strategies}` : action,
        rank: 0
      });
    }

    rows.sort((a, b) => {
      const timeDelta = Date.parse(b.ts || 0) - Date.parse(a.ts || 0);
      if (timeDelta !== 0) return timeDelta;
      return n(b.rank) - n(a.rank);
    });
    return rows;
  }

  function isTradeTapeLog(actor, action) {
    const raw = `${actor} ${action}`.toLowerCase();
    return (
      (raw.includes("market_scanner") && raw.includes("classify")) ||
      raw.includes("signal") ||
      raw.includes("place_order") ||
      raw.includes("format") ||
      raw.includes("risk_governor") ||
      raw.includes("clob")
    );
  }

  function formatPrice(value) {
    if (value === null || value === undefined || value === "") return "--";
    const price = n(value, NaN);
    if (!Number.isFinite(price)) return text(value, "--");
    if (price > 0 && price <= 1) return `${Math.round(price * 100)}c`;
    return price.toFixed(price % 1 ? 3 : 0);
  }

  function formatSize(value) {
    if (value === null || value === undefined || value === "") return "";
    const size = n(value, NaN);
    if (!Number.isFinite(size)) return text(value, "");
    return `x${size.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
  }

  function tapeTone(kind) {
    const raw = String(kind).toUpperCase();
    if (raw.includes("BUY")) return "side-buy";
    if (raw.includes("SELL") || raw.includes("REJE") || raw.includes("FAIL")) return "side-sell";
    return "side-sig";
  }

  function cell(tag, content, className) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    el.textContent = text(content, "");
    return el;
  }

  function toneFor(action) {
    const raw = String(action).toLowerCase();
    if (raw.includes("reject") || raw.includes("kill") || raw.includes("fail")) return "side-sell";
    if (raw.includes("place") || raw.includes("ready") || raw.includes("check")) return "side-buy";
    return "side-sig";
  }

  function render(data, transport) {
    snapshot = data || {};
    transportLabel = transport || transportLabel;
    updateChartSeries();
    renderMetrics();
    renderProcesses();
    renderLogs();
    drawMarketFlow();
    drawExecutionFlow();
  }

  function updateChartSeries() {
    const snapshotId = snapshot.generated_at || "";
    if (!snapshotId || snapshotId === lastChartSnapshot) return;
    lastChartSnapshot = snapshotId;
    const s = snapshot.summary || {};
    const value =
      n(s.total_records) +
      n(s.open_orders) * 4 +
      n(s.open_positions) * 6 +
      n(s.placed_orders) * 8 +
      n(s.rejected_orders) * 3 +
      n(s.kill_switch_events) * 10;
    chartSeries.push(value);
    if (chartSeries.length > 96) chartSeries.shift();
  }

  async function fetchSnapshot(transport) {
    const res = await fetch("/api/state", { cache: "no-store", headers: { "Accept": "application/json" } });
    if (!res.ok) throw new Error(`state ${res.status}`);
    render(await res.json(), transport);
  }

  function startFetchPolling() {
    clearInterval(pollTimer);
    fetchSnapshot("FETCH").catch(() => setStatus("stream-status", "OFFLINE", "bad"));
    pollTimer = setInterval(() => {
      fetchSnapshot("FETCH").catch(() => setStatus("stream-status", "OFFLINE", "bad"));
    }, 2500);
  }

  function connectStream() {
    if (!("EventSource" in window)) {
      startFetchPolling();
      return;
    }
    const es = new EventSource("/api/stream");
    es.addEventListener("open", () => setStatus("stream-status", "SSE", "ok"));
    es.addEventListener("snapshot", (event) => {
      try {
        render(JSON.parse(event.data), "SSE");
      } catch (_) {
        setStatus("stream-status", "BAD SNAP", "bad");
      }
    });
    es.onerror = () => {
      es.close();
      setStatus("stream-status", "RECONNECT", "warn");
      setTimeout(connectStream, 3000);
      startFetchPolling();
    };
  }

  function animate() {
    pulse += 1;
    if (!reduceMotion) {
      drawMarketFlow();
      drawExecutionFlow();
      frameId = window.requestAnimationFrame(animate);
    }
  }

  window.addEventListener("resize", () => {
    drawMarketFlow();
    drawExecutionFlow();
  });

  connectStream();
  fetchSnapshot("FETCH").catch(() => {});
  if (!reduceMotion) frameId = window.requestAnimationFrame(animate);
  window.addEventListener("beforeunload", () => {
    if (frameId) window.cancelAnimationFrame(frameId);
  });
})();
"""
