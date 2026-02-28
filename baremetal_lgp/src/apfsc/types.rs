use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};

pub type DigestHex = String;
pub type FamilyId = String;
pub type CandidateId = String;
pub type SnapshotId = String;

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
pub enum BackendKind {
    Tier0Cpu,
    Tier1Stub,
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

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq, PartialOrd, Ord)]
pub enum SplitKind {
    Train,
    Public,
    Holdout,
    Anchor,
    Canary,
    TransferTrain,
    TransferEval,
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

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
pub enum JudgeDecision {
    Promote,
    Reject,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
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

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct IngressReceipt {
    pub pack_hash: DigestHex,
    pub pack_kind: PackKind,
    pub validation_checks_passed: Vec<String>,
    pub ingest_time_unix_s: u64,
    pub protocol_version: String,
    pub snapshot_included: bool,
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
