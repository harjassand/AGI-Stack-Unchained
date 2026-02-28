use std::path::Path;

use serde::{Deserialize, Serialize};

use crate::apfsc::artifacts::append_jsonl_atomic;
use crate::apfsc::candidate::CandidateBundle;
use crate::apfsc::config::Phase1Config;
use crate::apfsc::errors::Result;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ColdFrontierNote {
    pub parent_hash: String,
    pub snapshot_hash: String,
    pub note: String,
}

pub fn record_only(
    root: &Path,
    active: &CandidateBundle,
    cfg: &Phase1Config,
) -> Result<Vec<CandidateBundle>> {
    let note = ColdFrontierNote {
        parent_hash: active.manifest.candidate_hash.clone(),
        snapshot_hash: active.manifest.snapshot_hash.clone(),
        note: format!(
            "cold-frontier stub active; max_public_candidates={}",
            cfg.lanes.max_public_candidates
        ),
    };
    append_jsonl_atomic(&root.join("archive/cold_frontier_stub.jsonl"), &note)?;
    Ok(Vec::new())
}
