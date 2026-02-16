# Archive Distillation (Normative)

## Scope
This document defines the normative requirements for primitive promotion, archive retention, distillation operators, dependency tracking, and determinism for archive updates. It applies to Genesis-side archives and any CDEL-side audit of archive artifacts.

## Normative Defaults
- Archive updates MUST be deterministic under a fixed seed and identical inputs.
- Distillation operators MUST be bounded in compute and data access.
- Primitive promotion MUST be auditable via provenance and evidence references.

## Primitive Promotion Criteria
A candidate primitive MAY be promoted only if all are true:
1. It has a valid capsule hash and schema-valid capsule bytes.
2. It has a passing Shadow-CDEL result under one-sided screening with recorded evidence.
3. If the primitive is intended for deployment, it has at least one PASS receipt from CDEL (binary-only boundary) and the receipt verifies.
4. It satisfies non-triviality checks (baseline improvement or equivalent) for its artifact type.
5. It declares explicit effects and does not exceed allowed effect policies for its target grade.

Promotion MUST record:
- Capsule hash and parents.
- Operator sequence used for creation.
- Evidence references (receipt hash or Shadow transcript hash).
- Dependency tags (shared data, shared randomness).

## Retention Policy
- The archive MUST retain the latest promoted version of each primitive (by capsule hash).
- The archive MAY retain older versions if required for provenance or reproduction; if retained, their status MUST be marked as superseded.
- Retention decisions MUST be deterministic and policy-driven (e.g., retain last N per descriptor bucket).

## Distillation Operators
Distillation operators MUST obey:
- Deterministic ordering of inputs (stable sort by capsule hash).
- Bounded compute (explicit caps on number of candidates examined and transformations applied).
- No network access and no private holdout access.
- Output capsules MUST include provenance referencing all source capsule hashes used in distillation.

## Dependency Tracking
Each promoted primitive MUST include dependency metadata:
- Shared data sources (dataset ids or handles).
- Shared randomness identifiers (seed policies or commitment ids).
- Upstream component hashes (if composed).

If dependency independence is not certified, downstream composition MUST assume dependence and apply conservative failure-probability accounting.

## Determinism Requirements
- Archive update order MUST be stable (lexicographic by capsule hash or equivalent).
- Archive records MUST be written in canonical JSON with stable key ordering.
- Any derived identifiers (e.g., primitive ids) MUST be computed deterministically from inputs.
