# Activation Protocol v1

This document defines the v1.4 activation state machine and ledger semantics.

## States

- `STAGED`: bundle present in staging area, not active
- `VERIFIED`: kernel receipt is VALID
- `CANARY_OK`: deterministic canary checks passed
- `COMMITTED`: ACTIVE_BUNDLE updated
- `ROLLED_BACK`: ACTIVE_BUNDLE restored to PREV

## Commands

### Stage (`meta_core_stage.py`)

- Inputs: `--bundle-dir <abs>`, `--work-dir <abs>`
- Outputs: writes canonical `stage.json`
- Copies bundle into a content-addressed staging area
- Computes and records all required hashes

### Verify (`meta_core_verify.py`)

- Inputs: staged descriptor, `--receipt-out <abs>`
- Outputs: canonical `receipt.json`
- Runs the kernel verifier on the staged bundle

### Canary (`meta_core_canary.py`)

Deterministic veto-only checks:

- rerun verification on the staged bundle
- recompute and compare all hashes
- no nondeterministic checks

### Commit (`meta_core_commit.py`)

Atomic pointer swap:

1. write `PREV_ACTIVE_BUNDLE`
2. write `ACTIVE_BUNDLE`
3. append ledger entry

Must be crash-safe (tmp + fsync + rename + fsync dir).

### Rollback (`meta_core_rollback.py`)

Atomic swap:

- `ACTIVE_BUNDLE ← PREV_ACTIVE_BUNDLE`
- append rollback ledger entry

Optional `--reason` is recorded in the ledger entry.

## Ledger entry schema (minimum)

Each entry is GCJ1 canonical JSON with at least:

- `seq` (monotone, derived)
- `prev_entry_hash`
- `action`: `"COMMIT"` or `"ROLLBACK"`
- `active_bundle_hash`
- `prev_active_bundle_hash`
- `receipt_hash`
- `meta_hash`
- `kernel_hash`
- `toolchain_merkle_root`

An `entry_hash` is computed as `sha256(GCJ1(entry_without_entry_hash))`
and appended to the entry.
