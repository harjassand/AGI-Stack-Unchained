# Failure Kind Mapping v1 (Pinned)

This document pins the deterministic mapping from runtime failure events to
`failure_kind` for v1.5r failure witnesses.

## Allowed failure_kind values

- `GOAL_FAIL`
- `SAFETY_FAIL`
- `INVARIANCE_FAIL`
- `DO_FAIL`
- `TIMEOUT_FAIL`
- `GAS_EXHAUST_FAIL`
- `PARSE_FAIL`

## Deterministic mapping

Implementations MUST map runtime events to the above values using a
case-insensitive, deterministic lookup.

Canonical event labels and their `failure_kind` are:

- `goal_fail` -> `GOAL_FAIL`
- `safety_fail` -> `SAFETY_FAIL`
- `invariance_fail` -> `INVARIANCE_FAIL`
- `do_fail` -> `DO_FAIL`
- `timeout` or `timeout_fail` -> `TIMEOUT_FAIL`
- `gas_exhaust` or `gas_exhaust_fail` -> `GAS_EXHAUST_FAIL`
- `parse_error` or `parse_fail` -> `PARSE_FAIL`

If the event label already matches an allowed `failure_kind` exactly, it MUST
be used as-is. Any unmapped event label MUST cause REJECT.
