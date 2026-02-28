# APF-v3 Integration Handoff (baremetal_lgp)

## Scope
This document summarizes the APF-v3 implementation delivered in `baremetal_lgp`, including determinism, security, morphism gating, wake/judge behavior, artifacts, and test evidence.

## What Was Added

### New module namespace
- `src/apf3/mod.rs`
- `src/apf3/digest.rs`
- `src/apf3/aal_ir.rs`
- `src/apf3/aal_exec.rs`
- `src/apf3/morphisms.rs`
- `src/apf3/nativeblock.rs`
- `src/apf3/sfi.rs`
- `src/apf3/a64_scan.rs`
- `src/apf3/metachunkpack.rs`
- `src/apf3/wake.rs`
- `src/apf3/profiler.rs`
- `src/apf3/omega.rs`
- `src/apf3/judge.rs`

### New binaries
- `src/bin/apf3_wake_hotloop.rs`
- `src/bin/apf3_omega_architect.rs`
- `src/bin/apf3_judge_daemon.rs`

### New tests
- `tests/apf3_sfi_memory_escape.rs`
- `tests/apf3_a64_scan_denylists.rs`
- `tests/apf3_branch_in_slot.rs`
- `tests/apf3_morphism_identity.rs`
- `tests/apf3_metachunk_support_query.rs`
- `tests/apf3_profiler_taxonomy.rs`
- `tests/apf3_end2end_workers1_replay.rs`

### Supportive integration changes
- `src/lib.rs` exports `pub mod apf3;`
- `Cargo.toml` adds deterministic RNG crate `rand` (existing `serde`, `serde_json`, `blake3`, `rand_chacha`, `libc` are used)
- Native trampoline/FFI extended to support explicit APF3 stack pointer and `i32` return ABI:
  - `native_jit/jit_trampoline.c`
  - `native_jit/jit_trampoline.h`
  - `src/jit2/ffi.rs`

## Non-negotiables Compliance

### 1) Determinism-first
- Canonical seed mixing is centralized in `apf3::splitmix64` and `apf3::mix_seed`.
- Deterministic RNG entrypoint is provided: `seeded_rng` using `ChaCha12Rng::seed_from_u64(mix_seed(...))`.
- Atomic artifact writing uses deterministic pathing + rename (`write_atomic`).
- Each APF3 executable includes `--seed` and writes `run_digest.txt` in `run-dir/apf3/`:
  - Wake digest includes config, pack digests, candidate digests, and aggregate score/failure metrics.
  - Omega digest includes config, graph/diff identity, candidate/pack context from profiler (if present), and summarized metrics.
  - Judge digest includes config, heldout/anchor pack digests, baseline/promoted candidate digests, and summarized heldout/anchor metrics.
- Replay determinism gate implemented and passing:
  - `tests/apf3_end2end_workers1_replay.rs`

### 2) Fail-closed security
- NativeBlock enforcement stack:
  - Address-space SFI window mapping and in-window heap/stack/state allocations (`sfi.rs`).
  - AArch64 denylist + branch containment + RET-final rule (`a64_scan.rs`).
  - NativeBlock install rejects on scan uncertainty/failure (`nativeblock.rs`).
  - Runtime pointer-range checks ensure only in-window pointers are passed.
  - Faults/timeouts map to typed failures (`NativeExecError` -> `ExecStop::NativeBlockFault/NativeBlockTimeout`) with score zeroing in executor.
- Memory escape test verifies no harness crash and fail-closed scoring:
  - `tests/apf3_sfi_memory_escape.rs`

### 3) Morphism-only diffs
- `ArchitectureDiff` accepts bounded morphism enum only.
- `validate()` enforces base digest and hard constraints (e.g., `alpha_init==0`, closed memory init, zero-head init).
- `validate_against_graph()` adds fail-closed graph-aware checks (anchor existence/type inferability, detached-only widening policy in v1, swap identity-init constraints, etc.).
- `identity_check()` enforces per-query replay equivalence (not just mean).
- Wake/Omega both gate on `validate_against_graph()` + `identity_check()` before continuing.

### 4) Silent Judge is sole promoter
- Wake does evaluation/reporting/receipts only; never updates active candidate pointer.
- Judge performs promotion decisions using heldout + anchor packs and identity gate evidence.
- Judge caches by `(candidate_hash, pack_digest)` at:
  - `run-dir/apf3/cache/<candidate_hash>/<pack_digest>.json`
- Promotion writes receipt + activation pointer file only:
  - `run-dir/apf3/receipts/judge/...`
  - `run-dir/apf3/registry/active_candidate.json`

## Artifact Contract

### Wake artifacts (`run-dir/apf3/`)
- `summary_latest.txt`
- `snapshot_latest.json`
- `run_digest.txt`
- `reports/<candidate_hash>.json`
- `reports/latest.json`
- `receipts/wake/<candidate_hash>_<pack_set_digest>.json`
- `registry/candidates/<candidate_hash>.json`
- `registry/diffs/<candidate_hash>.json`

### Judge artifacts (`run-dir/apf3/`)
- `summary_latest.txt`
- `snapshot_latest.json`
- `run_digest.txt`
- `receipts/judge/<candidate_hash>.json` (promote) or `reject_<hash>.json`
- `registry/active_candidate.json`
- `cache/<candidate_hash>/<pack_digest>.json`

### Omega artifacts (`run-dir/apf3/`)
- `run_digest.txt`
- Optional prompt file via `--prompt-out`
- Reject diagnostics: `<out-diff>.reject.json`

## Operational CLI (implemented)

### Wake
```bash
cargo run --release --bin apf3_wake_hotloop -- \
  --seed 20260227 \
  --run-dir /tmp/apf3_wake \
  --workers 4 \
  --max-candidates 50000 \
  --train-pack-dir /tmp/apf3_wake/apf3/packs/train \
  --proposal-dir /tmp/apf3_wake/apf3/proposals
```

### Omega (prompt-only)
```bash
cargo run --release --bin apf3_omega_architect -- \
  --run-dir /tmp/apf3_wake \
  --graph /tmp/apf3_wake/apf3/registry/base_graph.json \
  --profiler-report /tmp/apf3_wake/apf3/reports/latest.json \
  --llm-mode prompt_only \
  --prompt-out /tmp/apf3_prompt.txt \
  --out-diff /tmp/apf3_diff.json
```

### Judge
```bash
cargo run --release --bin apf3_judge_daemon -- \
  --seed 20260227 \
  --run-dir /tmp/apf3_wake \
  --heldout-salt-file /tmp/apf3_heldout_salt.bin \
  --heldout-pack-dir /tmp/apf3_wake/apf3/packs/heldout
```

## Validation Evidence
- `cargo test apf3_ --tests` passes.
- `cargo test sfi_alloc_heap_alignment_and_bounds` passes (SFI allocator/range alignment unit check).
- CLI mode contract includes `prompt_only` exactly for Omega.

## Notes for Researchers
- APF3 graph execution is deterministic and fail-closed by construction; any invalid graph/native path yields zero-score outcomes and typed failure labels.
- v1 widening policy is intentionally strict/fail-closed: detached linear widen only (identity-preserving without ambiguous downstream rewiring).
- Judge includes both heldout and anchor pack evaluation; heldout improvement + anchor non-regression + zero failures + identity gate are required for promotion.
