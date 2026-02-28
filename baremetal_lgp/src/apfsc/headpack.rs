use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};

use crate::apfsc::bank::{window_bytes, window_target};
use crate::apfsc::config::TrainConfig;
use crate::apfsc::errors::{ApfscError, Result};
use crate::apfsc::scir::ast::ScirProgram;
use crate::apfsc::scir::interp::run_program;
use crate::apfsc::types::{HeadPack, LinearHead, StatePack, WindowRef};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct HeadOnlyAdaGradLaw {
    pub steps: u32,
    pub lr: f32,
    pub eps: f32,
    pub l2: f32,
    pub clip_grad: f32,
    pub batch_windows: usize,
    pub shuffle: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct HeadOnlyAdaGradStats {
    pub applied_steps: u32,
    pub seen_windows: usize,
}

impl LinearHead {
    pub fn zeros(in_dim: u32, out_dim: u32) -> Self {
        Self {
            in_dim,
            out_dim,
            weights: vec![0.0; (in_dim * out_dim) as usize],
            bias: vec![0.0; out_dim as usize],
        }
    }

    pub fn deterministic(in_dim: u32, out_dim: u32, seed: u64) -> Self {
        let mut w = vec![0.0; (in_dim * out_dim) as usize];
        for o in 0..out_dim as usize {
            for i in 0..in_dim as usize {
                let idx = o * in_dim as usize + i;
                let h = seed
                    .wrapping_mul(6364136223846793005)
                    .wrapping_add((idx as u64) << 1)
                    .wrapping_add(17);
                let frac = (h % 10_000) as f32 / 10_000.0;
                w[idx] = (frac - 0.5) * 0.05;
            }
        }
        let mut b = vec![0.0; out_dim as usize];
        for (i, bi) in b.iter_mut().enumerate() {
            let h = seed.wrapping_add(i as u64 * 1315423911);
            let frac = (h % 10_000) as f32 / 10_000.0;
            *bi = (frac - 0.5) * 0.01;
        }
        Self {
            in_dim,
            out_dim,
            weights: w,
            bias: b,
        }
    }
}

impl HeadPack {
    pub fn deterministic(feature_dim: u32, shadow_heads: usize) -> Self {
        let native_head = LinearHead::deterministic(feature_dim, 256, 11);
        let nuisance_head = LinearHead::deterministic(feature_dim, 256, 29);
        let residual_head = LinearHead::zeros(feature_dim, 256);
        let mut shadows = Vec::with_capacity(shadow_heads);
        for i in 0..shadow_heads {
            shadows.push(LinearHead::deterministic(feature_dim, 256, 1000 + i as u64));
        }
        Self {
            native_head,
            nuisance_head,
            residual_head,
            shadow_heads: shadows,
        }
    }
}

pub fn apply_linear(head: &LinearHead, x: &[f32]) -> Vec<f32> {
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

pub fn head_param_bits(head: &LinearHead) -> u64 {
    ((head.weights.len() + head.bias.len()) as u64) * 32
}

impl HeadOnlyAdaGradLaw {
    pub fn from_train_config(cfg: &TrainConfig) -> Self {
        Self {
            steps: cfg.steps,
            lr: cfg.lr,
            eps: cfg.eps,
            l2: cfg.l2,
            clip_grad: cfg.clip_grad,
            batch_windows: cfg.batch_windows.max(1),
            shuffle: cfg.shuffle,
        }
    }

    pub fn train(
        &self,
        program: &ScirProgram,
        state: &mut StatePack,
        heads: &mut HeadPack,
        windows: &[WindowRef],
        payloads_by_seq_hash: &BTreeMap<String, Vec<u8>>,
    ) -> Result<HeadOnlyAdaGradStats> {
        if windows.is_empty() || self.steps == 0 {
            return Ok(HeadOnlyAdaGradStats {
                applied_steps: 0,
                seen_windows: 0,
            });
        }

        let in_dim = heads.native_head.in_dim as usize;
        if heads.nuisance_head.in_dim as usize != in_dim
            || heads.residual_head.in_dim as usize != in_dim
        {
            return Err(ApfscError::Validation(
                "head in_dim mismatch for HeadOnlyAdaGradLaw".to_string(),
            ));
        }

        if state.resid_weights.len() < in_dim {
            state.resid_weights.resize(in_dim, 0.0);
        }

        let mut ng2_w = vec![0.0f32; heads.native_head.weights.len()];
        let mut ng2_b = vec![0.0f32; heads.native_head.bias.len()];
        let mut ug2_w = vec![0.0f32; heads.nuisance_head.weights.len()];
        let mut ug2_b = vec![0.0f32; heads.nuisance_head.bias.len()];
        let mut rg2_w = vec![0.0f32; heads.residual_head.weights.len()];
        let mut rg2_b = vec![0.0f32; heads.residual_head.bias.len()];
        let mut sg2 = vec![0.0f32; in_dim];

        let out_dim = heads.native_head.out_dim as usize;
        let mut seen = 0usize;

        for step in 0..self.steps as usize {
            for b in 0..self.batch_windows {
                let idx = (step * self.batch_windows + b) % windows.len();
                let wref = &windows[idx];
                let payload = payloads_by_seq_hash.get(&wref.seq_hash).ok_or_else(|| {
                    ApfscError::Missing(format!("missing payload seq_hash {}", wref.seq_hash))
                })?;
                let input = window_bytes(payload, wref)?;
                let target = window_target(payload, wref)? as usize;

                let trace = run_program(program, input)?;
                let base_feature = adapt_feature_dim(&trace.feature, in_dim);
                let mut feature_scaled = base_feature.clone();
                for (i, x) in feature_scaled.iter_mut().enumerate() {
                    *x *= 1.0 + state.resid_weights[i];
                }

                let native_logits = apply_linear(&heads.native_head, &base_feature);
                let nuisance_logits = apply_linear(&heads.nuisance_head, &base_feature);
                let residual_logits = apply_linear(&heads.residual_head, &feature_scaled);

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

                let mut g_native = vec![0.0f32; out_dim];
                let mut g_nuisance = vec![0.0f32; out_dim];
                let mut g_residual = vec![0.0f32; out_dim];
                for o in 0..out_dim {
                    let p = mass[o] / total_mass;
                    let y = if o == target { 1.0 } else { 0.0 };
                    let g_mass = p - y;
                    g_native[o] = clip(g_mass * sigmoid(native_logits[o]), self.clip_grad);
                    g_nuisance[o] = clip(g_mass * sigmoid(nuisance_logits[o]), self.clip_grad);
                    g_residual[o] = clip(g_mass * sigmoid(residual_logits[o]), self.clip_grad);
                }

                update_head(
                    &mut heads.native_head,
                    &base_feature,
                    &g_native,
                    self.lr,
                    self.eps,
                    self.l2,
                    self.clip_grad,
                    &mut ng2_w,
                    &mut ng2_b,
                );
                update_head(
                    &mut heads.nuisance_head,
                    &base_feature,
                    &g_nuisance,
                    self.lr,
                    self.eps,
                    self.l2,
                    self.clip_grad,
                    &mut ug2_w,
                    &mut ug2_b,
                );
                update_head(
                    &mut heads.residual_head,
                    &feature_scaled,
                    &g_residual,
                    self.lr,
                    self.eps,
                    self.l2,
                    self.clip_grad,
                    &mut rg2_w,
                    &mut rg2_b,
                );

                update_resid_scales(
                    &mut state.resid_weights,
                    &base_feature,
                    &heads.residual_head,
                    &g_residual,
                    self.lr,
                    self.eps,
                    self.l2,
                    self.clip_grad,
                    &mut sg2,
                );

                seen += 1;
            }
        }

        Ok(HeadOnlyAdaGradStats {
            applied_steps: self.steps,
            seen_windows: seen,
        })
    }
}

fn update_head(
    head: &mut LinearHead,
    feature: &[f32],
    grad_out: &[f32],
    lr: f32,
    eps: f32,
    l2: f32,
    clip_grad: f32,
    g2_w: &mut [f32],
    g2_b: &mut [f32],
) {
    let in_dim = head.in_dim as usize;
    let out_dim = head.out_dim as usize;

    for o in 0..out_dim {
        let gb = clip(grad_out[o], clip_grad);
        g2_b[o] += gb * gb;
        head.bias[o] -= lr * gb / (g2_b[o].sqrt() + eps);

        for i in 0..in_dim {
            let idx = o * in_dim + i;
            let mut gw = gb * feature[i] + l2 * head.weights[idx];
            gw = clip(gw, clip_grad);
            g2_w[idx] += gw * gw;
            head.weights[idx] -= lr * gw / (g2_w[idx].sqrt() + eps);
        }
    }
}

#[allow(clippy::too_many_arguments)]
fn update_resid_scales(
    scales: &mut [f32],
    base_feature: &[f32],
    residual_head: &LinearHead,
    grad_residual_out: &[f32],
    lr: f32,
    eps: f32,
    l2: f32,
    clip_grad: f32,
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
        g += l2 * scales[i];
        g = clip(g, clip_grad);
        g2[i] += g * g;
        scales[i] -= lr * g / (g2[i].sqrt() + eps);
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
