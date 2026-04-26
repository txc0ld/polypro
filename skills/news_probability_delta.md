# Skill — `news_probability_delta`

**Cadence:** triggered by `news_context_monitor` every 60s, on candidate markets.
**Implementation:** strategy-side; consumes `polyflow.probability.build_estimate`.
**PRD section:** §9.1, §14.2.

## Purpose

Decide whether new public information has shifted true probability faster than
the market repriced. Output a `ProbabilityEstimate` with explicit uncertainty
and source-quality scoring, or refuse.

## Inputs

- the candidate `Market`
- the latest CLOB best-bid / best-ask / mid (`market_price`)
- a list of *public* source events from approved feeds (X API, RSS, official
  pages, sportsbook odds, polling aggregators) within the lookback window
- per-source reliability priors (a separate calibration table)

## Hard refusal rules

A trade signal **must not** be emitted if any of the following holds:

- **single-source rumor** — fewer than 2 independent credible public sources
  for a major delta (`probability_delta >= 0.06`)
- **private / leaked / confidential / illegal info** — any source flagged as
  non-public, leaked, or stolen
- **outcome influencer** — the source is a participant who can affect the
  outcome (e.g., a campaign insider on an election market)
- **resolution mismatch** — the news refers to a different settlement event
  than the market's resolution rule
- **stale source** — every confirming source is older than
  `source_latency_fresh_minutes_max` (default 20m)
- **source reliability below 0.75** averaged across confirmations

## Output (strict JSON)

```json
{
  "market_id": "0x…",
  "token_id": "0x…",
  "outcome": "YES",
  "current_price": 0.62,
  "new_model_probability": 0.69,
  "probability_delta": 0.07,
  "uncertainty": 0.05,
  "source_confidence": 0.83,
  "trade_allowed": true,
  "reason_codes": ["PUBLIC_NEWS_CONFIRMED", "MULTI_SOURCE"],
  "evidence_refs": ["sha256:…", "sha256:…"]
}
```

`trade_allowed` is the disposition; `reason_codes` carries the rationale (both
positive and negative codes). Malformed JSON is rejected by the runtime.

## Notes for builders

- Always store the *raw* source bytes (URL + fetched body hash) under
  `evidence_refs` before emitting the signal — the immutable log and Trade Court
  page must be able to reconstruct exactly what the model saw.
- Never use rate-limited or terms-prohibited scraping. Approved feeds only.
