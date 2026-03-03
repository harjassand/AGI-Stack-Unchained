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
    pub active_incubator_pointer: Option<String>,
    pub active_incubator_search_law: Option<String>,
    pub active_era: Option<String>,
    pub active_search_law: Option<String>,
    pub latest_backup_age_s: Option<u64>,
    pub latest_qualification_status: Option<String>,
    pub class_m_generation_count: u64,
    pub demon_lane_mortality_count: u64,
    pub demon_lane_consecutive_mortality_count: u64,
    pub best_demon_survival_margin: Option<f64>,
    pub current_demon_survival_margin: Option<f64>,
    pub last_rejected_proposal_score: Option<f64>,
    pub last_rejected_proposal_reason: Option<String>,
    pub last_rejected_proposal_trace: Option<String>,
    pub thermal_spike_active: bool,
    pub thermal_spike_temp: Option<f64>,
    pub thermal_spike_epochs_remaining: u32,
}

pub fn health_report(root: &Path) -> Result<HealthReport> {
    let active_candidate = read_pointer(root, "active_candidate").ok();
    let active_incubator_pointer = read_pointer(root, "active_incubator_pointer").ok();
    let active_incubator_search_law = read_pointer(root, "active_incubator_search_law").ok();
    let active_era = read_pointer(root, "active_era").ok();
    let active_search_law = read_pointer(root, "active_search_law").ok();
    let volatile = crate::apfsc::artifacts::omega_volatile_metrics();
    let thermal = crate::apfsc::searchlaw_eval::thermal_spike_state(root);
    Ok(HealthReport {
        liveness: true,
        readiness: active_candidate.is_some(),
        preflight_ok: true,
        active_candidate,
        active_incubator_pointer,
        active_incubator_search_law,
        active_era,
        active_search_law,
        latest_backup_age_s: None,
        latest_qualification_status: None,
        class_m_generation_count: volatile.class_m_generation_count,
        demon_lane_mortality_count: volatile.demon_lane_mortality_count,
        demon_lane_consecutive_mortality_count: volatile.demon_lane_consecutive_mortality_count,
        best_demon_survival_margin: volatile.best_demon_survival_margin,
        current_demon_survival_margin: volatile.current_demon_survival_margin,
        last_rejected_proposal_score: volatile.last_rejected_proposal_score,
        last_rejected_proposal_reason: volatile.last_rejected_proposal_reason,
        last_rejected_proposal_trace: volatile.last_rejected_proposal_trace,
        thermal_spike_active: thermal.active,
        thermal_spike_temp: thermal.temp,
        thermal_spike_epochs_remaining: thermal.epochs_remaining,
    })
}
