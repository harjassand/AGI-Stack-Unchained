# `cdel` Package (CDEL-v2)

`cdel` is the active certification and verification engine inside the **CDEL-v2** repository (RE2). It combines:
- a library of historical verifier families (`v1_5r` … `v19_0`),
- modern Omega daemon orchestration modules (`v18_0`, `v19_0`), and
- CLI tooling for ledger operations, concept adoption, sealed evaluation, and experiment workflows.

This file documents the package-level structure in `CDEL-v2/cdel`, not the outer `CDEL-v2` README.

## At a glance

- **Package name**: `cdel`
- **Version**: `0.1.0` (defined in `CDEL-v2/pyproject.toml`)
- **Entry point**: `cdel` command (`cdel.cli:main`)
- **Python requirement**: `>=3.11`
- **Core principle**: deterministic, fail-closed verification with replayability and canonical artifact handling.
- **Scope inside RE2**: executes/validates candidate campaign work and emits deterministic receipts consumed by verifier and activation stages.

## Layout

```text
CDEL-v2/cdel/
├── __init__.py                  # package metadata
├── cli.py                       # CLI entrypoint and command dispatcher
├── config.py                    # TOML config loading and defaults
├── run-time versioned namespaces  # v1_5r, v1_6r, ... v19_0
├── adoption/                    # adoption journal and manifest handling
├── bench/                       # experimental/benchmark runners and reporting
├── common/                      # shared registry and capability helpers
├── constitution/                # constitutional metadata helpers
├── experiments/                 # local experiment workflows
├── gen/                        # task/code generation helpers
├── kernel/                      # formal kernel primitives (types, parser, eval, eval cost)
├── ledger/                      # object storage, index, verification, auditing, rebuild
├── metrics/                     # (small helper modules for metric extraction)
├── ratchet/                     # ratcheting/upgrade support helpers
├── sealed/                      # sealed execution + crypto + stat-cert support
├── specpack/                    # spec-pack helper tools
└── tests                         # legacy tests and versioned test suites
```

## Core sub-systems

### 1) `v18_0` — Omega daemon runtime verification stack

This is the modern RE2 runtime path and the largest active set.

- `omega_observer_v1.py`: builds observations from run artifacts.
- `omega_decider_v1.py`: pure decision function (`state + observation + policy + registry + budgets`).
- `omega_promoter_v1.py`: runs subverifiers + orchestrates promotion artifacts.
- `omega_activator_v1.py`: activation handoff checks before any active pointer swap.
- `omega_runaway_v1.py`: objective-driven escalation logic.
- `verify_rsi_omega_daemon_v1.py`: full replay verifier for a daemon tick.
- `verify_ccap_v1.py`: universal CCAP verifier used by newer proposal paths.
- `omega_common_v1.py`: Q32 helpers and foundational arithmetic.
- `omega_*` ledger/state/run/perf/trace modules that produce and check deterministic receipts.

Testing partitions in v18_0 include:
- `tests_fast/` for fast invariant checks,
- `tests_omega_daemon/` for end-to-end tick behavior,
- `tests_integration/` for replay/stateful fixtures.

### 2) `v19_0` — Continuity and world-treaty extensions

v19.0 layers additional federation/invariants checks for ladder/continuity narratives.

- `continuity/`: continuity checks, back-refutation, environment upgrade, translator totality.
- `world/`: world snapshots, treaty/task binding, sip checks, Merkle helpers.
- `federation/`: treaty and OK-portability checks.
- `verify_rsi_omega_daemon_v1.py`: v19 daemon verifier wrapper plus compatibility load behavior.
- `omega_promoter_v1.py`: v19 promotion wrapper used by new profile wiring.

### 3) Legacy verifier generations

`cdel/v1_5r` through `cdel/v17_0` preserve historical verifier generations used by older campaign variants.

Common categories include:
- demon/autonomy families (`v1_5r`…`v2_3`),
- boundless/math/science campaigns (`v8_0`…`v13_0`),
- system/kernel evolution (`v14_0`…`v16_1`),
- SAS VAL (`v17_0`),
- and additional campaign-specific verifiers.

These are intentionally retained for migration compatibility and historical replay.

## Key invariants used by cdel verifiers

1. **Fail-closed checks**
   - malformed/missing fields, hash mismatches, unknown schema versions, and policy violations should produce explicit hard failures.
2. **Canonical content rules**
   - canonical JSON bytes + deterministic hashing for artifacts that flow across tick/subrun boundaries.
3. **Deterministic arithmetic (Q32)**
   - RE2 arithmetic-sensitive paths avoid floating-point nondeterminism.
4. **Replay-first**
   - verifier recomputation must be able to prove that a claimed action is exactly reproducible.
5. **Path and allowlist constraints**
   - touched/required paths are validated against allowlists to prevent verifier self-modification and policy escapes.

## `cdel` as a CLI surface

Install and run from the `CDEL-v2` root:

```bash
cd CDEL-v2
python3 -m pip install -e .[dev]
```

Core commands (run `cdel --help` for full options):

- `cdel init --budget 1000000`
- `cdel verify <module_json>`
- `cdel commit <module_json>`
- `cdel adopt <adoption_json|revert>`
- `cdel eval --expr '{...}'`
- `cdel query --symbol <name>`
- `cdel resolve --concept <name>`
- `cdel consolidate --concept <id> --outdir <dir>`
- `cdel run-tasks <stream_jsonl>`
- `cdel solve/solve-suite/run-solve-scoreboard/run-solve-stress`
- `cdel audit-ledger` / `cdel audit stat-cert`
- `cdel sealed keygen|worker|suite-hash`
- `cdel runs gc|check`, `cdel check-invariants`, `cdel selfcheck`

## How CDEL-v2 verifiers are typically consumed

For an Omega tick (RE2 runtime):

1. Campaign execution produces raw artifacts in a subrun/state path.
2. `verify_rsi_omega_daemon_v1.py` recomputes observation and decision from persisted artifacts.
3. If promotion claims exist, campaign-specific/verifier-level checks are replayed.
4. Promotion CCAP path uses `verify_ccap_v1.py` to run realize/score/audit stages.
5. Promotion receipts and hashes feed higher layers for activation and history accounting.

## Developer workflow (common tasks)

### Add or modify a module in the legacy namespace

- Keep changes scoped to module-specific verifier assumptions and schemas.
- Preserve deterministic behavior and deterministic sort order for any list-like outputs.
- Add or update regression tests in the matching versioned `tests*` directory.
- If artifact schema changes, update compatibility checks that consume those artifacts.

### Work with v18/v19 runtime modules

- Use deterministic inputs only (artifact hashes, campaign IDs, canonical JSON payloads).
- Keep subrun path handling explicit; many replay checks assume stable subrun-root based resolution.
- Respect campaign allowlist and policy/budget envelopes.
- Prefer failing closed on missing cache or replay inputs unless there is a documented fallback.

## Testing quick references

From the repository root:

```bash
cd CDEL-v2
python3 -m pytest cdel/v18_0/tests_fast -q
python3 -m pytest cdel/v18_0/tests_omega_daemon -q
python3 -m pytest cdel/v19_0/tests_continuity -q
python3 -m pytest cdel/v18_0/tests_integration -q
```

`CDEL-v2` also includes larger, environment-specific smoke scripts at repository level; use those when doing full stack replays.

## Version map and compatibility snapshot

- `v19_0` introduces continuity/world checks alongside the v19 daemon verifier.
- `v18_0` is the primary active execution/replay/CCAP path for modern daemon runs.
- `v17_0` and earlier remain in repo for replay and compatibility validation.

## Conventions and style notes

- Keep JSON canonicalization stable when emitting or comparing artifacts.
- Sort before writing maps/lists when order is semantically significant.
- Prefer small helper functions with pure transformation and explicit failure reasons.
- Use repo-relative paths in manifests and artifact references.
- Keep command outputs minimal and machine-parseable (machine-readable JSON preferred where appropriate).

## Related references

- `CDEL-v2/README.md` (repo-level overview)
- `CDEL-v2/WORKSPACE_AND_OMEGA_DETAILED_REPORT_v1.md`
- `CDEL-v2/CURRENT_IMPLEMENTATION_AUDIT_LEVEL1_LEVEL2.md`
- `CDEL-v2/cdel/v18_0/tests_integration/README.md`

