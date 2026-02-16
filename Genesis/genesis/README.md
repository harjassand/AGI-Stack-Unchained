# Genesis Engine (v1.3)

Genesis is the local search-and-correction engine used by the AGI Stack campaigns to generate, screen, and promote AGI-stack capsules. This folder (`Genesis/genesis`) contains the runnable implementation and artifacts for the ALGORITHM-family search stack (WORLD_MODEL, POLICY, CAUSAL_MODEL, and SYSTEM capsule workflows).

## Purpose and trust boundaries

- This is the RE2-to-RE4 handoff engine implementation under `Genesis/`.
- It does not replace RE4 specs in `Genesis/schema` and `Genesis/docs`; it implements one concrete pathway that those specs constrain.
- Promotion is a two-stage gate: internal Shadow-CDEL screening, then binary-only CDEL evaluation and promotion via a local CDEL server.
- All promoted outputs are expected to be deterministic and replayable, and artifacts should be validated before promotion claims are treated as authoritative.

## Directory map

- `core/` — search and optimization engines.
- `capsules/` — capsule construction and validation utilities.
- `shadow_cdel/` — algorithmic screening and statistical rule checks used before hard verification.
- `promotion/` — preflight checks, budget accounting, server orchestration, and receipt handling.
- `tools/` — release-pack, registry, specpack, and release verification helpers.
- `run_end_to_end_v0_3.py` through `run_end_to_end_v1_3.py` — end-to-end entrypoints per generation.
- `causal_run.py`, `world_model_run.py`, `policy_run.py`, `system_run.py` — artifact-specific run entrypoints.
- `configs/` — baseline and versioned run manifests.
- `genesis/` — nested directory for historical/legacy run artifacts.
- `components[_v*]/` and `receipts[_v*]/` — versioned component and receipt stores.
- `release_packs[_v*]/` and `release_registry_v1_*.jsonl` — packaged output artifacts.
- `tests/` — unit/integration coverage for pipelines and screening.

## High-level flow

1. A versioned config is loaded and normalized to absolute paths.
2. Core search runs produce candidate capsules through `run_causal_search` and companion builders.
3. Candidate list is prefiltered and a pass list is assembled for screening.
4. A local CDEL server is started.
5. Candidate artifacts are evaluated through the `/evaluate` endpoint.
6. Promotion candidates are screened with Shadow-CDEL rules.
7. On PASS, receipts and run logs are materialized.
8. Promotion artifacts are packaged into release packs and appended to release registries.
9. Certificates are optionally verified and revocation checks can be performed (v1.1+ paths).

This flow is intentionally strict about deterministic re-runs and artifact consistency.

## Canonical artifacts

- `genesis_run*.jsonl` — authoritative run log for the active generation.
- `genesis_archive.jsonl` (legacy entrypoint) — archive stream for selected legacy runs.
- `genesis_summary.json` — summary metadata for full-run status.
- `genesis_system_summary.json` — system-candidate summary for the latest local run.
- `library.json` — distilled primitives/library output from candidate synthesis.
- `policy_archive.jsonl` — policy-focused archive output in policy runs.
- `receipts[_v*]/` — PASS/FULL receipt streams and individual receipt files.
- `components[_v*]/` — generated component manifests used by downstream system assembly.
- `release_packs[_v*]/` and `release_pack_<system_hash>/` contents.
- `release_registry_v1_1.jsonl`, `release_registry_v1_2.jsonl` — append-only release append records.

## Versioned entrypoints

### End-to-end generation

- `run_end_to_end_v0_3.sh` -> `run_end_to_end_v0_3.py`
- `run_end_to_end_v0_4.sh` -> `run_end_to_end_v0_4.py`
- `run_end_to_end_v0_5.sh` -> `run_end_to_end_v0_5.py`
- `run_end_to_end_v0_6.sh` -> `run_end_to_end_v0_6.py`
- `run_end_to_end_v0_7.sh` -> `run_end_to_end_v0_7.py`
- `run_end_to_end_v0_8.sh` -> `run_end_to_end_v0_8.py`
- `run_end_to_end_v0_9.sh` -> `run_end_to_end_v0_9.py`
- `run_end_to_end_v1_0.sh` -> `run_end_to_end_v1_0.py`
- `run_end_to_end_v1_1.sh` -> `run_end_to_end_v1_1.py`
- `run_end_to_end_v1_2.sh` -> `run_end_to_end_v1_2.py`
- `run_end_to_end_v1_3.sh` -> `run_end_to_end_v1_3.py`

`run_end_to_end_v1_2.sh` and `run_end_to_end_v1_3.sh` are currently the newest stable versions in this folder.

### Config-backed runs

- `configs/system_v1_2.json` — used by `run_end_to_end_v1_2.py`.
- `configs/system_v1_1.json` — used by `run_end_to_end_v1_1.py`.
- `configs/system_v1_0.json`, `system_v0_9.json`, `system_v0_8.json`, `system_v0_7.json` — legacy generation configs.
- `configs/causal_v1_3.json` — used by `run_end_to_end_v1_3.py`.
- `configs/default.json`, `system.json`, `policy.json`, `policy_envs.json` — auxiliary/default entry points.

## Core module map

### `core/`

- `causal_search.py` — primary synthesis/search driver.
- `policy_search.py` — policy search helper path.
- `world_model_search.py` — world model candidate search flow.
- `search_loop.py` and `operators.py` — search orchestration and transformations.
- `distill.py` — candidate distillation and cleanup.
- `codesign.py` — preflight codesign and integrity check scaffolding.
- `counterexamples.py`, `failure_patterns.py` — forager/counterexample workflow.
- `library.py`, `planning.py` — planning and reusable artifact helpers.

### `capsules/`

- `canonicalize.py` and `validate.py` — deterministic serialization and schema checks.
- `world_model_builder.py`, `policy_builder.py`, `causal_model_builder.py`, `system_builder.py` — capsule builders.
- `receipt.py`, `causal_witness.py`, `seed_capsule.json` — receipt/witness support.

### `shadow_cdel/`

- `shadow_eval.py`, `shadow_causal_eval.py`, `shadow_world_model_eval.py`, `shadow_policy_eval.py`, `shadow_system_eval.py` — algorithmic pre-verification checks.
- `nontriviality.py` and `lcb.py` — conservative gate policy.
- `forager.py` — bounded adversarial test generation.
- `calibration.py`, `baseline_registry.py`, and dataset/policy env registries for reproducible screening.

### `promotion/`

- `preflight.py` and `protocol_budget.py` — preflight validation and budget tracking.
- `server_manager.py` — local CDEL server lifecycle.
- `promote.py` and `receipt_store.py` — promotion wiring and receipt book-keeping.
- `bid_policy.py` — bid/policy selection helpers for candidate acceptance.

### `tools/`

- `verify_specpack_lock.py` — validates pinned specpack lock state.
- `release_pack.py` — constructs release pack tarballs and manifests.
- `release_registry.py` — append-only release registry updates.
- `verify_release_pack.py` — manifest/signature/asset verification.
- `path_utils.py` and `archive_stats.py` — deterministic path and telemetry utilities.
- `redteam_genesis.py` — red-team/scenario tooling.

## Prerequisites

- Python 3.11+.
- Running CDEL source tree for `CDEL_ROOT`.
- For signature verification: signing tooling present in the referenced CDEL tree.

Install local dependencies:

```bash
cd /Users/harjas/AGI-Stack-Clean/Genesis/genesis
python3 -m pip install -r requirements-dev.txt
```

## Setup and quick start

From your shell:

```bash
export CDEL_ROOT=/path/to/CDEL-v2  # required
cd /Users/harjas/AGI-Stack-Clean/Genesis/genesis
./run_end_to_end_v1_2.sh
```

Outputs expected with v1.2:

- `genesis_run_v1_2.jsonl`
- `genesis_system_summary.json`
- `genesis/receipts_v1_2/` (PASS-only receipts)
- `genesis/release_packs_v1_2/`
- `genesis/release_registry_v1_2.jsonl`
- `GENESIS_END_TO_END_V1_2_VERIFICATION.txt`

For reproducible v1.3 runs:

```bash
export CDEL_ROOT=/path/to/CDEL-v2
./run_end_to_end_v1_3.sh
```

Where you need custom paths, set these environment variables:

- `CDEL_ROOT` — required location of checked-out CDEL source.
- `GENESIS_ROOT` — non-default Genesis root for wrapper script usage.
- `CONFIG` — path to a custom versioned config.
- `LEDGER_DIR`, `RECEIPTS_DIR`, `RUN_LOG`, `ARCHIVE_LOG`, `SUMMARY_LOG` — runtime output overrides.

## Validation and checks

```bash
cd /Users/harjas/AGI-Stack-Clean/Genesis/genesis
./run_checks.sh
```

`run_checks.sh` executes:

- `python3 tools/verify_specpack_lock.py`
- `python3 -m pytest`

Optional targeted test sets:

- `python3 -m pytest tests/test_shadow_*.py`
- `python3 -m pytest tests/test_release_pack.py`

## Versioned artifacts and behavior notes

### v1.1

- Runs two independent promotion candidates with key rotation in-between.
- Writes a revocable registry entry for one candidate and a valid entry for the second candidate.
- Demonstrates replay and revocation handling semantics.

### v1.2

- Single deterministic pipeline run.
- Builds and verifies release pack with optional evaluation bundle export.
- Appends release registry entries and enforces signature-based verification.

### v1.3

- Deterministic two-run hash comparison for run logs in one cycle.
- Uses explicit certificate-like verification against selected PASS capsule before success.

## Determinism and operational conventions

- Keep canonical JSON handling stable before hashing/canonicalization-sensitive steps.
- Do not introduce nondeterministic iteration paths in code that impacts digestable output.
- Maintain path normalization and repo-relative references for generated artifacts.
- Use decimal strings for budget values when using existing budget manifests.
- Replay checks are expected to be authoritative for admission claims.

## Files of interest

- `INTEGRATOR_INSTRUCTIONS.md` — integration-oriented command reference.
- `PLAN_COMPLETION_MATRIX.md` — feature-to-file and evidence mapping.
- `GENESIS_END_TO_END_V1_2_VERIFICATION.txt`
- `GENESIS_END_TO_END_V1_3_VERIFICATION.txt`
- `requirements-dev.txt`
- `specpack_lock.json` and `cdel_keystore_v1_1` / `cdel_keystore_v1_2` (where present).

## Operational runbook

### If you see a non-reproducible run

- Confirm `CDEL_ROOT` points to the exact expected code and Python version.
- Clear stale paths (`LEDGER_DIR`, `RECEIPTS_DIR`, component and release directories) and rerun.
- Verify the same `CONFIG` file and `CONFIG`-resolved paths are being used.
- Compare `genesis_run*.jsonl` hashes across reruns before trust decisions.

### If CDEL endpoint is unreachable

- Ensure CDEL server is starting from the correct `CDEL_ROOT` with `cdel` fixtures available.
- Check `/evaluate` reachability in `promotion/server_manager.py` startup logs.
- Validate env overrides for `CDEL_ALPHA_TOTAL`, `CDEL_EPSILON_TOTAL`, and `CDEL_DELTA_TOTAL`.

### If promotion unexpectedly fails after screening pass

- Check shadow rules in `docs/shadow_cdel_rules.md`.
- Confirm budget paths in config and `protocol_budget.json` are not exhausted.
- Inspect receipt index and verify signature/certificate path order in the target run version.

## Notes

- The `genesis/` tree contains multiple historical generations retained for replay and audit.
- Use the latest generation scripts for production-like validation and keep older generations for forensics.
- All paths above are repo-relative under this working tree unless explicitly stated otherwise.
