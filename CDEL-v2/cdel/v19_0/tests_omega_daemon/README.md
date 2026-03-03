# tests_omega_daemon

> Path: `CDEL-v2/cdel/v19_0/tests_omega_daemon`

## Mission

Verification and regression coverage for deterministic behavior and contract safety.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories


## Key Files

- `test_budget_no_k_times_official_eval_v1.py`: Python module or executable script.
- `test_candidate_precheck_dispatch_guard_v1.py`: Python module or executable script.
- `test_epistemic_airlock_v1.py`: Python module or executable script.
- `test_epistemic_pin_and_multimodal_v1.py`: Python module or executable script.
- `test_epistemic_usable_gate_static_v1.py`: Python module or executable script.
- `test_extension_proposal_public_only_guardrail_v1.py`: Python module or executable script.
- `test_frontier_hard_lock_v1.py`: Python module or executable script.
- `test_hard_task_observation_deltas_v1.py`: Python module or executable script.
- `test_long_run_discipline_v1.py`: Python module or executable script.
- `test_long_run_preflight_summary_v1.py`: Python module or executable script.
- `test_opcode_table_lifecycle.py`: Python module or executable script.
- `test_phase4c_real_swap_drill_v1.py`: Python module or executable script.
- `test_policy_vm_phase1.py`: Python module or executable script.
- `test_policy_vm_replay_and_microkernel.py`: Python module or executable script.
- `test_promoter_routes_ext_winner_to_queue_v1.py`: Python module or executable script.
- `test_promoter_routes_patch_winner_to_ccap_v1.py`: Python module or executable script.
- `test_proposer_arena_agent_dispatch_v1.py`: Python module or executable script.
- `test_proposer_arena_backlog_limits_v1.py`: Python module or executable script.
- `test_proposer_arena_quarantine_on_holdout_violation_v1.py`: Python module or executable script.
- `test_proposer_arena_selection_determinism_v1.py`: Python module or executable script.
- `test_shadow_j_eval_receipt_metrics_v1.py`: Python module or executable script.
- `test_state_verifier_replay_fail_detail_v1.py`: Python module or executable script.
- `test_subverifier_nontriviality_cert_guard_v1.py`: Python module or executable script.

## File-Type Surface

- `py`: 23 files

## Operational Checks

```bash
ls -la CDEL-v2/cdel/v19_0/tests_omega_daemon
find CDEL-v2/cdel/v19_0/tests_omega_daemon -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/v19_0/tests_omega_daemon | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
