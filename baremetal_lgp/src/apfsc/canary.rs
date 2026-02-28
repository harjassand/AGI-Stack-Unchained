use std::path::Path;

use serde::{Deserialize, Serialize};

use crate::apfsc::artifacts::{read_json, read_pointer, receipt_path, write_json_atomic};
use crate::apfsc::bank::WindowBank;
use crate::apfsc::candidate::load_candidate;
use crate::apfsc::config::Phase1Config;
use crate::apfsc::constellation::load_constellation;
use crate::apfsc::errors::Result;
use crate::apfsc::hardware_oracle::SafetyBudget;
use crate::apfsc::judge::{activate_candidate, evaluate_candidate_split};
use crate::apfsc::normalization::evaluate_static_panel;
use crate::apfsc::types::{CanaryBatchReport, JudgeDecision, PromotionReceipt, SplitKind};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct CanaryReceipt {
    pub candidate_hash: String,
    pub incumbent_hash: String,
    pub pass: bool,
    pub reason: String,
    pub candidate_bits: f64,
    pub incumbent_bits: f64,
    #[serde(default)]
    pub protocol_version: Option<String>,
    #[serde(default)]
    pub snapshot_hash: Option<String>,
    #[serde(default)]
    pub constellation_id: Option<String>,
    #[serde(default)]
    pub weighted_delta_bpb: Option<f64>,
}

pub fn drain_queue(
    root: &Path,
    banks: &[WindowBank],
    cfg: &Phase1Config,
) -> Result<CanaryBatchReport> {
    let qpath = root.join("queues/canary_queue.json");
    let queue: Vec<String> = if qpath.exists() {
        read_json(&qpath)?
    } else {
        Vec::new()
    };

    let mut evaluated = Vec::new();
    let mut activated = None;

    for candidate_hash in &queue {
        let safety = SafetyBudget::from_config(cfg);
        let incumbent_hash = read_pointer(root, "active_candidate")?;
        let incumbent = load_candidate(root, &incumbent_hash)?;
        let candidate = load_candidate(root, candidate_hash)?;

        let incumbent_receipt =
            evaluate_candidate_split(root, &incumbent, SplitKind::Canary, banks)?;
        let candidate_receipt =
            match evaluate_candidate_split(root, &candidate, SplitKind::Canary, banks) {
                Ok(v) => v,
                Err(_) => {
                    let receipt = CanaryReceipt {
                        candidate_hash: candidate_hash.clone(),
                        incumbent_hash: incumbent_hash.clone(),
                        pass: false,
                        reason: "runtime_failure".to_string(),
                        candidate_bits: f64::INFINITY,
                        incumbent_bits: incumbent_receipt.total_bits,
                        protocol_version: Some(cfg.protocol.version.clone()),
                        snapshot_hash: Some(candidate.manifest.snapshot_hash.clone()),
                        constellation_id: None,
                        weighted_delta_bpb: None,
                    };
                    write_json_atomic(
                        &receipt_path(root, "canary", &format!("{}.json", candidate_hash)),
                        &receipt,
                    )?;
                    evaluated.push(candidate_hash.clone());
                    continue;
                }
            };

        let pass = candidate_receipt.total_bits <= incumbent_receipt.total_bits
            && safety
                .validate_envelope(&candidate.manifest.resource_envelope)
                .is_ok();
        let reason = if pass {
            "pass".to_string()
        } else {
            "Reject(CanaryFail)".to_string()
        };

        let receipt = CanaryReceipt {
            candidate_hash: candidate_hash.clone(),
            incumbent_hash: incumbent_hash.clone(),
            pass,
            reason: reason.clone(),
            candidate_bits: candidate_receipt.total_bits,
            incumbent_bits: incumbent_receipt.total_bits,
            protocol_version: Some(cfg.protocol.version.clone()),
            snapshot_hash: Some(candidate.manifest.snapshot_hash.clone()),
            constellation_id: None,
            weighted_delta_bpb: None,
        };

        write_json_atomic(
            &receipt_path(root, "canary", &format!("{}.json", candidate_hash)),
            &receipt,
        )?;

        evaluated.push(candidate_hash.clone());
        if pass {
            activate_candidate(root, candidate_hash, &candidate.manifest.snapshot_hash)?;
            write_json_atomic(
                &receipt_path(root, "activation", &format!("{}.json", candidate_hash)),
                &receipt,
            )?;
            activated = Some(candidate_hash.clone());
            break;
        } else {
            let reject = PromotionReceipt {
                candidate_hash: candidate_hash.clone(),
                incumbent_hash,
                decision: JudgeDecision::Reject,
                reason: "Reject(CanaryFail)".to_string(),
                public_delta_bits: 0.0,
                holdout_delta_bits: 0.0,
                anchor_regress_bits: 0.0,
                weighted_static_public_delta_bpb: 0.0,
                weighted_static_holdout_delta_bpb: 0.0,
                weighted_transfer_holdout_delta_bpb: None,
                weighted_robust_holdout_delta_bpb: None,
                improved_family_ids: Vec::new(),
                regressed_family_ids: Vec::new(),
                protected_floor_failures: Vec::new(),
                canary_required: true,
                canary_result: Some("fail".to_string()),
                snapshot_hash: candidate.manifest.snapshot_hash.clone(),
                protocol_version: cfg.protocol.version.clone(),
                constellation_id: None,
            };
            write_json_atomic(
                &receipt_path(
                    root,
                    "judge",
                    &format!("reject_canary_{}.json", candidate_hash),
                ),
                &reject,
            )?;
        }
    }

    write_json_atomic(&qpath, &Vec::<String>::new())?;

    Ok(CanaryBatchReport {
        evaluated,
        activated,
    })
}

pub fn run_phase2_canary(
    root: &Path,
    candidate_hash: &str,
    incumbent_hash: &str,
    constellation_id: &str,
    cfg: &Phase1Config,
) -> Result<CanaryReceipt> {
    let constellation = load_constellation(root, constellation_id)?;
    let candidate = load_candidate(root, candidate_hash)?;
    let incumbent = load_candidate(root, incumbent_hash)?;

    let safety = SafetyBudget::from_config(cfg);
    let eval = evaluate_static_panel(
        root,
        &candidate,
        &incumbent,
        &constellation,
        crate::apfsc::types::PanelKind::Canary,
    )?;

    let pass = eval.delta_bpb >= 0.0
        && eval.protected_floor_failures.is_empty()
        && safety
            .validate_envelope(&candidate.manifest.resource_envelope)
            .is_ok();
    let reason = if pass {
        "pass".to_string()
    } else {
        "Reject(CanaryFail)".to_string()
    };

    let receipt = CanaryReceipt {
        candidate_hash: candidate_hash.to_string(),
        incumbent_hash: incumbent_hash.to_string(),
        pass,
        reason: reason.clone(),
        candidate_bits: eval.candidate_weighted_bpb,
        incumbent_bits: eval.incumbent_weighted_bpb,
        protocol_version: Some(constellation.protocol_version.clone()),
        snapshot_hash: Some(candidate.manifest.snapshot_hash.clone()),
        constellation_id: Some(constellation_id.to_string()),
        weighted_delta_bpb: Some(eval.delta_bpb),
    };

    write_json_atomic(
        &receipt_path(root, "canary", &format!("{}.json", candidate_hash)),
        &receipt,
    )?;

    if pass {
        activate_candidate(root, candidate_hash, &candidate.manifest.snapshot_hash)?;
        crate::apfsc::artifacts::write_pointer(root, "active_constellation", constellation_id)?;
        write_json_atomic(
            &receipt_path(root, "activation", &format!("{}.json", candidate_hash)),
            &receipt,
        )?;
    }

    Ok(receipt)
}
