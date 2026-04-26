# POLYFLOW Dashboard

Read-only Next.js 14 (App Router) operator console for the POLYFLOW Polymarket
runtime. Implements the five views from PRD §19:

| Route                           | PRD section | What it shows |
|---------------------------------|-------------|---------------|
| `/`                             | §19.1       | Live Desk: mode, heartbeat, bankroll, open positions/orders, daily PnL, kill-switch state, latest 10 immutable-log entries. |
| `/scanner`                      | §19.2       | Markets grouped by status, skip-reason histogram, quality-score distribution. |
| `/probability/[market_id]`      | §19.3       | Model probability vs market price (recharts), confidence bands, source evidence, calibration bucket. |
| `/portfolio`                    | §19.4       | Per-market / event / category exposure vs caps, Kelly usage, drawdown, stuck orders, incident queue. |
| `/trades/[signal_id]`           | §19.5       | One reconstructed trade: rule, model p, market price, edge, sources, Kelly size, order payload, fills, post-order hook, exit plan placeholder, final result, Brier impact. |

The top nav also surfaces the latest system state (`HEALTHY` / `DEGRADED` /
`LOCKDOWN` / `KILLED` / `UNKNOWN`) read from the most recent `kill_switch`,
`portfolio_sentinel`, or `runtime` entry in the immutable log.

## Run

```bash
cd dashboard
npm install
npm run dev          # http://localhost:3000
npm run build        # production build
npm run lint
```

The dashboard expects the runtime's `logs/` directory at the **project root**
(i.e. one level above `dashboard/`). Defaults:

| Env var               | Default                          |
|-----------------------|----------------------------------|
| `POLYFLOW_DB`         | `../logs/polyflow.db`            |
| `POLYFLOW_LOG`        | `../logs/immutable.jsonl`        |
| `POLYFLOW_HEARTBEAT`  | `../logs/heartbeat.json`         |
| `POLYFLOW_POLICY`     | `../configs/policy.yaml`         |

If a file is missing the page renders an empty-state panel rather than
erroring — useful before the runtime has been started.

## Architecture

- **Server components** for all data reads. The dashboard never holds long-
  lived connections; `better-sqlite3` opens the DB readonly and the JSONL is
  streamed line-by-line (no whole-file loads).
- **Client components** only where interactive: the recharts probability chart
  in `components/ProbabilityChart.tsx`.
- **No state library**, no auth, no writes. v1 is intentionally read-only —
  any kill-switch / pause action stays on the CLI for now (PRD §13).
- **Dependencies kept minimal**: `next`, `react`, `react-dom`, `tailwindcss`,
  `better-sqlite3`, `recharts` (+ types and lint plumbing).

## Notes on data source coupling

The dashboard reads — but never writes to — the same SQLite tables and JSONL
record shape produced by:

- `src/polyflow/persistence/sqlite_store.py` (markets, outcome_tokens,
  signals, positions, resolutions, calibration_observations)
- `src/polyflow/logger.py` (immutable JSONL: `{id, ts, actor, action,
  market_id, event_id, input_hash, output_hash, config_hash, code_version,
  payload}`).

If you change either of those, also update `lib/db.ts` / `lib/log.ts`.
