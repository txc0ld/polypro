# Skill — `clob_order_formatter`

**Implementation:** `polyflow.order_formatter.format_order`.
**PRD section:** §11, §14.4.

## Purpose

Produce the final CLOB payload, or refuse. This skill is the last deterministic
gate before the CLOB adapter sees an order — it owns tick alignment, min-size
quantization, fee/min-size requirement checks, reduce-only emulation for SELL,
and order-type policy.

## Required inputs

- approved `RiskDecision` (must be `approved=True`, `approved_size_usdc > 0`)
- `Market` with non-null `tick_size`, `min_order_size`, `fee_rate_bps`
- `ProbabilityEstimate` (provides `token_id`, `market_price`)
- `evidence_ref` and `risk_ref` — both **mandatory**; missing evidence is a hard refusal

## Refusal codes

| Reason | Meaning |
|---|---|
| `RISK_NOT_APPROVED` | governor said no |
| `ZERO_SIZE` | approved size collapsed to 0 after caps |
| `EVIDENCE_REF_MISSING` | no audit trail attached |
| `TOKEN_ID_UNKNOWN` | `estimate.token_id` empty |
| `TICK_SIZE_UNKNOWN` / `FEE_RATE_UNKNOWN` / `MIN_ORDER_SIZE_UNKNOWN` | metadata gap |
| `ORDER_TYPE_NOT_ALLOWED_LIVE_TINY` | order type outside `orders.allowed_types_live_tiny` |
| `FOK_BLOCKED` | FOK / market-style not yet promoted |
| `SELL_EXCEEDS_BALANCE` | reduce-only check failed (no holdings to sell) |
| `PRICE_OUT_OF_BOUNDS_AFTER_TICK_ALIGN` | tick rounding pushed price to 0 or 1 |
| `SIZE_BELOW_MIN_ORDER_SIZE` | size after grid rounding under `min_order_size` |

## Formatting rules

- **BUY** prices floor to the nearest tick; **SELL** prices ceil. We never cross
  fair value through rounding.
- Sizes are floored to the `min_order_size` grid.
- `clientOrderId` is a fresh UUID per call.
- `maxPositionAfterFill` carries the approved $ exposure for the post-order hook.

## Output (strict JSON)

```json
{
  "ready_to_submit": true,
  "rejected": false,
  "reason_codes": [],
  "risk_ref": "<signal_id>",
  "evidence_ref": "<sha256:…>",
  "order_payload": {
    "tokenID": "0x…",
    "side": "BUY",
    "price": "0.62",
    "size": "10",
    "orderType": "GTC",
    "strategy": "external_odds_divergence",
    "marketId": "0x…",
    "eventId": "0x…",
    "maxPositionAfterFill": "9.50",
    "clientOrderId": "uuid"
  }
}
```
