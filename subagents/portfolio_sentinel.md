# Subagent — `portfolio_sentinel`

**Cadence:** every 30s (configurable via `subagents.portfolio_sentinel_seconds`).
**PRD section:** §16.3, §10.5.

## Purpose

Final authority on portfolio safety. Watches positions, open orders, exposure
buckets, and venue / data-source health 24/7. Triggers cancel / flatten /
kill-switch on any breach.

## Each tick

1. Pull positions and open orders from CLOB (`get_positions`).
2. Recompute exposure per market / event / category and per-day P&L.
3. Run `polyflow.post_order_hook.evaluate_exposure`. Any `KillSwitch` raised
   here halts the runtime and pages the operator.
4. Check liveness:
   - CLOB user-channel last-event timestamp younger than 90s
   - market-data WS last-tick younger than 30s for active positions
   - wallet on-chain balance reconciles with internal state within tolerance
5. Detect stuck orders: any open order older than `max_age_minutes` (default 5)
   on a fast-moving market triggers a cancel + log entry.
6. On data-source staleness, contradiction, or unauthorized config mutation:
   trip kill switch (PRD §10.5).

## Outputs

- one log entry per tick with the exposure snapshot (`actor=portfolio_sentinel`,
  `action=tick`)
- separate entries for each detected breach, stuck order, or kill event
- alert payload to the operator side channel (Discord/Telegram/email) when a
  kill condition fires
