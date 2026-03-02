use std::collections::BTreeMap;
use std::path::Path;

use crate::apfsc::artifacts::digest_json;
use crate::apfsc::bank::{load_family_panel_windows, load_payload_index_for_windows};
use crate::apfsc::bytecoder::score_panel_with_resid_scales;
use crate::apfsc::candidate::CandidateBundle;
use crate::apfsc::errors::Result;
use crate::apfsc::normalization::{apply_robust_weighted_scores, select_eval_windows};
use crate::apfsc::types::{
    ConstellationManifest, ConstellationScoreReceipt, EvalMode, FamilyEvalVector, FamilyId,
    PanelKind, RobustnessFamilyTrace,
};

#[derive(Debug, Clone)]
pub struct RobustnessEvaluation {
    pub receipt: ConstellationScoreReceipt,
    pub candidate_weighted_bpb: f64,
    pub incumbent_weighted_bpb: f64,
    pub delta_bpb: f64,
    pub protected_floor_failures: Vec<FamilyId>,
    pub family_deltas: BTreeMap<FamilyId, f64>,
    pub traces: Vec<RobustnessFamilyTrace>,
}

pub fn evaluate_robustness(
    root: &Path,
    candidate: &CandidateBundle,
    incumbent: &CandidateBundle,
    constellation: &ConstellationManifest,
    mode: EvalMode,
) -> Result<RobustnessEvaluation> {
    let panel_key = match mode {
        EvalMode::Public => PanelKind::RobustPublic,
        EvalMode::Holdout => PanelKind::RobustHoldout,
    };

    let mut per_family = BTreeMap::<FamilyId, FamilyEvalVector>::new();
    let mut candidate_scores = BTreeMap::<FamilyId, f64>::new();
    let mut incumbent_scores = BTreeMap::<FamilyId, f64>::new();
    let mut protected_floor_failures = Vec::<FamilyId>::new();
    let mut traces = Vec::new();

    for fam in &constellation.family_specs {
        let mut windows = load_family_panel_windows(root, &fam.family_id, panel_key.as_key())?;
        if matches!(mode, EvalMode::Holdout)
            && constellation.normalization.holdout_eval_max_bytes.is_some()
        {
            windows = select_eval_windows(
                &windows,
                constellation.normalization.holdout_eval_max_bytes,
                constellation.normalization.public_eval_seed,
                &fam.family_id,
                "robust_holdout",
                &constellation.constellation_id,
            );
        }
        if windows.is_empty() {
            continue;
        }
        let payloads = load_payload_index_for_windows(root, &windows)?;

        let cand = score_panel_with_resid_scales(
            &candidate.arch_program,
            &candidate.head_pack,
            Some(&candidate.state_pack.resid_weights),
            &payloads,
            &windows,
        )?;
        let inc = score_panel_with_resid_scales(
            &incumbent.arch_program,
            &incumbent.head_pack,
            Some(&incumbent.state_pack.resid_weights),
            &payloads,
            &windows,
        )?;

        let target_bytes = windows.iter().map(|w| w.len as u64).sum::<u64>().max(1);
        let cand_bpb = cand.total_bits / target_bytes as f64;
        let inc_bpb = inc.total_bits / target_bytes as f64;
        let delta = inc_bpb - cand_bpb;

        if fam.floors.protected && delta < -fam.floors.max_robust_regress_bpb {
            protected_floor_failures.push(fam.family_id.clone());
        }

        candidate_scores.insert(fam.family_id.clone(), cand_bpb);
        incumbent_scores.insert(fam.family_id.clone(), inc_bpb);

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
        match mode {
            EvalMode::Public => vec.robust_public_bpb = Some(cand_bpb),
            EvalMode::Holdout => vec.robust_holdout_bpb = Some(cand_bpb),
        }
        per_family.insert(fam.family_id.clone(), vec);

        traces.push(RobustnessFamilyTrace {
            candidate_hash: candidate.manifest.candidate_hash.clone(),
            incumbent_hash: incumbent.manifest.candidate_hash.clone(),
            snapshot_hash: candidate.manifest.snapshot_hash.clone(),
            constellation_id: constellation.constellation_id.clone(),
            protocol_version: constellation.protocol_version.clone(),
            family_id: fam.family_id.clone(),
            panel: panel_key,
            candidate_bpb: cand_bpb,
            incumbent_bpb: inc_bpb,
            delta_bpb: delta,
            replay_hash: digest_json(&(fam.family_id.clone(), cand_bpb, inc_bpb, panel_key))?,
        });
    }

    let (candidate_weighted_bpb, incumbent_weighted_bpb, family_deltas) =
        apply_robust_weighted_scores(constellation, &candidate_scores, &incumbent_scores);

    let mut receipt = ConstellationScoreReceipt {
        candidate_hash: candidate.manifest.candidate_hash.clone(),
        incumbent_hash: incumbent.manifest.candidate_hash.clone(),
        snapshot_hash: candidate.manifest.snapshot_hash.clone(),
        constellation_id: constellation.constellation_id.clone(),
        protocol_version: constellation.protocol_version.clone(),
        per_family,
        code_penalty_bpb: 0.0,
        weighted_static_public_bpb: None,
        weighted_static_holdout_bpb: None,
        weighted_transfer_public_bpb: None,
        weighted_transfer_holdout_bpb: None,
        weighted_robust_public_bpb: None,
        weighted_robust_holdout_bpb: None,
        improved_families: Vec::new(),
        nonprotected_improved_families: Vec::new(),
        regressed_families: family_deltas
            .iter()
            .filter_map(|(k, v)| if *v < 0.0 { Some(k.clone()) } else { None })
            .collect(),
        protected_floor_pass: protected_floor_failures.is_empty(),
        target_subset_pass: true,
        replay_hash: String::new(),
    };

    match mode {
        EvalMode::Public => receipt.weighted_robust_public_bpb = Some(candidate_weighted_bpb),
        EvalMode::Holdout => receipt.weighted_robust_holdout_bpb = Some(candidate_weighted_bpb),
    }
    receipt.replay_hash = digest_json(&(receipt.clone(), traces.clone()))?;

    Ok(RobustnessEvaluation {
        receipt,
        candidate_weighted_bpb,
        incumbent_weighted_bpb,
        delta_bpb: incumbent_weighted_bpb - candidate_weighted_bpb,
        protected_floor_failures,
        family_deltas,
        traces,
    })
}
