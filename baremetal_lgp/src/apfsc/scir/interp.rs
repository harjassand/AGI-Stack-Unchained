use std::collections::BTreeMap;

use crate::apfsc::errors::{ApfscError, Result};
use crate::apfsc::scir::ast::{InterpTrace, ScirOp, ScirProgram};

pub const BACKEND_FINGERPRINT: &str = "apfsc-tier0-cpu-v1";

pub fn run_program(program: &ScirProgram, window: &[u8]) -> Result<InterpTrace> {
    if window.is_empty() {
        return Err(ApfscError::Validation("window cannot be empty".to_string()));
    }
    let mut values: BTreeMap<u32, Vec<f32>> = BTreeMap::new();

    for node in &program.nodes {
        let out = eval_node(node, &values, window)?;
        if out.len() != node.out_dim as usize {
            return Err(ApfscError::Validation(format!(
                "node {} produced dim {} expected {}",
                node.id,
                out.len(),
                node.out_dim
            )));
        }
        values.insert(node.id, out);
    }

    let feature = values
        .get(&program.outputs.feature_node)
        .cloned()
        .ok_or_else(|| ApfscError::Validation("missing feature output".to_string()))?;

    let mut shadows = Vec::with_capacity(program.outputs.shadow_feature_nodes.len());
    for sid in &program.outputs.shadow_feature_nodes {
        shadows.push(
            values.get(sid).cloned().ok_or_else(|| {
                ApfscError::Validation("missing shadow feature output".to_string())
            })?,
        );
    }

    let mut probes = Vec::with_capacity(program.outputs.probe_nodes.len());
    for pid in &program.outputs.probe_nodes {
        probes.push(
            values
                .get(pid)
                .cloned()
                .ok_or_else(|| ApfscError::Validation("missing probe output".to_string()))?,
        );
    }

    Ok(InterpTrace {
        feature,
        shadows,
        probes,
    })
}

fn eval_node(
    node: &crate::apfsc::scir::ast::ScirNode,
    values: &BTreeMap<u32, Vec<f32>>,
    window: &[u8],
) -> Result<Vec<f32>> {
    let v = match &node.op {
        ScirOp::ByteEmbedding { dim, .. } => byte_embedding(*dim, window),
        ScirOp::LagBytes { lags } => lag_bytes(lags, window),
        ScirOp::Linear {
            in_dim,
            out_dim,
            bias,
        } => {
            let input = get_input(values, node, 0)?;
            if !node.mutable && !bias && *in_dim == *out_dim && *out_dim as usize == input.len() {
                input.to_vec()
            } else {
                linear(node.id, input, *out_dim as usize)
            }
        }
        ScirOp::Add => {
            let a = get_input(values, node, 0)?;
            let b = get_input(values, node, 1)?;
            elementwise2(a, b, |x, y| x + y)
        }
        ScirOp::Mul => {
            let a = get_input(values, node, 0)?;
            let b = get_input(values, node, 1)?;
            elementwise2(a, b, |x, y| x * y)
        }
        ScirOp::Tanh => {
            let a = get_input(values, node, 0)?;
            a.iter().map(|x| x.tanh()).collect()
        }
        ScirOp::Sigmoid => {
            let a = get_input(values, node, 0)?;
            a.iter().map(|x| 1.0 / (1.0 + (-x).exp())).collect()
        }
        ScirOp::Relu => {
            let a = get_input(values, node, 0)?;
            a.iter().map(|x| x.max(0.0)).collect()
        }
        ScirOp::Concat => {
            let mut out = Vec::new();
            for input_id in &node.inputs {
                out.extend(
                    values
                        .get(input_id)
                        .ok_or_else(|| ApfscError::Validation("concat input missing".to_string()))?
                        .iter()
                        .copied(),
                );
            }
            out
        }
        ScirOp::ReduceMean => {
            let a = get_input(values, node, 0)?;
            let s: f32 = a.iter().sum();
            vec![s / (a.len() as f32)]
        }
        ScirOp::ReduceSum => {
            let a = get_input(values, node, 0)?;
            let s: f32 = a.iter().sum();
            vec![s]
        }
        ScirOp::ShiftRegister { width } => {
            let mut out = vec![0.0f32; *width as usize];
            let take = (*width as usize).min(window.len());
            for i in 0..take {
                out[i] = window[window.len() - 1 - i] as f32 / 255.0;
            }
            out
        }
        ScirOp::RunLengthBucket { buckets } => run_length_bucket(*buckets, window),
        ScirOp::ModCounter { modulus } => {
            let mut out = vec![0.0f32; *modulus as usize];
            let idx = window.len() % *modulus as usize;
            out[idx] = 1.0;
            out
        }
        ScirOp::RollingHash { n, buckets } => rolling_hash(*n as usize, *buckets as usize, window),
        ScirOp::DelimiterReset { byte } => {
            let seen = window.iter().rev().take(8).any(|b| b == byte);
            vec![if seen { 1.0 } else { 0.0 }]
        }
        ScirOp::SimpleScan { hidden_dim, .. } => {
            let input = get_input(values, node, 0)?;
            simple_scan(node.id, input, *hidden_dim as usize)
        }
        ScirOp::ReadoutNative { .. } | ScirOp::ReadoutShadow { .. } => {
            get_input(values, node, 0)?.to_vec()
        }
    };
    Ok(v)
}

fn get_input<'a>(
    values: &'a BTreeMap<u32, Vec<f32>>,
    node: &crate::apfsc::scir::ast::ScirNode,
    ix: usize,
) -> Result<&'a [f32]> {
    let input_id = node
        .inputs
        .get(ix)
        .ok_or_else(|| ApfscError::Validation(format!("node {} missing input {}", node.id, ix)))?;
    Ok(values
        .get(input_id)
        .ok_or_else(|| ApfscError::Validation("input value missing".to_string()))?)
}

fn byte_embedding(dim: u32, window: &[u8]) -> Vec<f32> {
    let mut out = vec![0.0f32; dim as usize];
    let last = *window.last().unwrap_or(&0) as f32 / 255.0;
    for (i, o) in out.iter_mut().enumerate() {
        let v = last + (i as f32 + 1.0) * 0.013;
        *o = (v.sin() + v.cos()) * 0.5;
    }
    out
}

fn lag_bytes(lags: &[u32], window: &[u8]) -> Vec<f32> {
    let mut out = Vec::with_capacity(lags.len());
    for lag in lags {
        let idx = window.len().saturating_sub(*lag as usize + 1);
        out.push(window[idx] as f32 / 255.0);
    }
    out
}

fn linear(node_id: u32, input: &[f32], out_dim: usize) -> Vec<f32> {
    let mut out = vec![0.0f32; out_dim];
    for o in 0..out_dim {
        let mut acc = 0.0f32;
        for (i, x) in input.iter().enumerate() {
            let w = pseudo_weight(node_id, i as u32, o as u32);
            acc += w * *x;
        }
        out[o] = acc;
    }
    out
}

fn pseudo_weight(node_id: u32, in_ix: u32, out_ix: u32) -> f32 {
    let a = (node_id as u64)
        .wrapping_mul(6364136223846793005)
        .wrapping_add((in_ix as u64) << 16)
        .wrapping_add(out_ix as u64);
    let frac = (a % 10_000) as f32 / 10_000.0;
    (frac - 0.5) * 0.1
}

fn elementwise2(a: &[f32], b: &[f32], f: impl Fn(f32, f32) -> f32) -> Vec<f32> {
    a.iter().zip(b.iter()).map(|(x, y)| f(*x, *y)).collect()
}

fn run_length_bucket(buckets: u32, window: &[u8]) -> Vec<f32> {
    let mut out = vec![0.0f32; buckets as usize];
    let last = *window.last().unwrap_or(&0);
    let mut run = 0usize;
    for b in window.iter().rev() {
        if *b == last {
            run += 1;
        } else {
            break;
        }
    }
    let bucket = run.min(buckets as usize - 1);
    out[bucket] = 1.0;
    out
}

fn rolling_hash(n: usize, buckets: usize, window: &[u8]) -> Vec<f32> {
    let mut out = vec![0.0f32; buckets];
    let start = window.len().saturating_sub(n);
    let mut h: u64 = 1469598103934665603;
    for b in &window[start..] {
        h ^= *b as u64;
        h = h.wrapping_mul(1099511628211);
    }
    let bucket = (h as usize) % buckets;
    out[bucket] = 1.0;
    out
}

fn simple_scan(node_id: u32, input: &[f32], hidden_dim: usize) -> Vec<f32> {
    let mut h = vec![0.0f32; hidden_dim];
    for (t, x) in input.iter().enumerate() {
        for i in 0..hidden_dim {
            let w_h = pseudo_weight(node_id + 11, i as u32, i as u32);
            let w_x = pseudo_weight(node_id + 17, t as u32, i as u32);
            h[i] = (h[i] * w_h + x * w_x).tanh();
        }
    }
    h
}

pub fn run_program_v2(
    program: &crate::apfsc::types::ScirV2Program,
    window: &[u8],
) -> Result<Vec<u16>> {
    if window.is_empty() {
        return Err(ApfscError::Validation("window cannot be empty".to_string()));
    }
    let mut mass = vec![1u16; 256];
    let mut seed = 0u64;
    for b in window {
        seed = seed.wrapping_mul(131).wrapping_add(*b as u64);
    }
    seed = seed
        .wrapping_add(program.channels.len() as u64 * 17)
        .wrapping_add(program.core_blocks.len() as u64 * 29)
        .wrapping_add(program.readouts.len() as u64 * 37);
    for (i, m) in mass.iter_mut().enumerate() {
        let v = seed.wrapping_add((i as u64) * 13);
        *m = (1 + (v % 1024)) as u16;
    }
    Ok(mass)
}
