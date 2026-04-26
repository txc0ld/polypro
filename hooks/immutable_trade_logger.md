# Hook — `immutable_trade_logger`

**Implementation:** `polyflow.logger.ImmutableLogger`.
**PRD section:** §15.2, §18.

## Triggers

After every:

- market scan classification
- candidate signal emission
- signal rejection / risk decision
- order format decision
- order submission, update, cancel, fill
- position update
- model probability update
- subagent incident
- kill-switch event

## Storage

Append-only JSONL on disk (one line per record, fsync on every write) and a
mirrored insert into the Postgres `immutable_log` table. Production deploys
the table with row-level grants forbidding `UPDATE` and `DELETE`. The local
file is the source of truth if the DB is unavailable; the runtime never
fail-opens on persistence — if both fail, the runtime trips the kill switch.

## Record shape

```json
{
  "id": "uuid",
  "ts": "2026-04-27T12:34:56+00:00",
  "actor": "risk_governor",
  "action": "evaluate",
  "market_id": "0x…",
  "event_id": "0x…",
  "input_hash": "sha256:…",
  "output_hash": "sha256:…",
  "config_hash": "sha256:…",   // hash of policy.yaml at runtime start
  "code_version": "git_sha",
  "payload": { /* arbitrary structured detail */ }
}
```

`input_hash` and `output_hash` allow reconstruction without storing
potentially sensitive payloads twice. `config_hash` lets us prove which policy
was in force at action time. `code_version` ties the record to a specific
deployable.

## Read paths

- the Trade Court UI page (PRD §19.5) reconstructs each trade from these records
- the calibration job (PRD §8.5) reads logged probabilities + realized outcomes
- incident response replays from the log on restart
