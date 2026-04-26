# Skill — `fractional_kelly_sizer`

**Implementation:** `polyflow.kelly` + `polyflow.risk_governor.evaluate`.
**PRD section:** §8.2, §8.3, §14.3.

## Purpose

Convert a `ProbabilityEstimate` into an approved $-size or a refusal.
**Raw Kelly is never used live.** This skill enforces the conservative
multiplier stack and the per-market / per-event / per-category /
daily-loss caps from PRD §10.

## Formulae

```
kelly_yes = max(0, (q - p) / (1 - p))        # buy YES at price p, model prob q
kelly_no  = max(0, (p - q) / p)               # buy NO at YES-price p, model YES prob q

position_fraction =
    raw_kelly
  * kelly_fraction          # default 0.05
  * confidence_multiplier   # source_confidence * (1 - uncertainty)
  * liquidity_multiplier    # shrink if order > 10% of 5c-depth
  * resolution_multiplier   # linear shrink to 0 at max_resolution_risk
  * portfolio_multiplier    # shrinks as open_markets / daily_loss approach caps

size_usdc = position_fraction * bankroll
```

## Hard caps (applied after the multipliers)

- **Per-market:** `max_single_market_position_pct` of bankroll
- **Per-event:** `max_single_event_exposure_pct` of bankroll
- **Per-category:** `max_category_exposure_pct` of bankroll
- **Daily loss:** if hit, all new orders blocked (kill switch)
- **First live day** (PRD §10.3): hard $ caps on order, position, exposure, and
  trade count regardless of percentage headroom

## Output (strict JSON)

```json
{
  "approved": true,
  "approved_size_usdc": 9.50,
  "raw_kelly": 0.21,
  "fractional_kelly": 0.0095,
  "caps_applied": ["FIRST_DAY_ORDER_CAP"],
  "reason_codes": []
}
```

If `approved=false`, `reason_codes` enumerates every gate that failed —
the runtime never re-runs sizing speculatively to "find" headroom.
