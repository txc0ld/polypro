# Skill — `market_scanner`

**Cadence:** every 5 minutes (configurable via `subagents.market_scanner_minutes`).
**Implementation:** `polyflow.market_scanner` (`classify`, `scan`, `hard_skip_reasons`).
**PRD section:** §6, §14.1.

## Purpose

First refusal layer. Discover candidate Polymarket markets and reject everything
that fails a deterministic hard-filter check before any modeling runs.

## Inputs

A list of `Market` records from the Gamma adapter. Each must include:

- `id`, `event_id`, `question`, `category`, `close_time`, `resolution_rules`
- liquidity / volume / spread / depth metrics
- `yes_token_id`, `no_token_id`, `tick_size`, `min_order_size`, `fee_rate_bps`, `neg_risk`

If any of those fields are missing, the market is **skipped** with the
corresponding `MISSING_*` reason code — never silently defaulted.

## Hard skip rules (deterministic)

| Reason code | Trigger |
|---|---|
| `LIQUIDITY_BELOW_MIN` | `liquidity_usd < market_filters.min_liquidity_usd` |
| `VOLUME_BELOW_MIN` | `volume_24h_usd < market_filters.min_volume_24h_usd` |
| `SPREAD_TOO_WIDE` | `spread_pct > market_filters.max_spread_pct` |
| `DEPTH_TOO_THIN` | `depth_within_5c_usd < market_filters.min_depth_within_5c_usd` |
| `CLOSES_TOO_SOON` | `close_time - now < min_time_to_close_minutes` |
| `MISSING_TOKEN_IDS` | yes/no token IDs absent |
| `MISSING_TICK_SIZE` / `MISSING_FEE_RATE` / `MISSING_MIN_ORDER_SIZE` | required CLOB metadata absent |
| `AMBIGUOUS_RESOLUTION` | resolution rules empty or unparseable |
| `FORBIDDEN_CATEGORY` | category contains war / death / terror / assassination |
| `LOW_QUALITY_REVIEW` | passed hard filters but `market_quality < 0.70` (routed to `manual_only`) |

## Output (strict JSON)

```json
{
  "approved_markets": [{"market_id": "0x…", "question": "…"}],
  "manual_only_markets": [{"market_id": "0x…", "question": "…", "reasons": ["LOW_QUALITY_REVIEW"]}],
  "skipped_markets": [{"market_id": "0x…", "question": "…", "reasons": ["LIQUIDITY_BELOW_MIN"]}]
}
```

Any other shape is rejected by the runtime.

## Side effects

- Every classification is written to `immutable_log` via the trade logger
  (`actor=market_scanner`, `action=classify`).
- Approved markets feed the watchlist; skipped reasons feed scanner-board metrics.
