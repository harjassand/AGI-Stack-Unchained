use std::collections::BTreeMap;
use std::path::Path;

use crate::apfsc::artifacts::digest_json;
use crate::apfsc::bank::{
    load_family_panel_windows, load_payload_index_for_windows, window_bytes, window_target,
};
use crate::apfsc::candidate::CandidateBundle;
use crate::apfsc::errors::{ApfscError, Result};
use crate::apfsc::headpack::apply_linear;
use crate::apfsc::normalization::apply_transfer_weighted_scores;
use crate::apfsc::scir::interp::run_program;
use crate::apfsc::types::{
    ConstellationManifest, ConstellationScoreReceipt, EvalMode, FamilyEvalVector, FamilyId,
    TransferAdaptSpec, TransferFamilyTrace,
};

#[derive(Debug, Clone)]
struct AdaptedFamilyModel {
    bundle: CandidateBundle,
    fast_weights: Vec<f32>,
    delta_bits: u64,
}

#[derive(Debug, Clone)]
pub struct TransferEvaluation {
    pub receipt: ConstellationScoreReceipt,
    pub candidate_weighted_bpb: f64,
    pub incumbent_weighted_bpb: f64,
    pub delta_bpb: f64,
    pub protected_floor_failures: Vec<FamilyId>,
    pub family_deltas: BTreeMap<FamilyId, f64>,
    pub traces: Vec<TransferFamilyTrace>,
}

pub fn evaluate_transfer(
    root: &Path,
    candidate: &CandidateBundle,
    incumbent: &CandidateBundle,
    constellation: &ConstellationManifest,
    mode: EvalMode,
) -> Result<TransferEvaluation> {
    let mut per_family = BTreeMap::<FamilyId, FamilyEvalVector>::new();
    let mut candidate_scores = BTreeMap::<FamilyId, f64>::new();
    let mut incumbent_scores = BTreeMap::<FamilyId, f64>::new();
    let mut protected_floor_failures = Vec::<FamilyId>::new();
    let mut traces = Vec::new();

    for fam in &constellation.family_specs {
        let train = load_family_panel_windows(root, &fam.family_id, "transfer_train")?;
        let eval = load_family_panel_windows(root, &fam.family_id, "transfer_eval")?;
        if train.is_empty() || eval.is_empty() {
            continue;
        }

        let mut all = train.clone();
        all.extend(eval.iter().cloned());
        let payloads = load_payload_index_for_windows(root, &all)?;

        let adapted_candidate = adapt_model(candidate, &fam.transfer_adapt, &train, &payloads)?;
        let adapted_incumbent = adapt_model(incumbent, &fam.transfer_adapt, &train, &payloads)?;

        let cand_panel_bits = score_eval_bits(&adapted_candidate, &eval, &payloads)?;
        let inc_panel_bits = score_eval_bits(&adapted_incumbent, &eval, &payloads)?;
        let target_bytes = eval.iter().map(|w| w.len as u64).sum::<u64>().max(1);

        let cand_panel_bpb = cand_panel_bits / target_bytes as f64;
        let inc_panel_bpb = inc_panel_bits / target_bytes as f64;

        let cand_penalty_bpb = adapted_candidate.delta_bits as f64
            / constellation.normalization.transfer_ref_bytes as f64;
        let inc_penalty_bpb = adapted_incumbent.delta_bits as f64
            / constellation.normalization.transfer_ref_bytes as f64;

        let cand_score = cand_panel_bpb + cand_penalty_bpb;
        let inc_score = inc_panel_bpb + inc_penalty_bpb;
        let delta = inc_score - cand_score;

        if fam.floors.protected && delta < -fam.floors.max_transfer_regress_bpb {
            protected_floor_failures.push(fam.family_id.clone());
        }

        candidate_scores.insert(fam.family_id.clone(), cand_score);
        incumbent_scores.insert(fam.family_id.clone(), inc_score);

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
            EvalMode::Public => vec.transfer_public_bpb = Some(cand_score),
            EvalMode::Holdout => vec.transfer_holdout_bpb = Some(cand_score),
        }
        per_family.insert(fam.family_id.clone(), vec);

        traces.push(TransferFamilyTrace {
            candidate_hash: candidate.manifest.candidate_hash.clone(),
            incumbent_hash: incumbent.manifest.candidate_hash.clone(),
            snapshot_hash: candidate.manifest.snapshot_hash.clone(),
            constellation_id: constellation.constellation_id.clone(),
            protocol_version: constellation.protocol_version.clone(),
            family_id: fam.family_id.clone(),
            mode,
            candidate_panel_bpb: cand_panel_bpb,
            incumbent_panel_bpb: inc_panel_bpb,
            candidate_penalty_bpb: cand_penalty_bpb,
            incumbent_penalty_bpb: inc_penalty_bpb,
            delta_bpb: delta,
            delta_bits: adapted_candidate.delta_bits,
            replay_hash: digest_json(&(
                fam.family_id.clone(),
                cand_score,
                inc_score,
                adapted_candidate.delta_bits,
            ))?,
        });
    }

    let (candidate_weighted_bpb, incumbent_weighted_bpb, family_deltas) =
        apply_transfer_weighted_scores(constellation, &candidate_scores, &incumbent_scores);

    protected_floor_failures.sort();

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
        EvalMode::Public => receipt.weighted_transfer_public_bpb = Some(candidate_weighted_bpb),
        EvalMode::Holdout => receipt.weighted_transfer_holdout_bpb = Some(candidate_weighted_bpb),
    }

    receipt.replay_hash = digest_json(&(receipt.clone(), traces.clone()))?;

    Ok(TransferEvaluation {
        receipt,
        candidate_weighted_bpb,
        incumbent_weighted_bpb,
        delta_bpb: incumbent_weighted_bpb - candidate_weighted_bpb,
        protected_floor_failures,
        family_deltas,
        traces,
    })
}

pub fn debug_adapt_candidate_for_family(
    root: &Path,
    candidate: &CandidateBundle,
    family_id: &str,
    constellation: &ConstellationManifest,
) -> Result<(CandidateBundle, u64)> {
    let fam = constellation
        .family_specs
        .iter()
        .find(|f| f.family_id == family_id)
        .ok_or_else(|| ApfscError::Missing(format!("unknown family {family_id}")))?;
    let train = load_family_panel_windows(root, &fam.family_id, "transfer_train")?;
    let payloads = load_payload_index_for_windows(root, &train)?;
    let adapted = adapt_model(candidate, &fam.transfer_adapt, &train, &payloads)?;
    Ok((adapted.bundle, adapted.delta_bits))
}

fn score_eval_bits(
    model: &AdaptedFamilyModel,
    eval: &[crate::apfsc::types::WindowRef],
    payloads: &BTreeMap<String, Vec<u8>>,
) -> Result<f64> {
    let in_dim = model.bundle.head_pack.native_head.in_dim as usize;
    let out_dim = model.bundle.head_pack.native_head.out_dim as usize;
    let mut total = 0.0f64;
    for w in eval {
        let payload = payloads
            .get(&w.seq_hash)
            .ok_or_else(|| ApfscError::Missing(format!("missing payload {}", w.seq_hash)))?;
        let input = window_bytes(payload, w)?;
        let target = window_target(payload, w)? as usize;
        let trace = run_program(&model.bundle.arch_program, input)?;

        let mut feature = adapt_feature_dim(&trace.feature, in_dim);
        for (i, x) in feature.iter_mut().enumerate() {
            if i < model.bundle.state_pack.resid_weights.len() {
                *x *= 1.0 + model.bundle.state_pack.resid_weights[i];
            }
            if i < model.fast_weights.len() {
                *x += model.fast_weights[i];
            }
        }

        let native_logits = apply_linear(&model.bundle.head_pack.native_head, &feature);
        let nuisance_logits = apply_linear(&model.bundle.head_pack.nuisance_head, &feature);
        let residual_logits = apply_linear(&model.bundle.head_pack.residual_head, &feature);

        let mut mass = vec![0.0f32; out_dim];
        let mut sum = 0.0f32;
        for o in 0..out_dim {
            let m = softplus(native_logits[o])
                + softplus(nuisance_logits[o])
                + softplus(residual_logits[o])
                + 1e-4;
            mass[o] = m;
            sum += m;
        }
        if sum <= 0.0 {
            continue;
        }
        let p = (mass[target] / sum).max(1e-9) as f64;
        total += -p.log2();
    }
    Ok(total)
}

fn adapt_model(
    base: &CandidateBundle,
    spec: &TransferAdaptSpec,
    train_windows: &[crate::apfsc::types::WindowRef],
    payloads: &BTreeMap<String, Vec<u8>>,
) -> Result<AdaptedFamilyModel> {
    let mut adapted = base.clone();

    let legal = [
        "nuisance_head",
        "residual_head",
        "resid_weights",
        "fast_weights",
    ];
    for s in &spec.mutable_surfaces {
        if !legal.contains(&s.as_str()) {
            return Err(ApfscError::Validation(format!(
                "illegal transfer mutable surface: {s}"
            )));
        }
    }
    let allow_nuisance_head = spec.mutable_surfaces.iter().any(|s| s == "nuisance_head");
    let allow_residual_head = spec.mutable_surfaces.iter().any(|s| s == "residual_head");
    let allow_resid_weights = spec.mutable_surfaces.iter().any(|s| s == "resid_weights");
    let allow_fast_weights = spec.mutable_surfaces.iter().any(|s| s == "fast_weights");

    if spec.reset_ephemeral_state {
        for x in &mut adapted.state_pack.init_state {
            *x = 0.0;
        }
    }

    let in_dim = adapted.head_pack.native_head.in_dim as usize;
    if adapted.state_pack.resid_weights.len() < in_dim {
        adapted.state_pack.resid_weights.resize(in_dim, 0.0);
    }
    let fast_slots = (spec.max_fast_weight_bytes / 4) as usize;
    let mut fast_weights = if allow_fast_weights {
        vec![0.0f32; fast_slots.min(in_dim)]
    } else {
        Vec::new()
    };

    let out_dim = adapted.head_pack.native_head.out_dim as usize;
    let mut ng2_w = vec![0.0f32; adapted.head_pack.nuisance_head.weights.len()];
    let mut ng2_b = vec![0.0f32; adapted.head_pack.nuisance_head.bias.len()];
    let mut rg2_w = vec![0.0f32; adapted.head_pack.residual_head.weights.len()];
    let mut rg2_b = vec![0.0f32; adapted.head_pack.residual_head.bias.len()];
    let mut sg2 = vec![0.0f32; in_dim];
    let mut fg2 = vec![0.0f32; fast_weights.len()];

    if !train_windows.is_empty() {
        let steps = spec.steps as usize;
        let batch_windows = spec.batch_windows.max(1) as usize;
        for step in 0..steps {
            for b in 0..batch_windows {
                let idx = (step * batch_windows + b) % train_windows.len();
                let w = &train_windows[idx];
                let payload = payloads.get(&w.seq_hash).ok_or_else(|| {
                    ApfscError::Missing(format!("missing payload {}", w.seq_hash))
                })?;
                let input = window_bytes(payload, w)?;
                let target = window_target(payload, w)? as usize;
                let trace = run_program(&adapted.arch_program, input)?;
                let base_feature = adapt_feature_dim(&trace.feature, in_dim);

                let mut feature = base_feature.clone();
                for (i, x) in feature.iter_mut().enumerate() {
                    *x *= 1.0 + adapted.state_pack.resid_weights[i];
                    if i < fast_weights.len() {
                        *x += fast_weights[i];
                    }
                }

                let native_logits = apply_linear(&adapted.head_pack.native_head, &feature);
                let nuisance_logits = apply_linear(&adapted.head_pack.nuisance_head, &feature);
                let residual_logits = apply_linear(&adapted.head_pack.residual_head, &feature);

                let mut mass = vec![0.0f32; out_dim];
                let mut total_mass = 0.0f32;
                for o in 0..out_dim {
                    let m = softplus(native_logits[o])
                        + softplus(nuisance_logits[o])
                        + softplus(residual_logits[o])
                        + 1e-4;
                    mass[o] = m;
                    total_mass += m;
                }
                if total_mass <= 0.0 || !total_mass.is_finite() {
                    continue;
                }

                let mut g_nuisance = vec![0.0f32; out_dim];
                let mut g_residual = vec![0.0f32; out_dim];
                for o in 0..out_dim {
                    let p = mass[o] / total_mass;
                    let y = if o == target { 1.0 } else { 0.0 };
                    let g_mass = p - y;
                    g_nuisance[o] = clip(g_mass * sigmoid(nuisance_logits[o]), spec.clip_grad);
                    g_residual[o] = clip(g_mass * sigmoid(residual_logits[o]), spec.clip_grad);
                }

                if allow_nuisance_head {
                    update_head(
                        &mut adapted.head_pack.nuisance_head,
                        &feature,
                        &g_nuisance,
                        spec,
                        &mut ng2_w,
                        &mut ng2_b,
                    );
                }
                if allow_residual_head {
                    update_head(
                        &mut adapted.head_pack.residual_head,
                        &feature,
                        &g_residual,
                        spec,
                        &mut rg2_w,
                        &mut rg2_b,
                    );
                }

                if allow_resid_weights {
                    update_scales(
                        &mut adapted.state_pack.resid_weights,
                        &base_feature,
                        &adapted.head_pack.residual_head,
                        &g_residual,
                        spec,
                        &mut sg2,
                    );
                }

                if allow_fast_weights {
                    for i in 0..fast_weights.len() {
                        let mut g = 0.0f32;
                        for (o, go) in g_residual.iter().copied().enumerate().take(out_dim) {
                            let w = adapted.head_pack.residual_head.weights[o * in_dim + i];
                            g += go * w;
                        }
                        g = clip(g, spec.clip_grad);
                        fg2[i] += g * g;
                        fast_weights[i] -= spec.lr * g / (fg2[i].sqrt() + spec.eps);
                    }
                }
            }
        }
    }

    let delta_bits = estimate_delta_bits(base, &adapted, &fast_weights);

    if delta_bits > spec.max_delta_bits {
        return Err(ApfscError::Validation(
            crate::apfsc::types::JudgeRejectReason::TransferDeltaBudgetExceeded.as_reason(),
        ));
    }
    if (fast_weights.len() as u64) * 4 > spec.max_fast_weight_bytes {
        return Err(ApfscError::Validation(
            crate::apfsc::types::JudgeRejectReason::TransferDeltaBudgetExceeded.as_reason(),
        ));
    }

    Ok(AdaptedFamilyModel {
        bundle: adapted,
        fast_weights,
        delta_bits,
    })
}

fn estimate_delta_bits(
    base: &CandidateBundle,
    adapted: &CandidateBundle,
    fast_weights: &[f32],
) -> u64 {
    let mut changed = 0u64;
    changed += changed_count(
        &base.head_pack.nuisance_head.weights,
        &adapted.head_pack.nuisance_head.weights,
    );
    changed += changed_count(
        &base.head_pack.nuisance_head.bias,
        &adapted.head_pack.nuisance_head.bias,
    );
    changed += changed_count(
        &base.head_pack.residual_head.weights,
        &adapted.head_pack.residual_head.weights,
    );
    changed += changed_count(
        &base.head_pack.residual_head.bias,
        &adapted.head_pack.residual_head.bias,
    );
    changed += changed_count(
        &base.state_pack.resid_weights,
        &adapted.state_pack.resid_weights,
    );
    changed += fast_weights.iter().filter(|v| v.abs() > 1e-9).count() as u64;

    // Deterministic fixed-width delta-state charge: 4 bits/value + constant header.
    changed.saturating_mul(4).saturating_add(128)
}

fn changed_count(a: &[f32], b: &[f32]) -> u64 {
    let n = a.len().max(b.len());
    let mut out = 0u64;
    for i in 0..n {
        let av = *a.get(i).unwrap_or(&0.0);
        let bv = *b.get(i).unwrap_or(&0.0);
        if (bv - av).abs() > 1e-9 {
            out += 1;
        }
    }
    out
}

fn update_head(
    head: &mut crate::apfsc::types::LinearHead,
    feature: &[f32],
    grad_out: &[f32],
    spec: &TransferAdaptSpec,
    g2_w: &mut [f32],
    g2_b: &mut [f32],
) {
    let in_dim = head.in_dim as usize;
    let out_dim = head.out_dim as usize;
    for o in 0..out_dim {
        let gb = clip(grad_out[o], spec.clip_grad);
        g2_b[o] += gb * gb;
        head.bias[o] -= spec.lr * gb / (g2_b[o].sqrt() + spec.eps);
        for i in 0..in_dim {
            let idx = o * in_dim + i;
            let mut gw = gb * feature[i] + spec.l2 * head.weights[idx];
            gw = clip(gw, spec.clip_grad);
            g2_w[idx] += gw * gw;
            head.weights[idx] -= spec.lr * gw / (g2_w[idx].sqrt() + spec.eps);
        }
    }
}

fn update_scales(
    scales: &mut [f32],
    base_feature: &[f32],
    residual_head: &crate::apfsc::types::LinearHead,
    grad_residual_out: &[f32],
    spec: &TransferAdaptSpec,
    g2: &mut [f32],
) {
    let in_dim = residual_head.in_dim as usize;
    let out_dim = residual_head.out_dim as usize;
    for i in 0..in_dim {
        let mut g = 0.0f32;
        for (o, go) in grad_residual_out.iter().copied().enumerate().take(out_dim) {
            let w = residual_head.weights[o * in_dim + i];
            g += go * w * base_feature[i];
        }
        g += spec.l2 * scales[i];
        g = clip(g, spec.clip_grad);
        g2[i] += g * g;
        scales[i] -= spec.lr * g / (g2[i].sqrt() + spec.eps);
    }
}

fn adapt_feature_dim(feature: &[f32], target_dim: usize) -> Vec<f32> {
    if feature.len() == target_dim {
        return feature.to_vec();
    }
    if feature.len() > target_dim {
        return feature[..target_dim].to_vec();
    }
    let mut out = feature.to_vec();
    out.resize(target_dim, 0.0);
    out
}

fn softplus(x: f32) -> f32 {
    if x > 20.0 {
        x
    } else {
        (1.0 + x.exp()).ln()
    }
}

fn sigmoid(x: f32) -> f32 {
    1.0 / (1.0 + (-x).exp())
}

fn clip(x: f32, lim: f32) -> f32 {
    if x > lim {
        lim
    } else if x < -lim {
        -lim
    } else {
        x
    }
}
