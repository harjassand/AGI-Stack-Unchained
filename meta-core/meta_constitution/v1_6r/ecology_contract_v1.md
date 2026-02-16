# Ecology Contract v1 (Pinned Documentation Only)

This note defines the v1.5r ignition ecology contract. It is **non-executable** and does not expand the TCB.

## Core Kernel ID

- `core_kernel_id` is a **stable identifier** for the shared mechanistic core across an ecology ladder.
- It MUST be a `sha256:<hex>` string computed from the canonical payload of the shared core (exact derivation is defined by the implementing pack generator).
- All families in a single ignition ecology MUST share the same `core_kernel_id`.

## Refinement Steps

- `refinement_step` is an integer in **[0, 63]**.
- The ignition ladder MUST progress in strictly increasing steps by **exactly 1** per insertion: `0 → 1 → 2 → 3 → 4`.

## Refinement Axis

The refinement axis MUST be one of:

- `NOISE`
- `DELAY`
- `ACTION_REMAP`
- `RENDER`
- `OBS_ALIAS`
- `COMPOSED`

The axis documents how the family differs from its predecessor (diagnostic only).

## Motif Hint

Each ecology contract includes a `motif_hint`:

- `target_action_names`: list length **[6, 12]**
- `min_occurrences_total`: integer
- `min_support_families`: integer

This hint **does not change any gates**; it is used only to measure whether the ecology produces repeated motifs for macro feasibility.

## Determinism & Enforcement

All ecology contract artifacts MUST be GCJ‑1 canonical JSON and schema‑valid. Missing or malformed fields MUST fail closed in diagnostics.
