use std::collections::BTreeSet;
use std::path::Path;

use serde::{Deserialize, Serialize};

use crate::apfsc::artifacts::{append_jsonl_atomic, read_jsonl};
use crate::apfsc::candidate::CandidateBundle;
use crate::apfsc::errors::Result;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct FailureMorphRow {
    pub candidate_hash: String,
    pub morphology_descriptor: String,
    pub failure_class: String,
    pub snapshot_hash: String,
    pub taboo_expiration_epoch: u64,
}

pub fn append_reject(
    root: &Path,
    candidate_hash: &str,
    morphology_descriptor: &str,
    failure_class: &str,
    snapshot_hash: &str,
    taboo_expiration_epoch: u64,
) -> Result<()> {
    let row = FailureMorphRow {
        candidate_hash: candidate_hash.to_string(),
        morphology_descriptor: morphology_descriptor.to_string(),
        failure_class: failure_class.to_string(),
        snapshot_hash: snapshot_hash.to_string(),
        taboo_expiration_epoch,
    };
    append_jsonl_atomic(&root.join("archive/failure_morph.jsonl"), &row)
}

pub fn apply_taboo(
    root: &Path,
    candidates: Vec<CandidateBundle>,
    current_epoch: u64,
) -> Result<Vec<CandidateBundle>> {
    let rows: Vec<FailureMorphRow> = read_jsonl(&root.join("archive/failure_morph.jsonl"))?;
    let taboo: BTreeSet<String> = rows
        .into_iter()
        .filter(|r| current_epoch < r.taboo_expiration_epoch)
        .map(|r| r.morphology_descriptor)
        .collect();

    let mut out = Vec::new();
    for c in candidates {
        if !taboo.contains(&c.build_meta.mutation_type) {
            out.push(c);
        }
    }
    Ok(out)
}
