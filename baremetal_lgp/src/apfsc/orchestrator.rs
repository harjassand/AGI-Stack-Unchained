use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;

use rayon::prelude::*;

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
    judge_searchlaw_candidate, run_batch,
    write_split_receipt, Phase2CandidateEvaluations,
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
    Phase3BuildMeta, Phase4BuildMeta, PromotionClass, PublicEvalRecord, QdCellRecord,
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
    if !path.exists() {
        return Ok(0);
    }
    let text =
        std::fs::read_to_string(&path).map_err(|e| crate::apfsc::errors::io_err(&path, e))?;
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
            let static_cmp =
                evaluate_static_panel(root, &cand, &active, &constellation, PanelKind::StaticPublic)?;
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
    let transfer_results: Vec<Option<(
        String,
        crate::apfsc::transfer::TransferEvaluation,
    )>> = public_a_candidates
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
    let robust_results: Vec<Option<(
        String,
        crate::apfsc::robustness::RobustnessEvaluation,
    )>> = public_robust_candidates
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
            let static_cmp =
                evaluate_static_panel(root, &cand, &active, &constellation, PanelKind::StaticPublic)?;
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
    let transfer_results: Vec<Option<(
        String,
        crate::apfsc::transfer::TransferEvaluation,
    )>> = structural_public_candidates
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
    let robust_results: Vec<Option<(
        String,
        crate::apfsc::robustness::RobustnessEvaluation,
    )>> = structural_public_candidates
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

pub fn run_phase4_epoch(
    root: &Path,
    cfg: &Phase1Config,
    requested_constellation: Option<&str>,
) -> Result<EpochReport> {
    let mut report = run_phase3_epoch(root, cfg, requested_constellation)?;
    let active = load_active_candidate(root)?;
    let constellation = resolve_constellation(root, requested_constellation)?;
    let current_epoch = current_epoch_index(root)?;
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
        let lane = load_candidate(root, &receipt.candidate_hash)
            .ok()
            .map(|c| c.build_meta.lane)
            .unwrap_or_else(|| "unknown".to_string());
        let branch_id = load_candidate(root, &receipt.candidate_hash)
            .ok()
            .and_then(|c| c.build_meta.phase4.map(|p| p.build.branch_id))
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
            parent_hashes: load_candidate(root, &receipt.candidate_hash)
                .ok()
                .map(|c| c.manifest.parent_hashes)
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

    if cfg.phase4.enable_searchlaw {
        let macro_period = cfg.phase4.searchlaw_min_ab_epochs.max(1) as u64;
        let run_searchlaw_cycle = current_epoch % macro_period == 0;
        if run_searchlaw_cycle {
            let g_candidates =
                generate_search_law_candidates(root, &active_searchlaw, &features, &law_tokens, cfg)?;
            for cand in g_candidates
                .iter()
                .take(cfg.phase4.max_searchlaw_ab_candidates.max(1))
            {
                let offline = evaluate_searchlaw_offline(
                    root,
                    cand,
                    &law_records,
                    &constellation.snapshot_hash,
                    &constellation.constellation_id,
                    &cfg.protocol.version,
                )?;
                let ab_epochs = cfg
                    .phase4
                    .searchlaw_min_ab_epochs
                    .max(1)
                    .min(cfg.phase4.searchlaw_max_ab_epochs.max(1));
                let ab = evaluate_searchlaw_ab(
                    root,
                    cand,
                    &active_searchlaw,
                    &offline,
                    &law_records,
                    ab_epochs,
                    cfg,
                    &constellation.snapshot_hash,
                    &constellation.constellation_id,
                    &cfg.protocol.version,
                )?;
                let g_receipt = judge_searchlaw_candidate(
                    cand,
                    &active_searchlaw,
                    &offline,
                    &ab,
                    cfg,
                    &constellation.snapshot_hash,
                    &constellation.constellation_id,
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
                report.judge_report.receipts.push(g_receipt.clone());
                let _promo = promote_search_law_if_pass(
                    root,
                    cand,
                    &active_searchlaw,
                    &ab,
                    &constellation.snapshot_hash,
                    &constellation.constellation_id,
                    &cfg.protocol.version,
                )?;
                if g_receipt.decision == JudgeDecision::Promote {
                    break;
                }
            }
        }
    }

    let _ = rotate_hidden_challenges(root, cfg, current_epoch + 1)?;
    let _ = cull_unproductive_branches(root, &mut portfolio, &mut branches, cfg)?;
    Ok(report)
}
