# APF-SC Phase 1 MVP - Full End-to-End Implementation Specification

This document is the implementation contract for a codex agent. It converts the Phase 1 design into a repo-ready MVP that is complete end to end on one machine, with deterministic judged execution, sealed inputs, public and holdout evaluation, structural candidate generation, incubator maturation, canarying, rollback, and atomic activation.

The goal of this MVP is not full open-ended paradigm invention. The goal is to stand up a correct recursive architecture laboratory kernel that can:

1. ingest sealed data, prior, and substrate packs,
2. build deterministic train/public/holdout/anchor/canary banks,
3. compile and run SCIR-Lite candidates,
4. score candidates on raw-byte next-byte MDL,
5. mature novelty through equivalence and incubator lanes before judged promotion,
6. judge and activate S and A class candidates only,
7. preserve strict protocol boundaries inherited from APF-v3,
8. run within an effective 16 GB unified-memory ceiling.

This is the minimum complete foundation for later Phase 2/3/4 work.

---

## 1. Hard constraints

Codex must follow these constraints exactly.

### 1.1 Trusted substrate boundary

Treat the existing APF-v3 substrate in `baremetal_lgp` / `apf3` as immutable. Do not rewrite trusted protocol law. Reuse existing facilities where available for:

- deterministic replay capsules and digests,
- content-addressed artifacts,
- atomic pointer writes,
- judge-only activation,
- fail-closed execution,
- rollback primitives.

If the names differ in the repo, add adapter code at the APF-SC boundary. Do not refactor the APF-v3 core.

### 1.2 MVP scope

Implement now:

- `RealityPack`, `PriorPack`, `SubstratePack` ingress,
- `WindowBank` with train/public/holdout/anchor/canary/mini-transfer splits,
- raw-byte bytecoder and MDL scoring,
- SCIR-Lite AST, verifier, and Tier-0 interpreter,
- `HeadPack`, `StatePack`, `SchedulePack`, `WarmRefinementPack`, `EpochSnapshot`,
- truth lane,
- equivalence lane,
- incubator lane,
- cold-frontier stub lane,
- judge daemon,
- shadow canary worker,
- genealogy/error/failure/hardware archives,
- one-shot epoch orchestrator,
- seed fixtures and integration tests.

Do not implement now:

- P-warm or P-cold promotion,
- NativeBlock in judged path,
- distributed execution,
- search-law promotion,
- dynamic tool execution in judged path,
- multi-parent recombination,
- full e-graph engine,
- general autograd framework,
- protocol self-modification.

### 1.3 Runtime envelope

Target a single Apple-silicon machine with a hard effective 16 GB memory budget. Treat this as a protocol envelope regardless of physical RAM.

Initial limits:

```text
RSS_HARD_LIMIT_BYTES          = 12 GiB
RSS_ABORT_LIMIT_BYTES         = 14 GiB
MAX_CONCURRENT_MAPPED_BYTES   = 2 GiB
SEGMENT_BYTES                 = 256 MiB
STATE_TILE_BYTES_MAX          = 2 MiB
MAX_PUBLIC_WORKERS            = 2
MAX_INCUBATOR_WORKERS         = 1
MAX_CANARY_WORKERS            = 1
MAX_PUBLIC_CANDIDATES         = 32
MAX_HOLDOUT_ADMISSIONS        = 8
MAX_RESIDENT_INCUBATORS       = 12
FAST_WEIGHT_MAX_BYTES         = 2 MiB
```

The judged path must remain stable with zero pageouts.

---

## 2. What success means

Phase 1 MVP is done when all of the following are true:

1. `cargo test` passes for all APF-SC unit, property, and end-to-end tests.
2. Two seed `RealityPack`s can be ingested and split deterministically.
3. A seed incumbent candidate can be initialized and scored.
4. At least one equivalence-lane candidate is generated and verified.
5. At least one incubator sidecar is trained behind shadow heads and converted into a splice candidate.
6. `apfsc_epoch_run --epochs 1` produces public receipts, holdout receipts, and either a reject or promotion receipt.
7. If a candidate passes judge and canary, `active_candidate` is atomically updated.
8. Replay of the same epoch with the same snapshot reproduces the same receipts exactly.

A successful demo run should look like:

```text
seed init -> ingress reality/prior/substrate -> build snapshot -> spawn candidates
-> witness prefilter -> public eval -> holdout admission -> judge
-> canary -> atomic activate or reject -> archive update
```

---

## 3. Repo layout to add

Keep existing APF-v3 modules untouched. Extend the repo with the following tree.

```text
src/apfsc/
  mod.rs
  constants.rs
  errors.rs
  types.rs
  protocol.rs
  config.rs
  artifacts.rs
  bytecoder.rs
  mdl.rs
  bank.rs
  candidate.rs
  headpack.rs
  bridge.rs
  emission.rs
  schedule_pack.rs
  hardware_oracle.rs
  judge.rs
  canary.rs
  seed.rs
  orchestrator.rs

  scir/
    mod.rs
    ast.rs
    verify.rs
    interp.rs
    rewrite.rs

  lanes/
    mod.rs
    truth.rs
    equivalence.rs
    incubator.rs
    cold_frontier_stub.rs

  ingress/
    mod.rs
    manifest.rs
    judge.rs
    reality.rs
    prior.rs
    substrate.rs
    receipts.rs

  archive/
    mod.rs
    genealogy.rs
    error_atlas.rs
    failure_morph.rs
    hardware_trace.rs

src/bin/
  apfsc_seed_init.rs
  apfsc_ingest_reality.rs
  apfsc_ingest_prior.rs
  apfsc_ingest_substrate.rs
  apfsc_public_eval.rs
  apfsc_judge_daemon.rs
  apfsc_shadow_canary.rs
  apfsc_epoch_run.rs
```

Add fixture content:

```text
fixtures/apfsc/
  reality_f0_det/
    manifest.json
    payload.bin
  reality_f1_text/
    manifest.json
    payload.bin
  prior_seed/
    manifest.json
    ops.json
    macros.json
  substrate_seed/
    manifest.json
    traces.jsonl
  config/
    phase1.toml
```

Add tests:

```text
tests/apfsc_phase1_ingress.rs
tests/apfsc_phase1_bank.rs
tests/apfsc_phase1_scir.rs
tests/apfsc_phase1_lanes.rs
tests/apfsc_phase1_judge.rs
tests/apfsc_phase1_e2e.rs
```

Export the module from `src/lib.rs`:

```rust
pub mod apfsc;
```

---

## 4. Crate dependencies

Use a small dependency surface. Prefer repo-existing crates if already present.

Required or strongly preferred:

- `serde`, `serde_json`
- `blake3`
- `thiserror`
- `clap`
- `memmap2`
- `csv` or JSONL only if already used elsewhere
- `rand_chacha`
- `parking_lot` or std sync only if needed
- `tempfile` for tests

Avoid introducing a large tensor stack for judged execution. If the repo already has a deterministic training utility, discovery-only code may reuse it. Otherwise implement the MVP training law manually as specified below.

---

## 5. MVP simplifications

These simplifications are intentional and should not be "improved away" during MVP implementation.

1. The judged path uses only the Rust Tier-0 interpreter.
2. `SCIR-Lite` is intentionally small.
3. Learning law is restricted to deterministic head/residual training plus bounded sidecar tuning. Full general trainable recurrent weights are deferred.
4. Search law is static heuristics and deterministic enumeration, not promoted recursion.
5. The equivalence lane uses a bounded rewrite set, not a full persistent e-graph engine.
6. The incubator lane grows sidecar feature modules and trains shadow heads before splice.
7. `FormalPack` and `ToolPack` are out of scope for this MVP.
8. `SubstratePack` is used only to build the hardware oracle and receipts, not to authorize promotion.

---

## 6. On-disk artifact model

All APF-SC artifacts live under one root directory configured by `phase1.toml`. Default: `.apfsc/`.

```text
.apfsc/
  protocol/
    version.json
    judge_policy.json
  snapshots/
    <snapshot_hash>.json
  packs/
    reality/<hash>/manifest.json
    reality/<hash>/payload.bin
    prior/<hash>/manifest.json
    prior/<hash>/ops.json
    prior/<hash>/macros.json
    substrate/<hash>/manifest.json
    substrate/<hash>/traces.jsonl
  banks/
    <family_id>/
      manifest.json
      train_windows.jsonl
      public_windows.jsonl
      holdout_windows.jsonl
      anchor_windows.jsonl
      canary_windows.jsonl
      transfer_train_windows.jsonl
      transfer_eval_windows.jsonl
  candidates/
    <candidate_hash>/
      manifest.json
      arch_program.json
      state_pack.bin
      head_pack.bin
      bridge_pack.json
      schedule_pack.json
      build_meta.json
  receipts/
    ingress/<receipt_hash>.json
    public/<candidate_hash>.json
    holdout/<candidate_hash>.json
    judge/<candidate_hash>.json
    canary/<candidate_hash>.json
    activation/<candidate_hash>.json
  pointers/
    active_candidate
    rollback_candidate
    active_snapshot
  archive/
    genealogy.jsonl
    error_atlas.jsonl
    failure_morph.jsonl
    hardware_trace.jsonl
```

Rules:

- Every content artifact is content-addressed by BLAKE3.
- Pointer files are the only mutable files and must be atomically written.
- Receipts are immutable.
- Holdout windows are referenced by digest and split manifest only; public code cannot inspect payload after the split stage.

---

## 7. Core data contracts

These types should be implemented directly in Rust. Field names may be adapted to repo style, but the semantics must be preserved.

### 7.1 Common types

```rust
pub type DigestHex = String;
pub type FamilyId = String;
pub type CandidateId = String;
pub type SnapshotId = String;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ResourceEnvelope {
    pub max_steps: u64,
    pub max_state_bytes: u64,
    pub max_param_bits: u64,
    pub max_wall_ms: u64,
    pub peak_rss_limit_bytes: u64,
    pub max_mapped_bytes: u64,
    pub backend: BackendKind,
    pub batch_shape: (u32, u32),
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum BackendKind {
    Tier0Cpu,
    Tier1Stub,
}
```

### 7.2 Ingress packs

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum PackKind {
    Reality,
    Prior,
    Substrate,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PackManifest {
    pub pack_kind: PackKind,
    pub pack_hash: DigestHex,
    pub protocol_version: String,
    pub created_unix_s: u64,
    pub family_id: Option<FamilyId>,
    pub provenance: Provenance,
    pub payload_hashes: Vec<DigestHex>,
    pub meta: serde_json::Value,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Provenance {
    pub source_name: String,
    pub source_type: String,
    pub attestation: Option<String>,
    pub notes: Option<String>,
}
```

### 7.3 WindowBank

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum SplitKind {
    Train,
    Public,
    Holdout,
    Anchor,
    Canary,
    TransferTrain,
    TransferEval,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WindowRef {
    pub family_id: FamilyId,
    pub split: SplitKind,
    pub seq_hash: DigestHex,
    pub start: u64,
    pub len: u32,
    pub target_offset: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BankManifest {
    pub family_id: FamilyId,
    pub source_pack_hash: DigestHex,
    pub window_len: u32,
    pub stride: u32,
    pub split_counts: std::collections::BTreeMap<String, u64>,
    pub manifest_hash: DigestHex,
}
```

### 7.4 Candidate object

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum PromotionClass {
    S,
    A,
    PWarmDisabled,
    PColdDisabled,
    GDisabled,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EpochSnapshot {
    pub snapshot_hash: SnapshotId,
    pub reality_roots: Vec<DigestHex>,
    pub prior_roots: Vec<DigestHex>,
    pub substrate_roots: Vec<DigestHex>,
    pub protocol_version: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CandidateManifest {
    pub candidate_hash: CandidateId,
    pub parent_hashes: Vec<CandidateId>,
    pub snapshot_hash: SnapshotId,
    pub promotion_class: PromotionClass,
    pub interface_pack_hash: DigestHex,
    pub arch_program_hash: DigestHex,
    pub state_pack_hash: DigestHex,
    pub head_pack_hash: DigestHex,
    pub bridge_pack_hash: Option<DigestHex>,
    pub schedule_pack_hash: DigestHex,
    pub prior_deps: Vec<DigestHex>,
    pub substrate_deps: Vec<DigestHex>,
    pub resource_envelope: ResourceEnvelope,
    pub build_meta_hash: DigestHex,
}
```

### 7.5 State, head, bridge, schedule

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StatePack {
    pub core_weights: Vec<f32>,
    pub resid_weights: Vec<f32>,
    pub fast_weight_budget_bytes: u64,
    pub init_state: Vec<f32>,
    pub codec_version: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HeadPack {
    pub native_head: LinearHead,
    pub nuisance_head: LinearHead,
    pub residual_head: LinearHead,
    pub shadow_heads: Vec<LinearHead>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LinearHead {
    pub in_dim: u32,
    pub out_dim: u32,
    pub weights: Vec<f32>,
    pub bias: Vec<f32>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WarmRefinementPack {
    pub protected_families: Vec<FamilyId>,
    pub max_anchor_regress_bits: f64,
    pub max_public_regress_bits: f64,
    pub migration_policy: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SchedulePack {
    pub backend: BackendKind,
    pub tile_bytes: u64,
    pub segment_bytes: u64,
    pub predicted_cost: Option<PredictedCost>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PredictedCost {
    pub wall_ms: f64,
    pub peak_rss_bytes: u64,
    pub risk_score: f64,
}
```

### 7.6 Receipts

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ByteScoreReceipt {
    pub candidate_hash: CandidateId,
    pub snapshot_hash: SnapshotId,
    pub split: SplitKind,
    pub family_scores_bits: std::collections::BTreeMap<FamilyId, f64>,
    pub total_bits: f64,
    pub mean_bits_per_byte: f64,
    pub peak_rss_bytes: u64,
    pub wall_ms: u64,
    pub replay_hash: DigestHex,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum JudgeDecision {
    Promote,
    Reject,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PromotionReceipt {
    pub candidate_hash: CandidateId,
    pub incumbent_hash: CandidateId,
    pub decision: JudgeDecision,
    pub reason: String,
    pub public_delta_bits: f64,
    pub holdout_delta_bits: f64,
    pub anchor_regress_bits: f64,
    pub canary_required: bool,
    pub canary_result: Option<String>,
    pub snapshot_hash: SnapshotId,
}
```

---

## 8. Seed families and fixtures

The MVP must ship with two seed reality families.

### 8.1 Family F0 - deterministic microtheory bytes

Generate a synthetic byte sequence from a deterministic mixture of:

- exact periodic runs,
- stack-machine trace bytes,
- delimiter-reset segments,
- simple copy patterns,
- deterministic counter modulo patterns.

Purpose:

- force the system to allow near-delta predictions,
- test exactness and anchor protection,
- give the incubator a clean novelty target.

### 8.2 Family F1 - passive text/code bytes

A fixed local payload fixture, for example a checked-in ASCII text or code snippet pack.

Purpose:

- provide noisy but structured real-sequence behavior,
- test nuisance handling,
- test generalization beyond F0.

### 8.3 Initial split policy

Use fixed deterministic split ratios over the committed byte stream:

```text
train          60%
public         15%
holdout        10%
anchor          5%
canary          5%
transfer_train  3%
transfer_eval   2%
```

All split boundaries are computed by manifest hash and deterministic offsets. The same payload must always produce the same windows.

Window defaults:

```text
window_len = 256
stride     = 64
target     = next byte
```

---

## 9. SCIR-Lite specification

This MVP uses a restricted architecture calculus. It must be simple, deterministic, and sufficient for safe structural change.

### 9.1 Allowed op set

Implement these op families only.

```rust
pub enum ScirOp {
    ByteEmbedding { vocab: u32, dim: u32 },
    LagBytes { lags: Vec<u32> },
    Linear { in_dim: u32, out_dim: u32, bias: bool },
    Add,
    Mul,
    Tanh,
    Sigmoid,
    Relu,
    Concat,
    ReduceMean,
    ReduceSum,
    ShiftRegister { width: u32 },
    RunLengthBucket { buckets: u32 },
    ModCounter { modulus: u32 },
    RollingHash { n: u32, buckets: u32 },
    DelimiterReset { byte: u8 },
    SimpleScan { in_dim: u32, hidden_dim: u32 },
    ReadoutNative { in_dim: u32 },
    ReadoutShadow { in_dim: u32, head_ix: u32 },
}
```

### 9.2 SCIR program shape

A program is a topologically ordered list of nodes with typed tensors.

```rust
pub struct ScirProgram {
    pub input_len: u32,
    pub nodes: Vec<ScirNode>,
    pub outputs: ProgramOutputs,
    pub bounds: ScirBounds,
}
```

`ProgramOutputs` must include:

- `feature_node` - the main feature tensor used by heads,
- `shadow_feature_nodes[]` - optional sidecar features,
- optional probe outputs for archive logging.

### 9.3 Verification rules

Reject any program that violates any of the following.

- dynamic allocation in execution path,
- cycles outside explicit `SimpleScan`,
- tensor shapes not inferrable statically,
- estimated state bytes above `max_state_bytes`,
- parameter bits above `max_param_bits`,
- nested gathers or arbitrary indexing,
- non-causal dependence,
- unsupported op or dtype,
- more than one scan loop,
- shadow heads writing into the native path.

### 9.4 Tier-0 interpreter

Implement a deterministic interpreter in `scir/interp.rs`.

Requirements:

- single-threaded,
- explicit loop order,
- no backend-specific fused kernels,
- no unsafe,
- no nondeterministic parallel reductions,
- same input and same snapshot must produce the same feature bytes and scores.

The interpreter may use `f32` internally for MVP, but all execution must happen in explicit Rust loops with fixed operation ordering. Record `backend_fingerprint` in receipts.

---

## 10. Emission and byte scoring

### 10.1 Emission law

Use the four-term mass law from the Phase 1 design.

```text
m_native = softplus(native_head(features))
         + softplus(nuisance_head(features))
         + softplus(residual_head(features))
         + epsilon

freq[256] = normalize_to_u16_mass_65536(m_native)
```

Rules:

- `epsilon` is a tiny positive floor, e.g. `1e-4`.
- `native_head` may become sharply peaked.
- `nuisance_head` is allowed but not required to carry mass.
- `residual_head` is the only transfer-flexible fast channel in MVP.
- no global certainty cap is allowed.

### 10.2 Bytecoder

The scorer computes next-byte negative log-likelihood in bits:

```text
bits_t = -log2(freq[target_byte] / 65536.0)
```

Total score for a window is the sum of per-step bits. Total score for a panel is the sum over windows.

Implement `bytecoder.rs` and `mdl.rs` as pure deterministic utilities.

### 10.3 Score comparison law

For MVP judge decisions, compare:

1. public delta bits,
2. holdout delta bits,
3. anchor regress bits,
4. resource violations,
5. canary result.

Do not compare by hardware oracle. Hardware oracle is ranking only.

---

## 11. Learning law for MVP

Do not add a large training framework. The MVP learning law is deliberately narrow.

### 11.1 Supported learning law

Implement one deterministic trainer:

`HeadOnlyAdaGradLaw`

It updates only:

- `native_head`,
- `nuisance_head`,
- `residual_head`,
- optional per-channel scales in `StatePack.resid_weights`.

It does not update SCIR structural weights in `core_weights` except for zero-initialized sidecar gates explicitly marked mutable.

### 11.2 Why this is enough for MVP

This keeps Phase 1 end-to-end feasible while still allowing:

- structural innovation via new feature modules,
- incubator maturation through shadow heads,
- splice-based promotion where new features prove value before activation.

### 11.3 Training contract

Implement deterministic single-threaded AdaGrad over train windows.

Hyperparameters in config:

```toml
[train]
steps = 200
lr = 0.05
eps = 1e-8
l2 = 1e-5
clip_grad = 1.0
batch_windows = 8
shuffle = false
```

Training order must be deterministic. Use manifest order, not random shuffling.

---

## 12. PriorPack MVP contents

The seed prior pack must be explicit and versioned.

### 12.1 Seed ops

Ship the following prior modules in `prior_seed/ops.json`:

- `lag_1`, `lag_2`, `lag_4`, `lag_8`, `lag_16`
- `rolling_hash_2`, `rolling_hash_3`
- `run_length_bucket`
- `mod_counter_2`, `mod_counter_4`, `mod_counter_8`
- `delimiter_reset_newline`
- `simple_scan_small`
- `simple_scan_medium`

### 12.2 Seed macros

Ship these macros in `prior_seed/macros.json`:

- `copy_detector_macro`
- `periodicity_macro`
- `delimiter_segment_macro`
- `text_local_context_macro`
- `sidecar_memory_macro`

Each macro expands into a legal SCIR-Lite subgraph.

### 12.3 Prior proof-of-use rule

A prior pack is admitted only if at least one op or macro is legal under SCIR-Lite and is capable of being instantiated in a candidate. For MVP, do not require a full benchmark proof-of-use battery. Log that requirement as TODO for Phase 2.

---

## 13. Seed candidate

Ship a deterministic seed incumbent created by `apfsc_seed_init`.

### 13.1 Seed architecture

The baseline incumbent is intentionally simple.

```text
input bytes
-> byte embedding
-> lag features [1,2,4,8]
-> small simple_scan
-> concat
-> native/nuisance/residual heads
-> next-byte freq[256]
```

### 13.2 Seed promotion class

The seed incumbent is written as an already active `S` candidate.

### 13.3 Seed quality target

The seed candidate only needs to be stable and beat a trivial uniform baseline on F0 and F1 public panels.

---

## 14. Discovery lanes

Phase 1 MVP has four lanes. Three are active. One is a stub.

### 14.1 Truth lane

Purpose:

- generate directly judged candidates close to the incumbent.

Allowed mutations:

- add or remove one macro,
- widen scan hidden dim by a fixed safe increment,
- add one lag feature,
- swap one macro from the prior pack,
- tune head regularization,
- adjust schedule tile bytes within bounds.

Generation algorithm:

- enumerate a bounded deterministic list of mutations,
- materialize candidates,
- verify bounds,
- keep at most `MAX_PUBLIC_CANDIDATES / 2`.

### 14.2 Equivalence lane

Purpose:

- explore semantics-preserving neighborhoods without destroying the incumbent’s function.

Implement these rewrites only:

1. insert/remove identity linear layer,
2. widen hidden state with zeroed channels,
3. split one linear into two composed linears initialized to identity composition,
4. fuse or unfuse concat plus linear when shapes match,
5. refactor single feature macro into equivalent explicit ops,
6. split native readout into native+nuisance+residual with nuisance/residual zero-init.

Contract:

- the rewritten candidate must initially score identically to the parent up to a small tolerance on a witness battery,
- if it does not, it is rejected before public eval.

### 14.3 Incubator lane

Purpose:

- let novelty train behind shadow heads before touching the native scored path.

Mechanism:

1. attach one sidecar feature module from the prior pack,
2. keep cross-talk into the native path zeroed,
3. expose sidecar features only to one or more shadow heads,
4. train shadow heads on train/public windows,
5. compute incubator utility,
6. if utility exceeds threshold, generate a splice candidate.

Incubator utility:

```text
utility = witness_gain_bits
        + public_gain_bits
        - lambda_code * added_code_bits
        - lambda_risk * predicted_risk
```

Use deterministic config thresholds.

### 14.4 Cold-frontier stub lane

Implement a stub that records attempted cold-frontier ideas but does not emit judged candidates. This is a placeholder for later phases and should not influence activation.

---

## 15. Witness battery and error atlas

These two objects are new MVP requirements. They keep compute low and route novelty toward real errors.

### 15.1 Error atlas

After every public eval of the active candidate, bin public failures into a small deterministic atlas.

Initial bins:

- `periodicity_miss`
- `copy_span_miss`
- `delimiter_reset_miss`
- `entropy_overspread`
- `long_memory_miss`
- `other`

### 15.2 Witness battery

Select a small rotating set of public windows from the atlas, e.g. 32 windows total.

Use the witness battery to prefilter candidates before full public scoring.

Rule:

- any candidate that fails to match or exceed incumbent performance on at least one witness bin is dropped before full public eval unless it is an equivalence candidate proving exact preservation.

---

## 16. Bank and split implementation

### 16.1 Reality ingestion flow

`apfsc_ingest_reality` must:

1. read a manifest and raw payload,
2. compute payload and pack digests,
3. write pack artifacts under `packs/reality/<hash>/`,
4. build deterministic windows,
5. split windows into all panels,
6. write `BankManifest` and panel files.

### 16.2 Holdout sealing rule

Holdout window metadata may be visible. Holdout raw contents must not be surfaced through the public candidate generation path. The judge may read holdout payload only when evaluating admitted candidates.

### 16.3 Transfer slices

For Phase 1 MVP, transfer panels are tiny and used only for Class A checks.

Rule:

- adaptation must be limited to `residual_head` and `StatePack.resid_weights`,
- all adaptation steps and resulting delta bits must be counted and logged,
- no structural edits in transfer.

---

## 17. Ingress plane

Phase 1 MVP ingress supports three pack kinds.

### 17.1 RealityPack

Admit local raw byte sequences.

Validation:

- payload exists,
- payload hash matches manifest,
- family id is present,
- split policy is legal,
- window length and stride are within config bounds.

### 17.2 PriorPack

Admit op and macro registries.

Validation:

- all ops map to supported SCIR-Lite ops,
- all macros expand into legal SCIR-Lite graphs,
- parameter sizes are within bounds,
- macro expansion is deterministic.

### 17.3 SubstratePack

Admit measured runtime traces.

Validation:

- trace schema is valid,
- each trace includes candidate or program fingerprint,
- peak RSS and wall time fields are present,
- trace values are nonnegative.

### 17.4 Ingress receipts

Every admitted pack produces an immutable ingress receipt.

Fields:

- pack hash,
- validation checks passed,
- ingest time,
- protocol version,
- resulting snapshot inclusion yes/no.

---

## 18. Epoch snapshot rules

Every epoch must run against one explicit snapshot.

A snapshot includes:

- admitted reality roots,
- admitted prior roots,
- admitted substrate roots,
- protocol version.

Judged candidates must include the exact `snapshot_hash` they were built against.

If a candidate references a missing or different snapshot, reject immediately.

---

## 19. Hardware oracle and resource safety

Split hardware logic into two parts.

### 19.1 SafetyBudget

Hard protocol rejects based on:

- predicted or measured state bytes too large,
- RSS above limit,
- mapped bytes above limit,
- unsupported backend,
- too many steps.

### 19.2 HardwareOracle

A non-authoritative empirical ranker fit from substrate traces.

MVP implementation:

- simple linear or piecewise-linear predictor over features such as op counts, feature dim, scan hidden dim, window len,
- trained from `SubstratePack` traces,
- used only to rank candidate evaluation order and incubator utility penalties.

Promotion must never depend directly on oracle output.

---

## 20. Judge rules

The judge is the only component allowed to activate a candidate.

### 20.1 Admission order

A candidate reaches judge only if:

1. it passes SCIR verification,
2. it passes witness prefilter,
3. it clears public margin,
4. it is within top-N holdout admissions.

### 20.2 Judge checks

The judge must execute checks in this order.

1. artifact completeness and digest validity,
2. snapshot validity,
3. replay capsule validity,
4. resource envelope validity,
5. holdout score improvement over incumbent,
6. anchor family non-regression,
7. warm bridge checks for Class A,
8. mini-transfer check for Class A,
9. stability check,
10. canary requirement decision.

### 20.3 MVP thresholds

Put these in config and use them by default.

```toml
[judge]
public_min_delta_bits = 32.0
holdout_min_delta_bits = 16.0
anchor_max_regress_bits = 0.0
mini_transfer_min_delta_bits = 0.0
require_canary_for_a = true
```

### 20.4 Stability check

For MVP, stability means:

- exact deterministic replay on two consecutive executions,
- no NaN or inf in features or heads,
- no RSS violation,
- no pageouts if OS counters are available,
- no malformed frequency tables.

### 20.5 Judge outcomes

Possible outcomes:

- `Reject(NoPublicMargin)`
- `Reject(HoldoutNoGain)`
- `Reject(AnchorRegress)`
- `Reject(WarmBridgeFail)`
- `Reject(MiniTransferFail)`
- `Reject(StabilityFail)`
- `Reject(CanaryFail)`
- `Promote`

---

## 21. Warm bridge contract for Class A

Phase 1 only supports `S` and `A` class promotions.

### 21.1 What Class A means in Phase 1

Class A is a structural change that preserves enough continuity to compare against the incumbent without requiring a paradigm break.

Examples:

- widened feature state,
- additional sidecar macro spliced into the native path,
- expanded readout decomposition,
- equivalent schedule rewrite.

### 21.2 Warm bridge validation

A `WarmRefinementPack` passes if:

- protected families are listed,
- anchor regress stays within threshold,
- migration policy is recognized,
- splice changes are local and declarative.

Do not implement deep state-map alignment for MVP. Use boundary continuity and protected-family non-regression as the operational bridge.

---

## 22. Canary and activation

### 22.1 Canary requirement

All Class A promotions require canary in Phase 1.

### 22.2 Canary behavior

`apfsc_shadow_canary` runs the promoted candidate on canary windows or streams and compares against the incumbent.

Pass conditions:

- no runtime failures,
- canary total bits not worse than incumbent by more than `0.0`,
- no resource envelope violations.

### 22.3 Activation

If canary passes:

1. write activation receipt,
2. atomically update `rollback_candidate` to previous active,
3. atomically update `active_candidate` to promoted hash,
4. atomically update `active_snapshot`.

If canary fails:

- keep the incumbent active,
- write reject receipt.

---

## 23. Archive outputs

Phase 1 MVP must maintain four archives.

### 23.1 Genealogy

Append one JSON line per candidate with:

- candidate hash,
- parent hashes,
- lane,
- mutation type,
- decision,
- snapshot hash.

### 23.2 Error atlas

Append one JSON line per epoch with failure-bin counts and witness selection.

### 23.3 Failure morphology archive

Append one JSON line per reject with:

- candidate hash,
- morphology descriptor,
- failure class,
- snapshot hash,
- taboo expiration epoch.

Use this to avoid resubmitting near-identical failed candidates for a fixed number of epochs.

### 23.4 Hardware trace archive

Append measured runtime traces from public/holdout/canary and substrate calibration.

---

## 24. End-to-end binary behavior

### 24.1 `apfsc_seed_init`

Responsibilities:

- initialize `.apfsc/` root,
- write protocol version,
- write default judge policy,
- install fixtures if requested,
- create the seed incumbent candidate,
- set `active_candidate` and `rollback_candidate` to the seed candidate,
- create initial empty archives.

CLI example:

```bash
cargo run --bin apfsc_seed_init -- --root .apfsc --fixtures fixtures/apfsc --force
```

### 24.2 `apfsc_ingest_reality`

Responsibilities:

- validate and store the pack,
- build a bank,
- emit ingress receipt.

### 24.3 `apfsc_ingest_prior`

Responsibilities:

- validate and store prior pack,
- register ops and macros,
- emit ingress receipt.

### 24.4 `apfsc_ingest_substrate`

Responsibilities:

- validate and store traces,
- update the hardware oracle training cache,
- emit ingress receipt.

### 24.5 `apfsc_public_eval`

Responsibilities:

- score one candidate on witness or full public panels,
- emit `ByteScoreReceipt`.

### 24.6 `apfsc_judge_daemon`

Responsibilities:

- read active candidate and pending admissions,
- run holdout, anchor, transfer, and canary decision logic,
- emit `PromotionReceipt`,
- if passed and canary not required, activate directly,
- otherwise enqueue canary.

### 24.7 `apfsc_shadow_canary`

Responsibilities:

- drain canary queue,
- run canary evaluations,
- activate on success,
- emit canary and activation receipts.

### 24.8 `apfsc_epoch_run`

This is the convenience binary that makes the MVP fully end to end.

Responsibilities:

1. load config and active snapshot,
2. update witness battery from current error atlas,
3. generate truth/equivalence/incubator candidates,
4. verify and rank them,
5. run public eval,
6. write public receipts,
7. admit top holdout candidates,
8. invoke judge,
9. invoke canary if needed,
10. update archives.

CLI example:

```bash
cargo run --bin apfsc_epoch_run -- --root .apfsc --config fixtures/apfsc/config/phase1.toml --epochs 1
```

---

## 25. Orchestrator algorithm

Implement this in `orchestrator.rs` and call it from `apfsc_epoch_run`.

```rust
pub fn run_epoch(root: &Path, cfg: &Phase1Config) -> Result<EpochReport> {
    let active = load_active_candidate(root)?;
    let snapshot = load_active_snapshot(root)?;
    let bank = load_window_banks(root, &snapshot)?;

    let atlas = update_error_atlas(root, &active, &bank.public)?;
    let witnesses = select_witnesses(&atlas, cfg)?;

    let truth = lanes::truth::generate(&active, &snapshot, &bank, cfg)?;
    let equiv = lanes::equivalence::generate(&active, &snapshot, &bank, cfg)?;
    let incubated = lanes::incubator::generate(&active, &snapshot, &bank, cfg)?;
    let splice = lanes::incubator::materialize_splice_candidates(incubated, cfg)?;
    let cold = lanes::cold_frontier_stub::record_only(&active, &snapshot, cfg)?;

    let mut pool = merge_and_dedup(truth, equiv, splice, cold)?;
    pool = verify_and_bound(pool, cfg)?;
    pool = apply_failure_morph_taboo(root, pool)?;
    pool = witness_prefilter(pool, &witnesses, &active, &bank, cfg)?;
    pool = rank_by_public_gain_then_oracle(pool, cfg)?;

    let public_receipts = evaluate_public(root, &pool, &bank, cfg)?;
    let admissions = admit_holdout_candidates(&public_receipts, cfg)?;

    let judge_report = judge::run_batch(root, &active, admissions, &bank, cfg)?;
    let canary_report = canary::drain_queue(root, &bank, cfg)?;

    archive::genealogy::append_epoch(root, &judge_report, &canary_report)?;
    archive::hardware_trace::append_epoch(root, &public_receipts, &judge_report, &canary_report)?;

    Ok(EpochReport { public_receipts, judge_report, canary_report })
}
```

---

## 26. Exact lane generation rules

### 26.1 Truth lane generation

Generate at most 12 candidates by deterministic mutation templates:

1. add one lag feature,
2. swap `simple_scan_small` to `simple_scan_medium`,
3. add `run_length_bucket`,
4. add `mod_counter_4`,
5. add `delimiter_reset_newline`,
6. add `rolling_hash_2`,
7. add `rolling_hash_3`,
8. swap one macro with another seed macro,
9. increase readout regularization,
10. decrease readout regularization,
11. widen feature concat by one safe block,
12. adjust `tile_bytes` within bounds.

### 26.2 Equivalence lane generation

Generate at most 8 candidates by applying one rewrite each:

1. insert identity linear,
2. remove identity linear,
3. widen by zero channels,
4. split linear into two equivalent linears,
5. split readout into native+nuisance+residual zero-init,
6. macro expansion/refolding.

Require witness equality within tolerance:

```text
total witness delta bits <= 1e-6 per byte
```

### 26.3 Incubator generation

Generate at most 8 sidecars from:

- `sidecar_memory_macro`,
- `periodicity_macro`,
- `copy_detector_macro`,
- `delimiter_segment_macro`.

For each sidecar:

1. attach sidecar features with zero native coupling,
2. train shadow heads only,
3. compute witness and public utility,
4. if utility > `incubator_min_utility_bits`, materialize a splice candidate.

Default config:

```toml
[incubator]
incubator_min_utility_bits = 8.0
lambda_code = 0.1
lambda_risk = 0.1
shadow_steps = 100
```

---

## 27. Splice candidate contract

A splice candidate is the only way incubator novelty enters the native scored path in MVP.

Rules:

- start from the active incumbent,
- copy in the matured sidecar feature subgraph,
- keep all existing incumbent outputs intact,
- initialize new native coupling weights to the learned shadow-head-derived values scaled by a conservative factor, e.g. `0.25`,
- mark promotion class as `A`,
- attach a `WarmRefinementPack` listing protected families.

This yields a conservative path from incubated novelty to judged structural change.

---

## 28. Config file schema

Create `Phase1Config` and load it from TOML.

Example `fixtures/apfsc/config/phase1.toml`:

```toml
[root]
artifact_root = ".apfsc"

[protocol]
version = "apfsc-phase1-mvp-v1"

[bank]
window_len = 256
stride = 64

[limits]
rss_hard_limit_bytes = 12884901888
rss_abort_limit_bytes = 15032385536
max_concurrent_mapped_bytes = 2147483648
segment_bytes = 268435456
state_tile_bytes_max = 2097152
max_public_workers = 2
max_incubator_workers = 1
max_canary_workers = 1

[train]
steps = 200
lr = 0.05
eps = 1e-8
l2 = 1e-5
clip_grad = 1.0
batch_windows = 8
shuffle = false

[judge]
public_min_delta_bits = 32.0
holdout_min_delta_bits = 16.0
anchor_max_regress_bits = 0.0
mini_transfer_min_delta_bits = 0.0
require_canary_for_a = true
max_holdout_admissions = 8

[lanes]
max_truth_candidates = 12
max_equivalence_candidates = 8
max_incubator_candidates = 8
max_public_candidates = 32

[incubator]
incubator_min_utility_bits = 8.0
lambda_code = 0.1
lambda_risk = 0.1
shadow_steps = 100

[witness]
count = 32
rotation = 8
```

---

## 29. Acceptance tests

Codex must implement these tests.

### 29.1 Ingress tests

- `reality_pack_hash_is_stable`
- `reality_ingest_builds_deterministic_bank`
- `prior_pack_rejects_illegal_macro`
- `substrate_pack_updates_oracle_cache`

### 29.2 Bank tests

- `window_split_counts_are_stable`
- `holdout_windows_not_listed_in_public_panel`
- `same_payload_same_bank_manifest`

### 29.3 SCIR tests

- `scir_verify_rejects_dynamic_allocation`
- `scir_verify_rejects_noncausal_edges`
- `equivalence_widen_zero_channels_preserves_output`
- `split_readout_zero_init_preserves_output`

### 29.4 Lane tests

- `truth_lane_emits_bounded_candidates`
- `equivalence_lane_candidates_pass_witness_equality`
- `incubator_sidecar_zero_native_coupling_preserves_parent_score`
- `incubator_materializes_splice_candidate`

### 29.5 Judge tests

- `judge_rejects_missing_snapshot`
- `judge_rejects_anchor_regression`
- `judge_requires_canary_for_a_class`
- `judge_promotes_valid_candidate`

### 29.6 End-to-end tests

- `phase1_seed_init_creates_active_candidate`
- `phase1_epoch_run_emits_receipts`
- `phase1_replay_is_deterministic`
- `phase1_canary_activation_updates_pointers_atomically`

The main e2e test must run in CI on the fixture packs and finish in a reasonable time, target under 60 seconds.

---

## 30. Coding rules for codex

Codex should follow these implementation rules.

1. Prefer small pure functions.
2. Keep all serialization schemas explicit and versioned.
3. No hidden global state.
4. All file writes must be atomic.
5. Every public function returning an artifact must include digests in its output.
6. Any failed verification must return a structured error and write a reject receipt where appropriate.
7. Keep judge logic side-effect-free until the final activation step.
8. Use deterministic iteration order everywhere; prefer `BTreeMap` over `HashMap` in serialized or replay-critical paths.
9. Do not add unsafe code in APF-SC MVP.
10. Do not bypass the `active_candidate` pointer discipline.

---

## 31. Suggested implementation order

Codex should implement in this exact order to reduce integration risk.

### Step 1
Create module skeletons, constants, config, common types, and artifact helpers.

### Step 2
Implement ingest manifests, pack storage, and deterministic bank building.

### Step 3
Implement bytecoder, MDL scorer, and seed fixtures.

### Step 4
Implement SCIR-Lite AST, verifier, interpreter, and seed incumbent generation.

### Step 5
Implement candidate serialization and receipts.

### Step 6
Implement truth lane and equivalence lane.

### Step 7
Implement `HeadOnlyAdaGradLaw` and incubator lane with shadow heads.

### Step 8
Implement judge daemon and canary worker.

### Step 9
Implement archives and hardware oracle.

### Step 10
Implement `apfsc_epoch_run` and end-to-end tests.

Do not start with incubator or judge before steps 1-5 are stable.

---

## 32. Minimum viable demo sequence

After implementation, this command sequence must work on a clean checkout.

```bash
cargo run --bin apfsc_seed_init -- --root .apfsc --fixtures fixtures/apfsc --force
cargo run --bin apfsc_ingest_reality -- --root .apfsc --manifest fixtures/apfsc/reality_f0_det/manifest.json
cargo run --bin apfsc_ingest_reality -- --root .apfsc --manifest fixtures/apfsc/reality_f1_text/manifest.json
cargo run --bin apfsc_ingest_prior -- --root .apfsc --manifest fixtures/apfsc/prior_seed/manifest.json
cargo run --bin apfsc_ingest_substrate -- --root .apfsc --manifest fixtures/apfsc/substrate_seed/manifest.json
cargo run --bin apfsc_epoch_run -- --root .apfsc --config fixtures/apfsc/config/phase1.toml --epochs 1
```

Expected artifacts after the run:

- pack receipts,
- bank manifests,
- at least one candidate receipt in `receipts/public/`,
- at least one `receipts/judge/` receipt,
- if promoted, one canary and activation receipt,
- updated archives.

---

## 33. Definition of done

The codex agent is done only when all of the following are true.

1. The module tree exists and builds.
2. The seed incumbent can be created and activated.
3. Reality, prior, and substrate packs can be ingested.
4. `WindowBank` splits are deterministic and replayable.
5. SCIR-Lite candidates compile, verify, and execute under the Tier-0 interpreter.
6. Truth, equivalence, and incubator lanes all produce candidates.
7. Witness prefilter, public eval, holdout judge, canary, and activation all work.
8. Archives are updated after every epoch.
9. An end-to-end fixture run succeeds from seed init through judge.
10. Re-running the same fixture epoch yields byte-identical receipts except for wall-clock timestamps.

---

## 34. What to defer explicitly

Leave TODO markers, but do not implement these in Phase 1 MVP.

- full e-graph saturation engine,
- APF-v3 GraphBackend bridge for SCIR execution,
- MLX or MPS discovery backend,
- richer search-law recursion,
- QD archive frontier,
- tool shadow lane,
- formal packs,
- cold boundary packs,
- multi-family normalization beyond the two seed families,
- distributed execution.

---

## 35. Final implementation intent

This MVP is deliberately narrow but complete.

It is not trying to solve recursive self-improvement in one jump. It is building the smallest correct lab that already has:

- fixed measurement,
- structural mutation,
- novelty maturation,
- sealed world contact,
- judged promotion,
- rollback-safe activation,
- deterministic archives.

That is the full Phase 1 foundation. Once this exists in the repo and passes deterministic end-to-end tests, later phases can expand search breadth, family diversity, backend sophistication, and paradigm-shift machinery without rewriting the core scientific boundary.
