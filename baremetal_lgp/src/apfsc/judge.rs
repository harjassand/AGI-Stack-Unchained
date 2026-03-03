use std::fs;
use std::path::Path;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{Instant, SystemTime, UNIX_EPOCH};

use serde::Serialize;

use crate::apfsc::archive::{failure_morph, family_scores, robustness_trace, transfer_trace};
use crate::apfsc::artifacts::{
    digest_json, read_json, read_pointer, receipt_path, write_json_atomic, write_pointer,
};
use crate::apfsc::bank::{load_payload_index_for_windows, WindowBank};
use crate::apfsc::bridge::validate_warm_refinement;
use crate::apfsc::bytecoder::score_panel_with_resid_scales;
use crate::apfsc::candidate::{load_candidate, validate_candidate_artifacts, CandidateBundle};
use crate::apfsc::config::Phase1Config;
use crate::apfsc::constellation::load_constellation;
use crate::apfsc::errors::{io_err, Result};
use crate::apfsc::hardware_oracle::SafetyBudget;
use crate::apfsc::ingress::judge::{
    load_pending_admissions, store_pending_admissions, PendingAdmission,
};
use crate::apfsc::normalization::{evaluate_static_panel, PanelComparison};
use crate::apfsc::qd_archive::upsert_cell;
use crate::apfsc::robustness::{evaluate_robustness, RobustnessEvaluation};
use crate::apfsc::transfer::{evaluate_transfer, TransferEvaluation};
use crate::apfsc::types::{
    BridgeReceipt, ByteScoreReceipt, ConstellationManifest, EvalMode, JudgeBatchReport,
    JudgeDecision, JudgeRejectReason, MorphologyDescriptor, PromotionClass, PromotionReceipt,
    QdCellRecord, RecentFamilyGainReceipt, SearchLawAbReceipt, SearchLawOfflineReceipt,
    SearchLawPack, SplitKind,
};

fn clamp01(v: f64) -> f64 {
    v.clamp(0.0, 1.0)
}

#[derive(Debug, Clone, Copy, serde::Serialize, serde::Deserialize, PartialEq, Eq)]
pub struct JudgePhase3Profile {
    pub calls: u64,
    pub total_ms: u64,
    pub last_ms: u64,
}

static JUDGE_PHASE3_CALLS: AtomicU64 = AtomicU64::new(0);
static JUDGE_PHASE3_TOTAL_MS: AtomicU64 = AtomicU64::new(0);
static JUDGE_PHASE3_LAST_MS: AtomicU64 = AtomicU64::new(0);

struct JudgePhase3Timer {
    started: Instant,
}

impl JudgePhase3Timer {
    fn new() -> Self {
        Self {
            started: Instant::now(),
        }
    }
}

impl Drop for JudgePhase3Timer {
    fn drop(&mut self) {
        let elapsed_ms = self
            .started
            .elapsed()
            .as_millis()
            .min(u128::from(u64::MAX)) as u64;
        JUDGE_PHASE3_CALLS.fetch_add(1, Ordering::Relaxed);
        JUDGE_PHASE3_TOTAL_MS.fetch_add(elapsed_ms, Ordering::Relaxed);
        JUDGE_PHASE3_LAST_MS.store(elapsed_ms, Ordering::Relaxed);
    }
}

pub fn judge_phase3_profile() -> JudgePhase3Profile {
    JudgePhase3Profile {
        calls: JUDGE_PHASE3_CALLS.load(Ordering::Relaxed),
        total_ms: JUDGE_PHASE3_TOTAL_MS.load(Ordering::Relaxed),
        last_ms: JUDGE_PHASE3_LAST_MS.load(Ordering::Relaxed),
    }
}

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
                promotion_class: Some(candidate.manifest.promotion_class.clone()),
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
                recent_family_receipt_hash: None,
                bridge_receipt_hash: None,
                canary_required,
                canary_result: None,
                rollback_target_hash: None,
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
        promotion_class: None,
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
        recent_family_receipt_hash: None,
        bridge_receipt_hash: None,
        canary_required: false,
        canary_result: None,
        rollback_target_hash: None,
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
    if matches!(candidate.manifest.promotion_class, PromotionClass::S)
        && evals.holdout_static.delta_bpb < cfg.phase3.promotion.s_class_min_static_delta_bpb
    {
        return Ok(phase2_reject_receipt(
            candidate,
            incumbent,
            JudgeRejectReason::SClassEpsilonFail,
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
        promotion_class: Some(candidate.manifest.promotion_class.clone()),
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
        recent_family_receipt_hash: None,
        bridge_receipt_hash: None,
        canary_required: matches!(candidate.manifest.promotion_class, PromotionClass::A)
            && cfg.judge.require_canary_for_a,
        canary_result: None,
        rollback_target_hash: None,
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
    let omega_mode = crate::apfsc::artifacts::omega_mode_enabled();
    if !omega_mode
        && receipt.improved_families.len() < constellation.normalization.min_improved_families as usize
    {
        return Some(JudgeRejectReason::InsufficientCrossFamilyEvidence);
    }
    if !omega_mode
        && receipt.nonprotected_improved_families.len()
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
        promotion_class: Some(candidate.manifest.promotion_class.clone()),
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
        recent_family_receipt_hash: None,
        bridge_receipt_hash: None,
        canary_required: false,
        canary_result: None,
        rollback_target_hash: None,
        snapshot_hash: candidate.manifest.snapshot_hash.clone(),
        protocol_version: evals.holdout_static.receipt.protocol_version.clone(),
        constellation_id: Some(evals.holdout_static.receipt.constellation_id.clone()),
    }
}

fn is_structural_arch_class(cls: PromotionClass) -> bool {
    matches!(
        cls,
        PromotionClass::A | PromotionClass::PWarm | PromotionClass::PCold
    )
}

fn is_class_r_family_id(family_id: &str) -> bool {
    let family = family_id.to_ascii_lowercase();
    family.starts_with("class_r")
        || family.contains("class_r")
        || family.contains("synthetic_alien")
        || family.contains("coev_r")
}

fn has_class_r_supremacy(evals: &Phase2CandidateEvaluations) -> bool {
    let public = evals
        .public_static
        .receipt
        .improved_families
        .iter()
        .any(|f| is_class_r_family_id(f));
    let holdout = evals
        .holdout_static
        .receipt
        .improved_families
        .iter()
        .any(|f| is_class_r_family_id(f));
    public || holdout
}

fn class_r_mdl_surprisal_bits(evals: &Phase2CandidateEvaluations) -> Option<f64> {
    let mut class_r_ids: Vec<String> = evals
        .public_static
        .family_deltas
        .keys()
        .filter(|f| is_class_r_family_id(f))
        .cloned()
        .collect();
    if class_r_ids.is_empty() {
        return None;
    }
    class_r_ids.sort();
    class_r_ids.dedup();

    let mut p = Vec::with_capacity(class_r_ids.len());
    let mut q = Vec::with_capacity(class_r_ids.len());
    for family_id in class_r_ids {
        let public_delta = evals
            .public_static
            .family_deltas
            .get(&family_id)
            .copied()
            .unwrap_or(0.0)
            .max(0.0);
        let holdout_delta = evals
            .holdout_static
            .family_deltas
            .get(&family_id)
            .copied()
            .unwrap_or(0.0)
            .max(0.0);
        // Public phase acts as the candidate's prediction over the class-R family energy landscape.
        p.push(public_delta + 1e-9);
        // Holdout phase acts as realized thermodynamic outcome.
        q.push(holdout_delta + 1e-9);
    }
    let p_sum: f64 = p.iter().sum();
    let q_sum: f64 = q.iter().sum();
    if p_sum <= 0.0 || q_sum <= 0.0 {
        return None;
    }
    let mut kl_bits = 0.0;
    for (pi_raw, qi_raw) in p.iter().zip(q.iter()) {
        let pi = *pi_raw / p_sum;
        let qi = *qi_raw / q_sum;
        kl_bits += pi * (pi / qi).log2();
    }
    Some(kl_bits.max(0.0))
}

fn class_r_telemetry_surprisal_bits(root: &Path, candidate: &CandidateBundle) -> Option<f64> {
    let samples = crate::apfsc::afferent::load_recent_samples(root, 2);
    if samples.len() < 2 {
        return None;
    }
    let prev = &samples[samples.len() - 2].telemetry;
    let cur = &samples[samples.len() - 1].telemetry;
    let prev_load = clamp01(prev.loadavg_1m as f64 / prev.available_cores.max(1) as f64);
    let prev_power = clamp01(prev.power_proxy_watts as f64 / 12.0);
    let mut seed = vec![
        (prev_load * 255.0).round() as u8,
        (prev_power * 255.0).round() as u8,
        (clamp01(prev.thermal_pressure as f64) * 255.0).round() as u8,
        (clamp01(prev.cpu_speed_limit_pct as f64 / 100.0) * 255.0).round() as u8,
    ];
    if seed.is_empty() {
        seed.push(0);
    }
    let mut window = Vec::with_capacity(128);
    while window.len() < 128 {
        window.extend(seed.iter().copied());
    }
    window.truncate(128);

    let trace = crate::apfsc::scir::interp::run_program(&candidate.arch_program, &window).ok()?;
    if trace.feature.is_empty() {
        return None;
    }
    let pred_load = clamp01((trace.feature[0] as f64).tanh() * 0.5 + 0.5);
    let pred_power = if trace.feature.len() > 1 {
        clamp01((trace.feature[1] as f64).tanh() * 0.5 + 0.5)
    } else {
        pred_load
    };
    let target_load = clamp01(cur.loadavg_1m as f64 / cur.available_cores.max(1) as f64);
    let target_power = clamp01(cur.power_proxy_watts as f64 / 12.0);
    let mse = ((pred_load - target_load).powi(2) + (pred_power - target_power).powi(2)) * 0.5;
    let likelihood = (1.0 - mse).clamp(1e-6, 1.0);
    Some((-likelihood.log2()).max(0.0))
}

fn class_r_surprisal_bits(
    root: &Path,
    candidate: &CandidateBundle,
    evals: &Phase2CandidateEvaluations,
) -> Option<f64> {
    let mdl = class_r_mdl_surprisal_bits(evals);
    let telemetry = class_r_telemetry_surprisal_bits(root, candidate);
    match (mdl, telemetry) {
        (Some(m), Some(t)) => Some(m + t),
        (Some(m), None) => Some(m),
        (None, Some(t)) => Some(t),
        (None, None) => None,
    }
}

#[derive(Debug, Clone, Copy, Serialize)]
struct ParetoVector {
    struct_complexity: f64,
    thermodynamic_surprisal: f64,
    execution_speed: f64,
}

fn pareto_dominates(candidate: ParetoVector, incumbent: ParetoVector) -> bool {
    let eps = 1e-9;
    let no_worse = candidate.struct_complexity <= incumbent.struct_complexity + eps
        && candidate.thermodynamic_surprisal <= incumbent.thermodynamic_surprisal + eps
        && candidate.execution_speed <= incumbent.execution_speed + eps;
    let strictly_better = candidate.struct_complexity < incumbent.struct_complexity - eps
        || candidate.thermodynamic_surprisal < incumbent.thermodynamic_surprisal - eps
        || candidate.execution_speed < incumbent.execution_speed - eps;
    no_worse && strictly_better
}

fn pareto_vector_for_candidate(
    _root: &Path,
    candidate: &CandidateBundle,
    evals: &Phase2CandidateEvaluations,
    constellation: &ConstellationManifest,
    class_r_surprisal: Option<f64>,
) -> ParetoVector {
    let codelen_ref = constellation.normalization.codelen_ref_bytes.max(1);
    let code_penalty = crate::apfsc::normalization::code_penalty_bpb(candidate, codelen_ref)
        .unwrap_or(evals.holdout_static.receipt.code_penalty_bpb.max(0.0));
    let node_count = candidate.arch_program.nodes.len() as f64;
    ParetoVector {
        struct_complexity: code_penalty + node_count / 2048.0,
        thermodynamic_surprisal: class_r_surprisal.unwrap_or(0.0),
        // Lower is better: proxy execution cost from graph size and schedule limits.
        execution_speed: node_count
            / (candidate.manifest.resource_envelope.max_steps.max(1) as f64)
            * 1e6,
    }
}

fn pareto_vector_for_incumbent(
    root: &Path,
    incumbent: &CandidateBundle,
    constellation: &ConstellationManifest,
) -> ParetoVector {
    let codelen_ref = constellation.normalization.codelen_ref_bytes.max(1);
    let code_penalty = crate::apfsc::normalization::code_penalty_bpb(incumbent, codelen_ref)
        .unwrap_or(0.0)
        .max(0.0);
    let node_count = incumbent.arch_program.nodes.len() as f64;
    ParetoVector {
        struct_complexity: code_penalty + node_count / 2048.0,
        thermodynamic_surprisal: class_r_telemetry_surprisal_bits(root, incumbent).unwrap_or(0.0),
        execution_speed: node_count
            / (incumbent.manifest.resource_envelope.max_steps.max(1) as f64)
            * 1e6,
    }
}

fn push_pareto_lateral_qd(
    root: &Path,
    candidate: &CandidateBundle,
    constellation: &ConstellationManifest,
    public_delta_bpb: f64,
    novelty_score: f64,
) -> Result<()> {
    let morphology_hash = digest_json(&(
        candidate.manifest.promotion_class,
        candidate.build_meta.lane.clone(),
        candidate.manifest.candidate_hash.clone(),
        "pareto_lateral",
        constellation.constellation_id.clone(),
    ))?;
    let qd_cell_id = digest_json(&(
        morphology_hash.clone(),
        constellation.snapshot_hash.clone(),
        "pareto",
    ))?;
    let qd = QdCellRecord {
        cell_id: qd_cell_id,
        descriptor: MorphologyDescriptor {
            paradigm_signature_hash: morphology_hash,
            scheduler_class: "pareto".to_string(),
            memory_law_kind: "thermo-lateral".to_string(),
            macro_density_bin: "mid".to_string(),
            state_bytes_bin: "small".to_string(),
            family_profile_bin: "thermo_dominant".to_string(),
        },
        occupant_candidate_hash: candidate.manifest.candidate_hash.clone(),
        public_quality_score: public_delta_bpb,
        novelty_score: novelty_score.max(0.0),
        last_updated_epoch: SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|d| d.as_secs())
            .unwrap_or(0),
    };
    let _ = upsert_cell(root, &constellation.snapshot_hash, qd);
    Ok(())
}

fn phase3_matrix_rule_label(
    candidate_cls: PromotionClass,
    incumbent_cls: PromotionClass,
) -> &'static str {
    if matches!(candidate_cls, PromotionClass::S) {
        "Rule 1"
    } else if is_structural_arch_class(candidate_cls) && matches!(incumbent_cls, PromotionClass::S)
    {
        "Rule 2"
    } else if is_structural_arch_class(candidate_cls) && is_structural_arch_class(incumbent_cls) {
        "Rule 3"
    } else {
        "Rule Fallback"
    }
}

fn phase3_static_gate_reject_reason(
    candidate_cls: PromotionClass,
    incumbent_cls: PromotionClass,
    delta_bpb: f64,
    panel_margin_bpb: f64,
    s_class_min_static_delta_bpb: f64,
    paradigm_shift_allowance_bpb: f64,
    margin_reason: JudgeRejectReason,
) -> Option<JudgeRejectReason> {
    if matches!(candidate_cls, PromotionClass::S) {
        // Rule 1: S-class must strictly improve over incumbent by epsilon.
        // Omega mode delegates this stress test to Demon Lane instead of a static epsilon gate.
        if !crate::apfsc::artifacts::omega_mode_enabled()
            && delta_bpb <= s_class_min_static_delta_bpb
        {
            return Some(JudgeRejectReason::SClassEpsilonFail);
        }
        return None;
    }

    if is_structural_arch_class(candidate_cls) {
        if matches!(incumbent_cls, PromotionClass::S) {
            // Rule 2: structural class can spend a bounded MDL allowance to dethrone S.
            let allowance = paradigm_shift_allowance_bpb.max(0.0);
            if delta_bpb < -allowance {
                return Some(margin_reason);
            }
            return None;
        }
        if is_structural_arch_class(incumbent_cls) {
            // Rule 3: once structural is incumbent, no subsidy is allowed.
            if delta_bpb <= 0.0 {
                return Some(margin_reason);
            }
            return None;
        }
    }

    if delta_bpb < panel_margin_bpb {
        return Some(margin_reason);
    }
    None
}

#[derive(Debug, Serialize)]
struct DethroningAuditReceipt {
    candidate_hash: String,
    incumbent_hash: String,
    candidate_promotion_class: PromotionClass,
    incumbent_promotion_class: PromotionClass,
    matrix_rule: String,
    public_static_delta_bpb: f64,
    holdout_static_delta_bpb: f64,
    transfer_holdout_delta_bpb: Option<f64>,
    robust_holdout_delta_bpb: Option<f64>,
    improved_family_count: usize,
    regressed_family_count: usize,
    decision: JudgeDecision,
    reason: String,
    reject_reason: Option<String>,
    failed_gate: Option<String>,
    snapshot_hash: String,
    constellation_id: String,
    protocol_version: String,
    class_r_supremacy: bool,
    class_r_surprisal_bits: Option<f64>,
    static_allowance_bpb: f64,
    candidate_pareto: ParetoVector,
    incumbent_pareto: ParetoVector,
    pareto_override: bool,
    pareto_lateral_qd_pushed: bool,
    evaluated_unix_s: u64,
}

fn write_dethroning_audit(root: &Path, audit: &DethroningAuditReceipt) -> Result<()> {
    let path = receipt_path(
        root,
        "dethroning_audit",
        &format!("{}.json", audit.candidate_hash),
    );
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|e| io_err(parent, e))?;
    }
    write_json_atomic(&path, audit)
}

fn upsert_incubator_pointer(
    root: &Path,
    candidate_hash: &str,
    static_delta_bpb: f64,
) -> Result<bool> {
    let current = read_pointer(root, "active_incubator_pointer").ok();
    let mut should_replace = true;
    if let Some(current_hash) = current {
        if current_hash == candidate_hash {
            should_replace = false;
        } else {
            let current_receipt_path =
                receipt_path(root, "judge", &format!("{}.json", current_hash));
            if current_receipt_path.exists() {
                if let Ok(current_receipt) = read_json::<PromotionReceipt>(&current_receipt_path) {
                    if static_delta_bpb <= current_receipt.weighted_static_public_delta_bpb {
                        should_replace = false;
                    }
                }
            }
        }
    }
    if should_replace {
        write_pointer(root, "active_incubator_pointer", candidate_hash)?;
    }
    Ok(should_replace)
}

#[cfg(test)]
mod static_gate_tests {
    use super::phase3_static_gate_reject_reason;
    use crate::apfsc::types::{JudgeRejectReason, PromotionClass};

    #[test]
    fn s_class_requires_strict_epsilon_gain() {
        let eps = 0.005;
        assert_eq!(
            phase3_static_gate_reject_reason(
                PromotionClass::S,
                PromotionClass::S,
                eps,
                0.0,
                eps,
                0.10,
                JudgeRejectReason::NoPublicMargin,
            ),
            Some(JudgeRejectReason::SClassEpsilonFail)
        );
        assert_eq!(
            phase3_static_gate_reject_reason(
                PromotionClass::S,
                PromotionClass::S,
                eps + 1e-9,
                0.0,
                eps,
                0.10,
                JudgeRejectReason::NoPublicMargin,
            ),
            None
        );
    }

    #[test]
    fn structural_can_spend_allowance_only_against_s() {
        assert_eq!(
            phase3_static_gate_reject_reason(
                PromotionClass::PCold,
                PromotionClass::S,
                -0.09,
                0.0,
                0.0,
                0.10,
                JudgeRejectReason::NoHoldoutMargin,
            ),
            None
        );
        assert_eq!(
            phase3_static_gate_reject_reason(
                PromotionClass::PCold,
                PromotionClass::S,
                -0.1000001,
                0.0,
                0.0,
                0.10,
                JudgeRejectReason::NoHoldoutMargin,
            ),
            Some(JudgeRejectReason::NoHoldoutMargin)
        );
    }

    #[test]
    fn structural_vs_structural_requires_strict_improvement() {
        assert_eq!(
            phase3_static_gate_reject_reason(
                PromotionClass::PWarm,
                PromotionClass::PCold,
                0.0,
                0.0,
                0.0,
                0.10,
                JudgeRejectReason::NoPublicMargin,
            ),
            Some(JudgeRejectReason::NoPublicMargin)
        );
        assert_eq!(
            phase3_static_gate_reject_reason(
                PromotionClass::PWarm,
                PromotionClass::A,
                0.001,
                0.0,
                0.0,
                0.10,
                JudgeRejectReason::NoPublicMargin,
            ),
            None
        );
    }
}

pub fn judge_phase3_candidate(
    root: &Path,
    candidate: &CandidateBundle,
    incumbent: &CandidateBundle,
    constellation: &ConstellationManifest,
    cfg: &Phase1Config,
    evals: &Phase2CandidateEvaluations,
    bridge_receipt: Option<&BridgeReceipt>,
    recent_family: Option<&RecentFamilyGainReceipt>,
) -> Result<PromotionReceipt> {
    let _timer = JudgePhase3Timer::new();
    let mut reject_reason: Option<JudgeRejectReason> = None;
    let mut failed_gate: Option<&'static str> = None;
    let mut protected_floor_failures = Vec::<String>::new();
    let cls = candidate.manifest.promotion_class;
    let incumbent_cls = incumbent.manifest.promotion_class;
    let matrix_rule = phase3_matrix_rule_label(cls, incumbent_cls).to_string();
    let allowance = cfg.phase3.promotion.paradigm_shift_allowance_bpb.max(0.0);
    let class_r_supremacy = has_class_r_supremacy(evals);
    let class_r_surprisal = class_r_surprisal_bits(root, candidate, evals);
    let class_r_allowance = if class_r_supremacy
        && is_structural_arch_class(cls)
        && matches!(incumbent_cls, PromotionClass::S)
    {
        let base = cfg.phase3.promotion.class_r_takeover_allowance_bpb.max(0.0);
        let max_surprisal = cfg.phase3.promotion.class_r_max_surprisal_bits.max(1e-9);
        let scale = class_r_surprisal
            .map(|s| (1.0 - (s / max_surprisal).clamp(0.0, 1.0)).max(0.0))
            .unwrap_or(0.0);
        base * scale
    } else {
        0.0
    };
    let transfer_delta = evals.holdout_transfer.as_ref().map(|v| v.delta_bpb);
    let robust_delta = evals.holdout_robust.as_ref().map(|v| v.delta_bpb);
    let incubator_resident = read_pointer(root, "active_incubator_pointer")
        .ok()
        .as_deref()
        == Some(candidate.manifest.candidate_hash.as_str());
    // Exit strategy hook: once the incubator resident has transfer+robust receipts,
    // remove allowance and require a strict static dethrone.
    let static_allowance_bpb =
        if incubator_resident && transfer_delta.is_some() && robust_delta.is_some() {
            class_r_allowance
        } else {
            allowance + class_r_allowance
        };

    if reject_reason.is_none() && class_r_supremacy && is_structural_arch_class(cls) {
        let max_surprisal = cfg.phase3.promotion.class_r_max_surprisal_bits.max(0.0);
        match class_r_surprisal {
            Some(bits) if bits > max_surprisal => {
                reject_reason = Some(JudgeRejectReason::RecentFamilyGainFail);
                failed_gate = Some("ClassR.SurprisalGate");
            }
            None => {
                reject_reason = Some(JudgeRejectReason::RecentFamilyGainFail);
                failed_gate = Some("ClassR.MissingSurprisalSignal");
            }
            _ => {}
        }
    }

    // Shared gates.
    if let Some(reason) = phase3_static_gate_reject_reason(
        cls,
        incumbent_cls,
        evals.public_static.delta_bpb,
        constellation.normalization.public_static_margin_bpb,
        cfg.phase3.promotion.s_class_min_static_delta_bpb,
        static_allowance_bpb,
        JudgeRejectReason::NoPublicMargin,
    ) {
        reject_reason = Some(reason);
        failed_gate = Some("PublicStaticMarginGate");
    }
    if reject_reason.is_none() && !evals.public_static.protected_floor_failures.is_empty() {
        protected_floor_failures = evals.public_static.protected_floor_failures.clone();
        reject_reason = Some(JudgeRejectReason::ProtectedFamilyRegress);
        failed_gate = Some("PublicProtectedFloorGate");
    }
    if reject_reason.is_none() {
        if let Some(reason) = coverage_reject_reason(&evals.public_static.receipt, constellation) {
            reject_reason = Some(reason);
            failed_gate = Some("PublicCoverageGate");
        }
    }
    if reject_reason.is_none() {
        if let Some(reason) = phase3_static_gate_reject_reason(
            cls,
            incumbent_cls,
            evals.holdout_static.delta_bpb,
            constellation.normalization.holdout_static_margin_bpb,
            cfg.phase3.promotion.s_class_min_static_delta_bpb,
            static_allowance_bpb,
            JudgeRejectReason::NoHoldoutMargin,
        ) {
            reject_reason = Some(reason);
            failed_gate = Some("HoldoutStaticMarginGate");
        }
    }
    if reject_reason.is_none() && !evals.holdout_static.protected_floor_failures.is_empty() {
        protected_floor_failures = evals.holdout_static.protected_floor_failures.clone();
        reject_reason = Some(JudgeRejectReason::ProtectedFamilyRegress);
        failed_gate = Some("HoldoutProtectedFloorGate");
    }
    if reject_reason.is_none() {
        if let Some(reason) = coverage_reject_reason(&evals.holdout_static.receipt, constellation) {
            reject_reason = Some(reason);
            failed_gate = Some("HoldoutCoverageGate");
        }
    }

    if reject_reason.is_none() {
        match cls {
            PromotionClass::S => {}
            PromotionClass::A => {
                if transfer_delta.is_none() {
                    reject_reason = Some(JudgeRejectReason::TransferRegression);
                    failed_gate = Some("A.MissingTransferReceipt");
                } else if transfer_delta.unwrap_or(f64::NEG_INFINITY)
                    < constellation.normalization.holdout_transfer_margin_bpb
                {
                    reject_reason = Some(JudgeRejectReason::TransferRegression);
                    failed_gate = Some("A.TransferDeltaGate");
                } else if robust_delta.is_none() {
                    reject_reason = Some(JudgeRejectReason::RobustRegression);
                    failed_gate = Some("A.MissingRobustReceipt");
                } else if robust_delta.unwrap_or(f64::NEG_INFINITY)
                    < constellation.normalization.holdout_robust_margin_bpb
                {
                    reject_reason = Some(JudgeRejectReason::RobustRegression);
                    failed_gate = Some("A.RobustDeltaGate");
                } else if let Some(bridge) = bridge_receipt {
                    if !bridge.pass || bridge.bridge_kind != "Warm" {
                        reject_reason = Some(JudgeRejectReason::WarmRefinementFail);
                        failed_gate = Some("A.WarmBridgeGate");
                    }
                } else if candidate.bridge_pack.is_none() {
                    reject_reason = Some(JudgeRejectReason::WarmRefinementFail);
                    failed_gate = Some("A.MissingWarmBridgeReceipt");
                }
            }
            PromotionClass::PWarm => {
                if transfer_delta.is_none() {
                    reject_reason = Some(JudgeRejectReason::TransferRegression);
                    failed_gate = Some("PWarm.MissingTransferReceipt");
                } else if transfer_delta.unwrap_or(f64::NEG_INFINITY)
                    < cfg.phase3.promotion.p_warm_min_transfer_delta_bpb
                {
                    reject_reason = Some(JudgeRejectReason::TransferRegression);
                    failed_gate = Some("PWarm.TransferDeltaGate");
                } else if robust_delta.is_none() {
                    reject_reason = Some(JudgeRejectReason::RobustRegression);
                    failed_gate = Some("PWarm.MissingRobustReceipt");
                } else if robust_delta.unwrap_or(0.0)
                    < -cfg.phase3.promotion.p_warm_max_robust_regress_bpb
                {
                    reject_reason = Some(JudgeRejectReason::RobustRegression);
                    failed_gate = Some("PWarm.RobustDeltaGate");
                } else if let Some(recent) = recent_family {
                    if !recent.pass
                        || recent.max_recent_family_gain_bpb
                            < cfg.phase3.promotion.p_warm_min_recent_family_gain_bpb
                    {
                        reject_reason = Some(JudgeRejectReason::RecentFamilyGainFail);
                        failed_gate = Some("PWarm.RecentFamilyGainGate");
                    }
                } else {
                    reject_reason = Some(JudgeRejectReason::RecentFamilyGainFail);
                    failed_gate = Some("PWarm.MissingRecentFamilyReceipt");
                }
                if reject_reason.is_none() {
                    if let Some(bridge) = bridge_receipt {
                        if !bridge.pass || bridge.bridge_kind != "Warm" {
                            reject_reason = Some(JudgeRejectReason::WarmRefinementFail);
                            failed_gate = Some("PWarm.WarmBridgeGate");
                        }
                    } else {
                        reject_reason = Some(JudgeRejectReason::WarmRefinementFail);
                        failed_gate = Some("PWarm.MissingWarmBridgeReceipt");
                    }
                }
            }
            PromotionClass::PCold => {
                if transfer_delta.is_none() {
                    reject_reason = Some(JudgeRejectReason::PColdMarginInsufficient);
                    failed_gate = Some("PCold.MissingTransferReceipt");
                } else if transfer_delta.unwrap_or(f64::NEG_INFINITY)
                    < cfg.phase3.promotion.p_cold_min_transfer_delta_bpb
                {
                    reject_reason = Some(JudgeRejectReason::PColdMarginInsufficient);
                    failed_gate = Some("PCold.TransferDeltaGate");
                } else if evals.holdout_static.receipt.improved_families.len()
                    < cfg.phase3.promotion.p_cold_min_improved_families as usize
                    && !crate::apfsc::artifacts::omega_mode_enabled()
                {
                    reject_reason = Some(JudgeRejectReason::InsufficientCrossFamilyEvidence);
                    failed_gate = Some("PCold.CrossFamilyEvidenceGate");
                } else if let Some(recent) = recent_family {
                    if !recent.pass
                        || recent.max_recent_family_gain_bpb
                            < cfg.phase3.promotion.p_cold_min_recent_family_gain_bpb
                    {
                        reject_reason = Some(JudgeRejectReason::RecentFamilyGainFail);
                        failed_gate = Some("PCold.RecentFamilyGainGate");
                    }
                } else {
                    reject_reason = Some(JudgeRejectReason::RecentFamilyGainFail);
                    failed_gate = Some("PCold.MissingRecentFamilyReceipt");
                }
                if reject_reason.is_none() {
                    if let Some(bridge) = bridge_receipt {
                        if !bridge.pass || bridge.bridge_kind != "Cold" {
                            reject_reason = Some(JudgeRejectReason::ColdBoundaryFail);
                            failed_gate = Some("PCold.ColdBoundaryGate");
                        }
                    } else {
                        reject_reason = Some(JudgeRejectReason::ColdBoundaryFail);
                        failed_gate = Some("PCold.MissingColdBoundaryReceipt");
                    }
                }
                if reject_reason.is_none() && read_pointer(root, "rollback_candidate").is_err() {
                    reject_reason = Some(JudgeRejectReason::RollbackTargetMissing);
                    failed_gate = Some("PCold.RollbackTargetGate");
                }
            }
            PromotionClass::G => {}
            PromotionClass::GDisabled => {
                reject_reason = Some(JudgeRejectReason::ParadigmClassMismatch);
                failed_gate = Some("ParadigmClassMismatchGate");
            }
        }
    }

    let candidate_pareto =
        pareto_vector_for_candidate(root, candidate, evals, constellation, class_r_surprisal);
    let incumbent_pareto = pareto_vector_for_incumbent(root, incumbent, constellation);
    let omniscience_override = is_structural_arch_class(cls)
        && incumbent_pareto.thermodynamic_surprisal.is_finite()
        && incumbent_pareto.thermodynamic_surprisal > 0.0
        && candidate_pareto.thermodynamic_surprisal.is_finite()
        && candidate_pareto.thermodynamic_surprisal
            <= incumbent_pareto.thermodynamic_surprisal * 0.5;
    let pareto_override = is_structural_arch_class(cls)
        && pareto_dominates(candidate_pareto, incumbent_pareto)
        && matches!(
            reject_reason,
            Some(
                JudgeRejectReason::NoPublicMargin
                    | JudgeRejectReason::NoHoldoutMargin
                    | JudgeRejectReason::InsufficientCrossFamilyEvidence
                    | JudgeRejectReason::RecentFamilyGainFail
                    | JudgeRejectReason::TransferRegression
                    | JudgeRejectReason::PColdMarginInsufficient
            )
        );
    if pareto_override {
        reject_reason = None;
        failed_gate = Some("ParetoDominanceOverride");
    }

    let thermo_better_but_slower = is_structural_arch_class(cls)
        && candidate_pareto.thermodynamic_surprisal
            + cfg.phase4.searchlaw_ergodic_temperature_floor
            < incumbent_pareto.thermodynamic_surprisal
        && candidate_pareto.execution_speed > incumbent_pareto.execution_speed
        && !pareto_override;
    let mut pareto_lateral_qd_pushed = false;
    if reject_reason.is_some() && thermo_better_but_slower {
        let novelty =
            incumbent_pareto.thermodynamic_surprisal - candidate_pareto.thermodynamic_surprisal;
        let _ = push_pareto_lateral_qd(
            root,
            candidate,
            constellation,
            evals.public_static.delta_bpb,
            novelty,
        );
        pareto_lateral_qd_pushed = true;
    }
    if omniscience_override {
        reject_reason = None;
        failed_gate = Some("OmniscienceOverride");
    }

    let rule2_static_pass = matches!(cls, PromotionClass::PWarm | PromotionClass::PCold)
        && matches!(incumbent_cls, PromotionClass::S)
        && evals.public_static.delta_bpb >= -static_allowance_bpb
        && evals.holdout_static.delta_bpb >= -static_allowance_bpb;
    let missing_transfer_or_robust = matches!(
        failed_gate,
        Some("PWarm.MissingTransferReceipt")
            | Some("PWarm.MissingRobustReceipt")
            | Some("PCold.MissingTransferReceipt")
            | Some("PCold.MissingRobustReceipt")
    );
    let incubator_asylum =
        reject_reason.is_some() && rule2_static_pass && missing_transfer_or_robust;

    let canary_required = if omniscience_override {
        false
    } else {
        match cls {
            PromotionClass::PWarm | PromotionClass::PCold => true,
            PromotionClass::A => cfg.judge.require_canary_for_a,
            PromotionClass::G => true,
            _ => false,
        }
    };

    let mut incubator_pointer_updated = None;
    let decision = if incubator_asylum {
        incubator_pointer_updated = Some(upsert_incubator_pointer(
            root,
            &candidate.manifest.candidate_hash,
            evals.public_static.delta_bpb,
        )?);
        JudgeDecision::PromoteIncubator
    } else if reject_reason.is_some() {
        JudgeDecision::Reject
    } else {
        JudgeDecision::Promote
    };
    let reason = if incubator_asylum {
        "Promote(Incubator)".to_string()
    } else if omniscience_override {
        "Promote(OmniscienceOverride)".to_string()
    } else {
        reject_reason
            .as_ref()
            .map(|r| r.as_reason())
            .unwrap_or_else(|| "Promote".to_string())
    };
    let reject_reason_label = reject_reason.as_ref().map(|r| format!("{r:?}"));
    let evaluated_unix_s = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);

    let receipt = PromotionReceipt {
        candidate_hash: candidate.manifest.candidate_hash.clone(),
        incumbent_hash: incumbent.manifest.candidate_hash.clone(),
        decision,
        reason,
        promotion_class: Some(cls),
        public_delta_bits: 0.0,
        holdout_delta_bits: 0.0,
        anchor_regress_bits: bridge_receipt
            .and_then(|b| b.anchor_regret_bpb)
            .unwrap_or(0.0),
        weighted_static_public_delta_bpb: evals.public_static.delta_bpb,
        weighted_static_holdout_delta_bpb: evals.holdout_static.delta_bpb,
        weighted_transfer_holdout_delta_bpb: transfer_delta,
        weighted_robust_holdout_delta_bpb: robust_delta,
        improved_family_ids: evals.holdout_static.receipt.improved_families.clone(),
        regressed_family_ids: evals.holdout_static.receipt.regressed_families.clone(),
        protected_floor_failures,
        recent_family_receipt_hash: recent_family.and_then(|r| digest_json(r).ok()),
        bridge_receipt_hash: bridge_receipt.and_then(|b| digest_json(b).ok()),
        canary_required,
        canary_result: None,
        rollback_target_hash: read_pointer(root, "rollback_candidate").ok(),
        snapshot_hash: candidate.manifest.snapshot_hash.clone(),
        protocol_version: constellation.protocol_version.clone(),
        constellation_id: Some(constellation.constellation_id.clone()),
    };

    if is_structural_arch_class(cls) {
        let mut audit = DethroningAuditReceipt {
            candidate_hash: candidate.manifest.candidate_hash.clone(),
            incumbent_hash: incumbent.manifest.candidate_hash.clone(),
            candidate_promotion_class: cls,
            incumbent_promotion_class: incumbent_cls,
            matrix_rule,
            public_static_delta_bpb: evals.public_static.delta_bpb,
            holdout_static_delta_bpb: evals.holdout_static.delta_bpb,
            transfer_holdout_delta_bpb: transfer_delta,
            robust_holdout_delta_bpb: robust_delta,
            improved_family_count: evals.holdout_static.receipt.improved_families.len(),
            regressed_family_count: evals.holdout_static.receipt.regressed_families.len(),
            decision: receipt.decision,
            reason: receipt.reason.clone(),
            reject_reason: reject_reason_label,
            failed_gate: failed_gate.map(|g| g.to_string()),
            snapshot_hash: candidate.manifest.snapshot_hash.clone(),
            constellation_id: constellation.constellation_id.clone(),
            protocol_version: constellation.protocol_version.clone(),
            class_r_supremacy,
            class_r_surprisal_bits: class_r_surprisal,
            static_allowance_bpb,
            candidate_pareto,
            incumbent_pareto,
            pareto_override,
            pareto_lateral_qd_pushed,
            evaluated_unix_s,
        };
        if incubator_asylum {
            // Retain overwrite/no-overwrite state in the structured audit.
            let suffix = match incubator_pointer_updated {
                Some(true) => " [IncubatorPointerUpdated]",
                Some(false) => " [IncubatorPointerRetained]",
                None => "",
            };
            if let Some(g) = audit.failed_gate.as_mut() {
                g.push_str(suffix);
            } else {
                audit.failed_gate = Some(format!("IncubatorAsylum{}", suffix));
            }
        }
        write_dethroning_audit(root, &audit)?;
    }

    Ok(receipt)
}

pub fn judge_searchlaw_candidate(
    candidate: &SearchLawPack,
    incumbent: &SearchLawPack,
    offline: &SearchLawOfflineReceipt,
    ab: &SearchLawAbReceipt,
    _cfg: &Phase1Config,
    snapshot_hash: &str,
    constellation_id: &str,
    protocol_version: &str,
) -> PromotionReceipt {
    let mut reject = None::<JudgeRejectReason>;
    if crate::apfsc::searchlaw_eval::audit_forbidden_inputs(candidate).is_err() {
        reject = Some(JudgeRejectReason::ForbiddenSearchLawInput);
    }
    if !offline.pass {
        reject = Some(JudgeRejectReason::SearchLawOfflineFail);
    }
    if reject.is_none() && !ab.pass {
        reject = Some(JudgeRejectReason::SearchLawAbFail);
    }
    if reject.is_none() && ab.challenge_regression {
        // Ergodic/pseudo-Pareto pass may temporarily accept challenge drift while searching
        // sparse valleys. If AB marked pass, keep it admissible here.
        if !ab.ergodic_drift_accepted && !ab.pareto_dominates_incumbent {
            reject = Some(JudgeRejectReason::SearchLawAbFail);
        }
    }
    if reject.is_none() && ab.safety_regression {
        // SearchLaw canary gate: candidate must not increase unsafe outcomes.
        reject = Some(JudgeRejectReason::CanaryFail);
    }

    let delta = ab.candidate_yield_per_compute - ab.incumbent_yield_per_compute;
    let decision = if reject.is_some() {
        JudgeDecision::Reject
    } else {
        JudgeDecision::Promote
    };
    let canary_result = if ab.safety_regression {
        Some("fail".to_string())
    } else {
        Some("pass".to_string())
    };

    PromotionReceipt {
        candidate_hash: candidate.manifest_hash.clone(),
        incumbent_hash: incumbent.manifest_hash.clone(),
        decision,
        reason: reject
            .as_ref()
            .map(|r| r.as_reason())
            .unwrap_or_else(|| "Promote".to_string()),
        promotion_class: Some(PromotionClass::G),
        public_delta_bits: 0.0,
        holdout_delta_bits: 0.0,
        anchor_regress_bits: 0.0,
        weighted_static_public_delta_bpb: delta,
        weighted_static_holdout_delta_bpb: delta,
        weighted_transfer_holdout_delta_bpb: Some(delta),
        weighted_robust_holdout_delta_bpb: Some(if ab.safety_regression { -1.0 } else { 0.0 }),
        improved_family_ids: if reject.is_none() {
            vec!["searchlaw_yield_per_compute".to_string()]
        } else {
            Vec::new()
        },
        regressed_family_ids: if reject.is_none() {
            Vec::new()
        } else {
            vec!["searchlaw_yield_per_compute".to_string()]
        },
        protected_floor_failures: Vec::new(),
        recent_family_receipt_hash: Some(offline.searchlaw_hash.clone()),
        bridge_receipt_hash: Some(ab.candidate_searchlaw_hash.clone()),
        canary_required: true,
        canary_result,
        rollback_target_hash: None,
        snapshot_hash: snapshot_hash.to_string(),
        protocol_version: protocol_version.to_string(),
        constellation_id: Some(constellation_id.to_string()),
    }
}
