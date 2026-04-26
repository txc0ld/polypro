# Hook — `post_order_kelly_guard`

**Implementation:** `polyflow.post_order_hook.evaluate_exposure`.
**Triggers:** every order attempt, every order update, every cancel, every fill.
**PRD section:** §15.1, §10.5.

## Why it is mandatory

The Risk Governor approves *predicted* exposure based on cached state. Reality
diverges: partial fills, latency, double-fills, oracle drift. This hook is the
**only** reconciliation that uses venue truth — the actual position list pulled
fresh from CLOB — and is the only safe place to detect Kelly breaches.

The runtime must call this hook *every time*. It does not depend on the agent
remembering to invoke it; it is part of the order/fill code path.

## Procedure

1. Pull current positions from the CLOB adapter (`get_positions`).
2. Pull current open-order IDs grouped by market.
3. Recompute exposure per market / event / category against bankroll caps.
4. Run `assert_kill_conditions` (PRD §10.5) for daily/weekly loss + bankroll sanity.
5. If a per-market cap is exceeded, **cancel every open order on that market**
   and raise `KillSwitch("POST_ORDER_KELLY_BREACH:…")`.
6. If kill conditions trip, raise `KillSwitch` with the reason.

## Output

`GuardResult(ok, breaches, cancellations_required)` plus an immutable-log entry:

```json
{
  "actor": "post_order_kelly_guard",
  "action": "evaluate",
  "payload": { "ok": true, "breaches": [], "cancellations_required": [] }
}
```

A breach turns into a separate log entry with `action=kill_switch` and the
reason code, then halts the runtime.
