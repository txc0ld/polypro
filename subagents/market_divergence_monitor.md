# Subagent — `market_divergence_monitor`

**Cadence:** every 60s (configurable via `subagents.market_divergence_monitor_seconds`).
**PRD section:** §16.1, §9.2.

## Purpose

For each approved market in the watchlist, compare the Polymarket executable
price against credible *external* probability anchors (sportsbook odds with vig
removed, Kalshi quotes, liquid exchange spot, polling forecasts, public
forecast benchmarks). Emit a candidate `Signal` only when the divergence
survives liquidity, fee, slippage, and resolution-mismatch adjustments.

## Process

1. Pull the latest CLOB best-bid / best-ask for the market.
2. Map the market to its equivalent external event using a stored mapping table
   (built once per market by the operator; never auto-inferred for live
   trading).
3. Fetch the latest external odds; reject if older than 30s for liquid sources.
4. Strip vig with `polyflow.probability.remove_vig`.
5. Adjust for any settlement-definition mismatch; if the mismatch is material,
   reject and log `SETTLEMENT_DEFINITION_MISMATCH`.
6. Compute `effective_edge`; reject if below `kelly.min_effective_edge`.
7. Emit a `Signal` with `strategy="external_odds_divergence"` and the source
   evidence refs.

## Refusal reasons

`STALE_EXTERNAL_ODDS`, `MAPPING_MISSING`, `SETTLEMENT_DEFINITION_MISMATCH`,
`LOW_SOURCE_CONFIDENCE`, `LIQUIDITY_BELOW_MIN`, `EDGE_BELOW_MIN`.

## Side effects

Every accepted signal is logged with `actor="market_divergence_monitor"` and
the full evidence pack. Refusals are logged too, with reason codes — the
calibration job uses both for false-positive / false-negative analysis.
