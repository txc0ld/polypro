# POLYFLOW Dashboard

A read-only Next.js 14 (App Router) view of the POLYFLOW runtime. Reads the
SQLite store and the immutable JSONL log produced by the Python runtime — it
never writes to either.

## Pages

| Path | PRD | Purpose |
|---|---|---|
| `/` | §19.1 | Live Desk — runtime telemetry, wallet value, active signals (last 30m), activity feed |
| `/scanner` | §19.2 | Scanner Board — watching markets grouped by category with bid/ask, time-to-close, quickfire score, strategy badges, and skip-reason histogram |
| `/probability/[market_id]` | §19.3 | Probability Lab — model-vs-price hero chart, gap, per-strategy source evidence, calibration bucket, resolution rules |
| `/portfolio` | §19.4 | Portfolio Sentinel — positions with size/avg/current/unrealized PnL/CLV, exposure vs caps, kill-switch, incident queue |
| `/trades/[signal_id]` | §19.5 | Trade Court — chronological CI/CD-style timeline: score → risk → format → place → fill → resolution |

A persistent **TopBar** appears on every page with: bot state pill (HEALTHY / DEGRADED / LOCKDOWN / KILLED), mode badge, heartbeat freshness, wallet balance, bankroll, daily PnL, open orders, and active markets count.

## Run

```bash
cd dashboard
npm install
npm run dev
```

Open <http://localhost:3000>.

The dashboard expects the runtime's `logs/` directory at the project root
(one level up from `dashboard/`). All three sources are optional — pages
degrade gracefully when files are missing:

- `logs/polyflow.db` — SQLite store written by `polyflow.persistence.SQLiteStore`.
- `logs/immutable.jsonl` — append-only log written by `polyflow.logger.ImmutableLogger`.
- `logs/heartbeat.json` — written by `polyflow.subagents.heartbeat.Heartbeat`.
- `configs/policy.yaml` — current policy, parsed at request time for `mode` and `bankroll_usdc`.
- `.env.local` (or `process.env`) — `POLY_FUNDER_ADDRESS` (proxy/Safe address) drives the wallet widget. The dashboard fetches `/value` and `/positions` from the public Polymarket Data API; no auth required.

Override paths with environment variables if needed:

```bash
POLYFLOW_DB=/abs/path/to/polyflow.db \
POLYFLOW_LOG=/abs/path/to/immutable.jsonl \
POLYFLOW_HEARTBEAT=/abs/path/to/heartbeat.json \
POLYFLOW_POLICY=/abs/path/to/policy.yaml \
npm run dev
```

## Build / lint

```bash
npm run build
npm run lint
```

## Tech notes

- Server components for all data fetching (the only client component is
  `components/ProbabilityChart.tsx`, which uses recharts).
- `better-sqlite3` opens the DB in `readonly` mode with `PRAGMA query_only`.
- `lib/log.ts` reads the JSONL with line-buffered streaming so the whole file
  is never loaded; pass a smaller `limit` to `tailLog` for cheaper queries.
- No auth: v1 is intended for local / private network use.
