use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};

pub type DigestHex = String;
pub type FamilyId = String;
pub type VariantId = String;
pub type ConstellationId = String;
pub type CandidateId = String;
pub type SnapshotId = String;

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
pub enum BackendKind {
    Tier0Cpu,
    Tier1Stub,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
pub enum FamilyKind {
    AlgorithmicSymbolic,
    TextCodeLog,
    SensoryTemporal,
    PhysicalSimulation,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
pub enum RealityRole {
    Base,
    Transfer,
    Robust,
    ChallengeStub,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq, PartialOrd, Ord)]
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

impl PanelKind {
    pub fn as_key(self) -> &'static str {
        match self {
            PanelKind::Train => "train",
            PanelKind::StaticPublic => "static_public",
            PanelKind::StaticHoldout => "static_holdout",
            PanelKind::Anchor => "anchor",
            PanelKind::Canary => "canary",
            PanelKind::TransferTrain => "transfer_train",
            PanelKind::TransferEval => "transfer_eval",
            PanelKind::RobustPublic => "robust_public",
            PanelKind::RobustHoldout => "robust_holdout",
            PanelKind::ChallengeStub => "challenge_stub",
        }
    }
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
pub enum EvalMode {
    Public,
    Holdout,
}

impl EvalMode {
    pub fn as_key(self) -> &'static str {
        match self {
            EvalMode::Public => "public",
            EvalMode::Holdout => "holdout",
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
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

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum PackKind {
    Reality,
    Prior,
    Substrate,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
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

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Provenance {
    pub source_name: String,
    pub source_type: String,
    pub attestation: Option<String>,
    pub notes: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct RealityMeta {
    pub family_id: FamilyId,
    pub family_kind: FamilyKind,
    pub role: RealityRole,
    pub variant_id: VariantId,
    pub base_family_id: Option<FamilyId>,
    pub description: String,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq, PartialOrd, Ord)]
pub enum SplitKind {
    Train,
    Public,
    Holdout,
    Anchor,
    Canary,
    TransferTrain,
    TransferEval,
    RobustPublic,
    RobustHoldout,
    ChallengeStub,
}

impl SplitKind {
    pub fn as_key(self) -> &'static str {
        match self {
            SplitKind::Train => "train",
            SplitKind::Public => "public",
            SplitKind::Holdout => "holdout",
            SplitKind::Anchor => "anchor",
            SplitKind::Canary => "canary",
            SplitKind::TransferTrain => "transfer_train",
            SplitKind::TransferEval => "transfer_eval",
            SplitKind::RobustPublic => "robust_public",
            SplitKind::RobustHoldout => "robust_holdout",
            SplitKind::ChallengeStub => "challenge_stub",
        }
    }

    pub fn from_key(v: &str) -> Option<Self> {
        match v {
            "train" => Some(SplitKind::Train),
            "public" => Some(SplitKind::Public),
            "holdout" => Some(SplitKind::Holdout),
            "anchor" => Some(SplitKind::Anchor),
            "canary" => Some(SplitKind::Canary),
            "transfer_train" => Some(SplitKind::TransferTrain),
            "transfer_eval" => Some(SplitKind::TransferEval),
            "robust_public" => Some(SplitKind::RobustPublic),
            "robust_holdout" => Some(SplitKind::RobustHoldout),
            "challenge_stub" => Some(SplitKind::ChallengeStub),
            _ => None,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct WindowRef {
    pub family_id: FamilyId,
    pub split: SplitKind,
    pub seq_hash: DigestHex,
    pub start: u64,
    pub len: u32,
    pub target_offset: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct BankManifest {
    pub family_id: FamilyId,
    pub source_pack_hash: DigestHex,
    pub window_len: u32,
    pub stride: u32,
    pub split_counts: BTreeMap<String, u64>,
    pub manifest_hash: DigestHex,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct FamilyBankManifest {
    pub family_id: FamilyId,
    pub family_kind: FamilyKind,
    pub source_pack_hashes: Vec<String>,
    pub window_len: u32,
    pub stride: u32,
    pub panel_counts: BTreeMap<String, u64>,
    pub manifest_hash: String,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
pub enum PromotionClass {
    S,
    A,
    PWarmDisabled,
    PColdDisabled,
    GDisabled,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct EpochSnapshot {
    pub snapshot_hash: SnapshotId,
    pub reality_roots: Vec<DigestHex>,
    pub prior_roots: Vec<DigestHex>,
    pub substrate_roots: Vec<DigestHex>,
    pub protocol_version: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
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

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct CandidateBuildMeta {
    pub target_families: Vec<FamilyId>,
    pub source_lane: String,
    pub phase2_profile: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct StatePack {
    pub core_weights: Vec<f32>,
    pub resid_weights: Vec<f32>,
    pub fast_weight_budget_bytes: u64,
    pub init_state: Vec<f32>,
    pub codec_version: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct HeadPack {
    pub native_head: LinearHead,
    pub nuisance_head: LinearHead,
    pub residual_head: LinearHead,
    pub shadow_heads: Vec<LinearHead>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct LinearHead {
    pub in_dim: u32,
    pub out_dim: u32,
    pub weights: Vec<f32>,
    pub bias: Vec<f32>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct WarmRefinementPack {
    pub protected_families: Vec<FamilyId>,
    pub max_anchor_regress_bits: f64,
    pub max_public_regress_bits: f64,
    pub migration_policy: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct SchedulePack {
    pub backend: BackendKind,
    pub tile_bytes: u64,
    pub segment_bytes: u64,
    pub predicted_cost: Option<PredictedCost>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct PredictedCost {
    pub wall_ms: f64,
    pub peak_rss_bytes: u64,
    pub risk_score: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ByteScoreReceipt {
    pub candidate_hash: CandidateId,
    pub snapshot_hash: SnapshotId,
    pub split: SplitKind,
    pub family_scores_bits: BTreeMap<FamilyId, f64>,
    pub total_bits: f64,
    pub mean_bits_per_byte: f64,
    pub peak_rss_bytes: u64,
    pub wall_ms: u64,
    pub replay_hash: DigestHex,
    pub backend_fingerprint: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct FamilyWeights {
    pub static_weight: f64,
    pub transfer_weight: f64,
    pub robust_weight: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ProtectionFloor {
    pub protected: bool,
    pub max_static_regress_bpb: f64,
    pub max_transfer_regress_bpb: f64,
    pub max_robust_regress_bpb: f64,
    pub min_family_improve_bpb: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
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

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
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

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
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

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ConstellationManifest {
    pub constellation_id: ConstellationId,
    pub snapshot_hash: SnapshotId,
    pub family_specs: Vec<FamilySpec>,
    pub normalization: NormalizationPolicy,
    pub protocol_version: String,
    pub manifest_hash: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct FamilyPanelMetric {
    pub family_id: FamilyId,
    pub panel: PanelKind,
    pub bits_total: f64,
    pub target_bytes: u64,
    pub mean_bpb: f64,
    pub window_count: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
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

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ConstellationScoreReceipt {
    pub candidate_hash: CandidateId,
    pub incumbent_hash: CandidateId,
    pub snapshot_hash: SnapshotId,
    pub constellation_id: ConstellationId,
    #[serde(default)]
    pub protocol_version: String,
    pub per_family: BTreeMap<FamilyId, FamilyEvalVector>,
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

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
pub enum JudgeDecision {
    Promote,
    Reject,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum JudgeRejectReason {
    NoPublicMargin,
    NoHoldoutMargin,
    ArtifactMissing,
    ArtifactInvalid,
    MissingSnapshot,
    ResourceViolation,
    HoldoutNoGain,
    AnchorRegress,
    WarmBridgeFail,
    MiniTransferFail,
    StabilityFail,
    CanaryFail,
    InsufficientCrossFamilyEvidence,
    ProtectedFamilyRegress,
    TransferRegression,
    RobustRegression,
    TargetSubsetMiss,
    ConstellationMismatch,
    MissingFamilyRole,
    TransferDeltaBudgetExceeded,
}

impl JudgeRejectReason {
    pub fn as_reason(&self) -> String {
        format!("Reject({self:?})")
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct PromotionReceipt {
    pub candidate_hash: CandidateId,
    pub incumbent_hash: CandidateId,
    pub decision: JudgeDecision,
    pub reason: String,

    // Phase-1 fields kept for backward compatibility.
    pub public_delta_bits: f64,
    pub holdout_delta_bits: f64,
    pub anchor_regress_bits: f64,

    // Phase-2 fields.
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
    #[serde(default)]
    pub protocol_version: String,
    pub constellation_id: Option<ConstellationId>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct IngressReceipt {
    pub pack_hash: DigestHex,
    pub pack_kind: PackKind,
    pub validation_checks_passed: Vec<String>,
    pub ingest_time_unix_s: u64,
    pub protocol_version: String,
    pub snapshot_included: bool,
    #[serde(default)]
    pub family_id: Option<FamilyId>,
    #[serde(default)]
    pub family_kind: Option<FamilyKind>,
    #[serde(default)]
    pub reality_role: Option<RealityRole>,
    #[serde(default)]
    pub variant_id: Option<VariantId>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct SubstrateTrace {
    pub candidate_or_program_fingerprint: String,
    pub op_count: u64,
    pub feature_dim: u64,
    pub scan_hidden_dim: u64,
    pub window_len: u64,
    pub peak_rss_bytes: u64,
    pub wall_ms: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct PublicEvalRecord {
    pub candidate_hash: CandidateId,
    pub receipt: ByteScoreReceipt,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct JudgeBatchReport {
    pub receipts: Vec<PromotionReceipt>,
    pub queued_for_canary: Vec<CandidateId>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct CanaryBatchReport {
    pub evaluated: Vec<CandidateId>,
    pub activated: Option<CandidateId>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct EpochReport {
    pub public_receipts: Vec<ByteScoreReceipt>,
    pub judge_report: JudgeBatchReport,
    pub canary_report: CanaryBatchReport,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct CandidateStub {
    pub candidate_hash: CandidateId,
    pub lane: String,
    pub mutation_type: String,
    pub promotion_class: PromotionClass,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct WitnessSelection {
    pub selected: Vec<WindowRef>,
    pub bins: BTreeMap<String, usize>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct FamilyWitnessSelection {
    pub selected: Vec<WindowRef>,
    pub bins: BTreeMap<String, usize>,
    pub per_family_counts: BTreeMap<FamilyId, usize>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct TransferFamilyTrace {
    pub candidate_hash: CandidateId,
    pub incumbent_hash: CandidateId,
    pub snapshot_hash: SnapshotId,
    pub constellation_id: ConstellationId,
    #[serde(default)]
    pub protocol_version: String,
    pub family_id: FamilyId,
    pub mode: EvalMode,
    pub candidate_panel_bpb: f64,
    pub incumbent_panel_bpb: f64,
    pub candidate_penalty_bpb: f64,
    pub incumbent_penalty_bpb: f64,
    pub delta_bpb: f64,
    pub delta_bits: u64,
    pub replay_hash: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct RobustnessFamilyTrace {
    pub candidate_hash: CandidateId,
    pub incumbent_hash: CandidateId,
    pub snapshot_hash: SnapshotId,
    pub constellation_id: ConstellationId,
    #[serde(default)]
    pub protocol_version: String,
    pub family_id: FamilyId,
    pub panel: PanelKind,
    pub candidate_bpb: f64,
    pub incumbent_bpb: f64,
    pub delta_bpb: f64,
    pub replay_hash: String,
}
