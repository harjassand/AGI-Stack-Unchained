# CDEL Evaluate Protocol (Level-1)

This document defines the boundary protocol between Genesis and CDEL. CDEL is a binary-only interactive oracle that returns PASS or FAIL. A receipt is returned only on PASS.

## Interface

```
Evaluate(epoch_id, capsule, bid) -> PASS | FAIL (+ receipt on PASS)
```

### Inputs

- `epoch_id` (string): active spec epoch identifier.
- `capsule` (object): Artifact Capsule conforming to `schema/capsule.schema.json`.
- `bid` (object): explicit budget request for this evaluation. MUST match `capsule.budget_bid` exactly. Any mismatch yields FAIL.

### Output

- `PASS` or `FAIL` (single bit). No other return data on FAIL.
- On PASS only, a signed receipt is returned.

## Receipt (PASS only)

Receipt is a signed object that MUST bind the following fields:

- `capsule_hash` (hash of the canonical capsule bytes)
- `epoch_id`
- `budgets_spent`:
  - `alpha_spent`
  - `privacy_spent` (`epsilon_spent`, `delta_spent`)
  - `compute_spent` (actual compute units and wall time)
- `rng_commitment_id` (commitment to evaluator randomness)
- `measurement_transcript_hash` (hash of the evaluation transcript)
- `admission_token` (unique signed admission identifier)
- `signature` (object with `alg`, `key_id`, `signature_base64`)

Receipt structure MUST conform to `schema/receipt.schema.json`.

Receipt format is canonical JSON with a fixed field order for hashing.

Money-like budget fields (`alpha_spent`, `epsilon_spent`, `delta_spent`) MUST be canonical decimal strings (not JSON numbers).

## Protocol Steps (Normative)

1. **Admission Gate**
   - CDEL validates `capsule` against the Level-1 schema.
   - CDEL validates `bid` matches `capsule.budget_bid`.
   - CDEL checks all ledgers (AlphaLedger, PrivacyLedger, ComputeLedger).
   - If any check fails, return FAIL.

2. **Commitment Setup**
   - CDEL commits to evaluator randomness and datasets using a commit-reveal scheme.
   - CDEL records `rng_commitment_id` in the evaluation transcript.

3. **Evaluation**
   - CDEL executes the measurement harness using only the allowed effects and runtime kernel ISA.
   - CDEL applies the statistical decision rule specified in the capsule.
   - CDEL applies robustness evaluation limited to certified slice families or DRO sets.
   - CDEL applies causal identifiability checks for CAUSAL_MODEL capsules.

4. **Ledger Updates**
   - On acceptance, AlphaLedger and PrivacyLedger are updated using the actual spend.
   - On rejection, ledgers may still be charged (implementation-defined but MUST be conservative).

5. **Receipt Generation (PASS only)**
   - CDEL produces a receipt binding the measurement transcript hash, budgets spent, and the capsule hash.
   - CDEL signs the receipt and returns it alongside PASS.

6. **No Extra Disclosure**
   - CDEL returns no additional information on FAIL.
   - Timing, size, and formatting MUST be constant within coarse buckets (see PrivacyLedger spec).

## Canonical Capsule Hashing

- Canonicalization MUST follow the capsule's `canonicalization` field (GCJ-1 for Level-1; see `docs/canonicalization.md`).
- Hash function: SHA-256.
- `capsule_hash` is computed over the canonical capsule JSON with `commitments.capsule_hash` set to 64 zero hex.
- CDEL MUST recompute the hash and FAIL if it does not match `commitments.capsule_hash`.

## Failure Semantics

- FAIL provides no diagnostic details.
- FAIL does not reveal which ledger constraint or test caused rejection.
- Repeated calls with the same capsule and bid MUST be rejected within the same epoch.

## Audit Requirements

CDEL MUST retain an audit log containing:
- Input capsule hash and epoch id
- Ledger decisions
- Transcript hash
- Receipt (if PASS)

Audit logs are internal and MUST NOT be exposed to Genesis.
