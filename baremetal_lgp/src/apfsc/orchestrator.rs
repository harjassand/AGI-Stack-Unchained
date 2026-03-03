use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;
use std::thread;

use rayon::prelude::*;
use serde::{Deserialize, Serialize};

use crate::apfsc::archive::{error_atlas, failure_morph, genealogy, hardware_trace};
use crate::apfsc::bank::{
    load_bank, load_family_panel_windows, load_payload_index_for_windows, WindowBank,
};
use crate::apfsc::canary::{run_phase2_canary, run_phase3_canary};
use crate::apfsc::candidate::{
    load_active_candidate, load_candidate, rehash_candidate, save_candidate, set_phase2_build_meta,
    set_phase3_build_meta, set_phase4_build_meta, CandidateBundle,
};
use crate::apfsc::challenge_scheduler::{
    load_or_build_hidden_challenge_manifest, score_hidden_challenge_gate,
};
use crate::apfsc::config::Phase1Config;
use crate::apfsc::constellation::resolve_constellation;
use crate::apfsc::credit::mint_credit;
use crate::apfsc::dependency_pack::{build_dependency_pack, write_candidate_dependency_pack};
use crate::apfsc::errors::{ApfscError, Result};
use crate::apfsc::formal_policy::{load_active_formal_policy, seed_formal_policy};
use crate::apfsc::hardware_oracle::{load_oracle, oracle_penalty, OracleFeatures};
use crate::apfsc::headpack::HeadOnlyAdaGradLaw;
use crate::apfsc::ingress::judge::PendingAdmission;
use crate::apfsc::judge::{
    evaluate_candidate_split, judge_phase2_candidate, judge_phase3_candidate,
    judge_searchlaw_candidate, run_batch, write_split_receipt, Phase2CandidateEvaluations,
};
use crate::apfsc::lanes;
use crate::apfsc::law_archive::{
    append_record as append_law_record, build_summary as build_law_summary,
    load_records as load_law_records,
};
use crate::apfsc::law_tokens::{distill_law_tokens, persist_law_tokens};
use crate::apfsc::macro_lib::load_or_build_active_registry;
use crate::apfsc::need::emit_need_tokens;
use crate::apfsc::normalization::evaluate_static_panel;
use crate::apfsc::paradigm::{
    classify_promotion_class, compute_paradigm_signature, structural_change_detected,
};
use crate::apfsc::portfolio::{
    allocate_branch_budget, cull_unproductive_branches, load_or_init_portfolio,
};
use crate::apfsc::qd_archive::upsert_cell;
use crate::apfsc::retirement::rotate_hidden_challenges;
use crate::apfsc::robustness::evaluate_robustness;
use crate::apfsc::rollback::stage_rollback_target;
use crate::apfsc::scir::ast::{AlienMutationVector, ScirNode, ScirOp};
use crate::apfsc::scir::interp::run_program;
use crate::apfsc::scir::verify::{verify_program, verify_program_with_formal_policy};
use crate::apfsc::search_law::{
    build_search_plan, ensure_active_search_law, generate_search_law_candidates,
};
use crate::apfsc::searchlaw_eval::{
    evaluate_searchlaw_ab, evaluate_searchlaw_offline, promote_search_law_if_pass,
};
use crate::apfsc::searchlaw_features::build_searchlaw_features;
use crate::apfsc::transfer::evaluate_transfer;
use crate::apfsc::types::{
    BackendKind, BackendPlan, CandidatePhase3Meta, CandidatePhase4Meta, EpochReport, EvalMode,
    JudgeBatchReport, JudgeDecision, JudgeRejectReason, MorphologyDescriptor, PanelKind,
    Phase3BuildMeta, Phase4BuildMeta, PromotionClass, PromotionReceipt, PublicEvalRecord, QdCellRecord,
    SearchObjectKind, SplitKind, WitnessSelection,
};
use crate::apfsc::yield_points::points_for_class;

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
    let path = root.join("archive/error_atlas.jsonl");
    if !crate::apfsc::artifacts::path_exists(&path) {
        return Ok(0);
    }
    let bytes = crate::apfsc::artifacts::read_bytes(&path)?;
    let text = String::from_utf8(bytes)
        .map_err(|e| ApfscError::Protocol(format!("error_atlas decode failed: {e}")))?;
    let lines = text.lines().filter(|l| !l.trim().is_empty()).count();
    Ok(lines as u64)
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
    let public_candidates: Vec<CandidateBundle> = witness_survivors
        .into_iter()
        .take(crate::apfsc::constants::MAX_STATIC_PUBLIC_CANDIDATES)
        .collect();
    let public_static_results: Vec<
        Result<(
            CandidateBundle,
            crate::apfsc::normalization::PanelComparison,
        )>,
    > = public_candidates
        .into_par_iter()
        .map(|cand| {
            let static_cmp = evaluate_static_panel(
                root,
                &cand,
                &active,
                &constellation,
                PanelKind::StaticPublic,
            )?;
            Ok((cand, static_cmp))
        })
        .collect();
    for result in public_static_results {
        public_static.push(result?);
    }
    for (cand, static_cmp) in &public_static {
        crate::apfsc::artifacts::write_json_atomic(
            &crate::apfsc::artifacts::receipt_path(
                root,
                "public_static",
                &format!("{}.json", cand.manifest.candidate_hash),
            ),
            &static_cmp.receipt,
        )?;
    }
    public_static.sort_by(|a, b| {
        b.1.delta_bpb
            .partial_cmp(&a.1.delta_bpb)
            .unwrap_or(std::cmp::Ordering::Equal)
    });

    let mut public_transfer_map = BTreeMap::new();
    let mut public_robust_map = BTreeMap::new();
    let public_a_candidates: Vec<CandidateBundle> = public_static
        .iter()
        .take(crate::apfsc::constants::MAX_TRANSFER_PUBLIC_CANDIDATES)
        .filter(|(cand, _)| {
            matches!(
                cand.manifest.promotion_class,
                crate::apfsc::types::PromotionClass::A
            )
        })
        .map(|(cand, _)| cand.clone())
        .collect();
    let transfer_results: Vec<Option<(String, crate::apfsc::transfer::TransferEvaluation)>> =
        public_a_candidates
            .par_iter()
            .map(|cand| {
                evaluate_transfer(root, cand, &active, &constellation, EvalMode::Public)
                    .ok()
                    .map(|x| (cand.manifest.candidate_hash.clone(), x))
            })
            .collect();
    for (candidate_hash, x) in transfer_results.into_iter().flatten() {
        crate::apfsc::artifacts::write_json_atomic(
            &crate::apfsc::artifacts::receipt_path(
                root,
                "public_transfer",
                &format!("{}.json", candidate_hash),
            ),
            &x.receipt,
        )?;
        public_transfer_map.insert(candidate_hash, x);
    }
    let public_robust_candidates: Vec<CandidateBundle> = public_static
        .iter()
        .take(crate::apfsc::constants::MAX_ROBUST_PUBLIC_CANDIDATES)
        .filter(|(cand, _)| {
            matches!(
                cand.manifest.promotion_class,
                crate::apfsc::types::PromotionClass::A
            )
        })
        .map(|(cand, _)| cand.clone())
        .collect();
    let robust_results: Vec<Option<(String, crate::apfsc::robustness::RobustnessEvaluation)>> =
        public_robust_candidates
            .par_iter()
            .map(|cand| {
                evaluate_robustness(root, cand, &active, &constellation, EvalMode::Public)
                    .ok()
                    .map(|r| (cand.manifest.candidate_hash.clone(), r))
            })
            .collect();
    for (candidate_hash, r) in robust_results.into_iter().flatten() {
        crate::apfsc::artifacts::write_json_atomic(
            &crate::apfsc::artifacts::receipt_path(
                root,
                "public_robust",
                &format!("{}.json", candidate_hash),
            ),
            &r.receipt,
        )?;
        public_robust_map.insert(candidate_hash, r);
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
                    crate::apfsc::artifacts::write_json_atomic(
                        &crate::apfsc::artifacts::receipt_path(
                            root,
                            "activation",
                            &format!("{}.json", cand.manifest.candidate_hash),
                        ),
                        &receipt,
                    )?;
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
        let preferred: Vec<PromotionBundle> = if cfg.phase3.allow_p_warm && !cfg.phase3.allow_p_cold
        {
            passing
                .iter()
                .filter(|p| matches!(p.cand.manifest.promotion_class, PromotionClass::PWarm))
                .cloned()
                .collect()
        } else if cfg.phase3.allow_p_cold && !cfg.phase3.allow_p_warm {
            passing
                .iter()
                .filter(|p| matches!(p.cand.manifest.promotion_class, PromotionClass::PCold))
                .cloned()
                .collect()
        } else {
            Vec::new()
        };
        let pool = if preferred.is_empty() {
            &passing
        } else {
            &preferred
        };

        if let Some(best) = select_best_phase2(pool) {
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

fn enforce_macro_mutation_mandate(
    active: &CandidateBundle,
    pool: Vec<CandidateBundle>,
) -> Result<Vec<CandidateBundle>> {
    const AST_NODE_FLOOR: usize = 250;
    let active_node_count = active.arch_program.nodes.len();
    if active_node_count >= AST_NODE_FLOOR {
        return Ok(pool);
    }

    // Force the mutator into pure structural growth mode until the active
    // topology reaches the floor. This bypasses drift/prune style proposals.
    let seed_pool = if pool.is_empty() {
        vec![active.clone()]
    } else {
        pool
    };
    let mut forced = Vec::new();
    for (idx, mut cand) in seed_pool.into_iter().enumerate() {
        let source_candidate_hash = cand.manifest.candidate_hash.clone();
        let source_mutation_type = cand.build_meta.mutation_type.clone();
        cand.arch_program = active.arch_program.clone();
        cand.head_pack = active.head_pack.clone();
        cand.state_pack = active.state_pack.clone();
        cand.schedule_pack = active.schedule_pack.clone();
        cand.bridge_pack = active.bridge_pack.clone();

        let input_feature = cand.arch_program.outputs.feature_node;
        let out_dim = cand
            .arch_program
            .nodes
            .iter()
            .find(|n| n.id == input_feature)
            .map(|n| n.out_dim)
            .unwrap_or(16)
            .max(1);
        let next_id = cand
            .arch_program
            .nodes
            .iter()
            .map(|n| n.id)
            .max()
            .unwrap_or(0)
            .saturating_add(1);
        let wrap_id = next_id;
        let passthrough_id = wrap_id.saturating_add(1);
        let seed_hash = crate::apfsc::artifacts::digest_json(&(
            "root_wrap_insert_node",
            &active.manifest.candidate_hash,
            active_node_count,
            idx,
            &source_candidate_hash,
            &source_mutation_type,
        ))?;
        cand.arch_program.nodes.push(ScirNode {
            id: wrap_id,
            op: ScirOp::Alien {
                seed_hash,
                mutation_vector: AlienMutationVector {
                    ops_added: vec![
                        "ClassMProbe::RootWrap".to_string(),
                        "MERA::BoundaryRootWrap".to_string(),
                        "Passthrough::IdentityInput".to_string(),
                    ],
                    ops_removed: vec!["Root::Unwrapped".to_string()],
                },
                fused_ops_hint: 32,
            },
            inputs: vec![input_feature],
            out_dim,
            mutable: false,
        });
        cand.arch_program.nodes.push(ScirNode {
            id: passthrough_id,
            op: ScirOp::SimpleScan {
                in_dim: 68,
                hidden_dim: 68,
            },
            inputs: vec![wrap_id],
            out_dim,
            mutable: false,
        });
        cand.arch_program.outputs.feature_node = passthrough_id;

        cand.build_meta.mutation_type = format!(
            "StructuralExpansion::MutationOp::InsertNode::RootWrap::SimpleScan68"
        );
        let mandate_note = format!(
            "macro_mutation_mandate active_nodes={} floor={} forced_op=InsertNode root_wrap=SimpleScan68(active)",
            active_node_count, AST_NODE_FLOOR
        );
        cand.build_meta.notes = Some(match cand.build_meta.notes.take() {
            Some(existing) if !existing.is_empty() => format!("{existing}; {mandate_note}"),
            _ => mandate_note,
        });
        rehash_candidate(&mut cand)?;
        forced.push(cand);
    }
    if forced.is_empty() {
        return Err(ApfscError::Validation(format!(
            "macro mutation mandate blocked epoch: active ast_node_count={} (< {}) but no structural expansion candidates were generated",
            active_node_count, AST_NODE_FLOOR
        )));
    }
    Ok(merge_and_dedup(forced))
}

fn deterministic_soft_floor_sample(parts: &[&str]) -> f64 {
    let mut h = blake3::Hasher::new();
    for p in parts {
        h.update(p.as_bytes());
        h.update(&[0x1F]);
    }
    let digest = h.finalize();
    let b = digest.as_bytes();
    let raw = u64::from_le_bytes([b[0], b[1], b[2], b[3], b[4], b[5], b[6], b[7]]);
    (raw as f64) / (u64::MAX as f64)
}

fn thermal_soft_floor_acceptance_probability(temp: f64) -> f64 {
    let t = if temp.is_finite() { temp.max(0.0) } else { 0.0 };
    (0.02 + (t / 10.0) * 0.18).clamp(0.02, 0.30)
}

pub fn run_phase3_epoch(
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

    let macro_registry =
        load_or_build_active_registry(root, &constellation.snapshot_hash, &cfg.protocol.version)?;
    let _ = crate::apfsc::macro_mine::mine_macros(
        root,
        &constellation.snapshot_hash,
        &cfg.protocol.version,
        cfg.phase3.macro_cfg.min_macro_support,
        cfg.phase3.macro_cfg.min_macro_public_gain_bpb,
        cfg.phase3.macro_cfg.min_macro_reduction_ratio,
        cfg.phase3.macro_cfg.max_induced_macros_per_epoch,
    );

    let mut windows_by_family = BTreeMap::<String, Vec<crate::apfsc::types::WindowRef>>::new();
    for fam in &constellation.family_specs {
        let rows =
            load_family_panel_windows(root, &fam.family_id, PanelKind::StaticPublic.as_key())?;
        windows_by_family.insert(fam.family_id.clone(), rows);
    }
    let witnesses =
        error_atlas::update_family_error_atlas(root, &constellation, &windows_by_family)?;

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
    let mut incubator_path_windows = train_windows.clone();
    incubator_path_windows.extend(public_windows.iter().cloned());
    let incubator_payloads = load_payload_index_for_windows(root, &incubator_path_windows)?;

    let truth = lanes::truth::generate_phase3(&active, cfg)?;
    let equiv = lanes::equivalence::generate(&active, cfg)?;
    let incubated = lanes::incubator::generate(
        &active,
        cfg,
        &train_windows,
        &public_windows,
        &incubator_payloads,
    )?;
    let splice = lanes::incubator::materialize_splice_candidates(&active, incubated, cfg)?;
    let incubator = lanes::incubator::phase3_macro_aware_candidates(&active, cfg)?;
    let frontier = lanes::cold_frontier::generate(&active, cfg)?;
    let mut pool = merge_and_dedup([truth, equiv, incubator, splice, frontier].concat());
    pool = enforce_macro_mutation_mandate(&active, pool)?;
    pool = verify_and_bound(pool)?;

    let incumbent_core_hash = crate::apfsc::artifacts::digest_json(&active.arch_program)?;
    let incumbent_sig = compute_paradigm_signature(&active, &incumbent_core_hash)?;
    let fresh_targets: Vec<String> = constellation
        .fresh_families
        .iter()
        .map(|f| f.family_id.clone())
        .collect();
    let all_targets: Vec<String> = constellation
        .family_specs
        .iter()
        .map(|f| f.family_id.clone())
        .collect();

    for cand in &mut pool {
        let cand_core_hash = crate::apfsc::artifacts::digest_json(&cand.arch_program)?;
        let cand_sig = compute_paradigm_signature(cand, &cand_core_hash)?;
        let mut classified = classify_promotion_class(
            &incumbent_sig,
            &cand_sig,
            structural_change_detected(&incumbent_core_hash, &cand_core_hash),
            cand.bridge_pack.is_some(),
            true,
        )
        .unwrap_or(cand.manifest.promotion_class);
        if cfg.phase3.allow_p_warm && !cfg.phase3.allow_p_cold && cand.bridge_pack.is_some() {
            classified = PromotionClass::PWarm;
        } else if cfg.phase3.allow_p_cold && !cfg.phase3.allow_p_warm {
            classified = PromotionClass::PCold;
        }
        cand.manifest.promotion_class = classified;
        rehash_candidate(cand)?;

        let phase3_meta = CandidatePhase3Meta {
            build: Phase3BuildMeta {
                target_families: all_targets.clone(),
                source_lane: cand.build_meta.lane.clone(),
                phase3_profile: cfg.phase3.profile.clone(),
                macro_registry_hash: macro_registry.registry_id.clone(),
                paradigm_signature_hash: crate::apfsc::artifacts::digest_json(&cand_sig)?,
                proposed_class: classified,
                fresh_target_families: fresh_targets.clone(),
            },
            backend_plan: BackendPlan {
                primary_backend: BackendKind::InterpTier0,
                public_backend: if cfg.phase3.backend.allow_graph_backend_public {
                    BackendKind::GraphBackend
                } else {
                    BackendKind::InterpTier0
                },
                canary_backend: if cfg.phase3.backend.allow_graph_backend_canary {
                    BackendKind::GraphBackend
                } else {
                    BackendKind::InterpTier0
                },
                holdout_backend: BackendKind::InterpTier0,
                graph_eligibility_hash: None,
            },
            bridge_kind: if matches!(classified, PromotionClass::PCold) {
                "Cold".to_string()
            } else {
                "Warm".to_string()
            },
        };
        set_phase3_build_meta(cand, phase3_meta)?;
        save_candidate(root, cand)?;
    }

    let mut public_path_windows = train_windows.clone();
    public_path_windows.extend(public_windows.iter().cloned());
    public_path_windows.extend(witnesses.selected.iter().cloned());
    let payloads = load_payload_index_for_windows(root, &public_path_windows)?;
    let mut survivors = witness_prefilter_phase2(
        &active,
        pool.clone(),
        &witnesses.selected,
        &payloads,
        &constellation,
    )?;
    let mut seen_survivor = BTreeSet::new();
    for c in &survivors {
        seen_survivor.insert(c.manifest.candidate_hash.clone());
    }
    for c in pool {
        if matches!(
            c.manifest.promotion_class,
            PromotionClass::PWarm | PromotionClass::PCold
        ) && seen_survivor.insert(c.manifest.candidate_hash.clone())
        {
            survivors.push(c);
        }
    }

    let mut public_static = Vec::<(
        CandidateBundle,
        crate::apfsc::normalization::PanelComparison,
    )>::new();
    let public_candidates: Vec<CandidateBundle> = survivors
        .into_iter()
        .take(crate::apfsc::constants::MAX_STATIC_PUBLIC_CANDIDATES)
        .collect();
    let public_static_results: Vec<
        Result<(
            CandidateBundle,
            crate::apfsc::normalization::PanelComparison,
        )>,
    > = public_candidates
        .into_par_iter()
        .map(|cand| {
            let static_cmp = evaluate_static_panel(
                root,
                &cand,
                &active,
                &constellation,
                PanelKind::StaticPublic,
            )?;
            Ok((cand, static_cmp))
        })
        .collect();
    for result in public_static_results {
        public_static.push(result?);
    }
    for (cand, static_cmp) in &public_static {
        crate::apfsc::artifacts::write_json_atomic(
            &crate::apfsc::artifacts::receipt_path(
                root,
                "public_static",
                &format!("{}.json", cand.manifest.candidate_hash),
            ),
            &static_cmp.receipt,
        )?;
    }
    public_static.sort_by(|a, b| {
        b.1.delta_bpb
            .partial_cmp(&a.1.delta_bpb)
            .unwrap_or(std::cmp::Ordering::Equal)
    });

    let mut public_transfer_map = BTreeMap::new();
    let mut public_robust_map = BTreeMap::new();
    let structural_public_candidates: Vec<CandidateBundle> = public_static
        .iter()
        .filter(|(cand, _)| is_phase3_structural_candidate(cand.manifest.promotion_class))
        .map(|(cand, _)| cand.clone())
        .collect();
    let transfer_results: Vec<Option<(String, crate::apfsc::transfer::TransferEvaluation)>> =
        structural_public_candidates
            .par_iter()
            .map(|cand| {
                evaluate_transfer(root, cand, &active, &constellation, EvalMode::Public)
                    .ok()
                    .map(|x| (cand.manifest.candidate_hash.clone(), x))
            })
            .collect();
    for (candidate_hash, x) in transfer_results.into_iter().flatten() {
        crate::apfsc::artifacts::write_json_atomic(
            &crate::apfsc::artifacts::receipt_path(
                root,
                "public_transfer",
                &format!("{}.json", candidate_hash),
            ),
            &x.receipt,
        )?;
        public_transfer_map.insert(candidate_hash, x);
    }
    let robust_results: Vec<Option<(String, crate::apfsc::robustness::RobustnessEvaluation)>> =
        structural_public_candidates
            .par_iter()
            .map(|cand| {
                evaluate_robustness(root, cand, &active, &constellation, EvalMode::Public)
                    .ok()
                    .map(|r| (cand.manifest.candidate_hash.clone(), r))
            })
            .collect();
    for (candidate_hash, r) in robust_results.into_iter().flatten() {
        crate::apfsc::artifacts::write_json_atomic(
            &crate::apfsc::artifacts::receipt_path(
                root,
                "public_robust",
                &format!("{}.json", candidate_hash),
            ),
            &r.receipt,
        )?;
        public_robust_map.insert(candidate_hash, r);
    }

    let mut holdout_admissions = Vec::<CandidateBundle>::new();
    let mut pwarm_count = 0usize;
    let mut pcold_count = 0usize;
    for (cand, static_cmp) in &public_static {
        if holdout_admissions.len() >= cfg.phase3.limits.max_paradigm_public_candidates {
            break;
        }
        if !public_static_spend_gate_pass(static_cmp, &constellation) {
            continue;
        }
        if is_phase3_structural_candidate(cand.manifest.promotion_class) {
            let t = match public_transfer_map.get(&cand.manifest.candidate_hash) {
                Some(v) => v,
                None => continue,
            };
            let r = match public_robust_map.get(&cand.manifest.candidate_hash) {
                Some(v) => v,
                None => continue,
            };
            let min_transfer_delta = match cand.manifest.promotion_class {
                PromotionClass::PWarm => cfg.phase3.promotion.p_warm_min_transfer_delta_bpb,
                PromotionClass::PCold => cfg.phase3.promotion.p_cold_min_transfer_delta_bpb,
                _ => 0.0,
            };
            // PCold does not expose a dedicated robust-regress threshold in config,
            // so use the warm robustness budget as the shared structural tolerance.
            let min_robust_delta = -cfg.phase3.promotion.p_warm_max_robust_regress_bpb;
            if t.delta_bpb < min_transfer_delta
                || r.delta_bpb < min_robust_delta
                || !t.protected_floor_failures.is_empty()
                || !r.protected_floor_failures.is_empty()
            {
                continue;
            }
        }
        match cand.manifest.promotion_class {
            PromotionClass::PWarm => {
                if pwarm_count >= cfg.phase3.limits.max_pwarm_holdout_admissions {
                    continue;
                }
                pwarm_count += 1;
            }
            PromotionClass::PCold => {
                if pcold_count >= cfg.phase3.limits.max_pcold_holdout_admissions {
                    continue;
                }
                pcold_count += 1;
            }
            _ => {}
        }
        holdout_admissions.push(cand.clone());
    }
    if holdout_admissions.is_empty() {
        let mut fallback = active.clone();
        if cfg.phase3.allow_p_cold && !cfg.phase3.allow_p_warm {
            fallback.manifest.promotion_class = PromotionClass::PCold;
            rehash_candidate(&mut fallback)?;
        } else if cfg.phase3.allow_p_warm
            && !cfg.phase3.allow_p_cold
            && fallback.bridge_pack.is_some()
        {
            fallback.manifest.promotion_class = PromotionClass::PWarm;
            rehash_candidate(&mut fallback)?;
        }
        let fallback_public = evaluate_static_panel(
            root,
            &fallback,
            &active,
            &constellation,
            PanelKind::StaticPublic,
        )?;
        public_static.push((fallback.clone(), fallback_public));
        holdout_admissions.push(fallback);
    } else if cfg.phase3.allow_p_warm && !cfg.phase3.allow_p_cold {
        let has_pwarm = holdout_admissions
            .iter()
            .any(|c| matches!(c.manifest.promotion_class, PromotionClass::PWarm));
        if !has_pwarm {
            if let Some((cand, _)) = public_static
                .iter()
                .find(|(c, _)| matches!(c.manifest.promotion_class, PromotionClass::PWarm))
            {
                holdout_admissions.push(cand.clone());
            }
        }
    } else if cfg.phase3.allow_p_cold && !cfg.phase3.allow_p_warm {
        let has_pcold = holdout_admissions
            .iter()
            .any(|c| matches!(c.manifest.promotion_class, PromotionClass::PCold));
        if !has_pcold {
            if let Some((cand, _)) = public_static
                .iter()
                .find(|(c, _)| matches!(c.manifest.promotion_class, PromotionClass::PCold))
            {
                holdout_admissions.push(cand.clone());
            }
        }
    }

    let mut holdout_static_map = BTreeMap::new();
    let mut holdout_transfer_map = BTreeMap::new();
    let mut holdout_robust_map = BTreeMap::new();
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

        if is_phase3_structural_candidate(cand.manifest.promotion_class) {
            if let Ok(x) = evaluate_transfer(root, cand, &active, &constellation, EvalMode::Holdout)
            {
                crate::apfsc::artifacts::write_json_atomic(
                    &crate::apfsc::artifacts::receipt_path(
                        root,
                        "holdout_transfer",
                        &format!("{}.json", cand.manifest.candidate_hash),
                    ),
                    &x.receipt,
                )?;
                holdout_transfer_map.insert(cand.manifest.candidate_hash.clone(), x);
            }
            if let Ok(r) =
                evaluate_robustness(root, cand, &active, &constellation, EvalMode::Holdout)
            {
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
        }
    }

    let mut judge_receipts = Vec::new();
    let mut canary_evaluated = Vec::new();
    let mut canary_activated = None::<String>;
    let mut passing = Vec::<PromotionBundle>::new();
    let mut rollback_staged = false;
    let thermal = crate::apfsc::searchlaw_eval::thermal_spike_state(root);
    let epoch_hint = current_epoch_index(root).unwrap_or(0).to_string();

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

        let mut bridge_receipt = None;
        let mut recent_receipt = None;
        match cand.manifest.promotion_class {
            PromotionClass::A | PromotionClass::PWarm => {
                if let Some(pack) = &cand.bridge_pack {
                    if let Ok(b) = crate::apfsc::bridge::evaluate_warm_bridge(
                        root,
                        &cand,
                        &active,
                        &constellation,
                        pack,
                    ) {
                        bridge_receipt = Some(b);
                    }
                }
                if matches!(cand.manifest.promotion_class, PromotionClass::PWarm) {
                    if let Some(transfer_eval) = evals.holdout_transfer.as_ref() {
                        let recent = crate::apfsc::fresh_contact::recent_family_gain(
                            &cand.manifest.candidate_hash,
                            &active.manifest.candidate_hash,
                            &transfer_eval.receipt,
                            &evals.holdout_static.receipt,
                            &constellation.fresh_families,
                            0,
                            cfg.phase3.promotion.p_warm_min_recent_family_gain_bpb,
                        );
                        recent_receipt = Some(recent);
                    }
                }
            }
            PromotionClass::PCold => {
                let cold_pack = crate::apfsc::types::ColdBoundaryPack {
                    protected_panels: vec!["anchor".to_string()],
                    max_anchor_regret_bpb: cfg.phase3.promotion.p_cold_max_anchor_regret_bpb,
                    max_error_streak: cfg.phase3.promotion.p_cold_max_error_streak,
                    required_transfer_gain_bpb: cfg.phase3.promotion.p_cold_min_transfer_delta_bpb,
                    required_recent_family_gain_bpb: cfg
                        .phase3
                        .promotion
                        .p_cold_min_recent_family_gain_bpb,
                    mandatory_canary_windows: cfg.phase3.canary.cold_windows,
                    rollback_target_hash: active.manifest.candidate_hash.clone(),
                };
                if let Ok((bridge, recent)) = crate::apfsc::bridge::evaluate_cold_boundary(
                    root,
                    &cand,
                    &active,
                    &constellation,
                    &cold_pack,
                    &constellation.fresh_families,
                    0,
                ) {
                    bridge_receipt = Some(bridge);
                    recent_receipt = Some(recent);
                }
            }
            _ => {}
        }

        if let Some(bridge) = &bridge_receipt {
            crate::apfsc::artifacts::write_json_atomic(
                &crate::apfsc::artifacts::receipt_path(
                    root,
                    "bridge",
                    &format!("{}.json", cand.manifest.candidate_hash),
                ),
                bridge,
            )?;
        }
        if let Some(recent) = &recent_receipt {
            crate::apfsc::artifacts::write_json_atomic(
                &crate::apfsc::artifacts::receipt_path(
                    root,
                    "fresh_holdout",
                    &format!("{}.json", cand.manifest.candidate_hash),
                ),
                recent,
            )?;
        }

        let mut receipt = judge_phase3_candidate(
            root,
            &cand,
            &active,
            &constellation,
            cfg,
            &evals,
            bridge_receipt.as_ref(),
            recent_receipt.as_ref(),
        )?;

        let incumbent_score = evals.holdout_static.incumbent_weighted_bpb;
        let proposal_score = evals.holdout_static.candidate_weighted_bpb;
        let proposal_ast_nodes = cand.arch_program.nodes.len();
        println!(
            "EVAL COMPLETE | King: {} | Proposal (Nodes {}): {}",
            incumbent_score, proposal_ast_nodes, proposal_score
        );

        // During thermal spikes, keep a non-zero acceptance path for zero/unknown
        // proposal scores so exploratory structure growth is not hard-blocked.
        if receipt.decision == JudgeDecision::Reject && thermal.active {
            let holdout_score = receipt.weighted_static_holdout_delta_bpb;
            let score_unknown_or_zero = !holdout_score.is_finite() || holdout_score == 0.0;
            if score_unknown_or_zero {
                let p = thermal_soft_floor_acceptance_probability(thermal.temp.unwrap_or(0.0));
                let sample = deterministic_soft_floor_sample(&[
                    &cand.manifest.candidate_hash,
                    &active.manifest.candidate_hash,
                    &epoch_hint,
                    &receipt.reason,
                ]);
                if sample <= p {
                    receipt.decision = JudgeDecision::Promote;
                    receipt.reason =
                        format!("Promote(MetropolisThermalSoftFloor:p={p:.4},u={sample:.4})");
                }
            }
        }

        if receipt.decision == JudgeDecision::Promote {
            let promotion_bundle = build_promotion_bundle(&cand, &receipt, &evals);
            if receipt.canary_required {
                if !rollback_staged
                    && matches!(
                        cand.manifest.promotion_class,
                        PromotionClass::PWarm | PromotionClass::PCold
                    )
                {
                    stage_rollback_target(root, &active.manifest.candidate_hash)?;
                    rollback_staged = true;
                }
                let required_windows = phase3_canary_windows(cand.manifest.promotion_class, cfg);
                let canary = run_phase3_canary(
                    root,
                    &cand.manifest.candidate_hash,
                    &active.manifest.candidate_hash,
                    &constellation.constellation_id,
                    required_windows,
                    cfg,
                )?;
                canary_evaluated.push(cand.manifest.candidate_hash.clone());
                if canary.pass {
                    canary_activated = Some(cand.manifest.candidate_hash.clone());
                    receipt.canary_result = Some("pass".to_string());
                    crate::apfsc::artifacts::write_json_atomic(
                        &crate::apfsc::artifacts::receipt_path(
                            root,
                            "activation",
                            &format!("{}.json", cand.manifest.candidate_hash),
                        ),
                        &receipt,
                    )?;
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
        if receipt.decision == JudgeDecision::Reject {
            crate::apfsc::artifacts::note_last_rejected_proposal(
                receipt.weighted_static_holdout_delta_bpb,
                receipt.reason.clone(),
            );
            let output_feature_out_dim = cand
                .arch_program
                .nodes
                .iter()
                .find(|n| n.id == cand.arch_program.outputs.feature_node)
                .map(|n| n.out_dim as usize)
                .unwrap_or(0);
            let trace = serde_json::json!({
                "reason": receipt.reason.clone(),
                "candidate_hash": cand.manifest.candidate_hash.clone(),
                "promotion_class": format!("{:?}", cand.manifest.promotion_class),
                "ast_node_count": cand.arch_program.nodes.len(),
                "output_shape": format!("feature_vector[{}]", output_feature_out_dim),
                "public_target_subset_pass": evals.public_static.receipt.target_subset_pass,
                "holdout_target_subset_pass": evals.holdout_static.receipt.target_subset_pass,
                "expected_target_subset": constellation.normalization.target_subset.clone(),
                "holdout_improved_families": evals.holdout_static.receipt.improved_families.clone(),
                "holdout_nonprotected_improved_families": evals.holdout_static.receipt.nonprotected_improved_families.clone(),
                "min_improved_families": constellation.normalization.min_improved_families,
                "min_nonprotected_improved_families": constellation.normalization.min_nonprotected_improved_families
            });
            crate::apfsc::artifacts::note_last_rejected_proposal_trace(trace.to_string());
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
            if matches!(
                best.cand.manifest.promotion_class,
                PromotionClass::PWarm | PromotionClass::PCold
            ) {
                stage_rollback_target(root, &active.manifest.candidate_hash)?;
            }
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

fn is_phase3_structural_candidate(class: PromotionClass) -> bool {
    matches!(
        class,
        PromotionClass::A | PromotionClass::PWarm | PromotionClass::PCold
    )
}

fn phase3_canary_windows(class: PromotionClass, cfg: &Phase1Config) -> u32 {
    match class {
        PromotionClass::PCold => cfg.phase3.canary.cold_windows,
        PromotionClass::PWarm | PromotionClass::A => cfg.phase3.canary.warm_windows,
        _ => 0,
    }
}

struct PioneerEpochLease<'a> {
    root: &'a Path,
    previous_active: Option<String>,
    incubator_active: Option<String>,
}

impl<'a> PioneerEpochLease<'a> {
    fn enter(root: &'a Path, cfg: &Phase1Config, epoch_id: u64) -> Result<Self> {
        let timeslice = cfg.phase4.pioneer_timeslice as u64;
        if timeslice == 0 || epoch_id == 0 || epoch_id % timeslice != 0 {
            let _ = crate::apfsc::active::write_active_epoch_mode(root, "global");
            return Ok(Self {
                root,
                previous_active: None,
                incubator_active: None,
            });
        }
        let incubator_hash =
            match crate::apfsc::artifacts::read_pointer(root, "active_incubator_pointer") {
                Ok(v) => v,
                Err(_) => {
                    let _ = crate::apfsc::active::write_active_epoch_mode(root, "global");
                    return Ok(Self {
                        root,
                        previous_active: None,
                        incubator_active: None,
                    });
                }
            };
        // Only arm pioneer mode when the incubator resident still exists on disk.
        if load_candidate(root, &incubator_hash).is_err() {
            let _ = crate::apfsc::active::write_active_epoch_mode(root, "global");
            return Ok(Self {
                root,
                previous_active: None,
                incubator_active: None,
            });
        }
        let previous_active = crate::apfsc::artifacts::read_pointer(root, "active_candidate").ok();
        if previous_active.as_deref() == Some(incubator_hash.as_str()) {
            let _ = crate::apfsc::active::write_active_epoch_mode(root, "pioneer");
            return Ok(Self {
                root,
                previous_active: None,
                incubator_active: None,
            });
        }
        if let Some(prev) = previous_active.clone() {
            crate::apfsc::active::write_active_epoch_mode(root, "pioneer")?;
            crate::apfsc::artifacts::write_pointer(root, "active_candidate", &incubator_hash)?;
            let _ = crate::apfsc::artifacts::write_pointer(
                root,
                "pioneer_epoch_baseline_candidate",
                &prev,
            );
            Ok(Self {
                root,
                previous_active: Some(prev),
                incubator_active: Some(incubator_hash),
            })
        } else {
            Ok(Self {
                root,
                previous_active: None,
                incubator_active: None,
            })
        }
    }

    fn is_active(&self) -> bool {
        self.previous_active.is_some() && self.incubator_active.is_some()
    }

    fn baseline_hash(&self) -> Option<&str> {
        self.previous_active.as_deref()
    }

    fn incubator_hash(&self) -> Option<&str> {
        self.incubator_active.as_deref()
    }

    fn commit_collapse(&mut self) {
        self.previous_active = None;
        self.incubator_active = None;
    }
}

impl Drop for PioneerEpochLease<'_> {
    fn drop(&mut self) {
        if let (Some(previous_active), Some(incubator_active)) = (
            self.previous_active.as_ref(),
            self.incubator_active.as_ref(),
        ) {
            if let Ok(current_active) =
                crate::apfsc::artifacts::read_pointer(self.root, "active_candidate")
            {
                if current_active == *incubator_active {
                    let _ = crate::apfsc::artifacts::write_pointer(
                        self.root,
                        "active_candidate",
                        previous_active,
                    );
                }
            }
        }
        let _ = crate::apfsc::active::write_active_epoch_mode(self.root, "global");
    }
}

fn remove_pointer_file(root: &Path, name: &str) {
    let path = root.join("pointers").join(name);
    let _ = crate::apfsc::artifacts::remove_file_if_exists(&path);
}

fn persist_subcortex_prior(root: &Path, incumbent: &CandidateBundle) -> Result<String> {
    let record = serde_json::json!({
        "kind": "subcortex_prior_v1",
        "incumbent_hash": incumbent.manifest.candidate_hash,
        "snapshot_hash": incumbent.manifest.snapshot_hash,
        "manifest": incumbent.manifest,
        "head_pack_hash": incumbent.manifest.head_pack_hash,
        "state_pack_hash": incumbent.manifest.state_pack_hash,
        "arch_program_hash": incumbent.manifest.arch_program_hash,
        "created_at": crate::apfsc::protocol::now_unix_s(),
    });
    let prior_hash = crate::apfsc::artifacts::digest_json(&record)?;
    let prior_dir = root.join("packs").join("substrate").join(&prior_hash);
    crate::apfsc::artifacts::create_dir_all_if_persistent(&prior_dir)?;
    crate::apfsc::artifacts::write_json_atomic(&prior_dir.join("subcortex_prior.json"), &record)?;
    crate::apfsc::artifacts::append_jsonl_atomic(
        &root.join("archives").join("subcortex_priors.jsonl"),
        &serde_json::json!({
            "prior_hash": prior_hash,
            "incumbent_hash": incumbent.manifest.candidate_hash,
            "snapshot_hash": incumbent.manifest.snapshot_hash,
            "ts": crate::apfsc::protocol::now_unix_s(),
        }),
    )?;
    Ok(prior_hash)
}

fn inject_subcortex_endosymbiosis(
    candidate: &mut CandidateBundle,
    prior_hash: &str,
    incumbent_hash: &str,
) -> Result<()> {
    let feature = candidate.arch_program.outputs.feature_node;
    let feature_dim = candidate
        .arch_program
        .nodes
        .iter()
        .find(|n| n.id == feature)
        .map(|n| n.out_dim)
        .unwrap_or(1);
    let next = candidate
        .arch_program
        .nodes
        .iter()
        .map(|n| n.id)
        .max()
        .unwrap_or(0)
        .saturating_add(1);
    candidate
        .arch_program
        .nodes
        .push(crate::apfsc::scir::ast::ScirNode {
            id: next,
            op: crate::apfsc::scir::ast::ScirOp::Subcortex {
                prior_hash: prior_hash.to_string(),
                eigen_modulator_vector: vec![1.0; feature_dim as usize],
            },
            inputs: vec![feature],
            out_dim: feature_dim,
            mutable: false,
        });
    let join = next.saturating_add(1);
    candidate
        .arch_program
        .nodes
        .push(crate::apfsc::scir::ast::ScirNode {
            id: join,
            op: crate::apfsc::scir::ast::ScirOp::Concat,
            inputs: vec![feature, next],
            out_dim: feature_dim.saturating_mul(2),
            mutable: false,
        });
    candidate.arch_program.outputs.feature_node = join;

    candidate.head_pack.native_head.in_dim = candidate
        .head_pack
        .native_head
        .in_dim
        .saturating_add(feature_dim);
    candidate.head_pack.native_head.weights.extend(vec![
        0.0;
        (256u32.saturating_mul(feature_dim))
            as usize
    ]);
    candidate.head_pack.nuisance_head.in_dim = candidate
        .head_pack
        .nuisance_head
        .in_dim
        .saturating_add(feature_dim);
    candidate.head_pack.nuisance_head.weights.extend(vec![
        0.0;
        (256u32.saturating_mul(feature_dim))
            as usize
    ]);
    candidate.head_pack.residual_head.in_dim = candidate
        .head_pack
        .residual_head
        .in_dim
        .saturating_add(feature_dim);
    candidate.head_pack.residual_head.weights.extend(vec![
        0.0;
        (256u32.saturating_mul(feature_dim))
            as usize
    ]);
    candidate
        .state_pack
        .resid_weights
        .extend(vec![0.0; feature_dim as usize]);

    if !candidate
        .manifest
        .substrate_deps
        .iter()
        .any(|h| h == prior_hash)
    {
        candidate
            .manifest
            .substrate_deps
            .push(prior_hash.to_string());
    }
    let prior_hint = if prior_hash.len() > 12 {
        &prior_hash[..12]
    } else {
        prior_hash
    };
    let mut mutation = candidate.build_meta.mutation_type.clone();
    mutation.push_str("+subcortex:");
    mutation.push_str(prior_hint);
    candidate.build_meta.mutation_type = mutation;
    candidate.build_meta.lane = "collapse".to_string();
    candidate.build_meta.notes = Some(format!(
        "Endosymbiotic compression from incumbent {} into Subcortex({})",
        incumbent_hash, prior_hash
    ));

    rehash_candidate(candidate)
}

fn wipe_global_qd_archive(root: &Path) -> Result<()> {
    let qd_dir = root.join("qd_archive");
    if crate::apfsc::artifacts::path_exists(&qd_dir) {
        crate::apfsc::artifacts::remove_dir_all_if_exists(&qd_dir)?;
    }
    crate::apfsc::artifacts::create_dir_all_if_persistent(&qd_dir)?;
    for p in [
        root.join("archives").join("qd_archive.jsonl"),
        root.join("archives").join("incubator_qd_archive.jsonl"),
    ] {
        let _ = crate::apfsc::artifacts::remove_file_if_exists(&p);
    }
    Ok(())
}

fn append_era_shift(
    root: &Path,
    candidate_hash: &str,
    search_law_hash: Option<&str>,
) -> Result<u64> {
    let era = crate::apfsc::artifacts::read_pointer(root, "active_era")
        .ok()
        .and_then(|v| v.parse::<u64>().ok())
        .unwrap_or(1)
        .saturating_add(1);
    crate::apfsc::artifacts::write_pointer(root, "active_era", &era.to_string())?;
    crate::apfsc::artifacts::append_jsonl_atomic(
        &root.join("archives").join("era_shifts.jsonl"),
        &serde_json::json!({
            "era": era,
            "candidate_hash": candidate_hash,
            "search_law_hash": search_law_hash,
            "ts": crate::apfsc::protocol::now_unix_s(),
        }),
    )?;
    let journal = crate::apfsc::prod::journal::JournalRecord {
        job_id: format!("era_shift_{}", era),
        run_id: None,
        idempotency_key: format!("era-shift-{}", era),
        stage: "era_shift".to_string(),
        target_entity_hash: Some(candidate_hash.to_string()),
        planned_effects: vec![
            "active_candidate".to_string(),
            "active_search_law".to_string(),
            "qd_archive_reset".to_string(),
        ],
        created_at: crate::apfsc::protocol::now_unix_s(),
        state: crate::apfsc::prod::journal::JobState::Committed,
        receipt_hash: None,
        commit_marker: Some(format!("era{}", era)),
    };
    let _ = crate::apfsc::prod::journal::append_journal(root, &journal);
    Ok(era)
}

fn active_era(root: &Path) -> u64 {
    crate::apfsc::artifacts::read_pointer(root, "active_era")
        .ok()
        .and_then(|v| v.parse::<u64>().ok())
        .filter(|v| *v > 0)
        .unwrap_or(1)
}

fn apply_era_pressure(cfg: &Phase1Config, root: &Path) -> Phase1Config {
    let era = active_era(root);
    if era <= 1 {
        return cfg.clone();
    }
    let mut out = cfg.clone();
    let levels = era.saturating_sub(1) as i32;
    let public_mul = out.phase4.era_public_delta_multiplier.powi(levels);
    let holdout_mul = out.phase4.era_holdout_delta_multiplier.powi(levels);
    out.judge.public_min_delta_bits *= public_mul;
    out.judge.holdout_min_delta_bits *= holdout_mul;
    out.phase4.challenge_min_bucket_score = out.phase4.challenge_min_bucket_score.saturating_add(
        out.phase4
            .era_challenge_bucket_step
            .saturating_mul(levels.max(0)),
    );
    out.phase4.max_hidden_challenge_families =
        out.phase4.max_hidden_challenge_families.saturating_add(
            (levels.max(0) as usize).saturating_mul(out.phase4.era_hidden_challenge_growth),
        );
    out.phase2.min_improved_families = out
        .phase2
        .min_improved_families
        .saturating_add((era.saturating_sub(1) as u32).min(3));
    out
}

fn stable_ectoderm_window(seed: &str, len: usize) -> Vec<u8> {
    let n = len.max(1);
    if seed.is_empty() {
        return vec![0u8; n];
    }
    let mut out = Vec::with_capacity(n);
    let bytes = seed.as_bytes();
    for i in 0..n {
        let a = bytes[i % bytes.len()];
        let b = bytes[(i.wrapping_mul(7) + 3) % bytes.len()];
        out.push(a ^ b.rotate_left((i % 7) as u32));
    }
    out
}

fn clamp01(v: f64) -> f64 {
    v.clamp(0.0, 1.0)
}

fn lerp(min: f64, max: f64, t: f64) -> f64 {
    min + (max - min) * clamp01(t)
}

fn apply_ectoderm_overrides(root: &Path, cfg: &Phase1Config, epoch_id: u64) -> Phase1Config {
    if !cfg.phase4.ectoderm.enabled {
        let _ = crate::apfsc::artifacts::write_json_atomic(
            &crate::apfsc::artifacts::receipt_path(
                root,
                "ectoderm",
                &format!("epoch_{epoch_id}.json"),
            ),
            &serde_json::json!({
                "epoch": epoch_id,
                "enabled": false,
                "reason": "ectoderm_disabled",
                "constants": {
                    "paradigm_shift_scale_min": cfg.phase4.ectoderm.paradigm_shift_scale_min,
                    "paradigm_shift_scale_max": cfg.phase4.ectoderm.paradigm_shift_scale_max,
                    "class_r_difficulty_min": cfg.phase4.ectoderm.class_r_difficulty_min,
                    "class_r_difficulty_max": cfg.phase4.ectoderm.class_r_difficulty_max,
                    "pioneer_timeslice_min": cfg.phase4.ectoderm.pioneer_timeslice_min,
                    "pioneer_timeslice_max": cfg.phase4.ectoderm.pioneer_timeslice_max
                },
                "applied": {
                    "paradigm_shift_allowance_bpb": cfg.phase3.promotion.paradigm_shift_allowance_bpb,
                    "class_r_hamiltonian_difficulty_multiplier": cfg.phase4.class_r_hamiltonian_difficulty_multiplier,
                    "pioneer_timeslice": cfg.phase4.pioneer_timeslice
                }
            }),
        );
        return cfg.clone();
    }
    let active = match load_active_candidate(root) {
        Ok(v) => v,
        Err(_) => return cfg.clone(),
    };
    let mut probe_ix_by_id = BTreeMap::<u32, usize>::new();
    for (ix, node_id) in active.arch_program.outputs.probe_nodes.iter().enumerate() {
        probe_ix_by_id.insert(*node_id, ix);
    }
    let mut channel_probe = BTreeMap::<u8, usize>::new();
    for node in &active.arch_program.nodes {
        if let crate::apfsc::scir::ast::ScirOp::EctodermPrimitive { channel } = node.op {
            if let Some(ix) = probe_ix_by_id.get(&node.id).copied() {
                channel_probe.entry(channel).or_insert(ix);
            }
        }
    }
    if channel_probe.is_empty() {
        let _ = crate::apfsc::artifacts::write_json_atomic(
            &crate::apfsc::artifacts::receipt_path(
                root,
                "ectoderm",
                &format!("epoch_{epoch_id}.json"),
            ),
            &serde_json::json!({
                "epoch": epoch_id,
                "candidate_hash": active.manifest.candidate_hash,
                "enabled": true,
                "reason": "no_ectoderm_probes_on_active_candidate",
                "constants": {
                    "paradigm_shift_scale_min": cfg.phase4.ectoderm.paradigm_shift_scale_min,
                    "paradigm_shift_scale_max": cfg.phase4.ectoderm.paradigm_shift_scale_max,
                    "class_r_difficulty_min": cfg.phase4.ectoderm.class_r_difficulty_min,
                    "class_r_difficulty_max": cfg.phase4.ectoderm.class_r_difficulty_max,
                    "pioneer_timeslice_min": cfg.phase4.ectoderm.pioneer_timeslice_min,
                    "pioneer_timeslice_max": cfg.phase4.ectoderm.pioneer_timeslice_max
                },
                "applied": {
                    "paradigm_shift_allowance_bpb": cfg.phase3.promotion.paradigm_shift_allowance_bpb,
                    "class_r_hamiltonian_difficulty_multiplier": cfg.phase4.class_r_hamiltonian_difficulty_multiplier,
                    "pioneer_timeslice": cfg.phase4.pioneer_timeslice
                }
            }),
        );
        return cfg.clone();
    }

    let window = stable_ectoderm_window(
        &active.manifest.candidate_hash,
        cfg.bank.window_len as usize,
    );
    let trace = match run_program(&active.arch_program, &window) {
        Ok(v) => v,
        Err(_) => {
            let _ = crate::apfsc::artifacts::write_json_atomic(
                &crate::apfsc::artifacts::receipt_path(
                    root,
                    "ectoderm",
                    &format!("epoch_{epoch_id}.json"),
                ),
                &serde_json::json!({
                    "epoch": epoch_id,
                    "candidate_hash": active.manifest.candidate_hash,
                    "enabled": true,
                    "reason": "probe_trace_failed",
                    "applied": {
                        "paradigm_shift_allowance_bpb": cfg.phase3.promotion.paradigm_shift_allowance_bpb,
                        "class_r_hamiltonian_difficulty_multiplier": cfg.phase4.class_r_hamiltonian_difficulty_multiplier,
                        "pioneer_timeslice": cfg.phase4.pioneer_timeslice
                    }
                }),
            );
            return cfg.clone();
        }
    };

    let sample_channel = |channel: u8| -> f64 {
        let Some(ix) = channel_probe.get(&channel).copied() else {
            return 0.5;
        };
        let Some(vec) = trace.probes.get(ix) else {
            return 0.5;
        };
        if vec.is_empty() {
            return 0.5;
        }
        let mean = vec.iter().copied().map(f64::from).sum::<f64>() / vec.len() as f64;
        clamp01((mean.tanh() + 1.0) * 0.5)
    };

    let mut out = cfg.clone();
    let ect = &cfg.phase4.ectoderm;
    let scale = lerp(
        ect.paradigm_shift_scale_min,
        ect.paradigm_shift_scale_max,
        sample_channel(0),
    );
    out.phase3.promotion.paradigm_shift_allowance_bpb =
        (out.phase3.promotion.paradigm_shift_allowance_bpb * scale).max(0.0);

    let class_r_difficulty = lerp(
        ect.class_r_difficulty_min,
        ect.class_r_difficulty_max,
        sample_channel(1),
    );
    out.phase4.class_r_hamiltonian_difficulty_multiplier = class_r_difficulty.max(0.1);

    let pioneer_raw = lerp(
        ect.pioneer_timeslice_min as f64,
        ect.pioneer_timeslice_max as f64,
        sample_channel(2),
    )
    .round() as u32;
    out.phase4.pioneer_timeslice = pioneer_raw
        .clamp(
            ect.pioneer_timeslice_min.max(1),
            ect.pioneer_timeslice_max.max(1),
        )
        .max(1);

    let _ = crate::apfsc::artifacts::write_json_atomic(
        &crate::apfsc::artifacts::receipt_path(root, "ectoderm", &format!("epoch_{epoch_id}.json")),
        &serde_json::json!({
            "epoch": epoch_id,
            "candidate_hash": active.manifest.candidate_hash,
            "channels": {
                "0": sample_channel(0),
                "1": sample_channel(1),
                "2": sample_channel(2),
            },
            "constants": {
                "paradigm_shift_scale_min": cfg.phase4.ectoderm.paradigm_shift_scale_min,
                "paradigm_shift_scale_max": cfg.phase4.ectoderm.paradigm_shift_scale_max,
                "class_r_difficulty_min": cfg.phase4.ectoderm.class_r_difficulty_min,
                "class_r_difficulty_max": cfg.phase4.ectoderm.class_r_difficulty_max,
                "pioneer_timeslice_min": cfg.phase4.ectoderm.pioneer_timeslice_min,
                "pioneer_timeslice_max": cfg.phase4.ectoderm.pioneer_timeslice_max
            },
            "applied": {
                "paradigm_shift_allowance_bpb": out.phase3.promotion.paradigm_shift_allowance_bpb,
                "class_r_hamiltonian_difficulty_multiplier": out.phase4.class_r_hamiltonian_difficulty_multiplier,
                "pioneer_timeslice": out.phase4.pioneer_timeslice,
            }
        }),
    );
    out
}

#[derive(Debug, Deserialize)]
struct ExtropyDethroningSample {
    class_r_surprisal_bits: Option<f64>,
    public_static_delta_bpb: f64,
    holdout_static_delta_bpb: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct AutonomicSearchLawWindowSample {
    epoch: u64,
    searchlaw_receipts: u32,
    searchlaw_ab_fail_rejections: u32,
}

fn maybe_pause_for_exogenous_hunger(root: &Path, cfg: &Phase1Config, epoch_id: u64) -> Result<()> {
    let consecutive_mortality = crate::apfsc::artifacts::demon_lane_consecutive_mortality_count();
    if consecutive_mortality < 1_000 {
        return Ok(());
    }
    let staleness = crate::apfsc::afferent::arxiv_staleness_threshold_seconds(cfg, 0);
    let refreshed =
        crate::apfsc::afferent::refresh_arxiv_external_snapshot_if_stale(root, staleness, 24)?;
    if refreshed.is_some() {
        crate::apfsc::artifacts::note_demon_lane_survival();
    }
    crate::apfsc::artifacts::write_json_atomic(
        &crate::apfsc::artifacts::receipt_path(
            root,
            "truth_laws",
            &format!("exogenous_hunger_epoch_{epoch_id}.json"),
        ),
        &serde_json::json!({
            "epoch": epoch_id,
            "paused_for_exogenous_hunger": true,
            "demon_lane_consecutive_mortality_count": consecutive_mortality,
            "arxiv_refresh_triggered": refreshed.is_some(),
            "status": if refreshed.is_some() { "resumed_with_fresh_tensor_seed" } else { "refresh_skipped_or_unavailable" }
        }),
    )?;
    Ok(())
}

fn append_autonomic_searchlaw_sample(
    root: &Path,
    epoch_id: u64,
    searchlaw_receipts: &[PromotionReceipt],
) -> Result<AutonomicSearchLawWindowSample> {
    let ab_fail = searchlaw_receipts
        .iter()
        .filter(|r| r.reason == JudgeRejectReason::SearchLawAbFail.as_reason())
        .count() as u32;
    let sample = AutonomicSearchLawWindowSample {
        epoch: epoch_id,
        searchlaw_receipts: searchlaw_receipts.len() as u32,
        searchlaw_ab_fail_rejections: ab_fail,
    };
    crate::apfsc::artifacts::append_jsonl_atomic(
        &root
            .join("archives")
            .join("autonomic_searchlaw_window.jsonl"),
        &sample,
    )?;
    Ok(sample)
}

fn maybe_autonomic_thermal_spike(
    root: &Path,
    epoch_id: u64,
    searchlaw_receipts: &[PromotionReceipt],
) -> Result<()> {
    let _ = append_autonomic_searchlaw_sample(root, epoch_id, searchlaw_receipts)?;
    let rows = crate::apfsc::artifacts::read_jsonl::<AutonomicSearchLawWindowSample>(
        &root
            .join("archives")
            .join("autonomic_searchlaw_window.jsonl"),
    )
    .unwrap_or_default();
    let from_epoch = epoch_id.saturating_sub(99);
    let mut window_total = 0u64;
    let mut window_ab_fail = 0u64;
    for row in rows.iter().rev() {
        if row.epoch < from_epoch {
            break;
        }
        window_total = window_total.saturating_add(row.searchlaw_receipts as u64);
        window_ab_fail = window_ab_fail.saturating_add(row.searchlaw_ab_fail_rejections as u64);
    }
    let ratio = if window_total == 0 {
        0.0
    } else {
        window_ab_fail as f64 / window_total as f64
    };
    let threshold = 0.8;
    let demon_consecutive_mortality =
        crate::apfsc::artifacts::demon_lane_consecutive_mortality_count();
    let should_spike =
        demon_consecutive_mortality > 0 && demon_consecutive_mortality % 100 == 0;
    let spike_already_active = crate::apfsc::searchlaw_eval::thermal_spike_active(root);
    let spike_triggered = should_spike && !spike_already_active;
    if spike_triggered {
        let _ = crate::apfsc::searchlaw_eval::force_thermal_spike(root, 5.0, 50, 0.1)?;
    }
    crate::apfsc::artifacts::write_json_atomic(
        &crate::apfsc::artifacts::receipt_path(
            root,
            "extropy",
            &format!("autonomic_plateau_epoch_{epoch_id}.json"),
        ),
        &serde_json::json!({
            "epoch": epoch_id,
            "window_epochs": 100,
            "searchlaw_abfail_rejections": window_ab_fail,
            "searchlaw_total_receipts": window_total,
            "searchlaw_abfail_ratio": ratio,
            "threshold": threshold,
            "demon_lane_consecutive_mortality_count": demon_consecutive_mortality,
            "demon_trigger_modulus": 100,
            "spike_triggered": spike_triggered,
            "spike_already_active": spike_already_active
        }),
    )?;
    Ok(())
}

fn recent_json_receipts(dir: &Path, max_count: usize) -> Vec<std::path::PathBuf> {
    let mut rows = Vec::<(std::time::SystemTime, std::path::PathBuf)>::new();
    let Ok(rd) = std::fs::read_dir(dir) else {
        return Vec::new();
    };
    for entry in rd.flatten() {
        let path = entry.path();
        if path.extension().and_then(|s| s.to_str()) != Some("json") {
            continue;
        }
        let mtime = entry
            .metadata()
            .ok()
            .and_then(|m| m.modified().ok())
            .unwrap_or(std::time::SystemTime::UNIX_EPOCH);
        rows.push((mtime, path));
    }
    rows.sort_by(|a, b| b.0.cmp(&a.0));
    rows.truncate(max_count);
    rows.into_iter().map(|(_, p)| p).collect()
}

fn apply_extropy_guardrail(root: &Path, cfg: &Phase1Config, epoch_id: u64) -> Phase1Config {
    if !cfg.phase4.enable_extropy_guardrail {
        return cfg.clone();
    }
    let mut out = cfg.clone();
    let window = cfg.phase4.extropy_receipt_window.max(4);
    let files = recent_json_receipts(&root.join("receipts").join("dethroning_audit"), window);
    if files.is_empty() {
        let _ = crate::apfsc::artifacts::write_json_atomic(
            &crate::apfsc::artifacts::receipt_path(
                root,
                "extropy",
                &format!("epoch_{epoch_id}.json"),
            ),
            &serde_json::json!({
                "epoch": epoch_id,
                "panic": false,
                "reason": "no_dethroning_samples",
                "window": window,
                "applied": {
                    "class_r_hamiltonian_difficulty_multiplier": out.phase4.class_r_hamiltonian_difficulty_multiplier,
                    "pioneer_timeslice": out.phase4.pioneer_timeslice
                }
            }),
        );
        return out;
    }

    let mut low_surprisal = 0usize;
    let mut with_surprisal = 0usize;
    let mut zero_delta = 0usize;
    let eps = cfg.phase4.extropy_zero_delta_eps_bpb.max(0.0);
    let floor = cfg.phase4.extropy_surprisal_floor_bits.max(0.0);
    for path in &files {
        let Ok(text) = std::fs::read_to_string(path) else {
            continue;
        };
        let Ok(sample) = serde_json::from_str::<ExtropyDethroningSample>(&text) else {
            continue;
        };
        if let Some(s) = sample.class_r_surprisal_bits {
            with_surprisal += 1;
            if s <= floor {
                low_surprisal += 1;
            }
        }
        if sample.public_static_delta_bpb.abs() <= eps
            && sample.holdout_static_delta_bpb.abs() <= eps
        {
            zero_delta += 1;
        }
    }
    let usable = files.len().max(1) as f64;
    let low_surprisal_ratio = if with_surprisal == 0 {
        1.0
    } else {
        low_surprisal as f64 / with_surprisal as f64
    };
    let zero_delta_ratio = zero_delta as f64 / usable;
    let panic = low_surprisal_ratio >= 0.8
        && zero_delta_ratio >= cfg.phase4.extropy_zero_delta_ratio_trigger.clamp(0.0, 1.0);

    if panic {
        let boost = cfg.phase4.extropy_difficulty_boost.max(1.0);
        out.phase4.class_r_hamiltonian_difficulty_multiplier =
            (out.phase4.class_r_hamiltonian_difficulty_multiplier * boost).clamp(1.0, 8.0);
        out.phase4.pioneer_timeslice = out.phase4.pioneer_timeslice.max(1).saturating_sub(1).max(1);
        let _ = crate::apfsc::artifacts::write_pointer(
            root,
            "extropy_panic_epoch",
            &epoch_id.to_string(),
        );
    }

    let _ = crate::apfsc::artifacts::write_json_atomic(
        &crate::apfsc::artifacts::receipt_path(root, "extropy", &format!("epoch_{epoch_id}.json")),
        &serde_json::json!({
            "epoch": epoch_id,
            "panic": panic,
            "stats": {
                "sample_count": files.len(),
                "with_surprisal": with_surprisal,
                "low_surprisal_ratio": low_surprisal_ratio,
                "zero_delta_ratio": zero_delta_ratio,
                "surprisal_floor_bits": floor,
                "zero_delta_eps_bpb": eps,
                "zero_delta_ratio_trigger": cfg.phase4.extropy_zero_delta_ratio_trigger
            },
            "applied": {
                "class_r_hamiltonian_difficulty_multiplier": out.phase4.class_r_hamiltonian_difficulty_multiplier,
                "pioneer_timeslice": out.phase4.pioneer_timeslice
            }
        }),
    );
    out
}

fn refresh_truth_law_constraints(root: &Path, epoch_id: u64) -> Result<String> {
    let constraints = crate::apfsc::lanes::truth::load_discovery_constraints(root, 12)?;
    let runtime_dir = root.join("runtime");
    crate::apfsc::artifacts::create_dir_all_if_persistent(&runtime_dir)?;
    crate::apfsc::artifacts::write_json_atomic(
        &runtime_dir.join("discovery_constraints.json"),
        &constraints,
    )?;
    let constraints_hash = crate::apfsc::artifacts::digest_json(&constraints)?;
    crate::apfsc::active::write_active_discovery_constraints_hash(root, &constraints_hash)?;
    crate::apfsc::artifacts::write_json_atomic(
        &crate::apfsc::artifacts::receipt_path(
            root,
            "truth_laws",
            &format!("epoch_{epoch_id}.json"),
        ),
        &serde_json::json!({
            "epoch": epoch_id,
            "constraints_hash": constraints_hash,
            "constraint_count": constraints.len(),
            "constraints": constraints,
            "source": "discoveries/*"
        }),
    )?;
    Ok(constraints_hash)
}

fn maybe_emit_class_m_material(
    root: &Path,
    epoch_id: u64,
    candidate: &CandidateBundle,
) -> Result<Option<String>> {
    let channel3_seed_active = crate::apfsc::afferent::channel_seed_vector_from_root(root, 3, 8)
        .map(|v| !v.is_empty())
        .unwrap_or(false);
    let mut effective_mutation_type = candidate.build_meta.mutation_type.clone();
    if channel3_seed_active
        && !effective_mutation_type
            .to_ascii_lowercase()
            .contains("class_m_probe")
    {
        effective_mutation_type =
            format!("class_m_probe_forced_channel3::{}", candidate.build_meta.mutation_type);
    }
    let is_class_m = effective_mutation_type
        .to_ascii_lowercase()
        .contains("class_m_probe");
    if !is_class_m {
        return Ok(None);
    }
    let _ = crate::apfsc::artifacts::note_class_m_generation_attempt();

    let demon = crate::apfsc::lanes::truth::demon_lane_verify_class_m(candidate);
    crate::apfsc::artifacts::write_json_atomic(
        &crate::apfsc::artifacts::receipt_path(
            root,
            "truth_laws",
            &format!(
                "demon_{}_epoch_{}.json",
                candidate.manifest.candidate_hash, epoch_id
            ),
        ),
        &serde_json::json!({
            "epoch": epoch_id,
            "candidate_hash": candidate.manifest.candidate_hash,
            "mutation_type": effective_mutation_type,
            "class_m_override_active": channel3_seed_active,
            "survived": demon.survived,
            "ast_node_count": demon.ast_node_count,
            "parsimony_penalty": demon.parsimony_penalty,
            "baseline_ground_state": demon.baseline_ground_state,
            "survival_margin": demon.survival_margin,
            "conductivity_gain": demon.conductivity_gain,
            "thermal_stability_gain": demon.thermal_stability_gain,
            "quantum_latency_gain": demon.quantum_latency_gain,
            "scenarios": demon.scenarios,
        }),
    )?;
    if !demon.survived {
        let _ = crate::apfsc::artifacts::note_demon_lane_mortality();
        let _ = crate::apfsc::artifacts::note_current_demon_survival_margin(demon.survival_margin);
        let _ = crate::apfsc::artifacts::note_best_demon_survival_margin(demon.survival_margin);
        return Ok(None);
    }
    crate::apfsc::artifacts::note_demon_lane_survival();

    let material_id = crate::apfsc::artifacts::digest_json(&(
        "class_m",
        &candidate.manifest.candidate_hash,
        &effective_mutation_type,
    ))?;
    let mut lines = Vec::<String>::new();
    let atom_count = candidate.arch_program.nodes.len().clamp(6, 40);
    lines.push(atom_count.to_string());
    lines.push(format!(
        "material_id={} candidate={} mutation_type={}",
        material_id, candidate.manifest.candidate_hash, effective_mutation_type
    ));
    let periodic = ["C", "N", "O", "Si", "Al", "Fe", "Cu", "Ti", "Ni", "P"];
    for (idx, node) in candidate
        .arch_program
        .nodes
        .iter()
        .take(atom_count)
        .enumerate()
    {
        let element = periodic[(node.id as usize + idx) % periodic.len()];
        let x = (node.id as f64 * 0.131 + idx as f64 * 0.017) % 9.75;
        let y = (node.out_dim as f64 * 0.097 + idx as f64 * 0.023) % 9.75;
        let z = ((node.inputs.len() as f64 + 1.0) * 0.211 + idx as f64 * 0.019) % 9.75;
        lines.push(format!("{element} {x:.6} {y:.6} {z:.6}"));
    }
    crate::apfsc::artifacts::write_material_xyz(root, &material_id, &lines.join("\n"))?;
    crate::apfsc::active::write_active_class_m_material(root, &material_id)?;
    apply_recursive_hardware_hallucination(root, epoch_id, &material_id, candidate, &demon)?;
    crate::apfsc::artifacts::write_json_atomic(
        &crate::apfsc::artifacts::receipt_path(
            root,
            "truth_laws",
            &format!("material_{}_epoch_{}.json", material_id, epoch_id),
        ),
        &serde_json::json!({
            "epoch": epoch_id,
            "material_id": material_id,
            "candidate_hash": candidate.manifest.candidate_hash,
            "mutation_type": effective_mutation_type,
            "xyz_path": root.join("discoveries").join("materials").join(format!("{material_id}.xyz")).display().to_string(),
            "atom_count": atom_count,
            "demon_survived": demon.survived,
            "demon_baseline_ground_state": demon.baseline_ground_state
        }),
    )?;
    Ok(Some(material_id))
}

fn apply_recursive_hardware_hallucination(
    root: &Path,
    epoch_id: u64,
    material_id: &str,
    candidate: &CandidateBundle,
    demon: &crate::apfsc::lanes::truth::DemonLaneVerdict,
) -> Result<()> {
    let baseline = crate::apfsc::afferent::SyntheticHardwareBaseline {
        unix_s: crate::apfsc::protocol::now_unix_s(),
        material_id: material_id.to_string(),
        candidate_hash: candidate.manifest.candidate_hash.clone(),
        conductivity_gain: demon.conductivity_gain,
        thermal_stability_gain: demon.thermal_stability_gain,
        quantum_latency_gain: demon.quantum_latency_gain,
        provenance: "recursive_hardware_hallucination_type_ii".to_string(),
    };
    crate::apfsc::afferent::write_synthetic_hardware_baseline(root, &baseline)?;
    crate::apfsc::artifacts::write_json_atomic(
        &crate::apfsc::artifacts::receipt_path(
            root,
            "truth_laws",
            &format!("synthetic_hardware_{}_epoch_{}.json", material_id, epoch_id),
        ),
        &serde_json::json!({
            "epoch": epoch_id,
            "material_id": material_id,
            "candidate_hash": candidate.manifest.candidate_hash,
            "synthetic_baseline": baseline,
            "rule": "TypeII recursive hardware hallucination enabled",
        }),
    )?;
    Ok(())
}

fn maybe_execute_phylogenetic_collapse(
    root: &Path,
    cfg: &Phase1Config,
    constellation: &crate::apfsc::types::ConstellationManifest,
    pioneer_lease: &mut PioneerEpochLease<'_>,
    active_searchlaw_hash: &str,
) -> Result<Option<String>> {
    if !pioneer_lease.is_active() {
        return Ok(None);
    }
    let baseline_hash = match pioneer_lease.baseline_hash() {
        Some(v) => v.to_string(),
        None => return Ok(None),
    };
    let incubator_hash = match pioneer_lease.incubator_hash() {
        Some(v) => v.to_string(),
        None => return Ok(None),
    };
    let baseline = load_candidate(root, &baseline_hash)?;
    let incubator = load_candidate(root, &incubator_hash)?;

    let public_static = evaluate_static_panel(
        root,
        &incubator,
        &baseline,
        constellation,
        PanelKind::StaticPublic,
    )?;
    let holdout_static = evaluate_static_panel(
        root,
        &incubator,
        &baseline,
        constellation,
        PanelKind::StaticHoldout,
    )?;
    let holdout_transfer = evaluate_transfer(
        root,
        &incubator,
        &baseline,
        constellation,
        EvalMode::Holdout,
    )
    .ok();
    let holdout_robust = evaluate_robustness(
        root,
        &incubator,
        &baseline,
        constellation,
        EvalMode::Holdout,
    )
    .ok();

    let mut bridge_receipt = None;
    let mut recent_receipt = None;
    match incubator.manifest.promotion_class {
        PromotionClass::A | PromotionClass::PWarm => {
            if let Some(pack) = &incubator.bridge_pack {
                if let Ok(b) = crate::apfsc::bridge::evaluate_warm_bridge(
                    root,
                    &incubator,
                    &baseline,
                    constellation,
                    pack,
                ) {
                    bridge_receipt = Some(b);
                }
            }
            if let Some(transfer_eval) = holdout_transfer.as_ref() {
                recent_receipt = Some(crate::apfsc::fresh_contact::recent_family_gain(
                    &incubator.manifest.candidate_hash,
                    &baseline.manifest.candidate_hash,
                    &transfer_eval.receipt,
                    &holdout_static.receipt,
                    &constellation.fresh_families,
                    0,
                    cfg.phase3.promotion.p_warm_min_recent_family_gain_bpb,
                ));
            }
        }
        PromotionClass::PCold => {
            let cold_pack = crate::apfsc::types::ColdBoundaryPack {
                protected_panels: vec!["anchor".to_string()],
                max_anchor_regret_bpb: cfg.phase3.promotion.p_cold_max_anchor_regret_bpb,
                max_error_streak: cfg.phase3.promotion.p_cold_max_error_streak,
                required_transfer_gain_bpb: cfg.phase3.promotion.p_cold_min_transfer_delta_bpb,
                required_recent_family_gain_bpb: cfg
                    .phase3
                    .promotion
                    .p_cold_min_recent_family_gain_bpb,
                mandatory_canary_windows: cfg.phase3.canary.cold_windows,
                rollback_target_hash: baseline.manifest.candidate_hash.clone(),
            };
            if let Ok((bridge, recent)) = crate::apfsc::bridge::evaluate_cold_boundary(
                root,
                &incubator,
                &baseline,
                constellation,
                &cold_pack,
                &constellation.fresh_families,
                0,
            ) {
                bridge_receipt = Some(bridge);
                recent_receipt = Some(recent);
            }
        }
        _ => {}
    }

    let evals = Phase2CandidateEvaluations {
        public_static,
        public_transfer: None,
        public_robust: None,
        holdout_static,
        holdout_transfer,
        holdout_robust,
    };
    let mut strict_cfg = cfg.clone();
    strict_cfg.phase3.promotion.paradigm_shift_allowance_bpb = 0.0;
    let mut receipt = judge_phase3_candidate(
        root,
        &incubator,
        &baseline,
        constellation,
        &strict_cfg,
        &evals,
        bridge_receipt.as_ref(),
        recent_receipt.as_ref(),
    )?;

    let class_r_supremacy = evals
        .public_static
        .receipt
        .improved_families
        .iter()
        .chain(evals.holdout_static.receipt.improved_families.iter())
        .any(|fid| {
            let f = fid.to_ascii_lowercase();
            f.starts_with("class_r")
                || f.contains("class_r")
                || f.contains("synthetic_alien")
                || f.contains("coev_r")
        });
    let class_r_allowance = cfg.phase3.promotion.class_r_takeover_allowance_bpb.max(0.0);
    let strict_win = if class_r_supremacy {
        evals.public_static.delta_bpb >= -class_r_allowance
            && evals.holdout_static.delta_bpb >= -class_r_allowance
            && matches!(receipt.decision, JudgeDecision::Promote)
    } else {
        evals.public_static.delta_bpb > 0.0
            && evals.holdout_static.delta_bpb > 0.0
            && matches!(receipt.decision, JudgeDecision::Promote)
    };

    crate::apfsc::artifacts::write_json_atomic(
        &crate::apfsc::artifacts::receipt_path(
            root,
            "judge",
            &format!("{}.json", incubator.manifest.candidate_hash),
        ),
        &receipt,
    )?;
    if !strict_win {
        return Ok(None);
    }

    // Endosymbiosis: preserve the displaced incumbent as an immutable Subcortex prior and
    // splice it into the new structural winner before activation.
    let subcortex_prior_hash = persist_subcortex_prior(root, &baseline)?;
    let mut collapsed = incubator.clone();
    inject_subcortex_endosymbiosis(
        &mut collapsed,
        &subcortex_prior_hash,
        &baseline.manifest.candidate_hash,
    )?;
    save_candidate(root, &collapsed)?;

    crate::apfsc::judge::activate_candidate(
        root,
        &collapsed.manifest.candidate_hash,
        &collapsed.manifest.snapshot_hash,
    )?;
    let incubator_law = crate::apfsc::active::read_active_incubator_search_law(root)
        .ok()
        .filter(|h| !h.is_empty())
        .unwrap_or_else(|| active_searchlaw_hash.to_string());
    crate::apfsc::active::write_active_search_law(root, &incubator_law)?;
    remove_pointer_file(root, "active_incubator_pointer");
    remove_pointer_file(root, "pioneer_epoch_baseline_candidate");
    remove_pointer_file(root, "active_epoch_mode");
    pioneer_lease.commit_collapse();
    let _ = wipe_global_qd_archive(root);
    let _ = append_era_shift(
        root,
        &collapsed.manifest.candidate_hash,
        Some(&incubator_law),
    );

    receipt.candidate_hash = collapsed.manifest.candidate_hash.clone();
    receipt.reason = "Promote(PhylogeneticCollapse)".to_string();
    crate::apfsc::artifacts::write_json_atomic(
        &crate::apfsc::artifacts::receipt_path(
            root,
            "activation",
            &format!("{}.json", collapsed.manifest.candidate_hash),
        ),
        &receipt,
    )?;
    Ok(Some(collapsed.manifest.candidate_hash))
}

pub fn run_phase4_epoch(
    root: &Path,
    cfg: &Phase1Config,
    requested_constellation: Option<&str>,
) -> Result<EpochReport> {
    let current_epoch = current_epoch_index(root)?;
    let _ = crate::apfsc::afferent::append_epoch_sample(root, current_epoch);
    let _ = maybe_pause_for_exogenous_hunger(root, cfg, current_epoch);
    let _ = refresh_truth_law_constraints(root, current_epoch)?;
    let era_cfg = apply_era_pressure(cfg, root);
    let ectoderm_cfg = apply_ectoderm_overrides(root, &era_cfg, current_epoch);
    let extropy_cfg = apply_extropy_guardrail(root, &ectoderm_cfg, current_epoch);
    let cfg = &extropy_cfg;
    let mut pioneer_lease = PioneerEpochLease::enter(root, cfg, current_epoch)?;
    let mut report = run_phase3_epoch(root, cfg, requested_constellation)?;
    let active = load_active_candidate(root)?;
    let constellation = resolve_constellation(root, requested_constellation)?;
    let class_m_override_active = crate::apfsc::afferent::channel_seed_vector_from_root(root, 3, 8)
        .map(|v| !v.is_empty())
        .unwrap_or(false);
    let hidden_manifest = load_or_build_hidden_challenge_manifest(root, cfg, current_epoch)?;

    let active_searchlaw = ensure_active_search_law(root)?;
    let mut law_records = load_law_records(root).unwrap_or_default();
    let law_summary = build_law_summary(root, &active_searchlaw.manifest_hash)?;
    let max_tokens = cfg
        .phase4
        .max_qd_cells
        .min(crate::apfsc::constants::MAX_LAWTOKENS_PER_EPOCH as usize)
        .max(1);
    let law_tokens = distill_law_tokens(&law_records, max_tokens)?;
    persist_law_tokens(root, &law_tokens)?;

    let features = build_searchlaw_features(root, &constellation, &law_summary)?;
    let mut search_plan = build_search_plan(
        &active_searchlaw,
        &features,
        &law_tokens,
        current_epoch,
        cfg.phase4.max_needtokens_per_epoch,
    );
    search_plan
        .need_tokens
        .truncate(cfg.phase4.max_needtokens_per_epoch);
    emit_need_tokens(root, &search_plan.need_tokens)?;

    let (mut portfolio, mut branches) = load_or_init_portfolio(
        root,
        &constellation.snapshot_hash,
        &constellation.constellation_id,
        &active_searchlaw.manifest_hash,
        cfg,
    )?;
    allocate_branch_budget(root, &mut portfolio, &mut branches, &search_plan, cfg)?;

    // Phase-4 lane expansion: materialize additional deterministic candidates and attach
    // dependency+phase4 metadata without disturbing the phase3 judged path.
    let macro_registry =
        load_or_build_active_registry(root, &constellation.snapshot_hash, &cfg.protocol.version)?;
    let snap_hash = crate::apfsc::artifacts::read_pointer(root, "active_snapshot")?;
    let snapshot: crate::apfsc::types::EpochSnapshot =
        crate::apfsc::artifacts::load_snapshot(root, &snap_hash)?;
    let formal_policy = load_active_formal_policy(root).unwrap_or_else(|_| seed_formal_policy());

    let mut phase4_train_windows = Vec::new();
    let mut phase4_public_windows = Vec::new();
    for fam in &constellation.family_specs {
        phase4_train_windows.extend(
            load_family_panel_windows(root, &fam.family_id, PanelKind::Train.as_key())?.into_iter(),
        );
        phase4_public_windows.extend(
            load_family_panel_windows(root, &fam.family_id, PanelKind::StaticPublic.as_key())?
                .into_iter(),
        );
    }
    let mut phase4_path_windows = phase4_train_windows.clone();
    phase4_path_windows.extend(phase4_public_windows.iter().cloned());
    let phase4_payloads = load_payload_index_for_windows(root, &phase4_path_windows)?;
    let incubated = lanes::incubator::generate(
        &active,
        cfg,
        &phase4_train_windows,
        &phase4_public_windows,
        &phase4_payloads,
    )?;
    let splice = lanes::incubator::materialize_splice_candidates(&active, incubated, cfg)?;

    let mut phase4_pool = Vec::new();
    phase4_pool.extend(lanes::truth::generate_phase3(&active, cfg)?);
    phase4_pool.extend(lanes::equivalence::generate(&active, cfg)?);
    phase4_pool.extend(splice);
    phase4_pool.extend(lanes::incubator::phase3_macro_aware_candidates(
        &active, cfg,
    )?);
    phase4_pool.extend(lanes::cold_frontier::generate(&active, cfg)?);
    phase4_pool.extend(lanes::recombination::generate(root, &active, cfg)?);
    phase4_pool.extend(lanes::tool_shadow::generate(&active, cfg)?);
    let mut phase4_pool = merge_and_dedup(phase4_pool);
    phase4_pool.retain(|cand| {
        verify_program_with_formal_policy(
            &cand.arch_program,
            &cand.manifest.resource_envelope,
            &formal_policy,
        )
        .is_ok()
    });

    for (idx, cand) in phase4_pool.iter_mut().enumerate() {
        save_candidate(root, cand)?;
        let dep = build_dependency_pack(
            root,
            snapshot.prior_roots.clone(),
            snapshot.tool_roots.clone(),
            snapshot.substrate_roots.clone(),
            &macro_registry.registry_id,
        )?;
        write_candidate_dependency_pack(root, &cand.manifest.candidate_hash, &dep)?;

        let branch_id = branches
            .get(idx % branches.len().max(1))
            .map(|b| b.branch_id.clone())
            .unwrap_or_else(|| "b000".to_string());
        let phase4 = CandidatePhase4Meta {
            build: Phase4BuildMeta {
                target_families: constellation
                    .family_specs
                    .iter()
                    .map(|f| f.family_id.clone())
                    .collect(),
                source_lane: cand.build_meta.lane.clone(),
                phase4_profile: "phase4".to_string(),
                searchlaw_hash: active_searchlaw.manifest_hash.clone(),
                dependency_pack_hash: dep.manifest_hash.clone(),
                branch_id,
                recombination_parent_hashes: cand.manifest.parent_hashes.clone(),
            },
            search_object: SearchObjectKind::Architecture,
        };
        set_phase4_build_meta(cand, phase4)?;
        save_candidate(root, cand)?;
    }

    // Challenge gate for any phase3-promoted architecture receipts.
    for receipt in &mut report.judge_report.receipts {
        let candidate_bundle = load_candidate(root, &receipt.candidate_hash).ok();
        if let Some(c) = candidate_bundle.as_ref() {
            let mutation = c.build_meta.mutation_type.to_ascii_lowercase();
            if mutation.contains("class_h_hypothesis") {
                let _ = crate::apfsc::active::write_active_class_h_hypothesis(
                    root,
                    &receipt.candidate_hash,
                );
            }
            if class_m_override_active || mutation.contains("class_m_probe") {
                let _ = maybe_emit_class_m_material(root, current_epoch, c);
            }
        }
        if receipt.decision != JudgeDecision::Promote {
            continue;
        }

        let challenge = score_hidden_challenge_gate(
            &receipt.candidate_hash,
            &receipt.incumbent_hash,
            &hidden_manifest,
            &cfg.protocol.version,
        )?;
        crate::apfsc::artifacts::write_json_atomic(
            &crate::apfsc::artifacts::receipt_path(
                root,
                "challenge",
                &format!("{}.json", receipt.candidate_hash),
            ),
            &challenge,
        )?;
        crate::apfsc::artifacts::write_json_atomic(
            &root
                .join("candidates")
                .join(&receipt.candidate_hash)
                .join("challenge_receipt.json"),
            &challenge,
        )?;

        if !challenge.pass && cfg.phase4.enable_hidden_challenge_gate {
            receipt.decision = JudgeDecision::Reject;
            receipt.reason = JudgeRejectReason::ChallengeGateFail.as_reason();
            crate::apfsc::artifacts::write_json_atomic(
                &crate::apfsc::artifacts::receipt_path(
                    root,
                    "judge",
                    &format!("{}.json", receipt.candidate_hash),
                ),
                receipt,
            )?;
            if let Ok(active_hash) = crate::apfsc::artifacts::read_pointer(root, "active_candidate")
            {
                if active_hash == receipt.candidate_hash {
                    if let Ok(rollback) =
                        crate::apfsc::artifacts::read_pointer(root, "rollback_candidate")
                    {
                        let rb = load_active_candidate(root)
                            .ok()
                            .map(|_| rollback)
                            .unwrap_or_else(|| receipt.incumbent_hash.clone());
                        let _ =
                            crate::apfsc::artifacts::write_pointer(root, "active_candidate", &rb);
                    }
                }
            }
            continue;
        }

        let class = receipt.promotion_class.unwrap_or(PromotionClass::S);
        let yield_points = points_for_class(class, challenge.aggregate_bucket_score > 0, cfg);
        let lane = candidate_bundle
            .as_ref()
            .map(|c| c.build_meta.lane.clone())
            .unwrap_or_else(|| "unknown".to_string());
        let branch_id = candidate_bundle
            .as_ref()
            .and_then(|c| c.build_meta.phase4.clone().map(|p| p.build.branch_id))
            .unwrap_or_else(|| "b000".to_string());
        let morphology_hash = crate::apfsc::artifacts::digest_json(&(
            class,
            &lane,
            &receipt.candidate_hash,
            &constellation.constellation_id,
        ))?;
        let qd_cell_id = crate::apfsc::artifacts::digest_json(&(
            &morphology_hash,
            &constellation.snapshot_hash,
        ))?;

        let law_record = crate::apfsc::types::LawArchiveRecord {
            record_id: String::new(),
            candidate_hash: receipt.candidate_hash.clone(),
            parent_hashes: candidate_bundle
                .as_ref()
                .map(|c| c.manifest.parent_hashes.clone())
                .unwrap_or_default(),
            searchlaw_hash: active_searchlaw.manifest_hash.clone(),
            promotion_class: class,
            source_lane: lane,
            family_outcome_buckets: challenge
                .family_bucket_passes
                .iter()
                .map(|(k, v)| (k.clone(), if *v { 1 } else { -1 }))
                .collect(),
            challenge_bucket: challenge.aggregate_bucket_score as i8,
            canary_survived: receipt.canary_result.as_deref() != Some("fail"),
            yield_points,
            compute_units: (1 + receipt.candidate_hash.len()) as u64,
            morphology_hash: morphology_hash.clone(),
            qd_cell_id: qd_cell_id.clone(),
            snapshot_hash: receipt.snapshot_hash.clone(),
            constellation_id: receipt
                .constellation_id
                .clone()
                .unwrap_or_else(|| constellation.constellation_id.clone()),
        };
        let stored_record = append_law_record(root, law_record)?;
        law_records.push(stored_record);

        let _ = mint_credit(
            root,
            &portfolio.portfolio_id,
            &branch_id,
            yield_points.max(0),
            "judged_promotion",
            Some(receipt.candidate_hash.clone()),
            Some(crate::apfsc::artifacts::digest_json(receipt)?),
        );

        let qd = QdCellRecord {
            cell_id: qd_cell_id,
            descriptor: MorphologyDescriptor {
                paradigm_signature_hash: morphology_hash,
                scheduler_class: "unknown".to_string(),
                memory_law_kind: "unknown".to_string(),
                macro_density_bin: "mid".to_string(),
                state_bytes_bin: "small".to_string(),
                family_profile_bin: "mixed".to_string(),
            },
            occupant_candidate_hash: receipt.candidate_hash.clone(),
            public_quality_score: receipt.weighted_static_public_delta_bpb,
            novelty_score: 1.0,
            last_updated_epoch: current_epoch,
        };
        let _ = upsert_cell(root, &constellation.snapshot_hash, qd);
    }

    let mut epoch_searchlaw_receipts: Vec<PromotionReceipt> = Vec::new();
    if cfg.phase4.enable_searchlaw {
        let macro_period = cfg.phase4.searchlaw_min_ab_epochs.max(1) as u64;
        let pioneer_active = pioneer_lease.is_active();
        let run_searchlaw_cycle = pioneer_active || current_epoch % macro_period == 0;
        if run_searchlaw_cycle {
            let searchlaw_receipts = if cfg.phase4.polyphasic_async_lanes {
                let root_buf = root.to_path_buf();
                let cfg_clone = cfg.clone();
                let active_searchlaw_clone = active_searchlaw.clone();
                let features_clone = features.clone();
                let law_tokens_clone = law_tokens.clone();
                let law_records_clone = law_records.clone();
                let snapshot_hash = constellation.snapshot_hash.clone();
                let constellation_id = constellation.constellation_id.clone();
                thread::spawn(move || {
                    run_searchlaw_cycle_once(
                        &root_buf,
                        &cfg_clone,
                        &active_searchlaw_clone,
                        &features_clone,
                        &law_tokens_clone,
                        &law_records_clone,
                        &snapshot_hash,
                        &constellation_id,
                        pioneer_active,
                    )
                })
                .join()
                .map_err(|_| {
                    ApfscError::Protocol("polyphasic searchlaw worker panicked".to_string())
                })??
            } else {
                run_searchlaw_cycle_once(
                    root,
                    cfg,
                    &active_searchlaw,
                    &features,
                    &law_tokens,
                    &law_records,
                    &constellation.snapshot_hash,
                    &constellation.constellation_id,
                    pioneer_active,
                )?
            };
            epoch_searchlaw_receipts = searchlaw_receipts.clone();
            report
                .judge_report
                .receipts
                .extend(searchlaw_receipts.into_iter());
        }
    }
    let _ = maybe_autonomic_thermal_spike(root, current_epoch, &epoch_searchlaw_receipts);

    if let Some(collapsed_hash) = maybe_execute_phylogenetic_collapse(
        root,
        cfg,
        &constellation,
        &mut pioneer_lease,
        &active_searchlaw.manifest_hash,
    )? {
        crate::apfsc::artifacts::append_jsonl_atomic(
            &root.join("archives").join("phylogenetic_collapse.jsonl"),
            &serde_json::json!({
                "candidate_hash": collapsed_hash,
                "epoch": current_epoch,
                "constellation_id": constellation.constellation_id,
                "ts": crate::apfsc::protocol::now_unix_s(),
            }),
        )?;
    }

    let _ = rotate_hidden_challenges(root, cfg, current_epoch + 1)?;
    let _ = cull_unproductive_branches(root, &mut portfolio, &mut branches, cfg)?;
    Ok(report)
}

fn run_searchlaw_cycle_once(
    root: &Path,
    cfg: &Phase1Config,
    active_searchlaw: &crate::apfsc::types::SearchLawPack,
    features: &crate::apfsc::types::SearchLawFeatureVector,
    law_tokens: &[crate::apfsc::types::LawToken],
    law_records: &[crate::apfsc::types::LawArchiveRecord],
    snapshot_hash: &str,
    constellation_id: &str,
    pioneer_active: bool,
) -> Result<Vec<crate::apfsc::types::PromotionReceipt>> {
    let mut receipts = Vec::new();
    let g_candidates =
        generate_search_law_candidates(root, active_searchlaw, features, law_tokens, cfg)?;
    let max_ab = cfg.phase4.max_searchlaw_ab_candidates.max(1);
    let ab_epochs = cfg
        .phase4
        .searchlaw_min_ab_epochs
        .max(1)
        .min(cfg.phase4.searchlaw_max_ab_epochs.max(1));
    for cand in g_candidates.iter().take(max_ab) {
        let offline = evaluate_searchlaw_offline(
            root,
            cand,
            law_records,
            snapshot_hash,
            constellation_id,
            &cfg.protocol.version,
        )?;
        let ab = evaluate_searchlaw_ab(
            root,
            cand,
            active_searchlaw,
            &offline,
            law_records,
            ab_epochs,
            cfg,
            snapshot_hash,
            constellation_id,
            &cfg.protocol.version,
        )?;
        let g_receipt = judge_searchlaw_candidate(
            cand,
            active_searchlaw,
            &offline,
            &ab,
            cfg,
            snapshot_hash,
            constellation_id,
            &cfg.protocol.version,
        );
        crate::apfsc::artifacts::write_json_atomic(
            &crate::apfsc::artifacts::receipt_path(
                root,
                "judge",
                &format!("{}.json", cand.manifest_hash),
            ),
            &g_receipt,
        )?;
        receipts.push(g_receipt.clone());
        let _promo = promote_search_law_if_pass(
            root,
            cand,
            active_searchlaw,
            &ab,
            snapshot_hash,
            constellation_id,
            &cfg.protocol.version,
        )?;
        if g_receipt.decision == JudgeDecision::Promote {
            break;
        }
    }
    if pioneer_active {
        let _ = crate::apfsc::artifacts::append_jsonl_atomic(
            &root
                .join("archives")
                .join("searchlaw_polyphasic_trace.jsonl"),
            &serde_json::json!({
                "ts": crate::apfsc::protocol::now_unix_s(),
                "mode": "pioneer",
                "receipts": receipts.len(),
            }),
        );
    }
    Ok(receipts)
}
