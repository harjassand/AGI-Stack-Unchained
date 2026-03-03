# tests

> Path: `baremetal_lgp/tests`

## Mission

Verification and regression coverage for deterministic behavior and contract safety.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `.gitkeep`: project artifact.
- `agent1_vm_core.rs`: Rust source module.
- `agent1_vm_jit.rs`: Rust source module.
- `agent2_oracle_complex_family.rs`: Rust source module.
- `agent2_oracle_funnel_and_full_eval.rs`: Rust source module.
- `agent2_oracle_proxy_schedule.rs`: Rust source module.
- `agent3_outerloop.rs`: Rust source module.
- `agent3_search_library.rs`: Rust source module.
- `apf3_a64_scan_denylists.rs`: Rust source module.
- `apf3_branch_in_slot.rs`: Rust source module.
- `apf3_end2end_workers1_replay.rs`: Rust source module.
- `apf3_metachunk_support_query.rs`: Rust source module.
- `apf3_morphism_identity.rs`: Rust source module.
- `apf3_profiler_taxonomy.rs`: Rust source module.
- `apf3_sfi_memory_escape.rs`: Rust source module.
- `apfsc_phase1_bank.rs`: Rust source module.
- `apfsc_phase1_e2e.rs`: Rust source module.
- `apfsc_phase1_ingress.rs`: Rust source module.
- `apfsc_phase1_judge.rs`: Rust source module.
- `apfsc_phase1_lanes.rs`: Rust source module.
- `apfsc_phase1_scir.rs`: Rust source module.
- `apfsc_phase2_constellation.rs`: Rust source module.
- `apfsc_phase2_e2e.rs`: Rust source module.
- `apfsc_phase2_judge.rs`: Rust source module.
- `apfsc_phase2_normalization.rs`: Rust source module.
- ... and 56 more files.

## File-Type Surface

- `rs`: 80 files
- `gitkeep`: 1 files

## Operational Checks

```bash
ls -la baremetal_lgp/tests
find baremetal_lgp/tests -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files baremetal_lgp/tests | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
