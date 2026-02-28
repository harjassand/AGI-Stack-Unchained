use std::path::Path;

use serde::{Deserialize, Serialize};

use crate::apfsc::artifacts::{read_json, read_pointer, receipt_path, write_json_atomic};
use crate::apfsc::bank::WindowBank;
use crate::apfsc::candidate::load_candidate;
use crate::apfsc::config::Phase1Config;
use crate::apfsc::errors::Result;
use crate::apfsc::hardware_oracle::SafetyBudget;
use crate::apfsc::judge::{activate_candidate, evaluate_candidate_split};
use crate::apfsc::types::{CanaryBatchReport, JudgeDecision, PromotionReceipt, SplitKind};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct CanaryReceipt {
    pub candidate_hash: String,
    pub incumbent_hash: String,
    pub pass: bool,
    pub reason: String,
    pub candidate_bits: f64,
    pub incumbent_bits: f64,
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
                canary_required: true,
                canary_result: Some("fail".to_string()),
                snapshot_hash: candidate.manifest.snapshot_hash.clone(),
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
