use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;

use crate::apfsc::archive::{error_atlas, failure_morph, genealogy, hardware_trace};
use crate::apfsc::bank::{load_bank, load_payload_index_for_windows, WindowBank};
use crate::apfsc::candidate::{
    load_active_candidate, rehash_candidate, save_candidate, CandidateBundle,
};
use crate::apfsc::config::Phase1Config;
use crate::apfsc::errors::{ApfscError, Result};
use crate::apfsc::hardware_oracle::{load_oracle, oracle_penalty, OracleFeatures};
use crate::apfsc::headpack::HeadOnlyAdaGradLaw;
use crate::apfsc::ingress::judge::PendingAdmission;
use crate::apfsc::judge::{evaluate_candidate_split, run_batch, write_split_receipt};
use crate::apfsc::lanes;
use crate::apfsc::scir::verify::verify_program;
use crate::apfsc::types::{EpochReport, PublicEvalRecord, SplitKind, WitnessSelection};

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
