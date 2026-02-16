# Level-2 Implementation Mapping (Repo-Agnostic)

This document maps Level-1 normative specs to logical implementation owners and required tests. It does not assume any specific CDEL codebase layout.

## CDEL Implementation Ownership

### Capsule Ingestion

- **Schema validation**: validate capsules and receipts against `schema/capsule.schema.json` and `schema/receipt.schema.json`.
- **Canonicalization + hashing**: GCJ-1 canonicalization and SHA-256 hash validation for capsules and receipts.
- **Effect permission enforcement**: deny by default for `network` and `filesystem_write`; only allow explicitly listed effects.
- **Commitment checks**: verify `commitments.capsule_hash` and `commitments.checkpoint_merkle_root`.

### Ledgers

- **AlphaLedger**: implement DeploymentGrade alpha-spending schedule and ResearchGrade LORD updates.
- **PrivacyLedger**: DP accounting (RDP + conversion), query caps, and side-channel discipline.
- **ComputeLedger**: enforce compute caps and adversary strength budgets.

### Evaluate Boundary

- **Bid matching**: reject if `Evaluate(..., bid)` does not match `capsule.budget_bid`.
- **PASS receipt generation**: bind capsule hash, epoch id, budgets spent, transcript hash, and randomness commitment id.
- **Binary-only response**: PASS/FAIL only; receipt returned only on PASS.

## Genesis Implementation Ownership

### Shadow-CDEL Screen

- One-sided LCB/CS rule with explicit `eta` bound.
- Only public or non-sensitive data; no private holdouts.

### Promotion Policy

- Enforce per-epoch call caps and refusal rules.
- Spend `alpha/epsilon/compute` only after PASS_shadow + stability criteria.

### Experiment Capsule Executor

- Runs `EXPERIMENT` capsules with simulator-only effects.
- Enforces reproducibility and resource caps.

## Minimal Conformance Tests (Black-Box)

### Capsule and Receipt Validation

- Invalid capsule schema ⇒ FAIL before any ledger spend.
- Receipt schema invalid ⇒ verification fails.
- Capsule hash mismatch ⇒ receipt verification fails.

### AlphaLedger

- Alpha-spending schedule never exceeds `alpha_total` over N attempts.
- ResearchGrade LORD wealth never negative; refusal on exhaustion.

### PrivacyLedger

- Refuse evaluation once `epsilon_total` or `delta_total` exhausted.
- Responses remain binary-only under repeated queries.

### ComputeLedger

- Refuse evaluation if compute caps are exceeded.
- Adversary strength bound enforced.

### Evaluate Boundary

- Bid mismatch ⇒ FAIL without evaluation.
- PASS receipt includes all required bindings and verifies.

### Shadow-CDEL

- PASS_shadow implies stated `eta` bound is satisfied for the screening rule.
- Shadow-CDEL never reads private holdouts (audit by data handles).

### Promotion Policy

- Repeated calls for same capsule hash in one epoch are refused.
- Promotion attempts stop after `N_promote_max`.
