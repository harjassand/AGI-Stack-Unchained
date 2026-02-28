use std::path::Path;

use serde::{Deserialize, Serialize};

use crate::apfsc::artifacts::append_jsonl_atomic;
use crate::apfsc::candidate::load_candidate;
use crate::apfsc::errors::Result;
use crate::apfsc::types::{CanaryBatchReport, JudgeBatchReport};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct GenealogyRow {
    pub candidate_hash: String,
    pub parent_hashes: Vec<String>,
    pub lane: String,
    pub mutation_type: String,
    pub decision: String,
    pub snapshot_hash: String,
    #[serde(default)]
    pub constellation_id: Option<String>,
    #[serde(default)]
    pub improved_family_ids: Vec<String>,
    #[serde(default)]
    pub regressed_family_ids: Vec<String>,
}

pub fn append_row(root: &Path, row: &GenealogyRow) -> Result<()> {
    append_jsonl_atomic(&root.join("archive/genealogy.jsonl"), row)
}

pub fn append_epoch(
    root: &Path,
    judge_report: &JudgeBatchReport,
    canary_report: &CanaryBatchReport,
) -> Result<()> {
    for r in &judge_report.receipts {
        let decision = match r.decision {
            crate::apfsc::types::JudgeDecision::Promote => "promote",
            crate::apfsc::types::JudgeDecision::Reject => "reject",
        };

        let lineage = load_candidate(root, &r.candidate_hash).ok();
        let row = GenealogyRow {
            candidate_hash: r.candidate_hash.clone(),
            parent_hashes: lineage
                .as_ref()
                .map(|c| c.manifest.parent_hashes.clone())
                .filter(|p| !p.is_empty())
                .unwrap_or_else(|| vec![r.incumbent_hash.clone()]),
            lane: lineage
                .as_ref()
                .map(|c| c.build_meta.lane.clone())
                .unwrap_or_else(|| "unknown".to_string()),
            mutation_type: lineage
                .as_ref()
                .map(|c| c.build_meta.mutation_type.clone())
                .unwrap_or_else(|| "unknown".to_string()),
            decision: decision.to_string(),
            snapshot_hash: lineage
                .as_ref()
                .map(|c| c.manifest.snapshot_hash.clone())
                .unwrap_or_else(|| r.snapshot_hash.clone()),
            constellation_id: r.constellation_id.clone(),
            improved_family_ids: r.improved_family_ids.clone(),
            regressed_family_ids: r.regressed_family_ids.clone(),
        };
        append_row(root, &row)?;
    }

    for c in &canary_report.evaluated {
        let lineage = load_candidate(root, c).ok();
        let row = GenealogyRow {
            candidate_hash: c.clone(),
            parent_hashes: lineage
                .as_ref()
                .map(|cand| cand.manifest.parent_hashes.clone())
                .unwrap_or_default(),
            lane: "canary".to_string(),
            mutation_type: lineage
                .as_ref()
                .map(|cand| cand.build_meta.mutation_type.clone())
                .unwrap_or_else(|| "shadow_canary".to_string()),
            decision: if canary_report.activated.as_ref() == Some(c) {
                "activated".to_string()
            } else {
                "not_activated".to_string()
            },
            snapshot_hash: lineage
                .as_ref()
                .map(|cand| cand.manifest.snapshot_hash.clone())
                .unwrap_or_default(),
            constellation_id: None,
            improved_family_ids: Vec::new(),
            regressed_family_ids: Vec::new(),
        };
        append_row(root, &row)?;
    }
    Ok(())
}
