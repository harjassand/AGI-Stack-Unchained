use std::path::Path;

use serde::{Deserialize, Serialize};

use crate::apfsc::artifacts::append_jsonl_atomic;
use crate::apfsc::errors::Result;
use crate::apfsc::types::ConstellationScoreReceipt;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct FamilyScoreRow {
    pub candidate_hash: String,
    pub incumbent_hash: String,
    pub snapshot_hash: String,
    pub constellation_id: String,
    pub stage: String,
    pub weighted_static_public_bpb: Option<f64>,
    pub weighted_static_holdout_bpb: Option<f64>,
    pub weighted_transfer_public_bpb: Option<f64>,
    pub weighted_transfer_holdout_bpb: Option<f64>,
    pub weighted_robust_public_bpb: Option<f64>,
    pub weighted_robust_holdout_bpb: Option<f64>,
    pub improved_families: Vec<String>,
    pub regressed_families: Vec<String>,
    pub protected_floor_pass: bool,
    pub target_subset_pass: bool,
    pub replay_hash: String,
}

pub fn append_receipt(root: &Path, stage: &str, receipt: &ConstellationScoreReceipt) -> Result<()> {
    let row = FamilyScoreRow {
        candidate_hash: receipt.candidate_hash.clone(),
        incumbent_hash: receipt.incumbent_hash.clone(),
        snapshot_hash: receipt.snapshot_hash.clone(),
        constellation_id: receipt.constellation_id.clone(),
        stage: stage.to_string(),
        weighted_static_public_bpb: receipt.weighted_static_public_bpb,
        weighted_static_holdout_bpb: receipt.weighted_static_holdout_bpb,
        weighted_transfer_public_bpb: receipt.weighted_transfer_public_bpb,
        weighted_transfer_holdout_bpb: receipt.weighted_transfer_holdout_bpb,
        weighted_robust_public_bpb: receipt.weighted_robust_public_bpb,
        weighted_robust_holdout_bpb: receipt.weighted_robust_holdout_bpb,
        improved_families: receipt.improved_families.clone(),
        regressed_families: receipt.regressed_families.clone(),
        protected_floor_pass: receipt.protected_floor_pass,
        target_subset_pass: receipt.target_subset_pass,
        replay_hash: receipt.replay_hash.clone(),
    };
    append_jsonl_atomic(&root.join("archive/family_scores.jsonl"), &row)
}
