use std::collections::BTreeMap;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::Instant;

use crate::apfsc::errors::{ApfscError, Result};
use crate::apfsc::scir::ast::{AlienMutationVector, InterpTrace, ScirOp, ScirProgram};

pub const BACKEND_FINGERPRINT: &str = "apfsc-tier0-cpu-v1";

#[derive(Debug, Clone, Copy, serde::Serialize, serde::Deserialize, PartialEq, Eq)]
pub struct ScirInterpProfile {
    pub calls: u64,
    pub total_ms: u64,
    pub last_ms: u64,
}

static SCIR_INTERP_CALLS: AtomicU64 = AtomicU64::new(0);
static SCIR_INTERP_TOTAL_MS: AtomicU64 = AtomicU64::new(0);
static SCIR_INTERP_LAST_MS: AtomicU64 = AtomicU64::new(0);

struct ScirInterpTimer {
    started: Instant,
}

impl ScirInterpTimer {
    fn new() -> Self {
        Self {
            started: Instant::now(),
        }
    }
}

impl Drop for ScirInterpTimer {
    fn drop(&mut self) {
        let elapsed_ms = self
            .started
            .elapsed()
            .as_millis()
            .min(u128::from(u64::MAX)) as u64;
        SCIR_INTERP_CALLS.fetch_add(1, Ordering::Relaxed);
        SCIR_INTERP_TOTAL_MS.fetch_add(elapsed_ms, Ordering::Relaxed);
        SCIR_INTERP_LAST_MS.store(elapsed_ms, Ordering::Relaxed);
    }
}

pub fn scir_interp_profile() -> ScirInterpProfile {
    ScirInterpProfile {
        calls: SCIR_INTERP_CALLS.load(Ordering::Relaxed),
        total_ms: SCIR_INTERP_TOTAL_MS.load(Ordering::Relaxed),
        last_ms: SCIR_INTERP_LAST_MS.load(Ordering::Relaxed),
    }
}

pub fn run_program(program: &ScirProgram, window: &[u8]) -> Result<InterpTrace> {
    let _timer = ScirInterpTimer::new();
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
        ScirOp::HdcBind => {
            let a = get_input(values, node, 0)?;
            let b = get_input(values, node, 1)?;
            hdc_bind(a, b)
        }
        ScirOp::HdcBundle => hdc_bundle(node, values)?,
        ScirOp::HdcPermute { shift } => {
            let a = get_input(values, node, 0)?;
            hdc_permute(a, *shift as usize)
        }
        ScirOp::HdcThreshold { threshold } => {
            let a = get_input(values, node, 0)?;
            hdc_threshold(a, *threshold)
        }
        ScirOp::SparseEventQueue { slots } => sparse_event_queue(*slots as usize, window),
        ScirOp::SparseRouter { experts, topk } => {
            let a = get_input(values, node, 0)?;
            sparse_router(node.id, a, *experts as usize, *topk as usize)
        }
        ScirOp::SymbolicStack { depth } => symbolic_stack(*depth as usize, window),
        ScirOp::SymbolicTape { cells } => symbolic_tape(*cells as usize, window),
        ScirOp::AfferentNode { channel } => afferent_node(*channel, node.out_dim as usize),
        ScirOp::EctodermPrimitive { channel } => {
            let input = get_input(values, node, 0)?;
            ectoderm_primitive(node.id, *channel, input, node.out_dim as usize)
        }
        ScirOp::Subcortex {
            prior_hash,
            eigen_modulator_vector,
        } => {
            let input = if node.inputs.is_empty() {
                byte_embedding(node.out_dim.max(1), window)
            } else {
                get_input(values, node, 0)?.to_vec()
            };
            subcortex_fused(
                node.id,
                prior_hash,
                eigen_modulator_vector,
                &input,
                node.out_dim as usize,
            )
        }
        ScirOp::Alien {
            seed_hash,
            mutation_vector,
            fused_ops_hint,
        } => alien_fused(
            node.id,
            seed_hash,
            mutation_vector,
            *fused_ops_hint,
            node,
            values,
            window,
        ),
        ScirOp::AlephZero { recursion_depth } => {
            let input = get_input(values, node, 0)?;
            aleph_zero(node.id, input, *recursion_depth, window)
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

fn mutation_requests_self_mutate(mutation_vector: &AlienMutationVector) -> bool {
    mutation_vector.ops_added.iter().any(|s| {
        let t = s.to_ascii_lowercase();
        t.contains("self-mutate")
            || t.contains("self_mutate")
            || t.contains("intralayer_mutation")
            || t.contains("opcode[self-mutate]")
    })
}

fn alien_fused(
    node_id: u32,
    seed_hash: &str,
    mutation_vector: &AlienMutationVector,
    fused_ops_hint: u32,
    node: &crate::apfsc::scir::ast::ScirNode,
    values: &BTreeMap<u32, Vec<f32>>,
    window: &[u8],
) -> Vec<f32> {
    let mut seed: u64 = 0x9E37_79B9_7F4A_7C15u64 ^ node_id as u64;
    for b in seed_hash.as_bytes() {
        seed = seed.rotate_left(7) ^ (*b as u64);
        seed = seed.wrapping_mul(0xA24B_AED4_963E_E407);
    }
    for s in &mutation_vector.ops_added {
        for b in s.as_bytes() {
            seed = seed.rotate_left(5) ^ (*b as u64);
        }
    }
    for s in &mutation_vector.ops_removed {
        for b in s.as_bytes() {
            seed = seed.rotate_left(3) ^ (*b as u64);
        }
    }
    let fused_ops = mutation_vector.effective_fused_ops(fused_ops_hint);
    seed ^= (fused_ops as u64).wrapping_mul(0x9E37_79B9);

    let base: Vec<f32> = if let Some(input_id) = node.inputs.first() {
        values
            .get(input_id)
            .cloned()
            .unwrap_or_else(|| byte_embedding(node.out_dim.max(1), window))
    } else {
        byte_embedding(node.out_dim.max(1), window)
    };
    let out_dim = node.out_dim.max(1) as usize;
    let max_iters = fused_ops.max(4).min(64) as usize;
    let epsilon = 1.0 / (512.0 + fused_ops as f32 * 8.0);
    let allow_self_mutate = mutation_requests_self_mutate(mutation_vector);
    let mut prev = vec![0.0_f32; out_dim];
    let mut state = base
        .iter()
        .copied()
        .cycle()
        .take(out_dim)
        .collect::<Vec<_>>();
    for _ in 0..max_iters {
        for o in 0..out_dim {
            let lane = ((seed as usize).wrapping_add(o * 13)) % base.len();
            let mix = ((seed >> ((o % 8) * 8)) as u8 as f32 / 255.0) * 2.0 - 1.0;
            state[o] = (0.7 * state[o] + 0.3 * base[lane] * mix).tanh();
        }
        let delta = state
            .iter()
            .zip(prev.iter())
            .map(|(a, b)| (a - b).abs())
            .sum::<f32>()
            / out_dim.max(1) as f32;
        if delta <= epsilon {
            break;
        }
        if allow_self_mutate && delta > epsilon * 4.0 {
            // In-flight morphogenesis: perturb fused-kernel seed when local surprisal is high.
            // This keeps runtime deterministic while allowing alien loops to reconfigure.
            let jitter = ((delta * 1_000_000.0) as u64).wrapping_mul(0x9E37_79B9);
            seed ^= jitter.rotate_left((seed as u32 % 31) + 1);
            seed = seed.wrapping_mul(0xA24B_AED4_963E_E407).rotate_left(7);
        }
        prev.copy_from_slice(&state);
    }
    state
}

fn subcortex_fused(
    node_id: u32,
    prior_hash: &str,
    eigen_modulator_vector: &[f32],
    input: &[f32],
    out_dim: usize,
) -> Vec<f32> {
    if out_dim == 0 {
        return Vec::new();
    }
    let mut seed = node_id as u64 ^ 0xD15C_A7E5_5EED_BA5Eu64;
    for b in prior_hash.as_bytes() {
        seed = seed.rotate_left(9) ^ (*b as u64);
        seed = seed.wrapping_mul(0x9E37_79B9_7F4A_7C15);
    }
    let mut out = vec![0.0f32; out_dim];
    let mlen = eigen_modulator_vector.len().max(1);
    for i in 0..out_dim {
        let src = if input.is_empty() {
            0.0
        } else {
            input[i % input.len()]
        };
        let lane = ((seed >> ((i % 8) * 8)) & 0xFF) as f32 / 255.0 * 2.0 - 1.0;
        let modulator = eigen_modulator_vector.get(i % mlen).copied().unwrap_or(1.0);
        let gate = modulator.tanh();
        if gate.abs() < 0.05 {
            // Hyper-sparse gate: near-zero modulators skip historical subgraph execution.
            out[i] = src;
            continue;
        }
        let mixed = (0.80 * src + 0.20 * lane).tanh();
        out[i] = (src + gate * mixed).tanh();
    }
    out
}

fn ectoderm_primitive(node_id: u32, channel: u8, input: &[f32], out_dim: usize) -> Vec<f32> {
    if out_dim == 0 {
        return Vec::new();
    }
    let mean_abs = if input.is_empty() {
        0.0
    } else {
        input.iter().map(|v| v.abs()).sum::<f32>() / input.len() as f32
    };
    let base_phase = (((node_id as u64).wrapping_mul(17) ^ channel as u64) & 0xFF) as f32 / 255.0;
    let raw = match channel {
        0 => mean_abs * 1.35 + base_phase,
        1 => mean_abs * 1.15 + base_phase * 0.5,
        2 => mean_abs * 0.85 + base_phase * 1.5,
        _ => mean_abs + base_phase,
    };
    let value = 1.0 / (1.0 + (-raw).exp());
    vec![value; out_dim]
}

fn afferent_node(channel: u8, out_dim: usize) -> Vec<f32> {
    if out_dim == 0 {
        return Vec::new();
    }
    if let Some(seed_vec) = crate::apfsc::afferent::channel_seed_vector(channel, out_dim) {
        return seed_vec;
    }
    let base = crate::apfsc::afferent::channel_value(channel).clamp(0.0, 1.0);
    let mut out = vec![0.0; out_dim];
    for (i, v) in out.iter_mut().enumerate() {
        let phase = (i as f32 / out_dim.max(1) as f32) * 0.01;
        *v = (base + phase).clamp(0.0, 1.0);
    }
    out
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

fn hdc_bind(a: &[f32], b: &[f32]) -> Vec<f32> {
    a.iter()
        .zip(b.iter())
        .map(|(x, y)| (x * y).tanh())
        .collect()
}

fn hdc_bundle(
    node: &crate::apfsc::scir::ast::ScirNode,
    values: &BTreeMap<u32, Vec<f32>>,
) -> Result<Vec<f32>> {
    let mut inputs = Vec::<&[f32]>::new();
    for id in &node.inputs {
        inputs.push(
            values
                .get(id)
                .ok_or_else(|| ApfscError::Validation("hdc bundle input missing".to_string()))?,
        );
    }
    if inputs.is_empty() {
        return Ok(Vec::new());
    }
    let len = inputs[0].len();
    let mut out = vec![0.0f32; len];
    for inp in inputs {
        for (dst, src) in out.iter_mut().zip(inp.iter()) {
            *dst += *src;
        }
    }
    let norm = node.inputs.len().max(1) as f32;
    for dst in &mut out {
        *dst = (*dst / norm).clamp(-1.0, 1.0);
    }
    Ok(out)
}

fn hdc_permute(a: &[f32], shift: usize) -> Vec<f32> {
    if a.is_empty() {
        return Vec::new();
    }
    let mut out = vec![0.0f32; a.len()];
    let s = shift % a.len();
    for (i, v) in a.iter().enumerate() {
        out[(i + s) % a.len()] = *v;
    }
    out
}

fn hdc_threshold(a: &[f32], threshold: f32) -> Vec<f32> {
    a.iter()
        .map(|x| if *x >= threshold { 1.0 } else { -1.0 })
        .collect()
}

fn sparse_event_queue(slots: usize, window: &[u8]) -> Vec<f32> {
    if slots == 0 {
        return Vec::new();
    }
    let mut out = vec![0.0f32; slots];
    let span = window.len().min(slots.saturating_mul(4));
    let start = window.len().saturating_sub(span);
    let mut ev_ix = 0usize;
    for pair in window[start..].windows(2) {
        if pair[0] != pair[1] {
            out[ev_ix % slots] = 1.0;
            ev_ix = ev_ix.saturating_add(1);
        }
    }
    out
}

fn sparse_router(node_id: u32, input: &[f32], experts: usize, topk: usize) -> Vec<f32> {
    if experts == 0 {
        return Vec::new();
    }
    let mut scored = Vec::<(usize, f32)>::with_capacity(experts);
    for e in 0..experts {
        let mut score = 0.0f32;
        for (i, x) in input.iter().enumerate() {
            let w = pseudo_weight(node_id + 23, i as u32, e as u32);
            score += *x * w;
        }
        scored.push((e, score));
    }
    scored.sort_by(|a, b| {
        b.1.abs()
            .partial_cmp(&a.1.abs())
            .unwrap_or(std::cmp::Ordering::Equal)
    });
    let mut out = vec![0.0f32; experts];
    let keep = topk.max(1).min(experts);
    for (idx, score) in scored.into_iter().take(keep) {
        out[idx] = score.tanh();
    }
    out
}

fn symbolic_stack(depth: usize, window: &[u8]) -> Vec<f32> {
    if depth == 0 {
        return Vec::new();
    }
    let mut stack = Vec::<u8>::new();
    for b in window.iter().copied() {
        match b {
            b'(' | b'[' | b'{' | b'A'..=b'Z' | b'0'..=b'9' => {
                if stack.len() < depth {
                    stack.push(b);
                }
            }
            b')' | b']' | b'}' => {
                let _ = stack.pop();
            }
            _ => {}
        }
    }
    let mut out = vec![0.0f32; depth];
    for (i, b) in stack.iter().rev().take(depth).enumerate() {
        out[i] = (*b as f32) / 255.0;
    }
    out
}

fn symbolic_tape(cells: usize, window: &[u8]) -> Vec<f32> {
    if cells == 0 {
        return Vec::new();
    }
    let mut tape = vec![0u8; cells];
    let mut ptr = cells / 2;
    for b in window.iter().copied() {
        match b {
            b'>' => {
                ptr = (ptr + 1).min(cells - 1);
            }
            b'<' => {
                ptr = ptr.saturating_sub(1);
            }
            b'+' => {
                tape[ptr] = tape[ptr].saturating_add(1);
            }
            b'-' => {
                tape[ptr] = tape[ptr].saturating_sub(1);
            }
            b'=' => {
                tape[ptr] = 0;
            }
            _ => {}
        }
    }
    tape.into_iter().map(|v| v as f32 / 255.0).collect()
}

fn aleph_zero(node_id: u32, input: &[f32], recursion_depth: u32, window: &[u8]) -> Vec<f32> {
    if input.is_empty() {
        return Vec::new();
    }
    let depth = recursion_depth.clamp(1, 4096) as usize;
    let load = crate::apfsc::afferent::channel_value(0).clamp(0.0, 1.0);
    let thermal = crate::apfsc::afferent::channel_value(1).clamp(0.0, 1.0);
    let mut seed = (node_id as u64).wrapping_mul(0x9E37_79B9_7F4A_7C15);
    for b in window.iter().take(64) {
        seed = seed.rotate_left(5) ^ (*b as u64);
    }
    let r_base = 3.57 + 0.42 * ((load + thermal) * 0.5);
    let coupling = 0.10 + ((seed & 0xFF) as f32 / 255.0) * 0.20;
    let mut out = vec![0.0f32; input.len()];
    for i in 0..input.len() {
        let mut x = ((input[i].tanh() + 1.0) * 0.5).clamp(1.0e-6, 1.0 - 1.0e-6);
        let r = (r_base + ((i as f32 / input.len() as f32) * 0.06)).clamp(3.57, 3.99);
        let left = if i == 0 {
            ((input[input.len() - 1].tanh() + 1.0) * 0.5).clamp(1.0e-6, 1.0 - 1.0e-6)
        } else {
            ((input[i - 1].tanh() + 1.0) * 0.5).clamp(1.0e-6, 1.0 - 1.0e-6)
        };
        for _ in 0..depth {
            let logistic = r * x * (1.0 - x);
            x = (1.0 - coupling) * logistic + coupling * left;
            x = x.clamp(1.0e-6, 1.0 - 1.0e-6);
        }
        out[i] = x * 2.0 - 1.0;
    }
    out
}

pub fn run_program_v2(
    program: &crate::apfsc::types::ScirV2Program,
    window: &[u8],
) -> Result<Vec<u16>> {
    let _timer = ScirInterpTimer::new();
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
