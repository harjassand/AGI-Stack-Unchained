# APF-SC Phase 2 MVP - Full End-to-End Implementation Specification

This document is the implementation contract for a codex agent. It extends the Phase 1 MVP from a bootstrap laboratory kernel into a family-aware bank constellation. The Phase 2 objective is not warm or cold paradigm change yet. The objective is to make promotion require reusable computational structure across multiple environments, with deterministic public and holdout judgment, protected-family floors, bounded transfer adaptation, robustness panels, and family-normalized scoring.

End to end in this phase means:

1. ingest multiple `RealityPack`s per family role,
2. build a deterministic bank constellation with four seed families,
3. run truth, equivalence, and incubator lanes against family-aware witnesses,
4. evaluate candidates on static public panels,
5. evaluate surviving structural candidates on transfer and robustness public panels,
6. evaluate admitted candidates on holdout static, transfer, and robustness panels,
7. judge promotions using weighted cross-family evidence and protected-family floors,
8. canary and atomically activate successful candidates,
9. write family-aware receipts and archives.

The Phase 2 exit criterion is simple:

**promotion must require cross-family evidence rather than one-family specialization.**

---

## 1. Hard constraints

Codex must follow these constraints exactly.

### 1.1 Phase 1 is a prerequisite

Assume the Phase 1 MVP contract exists or is being implemented exactly as specified in `apfsc_phase1_mvp_spec.md`.

Phase 2 is an extension layer. Do not redesign the trusted APF-SC Phase 1 kernel unless a Phase 2 data model requires a mechanical extension. Preserve Phase 1 semantics where possible.

### 1.2 Trusted substrate boundary

Treat the existing APF-v3 substrate in `baremetal_lgp` / `apf3` as immutable. Reuse existing facilities for:

- deterministic replay capsules and digests,
- content-addressed artifacts,
- atomic pointer writes,
- judge-only activation,
- fail-closed execution,
- rollback pointers.

If the names differ in the repo, adapt at the APF-SC boundary. Do not refactor APF-v3 core code.

### 1.3 Implement in Phase 2 now

Implement now:

- a `ConstellationManifest` built from multiple family-specific `RealityPack`s,
- family roles for base, transfer, robust, and optional challenge-stub packs,
- four seed families,
- family-normalized static scoring,
- fixed family weights,
- protected-family floors,
- bounded transfer adaptation and scoring,
- robustness panel scoring,
- family-aware public admission,
- family-aware holdout admission,
- family-aware judge receipts,
- lane quotas so all families participate in search,
- archive extensions for per-family outcomes,
- one Phase 2 end-to-end epoch path.

### 1.4 Explicitly do not implement now

Do not implement now:

- P-warm or P-cold promotion,
- challenge panels as a promotion gate,
- NativeBlock in judged execution,
- full macro induction,
- search-law promotion,
- distributed execution,
- multi-parent recombination,
- family-adaptive weights,
- active data acquisition,
- protocol self-modification.

### 1.5 Promotion classes in Phase 2

Phase 2 keeps the same class names as Phase 1, but only these are active:

- `S`: allowed
- `A`: allowed
- `PWarmDisabled`: schema-present, not admitted
- `PColdDisabled`: schema-present, not admitted
- `GDisabled`: schema-present, not admitted

### 1.6 Runtime envelope

Still target a single Apple-silicon machine with an effective 16 GiB protocol envelope.

Use these Phase 2 limits unless the Phase 1 repo already exposes stricter constants:

```text
RSS_HARD_LIMIT_BYTES                = 12 GiB
RSS_ABORT_LIMIT_BYTES               = 14 GiB
MAX_CONCURRENT_MAPPED_BYTES         = 2 GiB
SEGMENT_BYTES                       = 256 MiB
STATE_TILE_BYTES_MAX                = 2 MiB
MAX_ACTIVE_FAMILIES                 = 4
MAX_STATIC_PUBLIC_CANDIDATES        = 32
MAX_TRANSFER_PUBLIC_CANDIDATES      = 12
MAX_ROBUST_PUBLIC_CANDIDATES        = 12
MAX_HOLDOUT_STATIC_ADMISSIONS       = 6
MAX_HOLDOUT_XFER_ROBUST_ADMISSIONS  = 4
MAX_PUBLIC_WORKERS                  = 2
MAX_TRANSFER_WORKERS                = 1
MAX_ROBUST_WORKERS                  = 1
MAX_CANARY_WORKERS                  = 1
MAX_RESIDENT_INCUBATORS             = 16
MAX_TRANSFER_FAST_WEIGHT_BYTES      = 256 KiB
MAX_TRANSFER_DELTA_BITS             = 524288
```

The judged path must remain deterministic and pageout-free.

---

## 2. What success means

Phase 2 MVP is done when all of the following are true:

1. `cargo test` passes for all Phase 1 and Phase 2 tests.
2. Four seed family groups can be ingested and assembled into one deterministic constellation.
3. Static public and holdout receipts report per-family metrics and weighted cross-family scores.
4. Transfer public and holdout receipts report bounded adapted metrics per family.
5. Robustness public and holdout receipts report per-family metrics.
6. A deliberately over-specialized candidate that only improves one family is rejected with `InsufficientCrossFamilyEvidence` or `ProtectedFamilyRegress`.
7. At least one candidate with positive weighted multi-family evidence can pass judge and canary.
8. `apfsc_epoch_run --profile phase2 --epochs 1` produces end-to-end receipts and either a rejection or successful activation.
9. Replay of the same epoch with the same snapshot and constellation reproduces the same receipts exactly.

A successful demo trace should look like:

```text
seed init
-> ingest 4 family groups
-> build constellation
-> spawn family-aware candidates
-> witness prefilter
-> static public eval
-> transfer/robust public eval
-> holdout static eval
-> holdout transfer/robust eval
-> judge
-> canary
-> atomic activate or reject
-> archive update
```

---

## 3. Repo delta to add or modify

Keep APF-v3 untouched. Extend the APF-SC tree from Phase 1.

### 3.1 New and modified modules

```text
src/apfsc/
  mod.rs                         (update exports)
  types.rs                       (extend for family roles and panel kinds)
  config.rs                      (phase2 profile and weights)
  bank.rs                        (family-aware bank building)
  candidate.rs                   (family-aware metadata)
  judge.rs                       (phase2 judge gates)
  canary.rs                      (family-aware canary metadata)
  seed.rs                        (phase2 fixture installers)
  orchestrator.rs                (staged phase2 epoch flow)

  constellation.rs              (new)
  normalization.rs              (new)
  transfer.rs                   (new)
  robustness.rs                 (new)
  challenge_stub.rs             (new, schema only)

  ingress/
    manifest.rs                 (extend RealityPack meta)
    reality.rs                  (grouped family-role ingestion)
    receipts.rs                 (family-aware receipts)

  archive/
    mod.rs                      (update exports)
    genealogy.rs                (extend family vectors)
    error_atlas.rs              (per-family bins)
    family_scores.rs            (new)
    transfer_trace.rs           (new)
    robustness_trace.rs         (new)
```

### 3.2 New and modified binaries

```text
src/bin/
  apfsc_build_constellation.rs   (new)
  apfsc_transfer_eval.rs         (new)
  apfsc_robust_eval.rs           (new)

  apfsc_ingest_reality.rs        (extend)
  apfsc_public_eval.rs           (extend static public mode)
  apfsc_judge_daemon.rs          (extend family-aware judge mode)
  apfsc_epoch_run.rs             (extend with profile=phase2)
```

### 3.3 Fixtures and tests

```text
fixtures/apfsc/phase2/
  reality_f0_det_base/
  reality_f0_det_transfer/
  reality_f0_det_robust/

  reality_f1_text_base/
  reality_f1_text_transfer/
  reality_f1_text_robust/

  reality_f2_sensor_base/
  reality_f2_sensor_transfer/
  reality_f2_sensor_robust/

  reality_f3_phys_base/
  reality_f3_phys_transfer/
  reality_f3_phys_robust/

  config/phase2.toml
  expected/phase2_constellation_manifest.json

tests/
  apfsc_phase2_constellation.rs
  apfsc_phase2_normalization.rs
  apfsc_phase2_transfer.rs
  apfsc_phase2_robustness.rs
  apfsc_phase2_judge.rs
  apfsc_phase2_specialist_reject.rs
  apfsc_phase2_e2e.rs
```

---

## 4. Phase 2 simplifications

These simplifications are intentional. Do not "improve" them away during implementation.

1. Judged execution stays on the Phase 1 Rust Tier-0 interpreter.
2. `SCIR-Lite` remains the only judged architecture calculus.
3. Transfer adaptation updates only bounded residual surfaces and fast weights. It does not rewrite architecture or core structural weights.
4. Robustness panels are explicit reality-pack variants, not a general transformation engine.
5. Challenge-stub support is added in schema and artifact layout, but it is not a promotion gate in Phase 2.
6. Family weights are static config, not learned.
7. The public admission pipeline is staged to save compute: static first, then transfer and robustness only for survivors.
8. Search still uses deterministic heuristics and lane budgets. Search-law recursion remains deferred.

---

## 5. On-disk artifact delta

Extend the Phase 1 artifact tree.

```text
artifacts/apfsc/
  constellations/
    <constellation_id>.json

  banks/
    <family_id>/
      family_manifest.json
      windows/
        train/*.json
        static_public/*.json
        static_holdout/*.json
        anchor/*.json
        canary/*.json
        transfer_train/*.json
        transfer_eval/*.json
        robust_public/*.json
        robust_holdout/*.json
        challenge_stub/*.json

  receipts/
    public_static/<candidate_hash>.json
    public_transfer/<candidate_hash>.json
    public_robust/<candidate_hash>.json
    holdout_static/<candidate_hash>.json
    holdout_transfer/<candidate_hash>.json
    holdout_robust/<candidate_hash>.json
    judge/<candidate_hash>.json
    canary/<candidate_hash>.json
    activation/<candidate_hash>.json

  pointers/
    active_candidate
    rollback_candidate
    active_snapshot
    active_constellation

  archive/
    genealogy.jsonl
    error_atlas.jsonl
    family_scores.jsonl
    transfer_trace.jsonl
    robustness_trace.jsonl
    hardware_trace.jsonl
```

Rules:

- all content artifacts remain content-addressed,
- all receipt paths remain immutable,
- only pointer files are mutable,
- challenge-stub windows are never exposed to public search code,
- holdout, transfer-eval, and robust-holdout payload access must remain staged and deterministic.

---

## 6. Core data contracts

Implement these contracts directly in Rust. Field names may be adapted to repo style, but semantics must remain unchanged.

### 6.1 Family and panel taxonomy

```rust
pub type FamilyId = String;
pub type VariantId = String;
pub type ConstellationId = String;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum FamilyKind {
    AlgorithmicSymbolic,
    TextCodeLog,
    SensoryTemporal,
    PhysicalSimulation,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum RealityRole {
    Base,
    Transfer,
    Robust,
    ChallengeStub,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, PartialOrd, Ord)]
pub enum PanelKind {
    Train,
    StaticPublic,
    StaticHoldout,
    Anchor,
    Canary,
    TransferTrain,
    TransferEval,
    RobustPublic,
    RobustHoldout,
    ChallengeStub,
}
```

### 6.2 Reality metadata

Extend `PackManifest.meta` for `PackKind::Reality` so it cleanly decodes into:

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RealityMeta {
    pub family_id: FamilyId,
    pub family_kind: FamilyKind,
    pub role: RealityRole,
    pub variant_id: VariantId,
    pub base_family_id: Option<FamilyId>,
    pub description: String,
}
```

Rules:

- base packs use `role = Base`,
- transfer packs use `role = Transfer`,
- robust packs use `role = Robust`,
- challenge packs use `role = ChallengeStub`,
- each family must have exactly one base pack,
- each family must have at least one transfer and one robust pack for full Phase 2 operation.

### 6.3 Family spec and constellation manifest

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FamilyWeights {
    pub static_weight: f64,
    pub transfer_weight: f64,
    pub robust_weight: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProtectionFloor {
    pub protected: bool,
    pub max_static_regress_bpb: f64,
    pub max_transfer_regress_bpb: f64,
    pub max_robust_regress_bpb: f64,
    pub min_family_improve_bpb: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TransferAdaptSpec {
    pub steps: u32,
    pub lr: f32,
    pub eps: f32,
    pub l2: f32,
    pub clip_grad: f32,
    pub batch_windows: u32,
    pub max_fast_weight_bytes: u64,
    pub max_delta_bits: u64,
    pub reset_ephemeral_state: bool,
    pub mutable_surfaces: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FamilySpec {
    pub family_id: FamilyId,
    pub family_kind: FamilyKind,
    pub base_pack_hash: String,
    pub transfer_pack_hashes: Vec<String>,
    pub robust_pack_hashes: Vec<String>,
    pub challenge_pack_hashes: Vec<String>,
    pub weights: FamilyWeights,
    pub floors: ProtectionFloor,
    pub transfer_adapt: TransferAdaptSpec,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NormalizationPolicy {
    pub codelen_ref_bytes: u64,
    pub transfer_ref_bytes: u64,
    pub min_improved_families: u32,
    pub min_nonprotected_improved_families: u32,
    pub require_target_subset_hit: bool,
    pub target_subset: Vec<FamilyId>,
    pub public_static_margin_bpb: f64,
    pub holdout_static_margin_bpb: f64,
    pub holdout_transfer_margin_bpb: f64,
    pub holdout_robust_margin_bpb: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConstellationManifest {
    pub constellation_id: ConstellationId,
    pub snapshot_hash: SnapshotId,
    pub family_specs: Vec<FamilySpec>,
    pub normalization: NormalizationPolicy,
    pub protocol_version: String,
    pub manifest_hash: String,
}
```

### 6.4 Bank manifests

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FamilyBankManifest {
    pub family_id: FamilyId,
    pub family_kind: FamilyKind,
    pub source_pack_hashes: Vec<String>,
    pub window_len: u32,
    pub stride: u32,
    pub panel_counts: std::collections::BTreeMap<String, u64>,
    pub manifest_hash: String,
}
```

### 6.5 Candidate metadata additions

Keep the Phase 1 `CandidateManifest` and add only these fields:

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CandidateBuildMeta {
    pub target_families: Vec<FamilyId>,
    pub source_lane: String,
    pub phase2_profile: String,
}
```

Store `CandidateBuildMeta` behind `build_meta_hash` or inline if Phase 1 has not yet fixed the storage shape.

### 6.6 Family receipts and constellation receipts

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FamilyPanelMetric {
    pub family_id: FamilyId,
    pub panel: PanelKind,
    pub bits_total: f64,
    pub target_bytes: u64,
    pub mean_bpb: f64,
    pub window_count: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FamilyEvalVector {
    pub family_id: FamilyId,
    pub static_public_bpb: Option<f64>,
    pub static_holdout_bpb: Option<f64>,
    pub anchor_bpb: Option<f64>,
    pub transfer_public_bpb: Option<f64>,
    pub transfer_holdout_bpb: Option<f64>,
    pub robust_public_bpb: Option<f64>,
    pub robust_holdout_bpb: Option<f64>,
    pub challenge_stub_bpb: Option<f64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConstellationScoreReceipt {
    pub candidate_hash: CandidateId,
    pub incumbent_hash: CandidateId,
    pub snapshot_hash: SnapshotId,
    pub constellation_id: ConstellationId,
    pub per_family: std::collections::BTreeMap<FamilyId, FamilyEvalVector>,
    pub code_penalty_bpb: f64,
    pub weighted_static_public_bpb: Option<f64>,
    pub weighted_static_holdout_bpb: Option<f64>,
    pub weighted_transfer_public_bpb: Option<f64>,
    pub weighted_transfer_holdout_bpb: Option<f64>,
    pub weighted_robust_public_bpb: Option<f64>,
    pub weighted_robust_holdout_bpb: Option<f64>,
    pub improved_families: Vec<FamilyId>,
    pub nonprotected_improved_families: Vec<FamilyId>,
    pub regressed_families: Vec<FamilyId>,
    pub protected_floor_pass: bool,
    pub target_subset_pass: bool,
    pub replay_hash: String,
}
```

### 6.7 Promotion receipt extensions

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PromotionReceipt {
    pub candidate_hash: CandidateId,
    pub incumbent_hash: CandidateId,
    pub decision: JudgeDecision,
    pub reason: String,
    pub weighted_static_public_delta_bpb: f64,
    pub weighted_static_holdout_delta_bpb: f64,
    pub weighted_transfer_holdout_delta_bpb: Option<f64>,
    pub weighted_robust_holdout_delta_bpb: Option<f64>,
    pub improved_family_ids: Vec<FamilyId>,
    pub regressed_family_ids: Vec<FamilyId>,
    pub protected_floor_failures: Vec<FamilyId>,
    pub canary_required: bool,
    pub canary_result: Option<String>,
    pub snapshot_hash: SnapshotId,
    pub constellation_id: ConstellationId,
}
```

### 6.8 New reject reasons

Add these reject reasons if the repo uses typed enums:

- `InsufficientCrossFamilyEvidence`
- `ProtectedFamilyRegress`
- `TransferRegression`
- `RobustRegression`
- `TargetSubsetMiss`
- `ConstellationMismatch`
- `MissingFamilyRole`
- `TransferDeltaBudgetExceeded`

---

## 7. Seed constellation and fixtures

Phase 2 must ship with four seed family groups. Each group has one base pack, one transfer pack, and one robust pack.

### 7.1 Family F0 - `det_micro`

Kind: `AlgorithmicSymbolic`

Base payload content:

- exact periodic segments,
- copy-replay segments,
- delimiter-reset segments,
- stack-machine trace bytes,
- counter-mod arithmetic segments.

Transfer payload content:

- unseen periods,
- unseen delimiter vocabulary,
- different counter bases,
- altered stack op mixtures.

Robust payload content:

- equivalent subfamily under altered segmentation and phase shifts,
- deterministic acquisition variant with shifted boundaries.

Purpose:

- enforce exact certainty where appropriate,
- expose whether candidates actually learned algorithmic structure.

### 7.2 Family F1 - `text_code`

Kind: `TextCodeLog`

Base payload content:

- ASCII text,
- code snippets,
- log-style lines,
- newline and delimiter structure.

Transfer payload content:

- held-out text style or file type,
- alternate code idiom or log template.

Robust payload content:

- similar corpus with deterministic line-ending and spacing perturbations,
- alternate log burst density.

Purpose:

- test local context, delimiter handling, and nuisance behavior.

### 7.3 Family F2 - `sensor_temporal`

Kind: `SensoryTemporal`

Base payload content:

- quantized multi-channel sensor-like traces serialized to bytes,
- bursts, drifts, resets, and periodic cycles.

Transfer payload content:

- unseen calibration offsets,
- different burst lengths,
- altered drift profile.

Robust payload content:

- minor deterministic jitter or quantization-profile change emitted as a new pack.

Purpose:

- introduce nontrivial nuisance structure and temporal continuity.

### 7.4 Family F3 - `phys_sim`

Kind: `PhysicalSimulation`

Base payload content:

- serialized bytes from a tiny deterministic or low-noise simulator,
- collision, oscillation, or state-transition traces.

Transfer payload content:

- unseen simulator parameters,
- altered initial-condition regime,
- changed forcing pattern.

Robust payload content:

- related simulator capture with mild observational perturbation.

Purpose:

- require structural reuse beyond text-style heuristics.

### 7.5 Split policy

Use role-specific deterministic split policies.

For base packs:

```text
train           60%
static_public   15%
static_holdout  10%
anchor           5%
canary           5%
reserve          5%
```

For transfer packs:

```text
transfer_train  60%
transfer_eval   40%
```

For robust packs:

```text
robust_public   60%
robust_holdout  40%
```

For challenge-stub packs, if present:

```text
challenge_stub  100%
```

Window defaults:

```text
window_len = 256
stride     = 64
target     = next byte
```

### 7.6 Default family weights and floors

Ship this Phase 2 default policy in `fixtures/apfsc/phase2/config/phase2.toml`:

```text
static_weight  = 0.25 per family
transfer_weight = 0.25 per family
robust_weight = 0.25 per family

protected families = det_micro, text_code
min_improved_families = 2
min_nonprotected_improved_families = 1
target_subset = [det_micro, sensor_temporal, phys_sim]
```

Initial floor defaults:

```text
max_static_regress_bpb   = 0.0010
max_transfer_regress_bpb = 0.0020
max_robust_regress_bpb   = 0.0020
min_family_improve_bpb   = 0.0005
public_static_margin_bpb = 0.0010
holdout_static_margin_bpb = 0.0010
holdout_transfer_margin_bpb = 0.0000
holdout_robust_margin_bpb = 0.0000
```

These values are protocol defaults for the MVP. They can later move into governed config but do not make them dynamic in Phase 2.

---

## 8. Scoring and normalization

Phase 2 changes promotion truth from one-family raw aggregate to family-normalized cross-family evidence.

### 8.1 ByteNLL remains the atomic truth

Keep the Phase 1 byte-level next-byte scoring exactly unchanged.

For any panel window `w`:

```text
ByteNLL(C, w) = sum_t log2(S / f_t[w_t])
```

All determinism, fixed-point, and replay rules remain unchanged.

### 8.2 Panel BPB

For family `f` and panel `p`:

```text
PanelBPB(C, f, p) =
  sum_{w in Panel(f,p)} ByteNLL(C, w) / sum_{w in Panel(f,p)} bytes(w)
```

This gives a comparable bits-per-byte measure regardless of family size.

### 8.3 Code penalty

Convert model complexity into BPB-like units:

```text
CodePenaltyBPB(C) = CodeLenBits(C) / CODELEN_REF_BYTES
```

Use a fixed protocol constant:

```text
CODELEN_REF_BYTES = 4096
```

Do not make this depend on family size or current bank size.

### 8.4 Weighted static score

For static public or static holdout:

```text
StaticScoreBPB(C, panel) =
  CodePenaltyBPB(C) +
  sum_f alpha_f * PanelBPB(C, f, panel)
```

where `alpha_f` is the fixed static family weight from the constellation manifest.

### 8.5 Transfer score

For each family `f`, create an adapted clone `Adapt(C, f)` using only legal transfer-train windows and the family's `TransferAdaptSpec`.

Then:

```text
TransferPenaltyBPB(C, f) = DeltaBits(Adapt(C, f), C) / TRANSFER_REF_BYTES
TransferScoreBPB(C) =
  sum_f beta_f * (PanelBPB(Adapt(C,f), f, TransferEval) + TransferPenaltyBPB(C,f))
```

Use:

```text
TRANSFER_REF_BYTES = 4096
```

### 8.6 Robustness score

```text
RobustScoreBPB(C, panel) =
  sum_f gamma_f * PanelBPB(C, f, panel)
```

No adaptation is allowed in robustness evaluation.

### 8.7 Improvement deltas

Improvement is positive when the candidate has lower score than the incumbent.

```text
DeltaStatic(C, I, panel) = StaticScoreBPB(I, panel) - StaticScoreBPB(C, panel)
DeltaTransfer(C, I, panel) = TransferScoreBPB(I) - TransferScoreBPB(C)
DeltaRobust(C, I, panel) = RobustScoreBPB(I, panel) - RobustScoreBPB(C, panel)
```

### 8.8 Family-level evidence

Family `f` counts as improved if:

```text
PanelBPB(I, f, StaticHoldout) - PanelBPB(C, f, StaticHoldout) >= min_family_improve_bpb(f)
```

For Phase 2, count improvement using static holdout, not public.

This is the key rule that prevents one huge win on one family from dominating the promotion decision.

---

## 9. Transfer evaluation contract

Phase 2 transfer is bounded adaptation, not open training.

### 9.1 Legal mutable surfaces

Implement one deterministic transfer adaptation law:

`TransferHeadAdaGradLaw`

It may update only:

- `HeadPack.nuisance_head`,
- `HeadPack.residual_head`,
- explicit residual scale parameters in `StatePack.resid_weights`,
- bounded `fast_weights` storage.

It may not update:

- `A` / architecture topology,
- `SchedulePack`,
- `StatePack.core_weights`,
- `HeadPack.native_head`,
- `WarmRefinementPack`,
- any family weight or judge parameter.

### 9.2 Transfer procedure

For each family `f`:

1. clone the candidate,
2. reset ephemeral runtime state to the protocol null state,
3. zero or reinitialize fast weights deterministically,
4. run deterministic single-threaded AdaGrad on `TransferTrain(f)` windows,
5. quantize the post-adaptation delta with the fixed delta-state codec,
6. reject if delta bits exceed `max_delta_bits`,
7. score on `TransferEval(f)` windows,
8. discard the adapted clone after receipt emission.

### 9.3 Transfer hyperparameters

Default Phase 2 config:

```toml
[transfer]
steps = 64
lr = 0.03
eps = 1e-8
l2 = 1e-5
clip_grad = 1.0
batch_windows = 8
shuffle = false
max_fast_weight_bytes = 262144
max_delta_bits = 524288
reset_ephemeral_state = true
mutable_surfaces = ["nuisance_head", "residual_head", "resid_weights", "fast_weights"]
```

### 9.4 Transfer charge

Use the same deterministic delta codec for all families. The post-adaptation delta is part of the score. Do not hide adaptation cost.

### 9.5 Transfer evaluation staging

To save compute, Phase 2 evaluates transfer in two stages:

- `public_transfer`: only top static public survivors,
- `holdout_transfer`: only top holdout static survivors that still satisfy floors.

---

## 10. Robustness evaluation contract

Robustness is evaluation on related but not identical family captures. No adaptation is allowed.

### 10.1 Robustness rules

- Evaluate the original candidate, not an adapted copy.
- Use only the explicit robust packs bound into the constellation manifest.
- Emit separate public and holdout robustness receipts.
- Do not use robustness to mint search credit outside judged selection.

### 10.2 Robustness use in promotion

For Phase 2:

- `S` promotions do not require robustness gains; they only need static improvement and protected-family non-regression.
- `A` promotions require weighted robustness non-regression on holdout and no protected-family robustness floor failures.

This keeps Phase 2 tractable while ensuring structural changes are not brittle.

---

## 11. Bank constellation builder

Implement a dedicated builder that groups reality packs into family bundles and writes one `ConstellationManifest`.

### 11.1 Builder requirements

For each `family_id`:

- exactly one base pack is required,
- at least one transfer pack is required for full A-class operation,
- at least one robust pack is required for full A-class operation,
- challenge-stub packs are optional,
- every pack must share the same `family_id` and `family_kind`,
- all windows must be deterministically produced from manifests and payload hashes.

### 11.2 Builder pseudocode

```python
def build_constellation(snapshot, admitted_reality_packs, config):
    grouped = group_by_family(admitted_reality_packs)

    family_specs = []
    for family_id, packs in grouped.items():
        base = unique_role(packs, "Base")
        transfer = role_many(packs, "Transfer")
        robust = role_many(packs, "Robust")
        challenge = role_many(packs, "ChallengeStub")

        build_base_panels(base)
        build_transfer_panels(transfer)
        build_robust_panels(robust)
        build_challenge_stub_panels(challenge)

        spec = FamilySpec(
            family_id=family_id,
            family_kind=base.family_kind,
            base_pack_hash=base.pack_hash,
            transfer_pack_hashes=[p.pack_hash for p in transfer],
            robust_pack_hashes=[p.pack_hash for p in robust],
            challenge_pack_hashes=[p.pack_hash for p in challenge],
            weights=config.weights[family_id],
            floors=config.floors[family_id],
            transfer_adapt=config.transfer,
        )
        family_specs.append(spec)

    manifest = ConstellationManifest(
        constellation_id=hash(snapshot.hash + hash(family_specs)),
        snapshot_hash=snapshot.hash,
        family_specs=sort_by_family_id(family_specs),
        normalization=config.normalization,
        protocol_version=config.protocol_version,
        manifest_hash=content_hash(...)
    )

    write_constellation(manifest)
    atomically_update_active_constellation(manifest.constellation_id)
    return manifest
```

### 11.3 Public vs holdout visibility

Search code may see:

- train windows,
- static public windows,
- transfer-train windows,
- robust public windows,
- public receipts,
- bucketed holdout outcomes.

Search code may not see:

- static holdout payload bytes,
- transfer-eval payload bytes,
- robust-holdout payload bytes,
- challenge-stub payload bytes,
- raw per-window holdout traces.

---

## 12. Candidate generation changes

Phase 2 must prevent family starvation during search.

### 12.1 Family quotas

Per epoch, require at least:

- one truth-lane candidate targeted to each family,
- one equivalence-lane candidate targeted to a protected family,
- one incubator sidecar targeted to a nonprotected family,
- two global cross-family candidates.

### 12.2 Build meta

Every spawned candidate must include `target_families` in its build meta. This is diagnostic only. It must not affect judge truth.

### 12.3 Truth lane in Phase 2

Truth lane should generate:

- family-specialist variants for each family's top public error bins,
- one balanced low-risk candidate touching protected families,
- one global candidate based on aggregate witness failures.

### 12.4 Equivalence lane in Phase 2

Equivalence lane should continue to apply function-preserving rewrites, but score them against the family witness battery rather than one aggregate witness list.

### 12.5 Incubator lane in Phase 2

Incubator sidecars must be trained with mixed objectives:

- residual prediction on public windows from all families,
- at least one nuisance-invariant objective on public-vs-robust family pairs,
- optional transfer-train pre-adaptation objective,
- family-balanced sampling.

Do not route incubator improvements to holdout directly. They still have to emerge as normal `A` candidates.

---

## 13. Witness battery and error atlas v2

Phase 1 had one error atlas. Phase 2 needs per-family structure.

### 13.1 Error atlas structure

Store bins keyed by:

- `family_id`,
- `failure_class`,
- `window_hash`,
- `severity_bucket`.

Minimum failure classes:

- `periodicity_miss`
- `copy_span_miss`
- `delimiter_reset_miss`
- `entropy_overspread`
- `long_memory_miss`
- `nuisance_mismatch`
- `boundary_phase_miss`

### 13.2 Witness selection

Each epoch must construct a family-balanced witness set:

- 2 witness windows from each protected family,
- 1 witness window from each nonprotected family,
- 2 aggregate global witnesses.

### 13.3 Witness gate

Before transfer or robustness public evaluation, a candidate must improve at least one witness in two distinct families or reduce weighted witness loss enough to rank in the top band. This is a cheap compute-saving prefilter.

---

## 14. Judge rules

Phase 2 promotion remains lexicographic. All mandatory gates must pass in order.

### 14.1 Gate 1 - protocol validity

Reject on any of:

- protocol mismatch,
- missing artifact,
- replay mismatch,
- compilation failure,
- containment failure,
- bounds inference failure,
- missing constellation manifest,
- candidate snapshot / constellation mismatch.

### 14.2 Gate 2 - public static improvement

Candidate must clear `public_static_margin_bpb` on weighted static public score.

### 14.3 Gate 3 - public protected-family floors

No protected family may regress beyond `max_static_regress_bpb` on public static.

### 14.4 Gate 4 - public family coverage

Candidate must satisfy all of:

- `improved_families_count >= min_improved_families`,
- `nonprotected_improved_families_count >= min_nonprotected_improved_families`,
- `target_subset_pass == true` if target subsets are enabled.

Use public metrics here only as a spend gate.

### 14.5 Gate 5 - public transfer and robustness precheck for A

For `A` candidates only:

- public transfer must be non-regressing in weighted score,
- public robustness must be non-regressing in weighted score,
- no protected family may fail public transfer or robustness floors.

### 14.6 Gate 6 - holdout static improvement

Candidate must clear `holdout_static_margin_bpb` on weighted static holdout score.

### 14.7 Gate 7 - holdout protected-family floors

No protected family may regress beyond static holdout floor.

### 14.8 Gate 8 - holdout cross-family evidence

Use holdout static metrics to recompute:

- improved families,
- nonprotected improved families,
- target subset pass.

These are the promotion-truth family coverage values.

### 14.9 Gate 9 - holdout transfer and robustness for A

For `A` candidates only:

- weighted transfer holdout delta must be >= `holdout_transfer_margin_bpb`,
- weighted robustness holdout delta must be >= `holdout_robust_margin_bpb`,
- no protected family transfer or robustness floor failures.

### 14.10 Gate 10 - warm bridge / anchor

For `A` candidates only:

- pass existing Phase 1 warm refinement checks,
- pass anchor non-regression using family-aware anchor aggregation.

### 14.11 Gate 11 - stability

Improvement must persist across:

- multiple holdout shards,
- multiple deterministic replay seeds where applicable,
- family partitions.

### 14.12 Gate 12 - canary and activation

If the candidate is `A` and judged risky by config, run shadow canary before activation. Then atomically:

- update `active_candidate`,
- update `rollback_candidate`,
- update `active_constellation` only if changed,
- write activation receipt.

### 14.13 Judge pseudocode

```python
def judge_phase2(candidate, incumbent, constellation):
    verify_protocol(candidate, constellation)

    public = load_constellation_receipts(candidate, "public")
    if not clears_public_static_margin(public):
        return reject("NoPublicStaticMargin")

    if not public.protected_floor_pass:
        return reject("ProtectedFamilyRegress")

    if not public_family_coverage_pass(public):
        return reject("InsufficientCrossFamilyEvidence")

    if candidate.promotion_class == "A":
        if not public_transfer_and_robust_pass(candidate):
            return reject("TransferOrRobustnessFail")

    holdout = load_constellation_receipts(candidate, "holdout")
    if not clears_holdout_static_margin(holdout):
        return reject("NoHoldoutStaticMargin")

    if not holdout.protected_floor_pass:
        return reject("ProtectedFamilyRegress")

    if not holdout_family_coverage_pass(holdout):
        return reject("InsufficientCrossFamilyEvidence")

    if candidate.promotion_class == "A":
        if not holdout_transfer_and_robust_pass(candidate):
            return reject("TransferOrRobustnessFail")
        if not pass_warm_refinement(candidate):
            return reject("WarmRefinementFail")

    if not passes_stability(candidate):
        return reject("StabilityFail")

    if requires_canary(candidate):
        if not survives_canary(candidate):
            return reject("CanaryFail")

    return promote("Pass")
```

---

## 15. Orchestrator algorithm

Phase 2 evaluation must be staged to stay within compute and memory budgets.

### 15.1 Epoch flow

```python
def phase2_epoch(active, snapshot, constellation, budgets):
    error_atlas = update_family_error_atlas(active, constellation)
    witnesses = build_family_balanced_witnesses(error_atlas, constellation)

    truth_pool = run_truth_lane_phase2(active, witnesses, constellation, budgets.truth)
    eq_pool = run_equivalence_lane_phase2(active, witnesses, constellation, budgets.equivalence)
    inc_pool = run_incubator_lane_phase2(active, witnesses, constellation, budgets.incubator)

    candidates = compile_verify_bound(truth_pool + eq_pool + inc_pool)

    witness_survivors = witness_prefilter_family_balanced(candidates, witnesses)

    public_static = evaluate_static_public(witness_survivors, constellation)
    static_survivors = admit_transfer_public(public_static)

    public_transfer = evaluate_transfer_public(static_survivors, constellation)
    public_robust = evaluate_robust_public(static_survivors, constellation)

    holdout_static_admissions = admit_holdout_static(
        public_static,
        public_transfer,
        public_robust
    )

    holdout_static = evaluate_static_holdout(holdout_static_admissions, constellation)
    xfer_robust_admissions = admit_holdout_xfer_robust(holdout_static)

    holdout_transfer = evaluate_transfer_holdout(xfer_robust_admissions, constellation)
    holdout_robust = evaluate_robust_holdout(xfer_robust_admissions, constellation)

    judged = []
    for cand in holdout_static_admissions:
        receipt = judge_phase2(cand, active, constellation)
        if receipt.pass_:
            judged.append((cand, receipt))

    survivors = run_phase2_canary(judged, constellation)
    best = select_best_phase2_lexicographically(survivors)

    if best is not None:
        activate_atomically(best)

    update_phase2_archives()
```

### 15.2 Admission budgets

Use these staged public and holdout budgets:

```text
up to 32 candidates -> public static
top 12 -> public transfer
top 12 -> public robust
top 6 -> holdout static
top 4 A-candidates -> holdout transfer and holdout robust
```

`S` candidates may skip transfer and robust evaluation entirely.

### 15.3 Lexicographic final selection

If multiple candidates pass, choose by:

1. lower weighted static holdout score,
2. higher improved-family count,
3. higher nonprotected improved-family count,
4. lower weighted transfer holdout score if class `A`,
5. lower weighted robustness holdout score if class `A`,
6. lower code penalty,
7. lower predicted hardware risk.

Hardware risk remains a tie-breaker only. It is never a promotion gate by itself.

---

## 16. CLI behavior

### 16.1 `apfsc_build_constellation`

Inputs:

- snapshot hash,
- list of admitted reality pack hashes,
- Phase 2 config file.

Outputs:

- `ConstellationManifest`,
- one `FamilyBankManifest` per family,
- active constellation pointer update.

### 16.2 `apfsc_transfer_eval`

Inputs:

- candidate hash,
- incumbent hash,
- snapshot hash,
- constellation id,
- mode `public` or `holdout`.

Outputs:

- transfer receipt with per-family adapted metrics and weighted score.

### 16.3 `apfsc_robust_eval`

Inputs:

- candidate hash,
- incumbent hash,
- snapshot hash,
- constellation id,
- mode `public` or `holdout`.

Outputs:

- robustness receipt with per-family metrics and weighted score.

### 16.4 `apfsc_epoch_run`

Extend the Phase 1 binary with:

```text
--profile phase1|phase2
--constellation <constellation_id>     # optional, defaults to active_constellation
```

In `phase2` mode it must run the staged static -> transfer -> robust -> holdout flow defined above.

---

## 17. Config schema

Add a dedicated Phase 2 profile section to TOML.

```toml
[phase2]
enabled = true
profile_name = "phase2"
constellation_required = true
min_improved_families = 2
min_nonprotected_improved_families = 1
require_target_subset_hit = true
target_subset = ["det_micro", "sensor_temporal", "phys_sim"]

[phase2.normalization]
codelen_ref_bytes = 4096
transfer_ref_bytes = 4096
public_static_margin_bpb = 0.001
holdout_static_margin_bpb = 0.001
holdout_transfer_margin_bpb = 0.0
holdout_robust_margin_bpb = 0.0

[phase2.weights.det_micro]
static_weight = 0.25
transfer_weight = 0.25
robust_weight = 0.25

[phase2.weights.text_code]
static_weight = 0.25
transfer_weight = 0.25
robust_weight = 0.25

[phase2.weights.sensor_temporal]
static_weight = 0.25
transfer_weight = 0.25
robust_weight = 0.25

[phase2.weights.phys_sim]
static_weight = 0.25
transfer_weight = 0.25
robust_weight = 0.25

[phase2.floors.det_micro]
protected = true
max_static_regress_bpb = 0.001
max_transfer_regress_bpb = 0.002
max_robust_regress_bpb = 0.002
min_family_improve_bpb = 0.0005

[phase2.floors.text_code]
protected = true
max_static_regress_bpb = 0.001
max_transfer_regress_bpb = 0.002
max_robust_regress_bpb = 0.002
min_family_improve_bpb = 0.0005

[phase2.floors.sensor_temporal]
protected = false
max_static_regress_bpb = 0.002
max_transfer_regress_bpb = 0.003
max_robust_regress_bpb = 0.003
min_family_improve_bpb = 0.0005

[phase2.floors.phys_sim]
protected = false
max_static_regress_bpb = 0.002
max_transfer_regress_bpb = 0.003
max_robust_regress_bpb = 0.003
min_family_improve_bpb = 0.0005

[phase2.transfer]
steps = 64
lr = 0.03
eps = 1e-8
l2 = 1e-5
clip_grad = 1.0
batch_windows = 8
shuffle = false
max_fast_weight_bytes = 262144
max_delta_bits = 524288
reset_ephemeral_state = true
mutable_surfaces = ["nuisance_head", "residual_head", "resid_weights", "fast_weights"]
```

---

## 18. Acceptance tests

Implement these tests exactly.

### 18.1 `apfsc_phase2_constellation.rs`

Verify:

- four family groups ingest successfully,
- one deterministic constellation manifest is built,
- pack grouping by `family_id` and `RealityRole` is correct,
- active constellation pointer is updated atomically.

### 18.2 `apfsc_phase2_normalization.rs`

Verify:

- weighted static score uses family weights, not raw byte volume,
- code penalty is charged once,
- improved-family counting is deterministic.

### 18.3 `apfsc_phase2_transfer.rs`

Verify:

- transfer adaptation only mutates legal surfaces,
- delta bits are charged,
- exceeding delta budget causes deterministic reject,
- transfer receipts are replay-stable.

### 18.4 `apfsc_phase2_robustness.rs`

Verify:

- robustness evaluation uses no adaptation,
- public and holdout robust receipts differ only by panel source,
- protected-family robust floors are checked correctly.

### 18.5 `apfsc_phase2_judge.rs`

Verify:

- an `S` candidate can pass static-only gates,
- an `A` candidate must also pass transfer and robust gates,
- challenge-stub data is not loaded by judge in Phase 2.

### 18.6 `apfsc_phase2_specialist_reject.rs`

Construct a fixture candidate that strongly improves `det_micro` but regresses `sensor_temporal` and `phys_sim`. Verify judge rejects with either:

- `InsufficientCrossFamilyEvidence`, or
- `ProtectedFamilyRegress`, depending on exact fixture shape.

### 18.7 `apfsc_phase2_e2e.rs`

Run a one-epoch Phase 2 demo:

- ingest family packs,
- build constellation,
- seed incumbent,
- generate candidates,
- emit all public receipts,
- emit all holdout receipts,
- produce judge receipt,
- optionally canary,
- activate or reject deterministically.

---

## 19. Coding rules for codex

1. Preserve all Phase 1 public APIs unless a Phase 2 extension requires a field addition.
2. Centralize all Phase 2 formulas in `normalization.rs` so judge and tests use the same code path.
3. Keep deterministic ordering everywhere: family ids sorted lexicographically, window refs sorted by digest and start offset.
4. Do not add hidden randomness to transfer adaptation.
5. Do not add Python or external processes in judged execution.
6. Every receipt and manifest must carry protocol version, snapshot hash, and constellation id where relevant.
7. Keep family ids stable strings. Do not derive them from filenames at runtime.
8. If a family role is missing, fail closed at constellation-build time.
9. Do not leak challenge-stub windows or raw holdout traces into public search code.
10. Reuse Phase 1 archive files where appropriate, but add new archive streams rather than overloading unrelated ones.

---

## 20. Suggested implementation order

Implement in this order.

1. Extend types, config, and manifest parsing for family roles.
2. Add constellation manifest and builder.
3. Extend bank building for role-specific panel generation.
4. Add fixtures for the four family groups.
5. Add normalization formulas and receipt structs.
6. Add transfer adaptation and transfer eval.
7. Add robustness eval.
8. Extend public eval staging.
9. Extend judge gates.
10. Extend archives.
11. Extend orchestrator.
12. Write tests and demo fixtures.
13. Run one deterministic epoch and lock expected receipts.

---

## 21. Minimum viable demo sequence

The codex agent should make this exact demo runnable:

```text
cargo run --bin apfsc_seed_init -- --profile phase1
cargo run --bin apfsc_ingest_reality -- fixtures/apfsc/phase2/reality_f0_det_base
cargo run --bin apfsc_ingest_reality -- fixtures/apfsc/phase2/reality_f0_det_transfer
cargo run --bin apfsc_ingest_reality -- fixtures/apfsc/phase2/reality_f0_det_robust
...
cargo run --bin apfsc_build_constellation -- --config fixtures/apfsc/phase2/config/phase2.toml
cargo run --bin apfsc_epoch_run -- --profile phase2 --epochs 1
```

Expected behavior:

- constellation manifest created,
- family banks created,
- public static receipts emitted,
- public transfer and robust receipts emitted for survivors,
- holdout receipts emitted for admitted candidates,
- judge receipt emitted,
- candidate activated or rejected deterministically.

---

## 22. Definition of done

Phase 2 is complete only if all of the following are true:

1. four family groups exist in fixtures,
2. one deterministic constellation can be built from them,
3. weighted family-normalized static scoring is used for public and holdout,
4. transfer evaluation is bounded, charged, and deterministic,
5. robustness evaluation is deterministic and separate from transfer,
6. protected-family floors are enforced,
7. improved-family counting is enforced,
8. a one-family specialist is rejected,
9. an actually cross-family candidate can pass,
10. replay of the same one-epoch run reproduces the same receipts exactly.

---

## 23. Explicit deferrals

These belong to later phases. Do not start them in Phase 2.

- challenge as promotion truth,
- P-warm and P-cold,
- `ColdBoundaryPack`,
- shadow canary as mandatory for cold paradigms,
- full SCIR macro induction,
- backend abstraction beyond Phase 1 tiers,
- family-adaptive or learned weighting,
- search-law promotion,
- recombination or crossover,
- law archive as a promotion-relevant object.

---

## 24. Final implementation intent

Phase 2 is the point where APF-SC stops being a single-stream optimizer and becomes a real laboratory of reusable architecture. The codex agent should implement it as a disciplined extension of Phase 1, not a reinvention. The trusted plane stays fixed. The scoring atom stays byte-level MDL. The new ingredient is that promotion now requires evidence that the architecture helps across multiple family regimes, survives bounded transfer, and does not collapse under robustness variants. That is the minimum end-to-end substrate required before later phases can attempt genuine paradigm change.
