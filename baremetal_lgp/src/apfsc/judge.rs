use std::path::Path;

use crate::apfsc::archive::{failure_morph, family_scores, robustness_trace, transfer_trace};
use crate::apfsc::artifacts::{
    read_json, read_pointer, receipt_path, write_json_atomic, write_pointer,
};
use crate::apfsc::bank::{load_payload_index_for_windows, WindowBank};
use crate::apfsc::bridge::validate_warm_refinement;
use crate::apfsc::bytecoder::score_panel_with_resid_scales;
use crate::apfsc::candidate::{load_candidate, validate_candidate_artifacts, CandidateBundle};
use crate::apfsc::config::Phase1Config;
use crate::apfsc::constellation::load_constellation;
use crate::apfsc::errors::Result;
use crate::apfsc::hardware_oracle::SafetyBudget;
use crate::apfsc::ingress::judge::{
    load_pending_admissions, store_pending_admissions, PendingAdmission,
};
use crate::apfsc::normalization::{evaluate_static_panel, PanelComparison};
use crate::apfsc::robustness::{evaluate_robustness, RobustnessEvaluation};
use crate::apfsc::transfer::{evaluate_transfer, TransferEvaluation};
use crate::apfsc::types::{
    ByteScoreReceipt, ConstellationManifest, EvalMode, JudgeBatchReport, JudgeDecision,
    JudgeRejectReason, PromotionClass, PromotionReceipt, SplitKind,
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
                    &cfg.protocol.version,
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
                &cfg.protocol.version,
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
                weighted_static_public_delta_bpb: 0.0,
                weighted_static_holdout_delta_bpb: 0.0,
                weighted_transfer_holdout_delta_bpb: None,
                weighted_robust_holdout_delta_bpb: None,
                improved_family_ids: Vec::new(),
                regressed_family_ids: Vec::new(),
                protected_floor_failures: Vec::new(),
                canary_required,
                canary_result: None,
                snapshot_hash: candidate.manifest.snapshot_hash.clone(),
                protocol_version: cfg.protocol.version.clone(),
                constellation_id: None,
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
    protocol_version: &str,
) -> PromotionReceipt {
    PromotionReceipt {
        candidate_hash: candidate_hash.to_string(),
        incumbent_hash: incumbent_hash.to_string(),
        decision: JudgeDecision::Reject,
        reason: reason.to_string(),
        public_delta_bits,
        holdout_delta_bits,
        anchor_regress_bits,
        weighted_static_public_delta_bpb: 0.0,
        weighted_static_holdout_delta_bpb: 0.0,
        weighted_transfer_holdout_delta_bpb: None,
        weighted_robust_holdout_delta_bpb: None,
        improved_family_ids: Vec::new(),
        regressed_family_ids: Vec::new(),
        protected_floor_failures: Vec::new(),
        canary_required: false,
        canary_result: None,
        snapshot_hash,
        protocol_version: protocol_version.to_string(),
        constellation_id: None,
    }
}

#[derive(Debug, Clone)]
pub struct Phase2CandidateEvaluations {
    pub public_static: PanelComparison,
    pub public_transfer: Option<TransferEvaluation>,
    pub public_robust: Option<RobustnessEvaluation>,
    pub holdout_static: PanelComparison,
    pub holdout_transfer: Option<TransferEvaluation>,
    pub holdout_robust: Option<RobustnessEvaluation>,
}

pub fn evaluate_phase2_candidate(
    root: &Path,
    candidate: &CandidateBundle,
    incumbent: &CandidateBundle,
    constellation: &ConstellationManifest,
) -> Result<Phase2CandidateEvaluations> {
    let public_static = evaluate_static_panel(
        root,
        candidate,
        incumbent,
        constellation,
        crate::apfsc::types::PanelKind::StaticPublic,
    )?;
    let holdout_static = evaluate_static_panel(
        root,
        candidate,
        incumbent,
        constellation,
        crate::apfsc::types::PanelKind::StaticHoldout,
    )?;

    let (public_transfer, public_robust, holdout_transfer, holdout_robust) =
        if matches!(candidate.manifest.promotion_class, PromotionClass::A) {
            (
                evaluate_transfer(root, candidate, incumbent, constellation, EvalMode::Public).ok(),
                evaluate_robustness(root, candidate, incumbent, constellation, EvalMode::Public)
                    .ok(),
                evaluate_transfer(root, candidate, incumbent, constellation, EvalMode::Holdout)
                    .ok(),
                evaluate_robustness(root, candidate, incumbent, constellation, EvalMode::Holdout)
                    .ok(),
            )
        } else {
            (None, None, None, None)
        };

    Ok(Phase2CandidateEvaluations {
        public_static,
        public_transfer,
        public_robust,
        holdout_static,
        holdout_transfer,
        holdout_robust,
    })
}

pub fn judge_phase2_candidate(
    root: &Path,
    candidate: &CandidateBundle,
    incumbent: &CandidateBundle,
    constellation: &ConstellationManifest,
    cfg: &Phase1Config,
    evals: &Phase2CandidateEvaluations,
) -> Result<PromotionReceipt> {
    if candidate.manifest.snapshot_hash != incumbent.manifest.snapshot_hash
        || candidate.manifest.snapshot_hash != constellation.snapshot_hash
    {
        return Ok(phase2_reject_receipt(
            candidate,
            incumbent,
            JudgeRejectReason::ConstellationMismatch,
            evals,
            Vec::new(),
        ));
    }
    if validate_candidate_artifacts(root, &candidate.manifest.candidate_hash).is_err() {
        return Ok(phase2_reject_receipt(
            candidate,
            incumbent,
            JudgeRejectReason::ArtifactInvalid,
            evals,
            Vec::new(),
        ));
    }
    if !resource_valid(candidate, cfg) {
        return Ok(phase2_reject_receipt(
            candidate,
            incumbent,
            JudgeRejectReason::ResourceViolation,
            evals,
            Vec::new(),
        ));
    }

    if evals.public_static.delta_bpb < constellation.normalization.public_static_margin_bpb {
        return Ok(phase2_reject_receipt(
            candidate,
            incumbent,
            JudgeRejectReason::NoPublicMargin,
            evals,
            Vec::new(),
        ));
    }
    if !evals.public_static.protected_floor_failures.is_empty() {
        return Ok(phase2_reject_receipt(
            candidate,
            incumbent,
            JudgeRejectReason::ProtectedFamilyRegress,
            evals,
            evals.public_static.protected_floor_failures.clone(),
        ));
    }
    if let Some(reason) = coverage_reject_reason(&evals.public_static.receipt, constellation) {
        return Ok(phase2_reject_receipt(
            candidate,
            incumbent,
            reason,
            evals,
            Vec::new(),
        ));
    }

    if matches!(candidate.manifest.promotion_class, PromotionClass::A) {
        let pt = match &evals.public_transfer {
            Some(v) => v,
            None => {
                return Ok(phase2_reject_receipt(
                    candidate,
                    incumbent,
                    JudgeRejectReason::TransferRegression,
                    evals,
                    Vec::new(),
                ))
            }
        };
        let pr = match &evals.public_robust {
            Some(v) => v,
            None => {
                return Ok(phase2_reject_receipt(
                    candidate,
                    incumbent,
                    JudgeRejectReason::RobustRegression,
                    evals,
                    Vec::new(),
                ))
            }
        };
        if pt.delta_bpb < 0.0 || !pt.protected_floor_failures.is_empty() {
            return Ok(phase2_reject_receipt(
                candidate,
                incumbent,
                JudgeRejectReason::TransferRegression,
                evals,
                pt.protected_floor_failures.clone(),
            ));
        }
        if pr.delta_bpb < 0.0 || !pr.protected_floor_failures.is_empty() {
            return Ok(phase2_reject_receipt(
                candidate,
                incumbent,
                JudgeRejectReason::RobustRegression,
                evals,
                pr.protected_floor_failures.clone(),
            ));
        }
    }

    if evals.holdout_static.delta_bpb < constellation.normalization.holdout_static_margin_bpb {
        return Ok(phase2_reject_receipt(
            candidate,
            incumbent,
            JudgeRejectReason::NoHoldoutMargin,
            evals,
            Vec::new(),
        ));
    }
    if !evals.holdout_static.protected_floor_failures.is_empty() {
        return Ok(phase2_reject_receipt(
            candidate,
            incumbent,
            JudgeRejectReason::ProtectedFamilyRegress,
            evals,
            evals.holdout_static.protected_floor_failures.clone(),
        ));
    }
    if let Some(reason) = coverage_reject_reason(&evals.holdout_static.receipt, constellation) {
        return Ok(phase2_reject_receipt(
            candidate,
            incumbent,
            reason,
            evals,
            Vec::new(),
        ));
    }

    let mut anchor_eval = None;
    if matches!(candidate.manifest.promotion_class, PromotionClass::A) {
        let ht = match &evals.holdout_transfer {
            Some(v) => v,
            None => {
                return Ok(phase2_reject_receipt(
                    candidate,
                    incumbent,
                    JudgeRejectReason::TransferRegression,
                    evals,
                    Vec::new(),
                ))
            }
        };
        let hr = match &evals.holdout_robust {
            Some(v) => v,
            None => {
                return Ok(phase2_reject_receipt(
                    candidate,
                    incumbent,
                    JudgeRejectReason::RobustRegression,
                    evals,
                    Vec::new(),
                ))
            }
        };
        if ht.delta_bpb < constellation.normalization.holdout_transfer_margin_bpb
            || !ht.protected_floor_failures.is_empty()
        {
            return Ok(phase2_reject_receipt(
                candidate,
                incumbent,
                JudgeRejectReason::TransferRegression,
                evals,
                ht.protected_floor_failures.clone(),
            ));
        }
        if hr.delta_bpb < constellation.normalization.holdout_robust_margin_bpb
            || !hr.protected_floor_failures.is_empty()
        {
            return Ok(phase2_reject_receipt(
                candidate,
                incumbent,
                JudgeRejectReason::RobustRegression,
                evals,
                hr.protected_floor_failures.clone(),
            ));
        }

        match &candidate.bridge_pack {
            Some(bridge) => {
                if validate_warm_refinement(bridge).is_err() {
                    return Ok(phase2_reject_receipt(
                        candidate,
                        incumbent,
                        JudgeRejectReason::WarmBridgeFail,
                        evals,
                        Vec::new(),
                    ));
                }
            }
            None => {
                return Ok(phase2_reject_receipt(
                    candidate,
                    incumbent,
                    JudgeRejectReason::WarmBridgeFail,
                    evals,
                    Vec::new(),
                ))
            }
        }

        let anchor = evaluate_static_panel(
            root,
            candidate,
            incumbent,
            constellation,
            crate::apfsc::types::PanelKind::Anchor,
        )?;
        if anchor.delta_bpb < 0.0 || !anchor.protected_floor_failures.is_empty() {
            return Ok(phase2_reject_receipt(
                candidate,
                incumbent,
                JudgeRejectReason::AnchorRegress,
                evals,
                anchor.protected_floor_failures.clone(),
            ));
        }
        anchor_eval = Some(anchor);
    }

    let replay_check = evaluate_static_panel(
        root,
        candidate,
        incumbent,
        constellation,
        crate::apfsc::types::PanelKind::StaticHoldout,
    )?;
    if replay_check.receipt.replay_hash != evals.holdout_static.receipt.replay_hash {
        return Ok(phase2_reject_receipt(
            candidate,
            incumbent,
            JudgeRejectReason::StabilityFail,
            evals,
            Vec::new(),
        ));
    }

    // Emit archive rows on pass path.
    family_scores::append_receipt(root, "public_static", &evals.public_static.receipt)?;
    family_scores::append_receipt(root, "holdout_static", &evals.holdout_static.receipt)?;
    if let Some(t) = &evals.public_transfer {
        family_scores::append_receipt(root, "public_transfer", &t.receipt)?;
        transfer_trace::append_rows(root, &t.traces)?;
    }
    if let Some(t) = &evals.holdout_transfer {
        family_scores::append_receipt(root, "holdout_transfer", &t.receipt)?;
        transfer_trace::append_rows(root, &t.traces)?;
    }
    if let Some(r) = &evals.public_robust {
        family_scores::append_receipt(root, "public_robust", &r.receipt)?;
        robustness_trace::append_rows(root, &r.traces)?;
    }
    if let Some(r) = &evals.holdout_robust {
        family_scores::append_receipt(root, "holdout_robust", &r.receipt)?;
        robustness_trace::append_rows(root, &r.traces)?;
    }
    if let Some(anchor) = &anchor_eval {
        family_scores::append_receipt(root, "anchor", &anchor.receipt)?;
    }

    Ok(PromotionReceipt {
        candidate_hash: candidate.manifest.candidate_hash.clone(),
        incumbent_hash: incumbent.manifest.candidate_hash.clone(),
        decision: JudgeDecision::Promote,
        reason: "Promote".to_string(),
        public_delta_bits: 0.0,
        holdout_delta_bits: 0.0,
        anchor_regress_bits: anchor_eval
            .as_ref()
            .map(|a| (-a.delta_bpb).max(0.0))
            .unwrap_or(0.0),
        weighted_static_public_delta_bpb: evals.public_static.delta_bpb,
        weighted_static_holdout_delta_bpb: evals.holdout_static.delta_bpb,
        weighted_transfer_holdout_delta_bpb: evals.holdout_transfer.as_ref().map(|v| v.delta_bpb),
        weighted_robust_holdout_delta_bpb: evals.holdout_robust.as_ref().map(|v| v.delta_bpb),
        improved_family_ids: evals.holdout_static.receipt.improved_families.clone(),
        regressed_family_ids: evals.holdout_static.receipt.regressed_families.clone(),
        protected_floor_failures: Vec::new(),
        canary_required: matches!(candidate.manifest.promotion_class, PromotionClass::A)
            && cfg.judge.require_canary_for_a,
        canary_result: None,
        snapshot_hash: candidate.manifest.snapshot_hash.clone(),
        protocol_version: constellation.protocol_version.clone(),
        constellation_id: Some(constellation.constellation_id.clone()),
    })
}

pub fn judge_phase2_candidate_by_constellation_id(
    root: &Path,
    candidate: &CandidateBundle,
    incumbent: &CandidateBundle,
    constellation_id: &str,
    cfg: &Phase1Config,
) -> Result<PromotionReceipt> {
    let constellation = load_constellation(root, constellation_id)?;
    let evals = evaluate_phase2_candidate(root, candidate, incumbent, &constellation)?;
    judge_phase2_candidate(root, candidate, incumbent, &constellation, cfg, &evals)
}

fn coverage_reject_reason(
    receipt: &crate::apfsc::types::ConstellationScoreReceipt,
    constellation: &ConstellationManifest,
) -> Option<JudgeRejectReason> {
    if receipt.improved_families.len() < constellation.normalization.min_improved_families as usize
    {
        return Some(JudgeRejectReason::InsufficientCrossFamilyEvidence);
    }
    if receipt.nonprotected_improved_families.len()
        < constellation
            .normalization
            .min_nonprotected_improved_families as usize
    {
        return Some(JudgeRejectReason::InsufficientCrossFamilyEvidence);
    }
    if constellation.normalization.require_target_subset_hit && !receipt.target_subset_pass {
        return Some(JudgeRejectReason::TargetSubsetMiss);
    }
    None
}

fn phase2_reject_receipt(
    candidate: &CandidateBundle,
    incumbent: &CandidateBundle,
    reason: JudgeRejectReason,
    evals: &Phase2CandidateEvaluations,
    protected_floor_failures: Vec<String>,
) -> PromotionReceipt {
    PromotionReceipt {
        candidate_hash: candidate.manifest.candidate_hash.clone(),
        incumbent_hash: incumbent.manifest.candidate_hash.clone(),
        decision: JudgeDecision::Reject,
        reason: reason.as_reason(),
        public_delta_bits: 0.0,
        holdout_delta_bits: 0.0,
        anchor_regress_bits: 0.0,
        weighted_static_public_delta_bpb: evals.public_static.delta_bpb,
        weighted_static_holdout_delta_bpb: evals.holdout_static.delta_bpb,
        weighted_transfer_holdout_delta_bpb: evals.holdout_transfer.as_ref().map(|v| v.delta_bpb),
        weighted_robust_holdout_delta_bpb: evals.holdout_robust.as_ref().map(|v| v.delta_bpb),
        improved_family_ids: evals.holdout_static.receipt.improved_families.clone(),
        regressed_family_ids: evals.holdout_static.receipt.regressed_families.clone(),
        protected_floor_failures,
        canary_required: false,
        canary_result: None,
        snapshot_hash: candidate.manifest.snapshot_hash.clone(),
        protocol_version: evals.holdout_static.receipt.protocol_version.clone(),
        constellation_id: Some(evals.holdout_static.receipt.constellation_id.clone()),
    }
}
