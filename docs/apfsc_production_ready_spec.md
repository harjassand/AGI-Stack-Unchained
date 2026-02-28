# APF-SC Production Readiness - Final Completion Specification

This document is the implementation contract for a codex agent. It extends `apfsc_phase4_mvp_spec.md` into the final production-grade closure layer for APF-SC on a single Apple-silicon node.

The purpose of this plan is not to introduce new research semantics. The purpose is to close every remaining non-research gap between the Phase 4 recursive architecture-science engine and a production-ready system that can be built, released, operated, recovered, audited, qualified, and trusted.

End to end in this final plan means:

1. a clean checkout can be built into reproducible release artifacts,
2. release artifacts carry build metadata, SBOMs, signatures, and provenance,
3. the system can run continuously under a local supervisor with crash-safe recovery,
4. every mutating action is authenticated, authorized, audited, idempotent, and replayable,
5. storage, migrations, backups, restores, retention, and compaction are all qualified,
6. a full test, evaluation, and qualification program gates merge and release,
7. release promotion requires deterministic correctness, security, performance, soak, and recovery certification,
8. the trusted protocol plane remains immutable.

The completion condition is simple:

**APF-SC must become releasable and operable as a production-grade single-node recursive architecture-science service without weakening the Phase 1-4 trusted semantics.**

---

## 1. Hard constraints

Codex must follow these constraints exactly.

### 1.1 Phase 4 is a prerequisite

Assume the Phase 1, Phase 2, Phase 3, and Phase 4 contracts exist or are being implemented exactly as specified in:

- `apfsc_phase1_mvp_spec.md`
- `apfsc_phase2_mvp_spec.md`
- `apfsc_phase3_mvp_spec.md`
- `apfsc_phase4_mvp_spec.md`

This document is a production closure layer. Do not redesign the earlier semantics unless a production requirement needs a mechanical schema or infrastructure extension.

### 1.2 Trusted substrate boundary

Treat the existing APF-v3 substrate in `baremetal_lgp` / `apf3` as immutable. Reuse existing facilities for:

- deterministic replay capsules and digests,
- content-addressed artifacts,
- atomic pointer writes,
- judge-only activation,
- fail-closed execution,
- rollback pointers.

If actual names differ in the repo, adapt at the APF-SC boundary. Do not refactor APF-v3 core code.

### 1.3 Keep semantic truth unchanged

The following rules remain permanent:

- interpreter holdout truth remains the only truth source,
- hidden challenge contents remain outside recursion,
- holdout scalars remain outside search-law inputs,
- judged protocol rules are not self-modifiable,
- no dynamic tool execution is allowed on holdout truth,
- no judged network access is allowed,
- no NativeBlock judged execution is introduced by this plan.

### 1.4 Production target

This plan targets:

- one Apple-silicon node,
- effective 16 GiB protocol envelope,
- local artifact store,
- local control plane,
- local or CI release pipeline,
- operator-driven ingress only.

Distributed execution is explicitly out of scope for this production closure.

### 1.5 Production objective

The production objective is narrower than "more intelligence." It is:

- build reproducibly,
- run continuously,
- recover correctly,
- release safely,
- observe clearly,
- qualify rigorously.

---

## 2. Remaining gaps this plan must close

Phase 4 leaves the research loop complete, but not yet production ready. This plan closes the following remaining gaps.

### 2.1 Build and release hardening gap

Need:

- pinned and reproducible builds,
- release manifests,
- artifact signing,
- SBOM generation,
- provenance generation,
- dependency policy gates,
- vulnerability gates,
- release verification scripts.

### 2.2 Operability gap

Need:

- long-running daemon,
- local control API,
- launchd packaging,
- health checks,
- diagnostics bundles,
- structured telemetry,
- alert thresholds,
- operator runbooks.

### 2.3 Crash safety gap

Need:

- write-ahead run journal,
- idempotent jobs,
- lease ownership,
- startup recovery,
- explicit commit markers,
- backup and restore,
- corruption detection.

### 2.4 State evolution gap

Need:

- schema versions,
- forward migrations,
- downgrade guards,
- store compatibility checks,
- baseline requalification after migration.

### 2.5 Storage hygiene gap

Need:

- mark-and-sweep reachability,
- retention classes,
- archive compression,
- tombstones,
- compaction,
- disk-space alarms.

### 2.6 Security and governance gap

Need:

- local authn/authz for control-plane mutation,
- immutable audit log with hash chain,
- secret provider abstraction,
- pack classification metadata,
- operator separation of duties.

### 2.7 Qualification gap

Need:

- deterministic certification,
- migration certification,
- crash and fault injection tests,
- performance certification,
- soak tests,
- security scans,
- release promotion gates,
- evaluation registry and baselines.

---

## 3. Definition of production-ready

APF-SC is production-ready only if all of the following are true.

1. **Reproducible release**
   A clean checkout at a tagged commit can produce the same release manifest and identical binary digests when built in the same pinned build environment.

2. **Supply-chain verifiability**
   Every release artifact has:
   - release manifest,
   - SBOM,
   - provenance,
   - signature,
   - verification script.

3. **Crash-safe service**
   An interrupted run can recover without state corruption or ambiguous activation.

4. **Deterministic qualification**
   Repeated fixture epochs under the qualification profile produce byte-identical receipts.

5. **Migration safety**
   A previous store version can be migrated forward with no semantic drift in goldens.

6. **Operational visibility**
   The daemon exposes structured metrics, logs, traces, and diagnostic bundles sufficient for incident triage.

7. **Security baseline**
   Control-plane mutations require local authority, are audited, and pass dependency/security policy gates.

8. **Release gate discipline**
   No release is cut without green correctness, security, performance, soak, and recovery gates.

---

## 4. Scope

### 4.1 Implement now

Implement now:

- `apfscd` production daemon,
- `apfscctl` operator CLI,
- local control-plane transport,
- `ControlDB` for control-plane indexing and journaling,
- write-ahead run journal and idempotent job state machine,
- leases and single-writer enforcement,
- startup recovery and replay-safe resumption,
- schema versioning and migrations,
- backup, restore, retention, GC, and compaction,
- structured telemetry, health checks, preflight, and diagnostics,
- audit log with hash chain,
- authn/authz for local mutations,
- secret provider abstraction,
- build metadata, release manifests, SBOM, provenance, signing, verification,
- qualification harness,
- evaluation registry,
- CI/CD and release pipelines,
- full production test, evaluation, and soak suite,
- launchd packaging and operator runbooks.

### 4.2 Explicitly do not implement now

Do not implement now:

- distributed execution,
- remote multi-user API exposed on the public internet,
- autonomous web browsing or self-directed external acquisition,
- protocol self-modification,
- dynamic judged tool execution,
- judged network access,
- cloud control plane requirements,
- automatic scaling.

---

## 5. Production architecture

### 5.1 New top-level runtime model

```text
launchd / operator shell
        |
        v
     apfscd ------------------> metrics endpoint (localhost only)
        |         |  \-----> JSONL audit log + hash chain
        |
        +-----> ControlDB (SQLite, WAL)
        |
        +-----> APF-SC orchestrator
        |          |
        |          +--> ingress workers
        |          +--> public eval workers
        |          +--> holdout judge
        |          +--> canary worker
        |          +--> search-law evaluator
        |
        +-----> artifact store (content-addressed)
        +-----> archives / baselines / receipts
        +-----> backups / tombstones / compaction
        +-----> diagnostics bundles

apfscctl ----> local control socket only
```

### 5.2 Design principles

- **Trusted truth plane stays file-and-receipt based.**
- **ControlDB is a control-plane index, not semantic truth.**
- **Active pointers remain atomically written files.**
- **All mutating jobs are journaled before execution.**
- **All jobs are idempotent under `(run_id, stage, entity_hash)`.**
- **Daemon restart must be safe at any point.**
- **Public diagnostics are rich; holdout semantics remain sealed.**

---

## 6. Repo layout to add

Keep APF-v3 and the Phase 1-4 APF-SC tree intact. Extend the repo with the following tree.

```text
src/apfsc/prod/
  mod.rs
  daemon.rs
  service.rs
  control_api.rs
  control_db.rs
  journal.rs
  jobs.rs
  lease.rs
  recovery.rs
  migration.rs
  backup.rs
  restore.rs
  retention.rs
  gc.rs
  compaction.rs
  audit.rs
  auth.rs
  secrets.rs
  telemetry.rs
  health.rs
  diagnostics.rs
  preflight.rs
  release_manifest.rs
  buildinfo.rs
  versioning.rs
  profiles.rs
  install.rs

src/bin/
  apfscd.rs
  apfscctl.rs
  apfsc_preflight.rs
  apfsc_backup.rs
  apfsc_restore.rs
  apfsc_gc.rs
  apfsc_compact.rs
  apfsc_migrate.rs
  apfsc_qualify.rs
  apfsc_diag_dump.rs
  apfsc_release_verify.rs

config/
  base.toml
  profiles/dev.toml
  profiles/fixture_ci.toml
  profiles/nightly_qual.toml
  profiles/release_qual.toml
  profiles/prod_single_node.toml
  schema/config.schema.json

deploy/
  launchd/dev.apfscd.plist
  launchd/prod.apfscd.plist

scripts/
  ci/
    lint.sh
    test_unit.sh
    test_property.sh
    test_integration.sh
    test_faults.sh
    test_bench_smoke.sh
    test_release_qual.sh
    verify_release_artifacts.sh
  release/
    build_release.sh
    generate_sbom.sh
    generate_provenance.sh
    sign_release.sh
    publish_release.sh
    rollback_release.sh

evals/
  registry.yaml
  suites/
    phase1_regression.yaml
    phase2_constellation.yaml
    phase3_paradigm.yaml
    phase4_searchlaw.yaml
    prod_recovery.yaml
    prod_migration.yaml
    prod_perf.yaml
    prod_soak.yaml
    prod_security.yaml
  baselines/
    reference_m4pro_16g.json
  reports/.gitkeep

ops/
  runbooks/
    install.md
    bootstrap.md
    daily_ops.md
    ingress.md
    backup_restore.md
    recovery.md
    release.md
    rollback.md
    incident_response.md
    challenge_rotation.md
  dashboards/
    apfsc_overview.json
    apfsc_qualification.json
    apfsc_release.json
  alerts/
    apfsc_rules.yaml

tests/
  apfsc_prod_control_db.rs
  apfsc_prod_journal.rs
  apfsc_prod_recovery.rs
  apfsc_prod_migrations.rs
  apfsc_prod_backup_restore.rs
  apfsc_prod_retention_gc.rs
  apfsc_prod_compaction.rs
  apfsc_prod_audit.rs
  apfsc_prod_auth.rs
  apfsc_prod_preflight.rs
  apfsc_prod_telemetry.rs
  apfsc_prod_release_manifest.rs
  apfsc_prod_release_verify.rs
  apfsc_prod_e2e_daemon.rs
  apfsc_prod_e2e_crash_resume.rs
  apfsc_prod_e2e_release_qual.rs

fuzz/
  fuzz_targets/
    manifest_parse.rs
    scir_verify.rs
    bridge_parse.rs
    archive_read.rs
    control_api_parse.rs

.github/
  workflows/
    pr-ci.yml
    nightly-qual.yml
    release-qual.yml
    release.yml
```

---

## 7. Production profiles and config model

### 7.1 Config layering

Implement deterministic config layering:

```text
base.toml
  -> profile.toml
  -> local override file (optional, untracked)
  -> environment variable overrides
```

### 7.2 Required profiles

- `dev`
- `fixture_ci`
- `nightly_qual`
- `release_qual`
- `prod_single_node`

### 7.3 Config rules

- config is parsed once at startup,
- resolved config is emitted to diagnostics after secret redaction,
- invalid config fails closed,
- profile name is recorded in every run receipt,
- build profile and runtime profile are both recorded.

### 7.4 Example config surface

```toml
[paths]
root = "/Library/Application Support/APFSC"
artifacts = "artifacts"
archives = "archives"
backups = "backups"
control_db = "control/control.db"
control_socket = "run/apfscd.sock"
metrics_bind = "127.0.0.1:9464"

[limits]
rss_hard_limit_bytes = 12884901888
rss_abort_limit_bytes = 15032385536
max_concurrent_mapped_bytes = 2147483648
max_public_workers = 2
max_canary_workers = 1

[retention]
receipt_days = 365
public_trace_days = 90
candidate_tmp_hours = 24
tombstone_days = 30
backup_keep_last = 14

[auth]
enable_control_socket_tokens = true
token_file = "secrets/control_tokens.json"

[telemetry]
otel_enabled = true
json_logs = true
metrics_enabled = true
trace_sampling = "errors_and_release"

[release]
require_signed_artifacts = true
require_sbom = true
require_provenance = true
require_green_release_qual = true
```

---

## 8. Control plane

### 8.1 `apfscd` daemon

`apfscd` is the long-running local service that owns:

- control socket,
- control DB,
- job scheduler,
- recovery loop,
- background maintenance,
- telemetry export,
- preflight and health endpoints,
- qualification orchestration.

### 8.2 `apfscctl` operator CLI

`apfscctl` is the only supported operator interface for mutations.

Commands:

- `status`
- `health`
- `start-run`
- `pause`
- `resume`
- `cancel-run`
- `ingest reality`
- `ingest prior`
- `ingest substrate`
- `ingest formal`
- `ingest tool`
- `backup create`
- `backup verify`
- `restore dry-run`
- `restore apply`
- `gc dry-run`
- `gc apply`
- `compact`
- `qualify`
- `diag dump`
- `release verify`
- `active show`
- `rollback`

### 8.3 Local-only transport

Use a Unix domain socket by default.

Rules:

- no remote TCP listener by default,
- socket path permissions are restrictive,
- destructive commands require auth token or local operator identity,
- readonly status commands may be allowed with reduced privilege.

---

## 9. ControlDB

### 9.1 Purpose

Add `ControlDB` as a local SQLite database in WAL mode.

`ControlDB` is the authoritative index for:

- job state,
- leases,
- migration ledger,
- run journal,
- release history,
- backup history,
- operator audit mirror,
- materialized metrics snapshots.

`ControlDB` is **not** the semantic truth source for judged results.

### 9.2 Required tables

```text
schema_migrations
runs
jobs
leases
packs
active_pointer_mirror
backups
releases
baselines
audit_events
maintenance_events
```

### 9.3 Minimal schema sketch

```sql
CREATE TABLE schema_migrations (
  version INTEGER PRIMARY KEY,
  applied_at TEXT NOT NULL,
  checksum TEXT NOT NULL
);

CREATE TABLE runs (
  run_id TEXT PRIMARY KEY,
  snapshot_hash TEXT NOT NULL,
  profile TEXT NOT NULL,
  state TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  active_before TEXT,
  active_after TEXT,
  replay_digest TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE jobs (
  job_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  entity_hash TEXT,
  state TEXT NOT NULL,
  lease_owner TEXT,
  attempt INTEGER NOT NULL,
  receipt_hash TEXT,
  error_code TEXT,
  started_at TEXT,
  finished_at TEXT
);

CREATE TABLE leases (
  lease_name TEXT PRIMARY KEY,
  owner_id TEXT NOT NULL,
  expires_at TEXT NOT NULL
);

CREATE TABLE audit_events (
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  prev_hash TEXT,
  event_hash TEXT NOT NULL,
  event_type TEXT NOT NULL,
  actor TEXT NOT NULL,
  ts TEXT NOT NULL,
  body_json TEXT NOT NULL
);
```

### 9.4 Rules

- WAL mode enabled,
- foreign keys enabled,
- schema checksum verified at startup,
- database backup uses online backup API or clean snapshot,
- every mutating command writes both audit event and journal row before work starts.

---

## 10. Job model and write-ahead journal

### 10.1 Job states

```text
Planned -> Leased -> Running -> Succeeded
                       |           |
                       |           +-> Committed
                       |
                       +-> Failed
                       +-> Cancelled
                       +-> RecoveryPending
```

### 10.2 Idempotency key

Every mutating action must include:

```text
IdempotencyKey = hash(
  command_type,
  snapshot_hash?,
  entity_hash?,
  profile,
  operator_request_uuid
)
```

If the same request is replayed after crash or restart, the daemon must return the existing result or continue the same job.

### 10.3 Journal record

```text
JournalRecord = {
  job_id,
  run_id?,
  idempotency_key,
  stage,
  target_entity_hash?,
  planned_effects,
  created_at,
  state,
  receipt_hash?,
  commit_marker?
}
```

### 10.4 Atomicity rules

- all effects are planned before work starts,
- all receipts are persisted before commit marker,
- activation pointer update is the final commit effect,
- after pointer write, commit marker must be written immediately,
- recovery logic must interpret missing commit marker as incomplete.

### 10.5 Recovery algorithm

```python
def startup_recovery():
    verify_store_layout()
    verify_schema_versions()
    repair_or_replay_wal_if_needed()

    pending = load_jobs_in_states([
        "Leased", "Running", "RecoveryPending"
    ])

    for job in pending:
        if has_commit_marker(job):
            finalize_job(job)
        elif has_complete_receipts(job):
            replay_commit_if_idempotent(job)
        else:
            mark_recovery_pending(job)
            restart_from_last_safe_stage(job)

    verify_active_pointer_consistency()
    emit_recovery_receipt()
```

---

## 11. Leases and single-writer enforcement

### 11.1 Required leases

- `orchestrator`
- `judge`
- `activation`
- `backup`
- `gc`
- `compaction`
- `release`

### 11.2 Lease rules

- only one owner per lease,
- leases have explicit expiry,
- lease renewal is heartbeat-based,
- expired leases are reclaimable,
- activation requires both `judge` and `activation` lease,
- backup and GC cannot overlap with activation.

### 11.3 Concurrency model

Keep concurrency deliberately simple:

- one daemon process,
- worker pool for public-side evaluation only,
- one holdout judge at a time,
- one activation at a time,
- maintenance jobs serialized against activation-sensitive regions.

Use `loom` model tests for all lease and activation concurrency logic.

---

## 12. State layout and artifact hygiene

### 12.1 Root layout

```text
root/
  artifacts/
    objects/
    quarantine/
    tmp/
    tombstones/
  archives/
  backups/
  control/
  releases/
  diagnostics/
  logs/
  run/
  config/
  evals/
```

### 12.2 Artifact classes

- immutable content-addressed objects,
- mutable active pointers,
- append-only archives,
- temporary workspace,
- quarantined ingress artifacts,
- tombstoned objects awaiting deletion.

### 12.3 Reachability roots for GC

- active architecture pointer,
- active search-law pointer,
- rollback pointer,
- retained receipts,
- retained backups,
- live snapshots,
- pinned baselines,
- protected fixtures,
- current release artifacts.

### 12.4 GC rules

Implement mark-and-sweep with dry run:

1. build reachability set from all roots,
2. mark live content hashes,
3. move unreachable objects to tombstones,
4. wait grace period,
5. delete permanently only after second confirmation.

### 12.5 Compaction rules

- compress old JSONL archives with zstd,
- coalesce small trace files into segment bundles,
- preserve content hash identity for immutable objects,
- compaction must be resumable,
- compaction must emit a receipt and dry-run estimate.

---

## 13. Migrations and versioning

### 13.1 Version domains

Track four versions separately:

- `artifact_schema_version`
- `control_db_schema_version`
- `config_schema_version`
- `release_manifest_version`

### 13.2 Rules

- startup fails if version set is unsupported,
- forward migration commands are explicit,
- downgrade is forbidden unless an explicit restore path exists,
- every migration must have:
  - dry run,
  - irreversible-change warning,
  - before/after checks,
  - golden replay test.

### 13.3 Migration command

```text
apfsc_migrate --from <version> --to <version> --dry-run
apfsc_migrate --from <version> --to <version> --apply
```

### 13.4 Migration certification

A migration is accepted only if:

- old fixture store migrates,
- all expected hashes remain reachable,
- goldens replay exactly,
- active pointers are preserved,
- release manifest verification still passes.

---

## 14. Backup and restore

### 14.1 Backup objectives

Need:

- recover from disk failure,
- recover from operator error,
- recover from bad migration,
- recover from corrupted control DB.

### 14.2 Backup contents

Every backup must include:

- config snapshot,
- active pointers,
- rollback pointers,
- control DB snapshot,
- retained receipts,
- required immutable objects reachable from retention roots,
- backup manifest with all digests.

### 14.3 Backup format

```text
backup/
  manifest.json
  control.db.zst
  pointers/
  configs/
  objects/
  receipts/
```

### 14.4 Restore modes

- `dry-run`: verify digests and target path compatibility only,
- `staging`: restore into isolated directory and run replay verification,
- `apply`: stop daemon, restore, run integrity checks, restart.

### 14.5 Restore verification

After restore:

- compare active pointers,
- verify backup manifest digests,
- run fixture replay suite,
- run minimal health check,
- emit restore receipt.

---

## 15. Authn, authz, secrets, and audit

### 15.1 Roles

Implement minimal local roles:

- `Reader`
- `Operator`
- `ReleaseManager`

### 15.2 Authorization rules

- `Reader`: status, health, diagnostics metadata
- `Operator`: run control, ingress, backup, restore dry-run, GC dry-run
- `ReleaseManager`: release qualification, signing, publish, rollback, restore apply

### 15.3 Authn modes

Support:

- local OS user/group check,
- optional token file for CLI-to-daemon mutation,
- optional macOS keychain-backed secret retrieval where feasible,
- fallback file secrets with `0600` permissions.

### 15.4 Audit log

Write every mutating event as:

```text
AuditEvent = {
  seq,
  prev_hash,
  event_hash,
  actor,
  role,
  command,
  request_digest,
  result,
  ts,
  body_redacted_json
}
```

Rules:

- append-only,
- hash chained,
- mirrored in ControlDB,
- exported in diagnostics bundle,
- no secret values stored,
- release events always audited.

### 15.5 Separation of duties

Signing and publishing commands must require `ReleaseManager`. The daemon must reject signing or publish attempts from normal operators.

---

## 16. Telemetry, health, and diagnostics

### 16.1 Telemetry signals

Emit:

- metrics,
- structured logs,
- traces for long-running control-plane and evaluation operations.

### 16.2 Minimum metrics

- `apfsc_run_total`
- `apfsc_run_fail_total`
- `apfsc_job_recovery_total`
- `apfsc_activation_total`
- `apfsc_activation_fail_total`
- `apfsc_replay_mismatch_total`
- `apfsc_backup_total`
- `apfsc_restore_total`
- `apfsc_gc_bytes_reclaimed_total`
- `apfsc_compaction_total`
- `apfsc_rss_bytes`
- `apfsc_pageouts_total`
- `apfsc_disk_free_bytes`
- `apfsc_holdout_admissions_total`
- `apfsc_canary_fail_total`
- `apfsc_security_gate_fail_total`
- `apfsc_release_qual_fail_total`

### 16.3 Health endpoints

Expose locally:

- `liveness`
- `readiness`
- `preflight`
- `active pointers`
- `latest backup age`
- `latest qualification status`

### 16.4 Diagnostics bundle

`apfsc_diag_dump` must collect:

- resolved redacted config,
- active pointers,
- recent receipts,
- ControlDB integrity summary,
- audit tail,
- telemetry snapshot,
- disk usage summary,
- last qualification report,
- last recovery report,
- build info and version.

### 16.5 Alert rules

At minimum alert on:

- replay mismatch > 0,
- pageouts > 0 in judged run,
- failed startup recovery,
- stale backups,
- disk free below threshold,
- repeated canary failures,
- failed release qualification,
- failed migration check,
- failed signature or provenance verification.

---

## 17. Release engineering

### 17.1 Release artifacts

For each release produce:

- native tarball,
- optional OCI image for CI smoke use only,
- release manifest,
- SBOM,
- provenance,
- signature bundle,
- verification report.

### 17.2 Release manifest

```json
{
  "release_manifest_version": 1,
  "version": "1.0.0-rc1",
  "git_commit": "abc123",
  "build_profile": "release",
  "rust_toolchain": "pinned",
  "target_triple": "aarch64-apple-darwin",
  "artifact_digests": {
    "apfscd": "sha256:...",
    "apfscctl": "sha256:..."
  },
  "sbom_path": "release/sbom.spdx.json",
  "provenance_path": "release/provenance.json",
  "signature_bundle_path": "release/signature.bundle.json"
}
```

### 17.3 Build rules

- pinned toolchain committed,
- lockfile committed,
- release build scripts deterministic,
- no dirty working tree for release build,
- build info embedded in binaries,
- release build environment captured in provenance.

### 17.4 Required release verification command

```text
apfsc_release_verify   --manifest release_manifest.json   --sbom release/sbom.spdx.json   --provenance release/provenance.json   --signature release/signature.bundle.json
```

The release is invalid unless this command passes.

### 17.5 Release states

```text
Draft -> Built -> Verified -> Qualified -> Signed -> Published -> Active
```

No direct jump is allowed around `Qualified` or `Verified`.

---

## 18. launchd packaging

### 18.1 Service model

First-class deployment target is macOS `launchd`.

Provide:

- dev plist,
- prod plist,
- install script,
- uninstall script,
- log paths,
- socket path,
- environment file support.

### 18.2 launchd rules

- daemon restarts on failure,
- graceful stop timeout,
- stdout/stderr redirected to structured logs,
- config path passed explicitly,
- preflight must run before first start.

### 18.3 Installation flow

```text
install release -> run apfsc_preflight -> bootstrap launchd plist
-> start apfscd -> verify health -> record install receipt
```

---

## 19. Qualification harness

### 19.1 Purpose

Implement `apfsc_qualify` as the one command that drives all required production qualification suites.

### 19.2 Qualification modes

- `pr`
- `merge`
- `nightly`
- `release`
- `post-restore`

### 19.3 Output

`apfsc_qualify` must emit:

- machine-readable JSON report,
- markdown summary,
- failing suite list,
- baseline comparisons,
- artifact pointers to receipts and logs.

### 19.4 Qualification pseudocode

```python
def qualify(mode):
    run_lint_and_format()
    run_unit_and_property_tests()
    run_loom_concurrency_tests()
    run_fixture_goldens()
    run_integration_e2e()
    run_migration_suite()
    run_fault_injection_suite()
    run_perf_suite(mode)
    run_security_suite(mode)
    run_release_artifact_verification_if_needed(mode)
    run_soak_suite_if_needed(mode)
    summarize_and_write_report()
    return pass_if_all_required_suites_green()
```

---

## 20. Full production test program

This section is normative. The codex agent must implement all named suites and wire them into CI or release qualification.

### 20.1 Tier A - static quality gates

Required on every PR:

- `cargo fmt --check`
- `cargo clippy --workspace --all-targets --all-features -- -D warnings`
- config schema validation
- markdown and runbook link validation
- license/dependency policy check

### 20.2 Tier B - unit tests

Cover:

- manifests,
- control DB helpers,
- journal transitions,
- lease expiry and renewal,
- auth decision logic,
- audit hash chain,
- telemetry label validation,
- release manifest parsing.

### 20.3 Tier C - property tests

Use `proptest` for:

- manifest round trips,
- SCIR verifier invariants,
- journal state machine invariants,
- migration mapping invariants,
- reachability and GC root marking,
- audit hash chain continuity.

### 20.4 Tier D - concurrency model tests

Use `loom` for:

- activation pointer writes,
- lease acquisition and expiry,
- job recovery finalize-vs-restart race,
- backup-vs-activation exclusion,
- GC-vs-restore exclusion.

### 20.5 Tier E - golden fixture tests

Keep committed fixture epochs and expected receipts for:

- Phase 1 regression,
- Phase 2 cross-family regression,
- Phase 3 warm and cold paradigm regression,
- Phase 4 search-law regression,
- production recovery and migration regression.

Receipts must match byte for byte.

### 20.6 Tier F - integration tests

Must exercise:

- daemon startup,
- operator CLI round trips,
- local socket auth,
- ingest through judge through activation,
- backup create and verify,
- restore dry-run,
- GC dry-run and apply,
- compaction,
- release manifest generation.

### 20.7 Tier G - end-to-end crash and fault injection

Inject faults at these points:

- before journal write,
- after journal write but before execution,
- after public receipts but before holdout,
- after holdout receipts but before activation,
- after activation pointer write but before commit marker,
- mid-backup,
- mid-restore,
- during compaction,
- during migration.

Required outcome: recover without corruption or ambiguous active state.

### 20.8 Tier H - fuzzing

Add `cargo-fuzz` targets for:

- pack manifest parsers,
- control API request parsers,
- SCIR verifier input,
- archive index readers,
- release manifest readers.

Nightly only. Fail the nightly build on crash or memory safety issues.

### 20.9 Tier I - migration tests

Must cover:

- old fixture store to new schema,
- repeated migration idempotence,
- rejected unsupported downgrade,
- cross-version diagnostics compatibility,
- no golden drift after migration.

### 20.10 Tier J - performance tests

Measure and gate:

- public eval throughput,
- holdout eval throughput,
- peak RSS,
- pageouts,
- startup time,
- recovery time,
- backup verify time,
- restore dry-run time,
- GC scan rate,
- compaction throughput.

Compare against `evals/baselines/reference_m4pro_16g.json`.

### 20.11 Tier K - soak tests

Required before `1.0.0` and every release candidate:

- 72-hour daemon uptime under production profile,
- repeated runs, backups, GC dry-runs, and diagnostics,
- no memory leak beyond threshold,
- no journal corruption,
- no increasing replay mismatch count,
- no stale lease accumulation.

### 20.12 Tier L - security and supply-chain tests

Required suites:

- dependency vulnerability scan,
- dependency policy and license scan,
- secret scan,
- release manifest verification,
- SBOM existence and schema validation,
- provenance existence and validation,
- signature verification,
- audit trail integrity check.

### 20.13 Tier M - docs and runbook tests

Verify:

- all commands in runbooks parse or execute in fixture mode,
- config examples validate,
- install/uninstall scripts work on clean fixture host,
- release and rollback runbooks reference existing scripts.

---

## 21. Evaluation program

Production readiness requires both tests and evaluations. Tests ask whether the system is mechanically correct. Evaluations ask whether research semantics still behave acceptably after hardening.

### 21.1 Evaluation registry

Create `evals/registry.yaml` with suites, cadence, command, profile, baseline, and gating mode.

### 21.2 Required evaluation suites

#### `phase1_regression`
Verify Phase 1 deterministic receipts, incubator maturation, and activation path.

#### `phase2_constellation`
Verify cross-family weighting, protected-family floors, transfer, and robustness.

#### `phase3_paradigm`
Verify `PWarm` and `PCold` gates, bridge receipts, backend equivalence, and recent-family gain.

#### `phase4_searchlaw`
Verify search-law offline replay, branch A/B, hidden challenge gates, and law archive updates.

#### `prod_recovery`
Verify crash recovery and replay exactness under repeated forced restarts.

#### `prod_migration`
Verify schema migration and no-golden-drift.

#### `prod_perf`
Verify throughput, RSS, pageouts, and startup/recovery timings.

#### `prod_soak`
Verify long-haul stability.

#### `prod_security`
Verify release artifact integrity, auth rules, audit integrity, and secret hygiene.

### 21.3 Evaluation outputs

Every evaluation suite must emit:

- summary JSON,
- markdown report,
- receipt pointers,
- baseline comparisons,
- decision: `pass`, `warn`, or `fail`.

### 21.4 Baseline management

Baselines must be explicit and versioned.

Rules:

- baseline update requires human review,
- baseline change must explain reason,
- performance baseline changes require comparison artifact,
- no silent widening of thresholds.

---

## 22. Performance and resource certification

### 22.1 Reference machine baseline

Primary certification host:

- Apple-silicon M4 Pro class machine,
- effective 16 GiB protocol envelope,
- clean local SSD,
- no swap tolerated during judged runs.

### 22.2 Release performance gates

A release candidate fails if any of the following occur in release qualification:

- judged pageouts > 0,
- peak RSS > configured hard limit,
- public throughput regresses by more than 10 percent from approved baseline,
- holdout throughput regresses by more than 10 percent,
- startup time regresses by more than 20 percent,
- recovery time regresses by more than 20 percent,
- backup verify or restore dry-run exceeds approved threshold,
- activation latency exceeds approved threshold.

### 22.3 Memory-leak gate

Soak test must show stable RSS envelope over time. A release candidate fails if RSS trend grows monotonically past approved leak budget.

---

## 23. Security and compliance baseline

### 23.1 Dependency policy

Add allow/deny policy files and CI checks.

Rules:

- deny unknown licenses unless explicitly approved,
- deny vulnerable direct dependencies above approved threshold,
- require lockfile,
- require reviewed exceptions.

### 23.2 Secret handling

- never commit secrets,
- store secrets via provider abstraction,
- redact secrets from logs, diagnostics, and audit trails,
- validate secret file permissions at startup.

### 23.3 Ingress governance metadata

Every pack admission receipt should carry:

- source identifier,
- operator,
- time,
- pack type,
- quarantine verdict,
- policy verdict,
- optional data classification tag.

### 23.4 Red-team style tests

Implement local negative tests for:

- unauthorized control mutation,
- replayed stale token,
- tampered release manifest,
- tampered backup manifest,
- tampered audit chain,
- corrupted ControlDB,
- corrupted active pointer.

---

## 24. Operator workflows

### 24.1 Bootstrap workflow

```text
install release
-> apfsc_preflight
-> apfscctl status
-> ingest seed packs
-> build snapshot
-> run fixture qualification
-> start production profile
```

### 24.2 Daily operations workflow

```text
health check
-> status
-> inspect latest run
-> verify backup freshness
-> run scheduled qualification
-> review alerts
```

### 24.3 Release workflow

```text
run release qualification
-> build release artifacts
-> generate SBOM + provenance
-> sign
-> verify
-> publish
-> install on staging node
-> smoke verify
-> promote
```

### 24.4 Recovery workflow

```text
stop daemon
-> restore dry-run
-> restore staging
-> replay verification
-> restore apply
-> startup recovery
-> health verify
```

### 24.5 Rollback workflow

```text
freeze mutations
-> point to rollback candidate or previous release
-> verify health
-> emit rollback receipt
-> open incident report
```

---

## 25. Minimal implementation details

### 25.1 `apfscd` boot sequence

```python
def daemon_main():
    cfg = load_and_validate_config()
    buildinfo = load_build_info()
    preflight_or_die(cfg)
    open_or_migrate_control_db(cfg)
    recover_state()
    open_control_socket(cfg)
    start_metrics_export(cfg)
    schedule_background_jobs(cfg)
    serve_control_api_forever()
```

### 25.2 Recovery-safe activation

```python
def commit_activation(candidate_hash, searchlaw_hash=None):
    require_leases(["judge", "activation"])
    write_planned_effect("activation", candidate_hash, searchlaw_hash)
    persist_all_receipts()
    fsync_receipts()
    atomic_write_pointer("active_candidate.json", candidate_hash)
    if searchlaw_hash is not None:
        atomic_write_pointer("active_search_law.json", searchlaw_hash)
    write_commit_marker()
    append_audit_event("activation_commit", candidate_hash)
```

### 25.3 Mark-and-sweep GC

```python
def gc_apply():
    roots = collect_gc_roots()
    live = mark_reachable_hashes(roots)
    dead = list_unreachable_objects(live)
    move_to_tombstones(dead)
    write_gc_receipt(dead_count=len(dead))
```

### 25.4 Release qualification command flow

```python
def release_qual():
    require_clean_checkout()
    require_no_unapplied_migrations()
    run_pr_gates()
    run_merge_gates()
    run_release_only_gates()
    build_release_bundle()
    verify_release_bundle()
    write_release_qual_report()
```

---

## 26. CI/CD plan

### 26.1 PR CI

Required:

- format,
- clippy,
- unit tests,
- property tests,
- small integration suite,
- config validation,
- dependency policy,
- secret scan,
- docs validation.

### 26.2 Merge CI

Required:

- everything in PR CI,
- loom tests,
- expanded integration suite,
- golden fixture suites,
- migration suites,
- fault injection smoke,
- benchmark smoke,
- release artifact smoke.

### 26.3 Nightly qualification

Required:

- fuzzing,
- full integration,
- performance suite,
- repeated deterministic replay,
- recovery suite,
- backup/restore suite,
- extended security scans.

### 26.4 Release qualification

Required:

- all nightly suites green on release commit,
- full release build,
- SBOM + provenance + signing,
- full release verify,
- 72-hour soak,
- staging install and smoke,
- approval receipt emitted.

---

## 27. Acceptance tests for production completion

The production closure is done only when all of the following are true.

1. `cargo test`, property tests, loom tests, and integration tests all pass.
2. `apfscd` runs under launchd and survives restart.
3. `apfscctl` can perform authenticated local mutations over the control socket.
4. Journaled crash-resume tests pass at every injected interruption point.
5. Backup and restore round trip verifies on fixture and staging restore.
6. GC and compaction work without deleting reachable objects.
7. Migration from previous fixture store passes and preserves goldens.
8. Release bundle contains manifest, SBOM, provenance, signatures, and passes verification.
9. Nightly qualification emits green reports.
10. Release qualification emits green report including soak and performance certification.
11. No pageouts occur in judged qualification runs.
12. Audit chain remains continuous across daemon restarts.
13. Operator runbooks are present and validated.

---

## 28. Branch and tasking strategy

Implement on branch:

```text
feat/apfsc-production-ready
```

Prefer vertical slices in this order:

1. control-plane skeleton,
2. journaling and recovery,
3. backup/restore and migrations,
4. auth/audit,
5. telemetry and diagnostics,
6. release engineering,
7. qualification harness,
8. full test/eval matrix,
9. launchd packaging and runbooks.

Do not start on release/signing work before the journal, recovery, and migration core exists.

---

## 29. What the codex agent should not optimize for

Do not optimize for:

- distributed systems generality,
- cloud portability first,
- microservice decomposition,
- public API completeness,
- research-feature expansion.

Optimize for:

- single-node correctness,
- local operability,
- deterministic recovery,
- release trust,
- qualification rigor.

---

## 30. Final instruction to codex

Use this document as the production implementation contract. Treat all earlier phase specs as research-semantic prerequisites and this document as the closure layer that makes them releasable and operable.

Any ambiguity should be resolved in favor of:

1. immutable protocol semantics,
2. deterministic recovery,
3. auditable mutation,
4. reproducible release,
5. stricter qualification,
6. smaller operational surface.
