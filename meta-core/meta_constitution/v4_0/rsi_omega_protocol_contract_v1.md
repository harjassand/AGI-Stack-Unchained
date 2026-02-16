# RSI Omega Protocol v1 (v4.0)

This constitution defines the Omega ignition protocol for v4.0. The Omega run:

- Executes v3.3 holographic consensus in an unbounded epoch loop.
- Uses a sealed held-out suite where answers are RE2-only.
- Produces a prefix-verifiable, deterministic audit trail.

## Core invariants

1. Held-out answers are never exposed to RE3. Only prompts and metadata are visible.
2. Self-improvements must pass RE1/RE2 promotion gates (schema, hardening, CSI, dev gate).
3. Improvements are accepted only if dev performance improves and immutable core locks remain intact.
4. The omega ledger is hash-chained and prefix-verifiable; the run is defined only over closed epochs.
5. External stop is allowed; on stop, the current epoch must be closed and a final checkpoint written.

## Omega success criteria

Omega ignition is asserted only at the first checkpoint that satisfies:

- New solves strictly exceed baseline under identical budgets.
- Rolling-window pass-rate gain meets the minimum threshold.
- Acceleration metric (ACCEL_INDEX_V1) meets the minimum ratio over consecutive windows.

## Fail-closed behavior

Any missing artifact, hash mismatch, leak violation, or invalid promotion yields INVALID.
Unclosed epochs at stop time are ignored and must not be referenced.
