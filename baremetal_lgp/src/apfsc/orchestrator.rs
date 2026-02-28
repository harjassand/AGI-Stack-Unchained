use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;

use crate::apfsc::archive::{error_atlas, failure_morph, genealogy, hardware_trace};
use crate::apfsc::bank::{
    load_bank, load_family_panel_windows, load_payload_index_for_windows, WindowBank,
};
use crate::apfsc::canary::run_phase2_canary;
use crate::apfsc::candidate::{
    load_active_candidate, rehash_candidate, save_candidate, set_phase2_build_meta, CandidateBundle,
};
use crate::apfsc::config::Phase1Config;
use crate::apfsc::constellation::resolve_constellation;
use crate::apfsc::errors::{ApfscError, Result};
use crate::apfsc::hardware_oracle::{load_oracle, oracle_penalty, OracleFeatures};
use crate::apfsc::headpack::HeadOnlyAdaGradLaw;
use crate::apfsc::ingress::judge::PendingAdmission;
use crate::apfsc::judge::{
    evaluate_candidate_split, judge_phase2_candidate, run_batch, write_split_receipt,
    Phase2CandidateEvaluations,
};
use crate::apfsc::lanes;
use crate::apfsc::normalization::evaluate_static_panel;
use crate::apfsc::robustness::evaluate_robustness;
use crate::apfsc::scir::verify::verify_program;
use crate::apfsc::transfer::evaluate_transfer;
use crate::apfsc::types::{
    EpochReport, EvalMode, JudgeBatchReport, JudgeDecision, PanelKind, PublicEvalRecord, SplitKind,
    WitnessSelection,
};

pub fn run_epoch(root: &Path, cfg: &Phase1Config) -> Result<EpochReport> {
    let active = load_active_candidate(root)?;
    let snapshot = load_active_snapshot_hash(root)?;
    if active.manifest.snapshot_hash != snapshot {
        return Err(ApfscError::Validation(
            "active candidate snapshot mismatch".to_string(),
        ));
    }

    let banks = load_window_banks_for_active_snapshot(root)?;
    let all_public_windows = collect_split(&banks, SplitKind::Public);

    let witnesses = error_atlas::update_error_atlas(
        root,
        &all_public_windows,
        cfg.witness.count,
        cfg.witness.rotation,
    )?;

    let truth = lanes::truth::generate(&active, cfg)?;
    let equiv_raw = lanes::equivalence::generate(&active, cfg)?;

    let train_windows = collect_split(&banks, SplitKind::Train);
    let public_windows = all_public_windows.clone();
    let mut public_path_windows = Vec::new();
    public_path_windows.extend(train_windows.iter().cloned());
    public_path_windows.extend(public_windows.iter().cloned());
    public_path_windows.extend(witnesses.selected.iter().cloned());
    let payloads = load_payload_index_for_windows(root, &public_path_windows)?;
    let equiv = lanes::equivalence::filter_witness_equality(
        &active,
        equiv_raw,
        &witnesses.selected,
        &payloads,
    )?;

    let incubated =
        lanes::incubator::generate(&active, cfg, &train_windows, &public_windows, &payloads)?;
    let splice = lanes::incubator::materialize_splice_candidates(&active, incubated, cfg)?;

    let cold = lanes::cold_frontier_stub::record_only(root, &active, cfg)?;

    let mut pool = merge_and_dedup([truth, equiv, splice, cold].concat());
    pool = verify_and_bound(pool)?;
    let law = HeadOnlyAdaGradLaw::from_train_config(&cfg.train);
    let max_trained = (cfg.limits.max_public_workers as usize)
        .saturating_mul(2)
        .max(1);
    let mut trained = 0usize;
    for cand in &mut pool {
        if trained >= max_trained {
            break;
        }
        if cand.build_meta.lane != "truth" && cand.build_meta.lane != "incubator" {
            continue;
        }
        let _stats = law.train(
            &cand.arch_program,
            &mut cand.state_pack,
            &mut cand.head_pack,
            &train_windows,
            &payloads,
        )?;
        rehash_candidate(cand)?;
        trained += 1;
    }
    pool = merge_and_dedup(pool);

    let epoch_idx = current_epoch_index(root)?;
    pool = failure_morph::apply_taboo(root, pool, epoch_idx)?;
    pool = witness_prefilter(&active, pool, &witnesses, &payloads)?;
    for cand in &pool {
        save_candidate(root, cand)?;
    }

    let incumbent_public = evaluate_candidate_split(root, &active, SplitKind::Public, &banks)?;

    let ranked = rank_by_public_gain_then_oracle(root, &incumbent_public, pool, &banks)?;
    let limited: Vec<CandidateBundle> = ranked
        .into_iter()
        .take(cfg.lanes.max_public_candidates)
        .collect();

    let mut public_receipts = Vec::new();
    for cand in &limited {
        let receipt = evaluate_candidate_split(root, cand, SplitKind::Public, &banks)?;
        write_split_receipt(root, &receipt)?;
        public_receipts.push(receipt);
    }

    let admissions =
        admit_holdout_candidates(&active, &incumbent_public, &limited, &public_receipts, cfg);
    let judge_report = run_batch(root, &active, admissions, &banks, cfg)?;
    let canary_report = crate::apfsc::canary::drain_queue(root, &banks, cfg)?;

    genealogy::append_epoch(root, &judge_report, &canary_report)?;
    hardware_trace::append_epoch(root, &public_receipts, &judge_report, &canary_report)?;

    Ok(EpochReport {
        public_receipts,
        judge_report,
        canary_report,
    })
}

fn load_active_snapshot_hash(root: &Path) -> Result<String> {
    crate::apfsc::artifacts::read_pointer(root, "active_snapshot")
}

fn load_window_banks_for_active_snapshot(root: &Path) -> Result<Vec<WindowBank>> {
    let active_snapshot = crate::apfsc::artifacts::read_pointer(root, "active_snapshot")?;
    let snap: crate::apfsc::types::EpochSnapshot =
        crate::apfsc::artifacts::load_snapshot(root, &active_snapshot)?;

    let mut families = BTreeSet::new();
    for pack_hash in &snap.reality_roots {
        let manifest_path = root
            .join("packs/reality")
            .join(pack_hash)
            .join("manifest.json");
        if !manifest_path.exists() {
            continue;
        }
        let manifest: crate::apfsc::types::PackManifest =
            crate::apfsc::artifacts::read_json(&manifest_path)?;
        if let Some(fam) = manifest.family_id {
            families.insert(fam);
        }
    }

    let mut banks = Vec::new();
    for fam in families {
        banks.push(load_bank(root, &fam)?);
    }
    Ok(banks)
}

fn collect_split(banks: &[WindowBank], split: SplitKind) -> Vec<crate::apfsc::types::WindowRef> {
    let mut out = Vec::new();
    for b in banks {
        out.extend(b.split(split).iter().cloned());
    }
    out
}

fn merge_and_dedup(candidates: Vec<CandidateBundle>) -> Vec<CandidateBundle> {
    let mut seen = BTreeSet::new();
    let mut out = Vec::new();
    for c in candidates {
        if seen.insert(c.manifest.candidate_hash.clone()) {
            out.push(c);
        }
    }
    out
}

fn verify_and_bound(candidates: Vec<CandidateBundle>) -> Result<Vec<CandidateBundle>> {
    let mut out = Vec::new();
    for c in candidates {
        if verify_program(&c.arch_program, &c.manifest.resource_envelope).is_ok() {
            out.push(c);
        }
    }
    Ok(out)
}

fn witness_prefilter(
    active: &CandidateBundle,
    candidates: Vec<CandidateBundle>,
    witnesses: &WitnessSelection,
    payloads: &BTreeMap<String, Vec<u8>>,
) -> Result<Vec<CandidateBundle>> {
    if witnesses.selected.is_empty() {
        return Ok(candidates);
    }
    let parent_bins = witness_bin_bits(active, &witnesses.selected, payloads)?;

    let mut out = Vec::new();
    for c in candidates {
        if c.build_meta.lane == "equivalence" {
            out.push(c);
            continue;
        }
        let cand_bins = witness_bin_bits(&c, &witnesses.selected, payloads)?;
        let mut has_bin_gain = false;
        for (bin, parent_bits) in &parent_bins {
            let cand_bits = *cand_bins.get(bin).unwrap_or(&f64::INFINITY);
            if cand_bits <= *parent_bits {
                has_bin_gain = true;
                break;
            }
        }
        if has_bin_gain {
            out.push(c);
        }
    }
    Ok(out)
}

fn rank_by_public_gain_then_oracle(
    root: &Path,
    incumbent_public: &crate::apfsc::types::ByteScoreReceipt,
    candidates: Vec<CandidateBundle>,
    banks: &[WindowBank],
) -> Result<Vec<CandidateBundle>> {
    let model = load_oracle(root)?;
    let mut scored = Vec::<(f64, f64, CandidateBundle)>::new();
    for c in candidates {
        let public = evaluate_candidate_split(root, &c, SplitKind::Public, banks)?;
        let gain = incumbent_public.total_bits - public.total_bits;
        let features = OracleFeatures {
            op_count: c.arch_program.nodes.len() as f64,
            feature_dim: c
                .arch_program
                .nodes
                .iter()
                .find(|n| n.id == c.arch_program.outputs.feature_node)
                .map(|n| n.out_dim as f64)
                .unwrap_or(1.0),
            scan_hidden_dim: c
                .arch_program
                .nodes
                .iter()
                .find_map(|n| match n.op {
                    crate::apfsc::scir::ast::ScirOp::SimpleScan { hidden_dim, .. } => {
                        Some(hidden_dim as f64)
                    }
                    _ => None,
                })
                .unwrap_or(0.0),
            window_len: c.arch_program.input_len as f64,
        };
        let penalty = oracle_penalty(&model, features);
        scored.push((gain, penalty, c));
    }
    scored.sort_by(|a, b| {
        b.0.partial_cmp(&a.0)
            .unwrap_or(std::cmp::Ordering::Equal)
            .then_with(|| a.1.partial_cmp(&b.1).unwrap_or(std::cmp::Ordering::Equal))
    });
    Ok(scored.into_iter().map(|(_, _, c)| c).collect())
}

fn admit_holdout_candidates(
    active: &CandidateBundle,
    incumbent_public: &crate::apfsc::types::ByteScoreReceipt,
    candidates: &[CandidateBundle],
    public_receipts: &[crate::apfsc::types::ByteScoreReceipt],
    cfg: &Phase1Config,
) -> Vec<PendingAdmission> {
    let mut receipt_map: BTreeMap<&str, &crate::apfsc::types::ByteScoreReceipt> = BTreeMap::new();
    for r in public_receipts {
        receipt_map.insert(&r.candidate_hash, r);
    }

    let mut admissions = Vec::new();
    for c in candidates {
        if let Some(r) = receipt_map.get(c.manifest.candidate_hash.as_str()) {
            let delta = incumbent_public.total_bits - r.total_bits;
            if delta >= cfg.judge.public_min_delta_bits {
                admissions.push(PendingAdmission {
                    candidate_hash: c.manifest.candidate_hash.clone(),
                    snapshot_hash: c.manifest.snapshot_hash.clone(),
                    public_delta_bits: delta,
                });
            }
        }
    }

    if admissions.is_empty() {
        // Ensure judge emits deterministic receipts each epoch.
        admissions.push(PendingAdmission {
            candidate_hash: active.manifest.candidate_hash.clone(),
            snapshot_hash: active.manifest.snapshot_hash.clone(),
            public_delta_bits: 0.0,
        });
    }

    admissions.truncate(cfg.judge.max_holdout_admissions);
    admissions
}

fn current_epoch_index(root: &Path) -> Result<u64> {
    let entries: Vec<error_atlas::ErrorAtlasEntry> =
        crate::apfsc::artifacts::read_jsonl(&root.join("archive/error_atlas.jsonl"))?;
    Ok(entries.len() as u64)
}

fn witness_bin_bits(
    candidate: &CandidateBundle,
    witnesses: &[crate::apfsc::types::WindowRef],
    payloads: &BTreeMap<String, Vec<u8>>,
) -> Result<BTreeMap<String, f64>> {
    let mut out = BTreeMap::<String, f64>::new();
    for w in witnesses {
        let bin = crate::apfsc::constants::ERROR_ATLAS_BINS
            [(w.start as usize) % crate::apfsc::constants::ERROR_ATLAS_BINS.len()]
        .to_string();
        let one = vec![w.clone()];
        let s = crate::apfsc::bytecoder::score_panel_with_resid_scales(
            &candidate.arch_program,
            &candidate.head_pack,
            Some(&candidate.state_pack.resid_weights),
            payloads,
            &one,
        )?;
        *out.entry(bin).or_insert(0.0) += s.total_bits;
    }
    Ok(out)
}

pub fn collect_public_records(
    receipts: &[crate::apfsc::types::ByteScoreReceipt],
) -> Vec<PublicEvalRecord> {
    receipts
        .iter()
        .map(|r| PublicEvalRecord {
            candidate_hash: r.candidate_hash.clone(),
            receipt: r.clone(),
        })
        .collect()
}

pub fn run_phase2_epoch(
    root: &Path,
    cfg: &Phase1Config,
    requested_constellation: Option<&str>,
) -> Result<EpochReport> {
    let active = load_active_candidate(root)?;
    let constellation = resolve_constellation(root, requested_constellation)?;
    if active.manifest.snapshot_hash != constellation.snapshot_hash {
        return Err(ApfscError::Validation(
            "active candidate snapshot / constellation mismatch".to_string(),
        ));
    }

    let mut windows_by_family = BTreeMap::<String, Vec<crate::apfsc::types::WindowRef>>::new();
    for fam in &constellation.family_specs {
        let rows =
            load_family_panel_windows(root, &fam.family_id, PanelKind::StaticPublic.as_key())?;
        windows_by_family.insert(fam.family_id.clone(), rows);
    }
    let witnesses =
        error_atlas::update_family_error_atlas(root, &constellation, &windows_by_family)?;

    let mut truth = lanes::truth::generate(&active, cfg)?;
    let mut equiv = lanes::equivalence::generate(&active, cfg)?;
    let mut train_windows = Vec::new();
    let mut public_windows = Vec::new();
    for fam in &constellation.family_specs {
        train_windows.extend(
            load_family_panel_windows(root, &fam.family_id, PanelKind::Train.as_key())?.into_iter(),
        );
        public_windows.extend(
            load_family_panel_windows(root, &fam.family_id, PanelKind::StaticPublic.as_key())?
                .into_iter(),
        );
    }
    let mut public_path_windows = train_windows.clone();
    public_path_windows.extend(public_windows.iter().cloned());
    public_path_windows.extend(witnesses.selected.iter().cloned());
    let payloads = load_payload_index_for_windows(root, &public_path_windows)?;
    let mut incubated =
        lanes::incubator::generate(&active, cfg, &train_windows, &public_windows, &payloads)?;
    let mut splice =
        lanes::incubator::materialize_splice_candidates(&active, incubated.split_off(0), cfg)?;

    apply_phase2_lane_quotas(&constellation, &mut truth, &mut equiv, &mut splice, cfg)?;

    let mut pool = merge_and_dedup([truth, equiv, splice].concat());
    pool = verify_and_bound(pool)?;
    for cand in &pool {
        save_candidate(root, cand)?;
    }

    let witness_survivors = witness_prefilter_phase2(
        &active,
        pool,
        &witnesses.selected,
        &payloads,
        &constellation,
    )?;

    let mut public_static = Vec::<(
        CandidateBundle,
        crate::apfsc::normalization::PanelComparison,
    )>::new();
    for cand in witness_survivors
        .into_iter()
        .take(crate::apfsc::constants::MAX_STATIC_PUBLIC_CANDIDATES)
    {
        let static_cmp = evaluate_static_panel(
            root,
            &cand,
            &active,
            &constellation,
            PanelKind::StaticPublic,
        )?;
        crate::apfsc::artifacts::write_json_atomic(
            &crate::apfsc::artifacts::receipt_path(
                root,
                "public_static",
                &format!("{}.json", cand.manifest.candidate_hash),
            ),
            &static_cmp.receipt,
        )?;
        public_static.push((cand, static_cmp));
    }
    public_static.sort_by(|a, b| {
        b.1.delta_bpb
            .partial_cmp(&a.1.delta_bpb)
            .unwrap_or(std::cmp::Ordering::Equal)
    });

    let mut public_transfer_map = BTreeMap::new();
    let mut public_robust_map = BTreeMap::new();
    for (cand, _) in public_static
        .iter()
        .take(crate::apfsc::constants::MAX_TRANSFER_PUBLIC_CANDIDATES)
    {
        if !matches!(
            cand.manifest.promotion_class,
            crate::apfsc::types::PromotionClass::A
        ) {
            continue;
        }
        let x = match evaluate_transfer(root, cand, &active, &constellation, EvalMode::Public) {
            Ok(v) => v,
            Err(_) => continue,
        };
        crate::apfsc::artifacts::write_json_atomic(
            &crate::apfsc::artifacts::receipt_path(
                root,
                "public_transfer",
                &format!("{}.json", cand.manifest.candidate_hash),
            ),
            &x.receipt,
        )?;
        public_transfer_map.insert(cand.manifest.candidate_hash.clone(), x);
    }
    for (cand, _) in public_static
        .iter()
        .take(crate::apfsc::constants::MAX_ROBUST_PUBLIC_CANDIDATES)
    {
        if !matches!(
            cand.manifest.promotion_class,
            crate::apfsc::types::PromotionClass::A
        ) {
            continue;
        }
        let r = match evaluate_robustness(root, cand, &active, &constellation, EvalMode::Public) {
            Ok(v) => v,
            Err(_) => continue,
        };
        crate::apfsc::artifacts::write_json_atomic(
            &crate::apfsc::artifacts::receipt_path(
                root,
                "public_robust",
                &format!("{}.json", cand.manifest.candidate_hash),
            ),
            &r.receipt,
        )?;
        public_robust_map.insert(cand.manifest.candidate_hash.clone(), r);
    }

    let mut holdout_admissions = Vec::<CandidateBundle>::new();
    for (cand, static_cmp) in &public_static {
        if holdout_admissions.len() >= crate::apfsc::constants::MAX_HOLDOUT_STATIC_ADMISSIONS {
            break;
        }
        if !public_static_spend_gate_pass(static_cmp, &constellation) {
            continue;
        }
        if matches!(
            cand.manifest.promotion_class,
            crate::apfsc::types::PromotionClass::A
        ) {
            let t = match public_transfer_map.get(&cand.manifest.candidate_hash) {
                Some(v) => v,
                None => continue,
            };
            let r = match public_robust_map.get(&cand.manifest.candidate_hash) {
                Some(v) => v,
                None => continue,
            };
            if t.delta_bpb < 0.0
                || r.delta_bpb < 0.0
                || !t.protected_floor_failures.is_empty()
                || !r.protected_floor_failures.is_empty()
            {
                continue;
            }
        }
        holdout_admissions.push(cand.clone());
    }
    if holdout_admissions.is_empty() {
        let fallback_public = evaluate_static_panel(
            root,
            &active,
            &active,
            &constellation,
            PanelKind::StaticPublic,
        )?;
        crate::apfsc::artifacts::write_json_atomic(
            &crate::apfsc::artifacts::receipt_path(
                root,
                "public_static",
                &format!("{}.json", active.manifest.candidate_hash),
            ),
            &fallback_public.receipt,
        )?;
        public_static.push((active.clone(), fallback_public));
        holdout_admissions.push(active.clone());
    }

    let mut holdout_static_map = BTreeMap::new();
    for cand in &holdout_admissions {
        let s = evaluate_static_panel(
            root,
            cand,
            &active,
            &constellation,
            PanelKind::StaticHoldout,
        )?;
        crate::apfsc::artifacts::write_json_atomic(
            &crate::apfsc::artifacts::receipt_path(
                root,
                "holdout_static",
                &format!("{}.json", cand.manifest.candidate_hash),
            ),
            &s.receipt,
        )?;
        holdout_static_map.insert(cand.manifest.candidate_hash.clone(), s);
    }

    let xfer_robust_admissions: Vec<CandidateBundle> = holdout_admissions
        .iter()
        .filter(|c| {
            matches!(
                c.manifest.promotion_class,
                crate::apfsc::types::PromotionClass::A
            )
        })
        .take(crate::apfsc::constants::MAX_HOLDOUT_XFER_ROBUST_ADMISSIONS)
        .cloned()
        .collect();

    let mut holdout_transfer_map = BTreeMap::new();
    let mut holdout_robust_map = BTreeMap::new();
    for cand in &xfer_robust_admissions {
        let x = match evaluate_transfer(root, cand, &active, &constellation, EvalMode::Holdout) {
            Ok(v) => v,
            Err(_) => continue,
        };
        crate::apfsc::artifacts::write_json_atomic(
            &crate::apfsc::artifacts::receipt_path(
                root,
                "holdout_transfer",
                &format!("{}.json", cand.manifest.candidate_hash),
            ),
            &x.receipt,
        )?;
        holdout_transfer_map.insert(cand.manifest.candidate_hash.clone(), x);

        let r = match evaluate_robustness(root, cand, &active, &constellation, EvalMode::Holdout) {
            Ok(v) => v,
            Err(_) => continue,
        };
        crate::apfsc::artifacts::write_json_atomic(
            &crate::apfsc::artifacts::receipt_path(
                root,
                "holdout_robust",
                &format!("{}.json", cand.manifest.candidate_hash),
            ),
            &r.receipt,
        )?;
        holdout_robust_map.insert(cand.manifest.candidate_hash.clone(), r);
    }

    let mut judge_receipts = Vec::new();
    let mut canary_evaluated = Vec::new();
    let mut canary_activated = None::<String>;
    let mut passing = Vec::<PromotionBundle>::new();

    for cand in holdout_admissions {
        let public_static_eval = match public_static
            .iter()
            .find(|(c, _)| c.manifest.candidate_hash == cand.manifest.candidate_hash)
        {
            Some((_, s)) => s.clone(),
            None => continue,
        };
        let holdout_static_eval = match holdout_static_map.get(&cand.manifest.candidate_hash) {
            Some(v) => v.clone(),
            None => continue,
        };
        let evals = Phase2CandidateEvaluations {
            public_static: public_static_eval,
            public_transfer: public_transfer_map
                .get(&cand.manifest.candidate_hash)
                .cloned(),
            public_robust: public_robust_map
                .get(&cand.manifest.candidate_hash)
                .cloned(),
            holdout_static: holdout_static_eval,
            holdout_transfer: holdout_transfer_map
                .get(&cand.manifest.candidate_hash)
                .cloned(),
            holdout_robust: holdout_robust_map
                .get(&cand.manifest.candidate_hash)
                .cloned(),
        };

        let mut receipt =
            judge_phase2_candidate(root, &cand, &active, &constellation, cfg, &evals)?;
        if receipt.decision == JudgeDecision::Promote {
            let promotion_bundle = build_promotion_bundle(&cand, &receipt, &evals);
            if receipt.canary_required {
                let canary = run_phase2_canary(
                    root,
                    &cand.manifest.candidate_hash,
                    &active.manifest.candidate_hash,
                    &constellation.constellation_id,
                    cfg,
                )?;
                canary_evaluated.push(cand.manifest.candidate_hash.clone());
                if canary.pass {
                    canary_activated = Some(cand.manifest.candidate_hash.clone());
                    receipt.canary_result = Some("pass".to_string());
                    passing.push(promotion_bundle);
                } else {
                    receipt.decision = JudgeDecision::Reject;
                    receipt.reason = crate::apfsc::types::JudgeRejectReason::CanaryFail.as_reason();
                    receipt.canary_result = Some("fail".to_string());
                }
            } else {
                passing.push(promotion_bundle);
            }
        }

        crate::apfsc::artifacts::write_json_atomic(
            &crate::apfsc::artifacts::receipt_path(
                root,
                "judge",
                &format!("{}.json", cand.manifest.candidate_hash),
            ),
            &receipt,
        )?;
        judge_receipts.push(receipt);
    }

    if canary_activated.is_none() {
        if let Some(best) = select_best_phase2(&passing) {
            crate::apfsc::judge::activate_candidate(
                root,
                &best.cand.manifest.candidate_hash,
                &best.cand.manifest.snapshot_hash,
            )?;
            crate::apfsc::artifacts::write_pointer(
                root,
                "active_constellation",
                &constellation.constellation_id,
            )?;
            crate::apfsc::artifacts::write_json_atomic(
                &crate::apfsc::artifacts::receipt_path(
                    root,
                    "activation",
                    &format!("{}.json", best.cand.manifest.candidate_hash),
                ),
                &best.receipt,
            )?;
            canary_activated = Some(best.cand.manifest.candidate_hash.clone());
        }
    }

    let judge_report = JudgeBatchReport {
        receipts: judge_receipts.clone(),
        queued_for_canary: Vec::new(),
    };
    let canary_report = crate::apfsc::types::CanaryBatchReport {
        evaluated: canary_evaluated,
        activated: canary_activated,
    };
    genealogy::append_epoch(root, &judge_report, &canary_report)?;
    hardware_trace::append_epoch(root, &[], &judge_report, &canary_report)?;

    Ok(EpochReport {
        public_receipts: Vec::new(),
        judge_report,
        canary_report,
    })
}

#[derive(Debug, Clone)]
struct PromotionBundle {
    cand: CandidateBundle,
    receipt: crate::apfsc::types::PromotionReceipt,
    static_holdout_score: f64,
    improved_family_count: usize,
    nonprotected_improved_family_count: usize,
    transfer_holdout_score: Option<f64>,
    robust_holdout_score: Option<f64>,
    code_penalty_bpb: f64,
    hardware_risk: f64,
}

fn select_best_phase2(passing: &[PromotionBundle]) -> Option<PromotionBundle> {
    let mut v = passing.to_vec();
    v.sort_by(|a, b| {
        a.static_holdout_score
            .partial_cmp(&b.static_holdout_score)
            .unwrap_or(std::cmp::Ordering::Equal)
            .then_with(|| b.improved_family_count.cmp(&a.improved_family_count))
            .then_with(|| {
                b.nonprotected_improved_family_count
                    .cmp(&a.nonprotected_improved_family_count)
            })
            .then_with(|| compare_a_optional_score(a, b, |x| x.transfer_holdout_score))
            .then_with(|| compare_a_optional_score(a, b, |x| x.robust_holdout_score))
            .then_with(|| {
                a.code_penalty_bpb
                    .partial_cmp(&b.code_penalty_bpb)
                    .unwrap_or(std::cmp::Ordering::Equal)
            })
            .then_with(|| {
                a.hardware_risk
                    .partial_cmp(&b.hardware_risk)
                    .unwrap_or(std::cmp::Ordering::Equal)
            })
            .then_with(|| {
                a.cand
                    .manifest
                    .candidate_hash
                    .cmp(&b.cand.manifest.candidate_hash)
            })
    });
    v.into_iter().next()
}

fn compare_a_optional_score(
    a: &PromotionBundle,
    b: &PromotionBundle,
    f: impl Fn(&PromotionBundle) -> Option<f64>,
) -> std::cmp::Ordering {
    let a_is_a = matches!(
        a.cand.manifest.promotion_class,
        crate::apfsc::types::PromotionClass::A
    );
    let b_is_a = matches!(
        b.cand.manifest.promotion_class,
        crate::apfsc::types::PromotionClass::A
    );
    if !(a_is_a && b_is_a) {
        return std::cmp::Ordering::Equal;
    }
    f(a).unwrap_or(f64::INFINITY)
        .partial_cmp(&f(b).unwrap_or(f64::INFINITY))
        .unwrap_or(std::cmp::Ordering::Equal)
}

fn apply_phase2_lane_quotas(
    constellation: &crate::apfsc::types::ConstellationManifest,
    truth: &mut Vec<CandidateBundle>,
    equiv: &mut Vec<CandidateBundle>,
    incubator: &mut Vec<CandidateBundle>,
    cfg: &Phase1Config,
) -> Result<()> {
    let family_ids: Vec<String> = constellation
        .family_specs
        .iter()
        .map(|f| f.family_id.clone())
        .collect();
    let required_truth = family_ids.len().saturating_add(2);
    if truth.len() < required_truth {
        return Err(ApfscError::Validation(format!(
            "phase2 truth lane quota requires at least {required_truth} candidates, found {}",
            truth.len()
        )));
    }

    for (i, fam_id) in family_ids.iter().enumerate() {
        set_phase2_build_meta(
            &mut truth[i],
            vec![fam_id.clone()],
            "truth",
            &cfg.phase2.profile_name,
        )?;
    }
    for cand in truth.iter_mut().skip(family_ids.len()).take(2) {
        set_phase2_build_meta(cand, family_ids.clone(), "truth", &cfg.phase2.profile_name)?;
    }

    let protected_family = constellation
        .family_specs
        .iter()
        .find(|f| f.floors.protected)
        .map(|f| f.family_id.clone())
        .ok_or_else(|| ApfscError::Validation("phase2 requires a protected family".to_string()))?;
    let nonprotected_family = constellation
        .family_specs
        .iter()
        .find(|f| !f.floors.protected)
        .map(|f| f.family_id.clone())
        .ok_or_else(|| {
            ApfscError::Validation("phase2 requires a nonprotected family".to_string())
        })?;

    let equiv_first = equiv.first_mut().ok_or_else(|| {
        ApfscError::Validation(
            "phase2 equivalence lane requires at least one candidate".to_string(),
        )
    })?;
    set_phase2_build_meta(
        equiv_first,
        vec![protected_family],
        "equivalence",
        &cfg.phase2.profile_name,
    )?;

    let incubator_first = incubator.first_mut().ok_or_else(|| {
        ApfscError::Validation("phase2 incubator lane requires at least one candidate".to_string())
    })?;
    set_phase2_build_meta(
        incubator_first,
        vec![nonprotected_family],
        "incubator",
        &cfg.phase2.profile_name,
    )?;
    Ok(())
}

fn public_static_spend_gate_pass(
    static_cmp: &crate::apfsc::normalization::PanelComparison,
    constellation: &crate::apfsc::types::ConstellationManifest,
) -> bool {
    if static_cmp.delta_bpb < constellation.normalization.public_static_margin_bpb {
        return false;
    }
    if !static_cmp.protected_floor_failures.is_empty() {
        return false;
    }
    coverage_pass_for_receipt(&static_cmp.receipt, constellation)
}

fn coverage_pass_for_receipt(
    receipt: &crate::apfsc::types::ConstellationScoreReceipt,
    constellation: &crate::apfsc::types::ConstellationManifest,
) -> bool {
    if receipt.improved_families.len() < constellation.normalization.min_improved_families as usize
    {
        return false;
    }
    if receipt.nonprotected_improved_families.len()
        < constellation
            .normalization
            .min_nonprotected_improved_families as usize
    {
        return false;
    }
    if constellation.normalization.require_target_subset_hit && !receipt.target_subset_pass {
        return false;
    }
    true
}

fn build_promotion_bundle(
    cand: &CandidateBundle,
    receipt: &crate::apfsc::types::PromotionReceipt,
    evals: &Phase2CandidateEvaluations,
) -> PromotionBundle {
    PromotionBundle {
        cand: cand.clone(),
        receipt: receipt.clone(),
        static_holdout_score: evals
            .holdout_static
            .receipt
            .weighted_static_holdout_bpb
            .unwrap_or(f64::INFINITY),
        improved_family_count: evals.holdout_static.receipt.improved_families.len(),
        nonprotected_improved_family_count: evals
            .holdout_static
            .receipt
            .nonprotected_improved_families
            .len(),
        transfer_holdout_score: evals
            .holdout_transfer
            .as_ref()
            .map(|v| v.candidate_weighted_bpb),
        robust_holdout_score: evals
            .holdout_robust
            .as_ref()
            .map(|v| v.candidate_weighted_bpb),
        code_penalty_bpb: evals.holdout_static.receipt.code_penalty_bpb,
        hardware_risk: cand
            .schedule_pack
            .predicted_cost
            .as_ref()
            .map(|p| p.risk_score)
            .unwrap_or(f64::INFINITY),
    }
}

fn witness_prefilter_phase2(
    active: &CandidateBundle,
    candidates: Vec<CandidateBundle>,
    witnesses: &[crate::apfsc::types::WindowRef],
    payloads: &BTreeMap<String, Vec<u8>>,
    constellation: &crate::apfsc::types::ConstellationManifest,
) -> Result<Vec<CandidateBundle>> {
    if witnesses.is_empty() {
        return Ok(candidates);
    }
    let mut base_witness_bits = Vec::with_capacity(witnesses.len());
    for w in witnesses {
        let one = vec![w.clone()];
        let s = crate::apfsc::bytecoder::score_panel_with_resid_scales(
            &active.arch_program,
            &active.head_pack,
            Some(&active.state_pack.resid_weights),
            payloads,
            &one,
        )?;
        base_witness_bits.push(s.total_bits);
    }

    let mut scored = Vec::<(f64, usize, CandidateBundle)>::new();
    for cand in candidates {
        let mut total_delta = 0.0f64;
        let mut improved_families = BTreeSet::<String>::new();
        for (idx, w) in witnesses.iter().enumerate() {
            let one = vec![w.clone()];
            let s = crate::apfsc::bytecoder::score_panel_with_resid_scales(
                &cand.arch_program,
                &cand.head_pack,
                Some(&cand.state_pack.resid_weights),
                payloads,
                &one,
            )?;
            let delta = base_witness_bits[idx] - s.total_bits;
            total_delta += delta;
            if delta > 1e-12 {
                improved_families.insert(w.family_id.clone());
            }
        }
        scored.push((total_delta, improved_families.len(), cand));
    }
    scored.sort_by(|a, b| {
        b.0.partial_cmp(&a.0)
            .unwrap_or(std::cmp::Ordering::Equal)
            .then_with(|| b.1.cmp(&a.1))
    });

    let top_band = constellation.family_specs.len().max(2).min(scored.len());
    let mut out = Vec::new();
    for (i, (delta, improved_family_count, cand)) in scored.into_iter().enumerate() {
        if improved_family_count >= 2 || i < top_band || delta > 0.0 {
            out.push(cand);
        }
    }
    Ok(out)
}
