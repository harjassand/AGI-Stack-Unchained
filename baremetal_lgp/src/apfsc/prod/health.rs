use std::path::Path;

use serde::{Deserialize, Serialize};

use crate::apfsc::artifacts::read_pointer;
use crate::apfsc::errors::Result;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct HealthReport {
    pub liveness: bool,
    pub readiness: bool,
    pub preflight_ok: bool,
    pub active_candidate: Option<String>,
    pub active_search_law: Option<String>,
    pub latest_backup_age_s: Option<u64>,
    pub latest_qualification_status: Option<String>,
}

pub fn health_report(root: &Path) -> Result<HealthReport> {
    let active_candidate = read_pointer(root, "active_candidate").ok();
    let active_search_law = read_pointer(root, "active_search_law").ok();
    Ok(HealthReport {
        liveness: true,
        readiness: active_candidate.is_some(),
        preflight_ok: true,
        active_candidate,
        active_search_law,
        latest_backup_age_s: None,
        latest_qualification_status: None,
    })
}
