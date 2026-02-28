# APF-SC Phase 3 MVP - Full End-to-End Implementation Specification

This document is the implementation contract for a codex agent. It extends the Phase 2 MVP from a family-aware architecture laboratory into a controlled paradigm-transition layer. Phase 3 is the first phase where APF-SC may promote candidates that do not merely improve within one fixed architectural regime, but instead change memory law, scheduler semantics, primitive inventory, or learning-law class while still remaining pinned to byte-MDL truth, deterministic replay, family-normalized judgment, and atomic activation.

End to end in this phase means:

1. reuse the Phase 2 constellation and scoring substrate,
2. add SCIR-v2 with bounded macro expansion and deterministic lowering,
3. add a backend abstraction with a GraphBackend bridge into existing APF-v3 graph execution where eligible,
4. classify candidates into S, A, PWarm, and PCold using explicit paradigm signatures,
5. evaluate paradigm candidates on public static, transfer, robustness, and recent-family panels,
6. judge them with class-specific bridge gates,
7. require mandatory shadow canary for paradigm promotions,
8. preserve rollback targets and atomic activation semantics,
9. emit durable archives for paradigm signatures, macro receipts, backend equivalence, bridge traces, and canary outcomes.

The Phase 3 objective is not open-ended self-modification yet. The objective is narrower and more important:

**make genuine paradigm change mechanically possible without weakening the trusted plane.**

---

## 1. Hard constraints

Codex must follow these constraints exactly.

### 1.1 Phase 2 is a prerequisite

Assume the Phase 1 and Phase 2 MVP contracts exist or are being implemented exactly as specified in:

- `apfsc_phase1_mvp_spec.md`
- `apfsc_phase2_mvp_spec.md`

Phase 3 is an extension layer. Do not redesign the trusted APF-SC Phase 1/2 kernel unless Phase 3 requires a mechanical schema extension. Preserve Phase 1 and Phase 2 semantics where possible.

### 1.2 Trusted substrate boundary

Treat the existing APF-v3 substrate in `baremetal_lgp` / `apf3` as immutable. Reuse existing facilities for:

- deterministic replay capsules and digests,
- content-addressed artifacts,
- atomic pointer writes,
- judge-only activation,
- fail-closed execution,
- rollback primitives,
- graph-path execution adapters where already present.

If actual names differ in the repo, adapt at the APF-SC boundary. Do not refactor APF-v3 core code.

### 1.3 Implement in Phase 3 now

Implement now:

- `SCIR-v2` as an extension of the Phase 1/2 `SCIR-Lite` path,
- deterministic macro definitions, macro lowering, and macro registry,
- one bounded macro-induction path from archive fragments,
- backend abstraction with:
  - `InterpTier0` semantic source of truth,
  - `GraphBackend` adapter for eligible lowered programs,
- backend equivalence receipts,
- `ParadigmSignature` and automatic class classification,
- active `PWarm` and active `PCold`,
- stronger `WarmRefinementPack` for `A` and `PWarm`,
- `ColdBoundaryPack` for `PCold`,
- recent-family freshness accounting,
- active cold-frontier lane,
- mandatory paradigm canary,
- explicit rollback target preservation,
- archive extensions for paradigm, macro, bridge, backend, and canary evidence,
- one Phase 3 end-to-end epoch path.

### 1.4 Explicitly do not implement now

Do not implement now:

- search-law promotion as a judged class,
- protocol self-modification,
- distributed execution,
- NativeBlock in judged execution,
- hidden challenge families as a promotion gate,
- multi-parent recombination,
- law-archive-driven budget learning,
- unrestricted macro recursion,
- dynamic tool execution in judged path,
- autonomous admissibility relaxation.

### 1.5 Promotion classes in Phase 3

Phase 3 keeps the Phase 1/2 class family, but these are now active:

- `S`: allowed
- `A`: allowed
- `PWarm`: allowed
- `PCold`: allowed
- `GDisabled`: schema-present, not admitted

Interpretation:

- `S`: same paradigm signature, same warm bridge regime, small structural or residual improvements
- `A`: same paradigm signature, structural change within the same architectural regime, warm bridge required
- `PWarm`: paradigm signature changed, but continuity is still checkable through a valid warm bridge
- `PCold`: paradigm signature changed and no valid warm bridge exists or is intentionally disallowed; candidate is judged on truth plus boundary safety, not incumbent mimicry

### 1.6 Runtime envelope

Still target a single Apple-silicon machine with an effective 16 GiB protocol envelope.

Use these Phase 3 limits unless the Phase 1/2 repo already exposes stricter constants:

```text
RSS_HARD_LIMIT_BYTES                 = 12 GiB
RSS_ABORT_LIMIT_BYTES                = 14 GiB
MAX_CONCURRENT_MAPPED_BYTES          = 2 GiB
SEGMENT_BYTES                        = 256 MiB
STATE_TILE_BYTES_MAX                 = 2 MiB

MAX_SCIR_CORE_OPS                    = 4096
MAX_MACRO_CALLS_PER_PROGRAM          = 16
MAX_MACRO_EXPANSION_OPS              = 256
MAX_MACRO_DEPTH                      = 1
MAX_EGRAPH_NODES                     = 50000
MAX_EGRAPH_EXTRACTIONS               = 32

MAX_STATIC_PUBLIC_CANDIDATES         = 32
MAX_PARADIGM_PUBLIC_CANDIDATES       = 12
MAX_PWARM_HOLDOUT_ADMISSIONS         = 2
MAX_PCOLD_HOLDOUT_ADMISSIONS         = 1

MAX_PUBLIC_WORKERS                   = 2
MAX_INCUBATOR_WORKERS                = 1
MAX_CANARY_WORKERS                   = 1

MAX_PARADIGM_CANARY_WINDOWS_WARM     = 128
MAX_PARADIGM_CANARY_WINDOWS_COLD     = 256

MAX_TRANSFER_FAST_WEIGHT_BYTES       = 256 KiB
MAX_TRANSFER_DELTA_BITS              = 524288
MAX_COMPAT_HEAD_BYTES                = 4 MiB
```

The judged path must remain deterministic and pageout-free.

---

## 2. What success means

Phase 3 MVP is done when all of the following are true:

1. `cargo test` passes for all Phase 1, Phase 2, and Phase 3 tests.
2. At least one SCIR-v2 candidate with macro calls can be canonicalized, lowered, verified, and run deterministically through the interpreter.
3. At least one lowered candidate can produce a valid GraphBackend plan and a backend equivalence receipt against the interpreter on the equivalence corpus.
4. Candidate classification produces correct `S`, `A`, `PWarm`, and `PCold` labels on deterministic fixtures.
5. A valid `PWarm` fixture candidate can change scheduler, memory law, or learning-law class and pass public, holdout, warm bridge, and mandatory canary.
6. A valid `PCold` fixture candidate can change paradigm signature without a valid warm bridge and still pass truth, recent-family gain, cold-boundary gate, and mandatory canary.
7. A deliberately unsafe or continuity-breaking candidate with insufficient truth margin is rejected with a typed `JudgeDecisionReason`.
8. `apfsc_epoch_run --profile phase3 --epochs 1` produces end-to-end receipts and either a rejection or successful activation.
9. Replay of the same epoch with the same snapshot and constellation reproduces the same receipts exactly.

A successful demo trace should look like:

```text
seed init
-> ingest phase2 constellation and fresh phase3 families
-> build phase3 snapshot
-> macro registry load + optional macro induction
-> generate truth/equivalence/incubator/cold-frontier candidates
-> canonicalize + lower + verify
-> backend equivalence where eligible
-> witness prefilter
-> public static eval
-> public transfer + robustness + recent-family eval
-> holdout static/transfer/robust/fresh eval
-> warm bridge or cold boundary evaluation
-> mandatory shadow canary for paradigm classes
-> atomic activate or reject
-> archive update
```

---

## 3. Repo delta to add or modify

Keep APF-v3 untouched. Extend the APF-SC tree from Phase 2.

### 3.1 New and modified modules

```text
src/apfsc/
  mod.rs                         (update exports)
  types.rs                       (extend promotion kinds and receipt enums)
  config.rs                      (phase3 profile and paradigm thresholds)
  candidate.rs                   (phase3 candidate metadata)
  headpack.rs                    (compat head and shadow head extensions)
  bridge.rs                      (strengthened warm bridge + cold boundary)
  schedule_pack.rs               (scheduler classes and backend plans)
  bank.rs                        (extend for fresh-family metadata)
  constellation.rs               (extend for freshness manifests)
  judge.rs                       (phase3 judge gates)
  canary.rs                      (mandatory paradigm canary)
  rollback.rs                    (new)
  orchestrator.rs                (phase3 epoch flow)
  paradigm.rs                    (new)
  macro_lib.rs                   (new)
  macro_mine.rs                  (new)
  fresh_contact.rs               (new)

  scir/
    mod.rs
    ast.rs                       (upgrade to SCIR-v2)
    canonical.rs                 (new)
    lower.rs                     (new)
    verify.rs                    (extend)
    interp.rs                    (extend)
    egraph.rs                    (new bounded workspace)
    graph_backend.rs             (new)
    backend_equiv.rs             (new)

  lanes/
    truth.rs                     (extend for paradigm proposals)
    equivalence.rs               (upgrade to e-graph extraction)
    incubator.rs                 (macro-aware incubation)
    cold_frontier.rs             (new active lane; replaces stub)

  archive/
    mod.rs                       (update exports)
    genealogy.rs                 (extend for paradigm edges)
    error_atlas.rs               (extend bins with paradigm tags)
    family_scores.rs             (reuse and extend)
    transfer_trace.rs            (reuse)
    robustness_trace.rs          (reuse)
    paradigm_receipts.rs         (new)
    bridge_trace.rs              (new)
    backend_equiv.rs             (new)
    macro_registry.rs            (new)
    canary_trace.rs              (new)
```

### 3.2 New and modified binaries

```text
src/bin/
  apfsc_build_lowered_candidate.rs   (new)
  apfsc_backend_equiv.rs             (new)
  apfsc_bridge_eval.rs               (new)
  apfsc_macro_mine.rs                (new)

  apfsc_public_eval.rs               (extend)
  apfsc_judge_daemon.rs              (extend)
  apfsc_shadow_canary.rs             (extend)
  apfsc_epoch_run.rs                 (extend with profile=phase3)
```

### 3.3 Fixtures and tests

Reuse Phase 2 fixtures and add the following.

```text
fixtures/apfsc/phase3/
  priors/
    macro_seed/
      manifest.json
      macros.json
    macro_seed_alt/
      manifest.json
      macros.json

  reality_f4_event_sparse_base/
  reality_f4_event_sparse_transfer/
  reality_f4_event_sparse_robust/

  reality_f5_formal_alg_base/
  reality_f5_formal_alg_transfer/
  reality_f5_formal_alg_robust/

  expected/
    phase3_warm_candidate_manifest.json
    phase3_cold_candidate_manifest.json
    phase3_graph_equiv_receipt.json
    phase3_warm_promotion_receipt.json
    phase3_cold_promotion_receipt.json

  config/
    phase3.toml
```

Add tests:

```text
tests/
  apfsc_phase3_scir_v2.rs
  apfsc_phase3_macro_lowering.rs
  apfsc_phase3_macro_mine.rs
  apfsc_phase3_graph_backend.rs
  apfsc_phase3_classifier.rs
  apfsc_phase3_warm_bridge.rs
  apfsc_phase3_cold_boundary.rs
  apfsc_phase3_recent_family_gate.rs
  apfsc_phase3_canary_rollback.rs
  apfsc_phase3_e2e_pwarm.rs
  apfsc_phase3_e2e_pcold.rs
```

---

## 4. Phase 3 simplifications

These simplifications are intentional. Do not "improve" them away during implementation.

1. The interpreter remains the semantic source of truth.
2. Holdout judgment always recomputes truth on the interpreter, even if a GraphBackend plan exists.
3. GraphBackend is used only for:
   - eligibility checks,
   - public acceleration,
   - canary acceleration,
   - backend research receipts.
4. `NativeBlock` remains out of the judged path.
5. Macro depth is one. Macros may not recursively expand into further macro calls.
6. Macro induction is bounded to frequent fragment mining with deterministic thresholds. No learned miner exists yet.
7. Hidden challenge families remain schema-present only. They do not gate promotion in Phase 3.
8. Search law remains heuristic and fixed. `G` remains disabled.
9. `PCold` is narrow:
   - one candidate at a time in holdout,
   - interpreter-judged only,
   - mandatory canary always,
   - rollback pointer always preserved.
10. Recent-family evidence is required for `PWarm` and `PCold`, but only over explicitly admitted fresh families. No active data acquisition exists yet.

---

## 5. On-disk artifact delta

Extend the Phase 2 artifact tree.

```text
artifacts/apfsc/
  snapshots/
    <snapshot_hash>/
      epoch_snapshot.json
      constellation_manifest.json
      fresh_family_manifest.json

  macro_registry/
    <macro_registry_hash>/
      macro_registry.json
      induced_macros.jsonl
      admission_receipts.jsonl

  candidates/
    <candidate_hash>/
      manifest.json
      build_meta.json
      paradigm_signature.json
      scir_v2.json
      scir_canonical.json
      scir_lowered.json
      schedule_pack.json
      backend_plan.json
      headpack.json
      bridgepack.json
      macro_usage.json
      compile_receipt.json
      backend_equiv_receipt.json    (optional)
      static_public_receipt.json
      transfer_public_receipt.json
      robust_public_receipt.json
      fresh_public_receipt.json
      holdout_receipt.json
      bridge_receipt.json
      canary_receipt.json           (optional)
      promotion_receipt.json

  active/
    active_candidate.json
    rollback_candidate.json
    active_constellation.json
    active_snapshot.json

  archives/
    genealogy.jsonl
    family_scores.jsonl
    transfer_trace.jsonl
    robustness_trace.jsonl
    error_atlas.jsonl
    paradigm_receipts.jsonl
    bridge_trace.jsonl
    backend_equiv.jsonl
    macro_registry.jsonl
    canary_trace.jsonl
```

Rules:

- all artifact directories remain content-addressed,
- every receipt must carry `protocol_version`, `snapshot_hash`, and `constellation_id`,
- `backend_equiv_receipt.json` is optional and exists only when a graph plan is eligible,
- `rollback_candidate.json` must point to the incumbent active candidate before any `PWarm` or `PCold` activation,
- `promotion_receipt.json` is authoritative for the final decision.

---

## 6. Core data contracts

Implement these contracts directly in Rust. Field names may be adapted to repo style, but semantics must remain unchanged.

### 6.1 Promotion and backend enums

```rust
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum PromotionClass {
    S,
    A,
    PWarm,
    PCold,
    GDisabled,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum BackendKind {
    InterpTier0,
    GraphBackend,
    NativeBlockDisabled,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum SchedulerClass {
    SerialScan,
    BlockScan,
    EventSparse,
    TwoPassMemory,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum MemoryLawKind {
    FlatState,
    RingSlots,
    SelectiveState,
    AccumulatorBank,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum LearningLawKind {
    HeadOnlyAdaGrad,
    ResidualAdaGrad,
    FastWeightDelta,
}
```

### 6.2 SCIR-v2 program model

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScirV2Program {
    pub version: String,
    pub state_schema: StateSchema,
    pub channels: Vec<ChannelDef>,
    pub core_blocks: Vec<CoreBlock>,
    pub macro_calls: Vec<MacroCall>,
    pub schedule: ScheduleDef,
    pub readouts: Vec<ReadoutDef>,
    pub adapt_hooks: Vec<AdaptHook>,
    pub bounds: BoundSpec,
}
```

Core intent:

- `core_blocks` contain explicit bounded primitive graphs,
- `macro_calls` are syntactic sugar that must lower deterministically into `core_blocks`,
- `schedule` expresses execution semantics and backend hints,
- `bounds` are protocol-checked and must remain finite.

### 6.3 Macro contracts

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum MacroOriginKind {
    SeedPrior,
    InducedFromArchive,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MacroDef {
    pub macro_id: String,
    pub version: u32,
    pub origin_kind: MacroOriginKind,
    pub origin_hash: String,
    pub input_ports: Vec<PortSpec>,
    pub output_ports: Vec<PortSpec>,
    pub local_state_bytes: u64,
    pub expansion_hash: String,
    pub expansion_core: Vec<CoreOp>,
    pub max_expansion_ops: u32,
    pub canonical_hash: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MacroCall {
    pub call_id: String,
    pub macro_id: String,
    pub arg_bindings: std::collections::BTreeMap<String, String>,
    pub instance_seed: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MacroRegistry {
    pub registry_id: String,
    pub snapshot_hash: String,
    pub macro_defs: Vec<MacroDef>,
    pub protocol_version: String,
    pub manifest_hash: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MacroInductionReceipt {
    pub macro_id: String,
    pub support_count: u32,
    pub source_fragment_hashes: Vec<String>,
    pub mean_public_gain_bpb: f64,
    pub op_count_reduction_ratio: f64,
    pub accepted: bool,
    pub reason: String,
}
```

### 6.4 Backend and lowering contracts

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LoweringReceipt {
    pub candidate_hash: String,
    pub scir_hash: String,
    pub canonical_hash: String,
    pub lowered_hash: String,
    pub macro_registry_hash: String,
    pub core_op_count: u32,
    pub state_bytes_estimate: u64,
    pub graph_backend_eligible: bool,
    pub replay_hash: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BackendPlan {
    pub primary_backend: BackendKind,
    pub public_backend: BackendKind,
    pub canary_backend: BackendKind,
    pub holdout_backend: BackendKind,
    pub graph_eligibility_hash: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BackendEquivReceipt {
    pub candidate_hash: String,
    pub canonical_hash: String,
    pub lowered_hash: String,
    pub backend_kind: BackendKind,
    pub witness_exact_match: bool,
    pub public_exact_match: bool,
    pub max_abs_mass_diff_q16: u32,
    pub eligible: bool,
    pub reason: String,
}
```

Rules:

- `holdout_backend` must remain `InterpTier0` in Phase 3,
- `GraphBackend` can be used only if `eligible == true`,
- if equivalence fails, public and canary must fall back to the interpreter.

### 6.5 Head, bridge, and paradigm contracts

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HeadPack {
    pub native_head_hash: String,
    pub compat_head_hash: Option<String>,
    pub shadow_head_hashes: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WarmRefinementPack {
    pub observable_map_hash: String,
    pub state_map_hash: String,
    pub tolerance_spec_hash: String,
    pub migration_policy: String,
    pub protected_head_ids: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ColdBoundaryPack {
    pub protected_panels: Vec<String>,
    pub max_anchor_regret_bpb: f64,
    pub max_error_streak: u32,
    pub required_transfer_gain_bpb: f64,
    pub required_recent_family_gain_bpb: f64,
    pub mandatory_canary_windows: u32,
    pub rollback_target_hash: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum BridgePack {
    Warm(WarmRefinementPack),
    Cold(ColdBoundaryPack),
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ParadigmSignature {
    pub primitive_family_hash: String,
    pub scheduler_class: SchedulerClass,
    pub memory_law: MemoryLawKind,
    pub learning_law: LearningLawKind,
    pub state_schema_hash: String,
    pub native_head_semantics_hash: String,
    pub canonical_core_hash: String,
}
```

Interpretation:

- backend selection alone does not change paradigm class if semantics remain identical,
- paradigm classification is based on semantic signature fields, not only runtime backend choice,
- `native_head_semantics_hash` lets head changes participate in signature differences,
- `canonical_core_hash` is computed after macro lowering and canonicalization.

### 6.6 Candidate metadata additions

Keep Phase 2 `CandidateManifest` and add these fields:

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Phase3BuildMeta {
    pub target_families: Vec<String>,
    pub source_lane: String,
    pub phase3_profile: String,
    pub macro_registry_hash: String,
    pub paradigm_signature_hash: String,
    pub proposed_class: PromotionClass,
    pub fresh_target_families: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CandidatePhase3Meta {
    pub build: Phase3BuildMeta,
    pub backend_plan: BackendPlan,
    pub bridge_kind: String,
}
```

### 6.7 Recent-family and bridge receipts

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RecentFamilyGainReceipt {
    pub candidate_hash: String,
    pub incumbent_hash: String,
    pub recent_family_ids: Vec<String>,
    pub family_gain_bpb: std::collections::BTreeMap<String, f64>,
    pub max_recent_family_gain_bpb: f64,
    pub pass: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BridgeReceipt {
    pub candidate_hash: String,
    pub incumbent_hash: String,
    pub promotion_class: PromotionClass,
    pub bridge_kind: String,
    pub pass: bool,
    pub reason: String,
    pub anchor_regret_bpb: Option<f64>,
    pub max_error_streak: Option<u32>,
    pub canary_windows_required: u32,
}
```

### 6.8 Promotion receipt extensions

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PromotionReceipt {
    pub candidate_hash: String,
    pub incumbent_hash: String,
    pub decision: String,
    pub reason: String,
    pub promotion_class: PromotionClass,
    pub weighted_static_holdout_delta_bpb: f64,
    pub weighted_transfer_holdout_delta_bpb: Option<f64>,
    pub weighted_robust_holdout_delta_bpb: Option<f64>,
    pub improved_family_ids: Vec<String>,
    pub regressed_family_ids: Vec<String>,
    pub protected_floor_failures: Vec<String>,
    pub recent_family_receipt_hash: Option<String>,
    pub bridge_receipt_hash: Option<String>,
    pub canary_required: bool,
    pub canary_result: Option<String>,
    pub rollback_target_hash: Option<String>,
    pub snapshot_hash: String,
    pub constellation_id: String,
}
```

### 6.9 New reject reasons

Add these reject reasons if the repo uses typed enums:

- `ParadigmClassMismatch`
- `MacroLoweringFail`
- `BackendEquivalenceFail`
- `WarmRefinementFail`
- `ColdBoundaryFail`
- `RecentFamilyGainFail`
- `CanaryFail`
- `RollbackTargetMissing`
- `UnsupportedBackendPlan`
- `PColdMarginInsufficient`

---

## 7. Seed fresh families and fixtures

Reuse the four Phase 2 seed families and add two Phase 3 families with explicit freshness metadata.

### 7.1 Required family inventory

Phase 3 evaluation assumes these six families exist:

1. `det_micro`
2. `text_code`
3. `sensor_temporal`
4. `phys_sim`
5. `event_sparse`
6. `formal_alg`

The last two are new in Phase 3 and must be marked as recently admitted.

### 7.2 Family role requirements

For `event_sparse` and `formal_alg`, provide:

- one `Base` pack,
- at least one `Transfer` pack,
- at least one `Robust` pack.

`ChallengeStub` remains optional.

### 7.3 Freshness metadata

Extend constellation or family manifests with:

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FamilyFreshnessMeta {
    pub family_id: String,
    pub admitted_epoch: u64,
    pub fresh_until_epoch: u64,
}
```

Rules:

- the two new Phase 3 families must satisfy `current_epoch <= fresh_until_epoch`,
- `PWarm` and `PCold` require positive gain on at least one recent family,
- recent-family gain is computed on transfer holdout if available, otherwise on static holdout.

### 7.4 Fixture intent

The fixtures should support these deterministic stories:

- the incumbent Phase 2 candidate is competent but weak on `event_sparse`,
- a `PWarm` candidate improves `event_sparse` using a warm-bridgeable `EventSparseAccumulator` macro and a `RingSlots` memory law,
- a `PCold` candidate improves `formal_alg` using a `SelectiveState` memory law and an incompatible state schema with no valid warm bridge,
- a negative-control `PCold` candidate shows impressive public improvement but fails recent-family or anchor-regret gates.

---

## 8. SCIR-v2 specification

Phase 3 upgrades the judged architecture language without giving up deterministic lowering.

### 8.1 SCIR-v2 capabilities

SCIR-v2 must support:

- fixed-point scalar, vector, and small-matrix state,
- bounded recurrent and scan updates,
- bounded slot-based memory access,
- event-masked state updates,
- deterministic reducer ops,
- macro call sites,
- explicit schedule class tags,
- explicit adaptation hooks,
- backend eligibility hints.

### 8.2 Allowed primitive categories

Implement these primitive categories:

1. `LinearMix`
2. `AffineBias`
3. `ElementwiseGate`
4. `StateUpdate`
5. `ScanReduce`
6. `SlotRead`
7. `SlotWrite`
8. `EventMask`
9. `ResetIf`
10. `HeadReadout`

Every primitive must have:

- a static output shape,
- a static memory bound,
- deterministic fixed-point semantics,
- a canonical serialization form.

### 8.3 Forbidden in Phase 3

Do not allow:

- dynamic allocation,
- unbounded loops,
- data-dependent graph mutation,
- recursive macro expansion,
- external side effects,
- filesystem or tool calls,
- arbitrary pointer arithmetic,
- backend-specific semantics that diverge from interpreter semantics.

### 8.4 Canonicalization rules

Implement canonicalization before hashing:

1. sort state declarations by stable id,
2. normalize commutative input order for supported ops,
3. inline identity edges,
4. strip dead nodes,
5. sort macro-call metadata by call id,
6. hash after macro lowering, not before.

Canonicalization must be deterministic and stable across runs.

### 8.5 Bounds inference

`verify.rs` must reject any program that exceeds:

- `MAX_SCIR_CORE_OPS`,
- `STATE_TILE_BYTES_MAX`,
- `MAX_MACRO_CALLS_PER_PROGRAM`,
- `MAX_MACRO_EXPANSION_OPS`,
- schedule-specific memory bounds,
- transfer adaptation mutable-surface bounds inherited from Phase 2.

---

## 9. Macro library and induction contract

Phase 3 is the first phase where APF-SC may reuse and induce reusable architecture fragments.

### 9.1 Seed macro families

Implement these seed macros first:

1. `EventSparseAccumulator`
2. `RingDelayTap`
3. `SelectiveStateCell`
4. `ResetOnDelimiter`

Each macro must:

- lower deterministically to SCIR core ops,
- declare local state bytes,
- declare allowed scheduler classes,
- declare allowed memory-law kinds,
- pass bounds verification after lowering.

### 9.2 Macro lowering policy

Lowering is strict:

- every macro call must lower to a finite SCIR core expansion,
- macro expansion is charged in code length,
- macro expansion is included in canonical hashing,
- macro expansion must not weaken safety checks.

### 9.3 Macro induction policy

Implement one deterministic induction path:

1. scan accepted and incubator archive candidates from prior epochs,
2. extract repeated canonical fragments with the same port signature,
3. keep only fragments with support count >= `MIN_MACRO_SUPPORT`,
4. require mean public witness gain above `MIN_MACRO_PUBLIC_GAIN_BPB`,
5. require op-count reduction ratio above `MIN_MACRO_REDUCTION_RATIO`,
6. materialize an induced `MacroDef`,
7. write a `MacroInductionReceipt`,
8. add accepted macros to the next epoch's macro registry.

Suggested initial constants:

```text
MIN_MACRO_SUPPORT              = 3
MIN_MACRO_PUBLIC_GAIN_BPB      = 0.001
MIN_MACRO_REDUCTION_RATIO      = 1.20
MAX_INDUCED_MACROS_PER_EPOCH   = 8
```

### 9.4 Macro induction is not promotion truth

Macros do not promote on their own. They are proposal surface only.

Promotion truth remains candidate MDL on sealed panels.

---

## 10. Backend abstraction and GraphBackend bridge

### 10.1 Semantic rule

The interpreter is the source of truth. GraphBackend is an acceleration and execution-plan layer, not an independent semantics source.

### 10.2 GraphBackend eligibility

A lowered program is GraphBackend-eligible only if all lowered ops belong to the graph-safe subset:

- `LinearMix`
- `AffineBias`
- `ElementwiseGate`
- `StateUpdate`
- `ScanReduce`
- `HeadReadout`

Programs containing `SlotRead`, `SlotWrite`, `EventMask`, or `ResetIf` may still run, but they are interpreter-only in Phase 3 unless the existing APF-v3 graph path already exposes exact equivalents.

### 10.3 GraphBackend adapter contract

Implement an adapter rather than modifying APF-v3 internals:

```rust
pub trait GraphBackendAdapter {
    fn lower_program(&self, prog: &ScirV2Program) -> anyhow::Result<GraphExecPlan>;
    fn run_plan(&self, plan: &GraphExecPlan, window: &[u8]) -> anyhow::Result<ByteMassTrace>;
}
```

If the underlying APF-v3 graph path uses different naming, add a local wrapper in `src/apfsc/scir/graph_backend.rs`.

### 10.4 Backend equivalence receipt

For every eligible candidate:

1. run the interpreter on the equivalence corpus,
2. run the graph plan on the same windows,
3. compare emitted byte-mass vectors exactly,
4. emit `BackendEquivReceipt`.

Policy:

- `max_abs_mass_diff_q16` must equal `0`,
- if exact match fails, mark `eligible = false`,
- holdout still runs on the interpreter,
- public and canary may use GraphBackend only if equivalence passes.

---

## 11. Paradigm signature and classification

Phase 3 must stop inferring class names from ad hoc code paths.

### 11.1 Classification rule

Compute a candidate's `ParadigmSignature` after lowering and canonicalization. Then compare against the incumbent.

Classification:

1. same signature, no structural graph change -> `S`
2. same signature, structural graph changed -> `A`
3. different signature, valid warm bridge exists -> `PWarm`
4. different signature, no valid warm bridge but a valid cold boundary pack exists -> `PCold`
5. otherwise reject with `ParadigmClassMismatch`

### 11.2 What counts as a signature change

A signature change occurs if any of these differ from the incumbent:

- `primitive_family_hash`
- `scheduler_class`
- `memory_law`
- `learning_law`
- `state_schema_hash`
- `native_head_semantics_hash`
- `canonical_core_hash`

GraphBackend eligibility or backend choice alone does not force a paradigm-class upgrade if semantics remain identical.

### 11.3 Structural change detection

A structural change occurs if the canonical lowered program hash changes, even when the paradigm signature does not.

---

## 12. Bridge contracts

Phase 3 uses two bridge families.

### 12.1 Warm bridge for `A` and `PWarm`

`WarmRefinementPack` remains continuity-preserving. Extend the Phase 1/2 bridge checker so it verifies:

- state-map type compatibility,
- observable-map compatibility,
- tolerance thresholds on anchor windows,
- migration-policy legality,
- protected-head coverage,
- commutativity between incumbent observables and candidate observables where defined.

Warm bridge policy:

- required for all `A`,
- required for all `PWarm`,
- optional and ignored for `PCold`.

### 12.2 Cold boundary for `PCold`

`PCold` does not require incumbent mimicry. It requires boundary safety.

`ColdBoundaryPack` must enforce:

- protected anchor panels remain within `max_anchor_regret_bpb`,
- no error streak longer than `max_error_streak`,
- transfer holdout gain exceeds `required_transfer_gain_bpb`,
- recent-family gain exceeds `required_recent_family_gain_bpb`,
- mandatory canary runs for `mandatory_canary_windows`,
- rollback target exists and is valid.

### 12.3 Native head truth rule

For `PCold`, the native head is never forced to imitate incumbent predictions.

Truth scoring always uses the candidate's native head against sealed bytes.

A compat head may exist for diagnostics, but it contributes no promotion credit.

### 12.4 Bridge receipt behavior

`apfsc_bridge_eval` must emit one typed receipt per candidate:

- `WarmBridgePass`
- `WarmBridgeFail`
- `ColdBoundaryPass`
- `ColdBoundaryFail`

---

## 13. Cold frontier lane and discovery changes

Phase 2 carried a cold-frontier stub. Phase 3 activates it.

### 13.1 Lane budget split

Initial deterministic budget split:

```text
truth            = 0.35
equivalence      = 0.20
incubator        = 0.25
cold_frontier    = 0.20
```

This split is fixed by config in Phase 3.

### 13.2 Truth lane changes

Truth lane may now propose:

- same-signature structural variants,
- macro-enabled same-signature variants,
- candidate schedules that remain warm-bridgeable.

Truth lane should predominantly emit `S` and `A`, with occasional `PWarm`.

### 13.3 Equivalence lane changes

Upgrade the rewrite workspace into a bounded e-graph-like additive workspace.

Required support:

- semantics-preserving rewrites over lowered SCIR,
- macro decomposition/recomposition,
- schedule-preserving reorderings,
- dead-state elimination,
- strength reduction.

Extraction remains deterministic and bounded.

### 13.4 Incubator lane changes

Incubator sidecars may now test:

- macro-augmented modules,
- new schedule classes,
- new memory-law modules,
- new residual/fast-weight surfaces.

Incubator remains behind shadow heads. It must still materialize splice candidates before judged entry.

### 13.5 Cold-frontier lane rules

Cold-frontier is the only lane allowed to deliberately propose candidates that:

- change paradigm signature without a warm bridge,
- alter state schema incompatibly,
- introduce new memory-law kinds from allowed seed priors,
- route through cold boundary evaluation.

Cold-frontier candidates still must:

- compile,
- verify bounds,
- stay interpreter-legal,
- pass public gates before holdout.

---

## 14. Public and holdout evaluation in Phase 3

Phase 3 keeps Phase 2's family-normalized score law and adds recent-family evidence plus class-specific admission.

### 14.1 Public staging

Staging order:

1. witness battery prefilter
2. static public eval
3. transfer public eval
4. robustness public eval
5. recent-family public eval
6. class classification
7. bridge precheck
8. holdout admission

### 14.2 Holdout staging

For admitted candidates:

1. static holdout eval
2. transfer holdout eval
3. robustness holdout eval
4. recent-family holdout aggregation
5. bridge evaluation
6. canary admission if bridge passes

### 14.3 Recent-family evidence

Implement one helper module `fresh_contact.rs` that computes:

```rust
pub fn recent_family_gain(
    candidate: &ConstellationScoreReceipt,
    incumbent: &ConstellationScoreReceipt,
    fresh_meta: &[FamilyFreshnessMeta],
    current_epoch: u64,
) -> RecentFamilyGainReceipt
```

Rules:

- only families with `current_epoch <= fresh_until_epoch` count,
- use transfer holdout delta where present,
- otherwise use static holdout delta,
- require `max_recent_family_gain_bpb >= tau_recent`.

### 14.4 Public admission quotas by class

Use fixed quotas:

```text
max_public_survivors_total      = 12
max_public_survivors_pwarm      = 4
max_public_survivors_pcold      = 2
max_holdout_admissions_pwarm    = 2
max_holdout_admissions_pcold    = 1
```

This keeps cold experimentation bounded.

---

## 15. Judge rules

Promotion remains lexicographic and deterministic.

### 15.1 Shared gates

Every candidate must pass these shared gates first:

1. protocol validity
2. public static truth improvement
3. public transfer and robustness non-regression
4. holdout static truth improvement
5. protected-family floors
6. stability and resource safety

### 15.2 `S` and `A`

`S` and `A` continue to follow Phase 2 semantics.

Additional Phase 3 rule:

- if a macro registry is used, all macro calls must be lowered and verified first.

### 15.3 `PWarm`

A `PWarm` candidate promotes only if all of the following are true:

- paradigm signature differs from incumbent,
- weighted static holdout delta exceeds `p_warm_min_static_delta_bpb`,
- weighted transfer holdout delta exceeds `p_warm_min_transfer_delta_bpb`,
- weighted robustness holdout delta does not regress beyond `p_warm_max_robust_regress_bpb`,
- protected-family floors pass,
- recent-family gain passes,
- warm bridge passes,
- mandatory canary passes,
- rollback target is written before activation.

### 15.4 `PCold`

A `PCold` candidate promotes only if all of the following are true:

- paradigm signature differs from incumbent,
- no valid warm bridge exists or `bridge_kind == Cold`,
- weighted static holdout delta exceeds `p_cold_min_static_delta_bpb`,
- weighted transfer holdout delta exceeds `p_cold_min_transfer_delta_bpb`,
- improved family count exceeds `p_cold_min_improved_families`,
- protected-family floors pass,
- recent-family gain passes,
- cold boundary passes,
- mandatory canary passes,
- rollback target is written before activation.

### 15.5 Suggested initial thresholds

Use config, but seed it with these defaults:

```text
p_warm_min_static_delta_bpb         = 0.0020
p_warm_min_transfer_delta_bpb       = 0.0010
p_warm_max_robust_regress_bpb       = 0.0005
p_warm_min_recent_family_gain_bpb   = 0.0010

p_cold_min_static_delta_bpb         = 0.0060
p_cold_min_transfer_delta_bpb       = 0.0030
p_cold_min_recent_family_gain_bpb   = 0.0025
p_cold_max_anchor_regret_bpb        = 0.0010
p_cold_max_error_streak             = 3
p_cold_min_improved_families        = 2
```

### 15.6 Typed reasons

Return typed reasons at the first failing lexicographic gate.

Examples:

- `WarmRefinementFail`
- `ColdBoundaryFail`
- `RecentFamilyGainFail`
- `PColdMarginInsufficient`
- `BackendEquivalenceFail`
- `RollbackTargetMissing`

---

## 16. Canary and rollback

### 16.1 Mandatory canary policy

`S` and `A` may canary optionally as in Phase 2.

`PWarm` and `PCold` must canary always.

### 16.2 Shadow canary behavior

The incumbent remains active while the candidate runs in shadow on canary panels.

For every paradigm canary:

- run the candidate on canary windows,
- score native-head truth,
- track per-family regret versus incumbent,
- track maximum consecutive bad windows,
- emit `canary_receipt.json`.

### 16.3 Canary thresholds

Suggested initial thresholds:

- `PWarm`: 128 windows, no protected-family regress above configured tolerance
- `PCold`: 256 windows, no streak above `max_error_streak`, anchor regret bounded

### 16.4 Rollback behavior

Before activating `PWarm` or `PCold`:

1. atomically write `rollback_candidate.json = incumbent_active_hash`,
2. atomically stage new `active_candidate.json`,
3. atomically write promotion receipt.

If a post-activation smoke check or canary finalization fails before commit, restore the incumbent and emit a rollback receipt.

---

## 17. Orchestrator algorithm

Implement the Phase 3 epoch path in `orchestrator.rs`.

```rust
pub fn run_phase3_epoch(cfg: &Phase3Config) -> anyhow::Result<()> {
    let incumbent = load_active_candidate()?;
    let constellation = load_active_constellation()?;
    let snapshot = load_active_snapshot()?;
    let macro_registry = load_or_build_macro_registry(cfg, &snapshot)?;

    let witnesses = build_family_aware_witness_battery(&incumbent, &constellation)?;
    let error_atlas = load_or_build_error_atlas(&incumbent, &constellation)?;

    let truth_pool = run_truth_lane_phase3(
        &incumbent,
        &constellation,
        &macro_registry,
        &witnesses,
        cfg,
    )?;

    let equiv_pool = run_equivalence_lane_phase3(
        &incumbent,
        &constellation,
        &macro_registry,
        &witnesses,
        cfg,
    )?;

    let incubator_pool = run_incubator_lane_phase3(
        &incumbent,
        &constellation,
        &macro_registry,
        &error_atlas,
        &witnesses,
        cfg,
    )?;

    let frontier_pool = run_cold_frontier_lane(
        &incumbent,
        &constellation,
        &macro_registry,
        &error_atlas,
        cfg,
    )?;

    let mut candidates = merge_candidate_pools(
        truth_pool,
        equiv_pool,
        incubator_pool,
        frontier_pool,
    )?;

    candidates = canonicalize_lower_verify(candidates, &macro_registry, cfg)?;
    candidates = attach_backend_plans_and_equiv(candidates, &constellation, cfg)?;
    candidates = witness_prefilter(candidates, &witnesses, cfg)?;

    let public_receipts = run_phase3_public_eval(&incumbent, &candidates, &constellation, cfg)?;
    let admitted = admit_phase3_holdout(public_receipts, cfg)?;

    let holdout_receipts = run_phase3_holdout_eval(&incumbent, &admitted, &constellation, cfg)?;
    let classified = classify_candidates(admitted, &holdout_receipts)?;

    let bridge_receipts = evaluate_bridges(&incumbent, &classified, &constellation, cfg)?;
    let judged = judge_phase3(&incumbent, &classified, &holdout_receipts, &bridge_receipts, cfg)?;

    let canary_survivors = run_paradigm_canary_if_required(judged, &constellation, cfg)?;
    let best = select_best_lexicographically(canary_survivors)?;

    if let Some(winner) = best {
        stage_rollback_target(&incumbent)?;
        atomic_activate_phase3(&winner, &constellation, &snapshot)?;
    }

    append_phase3_archives()?;
    Ok(())
}
```

---

## 18. CLI behavior

### 18.1 `apfsc_build_lowered_candidate`

Purpose:

- load candidate manifest and SCIR-v2,
- canonicalize,
- lower macros,
- verify bounds,
- emit `scir_canonical.json`, `scir_lowered.json`, and `compile_receipt.json`.

Example:

```text
cargo run --bin apfsc_build_lowered_candidate -- --candidate <candidate_hash>
```

### 18.2 `apfsc_backend_equiv`

Purpose:

- load a lowered candidate,
- attempt GraphBackend lowering,
- run interpreter and GraphBackend on equivalence windows,
- emit `backend_equiv_receipt.json`.

Example:

```text
cargo run --bin apfsc_backend_equiv -- --candidate <candidate_hash>
```

### 18.3 `apfsc_bridge_eval`

Purpose:

- classify candidate as warm or cold,
- execute warm refinement or cold boundary checks,
- emit `bridge_receipt.json`.

Example:

```text
cargo run --bin apfsc_bridge_eval -- --candidate <candidate_hash>
```

### 18.4 `apfsc_macro_mine`

Purpose:

- scan archive fragments,
- emit induced macro candidates,
- write a new macro registry for the next epoch.

Example:

```text
cargo run --bin apfsc_macro_mine -- --snapshot <snapshot_hash>
```

### 18.5 `apfsc_public_eval`, `apfsc_judge_daemon`, `apfsc_shadow_canary`, `apfsc_epoch_run`

Extend these binaries rather than cloning them.

Required behavior:

- `apfsc_public_eval` must understand SCIR-v2, macro lowering, backend plans, and class quotas,
- `apfsc_judge_daemon` must understand `PWarm` and `PCold`,
- `apfsc_shadow_canary` must enforce mandatory paradigm windows and rollback-aware receipts,
- `apfsc_epoch_run` must accept `--profile phase3`.

---

## 19. Config schema

Extend config with a Phase 3 profile.

Example `fixtures/apfsc/phase3/config/phase3.toml`:

```toml
[phase3]
profile = "phase3"
allow_p_warm = true
allow_p_cold = true
fresh_horizon_epochs = 8

[budgets]
truth = 0.35
equivalence = 0.20
incubator = 0.25
cold_frontier = 0.20

[limits]
max_scir_core_ops = 4096
max_macro_calls_per_program = 16
max_macro_expansion_ops = 256
max_macro_depth = 1
max_egraph_nodes = 50000
max_egraph_extractions = 32
max_paradigm_public_candidates = 12
max_pwarm_holdout_admissions = 2
max_pcold_holdout_admissions = 1

[promotion]
p_warm_min_static_delta_bpb = 0.0020
p_warm_min_transfer_delta_bpb = 0.0010
p_warm_max_robust_regress_bpb = 0.0005
p_warm_min_recent_family_gain_bpb = 0.0010
p_cold_min_static_delta_bpb = 0.0060
p_cold_min_transfer_delta_bpb = 0.0030
p_cold_min_recent_family_gain_bpb = 0.0025
p_cold_max_anchor_regret_bpb = 0.0010
p_cold_max_error_streak = 3
p_cold_min_improved_families = 2

[macro]
min_macro_support = 3
min_macro_public_gain_bpb = 0.001
min_macro_reduction_ratio = 1.20
max_induced_macros_per_epoch = 8

[backend]
allow_graph_backend_public = true
allow_graph_backend_canary = true
allow_graph_backend_holdout = false
require_exact_backend_equiv = true

[canary]
warm_windows = 128
cold_windows = 256
```

Rules:

- configs are deterministic inputs and must be content-addressed,
- if a profile flag conflicts with protocol law, fail closed,
- `allow_graph_backend_holdout` must remain false in Phase 3.

---

## 20. Acceptance tests

Implement these tests exactly.

### 20.1 `apfsc_phase3_scir_v2.rs`

- build a SCIR-v2 candidate with seed macros,
- canonicalize and lower it,
- assert deterministic hashes and bound checks.

### 20.2 `apfsc_phase3_macro_lowering.rs`

- verify macro lowering is deterministic,
- verify macro expansion is charged in code length,
- verify recursive macro calls are rejected.

### 20.3 `apfsc_phase3_macro_mine.rs`

- construct archive fragments with repeated support,
- assert accepted induced macro receipt when thresholds are met,
- assert rejection when support or gain is too low.

### 20.4 `apfsc_phase3_graph_backend.rs`

- lower a graph-safe candidate,
- run backend equivalence,
- require exact byte-mass match,
- verify fallback to interpreter on failure.

### 20.5 `apfsc_phase3_classifier.rs`

- construct fixtures that differ only structurally -> `A`,
- differ semantically with warm bridge -> `PWarm`,
- differ semantically without warm bridge -> `PCold`.

### 20.6 `apfsc_phase3_warm_bridge.rs`

- verify `WarmRefinementPack` passes on a compatible state-map fixture,
- verify failure on incompatible observable mapping.

### 20.7 `apfsc_phase3_cold_boundary.rs`

- verify `ColdBoundaryPack` passes a strong truth margin fixture,
- verify rejection for excessive anchor regret,
- verify rejection for recent-family miss.

### 20.8 `apfsc_phase3_recent_family_gate.rs`

- mark one family stale and one fresh,
- verify only the fresh family contributes to the recent-family gate.

### 20.9 `apfsc_phase3_canary_rollback.rs`

- simulate a `PCold` candidate that fails canary,
- assert incumbent remains active and rollback pointer is intact.

### 20.10 `apfsc_phase3_e2e_pwarm.rs`

- run one deterministic epoch with a warm-winning candidate,
- assert activation and receipt hashes match expected fixtures.

### 20.11 `apfsc_phase3_e2e_pcold.rs`

- run one deterministic epoch with a cold-winning candidate,
- assert:
  - cold boundary receipt exists,
  - mandatory canary receipt exists,
  - rollback pointer was written before activation,
  - final activation matches expected fixtures.

---

## 21. Coding rules for codex

1. Preserve all Phase 1 and Phase 2 public APIs unless a Phase 3 extension requires a field addition.
2. Centralize class-classification logic in `paradigm.rs`. Do not scatter class inference across binaries.
3. Keep deterministic ordering everywhere: family ids, macro ids, candidate ids, fragment hashes, and witness refs must all be sorted lexicographically before hashing.
4. Macro lowering, backend equivalence, and bridge evaluation must each write standalone receipts so failures are debuggable.
5. Do not add hidden randomness to macro induction or cold-frontier proposal order.
6. Do not add Python or external processes in judged execution.
7. Every receipt and manifest must carry protocol version, snapshot hash, and constellation id where relevant.
8. Keep holdout truth on the interpreter. Do not silently shortcut holdout through GraphBackend.
9. Do not let a compat head influence promotion truth.
10. Do not write over `rollback_candidate.json` after canary starts. It must point to the pre-activation incumbent.
11. If backend equivalence fails, fail closed to interpreter. Do not partially accept approximate graph execution.
12. Cold-frontier candidates must still reuse shared scoring and archive code. Do not fork a second scoring plane.

---

## 22. Suggested implementation order

Implement in this order.

1. Extend common types, config, and promotion enums.
2. Upgrade SCIR AST to SCIR-v2 with canonicalization, lowering, and bounds checks.
3. Add seed macro registry and deterministic macro lowering.
4. Add macro induction miner.
5. Add `ParadigmSignature` and class-classification logic.
6. Add backend plan and GraphBackend equivalence receipts.
7. Extend candidate, headpack, bridge, and schedule contracts.
8. Upgrade lanes for macro-aware and cold-frontier proposals.
9. Extend public eval for SCIR-v2, backend plans, and class quotas.
10. Implement warm bridge evaluation.
11. Implement cold boundary evaluation.
12. Extend canary and rollback.
13. Extend archives.
14. Wire the Phase 3 orchestrator.
15. Write tests and lock expected receipts.
16. Run one deterministic warm epoch and one deterministic cold epoch.

---

## 23. Minimum viable demo sequence

The codex agent should make this exact demo runnable:

```text
cargo run --bin apfsc_seed_init -- --profile phase1

# Reuse Phase 2 families, then add Phase 3 fresh families
cargo run --bin apfsc_ingest_reality -- fixtures/apfsc/phase3/reality_f4_event_sparse_base
cargo run --bin apfsc_ingest_reality -- fixtures/apfsc/phase3/reality_f4_event_sparse_transfer
cargo run --bin apfsc_ingest_reality -- fixtures/apfsc/phase3/reality_f4_event_sparse_robust
cargo run --bin apfsc_ingest_reality -- fixtures/apfsc/phase3/reality_f5_formal_alg_base
cargo run --bin apfsc_ingest_reality -- fixtures/apfsc/phase3/reality_f5_formal_alg_transfer
cargo run --bin apfsc_ingest_reality -- fixtures/apfsc/phase3/reality_f5_formal_alg_robust

cargo run --bin apfsc_ingest_prior -- fixtures/apfsc/phase3/priors/macro_seed
cargo run --bin apfsc_macro_mine -- --snapshot <snapshot_hash>
cargo run --bin apfsc_epoch_run -- --profile phase3 --epochs 1
```

Expected behavior:

- macro registry is created,
- candidates are canonicalized and lowered,
- graph-eligible candidates receive backend equivalence receipts,
- public and holdout constellation receipts are emitted,
- warm or cold bridge receipts are emitted,
- paradigm canary receipt is emitted where required,
- candidate activates or rejects deterministically,
- rollback target is preserved for paradigm classes.

---

## 24. Definition of done

Phase 3 is complete only if all of the following are true:

1. SCIR-v2 exists and is deterministic,
2. macro lowering exists and is deterministic,
3. one bounded macro-induction path exists,
4. GraphBackend equivalence receipts exist for eligible candidates,
5. candidate classification into `S`, `A`, `PWarm`, and `PCold` is deterministic,
6. `WarmRefinementPack` gates `A` and `PWarm`,
7. `ColdBoundaryPack` gates `PCold`,
8. recent-family gain is enforced for `PWarm` and `PCold`,
9. mandatory canary exists for paradigm promotions,
10. rollback target is preserved for paradigm promotions,
11. one warm positive path works end to end,
12. one cold positive path works end to end,
13. replay of the same one-epoch run reproduces the same receipts exactly.

---

## 25. Explicit deferrals

These belong to later phases. Do not start them in Phase 3.

- `G` search-law promotion,
- hidden challenge families as mandatory truth gate,
- NativeBlock judged execution,
- learned search budgeting,
- multi-parent recombination,
- active data acquisition,
- law archive as a judged promotion object,
- protocol self-editing,
- autonomous admissibility changes.

---

## 26. Final implementation intent

Phase 3 is the point where APF-SC becomes capable of genuine architectural discontinuity without surrendering scientific control. The codex agent should implement it as a disciplined extension of Phase 2, not as a second system. The trusted plane stays fixed. Byte-level MDL on sealed panels remains the truth atom. Family-normalized judgment remains in force. The new ingredient is that APF-SC can now represent, evaluate, and safely activate candidates whose computational semantics differ from the incumbent in meaningful ways. Warm changes prove continuity through refinement. Cold changes prove superiority through truth plus boundary safety. Macro induction broadens the proposal surface. GraphBackend broadens execution strategy. Canary plus rollback contain risk. That is the minimum end-to-end substrate required before a later phase can start improving the research strategy itself rather than only the candidate architectures.
