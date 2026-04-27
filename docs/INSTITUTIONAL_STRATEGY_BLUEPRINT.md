# POLYFLOW Institutional Strategy Blueprint

Research date: 2026-04-27  
Operating rule: survive first, trade second, scale last.

This document upgrades POLYFLOW from "find mispricings" to a trading-desk style strategy stack. It does not authorize live orders by itself. Every candidate still must pass `market_scanner`, `probability`, `kelly`, `risk_governor`, `order_formatter`, post-order hooks, and immutable logging.

## Current Public Mechanics That Matter

Sources checked:

| Source | Relevant constraint |
|---|---|
| Polymarket API introduction: https://docs.polymarket.com/api-reference/introduction | Gamma discovers markets, Data API reads activity/positions, CLOB handles orderbooks and trading. Gamma and Data are public; CLOB trading endpoints require auth. |
| Polymarket market data overview: https://docs.polymarket.com/market-data/overview | Events can contain multiple binary markets; each market maps to YES/NO CLOB token IDs. `enableOrderBook` decides CLOB tradability. |
| Polymarket orderbook docs: https://docs.polymarket.com/trading/orderbook | Orderbooks expose `min_order_size`, `tick_size`, `neg_risk`, best bid/ask, book hash, and WebSocket events including `tick_size_change`, `best_bid_ask`, and `market_resolved`. |
| Polymarket market-maker trading docs: https://docs.polymarket.com/market-makers/trading | Market makers should quote around fair value, manage inventory, cancel stale quotes, use WebSockets, validate prices, and use kill switches. |
| Polymarket fees docs: https://docs.polymarket.com/trading/fees | Makers are not charged fees. Taker fees are dynamic by market and applied at match time with `fee = C * feeRate * p * (1 - p)`. |
| Polymarket CLOB V2 migration: https://docs.polymarket.com/v2-migration | `getClobMarketInfo(conditionID)` returns minimum tick, minimum order size, fee details, tokens, and RFQ status. Fee rate is no longer embedded in signed orders. |
| Polymarket negative-risk docs: https://docs.polymarket.com/advanced/neg-risk | Neg-risk events allow conversion relationships across mutually exclusive outcomes. Augmented neg-risk requires ignoring unnamed placeholders and treating `Other` carefully. |
| Polymarket liquidity rewards docs: https://docs.polymarket.com/market-makers/liquidity-rewards | Rewards favor resting liquidity, two-sided depth, tight quotes, and eligible size/spread. April 2026 incentives are concentrated in sports and esports. |
| Arbitrage in Prediction Markets paper: https://arxiv.org/abs/2508.03474 | Related outcome sets should sum to 1, but empirical mispricings exist; scalable detection requires grouping related markets and validating exhaustiveness/mutual exclusivity. |
| poly_data: https://github.com/warproxxx/poly_data | Historical market, Goldsky order-filled, and processed trade CSV pipeline for backtests and wallet replay. Pinned in `configs/policy.yaml` at `b7c1d1703d6a3d1dfaa5f49c9ef7b4b899775392`. |
| Polymarket CLI: https://github.com/Polymarket/polymarket-cli | Official Rust CLI exposing market scans, CLOB reads, and authenticated order commands with JSON output. Pinned at `4b5a749d5bf04f23611544a059e2a15c7281ae83`. |
| Polymarket agents: https://github.com/Polymarket/agents | Python agent framework reference for public-source reasoning, RAG, Gamma access, and LLM tool contracts. Pinned at `081f2b5594c37edeb9d3780a778c084d5b6f2743`. |
| polymarket-trade-engine: https://github.com/KaustubhPatange/polymarket-trade-engine | 5-minute lifecycle, orderbook tracker, ticker, wallet tracker, and simulation patterns. Pinned at `b941451fb2a65cfc721c73bdc92e0a3e4b7c9a4f`. |
| Practical Polymarket/BTC 5-minute guide: https://github.com/KaustubhPatange/polymarket-trade-engine/blob/master/docs/LEARNING.md | Useful mechanics summary for CLOB fills, BTC threshold markets, buy-side fee effects on net received shares, CTF mint/redeem, and oracle-resolution differences. |

## Opinionated Priority

Do this first: build passive fair-value quoting on markets with high-quality external anchors, then upgrade negative-risk basket detection. These edges use the CLOB structure itself, avoid taker fees when resting, and fit POLYFLOW's existing risk rails better than chasing public news with aggressive orders.

| Rank | Strategy | Why it ranks here | Repo fit |
|---:|---|---|---|
| 1 | Anchored passive fair-value quoting | Maker fees are zero, reward programs subsidize some markets, and external anchors provide a defensible fair value. | New `src/polyflow/strategies/passive_fair_value_quoting.py`; reuse `external_odds_divergence.py`, `order_formatter.py`, `risk_governor.py`. |
| 2 | Complete negative-risk basket arbitrage | Best theoretical edge when complete baskets are genuinely exhaustive, executable, and convertible. | Upgrade `src/polyflow/strategies/negative_risk.py` from research-only to paper-traded basket order plans. |
| 3 | Cross-venue probability divergence | Already implemented, but should become ensemble-calibrated instead of single-anchor weighted average. | Extend `src/polyflow/strategies/external_odds_divergence.py` and `src/polyflow/source_reliability.py`. |
| 4 | Public-data repricing | Can work around scheduled data releases, injuries, lineups, crypto thresholds, weather, and polling, but stale/false signals are common. | Existing `src/polyflow/strategies/news_repricing.py`. |
| 5 | BTC short-horizon threshold specialist | High-feedback market class, but only viable with WebSocket, oracle-aware modeling, and strict latency controls. | New `src/polyflow/strategies/btc_threshold.py`; reuse `tick_pipeline.py`, `simulator.py`, and `clv.py`. |
| 6 | Four-layer alignment | Requires order-book depth, public wallet movement, news-to-price lag, and position delta convergence. Powerful only after clean snapshot infrastructure exists. | New `src/polyflow/strategies/four_layer_alignment.py`; observe/paper only until 30-day simulation proves +EV. |
| 7 | Closing-line value accumulation | Treat CLV as the primary learning metric before scaling bankroll. | Existing `src/polyflow/clv.py`, `tests/test_clv.py`, `src/polyflow/promotion.py`. |
| 8 | Pure orderbook microstructure | Lowest priority until WebSocket capture and tick replay are stable. Thin books create false positives. | Needs `tick_recorder.py`, `tick_pipeline.py`, replay tests, and adverse-selection metrics. |

## The 100x Upgrade

"100x" should mean 100x stricter evidence density, not 100x larger size. The institutional edge is a multi-layer refusal engine:

1. Refuse bad markets before modeling.
2. Use public, timestamped, reproducible evidence only.
3. Estimate fair value with calibrated ensembles, not one LLM answer.
4. Trade passively unless the edge survives taker fees, spread, slippage, stale-book risk, and resolution risk.
5. Scale only after observed CLV and calibration remain positive out of sample.

## Strategy 1: Anchored Passive Fair-Value Quoting

Objective: earn spread and rewards while only quoting where POLYFLOW has a calibrated public fair value.

Entry universe:

| Gate | Requirement |
|---|---|
| Market quality | Pass `src/polyflow/market_scanner.py` with high liquidity, narrow spread, low resolution risk, known token IDs, known tick size, and known min order size. |
| Data quality | At least two independent public anchors, or one very high-quality regulated/official anchor plus strong historical calibration. |
| Fee posture | Prefer maker quotes. Use taker orders only when `edge_after_costs >= 2 * policy.kelly.min_effective_edge`. |
| Event risk | No unresolved rule ambiguity, no insider/influencer risk, no market whose outcome can be affected by the trader. |
| Execution | Quote must be inside allowed tick size and small enough to cancel without moving the book. |

Fair value:

```text
q_fair = weighted_median(anchor_probabilities)
weight_i = reliability_i * freshness_i * settlement_match_i * calibration_i
sigma = max(source_disagreement, calibration_rmse, stale_penalty, resolution_risk / 2)
```

Quote logic:

```text
reservation_bid = q_fair - sigma - inventory_skew - catalyst_risk
reservation_ask = q_fair + sigma - inventory_skew + catalyst_risk

place_bid if best_bid < reservation_bid and quote_size <= risk_headroom
place_ask only reduce-only unless inventory exists
cancel if abs(mid - q_fair) > stale_threshold or tick_size changes
```

Implementation:

| File | Change |
|---|---|
| `src/polyflow/types.py` | Add strategy enum `PASSIVE_FAIR_VALUE_QUOTING` only after tests are added. |
| `src/polyflow/strategies/passive_fair_value_quoting.py` | Emit quote intents, not immediate marketable orders. |
| `src/polyflow/order_formatter.py` | Support GTD expiration when the adapter supports it; current `OrderType` lacks GTD. |
| `src/polyflow/probability.py` | Replace approximate fee impact with CLOB V2 fee model for taker simulations; maker fee should be zero. |
| `src/polyflow/tick_pipeline.py` | Subscribe to `best_bid_ask`, `tick_size_change`, and `market_resolved`; cancel stale quotes on any invalidating event. |

## Strategy 2: Complete Negative-Risk Basket Arbitrage

Objective: buy or convert related outcomes where a complete mutually exclusive set is executable below guaranteed payout after all costs.

Entry universe:

| Gate | Requirement |
|---|---|
| Completeness | Event markets must be exhaustive and mutually exclusive. |
| Neg-risk metadata | `negRisk` true from Gamma/CLOB metadata and `neg_risk: true` used in order options. |
| Augmented neg-risk | Ignore unnamed placeholders. Do not trade `Other` unless the rules are stable and the residual definition is explicitly understood. |
| Executability | Every leg has depth at or below target ask, valid tick size, min size, and enough inventory/USDC. |
| Atomicity | In live mode, no leg is submitted unless the basket can be completed or unwound inside worst-case limits. |

Basket math:

```text
complete_yes_cost = sum(executable_yes_ask_i + taker_fee_i + slippage_i)
guaranteed_edge = 1.00 - complete_yes_cost
trade if guaranteed_edge >= max(0.01, 3 * expected_slippage_error)
```

Implementation:

| File | Change |
|---|---|
| `src/polyflow/strategies/negative_risk.py` | Add depth-aware executable cost, not just top ask. |
| `src/polyflow/strategies/negative_risk.py` | Add augmented-neg-risk refusal reasons: `PLACEHOLDER_OUTCOME`, `OTHER_DEFINITION_UNSTABLE`, `INCOMPLETE_OUTCOME_SET`. |
| `src/polyflow/risk_governor.py` | Add basket-level exposure approval instead of per-leg approval only. |
| `src/polyflow/order_formatter.py` | Format a basket plan with all legs and shared `basket_id`; submit only through a basket executor that can fail closed. |

## Strategy 3: Cross-Venue Probability Divergence

Objective: buy when Polymarket executable price is materially away from a public external fair probability.

Upgrade the current implementation:

| Current file | Upgrade |
|---|---|
| `src/polyflow/strategies/external_odds_divergence.py` | Require settlement-rule mapping per anchor, not just `settlement_match: bool`. |
| `src/polyflow/probability.py` | Compute side-specific executable price from full book depth. |
| `src/polyflow/source_reliability.py` | Track realized Brier/log loss by source category and event type. |
| `tests/test_external_odds_divergence.py` | Add stale-anchor, mismatched settlement, and adverse-fill tests. |

Entry formula:

```text
edge = side_probability - executable_price
cost = spread_cross + expected_slippage + taker_fee + resolution_buffer + uncertainty_buffer
trade if edge - cost >= min_effective_edge and CLV history for this source/event class is positive
```

Use cases:

| Domain | Public anchors |
|---|---|
| Sports | Regulated sportsbook consensus, exchange odds, official injury/lineup feeds. |
| Crypto | Liquid spot/perp prices, options-implied probabilities, exchange status pages. |
| Finance/economics | Official release calendars, futures/ETF prices, FedWatch-style public tools. |
| Weather | Official meteorological feeds and station-level observations. |

## Strategy 4: Public-Data Repricing

Objective: react to public information faster than the Polymarket midpoint while avoiding rumor and insider traps.

Trade only after:

| Gate | Requirement |
|---|---|
| Source integrity | No leaked, non-public, confidential, or outcome-influencer source. |
| Confirmation | Major deltas need at least two independent public sources or one primary official source. |
| Directionality | The event maps directly to market resolution language. |
| Freshness | Evidence timestamp is recent enough for the market type. |
| Market reaction | The orderbook has not already repriced beyond fair value. |

Best targets:

| Target | Why |
|---|---|
| Scheduled official releases | Timestamped, public, machine-readable. |
| Sports lineups/injuries | Strong external odds anchors can verify probability move. |
| Weather nowcasts | Public station data can move near-expiry markets. |
| Crypto threshold markets | Public exchange prices provide continuous anchor. |

Avoid:

| Market type | Reason |
|---|---|
| Ambiguous political/personality markets | Resolution language and insider risk dominate. |
| Low-liquidity viral news markets | Spread and stale quotes erase edge. |
| Markets where one actor can influence outcome | Integrity refusal. |

## Strategy 5: BTC Short-Horizon Threshold Specialist

Objective: trade BTC 5-minute UP/DOWN markets only when a live public price/oracle model materially disagrees with the executable Polymarket price.

This is not the first live strategy. It should run in observe/paper until the runtime has reliable WebSocket orderbooks, BTC reference-price capture, exchange-price feeds, and resolution reconciliation. The edge decays in seconds, so a slow bot is just paying spread and adverse selection.

Probability model:

```text
gap = btc_spot_now - price_to_beat
tau = seconds_to_resolution / 31_536_000
sigma = short_horizon_realized_volatility

q_up = NormalCDF((ln(btc_spot_now / price_to_beat) + drift_adjustment * tau) / (sigma * sqrt(tau)))
q_up = blend(q_up, orderflow_adjusted_q, oracle_latency_adjusted_q)
uncertainty = max(feed_disagreement, oracle_latency_penalty, volatility_regime_error)
```

Entry gates:

| Gate | Requirement |
|---|---|
| Reference integrity | Capture the market's `price_to_beat` from a public market field or deterministic parser and store it in the evidence pack. |
| Feed agreement | BTC spot feeds must agree inside a tight bps threshold; reject on exchange outage or stale tick. |
| Oracle mapping | Confirm the settlement source for the market class and include resolution-source risk in uncertainty. |
| Time window | Refuse very late entries unless the book has enough depth and the edge survives worst-case close slippage. |
| Spread/depth | Use full book depth, not top-of-book only. |
| Post-fee balance | For taker buys, reduce expected token balance by fee-in-shares before any reduce-only sell simulation. |

Implementation:

| File | Change |
|---|---|
| `src/polyflow/strategies/btc_threshold.py` | Add model output for UP/DOWN threshold markets with `price_to_beat`, `gap`, `tau`, `sigma`, and feed evidence. |
| `src/polyflow/probability.py` | Add short-horizon volatility/uncertainty helpers and correct taker fee treatment. |
| `src/polyflow/simulator.py` | Simulate 5-minute markets at tick level with resolution outcome and post-fee balances. |
| `src/polyflow/reconciliation.py` | Compare expected resolution with actual final settled outcome for oracle/rule drift. |
| `tests/test_btc_threshold.py` | Cover near-expiry refusal, stale BTC feed refusal, fee-adjusted balance, and full-depth slippage. |

Best use:

| Mode | Rule |
|---|---|
| Observe | Always on, no orders. Build calibration by time-to-expiry bucket. |
| Paper | Only when WebSocket book and BTC feed are both healthy. |
| Live tiny | Only after positive paper CLV and zero resolution mismatches. |

## Strategy 6: CLV-First Learning Loop

## Strategy 6: Four-Layer Alignment

Objective: emit a signal only when at least three independent public layers converge in the same direction inside one 10-minute window.

Implemented as `src/polyflow/strategies/four_layer_alignment.py`. It expects cleaned, timestamped signals from the snapshot engine; raw scraping, private sources, leaderboard worship, and trap-wallet copying are explicitly outside this strategy.

Required layers:

| Layer | Acceptance rule |
|---|---|
| Order-book depth | Depth ratio flip must be at least 2.5x and volume-confirmed. |
| Wallet conviction | Wallet must meet accuracy/resolved-market/PnL/delta gates and must not be trap-flagged. |
| News-to-price lag | Public headline must be 2-15 minutes old and price must have moved less than 60% toward fair value. |
| Position delta | Requires meaningful size delta plus adding against adverse price or a full flip. |

Cycle hygiene:

| Gate | Refusal |
|---|---|
| Feed latency | Reject cycle above 120 ms. |
| Wallet universe | Reject unless the cleaned wallet universe contains exactly 200 tracked wallets. |
| Snapshot integrity | Reject stale or out-of-sequence cycles. |
| Book jump | Reject order-book jumps above 12% unless on-chain flow confirms. |

Minimum directional edge:

```text
early-cycle edge >= 18%
late-cycle edge >= 25%
aligned layers >= 3
```

This strategy is not a live execution permission. It must still pass probability uncertainty, Kelly sizing, Risk Governor, order formatting, post-order hooks, and immutable logging.

## Strategy 7: CLV-First Learning Loop

Objective: scale only strategies that beat the closing line before they produce realized PnL.

Metrics:

| Metric | Definition | Promotion use |
|---|---|---|
| Brier score | Mean squared probability error. | Must improve against market midpoint baseline. |
| Log loss | Penalizes overconfidence. | Blocks scale if forecasts are sharp but wrong. |
| Expected calibration error | Bucketed forecast accuracy gap. | Drives uncertainty inflation. |
| CLV at 1h/6h/close | Signed move from fill price toward later market price. | Main early edge proof. |
| Adverse selection | Fill followed by immediate price move against us. | Shrinks quote size or disables market making. |
| Fill quality | Filled price versus intended executable price. | Feeds execution-cost model. |
| Reward-adjusted PnL | PnL plus maker rewards minus fees/slippage. | Only mature metric for reward markets. |

Promotion rule:

```text
OBSERVE -> PAPER:
  500+ scored signals, positive simulated CLV, no source-integrity violations

PAPER -> LIVE_TINY:
  positive out-of-sample CLV, Brier beats midpoint baseline, max drawdown within policy

LIVE_TINY -> LIVE_STANDARD:
  30+ days, positive realized reward-adjusted PnL, positive CLV, no unresolved incidents
```

## Required Engineering Fixes Before Scaling

| Priority | Fix | Why |
|---:|---|---|
| P0 | Update fee modeling in `src/polyflow/probability.py` for CLOB V2. | Current `fee_rate_bps * price` approximation does not match public fee docs and can overstate or understate taker cost. |
| P0 | Simulate buy-side taker fees as reduced net shares and sell-side taker fees as reduced proceeds. | Reduce-only sells can fail if the bot assumes gross bought shares instead of post-fee token balance. |
| P0 | Wire WebSocket book/tick events into cancellation logic. | Polymarket docs identify `tick_size_change` as critical; stale tick size causes order rejection. |
| P0 | Keep spread-capture disabled for live until reduce-only SELL and cancel-all behavior are tested against live-like fills. | Market making without fast cancels is adverse-selection bait. |
| P1 | Convert `negative_risk.py` from top-of-book research to full-depth basket simulation. | Complete baskets require every leg to be executable, not just attractive at the first ask. |
| P1 | Add source-level calibration tables keyed by source, market category, and horizon. | Static reliability is not institutional. |
| P1 | Add evidence packs for every signal with source URL, hash, timestamp, parser version, and settlement-rule mapping. | Reproducibility is the desk audit trail. |
| P2 | Add GTD order type once adapter support is complete. | Quotes should auto-expire before catalysts and market close. |

## Reference Repo Automation

POLYFLOW now treats the four external repos as pinned automation inputs rather
than code to import directly. The `reference_repo_monitor` subagent checks
local materialization, required files, optional command availability, and pinned
commit drift, then persists results to SQLite for the operations dashboard.

| Repo | Automation input | Readiness checks |
|---|---|---|
| `warproxxx/poly_data` | Backtest and wallet-replay data source | `update_all.py`, `update_utils/process_live.py`, `poly_utils/utils.py`, pinned commit |
| `Polymarket/polymarket-cli` | Scan/order command reference | `Cargo.toml`, CLOB/market command modules, `polymarket` command availability, pinned commit |
| `Polymarket/agents` | Agent/RAG reference surface | trade application, Gamma connector, object models, pinned commit |
| `KaustubhPatange/polymarket-trade-engine` | 5-minute engine architecture | lifecycle, simulation, orderbook tracker files, pinned commit |

| Risk | Likelihood | Mitigation |
|---|---|---|
| Upstream behavior changes after this audit | High | Pin commits in policy and emit `PIN_MISMATCH` until reviewed. |
| Local clone missing or stale | Medium | Dashboard and `polyflow automation-sources` surface `LOCAL_SOURCE_NOT_FOUND` or commit drift before automation consumes it. |
| External CLI accidentally bypasses POLYFLOW gates | Medium | Treat CLI as an inspected command surface; live orders still pass POLYFLOW scanner, risk, formatter, hook, and immutable log gates. |

## Candidate Trade JSON Contract

No strategy may emit free text into execution. The strategy layer should emit this shape, then downstream deterministic modules decide approval:

```json
{
  "market_id": "string",
  "event_id": "string|null",
  "strategy": "external_odds_divergence",
  "side": "BUY",
  "outcome": "YES",
  "token_id": "string",
  "market_price": 0.42,
  "model_probability": 0.49,
  "uncertainty": 0.04,
  "effective_edge": 0.031,
  "evidence_refs": ["source:url:hash"],
  "reason_codes": ["PUBLIC_ANCHOR_MATCHED", "CLV_CLASS_POSITIVE"],
  "expires_at": "2026-04-27T12:00:00Z"
}
```

## Risk Register

| Risk | Likelihood | Mitigation |
|---|---|---|
| Model overconfidence | High | Inflate uncertainty from calibration error, source disagreement, and resolution risk; cap Kelly at tiny fractions. |
| Stale public data | High | Timestamp every source; reject anchors outside event-specific freshness windows. |
| CLOB tick/min-size change | Medium | Subscribe to WebSocket `tick_size_change`; cancel and reformat quotes immediately. |
| Fee model drift | Medium | Query CLOB market info and simulate taker fees with `fee = C * feeRate * p * (1 - p)`. |
| False neg-risk completeness | Medium | Require event-level outcome set validation and refuse augmented placeholders/unstable `Other`. |
| Adverse selection on passive quotes | High | Use GTD/cancel-on-news, small quote sizes, inventory skew, and fill-following price movement metrics. |
| Manipulation or wash-trading contamination | Medium | Ignore suspicious prints; rely on orderbook depth, public external anchors, and Data API wallet/activity checks where legally and ethically allowed. |
| Resolution ambiguity | High | Market scanner should score down ambiguous rules and hard-reject poor-resolution markets. |
| Correlated event exposure | High | Enforce event/category caps and source-correlation caps; do not treat related markets as independent Kelly bets. |

## Execution Roadmap

1. P0 correctness: fix fee model, WebSocket tick-size invalidation, and evidence-pack persistence.
2. P1 edge: implement passive fair-value quote intents and depth-aware neg-risk basket simulation in paper mode.
3. P2 validation: run 30 days of observe/paper metrics by strategy, source class, market category, and horizon.
4. P3 scale: promote only the best calibrated, positive-CLV strategy/category pairs into `live_tiny`.

Key Principle: POLYFLOW's durable edge is not prediction alone; it is calibrated public probability plus superior refusal, execution, and post-trade measurement.
