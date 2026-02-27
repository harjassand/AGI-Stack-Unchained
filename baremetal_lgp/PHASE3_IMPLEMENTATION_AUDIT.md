# Phase 3 Implementation + Compliance Audit

Generated: 2026-02-27
Workspace: `/Users/harjas/AGI-Stack-Unchained/baremetal_lgp`

## 1) Final verdict

Phase 3 directive is implemented end-to-end in this repo path, including:
- Compile-to-chunk oracle (`RegimeSpec -> ChunkPack`)
- Deterministic death semantics (SIGALRM and all trap/fault paths -> score 0, no retries)
- Agent B curriculum generator + validity gating + league/archive
- Chunk-only epoch scheduling and coevolution outer loop
- New operational binary `lgp_coev_hotloop`
- Run digest versioning (`RunDigestV2`, `RunDigestV3`) with required Phase 3 fields
- Required Phase 3 tests + DoD tests + deterministic replay test for `workers=1`

No open implementation gaps remain against the directive checklist below.

---

## 2) Gap closure pass (what was missing and closed)

These were identified and closed during this audit pass:

1. Validity gate baselines/champs were too weak.
- Fixed in `src/oracle3/validity.rs`:
  - VMChampSet now deterministically derives from seeded Phase 1 library slots (`CALL_LIB` wrappers), plus fixed affine-capable champ.
  - Zero/copy trivial baselines now operate on full/min lanes, not only lane 0.

2. Invalid B candidates (`fitness = -1e9`) could still enter league/archive.
- Fixed in `src/agent_b/mod.rs`:
  - Early-return before archive/league update when `fitness <= INVALID_FITNESS`.

3. Chunk compile fallback silently substituted default anchor on compile error.
- Fixed in `src/outer_loop/coev.rs`:
  - Removed fallback substitution; scheduled compile/cache lookup is strict and deterministic.

4. Deterministic replay (`workers=1`) not explicitly tested.
- Fixed by adding `tests/phase3_coev_replay.rs`:
  - Runs `lgp_coev_hotloop` twice with same seed and asserts identical `run_digest.txt` and `b_current.json`.

5. `compiled_chunks` was tracked but not emitted for auditability.
- Fixed in `src/bin/lgp_coev_hotloop.rs`:
  - Added `compiled_chunks` to both `summary_latest.txt` and `snapshot_latest.json`.

---

## 3) Directive compliance matrix

## 0) Non-negotiable invariants

### 0.1 Deterministic death semantics
Status: PASS
- Fault mapping to `score=0` and short-circuit in `src/oracle3/mod.rs` (`score_candidate_on_chunk` + `ExecFault`).
- `SIGILL/SIGSEGV/SIGBUS/SIGALRM/other` all mapped to fault outcomes in `RawJitExecEngine`.
- No retries in scoring loop.
- Verified by:
  - `sigalrm_is_zero_score_and_single_attempt`
  - `dod_phase3_sigalrm_is_solver_failure`

### 0.2 Static deterministic compute budget
Status: PASS
- Cost model constants are all `pub const` in `src/oracle3/cost.rs`.
- No runtime calibration/microbenchmark introduced in Phase 3 code path.
- Compiler/validity depend deterministically on `RegimeSpec` + fixed compile seed/config.

### 0.3 Oracle squeeze eliminated by architecture
Status: PASS
- AST evaluation only in compile path (`compile_chunkpack` calls AST interpreter).
- Hot scoring path uses precomputed `ChunkPack` buffers only.
- Verified by unit test `no_ast_calls_during_candidate_scoring` (now in `src/oracle3/mod.rs` unit tests).

### 0.4 Validity gate uses VM champions
Status: PASS
- Implemented in `src/oracle3/validity.rs`:
  - Cost gate
  - Compile gate (validity chunk)
  - VMChampSet baseline gate (`S* >= Srand + DELTA_VALID`)
  - Anti-leak gate (`S* >= S_trivial + DELTA_LEAK`)

### 0.5 Chunk scheduling is chunk-only
Status: PASS
- Epoch schedule built as chunk jobs in `src/outer_loop/coev.rs`.
- Each job compiled once into chunkpack and cached by `(OpponentSource, compile_seed, spec_hash)`.

## 1) File/module plan
Status: PASS
- Added all required Phase 3 modules/files:
  - `src/oracle3/{mod,spec,ast,cost,chunkpack,compile,validity}.rs`
  - `src/agent_b/mod.rs`
  - `src/outer_loop/coev.rs`
  - `src/bin/lgp_coev_hotloop.rs`
- Wired exports in `src/lib.rs`, `src/outer_loop/mod.rs`, `src/search/mod.rs`.

## 2) Core data structures
Status: PASS
- `RegimeSpec`, `InputDistSpec`, `PiecewiseScheduleSpec`, `ScheduleSegment` implemented.
- `spec_hash_32` uses canonical bincode options + BLAKE3.
- AST model implemented with node arena + deterministic evaluator.
- `ChunkPack` SoA + digest + slicing helpers implemented.

## 3) Static deterministic cost model
Status: PASS
- `AstCost` and cap constants exactly present in `src/oracle3/cost.rs`.
- Peak words uses deterministic over-approx sum-of-node-words rule.
- `compute_cost(spec) -> Result<AstCost, CostViolation>` implemented.

## 4) RegimeSpec -> ChunkPack compilation
Status: PASS
- `CompileCfg`, `VALIDITY_COMPILE_CFG`, `FULL_COMPILE_CFG` implemented.
- Per-episode seed derivation + ChaCha8Rng deterministic seed expansion implemented.
- Deterministic layout with bounded attempts + deterministic fallback.
- Meta schema indices `[0..16)` implemented exactly.
- Compile failure modes implemented: cost/shape/meta bounds/output shape/non-finite.

## 5) Chunk scoring
Status: PASS
- MSE -> `1/(1+mse)` scoring in `src/oracle3/mod.rs`.
- Fault episode handling returns chunk score 0 with short-circuit.
- `ChunkScoreReport` implemented with per-signal counters.
- `SNIPER_USEC: i64 = 50_000` implemented in `src/jit2/raw_runner.rs`.

## 6) Validity gate
Status: PASS
- `VMChampSet`, constant-zero baseline, trivial baselines, deltas, full verdict enum implemented.

## 7) Agent B loop
Status: PASS
- Genotype = `RegimeSpec`.
- Required mutation operators implemented:
  - `mut_input_dist_params`
  - `mut_schedule_segments`
  - `mut_ast_local_edit`
  - `mut_ast_insert_affine`
  - `mut_ast_prune_subgraph`
  - `mut_io_lengths`
- B league + archive bins implemented (`B_LEAGUE_K`, `B_BINS`).
- Fitness `1 - S_A` with invalid = `-1e9` implemented.
- Promotion rule (`MIN_A_BREAK`, `DELTA_BREAK`) implemented.

## 8) Coevolution outer loop
Status: PASS
- `OpponentSource`, `ChunkJob`, schedule pattern `K1/K2/K3` implemented.
- Compile cache key rule implemented.
- A promotion rule implemented including no-fault condition.

## 9) Operational binary
Status: PASS
- CLI supports required args in `src/bin/lgp_coev_hotloop.rs`.
- Run dir outputs implemented:
  - `summary_latest.txt`
  - `snapshot_latest.json`
  - `run_digest.txt`
  - `b_current.json`
  - `b_league_0..K-1.json`
- Digest fields include:
  - `b_current_spec_hash`
  - `b_league_topk_hashes`
  - `chunk_schedule_hash`

## 10) Test plan
Status: PASS
- Implemented tests:
  - `agentb_cost_model_rejects_node_overflow`
  - `agentb_cost_model_counts_affine_mac_exactly`
  - `chunkpack_compile_is_bitwise_deterministic`
  - `no_ast_calls_during_candidate_scoring`
  - `sigalrm_is_zero_score_and_single_attempt`
  - `validity_gate_rejects_noise_regime`
  - `validity_gate_accepts_simple_affine_regime`
  - `dod_phase3_sigalrm_is_solver_failure`
  - `dod_phase3_chunkpack_digest_matches`
  - deterministic replay test `phase3_workers1_replay_is_deterministic_by_digest`

## 11) Definition of done
Status: PASS
- All listed DoD points satisfied with code + tests + runtime artifact checks.

---

## 4) File-by-file implementation detail

### New module tree
- `src/oracle3/spec.rs`
  - Defines `RegimeSpec` and family types.
  - Deterministic stable hash via bincode fixed-int LE + BLAKE3.
- `src/oracle3/ast.rs`
  - AST DAG node model + deterministic interpreter.
  - Shape validation and typed errors.
  - AST call counter instrumentation under `cfg(any(test, feature="ast_call_counter"))`.
- `src/oracle3/cost.rs`
  - Deterministic static cost extraction and cap checking.
- `src/oracle3/chunkpack.rs`
  - SoA chunk representation, digest, helpers.
- `src/oracle3/compile.rs`
  - Compiler from spec to chunkpack with deterministic episode RNG and layout.
- `src/oracle3/validity.rs`
  - Validity verdict logic, VM champ/trivial gate scoring.
- `src/oracle3/mod.rs`
  - Scoring loop, fault accounting, raw-jit executor adapter.

### Agent B + coevolution
- `src/agent_b/mod.rs`
  - Regime mutation, fitness evaluation, league/archive maintenance.
- `src/outer_loop/coev.rs`
  - Chunk schedule construction, compile cache, A/B interactions per epoch.

### Binary and digests
- `src/bin/lgp_coev_hotloop.rs`
  - End-to-end operational loop and run artifact emission.
- `src/search/digest.rs`
  - `RunDigestV2` and `RunDigestV3` types + text serializer.

### Existing execution path modifications
- `src/jit2/raw_runner.rs`
  - Added `SNIPER_USEC` constant and `raw_thread_init_with_stall_us` for Phase 3 path.

### New tests
- `tests/phase3_oracle.rs`
- `tests/dod_acceptance_phase3.rs`
- `tests/phase3_coev_replay.rs`
- `src/oracle3/mod.rs` unit test `no_ast_calls_during_candidate_scoring`

---

## 5) Verification commands + results

Executed commands:

```bash
cd /Users/harjas/AGI-Stack-Unchained/baremetal_lgp
cargo test
```

Result: PASS (all tests in crate including existing Phase 2 suites and new Phase 3 suites).

Key phase3-specific test outcomes:
- `tests/phase3_oracle.rs`: 6 passed
- `tests/dod_acceptance_phase3.rs`: 2 passed
- `tests/phase3_coev_replay.rs`: 1 passed
- `src/oracle3/mod.rs` unit test: 1 passed

---

## 6) Runtime artifact dumps (audit run)

Run command:

```bash
cargo run --bin lgp_coev_hotloop -- \
  --seed 20260227 \
  --run-dir /tmp/lgp_coev_phase3_audit_20260227_v3 \
  --epochs 3 \
  --workers 1 \
  --a-evals-per-epoch 64
```

### `/tmp/lgp_coev_phase3_audit_20260227_v3/summary_latest.txt`

```text
epoch=2 a_champion_score=0.526245 b_current_fitness=0.400038 b_current_spec_hash=62fb6663539f2617ae9c0b415e7f995ec421abf7d95f560f13b28fcdbef328d0 sigalrm_count=0 fault_count=0 eval_throughput=40.75/s compiled_chunks=16
```

### `/tmp/lgp_coev_phase3_audit_20260227_v3/snapshot_latest.json`

```json
{
  "a_champion_score": 0.5262453556060791,
  "b_current_fitness": 0.4000380039215088,
  "b_current_spec_hash": "62fb6663539f2617ae9c0b415e7f995ec421abf7d95f560f13b28fcdbef328d0",
  "compiled_chunks": 16,
  "epoch": 2,
  "eval_throughput": 40.74671863571073,
  "fault_count": 0,
  "sigalrm_count": 0
}
```

### `/tmp/lgp_coev_phase3_audit_20260227_v3/run_digest.txt`

```text
version=3
seed=20260227
epochs=3
a_champion_hash=17fbd87aa5ec9afa68aa47267610174d1191bd84bd39e56137df3ea4974cc0cc
b_current_spec_hash=62fb6663539f2617ae9c0b415e7f995ec421abf7d95f560f13b28fcdbef328d0
b_league_topk_hashes=[1e3128ccfc3f74e7cb76d7cc08e1e228c45d8ac4968234fa9b68bcab378a8dd3,e99a534cd2ecb240a9ea3b572b5bacf4fd051df0f2d7a037514ecafcb95d2a72,0000000000000000000000000000000000000000000000000000000000000000,0000000000000000000000000000000000000000000000000000000000000000,0000000000000000000000000000000000000000000000000000000000000000,0000000000000000000000000000000000000000000000000000000000000000,0000000000000000000000000000000000000000000000000000000000000000,0000000000000000000000000000000000000000000000000000000000000000]
chunk_schedule_hash=d0fc5244f54f89d79f30716f1de54a8a29a261aa0216ecd80b4d4204c928ee8e
```

### `/tmp/lgp_coev_phase3_audit_20260227_v3/b_current.json`

```json
{
  "version": 3,
  "spec_seed_salt": 0,
  "input_len": 1,
  "output_len": 1,
  "meta_u32_len": 16,
  "meta_f32_len": 16,
  "episode_param_count": 4,
  "input_dist": {
    "Uniform": {
      "lo": -1.0,
      "hi": 1.0
    }
  },
  "ast": {
    "nodes": [
      {
        "op": "InputVector",
        "shape": {
          "Vector": 1
        }
      },
      {
        "op": {
          "ConstF32": 2.0
        },
        "shape": "Scalar"
      },
      {
        "op": {
          "Mul": {
            "a": 0,
            "b": 1
          }
        },
        "shape": {
          "Vector": 1
        }
      }
    ],
    "output": 2
  },
  "schedule": {
    "segments": []
  }
}
```

### `/tmp/lgp_coev_phase3_audit_20260227_v3/b_league_0.json`

```json
{
  "version": 3,
  "spec_seed_salt": 17264279406726591922,
  "input_len": 1,
  "output_len": 1,
  "meta_u32_len": 16,
  "meta_f32_len": 16,
  "episode_param_count": 4,
  "input_dist": {
    "Uniform": {
      "lo": -1.0,
      "hi": 1.0
    }
  },
  "ast": {
    "nodes": [
      {
        "op": "InputVector",
        "shape": {
          "Vector": 1
        }
      },
      {
        "op": {
          "ConstF32": 2.0
        },
        "shape": "Scalar"
      },
      {
        "op": {
          "Mul": {
            "a": 0,
            "b": 1
          }
        },
        "shape": {
          "Vector": 1
        }
      }
    ],
    "output": 2
  },
  "schedule": {
    "segments": []
  }
}
```

### `/tmp/lgp_coev_phase3_audit_20260227_v3/b_league_1.json`

```json
{
  "version": 3,
  "spec_seed_salt": 2576459091466091185,
  "input_len": 1,
  "output_len": 1,
  "meta_u32_len": 16,
  "meta_f32_len": 16,
  "episode_param_count": 4,
  "input_dist": {
    "Uniform": {
      "lo": -1.0,
      "hi": 1.0
    }
  },
  "ast": {
    "nodes": [
      {
        "op": "InputVector",
        "shape": {
          "Vector": 1
        }
      },
      {
        "op": {
          "ConstF32": 2.0
        },
        "shape": "Scalar"
      },
      {
        "op": {
          "Mul": {
            "a": 0,
            "b": 1
          }
        },
        "shape": {
          "Vector": 1
        }
      }
    ],
    "output": 2
  },
  "schedule": {
    "segments": []
  }
}
```

---

## 7) Deterministic replay dump

Replay run command:

```bash
cargo run --bin lgp_coev_hotloop -- \
  --seed 20260227 \
  --run-dir /tmp/lgp_coev_phase3_audit_20260227_v3_replay \
  --epochs 3 \
  --workers 1 \
  --a-evals-per-epoch 64
```

Digest comparison:

```text
replay_digest_identical=0
```

`0` indicates `cmp` success (files identical).

---

## 8) Notes on observed behavior vs expected behavior section

- `compiled_chunks=16` matches `K1+K2+K3` exactly.
- In this short 3-epoch sample, `b_current_spec_hash` did not change.
  - This does not violate requirements; hash changes are expected "occasionally" over longer runs.
- `sigalrm_count=0` in this sample because generated candidates did not hang in this specific run.
  - SIGALRM-to-zero behavior is separately verified by DoD test (`dod_phase3_sigalrm_is_solver_failure`).

---

## 9) Changed Phase 3 files (primary)

- `src/oracle3/mod.rs`
- `src/oracle3/spec.rs`
- `src/oracle3/ast.rs`
- `src/oracle3/cost.rs`
- `src/oracle3/chunkpack.rs`
- `src/oracle3/compile.rs`
- `src/oracle3/validity.rs`
- `src/agent_b/mod.rs`
- `src/outer_loop/coev.rs`
- `src/bin/lgp_coev_hotloop.rs`
- `src/search/digest.rs`
- `src/jit2/raw_runner.rs`
- `tests/phase3_oracle.rs`
- `tests/dod_acceptance_phase3.rs`
- `tests/phase3_coev_replay.rs`

