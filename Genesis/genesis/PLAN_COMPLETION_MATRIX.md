# Plan Completion Matrix

This matrix maps every Phase-1 → Phase-5 requirement to implementation files and verification evidence. Specpack is pinned to v1.0.1; all budgets are decimal strings.

## Phase 1 — Level-1 Spec Pack (Schema/Protocol/Ledgers/TCB/Determinism)

- Capsule schema + examples
  - Implementation: `schema/capsule.schema.json`, `examples/*.capsule.json`
  - Evidence: `run_checks.sh`, `tools/validate_schema.py`
- Receipt schema + verification
  - Implementation: `schema/receipt.schema.json`, `tools/verify_receipt.py`
  - Evidence: `run_checks.sh`
- Evaluate protocol (binary-only boundary)
  - Implementation: `docs/evaluate_protocol.md`, `api/evaluate_v1.openapi.yaml`
  - Evidence: conformance harness (`conformance/`)
- Ledgers (Alpha/Privacy/Compute)
  - Implementation: `docs/alpha_ledger.md`, `docs/privacy_ledger.md`, `docs/compute_ledger.md`, `ledger_sim/`
  - Evidence: ledger sims (`ledger_sim/*_sim.py`)
- Contracts and robustness
  - Implementation: `docs/contract_taxonomy.md`, `docs/contract_calculus.md`, `docs/robustness_spec.md`
  - Evidence: conformance harness + CDEL tests
- Assumptions (quantified, causal witness rule)
  - Implementation: `docs/assumptions_spec.md`
  - Evidence: CDEL witness checks (`cdel/cdel/specpack/causal_eval.py`)
- Determinism/attestation + TCB
  - Implementation: `docs/determinism_attestation.md`, `docs/tcb_boundary.md`
  - Evidence: CDEL transcript + audit chain tests (`cdel/tests/test_audit_log_integrity.py`)

## Phase 2 — Shadow-CDEL + Genesis internal evaluation semantics

- Shadow one-sided screening
  - Implementation: `docs/shadow_cdel.md`, `genesis/shadow_cdel/*`
  - Evidence: Genesis tests (`genesis/tests/test_shadow_*.py`)
- Genesis search loop + CEGIS repair
  - Implementation: `genesis/core/search_loop.py`, `genesis/core/operators.py`, `genesis/core/counterexamples.py`
  - Evidence: deterministic run logs (`genesis/GENESIS_END_TO_END_V0_3_VERIFICATION.txt`)
- Forager and experiments
  - Implementation: `docs/experiment_capsule.md`, `genesis/shadow_cdel/forager.py`
  - Evidence: deterministic logs (v0.3+)
- Promotion policy and binary-only CDEL calls
  - Implementation: `docs/promotion_policy.md`, `genesis/promotion/promote.py`
  - Evidence: `genesis/GENESIS_END_TO_END_V1_2_VERIFICATION.txt`

## Phase 3 — Robustness + adversary budgeting + compute caps

- Robustness adjudication (certified slices / DRO)
  - Implementation: `docs/robustness_spec.md`, `cdel/cdel/specpack/robust_eval.py`
  - Evidence: `cdel/tests/test_stat_dp_robust.py`
- DP leakage control
  - Implementation: `cdel/cdel/specpack/dp_eval.py`, PrivacyLedger
  - Evidence: `cdel/tests/test_stat_dp_robust.py`
- Protocol caps / compute budgets
  - Implementation: `cdel/cdel/specpack/protocol_ledger.py`, `cdel/cdel/specpack/ledgers.py`
  - Evidence: `cdel/tests/test_protocol_caps_*.py`

## Phase 4 — Promotion + accumulation semantics

- SYSTEM composition evaluation
  - Implementation: `cdel/cdel/specpack/system_eval.py`, `cdel/cdel/specpack/component_store.py`
  - Evidence: `cdel/tests/test_system_eval.py`
- Non-triviality checks
  - Implementation: `cdel/cdel/specpack/nontriviality_eval.py`, `genesis/shadow_cdel/nontriviality.py`
  - Evidence: `cdel/tests/test_nontriviality_eval.py`
- Promotion certificates + lifecycle
  - Implementation: `cdel/cdel/specpack/promotion_certificate.py`, `cdel/cdel/specpack/receipt_signing.py`
  - Evidence: `cdel/tests/test_promotion_certificate.py`, `cdel/tests/test_certificate_lifecycle.py`
- Release packs and registries
  - Implementation: `genesis/tools/release_pack.py`, `genesis/tools/release_registry.py`
  - Evidence: `genesis/GENESIS_END_TO_END_V1_2_VERIFICATION.txt`

## Phase 5 — Hardening (side-channels, DP validation, alpha proof sketch, red-team)

- Side-channel checklist
  - Implementation: `cdel/docs/side_channel_audit_checklist.md`
  - Evidence: `cdel/tools/hardening/check_side_channel.py`
- DP accountant validation plan
  - Implementation: `cdel/docs/dp_accountant_validation_plan.md`
  - Evidence: `cdel/tools/hardening/validate_dp_accountant.py`
- Alpha ledger proof sketch
  - Implementation: `cdel/docs/alpha_ledger_correctness_proof_sketch.md`
  - Evidence: `cdel/tools/hardening/validate_alpha_ledger.py`
- Red-team plan and tooling
  - Implementation: `cdel/docs/red_team_plan.md`, `cdel/tools/hardening/run_redteam_cases.py`
  - Evidence: `cdel/tools/hardening/run_hardening_suite.py`

## Artifact Type Coverage

- ALGORITHM: `genesis/genesis_run.py`, `cdel/tests/test_harness_execution.py`
- WORLD_MODEL: `genesis/world_model_run.py`, `cdel/tests/test_world_model_eval.py`
- POLICY: `genesis/policy_run.py`, `cdel/tests/test_policy_eval.py`
- CAUSAL_MODEL: `genesis/causal_run.py`, `cdel/tests/test_causal_model_eval.py`
- SYSTEM: `genesis/system_run.py`, `cdel/tests/test_system_eval.py`

## Verification Evidence (Latest)

- Specpack integrity: `run_checks.sh` (specpack root)
- CDEL clean-room logs: `cdel/dist/LEVEL4_7_CLEANROOM_VERIFICATION.txt` (CAUSAL_MODEL) and `cdel/dist/LEVEL4_8_CLEANROOM_VERIFICATION.txt` (hardening suite)
- Genesis end-to-end logs: `genesis/GENESIS_END_TO_END_V1_3_VERIFICATION.txt` (CAUSAL_MODEL)
- Plan closure: `PLAN_CLOSURE_VERIFICATION.txt`

## Residual Assumptions (Explicit)

- Formal proofs are not mechanized; alpha ledger correctness is documented as a proof sketch.
- DP accounting uses basic composition (documented; no advanced accountant claims).
- Sandbox isolation is portable best-effort on non-Linux platforms.
