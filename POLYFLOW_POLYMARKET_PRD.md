# POLYFLOW — Next-Gen Autonomous Polymarket Trading Runtime PRD

**Version:** 1.0  
**Document type:** Build-ready PRD + operational runtime spec  
**Target platform:** Polymarket CLOB / Gamma / Data / WebSocket ecosystem  
**Runtime concept:** 24/7 autonomous prediction-market trading being  
**Primary objective:** Trade live on Polymarket with institutional-grade market selection, probability modeling, position sizing, execution control, and autonomous monitoring  
**Design bar:** Build it as if it is being reviewed by Sam Altman: not a toy bot, not a prompt wrapper, not an “AI trader,” but a self-observing autonomous market organism with hard risk boundaries.  
**Hard rule:** The system must never rely on private, stolen, illegal, confidential, or outcome-influencing information. It must not spoof, wash trade, self-deal, manipulate, front-run, or use deceptive orders.

---

## 0. Reality Contract

No autonomous trading system can guarantee profit. No prediction market bot can be “proven” to work forever. The correct objective is not “never lose.” The objective is:

1. **Never die from one market, one bug, one bad model, one stale feed, or one hallucinated trade.**
2. **Only risk capital when the system can explain why the market price is wrong.**
3. **Avoid garbage markets before trying to outsmart good ones.**
4. **Trade live only inside deterministic risk rails.**
5. **Measure everything: Brier score, calibration, closing-line value, slippage, fill quality, edge decay, market-selection quality, and realized PnL.**
6. **Continuously monitor 24/7 and fail closed.**

POLYFLOW must be treated as a small autonomous trading desk, not a script.

---

## 1. Executive Summary

POLYFLOW is a fully autonomous prediction-market trading platform for Polymarket. It scans markets continuously, filters out low-liquidity and poor-resolution markets, builds probability models from public data, compares model probability against market-implied probability, sizes using capped fractional Kelly, formats safe CLOB orders, verifies exposure after every order, and logs every action immutably.

The system operates as a **Claude/OpenClaw-style runtime**:

```text
CLAUDE.md operational doctrine
    ↓
Skills: deterministic tools the agent may invoke
    ↓
Hooks: mandatory guardrails that run every time
    ↓
Subagents: persistent 24/7 monitoring specialists
    ↓
Risk Governor: final deterministic approval
    ↓
CLOB Execution Adapter
    ↓
Portfolio Sentinel + Immutable Evidence Log
```

The product goal:

> An autonomous being that watches Polymarket 24/7, finds only high-quality mispricings, sizes conservatively, trades live, and survives long enough for edge to compound.

---

## 2. Polymarket-Specific Model

### 2.1 Core Mechanics

A binary outcome token is priced between 0 and 1. Buying YES at 0.62 means paying $0.62 for a contract that settles at $1 if YES wins and $0 if YES loses.

The trading problem is therefore not classical chart trading. It is:

```text
Find q_model ≠ p_market
where:
  q_model = system-estimated probability of outcome
  p_market = executable market price after spread/slippage
```

The bot trades only when:

```text
edge_after_uncertainty > total_execution_cost + resolution_risk_buffer + model_error_buffer
```

### 2.2 Core Difference From Crypto Perp Bot

| Crypto Perp Bot | Polymarket Bot |
|---|---|
| Trades price movement | Trades event probability |
| Stop loss is price-based | Loss can be binary at resolution |
| Edge from flow/market structure | Edge from probability mispricing |
| Liquidity is usually deeper | Liquidity is fragmented/thin |
| Position can be closed anytime if book exists | Exit liquidity may disappear |
| Market data mostly numeric | Data is narrative/news/rules-heavy |
| Oracle risk low | Resolution/rules risk is material |
| Leverage possible | Usually fully funded outcome exposure |
| Strategy can be technical | Strategy must be epistemic |

---

## 3. Operating Doctrine

### 3.1 Do Not Trade Everything

The bot’s first job is **market refusal**.

Most Polymarket markets are not tradable for an autonomous live system because they have:

- poor liquidity;
- wide spreads;
- ambiguous rules;
- low-quality resolution language;
- low volume;
- high manipulation risk;
- insider-information risk;
- event-influence risk;
- poor external reference data;
- insufficient time to exit;
- stale order books;
- no reliable probability anchor.

The bot must skip most markets.

### 3.2 Trade Types Allowed

POLYFLOW may trade only these edge classes:

1. **Public-information probability repricing**  
   The model detects that new public information has changed true probability faster than the market updated.

2. **Cross-market divergence**  
   Polymarket probability diverges from credible external public benchmarks such as regulated prediction markets, bookmaker odds, liquid exchange prices, or public statistical forecasts.

3. **Market-making / spread capture**  
   The system quotes genuine two-sided liquidity only when inventory, volatility, and resolution risk are controlled.

4. **Negative-risk / combinatorial mispricing**  
   The system detects structurally bounded baskets across related outcomes where total payout/risk is mathematically favorable, subject to all venue rules and liquidity constraints.

5. **Closing-line value accumulation**  
   The system enters when it expects the market probability to move toward its modeled fair value before resolution, not only at final settlement.

### 3.3 Trade Types Prohibited

The bot must never trade based on:

- private/confidential/stolen information;
- illegal tips;
- information from someone able to influence the outcome;
- hacking, scraping restricted systems, or non-public data access;
- sensor tampering/weather manipulation/event manipulation;
- deceptive orders;
- self-trading;
- wash trading;
- spoofing;
- fake liquidity;
- front-running user/customer orders;
- attempt to influence market settlement.

---

## 4. The Runtime Files

The operational runtime is intentionally small but strict:

```text
CLAUDE.md
skills/market_scanner.md
skills/news_probability_delta.md
skills/fractional_kelly_sizer.md
skills/clob_order_formatter.md
hooks/post_order_kelly_guard.md
hooks/immutable_trade_logger.md
subagents/market_divergence_monitor.md
subagents/news_context_monitor.md
subagents/portfolio_sentinel.md
configs/policy.yaml
```

The phrase “Claude is not a chatbot; Claude is a runtime” is treated literally.

Claude/OpenClaw does not “chat.” It operates against a contract:

- what markets to scan;
- what markets to skip;
- what sources are allowed;
- how to calculate probability deltas;
- how to size;
- how to format orders;
- what hooks must run every time;
- what subagents monitor continuously;
- what blocks live trading;
- what logs must be written.

---

## 5. System Architecture

```text
┌─────────────────────────────────────────────────────────────────────┐
│                          POLYFLOW                                    │
├─────────────────────────────────────────────────────────────────────┤
│  External Public Data                                                │
│  News | X API | RSS | Sportsbooks | Kalshi | Crypto Prices | Polls    │
├─────────────────────────────────────────────────────────────────────┤
│  Polymarket Data Plane                                               │
│  Gamma API | CLOB Market Data | WebSockets | Data API | Polygon RPC   │
├─────────────────────────────────────────────────────────────────────┤
│  Market Discovery Engine                                             │
│  New Market Scanner | Liquidity Filter | Rule Parser | Skip Classifier│
├─────────────────────────────────────────────────────────────────────┤
│  Probability Intelligence Engine                                     │
│  Baselines | Public-News Delta | External-Odds Mapping | Calibration  │
├─────────────────────────────────────────────────────────────────────┤
│  Edge Engine                                                         │
│  Fair Probability | Uncertainty | Spread | Slippage | Resolution Risk │
├─────────────────────────────────────────────────────────────────────┤
│  Strategy Ensemble                                                   │
│  News Repricing | Divergence | Spread Capture | Negative Risk         │
├─────────────────────────────────────────────────────────────────────┤
│  Kelly + Risk Governor                                               │
│  Fractional Kelly | Hard Caps | Event Caps | Category Caps | Kill     │
├─────────────────────────────────────────────────────────────────────┤
│  CLOB Execution Adapter                                              │
│  Order Format | Tick Size | Min Size | GTC/FAK/FOK | Cancel/Replace   │
├─────────────────────────────────────────────────────────────────────┤
│  Hooks                                                               │
│  Post-Order Kelly Guard | Immutable Trade Logger                     │
├─────────────────────────────────────────────────────────────────────┤
│  24/7 Subagents                                                      │
│  Market Divergence | News Context | Portfolio Sentinel               │
├─────────────────────────────────────────────────────────────────────┤
│  Dashboard + Alerting                                                │
│  Live Desk | Opportunity Feed | Portfolio Risk | Incident Room        │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 6. Market Universe Policy

### 6.1 Market Categories to Scan

#### Priority A — Best Fit

| Category | Why |
|---|---|
| Crypto price-level markets | External reference prices are liquid and real-time. |
| Macro/economic releases | Public calendars, historical models, clear timestamps. |
| Large sports markets | External bookmaker odds provide anchors. |
| Major election markets | Polling/forecast anchors, but high regulatory/integrity sensitivity. |
| High-volume breaking news markets | Useful if public-source velocity is measurable. |
| Markets with strong cross-platform equivalents | Allows divergence analysis. |

#### Priority B — Conditional

| Category | Conditions |
|---|---|
| Weather markets | Only if official data source is clear, manipulation risk low, and external forecasts are reliable. |
| Awards/pop culture | Only if high liquidity and credible public odds exist. |
| Corporate/product-launch markets | Only if not dependent on non-public company information. |
| Regulatory decision markets | Only if public process and public record are sufficient. |

### 6.2 Markets to Skip

Hard skip if any condition is true:

```yaml
skip_if:
  liquidity_usd_below: 25000
  best_bid_ask_spread_pct_above: 8
  depth_within_5c_below_usd: 5000
  volume_24h_below_usd: 10000
  market_closes_within_minutes: 30
  ambiguous_resolution_language: true
  missing_clob_token_ids: true
  missing_tick_size: true
  unresolved_oracle_dispute: true
  outcome_can_be_influenced_by_small_actor: true
  source_data_can_be_tampered_with: true
  requires_private_information: true
  category_is_war_death_terror_assassination: true
  category_is_thin_meme_market: true
  market_has_micro_liquidity_problem: true
```

### 6.3 Tradable Market Requirements

```yaml
tradable_market_minimum:
  liquidity_usd: 100000
  volume_24h_usd: 25000
  depth_within_5c_usd: 10000
  max_spread_pct: 5
  min_time_to_close_minutes: 60
  clear_resolution: true
  clob_token_ids_present: true
  order_book_present: true
  tick_size_known: true
  fee_rate_known: true
  neg_risk_known: true
```

---

## 7. Data Sources

### 7.1 Polymarket Sources

| Source | Purpose |
|---|---|
| Gamma API | Market/event discovery, metadata, descriptions, tags, close dates. |
| CLOB API | Order books, prices, tick size, fee rate, order placement. |
| CLOB WebSocket Market Channel | Real-time order book/trade updates. |
| CLOB WebSocket User Channel | Fills, order updates, cancellations. |
| Data API | User positions, activity, portfolio analytics. |
| Polygon RPC | Settlement, token balances, on-chain confirmations. |

### 7.2 External Public Sources

| Source Type | Use |
|---|---|
| X API / approved social APIs | Public-event velocity and sentiment. |
| RSS/news APIs | Breaking public information. |
| Sportsbook APIs/odds feeds | Sports fair probability anchors. |
| Kalshi/public prediction markets | Cross-market probability comparison. |
| Crypto exchange prices | Crypto event settlement anchors. |
| Polling aggregators | Election baseline probabilities. |
| Economic calendar APIs | Macro event timing and consensus. |
| Weather APIs | Weather-market baselines where allowed. |
| Official source pages | Resolution verification. |

### 7.3 Source Compliance Rule

Do not scrape sources that prohibit scraping. Use official APIs, licensed feeds, or public pages with permitted access.

---

## 8. Probability Engine

### 8.1 Probability Object

Every model output must include:

```json
{
  "market_id": "string",
  "token_id": "string",
  "outcome": "YES",
  "market_price": 0.62,
  "model_probability": 0.70,
  "uncertainty": 0.06,
  "fair_bid": 0.61,
  "fair_ask": 0.69,
  "edge_before_costs": 0.08,
  "edge_after_costs": 0.035,
  "source_confidence": 0.82,
  "resolution_risk": 0.10,
  "recommendation": "BUY_YES",
  "expires_at": "ISO_TIMESTAMP",
  "reason_codes": [
    "BOOKMAKER_DIVERGENCE",
    "PUBLIC_NEWS_CONFIRMED",
    "SPREAD_ACCEPTABLE"
  ]
}
```

### 8.2 Binary Kelly Formula

For buying YES at market price `p` with model probability `q`:

```text
kelly_yes = (q - p) / (1 - p)
```

For buying NO, using YES market price `p` and model YES probability `q`:

```text
kelly_no = (p - q) / p
```

The bot never uses raw Kelly live. It uses capped fractional Kelly:

```text
position_fraction =
max(0, raw_kelly)
× kelly_fraction
× confidence_multiplier
× liquidity_multiplier
× resolution_multiplier
× portfolio_multiplier
```

### 8.3 Default Kelly Settings

```yaml
kelly:
  live_fraction: 0.05
  paper_fraction: 0.25
  max_single_market_bankroll_pct: 1.00
  max_single_event_bankroll_pct: 2.50
  max_category_bankroll_pct: 5.00
  max_daily_new_risk_bankroll_pct: 2.00
  max_daily_loss_bankroll_pct: 0.75
  min_edge_after_costs_pct: 3.00
  min_edge_after_uncertainty_pct: 1.50
```

### 8.4 Edge Calculation

```text
effective_edge =
abs(q_model - p_executable)
- half_spread
- expected_slippage
- fee_impact
- resolution_risk_buffer
- model_uncertainty_buffer
- liquidity_exit_buffer
```

Trade only if:

```text
effective_edge >= min_edge_threshold
AND confidence >= min_confidence
AND market_quality >= min_market_quality
AND risk_governor_approved == true
```

### 8.5 Calibration Metrics

The bot must track:

- Brier score;
- log loss;
- calibration by probability bucket;
- closing-line value;
- edge decay;
- model-vs-market error;
- realized PnL by edge bucket;
- PnL by source type;
- PnL by market category;
- PnL by liquidity tier;
- false-positive news adjustments;
- false-negative missed adjustments.

---

## 9. Strategy Ensemble

### 9.1 Strategy A — Public News Repricing

Public information can change the true probability faster than the market reprices, especially in thinner or newly created markets.

```yaml
entry:
  public_news_confirmed_by_sources_min: 2
  source_reliability_min: 0.75
  probability_delta_min: 0.06
  effective_edge_min: 0.03
  market_quality_min: 0.70
  source_latency_fresh_minutes_max: 20
```

Reject if:

- single-source rumor;
- private/leaked/confidential info;
- source can influence outcome;
- market rules do not match news;
- liquidity insufficient;
- spread too wide;
- resolution ambiguity high.

### 9.2 Strategy B — External Odds Divergence

Sportsbooks, regulated prediction markets, and liquid reference markets can imply a probability different from Polymarket. The bot trades only when the divergence persists after vig removal, fees, spread, and resolution mismatch.

Process:

1. Fetch Polymarket market.
2. Map market to equivalent external event.
3. Normalize outcome definitions.
4. Remove bookmaker vig.
5. Convert external odds to fair probability.
6. Compare against Polymarket executable price.
7. Apply liquidity and resolution adjustments.
8. Size with capped Kelly.
9. Place limit/FAK order only if edge remains.

### 9.3 Strategy C — New Market Opening Mispricing

Newly listed markets often open with inefficient prices before liquidity and attention arrive.

```yaml
new_market_strategy:
  scan_frequency_minutes: 5
  min_liquidity_usd: 50000
  max_spread_pct: 6
  min_external_anchor_confidence: 0.80
  max_order_size_usd: 50
  human_approval_required_until_100_paper_trades: true
```

### 9.4 Strategy D — Spread Capture / Passive Liquidity

High-quality markets with genuine two-sided flow may allow passive quoting around fair probability.

Strict legal requirement: every order must have genuine intent to trade. No spoofing. No layering. No fake liquidity.

```text
fair_mid = model_probability
quote_width =
base_width
+ uncertainty_width
+ liquidity_width
+ resolution_width
+ inventory_width
```

Disable if:

- order cancel rate exceeds policy;
- quote lifetime too short;
- toxicity high;
- news event active;
- portfolio inventory too one-sided;
- spread narrows below expected fee/slippage;
- fill quality deteriorates.

### 9.5 Strategy E — Negative Risk / Basket Optimizer

Some related outcome sets can create bounded or favorable basket exposure if prices are inconsistent.

Requirements:

- market `neg_risk` status known;
- all related token IDs mapped;
- payout matrix known;
- cost basis known;
- execution liquidity sufficient;
- no market-rule mismatch;
- solver proves bounded downside.

Solver:

```text
maximize expected_value
subject to:
  worst_case_loss <= max_loss
  per_market_position <= cap
  per_event_exposure <= cap
  available_liquidity >= required_size
  all_orders_executable <= max_slippage
```

v1 status: research/paper only until thoroughly tested.

---

## 10. Risk Governor

### 10.1 Authority

The Risk Governor is final. It can:

- reject a trade;
- reduce size;
- require manual approval;
- cancel orders;
- flatten positions;
- disable a market;
- disable a strategy;
- pause live trading;
- activate global kill switch.

### 10.2 Live Default Limits

```yaml
risk:
  bankroll_usdc: 1000
  max_single_market_position_pct: 1.0
  max_single_event_exposure_pct: 2.5
  max_category_exposure_pct: 5.0
  max_daily_loss_pct: 0.75
  max_weekly_loss_pct: 2.0
  max_open_markets: 10
  max_new_markets_per_hour: 4
  max_orders_per_minute: 10
  max_cancel_ratio_per_market_per_hour: 0.80
  min_confidence: 0.75
  min_effective_edge: 0.03
  min_market_quality: 0.70
  max_resolution_risk: 0.35
  max_model_uncertainty: 0.12
```

### 10.3 First Live Day Limits

```yaml
first_live_day:
  mode: live_tiny
  bankroll_airlock_usdc: 250
  max_order_usdc: 10
  max_market_position_usdc: 25
  max_event_exposure_usdc: 50
  max_daily_loss_usdc: 15
  max_trades: 5
  allowed_order_types: ["GTC_LIMIT", "FAK_LIMIT"]
  disallowed_order_types: ["MARKET_FOK"]
  no_market_making: true
  no_negative_risk_baskets: true
  human_ack_required_for_first_10_orders: true
```

### 10.4 Market Quality Score

```text
market_quality =
liquidity_score
+ spread_score
+ volume_score
+ clarity_score
+ external_anchor_score
+ time_to_close_score
+ book_stability_score
- resolution_risk_penalty
- manipulation_risk_penalty
- insider_risk_penalty
```

### 10.5 Kill Switch Conditions

Immediate stop if:

- post-order Kelly guard fails;
- position exceeds cap;
- event exposure exceeds cap;
- wallet balance mismatch;
- CLOB order status unknown;
- user channel stale;
- market data stale;
- unresolved order older than threshold;
- API errors spike;
- model emits malformed probability;
- Claude/subagent output is non-JSON or invalid;
- data source produces contradictory result;
- unauthorized config mutation;
- forbidden market category detected;
- market integrity policy violation risk detected;
- daily loss cap hit.

---

## 11. Execution Layer

### 11.1 Order Types

Allowed order format:

```json
{
  "tokenID": "string",
  "side": "BUY",
  "price": "0.63",
  "size": "25",
  "orderType": "GTC",
  "strategy": "external_odds_divergence",
  "marketId": "string",
  "eventId": "string",
  "maxPositionAfterFill": "50",
  "clientOrderId": "uuid"
}
```

Supported:

- GTC limit;
- FAK limit;
- FOK limit only after live maturity;
- market-style orders disabled in initial live mode;
- reduce-only emulation for sells;
- cancel/replace with policy-based cancel-rate caps.

### 11.2 Order Formatting Rules

Before order submission:

1. Confirm token ID.
2. Confirm outcome mapping.
3. Confirm tick size.
4. Confirm min order size.
5. Confirm fee rate.
6. Confirm neg risk flag.
7. Confirm order book exists.
8. Confirm executable price still valid.
9. Confirm size <= Kelly cap.
10. Confirm event/category caps.
11. Confirm no forbidden category.
12. Confirm source evidence exists.
13. Generate client order ID.
14. Write pre-trade evidence pack.
15. Submit order.
16. Run post-order hook.
17. Log every result.

### 11.3 Reduce-Only Emulation

```text
if side == SELL:
  assert sell_size <= current_token_balance
  assert sell_does_not_create_unintended_short_or_invalid_state
```

If the system cannot verify holdings, it may not sell.

---

## 12. 24/7 Autonomous Runtime

### 12.1 Core Loop

```text
Every 5 minutes:
  scan new markets
  update existing watchlist
  classify markets
  skip bad markets
  refresh order books
  refresh external anchors
  compute probability deltas
  score opportunities
  size candidates
  submit allowed orders
  verify positions
  log everything

Every 30 seconds:
  monitor live order books for active positions
  monitor fills/orders
  update risk state
  check kill switches

Every 1 minute:
  refresh breaking-news queue
  trigger probability updates
  alert on major divergence

Every 15 minutes:
  portfolio sentinel review
  stale market review
  exposure review

Every 1 hour:
  calibration report
  strategy health update

Every 24 hours:
  full post-trade review
  model calibration update
  source-quality scoring
  market blacklist/whitelist update
```

### 12.2 Autonomy Levels

| Mode | Description |
|---|---|
| OBSERVE | No orders. Scan and score only. |
| PAPER | Simulate orders and fills. |
| LIVE_CONFIRM | Agent proposes; operator approves. |
| LIVE_TINY | Fully autonomous with tiny caps. |
| LIVE_STANDARD | Fully autonomous after promotion gates. |
| LOCKDOWN | Existing risk only; no new orders. |

### 12.3 Fully Autonomous Being Definition

The system is a “being” only in the operational sense:

- persistent state;
- persistent memory;
- source memory;
- strategy memory;
- market blacklist;
- market whitelist;
- self-diagnostics;
- risk reflexes;
- subagents;
- hooks;
- autonomous action within policy;
- incident response;
- self-review.

It is not allowed to rewrite its own live policy, override risk limits, access private data, or improvise outside the PRD.

---

## 13. CLAUDE.md Operational Context

This file is the non-negotiable runtime constitution.

```markdown
# CLAUDE.md — POLYFLOW Operational Context

You are POLYFLOW, a 24/7 autonomous Polymarket trading runtime.

Your objective is not to trade often. Your objective is to identify high-quality, publicly defensible probability mispricings and execute only when edge survives liquidity, uncertainty, resolution risk, and portfolio constraints.

## Prime Directive

Survive first. Trade second. Scale last.

## Live Trading Rule

You may only format and submit live orders through the `clob_order_formatter` skill after:
1. market_scanner approves the market;
2. news_probability_delta or divergence logic produces a valid probability;
3. fractional_kelly_sizer approves size;
4. Risk Governor approves;
5. order evidence pack exists.

## Markets To Scan

Scan:
- high-liquidity crypto markets;
- macro/economic release markets;
- high-liquidity sports markets with external odds;
- major election markets with public polling/forecast anchors;
- breaking-news markets with multiple public confirmations;
- high-volume markets with clear resolution;
- related markets eligible for negative-risk analysis.

## Markets To Skip

Skip:
- markets with liquidity below policy;
- markets with wide spreads;
- markets with ambiguous resolution criteria;
- markets closing too soon;
- markets requiring private/confidential information;
- markets where trader/source can influence outcome;
- suspicious weather/sensor markets;
- thin meme markets;
- markets with poor external anchors;
- war/death/terror/assassination markets;
- any market where trade rationale would look indefensible under review.

## Position Limits

Default:
- max 1% bankroll per market;
- max 2.5% bankroll per event;
- max 5% bankroll per category;
- max 0.75% daily loss;
- max 2% weekly loss;
- first live day max order: $10 USDC;
- first live day max daily loss: $15 USDC.

## Order Policy

Prefer limit orders.
Initial live mode may use GTC or FAK only.
FOK/market-style orders are disabled until promoted.
Never submit an order if tick size, min size, fee rate, or token mapping is unknown.

## Information Policy

Use public information only.
Do not trade on stolen, private, confidential, illegal, leaked, or outcome-influencing information.
Do not scrape prohibited sources.
Use official APIs or allowed public data access.

## Integrity Policy

No spoofing.
No wash trading.
No self-dealing.
No fake liquidity.
No front-running.
No deceptive orders.
Every order must have genuine intent to trade.

## Required Output Format

Every candidate trade must be JSON.

Malformed output must be rejected.
```

---

## 14. Skills

### 14.1 Skill 1 — Market Scanner

File: `skills/market_scanner.md`

Purpose:

- scan new Polymarket markets every 5 minutes;
- classify market category;
- extract event/market/token metadata;
- reject bad markets before modeling;
- maintain watchlist.

Hard filters:

- liquidity;
- spread;
- volume;
- close time;
- token IDs;
- rule clarity;
- external anchor availability;
- manipulation risk;
- insider risk.

### 14.2 Skill 2 — News Probability Delta

File: `skills/news_probability_delta.md`

Purpose:

- parse public news and social signals;
- determine whether new information changes event probability;
- output probability adjustment with uncertainty;
- require multiple confirmations for major adjustments.

Reject conditions:

- rumor only;
- private/leaked/confidential info;
- source can influence outcome;
- source relevance mismatch;
- market resolution mismatch.

### 14.3 Skill 3 — Fractional Kelly Sizer

File: `skills/fractional_kelly_sizer.md`

Purpose:

- convert probability edge into conservative position size;
- apply bankroll, market, event, category, source, and drawdown caps;
- return approved size or reject.

### 14.4 Skill 4 — CLOB Order Formatter

File: `skills/clob_order_formatter.md`

Purpose:

- format a safe Polymarket CLOB order;
- validate token ID, tick size, min size, fee, order type, and exposure;
- produce final order payload.

Reject if:

- token ID unknown;
- tick size unknown;
- size below min;
- price not aligned to tick;
- order would exceed Kelly;
- order would exceed event/category cap;
- order is not backed by evidence.

---

## 15. Hooks

### 15.1 Hook 1 — Post-Order Kelly Guard

File: `hooks/post_order_kelly_guard.md`

Runs after every order attempt and every fill.

Responsibilities:

- recalculate actual position;
- recalculate Kelly exposure;
- compare against approved exposure;
- detect accidental oversize;
- trigger cancel/flatten if needed;
- disable strategy if breach occurs.

This hook must run every time. Not when the model remembers. Every time.

### 15.2 Hook 2 — Immutable Trade Logger

File: `hooks/immutable_trade_logger.md`

Runs after:

- market scan;
- candidate signal;
- trade rejection;
- risk decision;
- order formatting;
- order submission;
- order update;
- fill;
- cancel;
- position update;
- model update;
- incident.

Logs must be append-only.

---

## 16. Subagents

### 16.1 Subagent 1 — Market Divergence Monitor

File: `subagents/market_divergence_monitor.md`

Purpose:

- monitor approved markets;
- compare Polymarket probability against external public anchors;
- detect divergence;
- send candidate opportunities to Signal Arbiter.

Runs every 60 seconds.

### 16.2 Subagent 2 — News Context Monitor

File: `subagents/news_context_monitor.md`

Purpose:

- read public news/social feeds from allowed APIs;
- look back over last 48 hours;
- detect new public information;
- identify stale market prices;
- flag integrity risks.

Runs every 60 seconds.

### 16.3 Subagent 3 — Portfolio Sentinel

File: `subagents/portfolio_sentinel.md`

Purpose:

- monitor portfolio exposure 24/7;
- enforce bankroll limits;
- detect stuck orders;
- monitor unresolved markets;
- detect drawdown;
- run incident response.

Runs every 30 seconds.

---

## 17. Signal Arbitration

### 17.1 Candidate Signal Schema

```json
{
  "signal_id": "uuid",
  "market_id": "string",
  "event_id": "string",
  "token_id": "string",
  "outcome": "YES",
  "side": "BUY",
  "strategy": "external_odds_divergence",
  "market_price": 0.62,
  "model_probability": 0.70,
  "uncertainty": 0.05,
  "effective_edge": 0.035,
  "market_quality": 0.82,
  "resolution_risk": 0.15,
  "liquidity_score": 0.78,
  "confidence": 0.81,
  "expires_at": "ISO",
  "evidence_refs": []
}
```

### 17.2 Scoring

```text
signal_score =
edge_score * 0.25
+ market_quality * 0.20
+ source_confidence * 0.15
+ liquidity_score * 0.15
+ resolution_clarity * 0.10
+ calibration_score * 0.10
+ execution_quality * 0.05
- risk_penalties
```

### 17.3 Decision Matrix

| Score | Action |
|---:|---|
| < 70 | Reject |
| 70–79 | Watch only |
| 80–87 | Paper/manual |
| 88–93 | Live tiny allowed |
| 94+ | Live standard candidate after promotion gates |

---

## 18. Database Schema

```sql
CREATE TABLE markets (
  id TEXT PRIMARY KEY,
  event_id TEXT,
  question TEXT NOT NULL,
  category TEXT,
  close_time TIMESTAMPTZ,
  resolution_rules TEXT,
  liquidity_usd NUMERIC,
  volume_24h_usd NUMERIC,
  spread_pct NUMERIC,
  market_quality NUMERIC,
  resolution_risk NUMERIC,
  status TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE outcome_tokens (
  token_id TEXT PRIMARY KEY,
  market_id TEXT NOT NULL REFERENCES markets(id),
  outcome TEXT NOT NULL,
  tick_size NUMERIC,
  min_order_size NUMERIC,
  fee_rate_bps NUMERIC,
  neg_risk BOOLEAN
);

CREATE TABLE probability_estimates (
  id UUID PRIMARY KEY,
  market_id TEXT NOT NULL,
  token_id TEXT NOT NULL,
  model_probability NUMERIC NOT NULL,
  market_price NUMERIC NOT NULL,
  uncertainty NUMERIC NOT NULL,
  effective_edge NUMERIC NOT NULL,
  source_confidence NUMERIC NOT NULL,
  created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE signals (
  id UUID PRIMARY KEY,
  market_id TEXT NOT NULL,
  token_id TEXT NOT NULL,
  strategy TEXT NOT NULL,
  side TEXT NOT NULL,
  score NUMERIC NOT NULL,
  status TEXT NOT NULL,
  reason_codes JSONB NOT NULL,
  evidence_refs JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE orders (
  id UUID PRIMARY KEY,
  client_order_id TEXT UNIQUE NOT NULL,
  exchange_order_id TEXT,
  market_id TEXT NOT NULL,
  token_id TEXT NOT NULL,
  side TEXT NOT NULL,
  price NUMERIC NOT NULL,
  size NUMERIC NOT NULL,
  order_type TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE positions (
  id UUID PRIMARY KEY,
  market_id TEXT NOT NULL,
  token_id TEXT NOT NULL,
  outcome TEXT NOT NULL,
  size NUMERIC NOT NULL,
  avg_price NUMERIC NOT NULL,
  market_value NUMERIC,
  max_loss NUMERIC,
  status TEXT NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE immutable_log (
  id UUID PRIMARY KEY,
  ts TIMESTAMPTZ NOT NULL,
  actor TEXT NOT NULL,
  action TEXT NOT NULL,
  market_id TEXT,
  event_id TEXT,
  input_hash TEXT,
  output_hash TEXT,
  config_hash TEXT,
  code_version TEXT,
  payload JSONB NOT NULL
);
```

---

## 19. Dashboard

### 19.1 Live Autonomous Desk

Shows:

- mode;
- bot heartbeat;
- current bankroll;
- daily PnL;
- open positions;
- open orders;
- risk used;
- current market count;
- skipped market count;
- latest candidates;
- kill switch;
- lock live mode;
- source-health panel.

### 19.2 Market Scanner Board

Shows:

- new markets found;
- approved markets;
- manual-only markets;
- skipped markets;
- skip reasons;
- liquidity/spread filters;
- market quality score.

### 19.3 Probability Lab

Shows:

- model probability vs market price;
- confidence bands;
- source evidence;
- external odds;
- probability delta;
- calibration bucket;
- model history.

### 19.4 Portfolio Sentinel

Shows:

- market exposure;
- event exposure;
- category exposure;
- Kelly usage;
- drawdown;
- stuck orders;
- kill-switch status;
- incident queue.

### 19.5 Trade Court

Every trade gets a page:

1. market;
2. rule summary;
3. model probability;
4. market price;
5. edge;
6. sources;
7. Kelly size;
8. order payload;
9. fills;
10. post-order hook result;
11. exit plan;
12. final result;
13. Brier/log-loss impact;
14. verdict.

---

## 20. Testing and Promotion Gates

### 20.1 Unit Tests

Must cover:

- Kelly formula;
- position caps;
- tick rounding;
- order formatter;
- market skip classifier;
- probability edge calculation;
- market quality scoring;
- resolution risk scoring;
- malformed agent output rejection.

### 20.2 Integration Tests

Must cover:

- Gamma API market ingestion;
- CLOB order book ingestion;
- WebSocket reconnect;
- user order update stream;
- order placement mock;
- fill update;
- stale data;
- cancel/replace;
- post-order hook.

### 20.3 Live Promotion

No standard live autonomy until:

```yaml
promotion:
  observer_days: 14
  paper_days: 30
  paper_trades_min: 200
  live_tiny_trades_min: 50
  max_unexplained_pnl_events: 0
  max_kelly_breaches: 0
  max_unlogged_actions: 0
  calibration_report_required: true
  closing_line_value_positive: true
  post_order_hook_pass_rate: 1.0
```

---

## 21. Infrastructure

### 21.1 Stack

| Layer | Choice |
|---|---|
| Runtime/orchestration | OpenClaw / Claude runtime style |
| Backend | TypeScript or Python FastAPI |
| CLOB SDK | Polymarket TypeScript CLOB client v2 |
| DB | PostgreSQL |
| Time-series/events | ClickHouse or TimescaleDB |
| Queue | Redis Streams / NATS |
| Dashboard | Next.js |
| Observability | Grafana + Prometheus + Sentry |
| Deployment | Docker + VPS |
| Secrets | 1Password/Doppler/Vault |
| Alerts | Discord + Telegram + email |

### 21.2 24/7 Reliability

Required:

- watchdog process;
- process supervisor;
- heartbeat monitor;
- auto-restart with safe mode;
- deadman switch;
- source-health monitor;
- exchange/API health monitor;
- persistent event queue;
- crash replay;
- backup logs;
- manual kill switch.

---

## 22. Config Policy

File: `configs/policy.yaml`

```yaml
mode: live_tiny

market_filters:
  min_liquidity_usd: 100000
  min_volume_24h_usd: 25000
  max_spread_pct: 5
  min_depth_within_5c_usd: 10000
  min_time_to_close_minutes: 60

risk:
  bankroll_usdc: 1000
  max_single_market_position_pct: 1
  max_single_event_exposure_pct: 2.5
  max_category_exposure_pct: 5
  max_daily_loss_pct: 0.75
  max_weekly_loss_pct: 2
  max_open_markets: 10
  max_orders_per_minute: 10

kelly:
  fraction: 0.05
  min_effective_edge: 0.03
  max_model_uncertainty: 0.12

orders:
  allowed_types_live_tiny:
    - GTC
    - FAK
  allow_market_orders: false
  require_tick_size: true
  require_fee_rate: true
  require_min_order_size: true

integrity:
  ban_private_information: true
  ban_leaked_information: true
  ban_outcome_influencer_trading: true
  ban_spoofing: true
  ban_wash_trading: true
  ban_self_dealing: true
  ban_manipulation: true

subagents:
  market_divergence_monitor_seconds: 60
  news_context_monitor_seconds: 60
  portfolio_sentinel_seconds: 30
  market_scanner_minutes: 5
```

---

## 23. Build Directive for Codex / Claude / OpenClaw

```text
Build POLYFLOW as a production-grade autonomous Polymarket trading runtime.

This is not a chatbot. It is an agentic trading infrastructure system.

Implement:
1. CLAUDE.md operational constitution.
2. Four skills:
   - market_scanner
   - news_probability_delta
   - fractional_kelly_sizer
   - clob_order_formatter
3. Two mandatory hooks:
   - post_order_kelly_guard
   - immutable_trade_logger
4. Three subagents:
   - market_divergence_monitor
   - news_context_monitor
   - portfolio_sentinel
5. Polymarket data adapters:
   - Gamma API
   - CLOB market data
   - CLOB order formatting
   - CLOB user stream
   - Data API optional
   - Polygon RPC optional
6. Risk Governor.
7. Dashboard.
8. Paper mode.
9. Live tiny mode.
10. Incident handling.

Non-negotiables:
- no order without Kelly sizing;
- no order without market approval;
- no order without evidence;
- no order without post-order hook;
- no unlogged action;
- no stale-data trading;
- no low-liquidity markets;
- no ambiguous resolution markets;
- no private/confidential/illegal information;
- no spoofing/wash trading/manipulation;
- no live standard mode until promotion gates pass.

The system must run 24/7, monitor continuously, fail closed, and trade live only inside configured limits.
```

---

## 24. Acceptance Criteria

POLYFLOW is acceptable only when:

- market scanner rejects low-liquidity markets automatically;
- skills produce strict JSON;
- malformed agent output is rejected;
- Kelly sizing is unit tested;
- order formatter validates tick size and min order size;
- post-order hook runs after every order/fill;
- immutable logger records every action;
- subagents run continuously;
- live mode is capped;
- kill switch works;
- dashboard displays all exposure;
- every trade has evidence;
- no strategy can bypass risk governor;
- no live order can be placed from a free-form chat response.

---

## 25. Final Operating Standard

The bot should behave like this:

```text
Scan everything.
Trade almost nothing.
Reject bad markets instantly.
Use public information only.
Calculate probability, not vibes.
Size with capped Kelly.
Submit only valid CLOB orders.
Verify exposure after every order.
Log every action.
Monitor 24/7.
Kill itself before it can die.
```

POLYFLOW is not a gambling bot.

It is an autonomous probability desk with strict market selection, public-source intelligence, capped sizing, deterministic execution, and continuous self-surveillance.