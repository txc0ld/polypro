# POLYFLOW

Autonomous Polymarket trading runtime. See `POLYFLOW_POLYMARKET_PRD.md` for the full spec.

## Layout

```
src/polyflow/                  deterministic core
src/polyflow/strategies/       probability producers (external odds, news)
src/polyflow/adapters/         Polymarket Gamma / CLOB read / CLOB trade / Data API + stubs
src/polyflow/persistence/      SQLite store
src/polyflow/subagents/        async cadence scheduler + heartbeat + sentinel
skills/  hooks/  subagents/    operational contracts (markdown)
configs/policy.yaml            live policy
db/schema.sql                  PostgreSQL schema
tests/                         165 unit + e2e tests (no live network calls)
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
polyflow scan-once          Single scanner tick — useful for inspection
polyflow show-policy        Echo parsed policy + config hash
polyflow status             Heartbeat + tail of immutable log
polyflow calibrate          Compute Brier / log-loss / bucket calibration
polyflow promotion-check    LIVE_TINY -> LIVE_STANDARD gate evaluator
polyflow creds-check        Redacted credential summary
polyflow derive-creds       Sign ClobAuth + POST /auth/api-key to derive secret + passphrase
polyflow positions          Read live wallet positions from the Data API
```

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
watched markets, source reliability, calibration/CLV summary, and immutable log
tail via Server-Sent Events. Operator controls are safe intents only: they copy
the exact command or policy action to run, but they do not mutate live orders.

## Learning status

POLYFLOW has measurement-driven learning primitives, not autonomous model
self-modification. Implemented:

- calibration buckets from resolved predictions
- source reliability updates with hit/miss and Brier increments
- closing-line value tracking
- replay tools for regression-testing policy changes against logged decisions
- promotion gates that require calibration and positive CLV before scale

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

## What's still out of scope

- WebSocket adapters (CLOB market channel + user channel) — scheduled remote agent in flight; REST polling only locally
- Spread-capture / market-making strategy — disabled until live maturity
- Trade Court approval workflow — dashboard observes and surfaces operator intents, but does not approve live orders
- Postgres adapter mirroring `SQLiteStore` — `db/schema.sql` is loaded by the docker-compose Postgres service; an async asyncpg-backed `PostgresStore` is a small follow-up
- Resolution monitor wiring — module + tests exist; needs an entry in the runtime's subagent scheduler once the live Gamma adapter is wired in
