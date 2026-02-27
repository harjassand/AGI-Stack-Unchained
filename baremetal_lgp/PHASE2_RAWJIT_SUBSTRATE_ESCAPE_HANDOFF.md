# Phase 2 Substrate Escape (RawAArch64 JIT) - Implementation Handoff

Date: 2026-02-27  
Workspace: `/Users/harjas/AGI-Stack-Unchained/baremetal_lgp`

## 1) Executive Summary
Phase 2 has been implemented as an isolated parallel subsystem (`jit2` + `native_jit`) with a new binary (`raw_hotloop`) so the Phase 1 VM path remains intact.

The implementation now includes:
- Raw AArch64 candidate execution (`Vec<u32>`) with hard bounds.
- Native trap recovery for `SIGILL`, `SIGSEGV`, `SIGBUS`, `SIGALRM`.
- Sniper watchdog timeout interruption outside the hot path.
- Per-thread MAP_JIT arenas with slot wipe and full icache invalidation.
- Correct Apple MAP_JIT W^X toggle ordering (`write-protect off -> write/flush -> write-protect on`).
- Callee-saved register preservation (`x19..x29`, `q8..q15`) across success and trap paths.
- Caller-saved NEON clobbers (`v0-v7`, `v16-v31`) declared for raw-call inline asm safety.
- Full runtime state wipe before every episode.
- Raw oracle path with crash gating, stability gating, promotion, epoch swap, and rollback.
- New Phase 2 tests and a passing validation run.

## 2) Directive Compliance Matrix

### 0.1 Done Gates
1. Raw candidate format (`Vec<u32>`, hard max): **Implemented**.
2. Recover from `SIGILL/SIGSEGV/SIGBUS`: **Implemented and tested**.
3. Hang timeout via sniper (not hot path): **Implemented and tested**.
4. Thread-owned MAP_JIT arena per worker: **Implemented**.
5. Preserve `x19..x29`, `q8..q15` across success/trap: **Implemented and tested**.
6. Promote + epoch hot-swap + rollback: **Implemented**.
7. Three substrate modes (VM baseline / MacroASM optional / Raw): **Implemented via mode enum + separate VM and Raw binaries; MacroASM remains optional mode placeholder**.

### 0.2 Dirty State Poisoning fix
- Mandatory full wipe before every episode: **Implemented in `run_raw_candidate`**.
- Oracle-owned pre-run scoring params only: **Implemented and regression-tested**.

### 1) Branching + PR slicing
- Recommended process items (branch naming and PR slicing): **Process guidance, not code requirement**.

### 2) Required file tree
All requested Phase 2 files are present.

### 3) Build integration
- `build.rs` compiles both C sources at `-O3`: **Implemented**.
- `cc = "1.0"` build dependency: **Implemented**.

### 4) Phase 2 constants
All required constants added in `src/jit2/constants.rs`: **Implemented**.

### 5) RuntimeState ABI
- Rust `RuntimeState` matches required shape/order/alignment.
- C mirror struct included in `jit_trampoline.h` with matching layout assumptions.

### 6) Native trap layer
- TLS env/armed/last trap: **Implemented**.
- Altstack + signal handlers + SA_ONSTACK: **Implemented**.
- Async-signal-safe handler behavior and longjmp path: **Implemented**.
- Manual save/restore of required regs around candidate: **Implemented**.
- Dedicated JIT execution stack with guard pages: **Implemented**.

### 7) Sniper watchdog
- Worker watch atomics and FFI pointer registration: **Implemented**.
- C watchdog loop with relaxed atomic loads and `pthread_kill(SIGALRM)`: **Implemented**.
- Hot path only updates local atomics: **Implemented**.

### 8) JIT arena
- Per-thread contiguous MAP_JIT arena + slots: **Implemented**.
- Slot 0 active kernel / slot 1 candidate path: **Implemented**.
- Write-protect toggles + full slot RET wipe + full icache invalidate: **Implemented**.

### 9) RawRunner safe entrypoint
- `raw_thread_init(watch)` and `run_raw_candidate(ctx, words, spec)`: **Implemented**.
- Full wipe sequence and scoring safety rules: **Implemented**.

### 10) Raw oracle integration
- Parallel `RawOracle` path added in `oracle/raw.rs`: **Implemented**.
- `RawEvalReport` fields match directive minimum: **Implemented**.
- Proxy/full/stability and crash gating rules: **Implemented**.

### 11) Templates + mutation
- Required templates (`ret_only`, `two_ret`, `nops_then_ret`): **Implemented**.
- Templates verified no-trap-return in tests: **Implemented**.
- All required mutation operators and constraints: **Implemented**.

### 12) Promotion + swap/rollback
- `ActiveRawKernel {hash, words, epoch}` model: **Implemented**.
- Worker slot0 install on epoch/hash change: **Implemented**.
- `EPOCH_EVALS=50_000`, publish, history N=3, rollback logic: **Implemented**.

### 13) Mode wiring
- New Phase 2 binary `raw_hotloop`: **Implemented**.
- CLI args match required minimum: **Implemented**.
- Snapshot outputs with trap/timeout counters: **Implemented**.

### 14) Tests
All required macOS/AArch64-gated tests added and passing.

### 15) Hot path constraints
`run_raw_candidate` hot path is wipe + slot write/flush + C trampoline + score; no logging, no allocation, no locks in that path: **Implemented**.

## 3) Files Added
- `build.rs`
- `native_jit/jit_trampoline.h`
- `native_jit/jit_trampoline.c`
- `native_jit/sniper.h`
- `native_jit/sniper.c`
- `src/jit2/mod.rs`
- `src/jit2/constants.rs`
- `src/jit2/abi.rs`
- `src/jit2/ffi.rs`
- `src/jit2/arena.rs`
- `src/jit2/raw_runner.rs`
- `src/jit2/sniper.rs`
- `src/jit2/templates.rs`
- `src/jit2/mutate.rs`
- `src/jit2/promote.rs`
- `src/jit2/swap.rs`
- `src/oracle/raw.rs`
- `src/bin/raw_hotloop.rs`
- `tests/phase2_rawjit_traps.rs`
- `tests/phase2_rawjit_sniper.rs`
- `tests/phase2_rawjit_regsave.rs`
- `tests/phase2_rawjit_statewipe.rs`

## 4) Files Updated
- `Cargo.toml` (build-dependency `cc`)
- `src/lib.rs` (`pub mod jit2`)
- `src/oracle/mod.rs` (`pub mod raw`)

## 5) Native Layer Details
- `jit_trap_thread_init()` performs per-thread altstack allocation/install and ensures signal handlers are installed.
- Signals handled: `SIGILL`, `SIGSEGV`, `SIGBUS`, `SIGALRM`, `SIGTRAP`, `SIGFPE`, `SIGSYS`, `SIGABRT`.
- Signal handler behavior:
  - `armed==0`: fatal host bug path (`_exit`), except unarmed `SIGALRM` is ignored as a benign sniper race tail event.
  - `armed==1`: fills TLS `trap_info_t`, then `siglongjmp`.
- Dedicated JIT execution stack:
  - Thread-local mmap region with guard pages (`PROT_NONE`) on both sides.
  - Candidate runs on JIT stack; signal handler runs on altstack.
- Register preservation:
  - Manual save/restore of `x19..x29` and `q8..q15` around candidate execution.
  - Restored on both success and trap paths.
- Inline asm raw-call clobber declaration now includes caller-saved vector regs (`v0-v7`, `v16-v31`) in addition to caller-saved GPRs.

## 6) Rust JIT2 Details
- `RuntimeState` (`repr(C, align(16))`) mirrors C ordering.
- `RuntimeState::wipe_all()` zeroes scratch/fregs/iregs/meta/status every episode.
- `JitArena`:
  - Per-thread MAP_JIT allocation.
  - Slot model: slot0 active substrate, slot1 candidate eval.
  - Explicit W^X sequence: disable protection (`pthread_jit_write_protect_np(0)`), write + pad RET, full icache invalidate, re-enable protection (`...np(1)`).
  - Full-slot RET wipe and full-slot icache invalidation per write.
- `WorkerWatch`:
  - `armed` + `progress` atomics; hot path only local atomic ops.
- `run_raw_candidate`:
  - Hard candidate bound checks.
  - Full wipe sequence before each run.
  - Score computed from oracle-owned `EpisodeSpec` data captured pre-run.
  - Per-episode `FaultKindCounts` emitted for external aggregation.

## 7) Raw Oracle + Evolution Flow
- `RawOracle` implements:
  - Proxy (2 episodes), Full (16 episodes), Stability (3xFull).
  - Proxy crash gate: reject if `trap_rate > 0.10`.
  - Promotion gate helper: require `trap_rate == 0` and `timeout_rate == 0` in stability.
- `ActiveRawKernel`:
  - Immutable shared words (`Arc<Vec<u32>>`) + hash + epoch.
- `KernelSwapState`:
  - Atomic eval counting with epoch boundary detection.
  - Publish new kernels at epoch boundaries.
  - Keep last 3 kernels for rollback.
  - Rollback on score drop/trap rise/timeout.

## 8) Tests Added and What They Prove
- `phase2_rawjit_traps.rs`
  - Safe templates return without traps.
  - Invalid word stream traps SIGILL and recovers.
  - Raw null-write candidate traps SIGSEGV and recovers.
  - Dedicated helper path traps SIGBUS and recovers.
- `phase2_rawjit_sniper.rs`
  - Infinite loop candidate (`b .`) is interrupted via SIGALRM.
  - Subsequent safe candidate still runs.
- `phase2_rawjit_regsave.rs`
  - Candidate clobbers callee-saved regs.
  - Pre/post snapshots verify preservation across success and trap.
- `phase2_rawjit_statewipe.rs`
  - Meta poisoning across successful and trapping episodes is wiped before next episode.
  - Scoring uses pre-run oracle-owned dimensions (not post-run meta mutation).

## 9) Validation Results
Commands run:
- `cargo check`
- `cargo test phase2_rawjit_ -- --nocapture`

Result:
- `cargo check`: **PASS**
- Phase 2 test suite: **PASS**
  - `phase2_rawjit_traps_sigill_and_recovers`: PASS
  - `phase2_rawjit_sniper_interrupts_hang_and_recovers`: PASS
  - `phase2_rawjit_regsave_restores_across_success_and_trap`: PASS
  - `phase2_rawjit_statewipe_full_wipe_and_oracle_owned_scoring`: PASS

### 9.1 Performance Results (Release, 2026-02-27)
Benchmark command shape:
- `target/release/raw_hotloop --run-dir runs/phase2_verify_final_w<N> --workers <N> --max-evals 500000 --seed 424242`

Phase 2 throughput results:

| Workers | Eval Throughput (/s) | Speedup vs W1 | Completed | Traps | Timeouts |
|---|---:|---:|---:|---:|---:|
| 1 | 10,369.46 | 1.00x | 500,000 | 0 | 0 |
| 2 | 17,160.47 | 1.65x | 500,000 | 0 | 0 |
| 4 | 29,299.86 | 2.83x | 500,000 | 0 | 0 |
| 6 | 35,564.89 | 3.43x | 500,000 | 0 | 0 |

Phase 1 reference (same machine/session, release, 500k evals, W=1):
- Throughput: **14,965.70 eval/s**

Derived comparison:
- Phase 2 W=1 vs Phase 1 W=1: **0.69x** (Phase 2 is ~30.7% lower at current mutation safety profile).
- Phase 2 scaling efficiency W=4: **2.83x** (within the target 2.5x-4.0x band for thread scaling).
- 500k-run survival for W=1/2/4/6: **all completed with `rc=0`**, no kernel panic observed.

Exact summary lines captured:
- W1: `wins/hour=0.000 champion_mu=-0.288838 champion_var=inf filled_bins=0 eval_throughput=10369.46/s completed=500000 traps=0 timeouts=0 trap_rate=0.000000 timeout_rate=0.000000 active_epoch=4`
- W2: `wins/hour=0.000 champion_mu=-0.306042 champion_var=inf filled_bins=0 eval_throughput=17160.47/s completed=500000 traps=0 timeouts=0 trap_rate=0.000000 timeout_rate=0.000000 active_epoch=3`
- W4: `wins/hour=0.000 champion_mu=-0.307242 champion_var=inf filled_bins=0 eval_throughput=29299.86/s completed=500000 traps=0 timeouts=0 trap_rate=0.000000 timeout_rate=0.000000 active_epoch=4`
- W6: `wins/hour=0.000 champion_mu=-0.316751 champion_var=inf filled_bins=0 eval_throughput=35564.89/s completed=500000 traps=0 timeouts=0 trap_rate=0.000000 timeout_rate=0.000000 active_epoch=4`
- Phase1 W1: `wins/hour=0.000 champion_mu=-0.299163 champion_var=0.040887 filled_bins=328 eval_throughput=14965.70/s completed=500000`

## 10) Runtime/Operational Notes
- `raw_hotloop` keeps Phase 2 isolated from existing Phase 1 `lgp_hotloop`.
- Worker watch instances are intentionally process-lived in tests and `raw_hotloop` workers to avoid stale-pointer polling by the global sniper thread at teardown.
- Snapshot files emitted by `raw_hotloop`:
  - `snapshot_latest.json`
  - `summary_latest.txt`
- Direct PMU/L2 counter collection was not captured in this run set due environment limits:
  - `powermetrics` requires superuser.
  - `xctrace record` was blocked by execution policy.

## 11) Handoff Checklist
- Build and run Phase 1 binary unchanged:
  - `cargo run --bin lgp_hotloop -- ...`
- Build and run Phase 2 binary:
  - `cargo run --bin raw_hotloop -- --run-dir <path> --workers <n> --max-evals <u64> [--seed <u64>]`
- Validate Phase 2 tests:
  - `cargo test phase2_rawjit_ -- --nocapture`

## 12) Known Non-Blocking Notes
- Branching/PR slicing guidance from the directive was process-oriented and not enforced in code.
- Optional MacroASM mode remains optional; mode enum includes a placeholder variant, while VM baseline and RawAArch64 execution modes are operational.
