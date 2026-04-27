# POLYFLOW

Autonomous Polymarket trading runtime for daily/quickfire markets. POLYFLOW scans
public Polymarket markets, filters for liquid near-term candidates, analyzes
public news and optional external anchors, scores strategy signals, and routes
any candidate through the full risk/order gauntlet before placement.

Prime directive: survive first, trade second, scale last. See
`POLYFLOW_POLYMARKET_PRD.md` for the full spec.

## Layout

```
src/polyflow/                  deterministic core
src/polyflow/strategies/       probability producers (external odds, news, four-layer, BTC)
src/polyflow/adapters/         Gamma / CLOB read+trade / Data API / RSS news + stubs
src/polyflow/persistence/      SQLite store
src/polyflow/subagents/        scheduler + heartbeat + sentinel + 24/7 automation
skills/  hooks/  subagents/    operational contracts (markdown)
configs/policy.yaml            live policy
deploy/polyflow.service        systemd unit for VPS deployment
db/schema.sql                  PostgreSQL schema
tests/                         281 passing tests, 5 skipped (no live network calls)
.env.local                     local secrets (gitignored)
```

## Install

```bash
python -m venv .venv
. .venv/Scripts/activate    # Windows bash
pip install -e ".[dev,trade]"
```

`[trade]` brings in `eth-account` for L1/EIP-712 signing. Skip it for OBSERVE / PAPER mode.

## Run tests

```bash
PYTHONIOENCODING=utf-8 pytest    # Windows
pytest                            # Linux / macOS
```

## CLI

```
polyflow run                Run the 24/7 runtime (stub adapters by default)
polyflow scan-once          Single scanner tick; --live pulls public Polymarket markets
polyflow show-policy        Echo parsed policy + config hash
polyflow status             Heartbeat + tail of immutable log
polyflow calibrate          Compute Brier / log-loss / bucket calibration
polyflow promotion-check    LIVE_TINY -> LIVE_STANDARD gate evaluator
polyflow creds-check        Redacted credential summary
polyflow derive-creds       Sign ClobAuth + POST /auth/api-key to derive secret + passphrase
polyflow positions          Read live wallet positions from the Data API
```

## 24/7 automation

Recommended analysis/paper command:

```bash
polyflow run \
  --config configs/policy.yaml \
  --log logs/immutable.jsonl \
  --db logs/polyflow.db \
  --live-scanner \
  --gamma-limit 120
```

Registered runtime tasks:

| Task | Default cadence | Purpose |
|---|---:|---|
| `heartbeat` | 10s | Liveness file for dashboard/ops |
| `market_scanner` | 300s | Pull public Gamma markets, enrich CLOB depth, admit daily quickfire markets |
| `strategy_automation` | 30s | Analyze approved markets with external anchors/news and submit signals through gates |
| `trade_activity_analyzer` | 60s | Poll wallet activity/positions for audit and monitoring |
| `order_sync` | 30s | Sync open CLOB orders when the adapter supports it |
| `resolution_monitor` | 900s | Close calibration loop on resolved markets |
| `reference_repo_monitor` | 3600s | Verify pinned automation source repos |

The strategy automation loop does not bypass safety. Candidate trades must pass:
scanner approval, probability estimate, signal scoring, Kelly/risk approval,
CLOB order formatting, CLOB placement, post-order exposure check, and immutable
logging.

## Daily quickfire scanner

`configs/policy.yaml` is tuned for daily markets:

```yaml
market_filters:
  min_liquidity_usd: 100000
  min_volume_24h_usd: 25000
  max_spread_pct: 5
  min_depth_within_5c_usd: 10000
  min_time_to_close_minutes: 60
  max_time_to_close_minutes: 2160
```

Approved markets are additionally ranked by `quickfire_score`, which combines
close window, 24h volume, liquidity, spread, depth, and strategy coverage. The
dashboard active scanner only renders quickfire-eligible markets, sorted by this
score. Long-horizon markets are not shown as trade candidates.

Live inspection:

```bash
polyflow scan-once --config configs/policy.yaml --db logs/polyflow.db --log logs/immutable.jsonl --live --gamma-limit 120
```

## Strategy automation inputs

Configured in `configs/policy.yaml`:

```yaml
automation:
  enabled: true
  allow_order_placement: false
  max_markets_per_strategy_cycle: 12
  external_anchors_path: configs/external_anchors.json
  news_rss_urls:
    - https://www.reutersagency.com/feed/?best-topics=political-general&post_type=best
    - https://www.espn.com/espn/rss/news
    - https://www.coindesk.com/arc/outboundfeeds/rss/
    - https://feeds.bbci.co.uk/news/world/rss.xml
```

`external_anchors_path` is optional. If present, it should map market IDs to
public external probability anchors:

```json
{
  "0xMARKET": [
    {
      "source": "regulated-anchor",
      "yes_decimal_odds": 1.55,
      "no_decimal_odds": 2.45,
      "reliability": 0.9,
      "settlement_match": true
    }
  ]
}
```

RSS/news analysis uses public feeds only. It creates candidate public-source
events for the existing `news_repricing` strategy; the strategy still refuses
weak, stale, low-reliability, or single-source major deltas.

## Credential setup (live trading)

Live order placement requires four secrets in `.env.local` (which is gitignored):

```
POLY_PRIVATE_KEY=0x…       # Polygon EOA private key — never commit
POLY_API_KEY=…             # derived in the next step (or pre-existing)
POLY_API_SECRET=…          # derived
POLY_API_PASSPHRASE=…      # derived
POLY_FUNDER_ADDRESS=0x…    # proxy / Gnosis Safe holding USDC + outcome tokens (POLY_PROXY signature type)
POLY_WALLET_ADDRESS=0x…    # informational; derivable from the private key
```

If you only have a private key, derive the L2 set:

```bash
polyflow derive-creds --write     # signs ClobAuth, calls POST /auth/api-key, appends to .env.local
```

The derive-creds command:
- builds the EIP-712 `ClobAuth` typed message (chain 137, Polymarket's `ClobAuthDomain`)
- signs it with the private key via `eth-account`
- attaches POLY_ADDRESS / POLY_SIGNATURE / POLY_TIMESTAMP / POLY_NONCE headers
- POSTs to `https://clob.polymarket.com/auth/api-key`
- reads back `{apiKey, secret, passphrase}` and (with `--write`) appends them to `.env.local` without overwriting existing keys

Mirrors `client.createOrDeriveApiKey()` from `@polymarket/clob-client-v2`.

## Order placement

`polyflow.adapters.polymarket_clob_trade.PolymarketCLOBTradeAdapter.place_order()` signs an EIP-712 `Order` against the CTF Exchange contract (`0x4bFb…`) — or the neg-risk variant (`0xC5d5…`) — and POSTs to `/order`. Every invariant is checked locally before signing:

- price strictly in `(0, 1)`, size > 0
- `signatureType` in `{0=EOA, 1=POLY_PROXY, 2=POLY_GNOSIS_SAFE}`
- `maker == funder_address` for proxy/Safe types, else `maker == signer`
- integer `makerAmount` / `takerAmount` in 6-decimal base units cross-checked against `price * size`
- `feeRateBps` in `[0, 10000]`

`signatureType` defaults to `1` (POLY_PROXY); set on adapter construction.

## Live trading gates

Credentials alone are not enough to place live orders. Live placement requires
both:

1. `automation.allow_order_placement: true` in `configs/policy.yaml`
2. `--live-trading` on `polyflow run`

Example, only after the policy gate is intentionally flipped:

```bash
polyflow run \
  --config configs/policy.yaml \
  --log logs/immutable.jsonl \
  --db logs/polyflow.db \
  --live-scanner \
  --live-trading \
  --gamma-limit 120
```

If `--live-trading` is passed while `allow_order_placement` is false, the CLI
exits before starting the runtime. This is intentional.

## Modes

| Mode | Effect |
|---|---|
| `observe` | scan + score; no orders |
| `paper` | simulate orders/fills via PaperCLOBAdapter |
| `live_confirm` | propose orders for human approval |
| `live_tiny` | autonomous with hard caps (PRD §10.3 first-day limits) |
| `live_standard` | autonomous after promotion gates pass |
| `lockdown` | flatten / no-new-orders |

## Hard rules (from `CLAUDE.md`)

1. No order without market approval, valid probability, Kelly approval, Risk Governor approval, evidence pack, post-order hook, and immutable log.
2. Public information only. No spoofing, wash trading, self-dealing, manipulation, or front-running.
3. Skip low-liquidity, wide-spread, ambiguous, insider-risk, manipulation-risk, or poor-resolution markets.
4. Every candidate trade must be valid JSON. Malformed output is rejected.

## Agent quick start

Agents should read `docs/AGENT_QUICKSTART.md` before changing runtime,
strategy, order, automation, or dashboard code. It summarizes the system map,
non-negotiable safety gates, daily quickfire policy, core commands, and the
safe-change checklist.

## Operations tools

```
polyflow summarize-log       Actor / action / kill-switch / order counts from the log
polyflow replay-trade        Pull every record relevant to one signal_id (audit)
polyflow ghost-summary       Aggregate ghost-mode failure modes (Protocol §5)
polyflow deployment-gates    Walk the five deployment gates (Protocol §7)
polyflow reconcile           On-chain vs local-state drift check (Protocol §8)
polyflow dashboard           Real-time local operations console
```

## Operations dashboard

Serve the local real-time operations console:

```bash
polyflow dashboard --db logs/polyflow.db --log logs/immutable.jsonl
```

Then open `http://127.0.0.1:8643`.

The dashboard streams heartbeat, open positions, open orders, recent signals,
quickfire markets, source reliability, calibration/CLV summary, pinned reference
repo readiness, and immutable log tail via Server-Sent Events. The market scanner
and trade tape use real runtime state only; no mock/demo market rows are seeded.
Operator controls are safe intents only: they copy the exact command or policy
action to run, but they do not mutate live orders.

## Reference repo automation

The automation manifest is in `configs/policy.yaml` under `automation.sources`.
The same four repositories are tracked as pinned Git submodules under
`external/`, so local automation and GitHub review resolve the same commits:

```bash
polyflow automation-sources --config configs/policy.yaml --root .
```

| Source | Automation role | Local path / env override |
|---|---|---|
| `github.com/warproxxx/poly_data` | Historical trade data for backtests and wallet replay | `external/poly_data` or `POLYFLOW_POLY_DATA_PATH` |
| `github.com/Polymarket/polymarket-cli` | External market/order command surface | `external/polymarket-cli` or `POLYFLOW_POLYMARKET_CLI_PATH` |
| `github.com/Polymarket/agents` | Public-source agent/RAG framework reference | `external/agents` or `POLYFLOW_POLYMARKET_AGENTS_PATH` |
| `github.com/KaustubhPatange/polymarket-trade-engine` | 5-minute lifecycle, ticker, and simulation architecture reference | `external/polymarket-trade-engine` or `POLYFLOW_TRADE_ENGINE_PATH` |

The `reference_repo_monitor` subagent runs hourly by default, persists readiness
to SQLite, and writes an immutable audit record. Missing or drifted submodules
block source readiness. Optional binaries such as `polymarket` are warnings,
not live-trading permission. Live orders still remain governed by the normal
scanner, probability, Kelly, risk, formatter, hook, and logging gates.

## Learning status

POLYFLOW has measurement-driven learning primitives, not autonomous model
self-modification. Implemented:

- calibration buckets from resolved predictions
- source reliability updates with hit/miss and Brier increments
- closing-line value tracking
- replay tools for regression-testing policy changes against logged decisions
- promotion gates that require calibration and positive CLV before scale
- strategy automation logs for every analyzed market and candidate result
- wallet activity snapshots for trade analysis

Not implemented yet:

- automatic parameter retraining or model promotion
- online learning from live fills without human review
- autonomous whale-list refresh or news-embedding retraining

## Elite Trading Bot Protocol coverage

Modules added under the protocol's mandates:

| Section | Module(s) |
|---|---|
| §1 Data hygiene (3+ feeds, ns timestamps, tick filters, audit log) | `tick_pipeline.py`, `feed_health.py`, `tick_recorder.py` |
| §2 Reality-grade simulator (depth, FIFO, fees, gas) | `simulator.py` |
| §4 Expectancy / RTR / dynamic entry timing | `expectancy.py` |
| §5 Ghost mode (real wallet, 0 USDC) | `adapters/ghost_clob.py` |
| §7 Five-gate deployment workflow | `deployment_gates.py` |
| §8 Daily on-chain reconciliation | `reconciliation.py` + `polyflow reconcile` |

What's still operational time, not code:
- 30-day own-tick recording (run `tick_recorder` continuously; protocol blocks deploy until you have it)
- 72-hour ghost-mode soak (run the GhostCLOBAdapter for 72h before any capital moves)
- 7-day live dry-run at 0.1% bankroll
- VPS / RPC redundancy / latency to Polymarket contracts

The `replay` module also supports programmatic trade reconstruction for
calibration jobs and regression-testing policy changes.

## Deployment

### Docker

```
docker compose up -d
```

Services:
- `postgres` — applies `db/schema.sql` on first boot
- `polyflow` — runs the runtime container; reads credentials from `.env.local` (never baked in)
- exposes `:8642/healthz` and `:8642/readyz`

The runtime persists to `./logs/` (mounted volume) so the immutable JSONL log
survives container restarts. The `polyflow` container runs as UID 10001 and
re-uses the host's `configs/policy.yaml` read-only.

### Systemd / VPS

`deploy/polyflow.service` is a production-style systemd unit for a Linux VPS.
It expects the repo at `/opt/polyflow`, a virtualenv at `/opt/polyflow/.venv`,
and secrets in `/opt/polyflow/.env.local`.

```bash
sudo cp deploy/polyflow.service /etc/systemd/system/polyflow.service
sudo systemctl daemon-reload
sudo systemctl enable --now polyflow
sudo journalctl -u polyflow -f
```

Default service command runs analysis/paper mode with live public scanning. It
does not pass `--live-trading`.

## What's still out of scope

- WebSocket adapters (CLOB market channel + user channel) — scheduled remote agent in flight; REST polling only locally
- Spread-capture / market-making strategy — disabled until live maturity
- Trade Court approval workflow — dashboard observes and surfaces operator intents, but does not approve live orders
- Postgres adapter mirroring `SQLiteStore` — `db/schema.sql` is loaded by the docker-compose Postgres service; an async asyncpg-backed `PostgresStore` is a small follow-up
- Online retraining / autonomous parameter promotion — measurement exists; self-modification remains intentionally blocked
