use std::collections::BTreeMap;

use crate::apfsc::bank::{window_bytes, window_target};
use crate::apfsc::candidate::{clone_with_mutation, CandidateBundle};
use crate::apfsc::config::Phase1Config;
use crate::apfsc::errors::{ApfscError, Result};
use crate::apfsc::scir::ast::{ScirNode, ScirOp, ScirProgram};
use crate::apfsc::scir::interp::run_program;
use crate::apfsc::types::{LinearHead, PromotionClass, WarmRefinementPack, WindowRef};

#[derive(Debug, Clone)]
pub struct IncubatorArtifact {
    pub sidecar_name: String,
    pub utility_bits: f64,
    pub sidecar_program: ScirProgram,
    pub shadow_head: LinearHead,
    pub sidecar_dim: u32,
}

pub fn generate(
    active: &CandidateBundle,
    cfg: &Phase1Config,
    train_windows: &[WindowRef],
    public_windows: &[WindowRef],
    payloads_by_seq_hash: &BTreeMap<String, Vec<u8>>,
) -> Result<Vec<IncubatorArtifact>> {
    let sidecars = [
        "sidecar_memory_macro",
        "periodicity_macro",
        "copy_detector_macro",
        "delimiter_segment_macro",
    ];

    let mut out = Vec::new();
    for name in sidecars
        .into_iter()
        .take(cfg.lanes.max_incubator_candidates)
    {
        let (program, sidecar_node, sidecar_dim) = attach_sidecar(&active.arch_program, name)?;
        let mut shadow = LinearHead::zeros(sidecar_dim, 256);

        train_shadow_head(
            &program,
            &mut shadow,
            sidecar_node,
            train_windows,
            payloads_by_seq_hash,
            cfg.incubator.shadow_steps,
            cfg.train.lr,
            cfg.train.eps,
            cfg.train.l2,
            cfg.train.clip_grad,
        )?;

        let witness_sample: Vec<WindowRef> = public_windows
            .iter()
            .take(cfg.witness.count.min(public_windows.len()))
            .cloned()
            .collect();

        let witness_bits = eval_shadow_bits(
            &program,
            &shadow,
            sidecar_node,
            &witness_sample,
            payloads_by_seq_hash,
        )?;
        let public_bits = eval_shadow_bits(
            &program,
            &shadow,
            sidecar_node,
            public_windows,
            payloads_by_seq_hash,
        )?;

        let witness_gain = witness_sample.len() as f64 * 8.0 - witness_bits;
        let public_gain = public_windows.len() as f64 * 8.0 - public_bits;
        let added_code_bits = (sidecar_dim as f64) * 256.0 * 32.0;
        let predicted_risk = 0.1;

        let utility = witness_gain + public_gain
            - cfg.incubator.lambda_code * added_code_bits.log2().max(0.0)
            - cfg.incubator.lambda_risk * predicted_risk;

        out.push(IncubatorArtifact {
            sidecar_name: name.to_string(),
            utility_bits: utility,
            sidecar_program: program,
            shadow_head: shadow,
            sidecar_dim,
        });
    }

    Ok(out)
}

pub fn materialize_splice_candidates(
    active: &CandidateBundle,
    artifacts: Vec<IncubatorArtifact>,
    cfg: &Phase1Config,
) -> Result<Vec<CandidateBundle>> {
    let mut out = Vec::new();
    for item in artifacts {
        if item.utility_bits <= cfg.incubator.incubator_min_utility_bits {
            continue;
        }

        let sidecar_node_id = item
            .sidecar_program
            .outputs
            .shadow_feature_nodes
            .last()
            .copied()
            .ok_or_else(|| ApfscError::Validation("missing sidecar shadow node".to_string()))?;
        let base_feature = item.sidecar_program.outputs.feature_node;
        let base_dim = item
            .sidecar_program
            .nodes
            .iter()
            .find(|n| n.id == base_feature)
            .map(|n| n.out_dim)
            .ok_or_else(|| ApfscError::Validation("missing feature node".to_string()))?;

        let mut splice_program = item.sidecar_program.clone();
        let join_id = splice_program
            .nodes
            .iter()
            .map(|n| n.id)
            .max()
            .unwrap_or(0)
            .saturating_add(1);
        splice_program.nodes.push(ScirNode {
            id: join_id,
            op: ScirOp::Concat,
            inputs: vec![base_feature, sidecar_node_id],
            out_dim: base_dim + item.sidecar_dim,
            mutable: false,
        });
        splice_program.outputs.feature_node = join_id;

        let mut head_pack = active.head_pack.clone();
        extend_head_for_splice(&mut head_pack.native_head, item.sidecar_dim, None);
        extend_head_for_splice(&mut head_pack.nuisance_head, item.sidecar_dim, None);
        extend_head_for_splice(
            &mut head_pack.residual_head,
            item.sidecar_dim,
            Some((&item.shadow_head, 0.25)),
        );

        let mut state = active.state_pack.clone();
        state
            .resid_weights
            .extend(vec![0.0; item.sidecar_dim as usize]);

        let bridge = WarmRefinementPack {
            protected_families: vec!["F0".to_string(), "F1".to_string()],
            max_anchor_regress_bits: 0.0,
            max_public_regress_bits: 0.0,
            migration_policy: "local_splice_v1".to_string(),
        };

        let cand = clone_with_mutation(
            active,
            "incubator",
            &format!("splice_{}", item.sidecar_name),
            PromotionClass::A,
            splice_program,
            head_pack,
            state,
            active.schedule_pack.clone(),
            Some(bridge),
            BTreeMap::new(),
        )?;
        out.push(cand);
    }
    Ok(out)
}

fn attach_sidecar(program: &ScirProgram, macro_name: &str) -> Result<(ScirProgram, u32, u32)> {
    let mut p = program.clone();
    let next_id = p
        .nodes
        .iter()
        .map(|n| n.id)
        .max()
        .unwrap_or(0)
        .saturating_add(1);

    let (op, dim) = match macro_name {
        "sidecar_memory_macro" => (ScirOp::ShiftRegister { width: 8 }, 8),
        "periodicity_macro" => (ScirOp::ModCounter { modulus: 8 }, 8),
        "copy_detector_macro" => (ScirOp::RunLengthBucket { buckets: 8 }, 8),
        "delimiter_segment_macro" => (ScirOp::DelimiterReset { byte: b'\n' }, 1),
        _ => {
            return Err(ApfscError::Validation(format!(
                "unsupported incubator sidecar macro: {macro_name}"
            )));
        }
    };

    p.nodes.push(ScirNode {
        id: next_id,
        op,
        inputs: Vec::new(),
        out_dim: dim,
        mutable: false,
    });
    p.outputs.shadow_feature_nodes.push(next_id);
    Ok((p, next_id, dim))
}

#[allow(clippy::too_many_arguments)]
fn train_shadow_head(
    program: &ScirProgram,
    head: &mut LinearHead,
    sidecar_node: u32,
    windows: &[WindowRef],
    payloads_by_seq_hash: &BTreeMap<String, Vec<u8>>,
    steps: u32,
    lr: f32,
    eps: f32,
    l2: f32,
    clip_grad: f32,
) -> Result<()> {
    let in_dim = head.in_dim as usize;
    let out_dim = head.out_dim as usize;
    let mut g2_w = vec![0.0f32; head.weights.len()];
    let mut g2_b = vec![0.0f32; head.bias.len()];

    if windows.is_empty() {
        return Ok(());
    }

    for step in 0..steps as usize {
        let wref = &windows[step % windows.len()];
        let payload = payloads_by_seq_hash.get(&wref.seq_hash).ok_or_else(|| {
            ApfscError::Missing("missing payload for incubator training".to_string())
        })?;
        let input = window_bytes(payload, wref)?;
        let target = window_target(payload, wref)? as usize;

        let trace = run_program(program, input)?;
        let sidecar = find_sidecar_feature(program, sidecar_node, &trace)?;
        if sidecar.len() != in_dim {
            return Err(ApfscError::Validation(
                "sidecar feature dim/head dim mismatch".to_string(),
            ));
        }

        let mut logits = vec![0.0f32; out_dim];
        for o in 0..out_dim {
            let mut acc = head.bias[o];
            for i in 0..in_dim {
                acc += head.weights[o * in_dim + i] * sidecar[i];
            }
            logits[o] = acc;
        }

        let probs = softmax(&logits);
        for o in 0..out_dim {
            let mut grad = probs[o] - if o == target { 1.0 } else { 0.0 };
            if grad > clip_grad {
                grad = clip_grad;
            }
            if grad < -clip_grad {
                grad = -clip_grad;
            }

            for i in 0..in_dim {
                let idx = o * in_dim + i;
                let mut g = grad * sidecar[i] + l2 * head.weights[idx];
                if g > clip_grad {
                    g = clip_grad;
                }
                if g < -clip_grad {
                    g = -clip_grad;
                }
                g2_w[idx] += g * g;
                head.weights[idx] -= lr * g / (g2_w[idx].sqrt() + eps);
            }
            g2_b[o] += grad * grad;
            head.bias[o] -= lr * grad / (g2_b[o].sqrt() + eps);
        }
    }

    Ok(())
}

fn eval_shadow_bits(
    program: &ScirProgram,
    head: &LinearHead,
    sidecar_node: u32,
    windows: &[WindowRef],
    payloads_by_seq_hash: &BTreeMap<String, Vec<u8>>,
) -> Result<f64> {
    let mut total = 0.0f64;
    let in_dim = head.in_dim as usize;

    for wref in windows {
        let payload = payloads_by_seq_hash
            .get(&wref.seq_hash)
            .ok_or_else(|| ApfscError::Missing("missing payload for incubator eval".to_string()))?;
        let input = window_bytes(payload, wref)?;
        let target = window_target(payload, wref)? as usize;
        let trace = run_program(program, input)?;
        let sidecar = find_sidecar_feature(program, sidecar_node, &trace)?;
        if sidecar.len() != in_dim {
            return Err(ApfscError::Validation(
                "sidecar feature dim/head dim mismatch".to_string(),
            ));
        }

        let logits = linear_logits(head, sidecar);
        let probs = softmax(&logits);
        let p = probs[target].max(1e-9) as f64;
        total += -p.log2();
    }
    Ok(total)
}

fn linear_logits(head: &LinearHead, x: &[f32]) -> Vec<f32> {
    let in_dim = head.in_dim as usize;
    let out_dim = head.out_dim as usize;
    let mut out = vec![0.0f32; out_dim];
    for o in 0..out_dim {
        let mut acc = head.bias[o];
        for i in 0..in_dim {
            acc += head.weights[o * in_dim + i] * x[i];
        }
        out[o] = acc;
    }
    out
}

fn softmax(logits: &[f32]) -> Vec<f32> {
    let m = logits
        .iter()
        .copied()
        .fold(f32::NEG_INFINITY, |a, b| a.max(b));
    let mut exps = vec![0.0f32; logits.len()];
    let mut sum = 0.0f32;
    for (i, l) in logits.iter().copied().enumerate() {
        let e = (l - m).exp();
        exps[i] = e;
        sum += e;
    }
    if sum <= 0.0 {
        return vec![1.0 / logits.len() as f32; logits.len()];
    }
    exps.into_iter().map(|e| e / sum).collect()
}

fn find_sidecar_feature<'a>(
    program: &'a ScirProgram,
    sidecar_node: u32,
    trace: &'a crate::apfsc::scir::ast::InterpTrace,
) -> Result<&'a [f32]> {
    let idx = program
        .outputs
        .shadow_feature_nodes
        .iter()
        .position(|id| *id == sidecar_node)
        .ok_or_else(|| {
            ApfscError::Validation("sidecar node missing from shadow outputs".to_string())
        })?;
    trace
        .shadows
        .get(idx)
        .map(|v| v.as_slice())
        .ok_or_else(|| ApfscError::Validation("sidecar feature trace missing".to_string()))
}

fn extend_head_for_splice(
    head: &mut LinearHead,
    extra_dim: u32,
    from_shadow: Option<(&LinearHead, f32)>,
) {
    let old_in = head.in_dim as usize;
    let new_in = old_in + extra_dim as usize;
    let out = head.out_dim as usize;

    let mut new_weights = vec![0.0f32; out * new_in];
    for o in 0..out {
        let old_row = &head.weights[o * old_in..(o + 1) * old_in];
        let new_row = &mut new_weights[o * new_in..o * new_in + old_in];
        new_row.copy_from_slice(old_row);
    }

    if let Some((shadow, scale)) = from_shadow {
        let sh_in = shadow.in_dim as usize;
        for o in 0..out {
            for i in 0..extra_dim as usize {
                let sh_i = i.min(sh_in.saturating_sub(1));
                let sh_idx = o * sh_in + sh_i;
                let dst_idx = o * new_in + old_in + i;
                new_weights[dst_idx] = shadow.weights[sh_idx] * scale;
            }
        }
    }

    head.in_dim = new_in as u32;
    head.weights = new_weights;
}
