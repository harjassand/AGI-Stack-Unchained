use std::collections::BTreeMap;
use std::path::Path;

use crate::apfsc::artifacts::digest_json;
use crate::apfsc::bank::{load_family_panel_windows, load_payload_index_for_windows};
use crate::apfsc::bytecoder::score_panel_with_resid_scales;
use crate::apfsc::candidate::CandidateBundle;
use crate::apfsc::errors::Result;
use crate::apfsc::types::{
    ConstellationManifest, ConstellationScoreReceipt, FamilyEvalVector, FamilyId,
    FamilyPanelMetric, PanelKind,
};

#[derive(Debug, Clone)]
pub struct PanelComparison {
    pub receipt: ConstellationScoreReceipt,
    pub candidate_weighted_bpb: f64,
    pub incumbent_weighted_bpb: f64,
    pub delta_bpb: f64,
    pub protected_floor_failures: Vec<FamilyId>,
    pub family_deltas: BTreeMap<FamilyId, f64>,
}

pub fn code_len_bits(candidate: &CandidateBundle) -> Result<u64> {
    let arch = serde_json::to_vec(&candidate.arch_program)?;
    let head = bincode::serialize(&candidate.head_pack).map_err(|e| {
        crate::apfsc::errors::ApfscError::Protocol(format!("head encode failed: {e}"))
    })?;
    let state = bincode::serialize(&candidate.state_pack).map_err(|e| {
        crate::apfsc::errors::ApfscError::Protocol(format!("state encode failed: {e}"))
    })?;
    let schedule = serde_json::to_vec(&candidate.schedule_pack)?;
    let bridge = match &candidate.bridge_pack {
        Some(v) => serde_json::to_vec(v)?,
        None => Vec::new(),
    };
    Ok(((arch.len() + head.len() + state.len() + schedule.len() + bridge.len()) as u64) * 8)
}

pub fn code_penalty_bpb(candidate: &CandidateBundle, codelen_ref_bytes: u64) -> Result<f64> {
    let bits = code_len_bits(candidate)?;
    Ok(bits as f64 / codelen_ref_bytes as f64)
}

pub fn evaluate_static_panel(
    root: &Path,
    candidate: &CandidateBundle,
    incumbent: &CandidateBundle,
    constellation: &ConstellationManifest,
    panel: PanelKind,
) -> Result<PanelComparison> {
    let panel_key = panel.as_key();
    let mut per_family = BTreeMap::<FamilyId, FamilyEvalVector>::new();
    let mut family_deltas = BTreeMap::<FamilyId, f64>::new();
    let mut improved_families = Vec::new();
    let mut nonprotected_improved_families = Vec::new();
    let mut regressed_families = Vec::new();
    let mut protected_floor_failures = Vec::new();

    let code_penalty_candidate =
        code_penalty_bpb(candidate, constellation.normalization.codelen_ref_bytes)?;
    let code_penalty_incumbent =
        code_penalty_bpb(incumbent, constellation.normalization.codelen_ref_bytes)?;

    let mut weighted_candidate = code_penalty_candidate;
    let mut weighted_incumbent = code_penalty_incumbent;

    let mut replay_components = Vec::new();

    for fam in &constellation.family_specs {
        let windows = load_family_panel_windows(root, &fam.family_id, panel_key)?;
        if windows.is_empty() {
            continue;
        }

        let payloads = load_payload_index_for_windows(root, &windows)?;
        let cand_summary = score_panel_with_resid_scales(
            &candidate.arch_program,
            &candidate.head_pack,
            Some(&candidate.state_pack.resid_weights),
            &payloads,
            &windows,
        )?;
        let inc_summary = score_panel_with_resid_scales(
            &incumbent.arch_program,
            &incumbent.head_pack,
            Some(&incumbent.state_pack.resid_weights),
            &payloads,
            &windows,
        )?;

        let target_bytes = windows.iter().map(|w| w.len as u64).sum::<u64>().max(1);
        let cand_bpb = cand_summary.total_bits / target_bytes as f64;
        let inc_bpb = inc_summary.total_bits / target_bytes as f64;
        let delta = inc_bpb - cand_bpb;

        weighted_candidate += fam.weights.static_weight * cand_bpb;
        weighted_incumbent += fam.weights.static_weight * inc_bpb;

        if delta >= fam.floors.min_family_improve_bpb {
            improved_families.push(fam.family_id.clone());
            if !fam.floors.protected {
                nonprotected_improved_families.push(fam.family_id.clone());
            }
        }
        if delta < 0.0 {
            regressed_families.push(fam.family_id.clone());
        }
        if fam.floors.protected && delta < -fam.floors.max_static_regress_bpb {
            protected_floor_failures.push(fam.family_id.clone());
        }

        family_deltas.insert(fam.family_id.clone(), delta);

        let mut vec = FamilyEvalVector {
            family_id: fam.family_id.clone(),
            static_public_bpb: None,
            static_holdout_bpb: None,
            anchor_bpb: None,
            transfer_public_bpb: None,
            transfer_holdout_bpb: None,
            robust_public_bpb: None,
            robust_holdout_bpb: None,
            challenge_stub_bpb: None,
        };
        match panel {
            PanelKind::StaticPublic => vec.static_public_bpb = Some(cand_bpb),
            PanelKind::StaticHoldout => vec.static_holdout_bpb = Some(cand_bpb),
            PanelKind::Anchor => vec.anchor_bpb = Some(cand_bpb),
            PanelKind::Canary => vec.anchor_bpb = Some(cand_bpb),
            _ => {}
        }
        per_family.insert(fam.family_id.clone(), vec);

        replay_components.push(FamilyPanelMetric {
            family_id: fam.family_id.clone(),
            panel,
            bits_total: cand_summary.total_bits,
            target_bytes,
            mean_bpb: cand_bpb,
            window_count: windows.len() as u64,
        });
    }

    improved_families.sort();
    nonprotected_improved_families.sort();
    regressed_families.sort();
    protected_floor_failures.sort();

    let target_subset_pass = if constellation.normalization.require_target_subset_hit {
        constellation
            .normalization
            .target_subset
            .iter()
            .all(|f| improved_families.binary_search(f).is_ok())
    } else {
        true
    };

    let mut receipt = ConstellationScoreReceipt {
        candidate_hash: candidate.manifest.candidate_hash.clone(),
        incumbent_hash: incumbent.manifest.candidate_hash.clone(),
        snapshot_hash: candidate.manifest.snapshot_hash.clone(),
        constellation_id: constellation.constellation_id.clone(),
        protocol_version: constellation.protocol_version.clone(),
        per_family,
        code_penalty_bpb: code_penalty_candidate,
        weighted_static_public_bpb: None,
        weighted_static_holdout_bpb: None,
        weighted_transfer_public_bpb: None,
        weighted_transfer_holdout_bpb: None,
        weighted_robust_public_bpb: None,
        weighted_robust_holdout_bpb: None,
        improved_families,
        nonprotected_improved_families,
        regressed_families,
        protected_floor_pass: protected_floor_failures.is_empty(),
        target_subset_pass,
        replay_hash: String::new(),
    };

    match panel {
        PanelKind::StaticPublic => receipt.weighted_static_public_bpb = Some(weighted_candidate),
        PanelKind::StaticHoldout => receipt.weighted_static_holdout_bpb = Some(weighted_candidate),
        _ => {}
    }

    receipt.replay_hash = digest_json(&(receipt.clone(), replay_components))?;

    Ok(PanelComparison {
        receipt,
        candidate_weighted_bpb: weighted_candidate,
        incumbent_weighted_bpb: weighted_incumbent,
        delta_bpb: weighted_incumbent - weighted_candidate,
        protected_floor_failures,
        family_deltas,
    })
}

pub fn weighted_static_score_from_family_bpb(
    constellation: &ConstellationManifest,
    code_penalty_bpb: f64,
    per_family_bpb: &BTreeMap<FamilyId, f64>,
) -> f64 {
    let mut out = code_penalty_bpb;
    for fam in &constellation.family_specs {
        out +=
            fam.weights.static_weight * per_family_bpb.get(&fam.family_id).copied().unwrap_or(0.0);
    }
    out
}

pub fn improved_family_ids_from_static_holdout_deltas(
    constellation: &ConstellationManifest,
    deltas: &BTreeMap<FamilyId, f64>,
) -> Vec<FamilyId> {
    let mut out = Vec::new();
    for fam in &constellation.family_specs {
        let delta = *deltas.get(&fam.family_id).unwrap_or(&0.0);
        if delta >= fam.floors.min_family_improve_bpb {
            out.push(fam.family_id.clone());
        }
    }
    out.sort();
    out
}

pub fn apply_transfer_weighted_scores(
    constellation: &ConstellationManifest,
    per_family_candidate: &BTreeMap<FamilyId, f64>,
    per_family_incumbent: &BTreeMap<FamilyId, f64>,
) -> (f64, f64, BTreeMap<FamilyId, f64>) {
    let mut cand = 0.0;
    let mut inc = 0.0;
    let mut deltas = BTreeMap::new();
    for fam in &constellation.family_specs {
        let c = *per_family_candidate.get(&fam.family_id).unwrap_or(&0.0);
        let i = *per_family_incumbent.get(&fam.family_id).unwrap_or(&0.0);
        cand += fam.weights.transfer_weight * c;
        inc += fam.weights.transfer_weight * i;
        deltas.insert(fam.family_id.clone(), i - c);
    }
    (cand, inc, deltas)
}

pub fn apply_robust_weighted_scores(
    constellation: &ConstellationManifest,
    per_family_candidate: &BTreeMap<FamilyId, f64>,
    per_family_incumbent: &BTreeMap<FamilyId, f64>,
) -> (f64, f64, BTreeMap<FamilyId, f64>) {
    let mut cand = 0.0;
    let mut inc = 0.0;
    let mut deltas = BTreeMap::new();
    for fam in &constellation.family_specs {
        let c = *per_family_candidate.get(&fam.family_id).unwrap_or(&0.0);
        let i = *per_family_incumbent.get(&fam.family_id).unwrap_or(&0.0);
        cand += fam.weights.robust_weight * c;
        inc += fam.weights.robust_weight * i;
        deltas.insert(fam.family_id.clone(), i - c);
    }
    (cand, inc, deltas)
}
