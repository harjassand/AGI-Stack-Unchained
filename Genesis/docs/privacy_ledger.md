# PrivacyLedger and Side-Channel Discipline (Level-1)

PrivacyLedger enforces a global information-leakage budget for interactions with private evaluation data. It also specifies side-channel controls for the CDEL boundary.

## Normative Default Summary (MUST implement)

- DP mechanism: Gaussian noise on metrics + private thresholding for PASS/FAIL.
- Accounting: RDP (Renyi DP) accountant with conversion to (epsilon, delta).
- Responses: binary-only PASS/FAIL with constant-format and timing buckets.

## State Variables (per epoch)

- `epoch_id`
- `epsilon_total`, `delta_total`
- `epsilon_spent`, `delta_spent`
- `query_counter`
- `ledger_entries[]`

## Privacy Accounting (Normative)

- CDEL MUST use a valid DP accountant (RDP or moments accountant) and convert to (epsilon, delta).
- Each evaluation consumes a declared `privacy_bid` and an actual `privacy_spent`.
- `privacy_spent` MUST be <= `privacy_bid` for PASS; MAY be <= bid for FAIL.
- If `epsilon_spent + epsilon_i > epsilon_total` or `delta_spent + delta_i > delta_total`, CDEL MUST return FAIL without evaluation.

## Reusable Holdout (Required)

CDEL MUST implement a reusable holdout mechanism for private evaluation data. Acceptable families:

- Noise addition to metrics with calibrated thresholds.
- Private threshold testing with DP-aware accept rules.
- Reusable holdout via adaptive query auditing.

The mechanism MUST be compatible with binary PASS/FAIL outputs only.

## Side-Channel Requirements (Normative)

- CDEL outputs only PASS or FAIL. No stage identifiers or error codes.
- Response size and formatting MUST be constant within coarse buckets.
- Execution time MUST be padded or bucketed to reduce timing leakage.
- Batching or delayed responses are permitted.
- No detailed failure traces are exposed to Genesis.

## Shadow-CDEL Separation

- Shadow-CDEL MUST NOT access private holdout data.
- Shadow-CDEL diagnostics MUST be produced using public or non-sensitive data only.

## Ledger Entry Schema (Audit)

Each evaluation attempt appends an entry:

- `epoch_id`
- `attempt_id`
- `capsule_hash`
- `epsilon_allocated`, `delta_allocated`
- `epsilon_charged`, `delta_charged`
- `decision` (PASS/FAIL)
- `timestamp`

Audit logs are internal and MUST NOT be exposed to Genesis.

## Invariants (Auditable)

- `epsilon_spent` and `delta_spent` MUST be non-decreasing.
- `epsilon_spent <= epsilon_total` and `delta_spent <= delta_total`.
- `query_counter` MUST be strictly increasing.
