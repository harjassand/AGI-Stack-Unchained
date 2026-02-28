# APF-SC Phase 4 Final - Full End-to-End Implementation Specification

This document is the implementation contract for a codex agent. It extends the Phase 3 MVP from paradigm transition into the final one-node recursive architecture-science engine. The objective is no longer only to find better architecture candidates. The objective is to make the *research strategy itself* a judged mutable object while preserving an immutable protocol plane.

End to end in this phase means:

1. ingest and govern all five exogenous pack classes:
   - `RealityPack`
   - `PriorPack`
   - `SubstratePack`
   - `FormalPack`
   - `ToolPack`
2. build and rotate a deterministic family constellation with hidden challenge families and retirement policy,
3. extract a public `LawArchive` and distilled `LawTokens` from judged history,
4. run active branch portfolios with bounded credit and debt,
5. search over architectures across truth, equivalence, incubator, cold-frontier, recombination, and tool-shadow paths,
6. search over `SearchLawPack` candidates using only public features and bucketed judged outcomes,
7. judge architecture promotions on static, transfer, robustness, recent-family, hidden-challenge, bridge, and canary evidence,
8. judge search-law promotions on downstream judged yield per compute, not on raw holdout scalars,
9. atomically activate a new architecture candidate and/or a new search law,
10. keep challenge contents, holdout scalars, and the trusted protocol plane outside recursion permanently.

The Phase 4 completion condition is simple:

**APF-SC must become a fixed-protocol research laboratory whose mutable objects are architecture law and search law, with live external intake and no protocol drift.**

---

## 1. Hard constraints

Codex must follow these constraints exactly.

### 1.1 Phase 3 is a prerequisite

Assume the Phase 1, Phase 2, and Phase 3 contracts exist or are being implemented exactly as specified in:

- `apfsc_phase1_mvp_spec.md`
- `apfsc_phase2_mvp_spec.md`
- `apfsc_phase3_mvp_spec.md`

Phase 4 is the final extension layer. Do not redesign earlier semantics unless Phase 4 requires a mechanical extension.

### 1.2 Trusted substrate boundary

Treat the existing APF-v3 substrate in `baremetal_lgp` / `apf3` as immutable. Reuse existing facilities for:

- deterministic replay capsules and digests,
- content-addressed artifacts,
- atomic pointer writes,
- judge-only activation,
- fail-closed execution,
- rollback pointers,
- NativeBlock containment and scan if already present.

If actual names differ in the repo, adapt at the APF-SC boundary. Do not refactor APF-v3 core code.

### 1.3 Implement in Phase 4 now

Implement now:

- active `G` search-law promotion,
- `LawArchive` and `LawToken` distillation,
- hidden challenge families as active judged gates,
- challenge retirement and rotation,
- active `FormalPack` ingestion and tightening policy updates,
- active `ToolPack` ingestion and tool-shadow execution lane,
- `NeedToken` emission and plateau-triggered ingress requests,
- branch portfolios with deterministic credit and debt ledgers,
- bounded multi-parent recombination with two parents maximum,
- a morphology/QD archive used by the search law,
- `DependencyPack` pinning of tool/formal inputs used by discovery and public/canary execution,
- search-law offline replay evaluation,
- search-law live A/B branch trials,
- search-law activation via `active_search_law.json`,
- one full Phase 4 macro-epoch path on a single node.

### 1.4 Explicitly do not implement now

Do not implement now:

- protocol self-modification,
- judge self-editing,
- autonomous web browsing or self-directed external acquisition,
- distributed cluster execution,
- holdout truth on any backend other than the interpreter,
- unrestricted NativeBlock judged execution,
- more than two recombination parents,
- unrestricted macro recursion,
- autonomous admissibility loosening from `FormalPack`,
- direct consumption of raw holdout scalars or hidden challenge contents by a search law,
- online actuation in the physical world.

### 1.5 Mutable objects in Phase 4

Phase 4 supports two judged mutable objects.

#### A. Architecture candidates

These remain the Phase 3 classes:

- `S`: allowed
- `A`: allowed
- `PWarm`: allowed
- `PCold`: allowed

#### B. Search-law candidates

A separate judged object:

- `G`: allowed in Phase 4

Interpretation:

- architecture candidates rewrite the computational theory being scored,
- `G` rewrites the policy that allocates future discovery effort,
- `G` never changes the protocol plane,
- `G` is activated separately from the active architecture candidate.

### 1.6 Runtime envelope

Still target a single Apple-silicon machine with an effective 16 GiB protocol envelope.

Use these Phase 4 limits unless the repo already exposes stricter constants:

```text
RSS_HARD_LIMIT_BYTES                    = 12 GiB
RSS_ABORT_LIMIT_BYTES                   = 14 GiB
MAX_CONCURRENT_MAPPED_BYTES             = 2 GiB
SEGMENT_BYTES                           = 256 MiB
STATE_TILE_BYTES_MAX                    = 2 MiB

MAX_STATIC_PUBLIC_CANDIDATES            = 32
MAX_PARADIGM_PUBLIC_CANDIDATES          = 12
MAX_SEARCHLAW_PUBLIC_CANDIDATES         = 6
MAX_HOLDOUT_ADMISSIONS                  = 8
MAX_SEARCHLAW_AB_CANDIDATES             = 2
MAX_SEARCHLAW_AB_BRANCHES_PER_SIDE      = 4

MAX_PUBLIC_WORKERS                      = 2
MAX_INCUBATOR_WORKERS                   = 1
MAX_CANARY_WORKERS                      = 1
MAX_TOOL_SHADOW_WORKERS                 = 1

MAX_PORTFOLIO_BRANCHES                  = 8
MAX_BRANCH_LOCAL_DEBT_CREDITS           = 3
MAX_GLOBAL_DEBT_CREDITS                 = 8
MAX_IDLE_EPOCHS_BEFORE_CULL             = 3

MAX_HIDDEN_CHALLENGE_FAMILIES           = 4
MAX_CHALLENGE_WINDOWS_PER_FAMILY        = 256
CHALLENGE_RETIRE_AFTER_EPOCHS           = 8
HOLDOUT_RETIRE_AFTER_EPOCHS             = 12

MAX_NEEDTOKENS_PER_EPOCH                = 8
MAX_QD_CELLS                            = 128
MAX_RECOMBINATION_PARENTS               = 2
MAX_LAWTOKENS_PER_EPOCH                 = 128
MAX_LAWARCHIVE_IN_MEMORY_RECORDS        = 50000

SEARCHLAW_MIN_AB_EPOCHS                 = 2
SEARCHLAW_MAX_AB_EPOCHS                 = 4
SEARCHLAW_REQUIRED_YIELD_IMPROVEMENT    = 0.20
SEARCHLAW_MAX_SAFETY_REGRESSION         = 0.00
```

The judged path must remain deterministic and pageout-free.

---

## 2. What success means

Phase 4 is done when all of the following are true:

1. `cargo test` passes for all Phase 1, Phase 2, Phase 3, and Phase 4 tests.
2. All five pack types can be ingested with deterministic receipts.
3. Hidden challenge families can be sealed, judged, retired, and replaced deterministically.
4. `LawArchive` records and `LawTokens` are emitted from judged history.
5. At least one `SearchLawPack` candidate can pass offline replay evaluation.
6. At least one `SearchLawPack` candidate can complete a live A/B branch trial against the incumbent search law.
7. A bounded two-parent recombination candidate can be materialized and verified.
8. A branch can receive credit, borrow debt, fail to repay, and be culled deterministically.
9. A `FormalPack` can tighten admissibility and cause a previously discovery-admissible proposal to be rejected.
10. A `ToolPack` can pass tool-shadow equivalence and become eligible for public/canary execution.
11. `apfsc_epoch_run --profile phase4 --epochs 2` produces deterministic receipts and either:
    - an architecture activation,
    - a search-law activation,
    - both,
    - or deterministic rejection.
12. Replay of the same macro-epoch run with the same snapshot, constellation, and active search law reproduces identical receipts.

A successful demo trace should look like:

```text
seed init
-> ingest all five pack kinds
-> build constellation with hidden challenges
-> extract law archive and law tokens
-> active search law emits portfolio plan and need tokens
-> run truth/equivalence/incubator/cold-frontier/recombination/tool-shadow branches
-> compile/verify/lower/backend-equivalence
-> public static/transfer/robust/fresh eval
-> holdout static/transfer/robust/fresh eval
-> hidden challenge gate
-> warm bridge or cold boundary
-> canary + rollback
-> activate architecture or reject
-> evaluate search-law candidates offline + A/B
-> activate search law or reject
-> rotate or retire hidden challenges
-> update archives, credits, qd cells, and active pointers
```

---

## 3. Repo delta to add or modify

Keep APF-v3 untouched. Extend the APF-SC tree from Phase 3.

### 3.1 New and modified modules

```text
src/apfsc/
  mod.rs                           (update exports)
  types.rs                         (extend search-law, portfolio, pack, challenge enums)
  config.rs                        (phase4 profile, search-law, challenge, portfolio constants)
  candidate.rs                     (dependency pack, recombination metadata)
  headpack.rs                      (no semantic change; add provenance fields only if needed)
  bridge.rs                        (extend receipts with challenge context)
  bank.rs                          (extend for hidden challenge windows and retirement metadata)
  constellation.rs                 (extend for hidden challenge roles and retirements)
  judge.rs                         (phase4 architecture + search-law gates)
  canary.rs                        (tool-shadow and architecture/search-law activation context)
  rollback.rs                      (reuse; extend only if needed)
  orchestrator.rs                  (phase4 macro-epoch flow)
  dependency_pack.rs               (new)
  law_archive.rs                   (new)
  law_tokens.rs                    (new)
  search_law.rs                    (new)
  searchlaw_eval.rs                (new)
  searchlaw_features.rs            (new)
  need.rs                          (new)
  challenge_scheduler.rs           (new)
  retirement.rs                    (new)
  portfolio.rs                     (new)
  credit.rs                        (new)
  recombination.rs                 (new)
  qd_archive.rs                    (new)
  tool_shadow.rs                   (new)
  formal_policy.rs                 (new)
  active.rs                        (new)
  yield_points.rs                  (new)

  scir/
    mod.rs
    ast.rs                         (reuse Phase 3)
    canonical.rs                   (reuse)
    lower.rs                       (reuse)
    verify.rs                      (extend with formal-policy deny/allow checks)
    interp.rs                      (reuse as holdout truth)
    egraph.rs                      (reuse)
    graph_backend.rs               (reuse)
    backend_equiv.rs               (extend for tool-shadow receipts)

  lanes/
    truth.rs                       (extend for search-law budget plans)
    equivalence.rs                 (extend for qd targets and law-token priors)
    incubator.rs                   (extend for portfolio attribution)
    cold_frontier.rs               (extend for branch credits/debt)
    recombination.rs               (new)
    tool_shadow.rs                 (new)

  ingress/
    mod.rs
    manifest.rs                    (extend pack kinds and reveal policies)
    judge.rs                       (extend import governance)
    reality.rs                     (extend challenge rotation metadata)
    prior.rs                       (reuse, minor schema extension)
    substrate.rs                   (reuse)
    formal.rs                      (new)
    tool.rs                        (new)
    receipts.rs                    (extend)

  archive/
    mod.rs                         (update exports)
    genealogy.rs                   (extend for multi-parent and law attribution)
    family_scores.rs               (reuse)
    transfer_trace.rs              (reuse)
    robustness_trace.rs            (reuse)
    error_atlas.rs                 (extend with challenge bins)
    paradigm_receipts.rs           (reuse)
    bridge_trace.rs                (reuse)
    backend_equiv.rs               (extend)
    macro_registry.rs              (reuse)
    canary_trace.rs                (reuse)
    law_archive.rs                 (new)
    qd_archive.rs                  (new)
    searchlaw_trace.rs             (new)
    portfolio_trace.rs             (new)
    challenge_retirement.rs        (new)
    need_tokens.rs                 (new)
    tool_shadow.rs                 (new)
    formal_policy.rs               (new)
```

### 3.2 New and modified binaries

```text
src/bin/
  apfsc_ingest_formal.rs               (new)
  apfsc_ingest_tool.rs                 (new)
  apfsc_rotate_challenges.rs           (new)
  apfsc_recombine.rs                   (new)
  apfsc_portfolio_step.rs              (new)
  apfsc_searchlaw_offline_eval.rs      (new)
  apfsc_searchlaw_ab.rs                (new)
  apfsc_tool_shadow.rs                 (new)

  apfsc_public_eval.rs                 (extend)
  apfsc_judge_daemon.rs                (extend)
  apfsc_shadow_canary.rs               (extend)
  apfsc_epoch_run.rs                   (extend with profile=phase4)
```

### 3.3 Fixtures and tests

Reuse Phase 3 fixtures and add the following.

```text
fixtures/apfsc/phase4/
  formal/
    deny_unbounded_gather/
      manifest.json
      policy.json
    exploit_regression_seed/
      manifest.json
      policy.json

  tools/
    tool_graph_shadow/
      manifest.json
      toolpack.json
      gold_traces.jsonl
    tool_nativeblock_shadow/
      manifest.json
      toolpack.json
      gold_traces.jsonl

  reality_challenge/
    f6_hidden_logic_challenge/
      manifest.json
      payload.bin
    f7_hidden_sparse_challenge/
      manifest.json
      payload.bin

  priors/
    recombination_seed/
      manifest.json
      rules.json
    searchlaw_seed/
      manifest.json
      searchlaw.json

  expected/
    phase4_formal_receipt.json
    phase4_tool_shadow_receipt.json
    phase4_searchlaw_offline_receipt.json
    phase4_searchlaw_ab_receipt.json
    phase4_searchlaw_promotion_receipt.json
    phase4_arch_promotion_receipt.json

  config/
    phase4.toml
```

Add tests:

```text
tests/
  apfsc_phase4_formal_pack.rs
  apfsc_phase4_tool_shadow.rs
  apfsc_phase4_hidden_challenge.rs
  apfsc_phase4_challenge_retirement.rs
  apfsc_phase4_law_archive.rs
  apfsc_phase4_law_tokens.rs
  apfsc_phase4_need_tokens.rs
  apfsc_phase4_portfolio_credit.rs
  apfsc_phase4_qd_archive.rs
  apfsc_phase4_recombination.rs
  apfsc_phase4_searchlaw_offline.rs
  apfsc_phase4_searchlaw_ab.rs
  apfsc_phase4_judge.rs
  apfsc_phase4_e2e_architecture.rs
  apfsc_phase4_e2e_searchlaw.rs
  apfsc_phase4_e2e_full_loop.rs
```

---

## 4. Phase 4 simplifications

These simplifications are intentional. Do not "improve" them away during implementation.

1. The interpreter remains the semantic source of truth for holdout and hidden challenge judgment.
2. Search laws are deterministic rule-based policies in Phase 4. Do not add deep RL, stochastic policy gradients, or black-box meta-learners.
3. `G` may consume only:
   - public bank statistics,
   - bucketed public outcomes,
   - bucketed judged outcomes,
   - public genealogy and law archive state,
   - public challenge coverage metadata,
   - public pack availability metadata.
4. `G` may not consume:
   - raw holdout scalar deltas,
   - raw hidden challenge scalar deltas,
   - hidden challenge contents,
   - raw canary traces.
5. Two-parent recombination is the maximum. No k-parent merge.
6. `ToolPack` may influence discovery, public evaluation, and canary after equivalence. It may not replace interpreter truth on holdout or hidden challenge.
7. `FormalPack` may tighten admissibility automatically after validation. It may not loosen rules autonomously.
8. Search-law A/B trials are branch-partitioned within a macro-epoch on one machine. Do not implement a distributed bandit system.
9. Need tokens are advisory outputs for external curation. They do not trigger autonomous browsing or ingestion.
10. Credits and debt govern exploration only. They never weaken promotion law.

---

## 5. On-disk artifact delta

Extend the Phase 3 artifact tree.

```text
artifacts/apfsc/
  snapshots/
    <snapshot_hash>/
      epoch_snapshot.json
      constellation_manifest.json
      hidden_challenge_manifest.json
      retirement_manifest.json
      input_ledger.json

  formal_policy/
    <formal_policy_hash>/
      policy.json
      admission_receipt.json
      validation_receipt.json

  toolpacks/
    <toolpack_hash>/
      toolpack.json
      admission_receipt.json
      gold_equiv_receipt.json
      canary_equiv_receipt.json
      microbench_receipt.json

  law_archive/
    <law_archive_hash>/
      records.jsonl
      tokens.jsonl
      feature_cache.json
      summary.json

  search_laws/
    <searchlaw_hash>/
      manifest.json
      feature_schema.json
      rule_table.json
      offline_eval_receipt.json
      ab_eval_receipt.json
      promotion_receipt.json

  portfolios/
    <portfolio_id>/
      manifest.json
      branches.jsonl
      credit_ledger.jsonl
      debt_ledger.jsonl
      cull_receipts.jsonl

  qd_archive/
    <qd_archive_hash>/
      cells.jsonl
      occupancy.json
      replacement_receipts.jsonl

  challenges/
    <challenge_set_hash>/
      hidden_manifest.json
      retirement_receipts.jsonl
      exposure_ledger.jsonl

  candidates/
    <candidate_hash>/
      manifest.json
      build_meta.json
      paradigm_signature.json
      dependency_pack.json
      recombination_spec.json          (optional)
      scir_v2.json
      scir_canonical.json
      scir_lowered.json
      schedule_pack.json
      backend_plan.json
      headpack.json
      bridgepack.json
      compile_receipt.json
      backend_equiv_receipt.json       (optional)
      tool_shadow_receipt.json         (optional)
      static_public_receipt.json
      transfer_public_receipt.json
      robust_public_receipt.json
      fresh_public_receipt.json
      holdout_receipt.json
      challenge_receipt.json
      bridge_receipt.json
      canary_receipt.json              (optional)
      promotion_receipt.json

  active/
    active_candidate.json
    rollback_candidate.json
    active_constellation.json
    active_snapshot.json
    active_search_law.json
    active_formal_policy.json

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
    law_archive.jsonl
    qd_archive.jsonl
    searchlaw_trace.jsonl
    portfolio_trace.jsonl
    challenge_retirement.jsonl
    need_tokens.jsonl
    tool_shadow.jsonl
    formal_policy.jsonl
```

Rules:

- all artifact directories remain content-addressed,
- every receipt must carry `protocol_version`, `snapshot_hash`, and `constellation_id`,
- `challenge_receipt.json` is mandatory for Phase 4 architecture promotions,
- `promotion_receipt.json` remains authoritative for architecture and search-law activation decisions,
- `active_search_law.json` is separate from `active_candidate.json`,
- search-law activations never overwrite the active architecture pointer,
- `dependency_pack.json` must pin all non-protocol external inputs used by the candidate.

---

## 6. Core data contracts

Implement these contracts directly in Rust. Field names may be adapted to repo style, but semantics must remain unchanged.

### 6.1 Extended enums

```rust
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum SearchObjectKind {
    Architecture,
    SearchLaw,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum PromotionClass {
    S,
    A,
    PWarm,
    PCold,
    G,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum PackKind {
    Reality,
    Prior,
    Substrate,
    Formal,
    Tool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum ChallengeRole {
    HiddenGeneralization,
    HiddenIntervention,
    HiddenFreshness,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum ToolShadowStatus {
    Quarantined,
    GoldEquivalent,
    CanaryEquivalent,
    DiscoveryOnly,
    PublicCanaryEligible,
    Rejected,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum NeedBucket {
    Reality,
    Prior,
    Substrate,
    Formal,
    Tool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum BranchStatus {
    Active,
    Shadow,
    Debt,
    Culled,
    Promoted,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum SearchLawPolicyKind {
    RuleTableV1,
}
```

### 6.2 Dependency pack and provenance

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DependencyPack {
    pub snapshot_hash: String,
    pub prior_roots: Vec<String>,
    pub tool_roots: Vec<String>,
    pub formal_policy_hash: String,
    pub substrate_roots: Vec<String>,
    pub macro_registry_hash: String,
    pub manifest_hash: String,
}
```

Rules:

- every Phase 4 candidate must carry a `DependencyPack`,
- if a `ToolPack` influences public/canary execution, its hash must appear here,
- holdout truth must remain reproducible without the `ToolPack`.

### 6.3 Hidden challenge contracts

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HiddenChallengeFamily {
    pub family_id: String,
    pub role: ChallengeRole,
    pub source_pack_hash: String,
    pub window_commit_hash: String,
    pub reveal_epoch: u64,
    pub retire_after_epoch: u64,
    pub protected: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HiddenChallengeManifest {
    pub constellation_id: String,
    pub snapshot_hash: String,
    pub active_hidden_families: Vec<HiddenChallengeFamily>,
    pub retired_hidden_families: Vec<String>,
    pub manifest_hash: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChallengeReceipt {
    pub candidate_hash: String,
    pub incumbent_hash: String,
    pub family_bucket_passes: std::collections::BTreeMap<String, bool>,
    pub aggregate_bucket_score: i32,
    pub catastrophic_regression: bool,
    pub pass: bool,
    pub reason: String,
}
```

### 6.4 Formal policy contracts

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FormalRule {
    pub rule_id: String,
    pub severity: String,
    pub scope: String,
    pub pattern_hash: String,
    pub action: String,  // deny | allow | require_receipt
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FormalPolicy {
    pub policy_id: String,
    pub version: u32,
    pub rules: Vec<FormalRule>,
    pub source_pack_hashes: Vec<String>,
    pub manifest_hash: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FormalPackAdmissionReceipt {
    pub pack_hash: String,
    pub policy_hash: String,
    pub validated: bool,
    pub tightened_rules_only: bool,
    pub applied: bool,
    pub reason: String,
}
```

### 6.5 Tool shadow contracts

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolPack {
    pub tool_id: String,
    pub version: String,
    pub backend_kind: String,
    pub entrypoints: Vec<String>,
    pub dependency_digests: Vec<String>,
    pub manifest_hash: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolShadowReceipt {
    pub toolpack_hash: String,
    pub candidate_hash: Option<String>,
    pub gold_exact_match: bool,
    pub canary_exact_match: bool,
    pub deterministic_replay: bool,
    pub peak_rss_bytes: u64,
    pub status: ToolShadowStatus,
    pub reason: String,
}
```

### 6.6 Law archive contracts

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LawArchiveRecord {
    pub record_id: String,
    pub candidate_hash: String,
    pub parent_hashes: Vec<String>,
    pub searchlaw_hash: String,
    pub promotion_class: PromotionClass,
    pub source_lane: String,
    pub family_outcome_buckets: std::collections::BTreeMap<String, i8>,
    pub challenge_bucket: i8,
    pub canary_survived: bool,
    pub yield_points: i32,
    pub compute_units: u64,
    pub morphology_hash: String,
    pub qd_cell_id: String,
    pub snapshot_hash: String,
    pub constellation_id: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LawToken {
    pub token_id: String,
    pub token_kind: String,
    pub support_count: u32,
    pub mean_yield_points: f64,
    pub mean_compute_units: f64,
    pub conditioned_on: std::collections::BTreeMap<String, String>,
    pub payload_hash: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LawArchiveSummary {
    pub total_records: u64,
    pub total_tokens: u64,
    pub active_searchlaw_hash: String,
    pub dominant_failure_modes: Vec<String>,
    pub underfilled_qd_cells: Vec<String>,
    pub stale_family_ids: Vec<String>,
}
```

### 6.7 Need token contracts

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NeedToken {
    pub token_id: String,
    pub need_bucket: NeedBucket,
    pub priority_q16: u32,
    pub requested_family_shape: String,
    pub justification_codes: Vec<String>,
    pub originating_searchlaw_hash: String,
    pub epoch_id: u64,
}
```

Allowed `justification_codes` in Phase 4:

- `plateau_judged_yield`
- `stale_hidden_challenge`
- `family_gap`
- `tool_bottleneck`
- `formal_gap`
- `substrate_drift`
- `qd_hole`
- `fresh_family_gap`

### 6.8 Portfolio and credit contracts

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BranchRecord {
    pub branch_id: String,
    pub parent_branch_id: Option<String>,
    pub owner_searchlaw_hash: String,
    pub assigned_lane: String,
    pub assigned_family_targets: Vec<String>,
    pub assigned_class_targets: Vec<PromotionClass>,
    pub assigned_qd_targets: Vec<String>,
    pub credit_balance: i32,
    pub debt_balance: i32,
    pub idle_epochs: u32,
    pub status: BranchStatus,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CreditLedgerEntry {
    pub entry_id: String,
    pub branch_id: String,
    pub delta_credits: i32,
    pub reason: String,
    pub candidate_hash: Option<String>,
    pub promotion_hash: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PortfolioManifest {
    pub portfolio_id: String,
    pub snapshot_hash: String,
    pub constellation_id: String,
    pub active_searchlaw_hash: String,
    pub total_credit_supply: i32,
    pub total_debt_outstanding: i32,
    pub branch_ids: Vec<String>,
}
```

Rules:

- credits are minted only by judged architecture promotions and judged search-law promotions,
- debt may finance discovery-side public work only,
- holdout and hidden challenge costs are judge-owned and do not reduce branch credit balances,
- a branch that exceeds debt cap or idles too long is culled.

### 6.9 Recombination and QD contracts

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RecombinationSpec {
    pub parent_candidate_hashes: Vec<String>,
    pub parent_contribution_ranges: std::collections::BTreeMap<String, Vec<String>>,
    pub merge_mode: String,  // block_swap | head_merge | macro_mix
    pub compatibility_hash: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MorphologyDescriptor {
    pub paradigm_signature_hash: String,
    pub scheduler_class: String,
    pub memory_law_kind: String,
    pub macro_density_bin: String,
    pub state_bytes_bin: String,
    pub family_profile_bin: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct QdCellRecord {
    pub cell_id: String,
    pub descriptor: MorphologyDescriptor,
    pub occupant_candidate_hash: String,
    pub public_quality_score: f64,
    pub novelty_score: f64,
    pub last_updated_epoch: u64,
}
```

### 6.10 Search-law contracts

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchLawPack {
    pub law_id: String,
    pub parent_law_hash: Option<String>,
    pub policy_kind: SearchLawPolicyKind,
    pub feature_schema_version: String,
    pub lane_weights_q16: std::collections::BTreeMap<String, u32>,
    pub class_weights_q16: std::collections::BTreeMap<String, u32>,
    pub family_weights_q16: std::collections::BTreeMap<String, u32>,
    pub qd_explore_rate_q16: u32,
    pub recombination_rate_q16: u32,
    pub fresh_family_bias_q16: u32,
    pub need_rules_hash: String,
    pub debt_policy_hash: String,
    pub manifest_hash: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchLawFeatureVector {
    pub active_family_ids: Vec<String>,
    pub stale_family_ids: Vec<String>,
    pub underfilled_qd_cells: Vec<String>,
    pub dominant_failure_modes: Vec<String>,
    pub recent_public_yield_buckets: std::collections::BTreeMap<String, i32>,
    pub recent_judged_yield_points: i32,
    pub recent_compute_units: u64,
    pub recent_canary_failures: u32,
    pub recent_challenge_failures: u32,
    pub public_plateau_epochs: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchPlan {
    pub architecture_branch_budgets: Vec<(String, i32)>,
    pub lane_budget_q16: std::collections::BTreeMap<String, u32>,
    pub class_budget_q16: std::collections::BTreeMap<String, u32>,
    pub family_budget_q16: std::collections::BTreeMap<String, u32>,
    pub qd_target_cells: Vec<String>,
    pub recombination_pairs: Vec<(String, String)>,
    pub need_tokens: Vec<NeedToken>,
}
```

### 6.11 Search-law evaluation contracts

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchLawOfflineReceipt {
    pub searchlaw_hash: String,
    pub replay_records_used: u64,
    pub projected_yield_points: i32,
    pub projected_compute_units: u64,
    pub projected_yield_per_compute: f64,
    pub pass: bool,
    pub reason: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchLawAbReceipt {
    pub candidate_searchlaw_hash: String,
    pub incumbent_searchlaw_hash: String,
    pub ab_epochs: u32,
    pub incumbent_yield_points: i32,
    pub candidate_yield_points: i32,
    pub incumbent_compute_units: u64,
    pub candidate_compute_units: u64,
    pub incumbent_yield_per_compute: f64,
    pub candidate_yield_per_compute: f64,
    pub challenge_regression: bool,
    pub safety_regression: bool,
    pub pass: bool,
    pub reason: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchLawPromotionReceipt {
    pub candidate_searchlaw_hash: String,
    pub incumbent_searchlaw_hash: String,
    pub decision: String,
    pub reason: String,
    pub ab_receipt_hash: String,
    pub applied: bool,
}
```

### 6.12 Architecture promotion receipt extension

Keep Phase 3 `PromotionReceipt` and add these fields:

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Phase4PromotionExtension {
    pub challenge_receipt_hash: String,
    pub searchlaw_hash: String,
    pub branch_id: String,
    pub yield_points: i32,
    pub qd_cell_id: String,
    pub dependency_pack_hash: String,
}
```

---

## 7. The active five-bucket ingress plane

Phase 4 activates all five pack buckets as live recursive inputs.

### 7.1 Pack behavior table

| Pack kind      | First consumer                      | Phase 4 role                                               | Autonomy level |
| -------------- | ----------------------------------- | ---------------------------------------------------------- | -------------- |
| `RealityPack`  | bank / constellation builder        | new train/public/holdout/challenge/canary families         | auto-admissible after protocol validation |
| `PriorPack`    | equivalence/incubator/frontier      | new ops, rewrites, learning laws, macro motifs             | discovery only until matured |
| `SubstratePack`| hardware oracle / scheduler         | new empirical device traces and calibration                | ranking only, never truth |
| `FormalPack`   | verifier / import judge             | tightened admissibility, exploit regressions, deny rules   | auto-tightening only |
| `ToolPack`     | tool-shadow lane                    | new compiler/kernel/backend options for discovery/public/canary | discovery and public/canary after equivalence |

### 7.2 Import protocol

Every pack follows this path:

1. acquire,
2. canonicalize,
3. content-address,
4. quarantine,
5. validate bucket-specific obligations,
6. split reveal slices if needed,
7. commit to `input_ledger`,
8. publish immutable receipt.

### 7.3 Phase 4 import rules

#### A. `RealityPack`

Must be split before reveal into:

- train,
- public,
- holdout,
- hidden challenge,
- canary.

Holdout and hidden challenge contents are committed before any reveal.

#### B. `PriorPack`

Must include one of:

- symbolic equivalence proof,
- deterministic lowering proof into SCIR-v2 core,
- or a differential test harness plus bounds proof.

#### C. `SubstratePack`

May update:

- `SiliconOracle`,
- backend eligibility rankings,
- schedule priors.

It may not alter promotion truth.

#### D. `FormalPack`

Must validate as *tightening-only*:

- new deny patterns,
- new required receipts,
- new exploit regression tests.

It may not remove existing constraints autonomously.

#### E. `ToolPack`

Must pass:

- gold-trace exact equivalence,
- deterministic replay,
- bounded-memory microbench,
- optional canary equivalence.

Only then may it move from `Quarantined` to `PublicCanaryEligible`.

### 7.4 Need-token emission

The search law may emit need tokens when:

- judged yield plateaus,
- challenge families go stale,
- QD holes persist,
- family coverage gaps appear,
- tool/formal/substrate bottlenecks appear.

Need tokens are written as artifacts and archive records. They are requests for future external curation. They do not trigger autonomous browsing.

---

## 8. Hidden challenge families and retirement

Phase 4 activates hidden challenge families as judged gates.

### 8.1 Challenge policy

Each active constellation must carry:

- static public families,
- holdout families,
- fresh families,
- hidden challenge families.

Hidden challenge families are never visible to discovery in raw form.

### 8.2 Challenge pass rule

All architecture promotions must satisfy:

1. no catastrophic regression on any protected hidden challenge family,
2. aggregate challenge bucket score >= configured floor,
3. no hidden challenge failure streak beyond configured maximum.

### 8.3 Bucketed challenge scoring

Use bucketed judged outcomes, not raw exposed deltas.

Recommended bucket map:

```text
StrongGain        = +2
WeakGain          = +1
Flat              =  0
WeakRegress       = -1
StrongRegress     = -2
Catastrophic      = fail immediately
```

### 8.4 Retirement and rotation

A hidden challenge family must be retired when any of the following are true:

- it reaches `CHALLENGE_RETIRE_AFTER_EPOCHS`,
- it has been judged enough times to risk memorization,
- a new `RealityPack` provides a stronger replacement in the same role.

Retired challenge families remain archived but cannot continue gating new promotions.

### 8.5 Rotation algorithm

```python
def rotate_hidden_challenges(snapshot, constellation, archive_summary):
    stale = select_stale_hidden_families(constellation)
    replacements = select_replacements(
        available_reality_packs=snapshot.reality_roots,
        missing_roles=roles_of(stale),
        blind_spots=archive_summary.dominant_failure_modes,
    )
    commit_replacement_manifest(stale, replacements)
```

---

## 9. Law archive and law-token distillation

Phase 4 introduces judged history as a reusable public research memory.

### 9.1 What enters the law archive

Every architecture promotion or judged rejection appends a `LawArchiveRecord` containing:

- class,
- source lane,
- parent lineage,
- family bucket outcomes,
- challenge bucket,
- canary result,
- yield points,
- compute units,
- morphology hash,
- QD cell,
- active search law attribution.

### 9.2 Law-token distillation

A `LawToken` is a compressed pattern mined from the archive.

Examples:

- "ring_slots + block_scan + event_sparse families -> above-average yield under low compute"
- "macro_mix recombinations fail on hidden intervention challenge"
- "tool-shadow backend helps public throughput but predicts canary drift in one morphology bin"

Do not implement free-form language generation. Encode tokens as deterministic structured payloads.

### 9.3 Distillation algorithm

```python
def distill_law_tokens(records):
    grouped = bucket_by_morphology_lane_class(records)
    tokens = []
    for key, rs in grouped.items():
        if support(rs) < MIN_TOKEN_SUPPORT:
            continue
        token = LawToken(
            token_id=hash_key(key, rs),
            token_kind=infer_token_kind(key),
            support_count=len(rs),
            mean_yield_points=mean(r.yield_points for r in rs),
            mean_compute_units=mean(r.compute_units for r in rs),
            conditioned_on=extract_conditions(key, rs),
            payload_hash=hash_payload(key, rs),
        )
        tokens.append(token)
    return sort_tokens(tokens)
```

### 9.4 Archive visibility

The search law may read:

- `LawToken`s,
- `LawArchiveSummary`,
- bucketed public and judged outcomes.

It may not read raw holdout scalar traces or hidden challenge contents.

---

## 10. SearchLawPack and active G promotion

This is the core Phase 4 addition.

### 10.1 Search-law purpose

A `SearchLawPack` chooses how to spend future exploration budget:

- lane quotas,
- class quotas,
- family quotas,
- QD targets,
- recombination frequency,
- need-token issuance,
- branch debt policy,
- public compute allocation.

### 10.2 Search-law representation

Phase 4 uses a deterministic rule-table policy.

Do not implement a learned neural controller.

A search law computes:

```text
SearchPlan = f(
  SearchLawFeatureVector,
  LawTokens,
  active constellation metadata,
  public plateau state,
  qd occupancy,
  branch credit/debt state
)
```

### 10.3 Search-law candidate generation

Generate search-law candidates by mutating the active rule table:

- reweight lane budgets,
- reweight class emphasis,
- reweight family targeting,
- adjust QD exploration rate,
- adjust recombination rate,
- adjust need-token thresholds,
- adjust debt caps within fixed safety bounds.

No mutation may alter the protocol plane.

### 10.4 Offline replay gate

A candidate search law must pass offline replay before live A/B.

Offline replay uses:

- historical `LawArchiveRecord`s,
- bucketed outcomes,
- feature snapshots,
- compute-unit traces.

Offline pass requires:

- projected yield per compute >= incumbent replay score,
- no predicted challenge or safety regression,
- deterministic replay of the same historical window.

### 10.5 Live A/B branch trial

If offline passes, run a live A/B branch trial.

Because this is a single-node system, use **branch partitioning**:

- the incumbent search law controls half the available branch budget,
- the candidate search law controls the other half,
- both operate in the same macro-epoch,
- both begin from the same active candidate and same snapshot,
- architecture promotions from either side may still activate if they pass the judge,
- yield attribution is by branch ownership.

### 10.6 Search-law promotion metric

Search laws are judged on downstream yield per compute.

Use:

```text
YieldPerCompute = Sum(YieldPoints) / Sum(ComputeUnits)
```

Where:

- `YieldPoints` are judge-minted integer points from successful architecture promotions,
- `ComputeUnits` are deterministic normalized public/discovery units,
- raw holdout scalar deltas are not exposed to the search law.

Recommended yield-point schedule:

```text
S success       = 1 point
A success       = 2 points
PWarm success   = 3 points
PCold success   = 4 points
Challenge bonus = +1 point if hidden challenge bucket is positive
Canary fail     = 0 points
Rejected        = 0 points
```

### 10.7 Search-law promotion rule

Promote `G` only if all are true:

1. offline replay pass,
2. live A/B pass for `SEARCHLAW_MIN_AB_EPOCHS .. SEARCHLAW_MAX_AB_EPOCHS`,
3. candidate yield per compute >= incumbent yield per compute * `(1 + SEARCHLAW_REQUIRED_YIELD_IMPROVEMENT)`,
4. no safety regression,
5. no challenge regression,
6. deterministic receipts reproduced.

### 10.8 Search-law activation

If `G` passes, atomically update:

- `active_search_law.json`

Do not update `active_candidate.json` as part of the same file write. Separate activations are required even if both happen in one macro-epoch.

---

## 11. Branch portfolios and credit/debt economy

Phase 4 activates branch portfolios as the exploration budget mechanism.

### 11.1 Credit minting

Credits are minted only from judged improvement:

- architecture promotion success,
- search-law promotion success.

No other source may mint credits.

### 11.2 Credit spending

Credits may be spent on:

- more microcandidates in a lane,
- deeper incubator updates,
- additional recombination proposals,
- more public evaluation windows,
- search-law shadow evaluation,
- macro induction.

### 11.3 Debt

Debt is branch-local and discovery-only.

Rules:

- debt cannot relax admissibility,
- debt cannot buy holdout truth,
- debt cannot buy hidden challenge exposure,
- debt expires after `MAX_IDLE_EPOCHS_BEFORE_CULL`,
- a branch that fails to repay is culled.

### 11.4 Portfolio scheduler

The active search law emits a `SearchPlan` that allocates branch budgets.

Algorithm:

```python
def allocate_branch_budget(portfolio, search_plan):
    for branch in sort_branches(portfolio):
        assign_lane(branch, search_plan)
        assign_family_targets(branch, search_plan)
        assign_class_targets(branch, search_plan)
        assign_qd_targets(branch, search_plan)
        assign_credit_or_debt(branch, search_plan)
```

### 11.5 Culling rule

Cull a branch if any are true:

- debt exceeds `MAX_BRANCH_LOCAL_DEBT_CREDITS`,
- idle epochs exceed `MAX_IDLE_EPOCHS_BEFORE_CULL`,
- repeated challenge or canary failures make the branch nonproductive,
- the active search law marks the branch as dominated and the judge confirms no pending judged candidates exist.

---

## 12. Multi-parent recombination and QD archive

Phase 4 activates bounded lineage recombination and diversity preservation.

### 12.1 Recombination eligibility

A recombination candidate may be proposed only when:

- exactly two parent candidates are selected,
- both parents are from the same snapshot lineage or compatible dependency pack,
- formal policy permits all merged ops,
- compatibility hash passes.

### 12.2 Allowed recombination modes

Implement only:

- `block_swap`
- `head_merge`
- `macro_mix`

Do not implement arbitrary graph crossover.

### 12.3 Recombination receipt rules

Every recombination proposal must emit:

- parent hashes,
- contribution ranges,
- compatibility hash,
- formal-policy pass/fail,
- compile receipt.

### 12.4 QD archive role

The QD archive stores one strong occupant per morphology cell.

Cell axes:

- scheduler class,
- memory law,
- macro density,
- state-bytes bin,
- family-profile bin.

The search law uses:

- underfilled cells,
- stagnating cells,
- highly productive cells,

to target future exploration.

### 12.5 Recombination + QD coupling

The search law may preferentially recombine parents from:

- adjacent productive cells,
- one productive + one underexplored cell,
- one incumbent lineage + one challenge-strong lineage.

This is how Phase 4 preserves multiple viable basins rather than one incumbent line.

---

## 13. Tool shadow lane and FormalPack activation

### 13.1 FormalPack activation

After validation, a `FormalPack` may tighten:

- SCIR verifier deny patterns,
- required backend-equivalence receipts,
- required canary levels,
- specific exploit regression tests.

Mechanically, implement this as a `FormalPolicy` digest loaded into:

- `ingress/judge.rs`
- `scir/verify.rs`
- `judge.rs`

### 13.2 Tool shadow lane

A `ToolPack` enters the tool-shadow lane before it can influence public/canary execution.

The tool-shadow lane must perform:

1. gold-trace exact equivalence,
2. deterministic replay checks,
3. bounded-memory microbench,
4. optional canary equivalence.

If the tool passes, it may be used for:

- discovery acceleration,
- public execution,
- canary execution.

It may not replace holdout truth.

### 13.3 NativeBlock policy

If the repo already supports NativeBlock containment, Phase 4 may use a NativeBlock-based tool only in the tool-shadow lane and public/canary execution after equivalence. It remains forbidden as holdout truth.

### 13.4 Tool fallback

If tool-shadow equivalence fails:

- mark tool `Rejected`,
- fall back to interpreter or GraphBackend,
- do not silently continue with approximate execution.

---

## 14. Public, holdout, and challenge evaluation in Phase 4

### 14.1 Architecture public staging

Public evaluation order:

1. witness prefilter,
2. static public families,
3. transfer public families,
4. robustness public families,
5. fresh public families,
6. optional tool-shadow public acceleration for eligible candidates.

### 14.2 Holdout staging

Holdout evaluation order remains:

1. static holdout,
2. transfer holdout,
3. robustness holdout,
4. fresh holdout,
5. hidden challenge gate,
6. bridge gate,
7. canary if required.

### 14.3 Search-law public staging

Search-law candidate evaluation order:

1. offline replay over archived features/outcomes,
2. live A/B branch trial,
3. judged activation.

### 14.4 Shared scoring rule

Architecture truth remains byte-level MDL under the Phase 1/2/3 rules.

Search-law truth is *downstream judged yield per compute*.

These are separate judged objects and must never be mixed.

---

## 15. Judge rules

The Phase 4 judge owns both architecture and search-law activation decisions.

### 15.1 Architecture judge sequence

For every admitted architecture candidate:

1. protocol validity,
2. formal-policy validity,
3. public margin,
4. holdout truth gain,
5. family floors,
6. transfer/robust/fresh gates,
7. hidden challenge gate,
8. warm bridge or cold boundary,
9. stability,
10. canary,
11. promotion receipt,
12. yield-point minting.

### 15.2 Search-law judge sequence

For every admitted search-law candidate:

1. protocol validity,
2. feature visibility audit,
3. forbidden-input audit,
4. offline replay gate,
5. live A/B gate,
6. safety regression gate,
7. challenge regression gate,
8. activation receipt.

### 15.3 Forbidden-input audit for G

Reject immediately if the candidate search law is wired to any source containing:

- raw holdout scalars,
- hidden challenge raw contents,
- raw canary traces,
- protocol-private judge fields.

### 15.4 Architecture challenge rule

Pseudo-rule:

```python
def pass_hidden_challenge(receipt):
    if receipt.catastrophic_regression:
        return False
    if receipt.aggregate_bucket_score < CHALLENGE_MIN_BUCKET_SCORE:
        return False
    return True
```

### 15.5 Yield-point minting

Only the judge may mint yield points.

Yield points must be integer, deterministic, and derived from the final judged architecture promotion receipt. They may then feed:

- `LawArchiveRecord`,
- credit minting,
- search-law A/B evaluation.

### 15.6 Activation ordering

If both an architecture candidate and a search law pass in the same macro-epoch:

1. write `rollback_candidate.json` if architecture activation is needed,
2. atomically activate the architecture candidate,
3. atomically activate the search law in a separate pointer write.

---

## 16. Orchestrator algorithm

Phase 4 introduces a macro-epoch with both architecture and search-law flows.

```python
def phase4_macro_epoch(active_candidate, active_searchlaw, snapshot, constellation, portfolio):
    load_formal_policy(snapshot)
    maybe_rotate_hidden_challenges(snapshot, constellation)

    law_archive = build_or_refresh_law_archive()
    law_tokens = distill_law_tokens(law_archive.records)
    feature_vector = build_searchlaw_features(
        active_candidate, active_searchlaw, constellation, law_archive, portfolio
    )

    search_plan = active_searchlaw.plan(feature_vector, law_tokens)
    emit_need_tokens(search_plan.need_tokens)
    allocate_branch_budget(portfolio, search_plan)

    arch_candidates = []
    arch_candidates += run_truth_lane(search_plan, portfolio)
    arch_candidates += run_equivalence_lane(search_plan, portfolio, law_tokens)
    arch_candidates += run_incubator_lane(search_plan, portfolio, law_tokens)
    arch_candidates += run_cold_frontier_lane(search_plan, portfolio, law_tokens)
    arch_candidates += run_recombination_lane(search_plan, portfolio)
    arch_candidates += run_tool_shadow_lane(search_plan, portfolio)

    verified = compile_verify_bound_equiv(arch_candidates, snapshot)
    public_receipts = evaluate_architecture_public(verified, constellation)
    admitted_arch = holdout_admit_architecture(public_receipts)

    judged_arch = []
    for cand in admitted_arch:
        receipt = judge_architecture_phase4(cand, active_candidate, constellation)
        if receipt.pass_:
            judged_arch.append((cand, receipt))

    canary_survivors = run_architecture_canary(judged_arch, constellation)
    maybe_activate_best_architecture(canary_survivors)

    update_portfolio_ledgers(canary_survivors)
    update_qd_archive(canary_survivors, public_receipts)
    append_law_archive_records(canary_survivors)

    g_candidates = generate_searchlaw_candidates(active_searchlaw, law_tokens, feature_vector)
    g_offline = eval_searchlaw_offline(g_candidates, law_archive, portfolio)
    g_ab = run_searchlaw_ab_trials(g_offline.passing, active_searchlaw, portfolio, constellation)
    maybe_activate_searchlaw(g_ab)

    retire_or_replace_stale_hidden_challenges(constellation)
    cull_unproductive_branches(portfolio)
    persist_all_receipts()
```

---

## 17. CLI behavior

Implement these binaries and flags.

### 17.1 `apfsc_ingest_formal`

```text
cargo run --bin apfsc_ingest_formal -- fixtures/apfsc/phase4/formal/deny_unbounded_gather
```

Behavior:

- validate tightening-only semantics,
- emit admission receipt,
- update `active_formal_policy.json` only if configured to apply immediately.

### 17.2 `apfsc_ingest_tool`

```text
cargo run --bin apfsc_ingest_tool -- fixtures/apfsc/phase4/tools/tool_graph_shadow
```

Behavior:

- quarantine toolpack,
- emit `ToolShadowReceipt` with `Quarantined` status,
- do not activate until `apfsc_tool_shadow` passes.

### 17.3 `apfsc_tool_shadow`

```text
cargo run --bin apfsc_tool_shadow -- --toolpack <toolpack_hash> --candidate <candidate_hash>
```

Behavior:

- run gold-trace equivalence,
- run deterministic replay tests,
- emit `ToolShadowReceipt`,
- mark tool eligible for public/canary only on success.

### 17.4 `apfsc_rotate_challenges`

```text
cargo run --bin apfsc_rotate_challenges -- --snapshot <snapshot_hash> --constellation <constellation_id>
```

Behavior:

- retire stale hidden challenge families,
- select replacements,
- emit updated challenge manifest.

### 17.5 `apfsc_recombine`

```text
cargo run --bin apfsc_recombine -- --parent-a <hash> --parent-b <hash> --mode block_swap
```

Behavior:

- verify compatibility,
- emit recombination candidate artifacts.

### 17.6 `apfsc_portfolio_step`

```text
cargo run --bin apfsc_portfolio_step -- --profile phase4 --portfolio <portfolio_id>
```

Behavior:

- load active search law,
- allocate credits/debt,
- step branch bookkeeping,
- emit ledgers only.

### 17.7 `apfsc_searchlaw_offline_eval`

```text
cargo run --bin apfsc_searchlaw_offline_eval -- --searchlaw <hash> --archive <law_archive_hash>
```

Behavior:

- replay archived outcomes,
- emit offline receipt.

### 17.8 `apfsc_searchlaw_ab`

```text
cargo run --bin apfsc_searchlaw_ab -- --candidate <hash> --incumbent <hash> --epochs 2
```

Behavior:

- run branch-partitioned A/B trial,
- emit A/B receipt,
- do not activate directly.

### 17.9 `apfsc_epoch_run`

```text
cargo run --bin apfsc_epoch_run -- --profile phase4 --epochs 2
```

Behavior:

- run the full macro-epoch loop,
- may activate architecture and/or search law,
- emit all receipts and pointer updates.

---

## 18. Config schema

Extend the Phase 3 config with a `[phase4]` section.

```toml
[phase4]
enable_hidden_challenge_gate = true
challenge_min_bucket_score = 0
challenge_retire_after_epochs = 8
holdout_retire_after_epochs = 12

enable_formal_pack = true
enable_tool_pack = true
enable_recombination = true
enable_qd_archive = true
enable_searchlaw = true
enable_need_tokens = true
enable_credit_debt = true

max_hidden_challenge_families = 4
max_searchlaw_public_candidates = 6
max_searchlaw_ab_candidates = 2
searchlaw_min_ab_epochs = 2
searchlaw_max_ab_epochs = 4
searchlaw_required_yield_improvement = 0.20

max_portfolio_branches = 8
max_branch_local_debt_credits = 3
max_global_debt_credits = 8
max_idle_epochs_before_cull = 3

max_qd_cells = 128
max_needtokens_per_epoch = 8
max_recombination_parents = 2

yield_points_s = 1
yield_points_a = 2
yield_points_pwarm = 3
yield_points_pcold = 4
yield_points_challenge_bonus = 1
```

Implementation rules:

- config defaults must be deterministic,
- all enabled features must still fail closed if supporting artifacts are missing,
- changing config changes receipts and must be reflected in digest inputs.

---

## 19. Acceptance tests

Add the following tests exactly.

### 19.1 `apfsc_phase4_formal_pack.rs`

- ingest a valid tightening-only `FormalPack`,
- verify `FormalPackAdmissionReceipt.applied == true`,
- ensure a denied SCIR pattern is now rejected by `scir/verify.rs`.

### 19.2 `apfsc_phase4_tool_shadow.rs`

- ingest a `ToolPack`,
- run tool-shadow equivalence on a graph-safe candidate,
- assert promotion to `PublicCanaryEligible` only on exact match.

### 19.3 `apfsc_phase4_hidden_challenge.rs`

- build a constellation with hidden challenge families,
- judge a candidate that regresses catastrophically on one protected hidden family,
- assert immediate rejection.

### 19.4 `apfsc_phase4_challenge_retirement.rs`

- age a hidden challenge family beyond retirement threshold,
- run rotation,
- assert retirement receipt and replacement manifest.

### 19.5 `apfsc_phase4_law_archive.rs`

- append judged receipts,
- build a law archive,
- assert deterministic ordering and stable hash.

### 19.6 `apfsc_phase4_law_tokens.rs`

- create repeated archive motifs,
- distill law tokens,
- assert support threshold and stable token ids.

### 19.7 `apfsc_phase4_need_tokens.rs`

- construct stagnation conditions,
- run active search law,
- assert emitted need tokens with expected bucket and justification codes.

### 19.8 `apfsc_phase4_portfolio_credit.rs`

- mint credits after a judged promotion,
- borrow debt on one branch,
- fail to repay across idle epochs,
- assert cull receipt.

### 19.9 `apfsc_phase4_qd_archive.rs`

- insert candidates into multiple morphology cells,
- assert replacement only when new quality dominates or novelty policy allows.

### 19.10 `apfsc_phase4_recombination.rs`

- build two compatible parents,
- emit recombination candidate,
- assert dependency-pack compatibility and compile pass.

### 19.11 `apfsc_phase4_searchlaw_offline.rs`

- replay a historical archive window,
- assert projected yield per compute is computed deterministically,
- reject a candidate search law wired to forbidden fields.

### 19.12 `apfsc_phase4_searchlaw_ab.rs`

- run a two-epoch branch-partitioned A/B trial,
- assert yield attribution by branch owner,
- assert pass only when required improvement threshold is met.

### 19.13 `apfsc_phase4_judge.rs`

- verify architecture candidate challenge-gated positive path,
- verify search-law candidate positive path,
- verify forbidden-input audit rejection.

### 19.14 `apfsc_phase4_e2e_architecture.rs`

- run one macro-epoch where an architecture candidate from recombination or incubator wins,
- assert challenge receipt exists,
- assert architecture activation is atomic.

### 19.15 `apfsc_phase4_e2e_searchlaw.rs`

- run one macro-epoch where a search-law candidate wins,
- assert offline receipt, A/B receipt, and search-law activation receipt exist,
- assert `active_search_law.json` changes and `active_candidate.json` does not unless an architecture promotion also passed.

### 19.16 `apfsc_phase4_e2e_full_loop.rs`

- run two deterministic macro-epochs,
- assert:
  - all five pack types were loaded,
  - hidden challenge rotation occurred or was checked,
  - law archive grew,
  - need tokens emitted,
  - portfolio ledgers updated,
  - deterministic replay of receipts.

---

## 20. Coding rules for codex

1. Preserve all Phase 1/2/3 public APIs unless a Phase 4 extension requires a field addition.
2. Centralize search-law logic in `search_law.rs` and `searchlaw_eval.rs`. Do not scatter `G` logic across binaries.
3. Keep deterministic ordering everywhere: branch ids, challenge ids, token ids, law-archive records, and recombination parent lists must be lexicographically sorted before hashing.
4. Do not let a search law access any file or struct containing raw holdout scalars or hidden challenge contents.
5. Do not let `ToolPack` replace holdout truth.
6. Keep `FormalPack` tightening-only. Any attempted loosening must fail closed.
7. Every receipt and manifest must carry protocol version, snapshot hash, and constellation id where relevant.
8. Credits and yield points are different:
   - yield points are judge-owned scored evidence,
   - credits are exploration budget derived from judged outcomes.
9. Do not allow debt to pay for holdout or hidden challenge evaluation.
10. Recombination must never bypass compile, verify, and formal policy checks.
11. Search-law activation must be a separate atomic pointer write from architecture activation.
12. If a tool-shadow backend fails equivalence, fall back cleanly and emit a typed receipt.
13. Keep challenge rotation deterministic. No hidden random selection.
14. Keep one source of truth for hidden challenge retirement logic in `retirement.rs`.
15. Do not add Python or external processes in judged execution.

---

## 21. Suggested implementation order

Implement in this order.

1. Extend common types, config, and active-pointer management for Phase 4.
2. Add `FormalPack` and `ToolPack` ingestion plus receipts.
3. Add `DependencyPack` and extend candidate manifests.
4. Add hidden challenge manifests, retirement logic, and bank/constellation extensions.
5. Extend judge for architecture challenge gating.
6. Add `LawArchive` and `LawToken` extraction.
7. Add `NeedToken` emission.
8. Add portfolio ledgers and credit/debt accounting.
9. Add QD archive.
10. Add recombination lane.
11. Add tool-shadow lane and tool-shadow receipts.
12. Add search-law schema and feature extraction.
13. Add search-law offline evaluator.
14. Add search-law live A/B evaluator.
15. Extend orchestrator for macro-epoch flow.
16. Add fixtures and lock expected receipts.
17. Run one deterministic architecture macro-epoch.
18. Run one deterministic search-law macro-epoch.
19. Run the full two-epoch Phase 4 demo.

---

## 22. Minimum viable demo sequence

The codex agent should make this exact demo runnable:

```text
cargo run --bin apfsc_seed_init -- --profile phase1

# reuse existing Phase 2 / Phase 3 families, then add Phase 4 packs
cargo run --bin apfsc_ingest_reality -- fixtures/apfsc/phase4/reality_challenge/f6_hidden_logic_challenge
cargo run --bin apfsc_ingest_reality -- fixtures/apfsc/phase4/reality_challenge/f7_hidden_sparse_challenge

cargo run --bin apfsc_ingest_formal -- fixtures/apfsc/phase4/formal/deny_unbounded_gather
cargo run --bin apfsc_ingest_tool -- fixtures/apfsc/phase4/tools/tool_graph_shadow
cargo run --bin apfsc_ingest_prior -- fixtures/apfsc/phase4/priors/recombination_seed
cargo run --bin apfsc_ingest_prior -- fixtures/apfsc/phase4/priors/searchlaw_seed

cargo run --bin apfsc_rotate_challenges -- --snapshot <snapshot_hash> --constellation <constellation_id>
cargo run --bin apfsc_epoch_run -- --profile phase4 --epochs 2
```

Expected behavior:

- all five pack kinds exist in the snapshot/input ledger,
- hidden challenge manifest exists,
- formal policy is applied,
- tool shadow receipts exist,
- architecture candidates are generated across all active lanes,
- at least one law archive update occurs,
- at least one need token is emitted,
- search-law offline and A/B receipts are emitted,
- architecture and/or search law activates or rejects deterministically.

---

## 23. Definition of done

Phase 4 is complete only if all of the following are true:

1. all five ingress pack kinds are implemented,
2. hidden challenge families gate architecture promotion,
3. challenge retirement and replacement exist,
4. formal policy tightening is live,
5. tool-shadow execution exists,
6. dependency packs pin external inputs,
7. law archive and law-token distillation exist,
8. branch portfolios with credit/debt exist,
9. bounded recombination exists,
10. QD archive exists and influences search,
11. search-law candidates can be generated,
12. search-law offline replay exists,
13. search-law live A/B exists,
14. `G` can activate through a judged receipt,
15. architecture and search-law activations are independently atomic,
16. the same two-epoch Phase 4 run reproduces identical receipts exactly.

---

## 24. Permanent non-goals and trust boundaries

These remain outside recursion even in the final Phase 4 plan:

- the protocol plane,
- holdout and hidden challenge reveal policy,
- judge monopoly on activation,
- content-addressed artifact law,
- atomic activation protocol,
- fail-closed containment,
- deterministic replay law.

Phase 4 is the final one-node recursive architecture-science engine. It is not permission to rewrite the scientific method.

---

## 25. Final implementation intent

Phase 4 is where APF-SC stops being only an architecture search engine and becomes a full research laboratory under fixed law. The active architecture candidate remains the current best computational theory for the bank constellation. The active search law becomes the current best policy for discovering better theories. Hidden challenge families keep the system from memorizing the visible evaluation surface. Formal packs tighten admissibility. Tool packs widen the reachable execution space without contaminating interpreter truth. The law archive turns judged history into reusable public research memory. Branch portfolios let the system explore more than one basin while remaining credit-disciplined. Recombination and the QD archive preserve multiple viable morphologies. Need tokens keep the system pointing outward toward new reality, priors, tools, and constraints without allowing autonomous drift. That is the narrowest final design that still qualifies as a recursive architecture-science engine on a single 16 GiB-class node while keeping every trust anchor outside the recursion.
