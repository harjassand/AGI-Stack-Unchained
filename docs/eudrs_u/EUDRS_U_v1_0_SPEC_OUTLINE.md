# EUDRS-U v1.0 Spec Outline (Repo-Compatible Template)

This is a spec template designed to integrate cleanly with the existing AGI Stack repository structure and constraints (GCJ-1 canonical JSON, RE1/RE2/RE3/RE4 acceptance path, v19 axis/continuity rules).

## 1) Scope & Non-Negotiable Invariants

- Authority model (RE1-RE4) and acceptance path
- Determinism model (DC-1): canonical JSON + Q32 + pinned ordering + pinned PRNG
- Fail-closed policy: define "reject" and "safe-halt" precisely
- Additive growth model: immutable SHA256-addressed artifacts + root updates only

## 2) Definitions & Mapping To Repo Primitives

- Map EUDRS-U terminology to existing artifacts/modules:
  - `policy_hash`, `registry_hash`, `objectives_hash`, `budgets_hash`
  - `omega_trace_hash_chain_v1`
  - `omega_promotion_receipt_v1`, `omega_activation_binding_v1`
  - v19: `axis_upgrade_bundle_v1`, `axis_gate_failure_v1`
- Explicitly note which referenced "base systems" are not present as named components (e.g., QXWMR/CTC/DEP++) and define them as new artifacts/contracts.

## 3) Artifact Inventory (Normative)

For each artifact type, specify:

- `schema_name` / `schema_version` / `schema_version` (repo convention varies by family; pick one and be consistent)
- canonical JSON constraints (GCJ-1; no floats)
- hash identity rule (`sha256:canon_bytes(payload_without_id)`)
- required fields, types, and allowed enums
- any bound hashes to other artifacts (root hashes, chain tails)

Minimum set to define for EUDRS-U:

- `eudrs_u_promotion_v1` (promotion "summary/binding" object)
- `cac_v1` (Counterfactual Advantage Certificate)
- `ufc_v1` (Utility-Flow Certificate)
- `cooldown_ledger_v1`
- `ml_index_root_v1`, `ml_index_page_v1` (and codebook artifacts)
- `weights_root_v1`, `weights_block_v1` (Merkle-sharded Q32 tensors)
- `train_step_digest_v1`, `eval_step_digest_v1`, `onto_step_digest_v1`, `mem_step_digest_v1`
- `ontology_root_v1`, `concept_def_v1`, `strategy_root_v1`, `strategy_def_v1`, `capsule_root_v1`

## 4) Deterministic Execution Semantics (DC-1)

- Q32 arithmetic rules (overflow/saturation rules must be explicit)
- total ordering rules:
  - candidate enumeration order
  - reduction order
  - tie-break rules: `(score desc, id asc)`
- PRNG:
  - seeding formula
  - stream IDs
  - consumption order rules
- "No floats" rule and allowed numeric encodings

## 5) Replay & Verification Requirements (RE2)

Specify exactly what RE2 must recompute:

- dataset decoding + batch ordering
- canonical state packing
- retrieval traversal + candidate set definition
- concept expansion/compression and write-set enforcement
- capsule execution semantics and trace hashing
- world-model, planning expansions, tie breaks
- training loss + updates (Q32)
- CAC/UFC computation (paired base/counterfactual)
- stability metrics (drift, alias mass, bucket balance, etc.)

Define the divergence predicate:

- which roots must match
- which chain tails must match
- which receipts must be present

## 6) Gating Predicates (Fail-Closed)

Define each gate as a deterministic predicate over canonical artifacts:

- CAC thresholds
- Ontology stability gates STAB-G0..G5
- Retrieval/memory gates MEM-G1/MEM-G2
- Ladder-Adjoint conservation (LA-SUM) and exact Q32 equality
- Regression floors

Define:

- the error code to emit on failure
- whether failure is "reject" vs "safe-halt"

## 7) Promotion Bundle Integration

Describe how EUDRS-U artifacts are packaged for promotion in this repo:

- touched paths constraints (omega allowlists; CCAP allowlists)
- meta-core promotion bundle layout
- activation binding semantics
- v19 axis bundle requirement if touching governed prefixes:
  - define `axis_upgrade_bundle_v1` fields you will emit
  - define `morphism_type` taxonomy mapping to ladder levels

## 8) Implementation Plan (Incremental, Compatible)

Provide a staged roadmap aligned with repo constraints:

1. Conformance primitives (canonical binary layouts/digests; golden traces)
2. ML-Index artifacts + gates
3. CAC/UFC artifacts + paired eval runner
4. Ontology gates + cooldown ledger
5. Ladder-Adjoint enforcement
6. Large-scale deterministic training integration

For each stage:

- files/modules to add in `CDEL-v2/cdel/v18_0/` (RE2)
- schemas to add in `Genesis/schema/v18_0/` (RE4)
- tests to add (prefer mirroring existing test patterns in `CDEL-v2/cdel/v18_0/tests_*` and top-level `test_v19_*`)

## 9) Acceptance Criteria (Engineering-Checkable)

Define reproducible checks:

- unit tests that must pass
- determinism tests that must pass (same seed, same artifacts, byte-identical)
- a smoke run that produces:
  - promotion receipt(s)
  - CAC/UFC roots
  - v19 axis bundles (if governed prefixes touched)
  - a level attainment report that is stable across replays

