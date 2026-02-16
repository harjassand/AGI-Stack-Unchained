# Determinism and Attestation (Level-1)

This document specifies reproducibility requirements, checkpoint commitments, and the constrained kernel ISA.

## Normative Default Summary (MUST implement)

- Checkpoint commitments with Merkleized sketches.
- Semantic determinism under harness-controlled randomness.
- Numeric tolerances via `numeric_tolerance` when `determinism_mode` is `tolerant`.

## Normative Default (MUST implement)

## Extensions (MAY implement)

- Full replay logs for narrow-scope artifacts.

## Semantic Determinism

- Determinism is defined over observable outputs and metrics, not internal traces.
- The harness controls randomness and seeds all stochasticity unless the capsule declares otherwise.
- Acceptance metrics MUST be computed with declared tolerances or confidence sequences.

## Reproducibility Requirements

- `determinism_mode` must be one of: deterministic, seeded, tolerant.
- `seed_policy` must be `harness_seeded` or `artifact_seeded`.
- The runtime environment (OS, arch, kernel ISA) MUST be declared.
- If `determinism_mode` is `tolerant`, `numeric_tolerance` (abs/rel) MUST be specified.

## Checkpoint Commitments (Normative)

- Artifacts emit K checkpoints at fixed step indices.
- Each checkpoint includes seeded sketches or projections of state.
- A Merkle tree is constructed over checkpoint hashes.
- The Merkle root is stored in `commitments.checkpoint_merkle_root`.

### Verification

- CDEL may replay from checkpoint boundaries.
- Checkpoint verification MUST be deterministic under harness control.

## Kernel ISA (KISA-1)

- Artifacts MUST execute within a constrained kernel ISA (KISA-1).
- Allowed primitives include matmul/conv/reduce, elementwise ops, and control flow in IR.
- Arbitrary native code execution is forbidden.
- Kernel backends MUST be differentially tested or verified for semantic consistency.

## Attestation Requirements

- Measurement harness must verify capsule hashes and Merkle roots against capsule commitments.
- Any deviation from declared determinism or ISA constraints yields FAIL.
