use std::path::Path;

use serde::{Deserialize, Serialize};

use crate::apfsc::artifacts::{read_json, write_json_atomic};
use crate::apfsc::errors::Result;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct PendingAdmission {
    pub candidate_hash: String,
    pub snapshot_hash: String,
    pub public_delta_bits: f64,
}

pub fn load_pending_admissions(root: &Path) -> Result<Vec<PendingAdmission>> {
    let path = root.join("queues/holdout_admissions.json");
    if !path.exists() {
        return Ok(Vec::new());
    }
    read_json(&path)
}

pub fn store_pending_admissions(root: &Path, admissions: &[PendingAdmission]) -> Result<()> {
    let path = root.join("queues/holdout_admissions.json");
    write_json_atomic(&path, admissions)
}
