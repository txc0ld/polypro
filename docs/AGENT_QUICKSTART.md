# POLYFLOW Agent Quick Start

This is the fastest way for an agent to understand the program before making
changes. Read this before editing strategy, runtime, order, or dashboard code.

## Mission

POLYFLOW is a 24/7 Polymarket automation runtime for daily/quickfire markets.
It scans public markets, admits only liquid near-term candidates, analyzes
public evidence, creates strategy signals, and routes every candidate through
strict risk and order gates.

Prime directive: survive first, trade second, scale last.

## Non-Negotiable Rules

Never bypass these gates:

1. Market Scanner approves the market.
2. Probability engine emits a valid probability with uncertainty.
3. Signal arbiter scores the signal.
4. Kelly/risk governor approves size and exposure.
5. CLOB formatter validates token ID, tick size, min size, fee rate, and caps.
6. CLOB adapter submits only a validated order payload.
7. Post-order exposure hook runs.
8. Immutable log records the full path.

Use public information only. Do not add private, leaked, stolen, insider, or
outcome-influencing sources. Do not implement spoofing, wash trading,
self-dealing, fake liquidity, or manipulation.

## Core Flow

```text
Gamma + CLOB public reads
  -> market_scanner
  -> SQLite watchlist
  -> strategy_automation
  -> strategy probability estimate + Signal
  -> signal_arbiter
  -> risk_governor
  -> clob_order_formatter
  -> CLOB adapter
  -> post_order_kelly_guard
  -> immutable JSONL log + dashboard
```

## Key Files

| Area | Files |
|---|---|
| Policy/config | `configs/policy.yaml`, `src/polyflow/config.py` |
| Runtime scheduler | `src/polyflow/runtime.py`, `src/polyflow/subagents/scheduler.py` |
| Daily market scanner | `src/polyflow/market_scanner.py` |
| 24/7 strategy automation | `src/polyflow/subagents/strategy_automation.py` |
| Strategies | `src/polyflow/strategies/*.py` |
| Risk and sizing | `src/polyflow/risk_governor.py`, `src/polyflow/kelly.py` |
| Order validation | `src/polyflow/order_formatter.py`, `src/polyflow/order_signing.py` |
| CLOB adapters | `src/polyflow/adapters/polymarket_clob_read.py`, `src/polyflow/adapters/polymarket_clob_trade.py` |
| News and anchors | `src/polyflow/adapters/news.py`, `src/polyflow/adapters/anchors.py` |
| Persistence | `src/polyflow/persistence/sqlite_store.py` |
| Dashboard | `src/polyflow/dashboard.py`, `src/polyflow/dashboard_assets.py` |
| Ops service | `deploy/polyflow.service` |

## Runtime Modes

| Mode | Meaning |
|---|---|
| `observe` | Analyze and score only; no order placement |
| `paper` | Simulated orders/fills |
| `live_confirm` | Human confirmation layer |
| `live_tiny` | Autonomous with strict caps |
| `live_standard` | Autonomous only after promotion gates |
| `lockdown` | No new orders |

Live order placement also requires both:

1. `automation.allow_order_placement: true`
2. `polyflow run --live-trading`

If either is missing, live placement must not happen.

## Daily Quickfire Policy

The scanner is intentionally daily-market focused:

```yaml
market_filters:
  min_liquidity_usd: 100000
  min_volume_24h_usd: 25000
  max_spread_pct: 5
  min_depth_within_5c_usd: 10000
  min_time_to_close_minutes: 60
  max_time_to_close_minutes: 2160
```

`quickfire_score` ranks admitted markets by close window, volume, liquidity,
spread, depth, and strategy coverage. Long-horizon markets should not appear
as active trade candidates.

## Commands Agents Should Know

Install:

```bash
python -m venv .venv
. .venv/Scripts/activate
pip install -e ".[dev,trade]"
```

Run the safe 24/7 automation loop:

```bash
polyflow run --config configs/policy.yaml --log logs/immutable.jsonl --db logs/polyflow.db --live-scanner --gamma-limit 120
```

Run one live public scanner tick:

```bash
polyflow scan-once --config configs/policy.yaml --log logs/immutable.jsonl --db logs/polyflow.db --live --gamma-limit 120
```

Serve the dashboard:

```bash
polyflow dashboard --db logs/polyflow.db --log logs/immutable.jsonl
```

Check credentials without leaking secrets:

```bash
polyflow creds-check
```

Run tests:

```bash
PYTHONPATH=src pytest -s
```

## Strategy Work Rules

When adding or changing a strategy:

1. Strategy must return `(ProbabilityEstimate, Signal)` or `None`.
2. It must refuse stale, ambiguous, low-confidence, or non-public evidence.
3. It must set `evidence_refs` and `reason_codes`.
4. It must respect `policy.kelly.max_model_uncertainty`.
5. It must not place orders directly.
6. Add targeted tests for approval and refusal paths.

## Dashboard Work Rules

The dashboard observes only. It must not place, cancel, or approve orders.
It should render real state from SQLite/logs/SSE only. Do not add dummy,
sample, seeded, or mock market/trade rows to production dashboard assets.

## Current Learning Boundary

Implemented:

- calibration buckets
- source reliability rows
- closing-line value tracking
- immutable replay and trade reconstruction
- strategy automation logs
- wallet activity snapshots

Not implemented intentionally:

- autonomous parameter retraining
- model self-modification
- automatic promotion to larger size
- autonomous whale-list refresh

## Safe Change Checklist

Before finalizing any change:

1. `git status -sb`
2. Run targeted tests for touched modules.
3. Run full `PYTHONPATH=src pytest -s` for runtime/order/strategy changes.
4. Run `ruff check` on touched Python files.
5. For dashboard changes, check `/dashboard.js` with `node --check` and run a browser screenshot test.
6. Confirm no secrets or `.env.local` content were committed.

Key principle: strategies may discover edge, but only the runtime gates are
allowed to turn edge into orders.
