# Last 3 Days Implementation Audit (2026-02-28 to 2026-03-02)

## Metadata
- Repository: `AGI-Stack-Unchained`
- Audit window (Australia/Brisbane, UTC+10): `2026-02-28 00:00:00` to `2026-03-02 23:59:59`
- Included commits: non-merge commits in window
- Included state: committed history + current uncommitted working-tree delta (as of 2026-03-02)
- Evidence sources: git commit history, code diffs, test files, generated runtime/probe artifacts under `docs/`

## 1) Quantitative Summary

### 1.1 Commit volume
- Total implementation commits in window: **11**
- By day:
  - 2026-02-28: 2 commits
  - 2026-03-01: 8 commits
  - 2026-03-02: 1 commit

### 1.2 Diff volume (sum across 11 commits)
- Files changed (summed per commit): **845**
- Insertions: **75,631**
- Deletions: **843**

### 1.3 Diff volume by day
- 2026-02-28: 84 files, 19,770 insertions, 102 deletions
- 2026-03-01: 698 files, 43,285 insertions, 287 deletions
- 2026-03-02: 63 files, 12,576 insertions, 454 deletions

### 1.4 Dominant subsystems touched (by path-frequency over changed files)
- `baremetal_lgp/src/apfsc/*`: 237 touches
- `baremetal_lgp/fixtures/apfsc/*`: 109 touches
- `baremetal_lgp/src/bin/*`: 61 touches
- `baremetal_lgp/src/apf3/*`: 13 touches
- `baremetal_lgp/src/jit2/*`: 12 touches
- `baremetal_lgp/src/oracle3/*`: 7 touches
- `baremetal_lgp/.apfsc/*` artifact snapshots: high volume, primarily from runtime artifact capture commit

## 2) Chronological Implementation Detail

## 2.1 2026-02-28

### Commit `5b939765c4f948aa0df1be028f1e3589995af91e`
- Subject: `Implement Phase 3 compile-to-chunk oracle and deterministic death`
- Author/time: Codex Runner, 2026-02-28 01:19:50 +1000
- Diff stats: 54 files, 14,477 insertions, 101 deletions

#### What this commit implemented
- Added a compile-to-chunk Oracle v3 pipeline:
  - Chunk representation and digesting in `baremetal_lgp/src/oracle3/chunkpack.rs`
  - Compilation and schedule validation in `baremetal_lgp/src/oracle3/compile.rs`
  - Program validity/cost checks in `baremetal_lgp/src/oracle3/validity.rs`
- Added raw JIT execution hardening:
  - Trap/signal handling and timeout classification in `baremetal_lgp/src/jit2/raw_runner.rs`
  - SIGALRM timeout semantics (`TRAP_SIGALRM`) and sniper integration (`baremetal_lgp/src/jit2/sniper.rs`)
  - Full state wipe before each episode (deterministic reset behavior)
- Added co-evolution outer loop components and phase3 oracle linkage in `baremetal_lgp/src/outer_loop/coev.rs` and related modules
- Added audit/handoff markdown artifacts:
  - `baremetal_lgp/PHASE1_THROUGHPUT_UNCORKING_AUDIT.md`
  - `baremetal_lgp/PHASE2_RAWJIT_SUBSTRATE_ESCAPE_HANDOFF.md`
  - `baremetal_lgp/PHASE3_IMPLEMENTATION_AUDIT.md`

#### Evidence
- Function-level additions observed in diff include:
  - `compile.rs`: compile and schedule validation path
  - `raw_runner.rs`: trap handling, timeout mapping, deterministic wipes
  - `outer_loop/coev.rs`: league/archive update and mutation routines
- Concrete code anchors (current tree):
  - `baremetal_lgp/src/oracle3/compile.rs:95` (compile entry path)
  - `baremetal_lgp/src/oracle3/compile.rs:142` (schedule validation)
  - `baremetal_lgp/src/oracle3/chunkpack.rs:4` (chunkpack struct)
  - `baremetal_lgp/src/oracle3/validity.rs:58` (cost validity checks)
  - `baremetal_lgp/src/jit2/raw_runner.rs:13` (`TRAP_SIGALRM`)
  - `baremetal_lgp/src/jit2/raw_runner.rs:149` (full state wipe)
  - `baremetal_lgp/src/jit2/sniper.rs:33` (sniper start)
- Test artifacts added in commit include:
  - `baremetal_lgp/tests/dod_acceptance_phase3.rs`
  - `baremetal_lgp/tests/phase2_rawjit_regsave.rs`
  - `baremetal_lgp/tests/phase2_rawjit_sniper.rs`
  - `baremetal_lgp/tests/phase2_rawjit_statewipe.rs`
  - `baremetal_lgp/tests/phase2_rawjit_traps.rs`
  - `baremetal_lgp/tests/phase3_oracle.rs`

### Commit `cc682c1f0dfaa4d67e07d75ee10ac40e315067fc`
- Subject: `Add APF-v3 module with deterministic wake/judge/omega pipeline`
- Author/time: Codex Runner, 2026-02-28 10:28:31 +1000
- Diff stats: 30 files, 5,293 insertions, 1 deletion

#### What this commit implemented
- Introduced APF-v3 runtime module under `baremetal_lgp/src/apf3/`:
  - Wake path (`wake.rs`): candidate generation, digest formation, run digest output
  - Judge path (`judge.rs`): deterministic heldout/anchor evaluation with deterministic reject receipts
  - Omega architecture path (`omega.rs`): proposal loading and reject emission
  - AArch64 safety scanning and SFI checks (`a64_scan.rs`, `sfi.rs`)
- Added APF-v3 binaries:
  - `apf3_wake_hotloop`
  - `apf3_judge_daemon`
  - `apf3_omega_architect`
- Added module-specific tests covering scan safety, branch-slot policy, replay determinism, support/query behavior, profiler taxonomy, and SFI escapes

#### Evidence
- Key code anchors:
  - `baremetal_lgp/src/apf3/wake.rs:48` (`run_wake`)
  - `baremetal_lgp/src/apf3/judge.rs:52` (`run_judge`)
  - `baremetal_lgp/src/apf3/omega.rs:13` (proposal load)
  - `baremetal_lgp/src/apf3/a64_scan.rs` (denylist scanner)
- Determinism evidence in wake/judge code paths:
  - `wake.rs` contains digest chaining and persisted `run_digest.txt`
  - `judge.rs` emits deterministic reject/promote receipts and run digest
- Binary entry points:
  - `baremetal_lgp/src/bin/apf3_wake_hotloop.rs:26`
  - `baremetal_lgp/src/bin/apf3_judge_daemon.rs:20`
  - `baremetal_lgp/src/bin/apf3_omega_architect.rs:43`
- Tests added:
  - `baremetal_lgp/tests/apf3_a64_scan_denylists.rs`
  - `baremetal_lgp/tests/apf3_branch_in_slot.rs`
  - `baremetal_lgp/tests/apf3_end2end_workers1_replay.rs`
  - `baremetal_lgp/tests/apf3_sfi_memory_escape.rs`

## 2.2 2026-03-01

### Commit `565e5a1aa300121fd124fae4aba83eb06f76c2f2`
- Subject: `Add APF-SC Phase 1 MVP end-to-end implementation (#21)`
- Author/time: Harjas Sandhu, 2026-03-01 00:26:30 +1000
- Diff stats: 71 files, 9,170 insertions

#### What this commit implemented
- Established APF-SC Phase 1 foundation:
  - Artifact layout, pointering, snapshot persistence
  - Ingress for prior/reality/substrate packs
  - Judge engine and lane execution framework
  - SCIR verification/interpreter core
  - Binaries for seed init, ingestion, epoch run, judge daemon, public eval, shadow canary
- Added initial fixtures and Phase 1 spec/task docs

#### Evidence
- Core artifact layer:
  - `baremetal_lgp/src/apfsc/artifacts.rs:12` (`ensure_layout`)
  - `baremetal_lgp/src/apfsc/artifacts.rs:129` (`write_pointer`)
  - `baremetal_lgp/src/apfsc/artifacts.rs:162` (`store_snapshot`)
- Ingress entry points:
  - `baremetal_lgp/src/apfsc/ingress/prior.rs:17` (`ingest_prior`)
  - `baremetal_lgp/src/apfsc/ingress/reality.rs:17` (`ingest_reality`)
  - `baremetal_lgp/src/apfsc/ingress/substrate.rs:14` (`ingest_substrate`)
- Lane generation surfaces:
  - `baremetal_lgp/src/apfsc/lanes/truth.rs:10` (`truth generate`)
  - `baremetal_lgp/src/apfsc/lanes/equivalence.rs:13` (`equivalence generate`)
  - `baremetal_lgp/src/apfsc/lanes/incubator.rs:20` (`incubator generate`)
- Test coverage introduced:
  - `apfsc_phase1_bank.rs`, `apfsc_phase1_ingress.rs`, `apfsc_phase1_lanes.rs`, `apfsc_phase1_judge.rs`, `apfsc_phase1_scir.rs`, `apfsc_phase1_e2e.rs`

### Commit `48c235f72b5a4ca6608cbaac4970018c22189ac9`
- Subject: `Add APF-SC runtime artifact snapshot and Phase 2 MVP docs (#22)`
- Author/time: Harjas Sandhu, 2026-03-01 00:27:52 +1000
- Diff stats: 191 files, 5,011 insertions

#### What this commit implemented
- Captured runtime state snapshot into `baremetal_lgp/.apfsc/*`:
  - Candidate manifests/build_meta/head/state/schedule packs
  - Pack stores, pointers, receipts, snapshots, banks, archive traces
- Added Phase 2 docs:
  - `docs/apfsc_phase2_mvp_spec.md`
  - `docs/apfsc_phase2_mvp_tasks.yaml`

#### Evidence
- Path concentration from commit file list:
  - 189 paths under `baremetal_lgp/.apfsc/*`
  - 2 docs files under `docs/`
- This commit is operational evidence packaging, not major source-code behavior changes

### Commit `a268a2c345ee0c4adf945689c9e814eb783f99f6`
- Subject: `Implement APF-SC Phase 2 MVP end-to-end`
- Author/time: Codex Runner, 2026-03-01 02:03:15 +1000
- Diff stats: 69 files, 6,577 insertions, 38 deletions

#### What this commit implemented
- Added Phase 2 constellation and scoring layer:
  - Family bank persistence/loading and panel windowing
  - Static/transfer/robust normalization + protection floor handling
  - Phase 2 canary execution path
- Added Phase 2 fixtures and tests for determinism, judge behavior, normalization, robustness, specialist rejection, transfer checks

#### Evidence
- Core code anchors:
  - `baremetal_lgp/src/apfsc/constellation.rs:24` (`build_constellation`)
  - `baremetal_lgp/src/apfsc/bank.rs:442` (`persist_family_bank`)
  - `baremetal_lgp/src/apfsc/bank.rs:460` (`load_family_panel_windows`)
  - `baremetal_lgp/src/apfsc/archive/error_atlas.rs:75` (`update_family_error_atlas`)
  - `baremetal_lgp/src/apfsc/config.rs:684` (`phase2_policy`)
  - `baremetal_lgp/src/apfsc/normalization.rs:268` (weighted static scoring)
  - `baremetal_lgp/src/apfsc/canary.rs:164` (`run_phase2_canary`)
- Test evidence (added/expanded):
  - `baremetal_lgp/tests/apfsc_phase2_constellation.rs`
  - `baremetal_lgp/tests/apfsc_phase2_e2e.rs`
  - `baremetal_lgp/tests/apfsc_phase2_judge.rs`
  - `baremetal_lgp/tests/apfsc_phase2_normalization.rs`
  - `baremetal_lgp/tests/apfsc_phase2_robustness.rs`
  - `baremetal_lgp/tests/apfsc_phase2_specialist_reject.rs`
  - `baremetal_lgp/tests/apfsc_phase2_transfer.rs`

### Commit `31649bca16958e0b581c1b2ebbd62492658095c8`
- Subject: `apfsc: implement phase3 mvp end-to-end`
- Author/time: Codex Runner, 2026-03-01 03:38:41 +1000
- Diff stats: 91 files, 7,722 insertions, 44 deletions

#### What this commit implemented
- Added Phase 3 macro/scir/bridge/cold-frontier capabilities:
  - Macro mining + registry persistence
  - SCIR v2 lowering/verification and backend equivalence
  - Warm bridge and cold boundary checks
  - Phase3 canary + rollback path handling
- Added Phase 3 fixtures, docs, and extensive phase3 test suite

#### Evidence
- Code anchors:
  - `baremetal_lgp/src/apfsc/macro_mine.rs:12` (`mine_macros`)
  - `baremetal_lgp/src/apfsc/scir/verify.rs:15` (`verify_program`)
  - `baremetal_lgp/src/apfsc/bridge.rs:62` (`evaluate_warm_bridge`)
  - `baremetal_lgp/src/apfsc/bridge.rs:94` (`evaluate_cold_boundary`)
  - `baremetal_lgp/src/apfsc/archive/macro_registry.rs:7` and `:11` (registry + induction receipt appends)
  - `baremetal_lgp/src/apfsc/archive/backend_equiv.rs:7` (backend equiv receipts)
  - `baremetal_lgp/src/apfsc/canary.rs:225` (`run_phase3_canary`)
- Test evidence added:
  - `apfsc_phase3_classifier.rs`
  - `apfsc_phase3_cold_boundary.rs`
  - `apfsc_phase3_e2e_pcold.rs`
  - `apfsc_phase3_e2e_pwarm.rs`
  - `apfsc_phase3_graph_backend.rs`
  - `apfsc_phase3_macro_lowering.rs`
  - `apfsc_phase3_macro_mine.rs`
  - `apfsc_phase3_scir_v2.rs`
  - `apfsc_phase3_canary_rollback.rs`

### Commit `79b02997026dd32ab63cd3e5c1638f524c04edef`
- Subject: `Implement APF-SC Phase 4 end-to-end stack`
- Author/time: Codex Runner, 2026-03-01 04:54:21 +1000
- Diff stats: 126 files, 7,893 insertions, 180 deletions

#### What this commit implemented
- Added Phase 4 class-G/search-law/formal/tool/portfolio flows:
  - Active pointers for search law + formal policy
  - Hidden challenge scheduler and rotation/retirement machinery
  - Search-law offline and A/B evaluation flows
  - Law archive, QD archive, need token, and tool shadow ledgers
  - Formal and tool ingestion + policy enforcement
  - Recombination lane and challenge rotation binary
- Added full phase4 fixtures and broad phase4 tests

#### Evidence
- Code anchors:
  - `baremetal_lgp/src/apfsc/active.rs:6` (`read_active_search_law`)
  - `baremetal_lgp/src/apfsc/active.rs:10` (`write_active_search_law`)
  - `baremetal_lgp/src/apfsc/challenge_scheduler.rs:143` (hidden challenge gate scoring)
  - `baremetal_lgp/src/apfsc/challenge_scheduler.rs:209` (ensure hidden manifest)
  - `baremetal_lgp/src/apfsc/retirement.rs:37` (challenge rotation)
  - `baremetal_lgp/src/apfsc/ingress/formal.rs:16` (formal ingest)
  - `baremetal_lgp/src/apfsc/formal_policy.rs:77` (formal policy application)
  - `baremetal_lgp/src/apfsc/ingress/tool.rs:15` (tool ingest)
  - `baremetal_lgp/src/apfsc/tool_shadow.rs:17` (tool-shadow eval)
  - `baremetal_lgp/src/apfsc/archive/need_tokens.rs:7` (need token append)
  - `baremetal_lgp/src/apfsc/archive/qd_archive.rs:7` (QD append)
  - `baremetal_lgp/src/apfsc/archive/tool_shadow.rs:7` (tool-shadow ledger append)
- Test evidence added:
  - `apfsc_phase4_e2e_architecture.rs`
  - `apfsc_phase4_e2e_full_loop.rs`
  - `apfsc_phase4_e2e_searchlaw.rs`
  - `apfsc_phase4_formal_pack.rs`
  - `apfsc_phase4_hidden_challenge.rs`
  - `apfsc_phase4_judge.rs`
  - `apfsc_phase4_law_archive.rs`
  - `apfsc_phase4_law_tokens.rs`
  - `apfsc_phase4_need_tokens.rs`
  - `apfsc_phase4_portfolio_credit.rs`
  - `apfsc_phase4_qd_archive.rs`
  - `apfsc_phase4_recombination.rs`
  - `apfsc_phase4_searchlaw_ab.rs`
  - `apfsc_phase4_searchlaw_offline.rs`
  - `apfsc_phase4_tool_shadow.rs`

### Commit `e0d90cdb206ac506e07279afac336cd913f0d172`
- Subject: `apfsc phase4: close searchlaw and rotation contract gaps`
- Author/time: Codex Runner, 2026-03-01 05:30:43 +1000
- Diff stats: 8 files, 216 insertions, 17 deletions

#### What this commit implemented
- Tightened Phase4 search-law and challenge-rotation contracts:
  - Config default + contract refinements around search-law safety regression limits
  - Rotation path updates and compatibility checks
  - Added test case for out-of-range A/B epoch count

#### Evidence
- Config and phase4 fields:
  - `baremetal_lgp/src/apfsc/config.rs:319` (Phase4Config)
  - `baremetal_lgp/src/apfsc/config.rs:356` (search-law safety regression field)
  - `baremetal_lgp/src/apfsc/config.rs:1122` (default safety regression)
- Binary contract surface:
  - `baremetal_lgp/src/bin/apfsc_rotate_challenges.rs`
- Test evidence:
  - `baremetal_lgp/tests/apfsc_phase4_searchlaw_ab.rs` includes `searchlaw_ab_rejects_epoch_count_outside_config_range`

### Commit `52704ef00e9cc675df7c1ff5f853cd7678b940e1`
- Subject: `Implement APF-SC production readiness control plane and release tooling`
- Author/time: Codex Runner, 2026-03-01 06:37:25 +1000
- Diff stats: 133 files, 6,361 insertions

#### What this commit implemented
- Added production control-plane subsystem (`baremetal_lgp/src/apfsc/prod/*`):
  - Audit chain
  - Authn/authz token model
  - Control DB schema + WAL semantics
  - Daemon/service/job control plane
  - Backup/restore, compaction, GC, recovery, retention, telemetry, diagnostics
  - Build/release metadata generation and verification hooks
- Added production binaries:
  - `apfscd`, `apfscctl`, `apfsc_backup`, `apfsc_restore`, `apfsc_gc`, `apfsc_compact`, `apfsc_preflight`, `apfsc_release_verify`, `apfsc_migrate`, `apfsc_diag_dump`, `apfsc_qualify`
- Added CI/release workflows and scripts:
  - `.github/workflows/pr-ci.yml`, `nightly-qual.yml`, `release-qual.yml`, `release.yml`
  - `scripts/ci/*.sh`, `scripts/release/*.sh`
- Added production fixtures, configs, ops runbooks/dashboards, fuzz targets, and production tests

#### Evidence
- Production core anchors:
  - `baremetal_lgp/src/apfsc/prod/audit.rs:27` and `:70`
  - `baremetal_lgp/src/apfsc/prod/auth.rs:28`, `:50`, `:66`
  - `baremetal_lgp/src/apfsc/prod/control_db.rs:10`, `:70`, `:224`
  - `baremetal_lgp/src/apfsc/prod/service.rs:203` (request handling)
  - `baremetal_lgp/src/apfsc/prod/service.rs:900` (mutating command classification)
  - `baremetal_lgp/src/apfsc/prod/service.rs:907` (idempotency command materialization)
- Workflow/script anchors:
  - `.github/workflows/pr-ci.yml:1`
  - `.github/workflows/release.yml:1`
  - `.github/workflows/release.yml:13`
  - `.github/workflows/release-qual.yml:13`
  - `baremetal_lgp/scripts/ci/lint.sh:3`
  - `baremetal_lgp/scripts/ci/test_release_qual.sh:3`
  - `baremetal_lgp/scripts/release/build_release.sh:10`
  - `baremetal_lgp/scripts/release/generate_sbom.sh:12`
- Test evidence added:
  - `apfsc_prod_audit.rs`
  - `apfsc_prod_auth.rs`
  - `apfsc_prod_backup_restore.rs`
  - `apfsc_prod_control_db.rs`
  - `apfsc_prod_e2e_daemon.rs`
  - `apfsc_prod_e2e_crash_resume.rs`
  - `apfsc_prod_e2e_release_qual.rs`
  - `apfsc_prod_journal.rs`
  - `apfsc_prod_migrations.rs`
  - `apfsc_prod_preflight.rs`
  - `apfsc_prod_recovery.rs`
  - `apfsc_prod_release_manifest.rs`
  - `apfsc_prod_release_verify.rs`
  - `apfsc_prod_retention_gc.rs`
  - `apfsc_prod_telemetry.rs`
  - `loom_prod_activation.rs`, `loom_prod_leases.rs`

### Commit `a4d3cf922e81205a412f5ede96c177fcd34f6cbb`
- Subject: `Harden production control-plane journaling, backup format, and release state tracking`
- Author/time: Codex Runner, 2026-03-01 06:57:00 +1000
- Diff stats: 9 files, 335 insertions, 8 deletions

#### What this commit implemented
- Added backup integrity hardening:
  - Schema checksum validation in backup verification
- Added control DB compatibility resilience:
  - Busy retry and compatibility-schema evolution path
- Hardened idempotency + journaling behavior in service layer for mutating commands
- Added/updated tests to verify bad schema rejection and journaling idempotency behavior

#### Evidence
- Code anchors:
  - `baremetal_lgp/src/apfsc/prod/backup.rs:28` (`create_backup`)
  - `baremetal_lgp/src/apfsc/prod/backup.rs:85` (`verify_backup`)
  - `baremetal_lgp/src/apfsc/prod/control_db.rs:49` (`with_busy_retry`)
  - `baremetal_lgp/src/apfsc/prod/control_db.rs:192` (`ensure_compat_schema`)
  - `baremetal_lgp/src/apfsc/prod/daemon.rs:19` (`serve_with_on_ready`)
  - `baremetal_lgp/src/apfsc/prod/journal.rs:56` (`has_committed_idempotency`)
- Test evidence:
  - `baremetal_lgp/tests/apfsc_prod_control_db.rs` includes `control_db_rejects_bad_schema_checksum`
  - `baremetal_lgp/tests/apfsc_prod_journal.rs` includes `mutating_commands_are_journaled_and_idempotent`

## 2.3 2026-03-02

### Commit `dfb5cfccb0351abceda12c574f34790960d0c3ed`
- Subject: `apfsc: phase4 crucible, prod daemon resilience, and external ingress tooling (#29)`
- Author/time: Harjas Sandhu, 2026-03-02 13:05:01 +1000
- Diff stats: 63 files, 12,576 insertions, 454 deletions

#### What this commit implemented
- Phase4 crucible expansion and ingress tooling:
  - Added `phase4_crucible_16g.toml`
  - Added external prior fixture (`fixtures/apfsc/phase4/prior_alien/*`)
  - Added ingestion entrypoints/scripts (`apfsc_ingest_external`, shell helper)
- Production resilience hardening:
  - Backup closure copy improvements (required chunks and pointer snapshots)
  - Control DB compatibility/retry updates
  - Daemon readiness path (`serve_with_on_ready`) and lease handling updates
  - GC/tombstone sweep enhancements
- Additional runtime evidence artifacts in `docs/`:
  - `apfsc_phase1_4_evidence_summary_2026-03-01.json`
  - `apfsc_phase1_4_impl_metrics_2026-03-01.json`
  - `apfsc_runtime_timeline_2026-03-01.json`
  - release-probe reports and probe configs

#### Evidence
- Commit path concentration:
  - 36 paths in `baremetal_lgp/src/*`
  - 6 paths in `baremetal_lgp/fixtures/*`
  - docs evidence bundle added
- Key code anchors:
  - `baremetal_lgp/src/apfsc/prod/backup.rs:106` (`snapshot_control_db`)
  - `baremetal_lgp/src/apfsc/prod/backup.rs:141` (`copy_required_chunks`)
  - `baremetal_lgp/src/apfsc/prod/daemon.rs:19` (`serve_with_on_ready`)
  - `baremetal_lgp/src/apfsc/prod/control_db.rs:192` (`ensure_compat_schema`)
- Tests touched:
  - `baremetal_lgp/tests/apfsc_prod_e2e_daemon.rs`

## 3) Runtime/Artifact Evidence Added in Window

### 3.1 APF-SC implementation metrics (`docs/apfsc_phase1_4_impl_metrics_2026-03-01.json`)
- `apfsc_source_summary`:
  - 122 source files
  - 18,126 LOC
  - 575 total functions
  - 317 public functions
- Largest APF-SC source files include:
  - `src/apfsc/orchestrator.rs` (1,931 LOC)
  - `src/apfsc/types.rs` (1,293 LOC)
  - `src/apfsc/config.rs` (1,143 LOC)
  - `src/apfsc/judge.rs` (954 LOC)
- `phase_test_inventory` enumerates phase-scoped test functions across phase1-4

### 3.2 Runtime evidence summary (`docs/apfsc_phase1_4_evidence_summary_2026-03-01.json`)
- Candidate counts by class:
  - S: 61
  - A: 30
  - PWarm: 7
  - PCold: 20
- Pack counts:
  - reality: 20, prior: 3, substrate: 1, formal: 1, tool: 1
- Receipt counts include:
  - ingress: 26
  - public_static/public_transfer/public_robust: 18 each
  - holdout_static: 1
- Active pointers captured include active candidate, constellation, formal policy, and search law hashes

### 3.3 Runtime timeline (`docs/apfsc_runtime_timeline_2026-03-01.json`)
- Count snapshot:
  - searchlaw_trace: 6
  - need_tokens: 2
  - challenge_retirement: 2
  - genealogy: 2
  - hardware_trace: 2
  - snapshots_json_count: 28
- Need-token records and challenge-rotation records included with IDs/hashes/epochs

### 3.4 Release probe reports
- `docs/phase4_release_probe_epoch1_report_2026-03-01.md`
- `docs/phase4_release_probe_epoch1_after_patch2_report_2026-03-01.md`

Observed in reports:
- Initial probe found code-penalty-dominated scoring and `Reject(NoPublicMargin)` incumbent fallback
- After splice-coupling + config/gate rebalancing and constellation rebuild:
  - observed `improved_families > 0` in public_static receipt
  - observed first `Promote` decision in epoch
  - observed architecture-lane candidate reaching canary then failing (`Reject(CanaryFail)`)

## 4) Current Uncommitted Delta (Working Tree on 2026-03-02)

Modified files:
- `baremetal_lgp/fixtures/apfsc/phase4/config/phase4_crucible_16g.toml`
- `baremetal_lgp/src/apfsc/judge.rs`
- `baremetal_lgp/src/apfsc/prod/diagnostics.rs`
- `baremetal_lgp/src/apfsc/searchlaw_eval.rs`
- `baremetal_lgp/tests/apfsc_phase4_searchlaw_ab.rs`

Diff summary: 5 files changed, 138 insertions, 18 deletions.

### 4.1 Behavior changes in uncommitted delta
- Search-law A/B gate made strictly positive-gain-only (no tie acceptance):
  - `baremetal_lgp/src/apfsc/searchlaw_eval.rs:175` (strict nonzero gain check)
  - `baremetal_lgp/src/apfsc/judge.rs:996` (judge-side enforcement)
- Added diagnostics bundle output for Class-G A/B reason distribution window:
  - `baremetal_lgp/src/apfsc/prod/diagnostics.rs:23` (`ClassGAbSummary`)
  - `baremetal_lgp/src/apfsc/prod/diagnostics.rs:31` (`class_g_ab_summary`)
  - `baremetal_lgp/src/apfsc/prod/diagnostics.rs:114` (persist summary JSON)
- Crucible profile tuning changes:
  - `transfer_weight` set to `0.0` across phase2 family weights in crucible config
  - `enable_qd_archive = false` in phase4 config
  - Anchors:
    - `baremetal_lgp/fixtures/apfsc/phase4/config/phase4_crucible_16g.toml:19`
    - `baremetal_lgp/fixtures/apfsc/phase4/config/phase4_crucible_16g.toml:155`
- Added targeted regression test for strict non-zero yield requirement:
  - `baremetal_lgp/tests/apfsc_phase4_searchlaw_ab.rs:92`

## 5) Validation Runs Executed During This Audit

Executed in `baremetal_lgp/`:
1. `cargo test -p baremetal_lgp --test apfsc_phase4_searchlaw_ab`
   - Result: 3 passed, 0 failed
   - Includes `searchlaw_ab_requires_strict_nonzero_yield_gain`
2. `cargo test -p baremetal_lgp --test apfsc_prod_e2e_daemon`
   - Result: 1 passed, 0 failed
3. `cargo test -p baremetal_lgp --test apfsc_prod_telemetry`
   - Result: 1 passed, 0 failed

Not executed in this audit run:
- Full workspace test matrix
- Full release qualification pipeline (`apfsc_qualify --mode release`)
- Full fault-injection and soak suites

## 6) Commit Inventory (Non-Merge, In-Window)

1. `dfb5cfccb0351abceda12c574f34790960d0c3ed` - apfsc: phase4 crucible, prod daemon resilience, and external ingress tooling (#29)
2. `a4d3cf922e81205a412f5ede96c177fcd34f6cbb` - Harden production control-plane journaling, backup format, and release state tracking
3. `52704ef00e9cc675df7c1ff5f853cd7678b940e1` - Implement APF-SC production readiness control plane and release tooling
4. `e0d90cdb206ac506e07279afac336cd913f0d172` - apfsc phase4: close searchlaw and rotation contract gaps
5. `79b02997026dd32ab63cd3e5c1638f524c04edef` - Implement APF-SC Phase 4 end-to-end stack
6. `31649bca16958e0b581c1b2ebbd62492658095c8` - apfsc: implement phase3 mvp end-to-end
7. `a268a2c345ee0c4adf945689c9e814eb783f99f6` - Implement APF-SC Phase 2 MVP end-to-end
8. `48c235f72b5a4ca6608cbaac4970018c22189ac9` - Add APF-SC runtime artifact snapshot and Phase 2 MVP docs (#22)
9. `565e5a1aa300121fd124fae4aba83eb06f76c2f2` - Add APF-SC Phase 1 MVP end-to-end implementation (#21)
10. `cc682c1f0dfaa4d67e07d75ee10ac40e315067fc` - Add APF-v3 module with deterministic wake/judge/omega pipeline
11. `5b939765c4f948aa0df1be028f1e3589995af91e` - Implement Phase 3 compile-to-chunk oracle and deterministic death

## 7) Evidence Collection Commands (for reproducibility)

- Commit list and stats:
  - `git log --since='2026-02-28 00:00:00 +1000' --until='2026-03-02 23:59:59 +1000' --no-merges --date=iso --pretty=format:'%H|%h|%ad|%an|%s'`
  - `git log --since='2026-02-28 00:00:00 +1000' --until='2026-03-02 23:59:59 +1000' --no-merges --shortstat`
- Working tree delta:
  - `git diff --stat`
  - `git diff -- <files>`
- Function/test evidence extraction:
  - `git show --unified=0 <commit> ... | rg '^\+\s*(pub\s+)?fn\s+'`
  - `git show --unified=0 <commit> -- baremetal_lgp/tests/*.rs | rg '^\+\s*fn\s+'`
  - `rg -n '<symbol>' <file>`
- Runtime artifact inspection:
  - `jq ... docs/apfsc_phase1_4_impl_metrics_2026-03-01.json`
  - `jq ... docs/apfsc_phase1_4_evidence_summary_2026-03-01.json`
  - `jq ... docs/apfsc_runtime_timeline_2026-03-01.json`

