# ComputeLedger (Level-1)

ComputeLedger enforces evaluation compute caps and adversarial-budget limits to prevent unbounded evaluator search.

## State Variables (per epoch)

- `epoch_id`
- `compute_total_units`
- `compute_spent_units`
- `compute_spent_wall_ms`
- `adversary_strength_cap`
- `ledger_entries[]`

## Compute Units

Compute units are a fixed accounting unit defined by the evaluator (e.g., normalized CPU/GPU cycles). The conversion to wall-time MUST be declared in the epoch configuration.

## Enforcement (Normative)

- Each evaluation declares a `compute_bid` with:
  - `max_compute_units`
  - `max_wall_time_ms`
  - `max_adversary_strength`
- CDEL MUST refuse evaluation if any bid exceeds epoch caps.
- CDEL MUST enforce hard runtime limits; exceeding a limit yields FAIL.
- Adversarial scenario search MUST be bounded by `max_adversary_strength` and wall-time.

## Exhaustion

- If `compute_spent_units + compute_units_i > compute_total_units`, CDEL MUST return FAIL without evaluation.

## Charging Policy

- On PASS or FAIL, CDEL charges actual compute spent.
- Charging MUST be monotone and non-negative.

## Ledger Entry Schema (Audit)

Each evaluation attempt appends an entry:

- `epoch_id`
- `attempt_id`
- `capsule_hash`
- `compute_allocated_units`, `wall_allocated_ms`, `adversary_strength_allocated`
- `compute_charged_units`, `wall_charged_ms`, `adversary_strength_used`
- `decision` (PASS/FAIL)
- `timestamp`

Audit logs are internal and MUST NOT be exposed to Genesis.

## Invariants (Auditable)

- `compute_spent_units` and `compute_spent_wall_ms` MUST be non-decreasing.
- `compute_spent_units <= compute_total_units`.
