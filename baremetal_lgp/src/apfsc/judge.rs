use std::path::Path;

use crate::apfsc::archive::failure_morph;
use crate::apfsc::artifacts::{
    read_json, read_pointer, receipt_path, write_json_atomic, write_pointer,
};
use crate::apfsc::bank::{load_payload_index_for_windows, WindowBank};
use crate::apfsc::bridge::validate_warm_refinement;
use crate::apfsc::bytecoder::score_panel_with_resid_scales;
use crate::apfsc::candidate::{load_candidate, validate_candidate_artifacts, CandidateBundle};
use crate::apfsc::config::Phase1Config;
use crate::apfsc::errors::Result;
use crate::apfsc::hardware_oracle::SafetyBudget;
use crate::apfsc::ingress::judge::{
    load_pending_admissions, store_pending_admissions, PendingAdmission,
};
use crate::apfsc::types::{
    ByteScoreReceipt, JudgeBatchReport, JudgeDecision, PromotionClass, PromotionReceipt, SplitKind,
};

pub fn evaluate_candidate_split(
    root: &Path,
    candidate: &CandidateBundle,
    split: SplitKind,
    banks: &[WindowBank],
) -> Result<ByteScoreReceipt> {
    let mut windows = Vec::new();
    for bank in banks {
        windows.extend(bank.split(split).iter().cloned());
    }
    let payloads = load_payload_index_for_windows(root, &windows)?;

    let summary = score_panel_with_resid_scales(
        &candidate.arch_program,
        &candidate.head_pack,
        Some(&candidate.state_pack.resid_weights),
        &payloads,
        &windows,
    )?;
    let wall = (windows.len() as u64).saturating_mul(candidate.arch_program.nodes.len() as u64);
    let peak_rss = candidate
        .manifest
        .resource_envelope
        .max_state_bytes
        .min(candidate.manifest.resource_envelope.peak_rss_limit_bytes);

    Ok(ByteScoreReceipt {
        candidate_hash: candidate.manifest.candidate_hash.clone(),
        snapshot_hash: candidate.manifest.snapshot_hash.clone(),
        split,
        family_scores_bits: summary.family_scores_bits,
        total_bits: summary.total_bits,
        mean_bits_per_byte: summary.mean_bits_per_byte,
        peak_rss_bytes: peak_rss,
        wall_ms: wall,
        replay_hash: summary.replay_hash,
        backend_fingerprint: crate::apfsc::scir::interp::BACKEND_FINGERPRINT.to_string(),
    })
}

pub fn write_split_receipt(root: &Path, receipt: &ByteScoreReceipt) -> Result<()> {
    let lane = match receipt.split {
        SplitKind::Public => "public",
        SplitKind::Holdout => "holdout",
        SplitKind::Canary => "canary",
        _ => "public",
    };
    let path = receipt_path(root, lane, &format!("{}.json", receipt.candidate_hash));
    write_json_atomic(&path, receipt)
}

pub fn run_batch(
    root: &Path,
    active: &CandidateBundle,
    mut admissions: Vec<PendingAdmission>,
    banks: &[WindowBank],
    cfg: &Phase1Config,
) -> Result<JudgeBatchReport> {
    let epoch_snapshot_hash = read_pointer(root, "active_snapshot")
        .unwrap_or_else(|_| active.manifest.snapshot_hash.clone());

    admissions.sort_by(|a, b| {
        b.public_delta_bits
            .partial_cmp(&a.public_delta_bits)
            .unwrap_or(std::cmp::Ordering::Equal)
    });
    admissions.truncate(cfg.judge.max_holdout_admissions);

    let incumbent_holdout = evaluate_candidate_split(root, active, SplitKind::Holdout, banks)?;
    let incumbent_anchor = evaluate_candidate_split(root, active, SplitKind::Anchor, banks)?;
    let incumbent_transfer_eval =
        evaluate_candidate_split(root, active, SplitKind::TransferEval, banks)?;

    let mut receipts = Vec::new();
    let mut queued_for_canary = Vec::new();

    for admission in admissions {
        let candidate = match load_candidate(root, &admission.candidate_hash) {
            Ok(c) => c,
            Err(_) => {
                let receipt = reject_receipt(
                    &admission.candidate_hash,
                    &active.manifest.candidate_hash,
                    "Reject(ArtifactMissing)",
                    admission.public_delta_bits,
                    0.0,
                    0.0,
                    active.manifest.snapshot_hash.clone(),
                );
                let judge_path =
                    receipt_path(root, "judge", &format!("{}.json", receipt.candidate_hash));
                write_json_atomic(&judge_path, &receipt)?;
                receipts.push(receipt);
                continue;
            }
        };

        let mut reason = None::<String>;

        if admission.public_delta_bits < cfg.judge.public_min_delta_bits {
            reason = Some("Reject(NoPublicMargin)".to_string());
        }

        if reason.is_none()
            && validate_candidate_artifacts(root, &candidate.manifest.candidate_hash).is_err()
        {
            reason = Some("Reject(ArtifactInvalid)".to_string());
        }

        let snapshot_path = root
            .join("snapshots")
            .join(format!("{}.json", candidate.manifest.snapshot_hash));
        if candidate.manifest.snapshot_hash != epoch_snapshot_hash {
            reason = Some("Reject(MissingSnapshot)".to_string());
        } else if reason.is_none() && !snapshot_path.exists() {
            reason = Some("Reject(MissingSnapshot)".to_string());
        }

        if reason.is_none() && !resource_valid(&candidate, cfg) {
            reason = Some("Reject(ResourceViolation)".to_string());
        }

        let holdout = evaluate_candidate_split(root, &candidate, SplitKind::Holdout, banks)?;
        write_split_receipt(root, &holdout)?;
        let anchor = evaluate_candidate_split(root, &candidate, SplitKind::Anchor, banks)?;

        let holdout_delta = incumbent_holdout.total_bits - holdout.total_bits;
        let anchor_regress = (anchor.total_bits - incumbent_anchor.total_bits).max(0.0);

        if reason.is_none() && holdout_delta < cfg.judge.holdout_min_delta_bits {
            reason = Some("Reject(HoldoutNoGain)".to_string());
        }
        if reason.is_none() && anchor_regress > cfg.judge.anchor_max_regress_bits {
            reason = Some("Reject(AnchorRegress)".to_string());
        }

        if reason.is_none() && matches!(candidate.manifest.promotion_class, PromotionClass::A) {
            if let Some(bridge) = &candidate.bridge_pack {
                if validate_warm_refinement(bridge).is_err() {
                    reason = Some("Reject(WarmBridgeFail)".to_string());
                }
            } else {
                reason = Some("Reject(WarmBridgeFail)".to_string());
            }
        }

        if reason.is_none() && matches!(candidate.manifest.promotion_class, PromotionClass::A) {
            let transfer =
                evaluate_candidate_split(root, &candidate, SplitKind::TransferEval, banks)?;
            let transfer_delta = incumbent_transfer_eval.total_bits - transfer.total_bits;
            if transfer_delta < cfg.judge.mini_transfer_min_delta_bits {
                reason = Some("Reject(MiniTransferFail)".to_string());
            }
        }

        if reason.is_none() {
            let replay_a = evaluate_candidate_split(root, &candidate, SplitKind::Holdout, banks)?;
            let replay_b = evaluate_candidate_split(root, &candidate, SplitKind::Holdout, banks)?;
            if replay_a.replay_hash != replay_b.replay_hash
                || !finite_receipt(&replay_a)
                || !finite_receipt(&replay_b)
            {
                reason = Some("Reject(StabilityFail)".to_string());
            }
        }

        let canary_required = matches!(candidate.manifest.promotion_class, PromotionClass::A)
            && cfg.judge.require_canary_for_a;

        let receipt = if let Some(reason) = reason {
            let rec = reject_receipt(
                &candidate.manifest.candidate_hash,
                &active.manifest.candidate_hash,
                &reason,
                admission.public_delta_bits,
                holdout_delta,
                anchor_regress,
                candidate.manifest.snapshot_hash.clone(),
            );
            failure_morph::append_reject(
                root,
                &candidate.manifest.candidate_hash,
                &candidate.build_meta.mutation_type,
                &reason,
                &candidate.manifest.snapshot_hash,
                3,
            )?;
            rec
        } else {
            PromotionReceipt {
                candidate_hash: candidate.manifest.candidate_hash.clone(),
                incumbent_hash: active.manifest.candidate_hash.clone(),
                decision: JudgeDecision::Promote,
                reason: "Promote".to_string(),
                public_delta_bits: admission.public_delta_bits,
                holdout_delta_bits: holdout_delta,
                anchor_regress_bits: anchor_regress,
                canary_required,
                canary_result: None,
                snapshot_hash: candidate.manifest.snapshot_hash.clone(),
            }
        };

        let judge_path = receipt_path(root, "judge", &format!("{}.json", receipt.candidate_hash));
        write_json_atomic(&judge_path, &receipt)?;

        if receipt.decision == JudgeDecision::Promote {
            if receipt.canary_required {
                enqueue_canary(root, &receipt.candidate_hash)?;
                queued_for_canary.push(receipt.candidate_hash.clone());
            } else {
                activate_candidate(root, &receipt.candidate_hash, &receipt.snapshot_hash)?;
                write_json_atomic(
                    &receipt_path(
                        root,
                        "activation",
                        &format!("{}.json", receipt.candidate_hash),
                    ),
                    &receipt,
                )?;
            }
        }

        receipts.push(receipt);
    }

    store_pending_admissions(root, &[])?;
    Ok(JudgeBatchReport {
        receipts,
        queued_for_canary,
    })
}

pub fn run_pending_batch(
    root: &Path,
    active: &CandidateBundle,
    banks: &[WindowBank],
    cfg: &Phase1Config,
) -> Result<JudgeBatchReport> {
    let admissions = load_pending_admissions(root)?;
    run_batch(root, active, admissions, banks, cfg)
}

pub fn activate_candidate(root: &Path, candidate_hash: &str, snapshot_hash: &str) -> Result<()> {
    let previous = read_pointer(root, "active_candidate")?;
    write_pointer(root, "rollback_candidate", &previous)?;
    write_pointer(root, "active_candidate", candidate_hash)?;
    write_pointer(root, "active_snapshot", snapshot_hash)
}

fn enqueue_canary(root: &Path, candidate_hash: &str) -> Result<()> {
    let qpath = root.join("queues/canary_queue.json");
    let mut queue: Vec<String> = if qpath.exists() {
        read_json(&qpath)?
    } else {
        Vec::new()
    };
    if !queue.iter().any(|h| h == candidate_hash) {
        queue.push(candidate_hash.to_string());
    }
    write_json_atomic(&qpath, &queue)
}

fn resource_valid(candidate: &CandidateBundle, cfg: &Phase1Config) -> bool {
    SafetyBudget::from_config(cfg)
        .validate_envelope(&candidate.manifest.resource_envelope)
        .is_ok()
}

fn finite_receipt(r: &ByteScoreReceipt) -> bool {
    r.total_bits.is_finite() && r.mean_bits_per_byte.is_finite()
}

fn reject_receipt(
    candidate_hash: &str,
    incumbent_hash: &str,
    reason: &str,
    public_delta_bits: f64,
    holdout_delta_bits: f64,
    anchor_regress_bits: f64,
    snapshot_hash: String,
) -> PromotionReceipt {
    PromotionReceipt {
        candidate_hash: candidate_hash.to_string(),
        incumbent_hash: incumbent_hash.to_string(),
        decision: JudgeDecision::Reject,
        reason: reason.to_string(),
        public_delta_bits,
        holdout_delta_bits,
        anchor_regress_bits,
        canary_required: false,
        canary_result: None,
        snapshot_hash,
    }
}
