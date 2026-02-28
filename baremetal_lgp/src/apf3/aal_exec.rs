use std::collections::HashMap;
use std::mem;
use std::ptr;

use crate::apf3::aal_ir::{AALGraph, MemInit, NodeId, NodeKind, ParamInit, ValueTy};
use crate::apf3::metachunkpack::{Chunk, MetaChunkPack};
use crate::apf3::nativeblock::{NativeBlockRegistry, NativeCtx, NativeExecError, NativeSandbox};
use crate::apf3::sfi::{SfiContext, SfiLayout};
use serde::{Deserialize, Serialize};

#[derive(Clone, Copy, Debug)]
pub struct ExecBudget {
    pub fuel_max: u64,
    pub op_max: u64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ExecStop {
    Ok,
    FuelExhausted,
    InvalidGraph(&'static str),
    NativeBlockFault,
    NativeBlockTimeout,
    NonFinite,
}

#[derive(Default, Debug, Clone, Copy, Serialize, Deserialize)]
pub struct TraceStats {
    pub support_loss_first: f32,
    pub support_loss_last: f32,
    pub query_loss_first: f32,
    pub query_loss_last: f32,
    pub query_loss_min: f32,
    pub mem_reads: u64,
    pub mem_writes: u64,
    pub update_l1: f64,
    pub native_faults: u64,
    pub native_timeouts: u64,
}

#[derive(Debug, Clone)]
pub struct ExecReport {
    pub query_score_mean: f32,
    pub query_score_var: f32,
    pub query_scores: Vec<f32>,
    pub query_loss_before_support: f32,
    pub query_loss_after_support: f32,
    pub stop: ExecStop,
    pub failure_label: Option<&'static str>,
    pub trace: TraceStats,
    pub episodes: u32,
}

#[derive(Clone)]
enum Value {
    F32(f32),
    Vec(Vec<f32>),
}

enum Phase {
    Support,
    Query,
}

struct BudgetState {
    fuel_left: u64,
    op_used: u64,
    op_max: u64,
}

struct NativeRuntime {
    sfi: SfiContext,
    sandbox: NativeSandbox,
    ctx_ptr: *mut NativeCtx,
    in_ptr: *mut f32,
    out_ptr: *mut f32,
    len: usize,
}

pub struct AALExecutor {
    pub budget: ExecBudget,
    pub sfi_layout: SfiLayout,
    pub native_timeout_us: u64,
}

impl Default for AALExecutor {
    fn default() -> Self {
        Self {
            budget: ExecBudget {
                fuel_max: 200_000,
                op_max: 2_000_000,
            },
            sfi_layout: SfiLayout {
                window_size: 1 << 30,
                stack_size: 1 << 20,
                state_size: 1 << 20,
                heap_size: 1 << 20,
            },
            native_timeout_us: 50_000,
        }
    }
}

impl AALExecutor {
    pub fn eval_pack(
        &self,
        graph: &AALGraph,
        pack: &MetaChunkPack,
        registry: Option<&NativeBlockRegistry>,
    ) -> ExecReport {
        if let Err(err) = graph.validate() {
            let _ = err;
            return ExecReport {
                query_score_mean: 0.0,
                query_score_var: 0.0,
                query_scores: Vec::new(),
                query_loss_before_support: f32::INFINITY,
                query_loss_after_support: f32::INFINITY,
                stop: ExecStop::InvalidGraph("graph validation failed"),
                failure_label: Some("UpdateFailure"),
                trace: TraceStats::default(),
                episodes: 0,
            };
        }

        let topo = match graph.topo_order() {
            Ok(v) => v,
            Err(_) => {
                return ExecReport {
                    query_score_mean: 0.0,
                    query_score_var: 0.0,
                    query_scores: Vec::new(),
                    query_loss_before_support: f32::INFINITY,
                    query_loss_after_support: f32::INFINITY,
                    stop: ExecStop::InvalidGraph("cyclic graph"),
                    failure_label: Some("UpdateFailure"),
                    trace: TraceStats::default(),
                    episodes: 0,
                }
            }
        };

        let incoming = build_incoming(&graph.edges);
        let mut params = init_params(graph);
        let mut mem_slots = init_mem(graph);

        let max_native_len = graph
            .nodes
            .iter()
            .filter_map(|(_, node)| match node {
                NodeKind::NativeBlock { len, .. } => Some(*len as usize),
                _ => None,
            })
            .max()
            .unwrap_or(0);

        let mut native_rt = if max_native_len > 0 {
            match prepare_native_runtime(self.sfi_layout, self.native_timeout_us, max_native_len) {
                Ok(rt) => Some(rt),
                Err(_) => {
                    return ExecReport {
                        query_score_mean: 0.0,
                        query_score_var: 0.0,
                        query_scores: Vec::new(),
                        query_loss_before_support: f32::INFINITY,
                        query_loss_after_support: f32::INFINITY,
                        stop: ExecStop::NativeBlockFault,
                        failure_label: Some("NativeBlockFailure"),
                        trace: TraceStats {
                            native_faults: 1,
                            ..TraceStats::default()
                        },
                        episodes: 0,
                    }
                }
            }
        } else {
            None
        };

        let mut trace = TraceStats {
            query_loss_min: f32::INFINITY,
            ..TraceStats::default()
        };

        // Pre-support query baseline (adaptation gain reference).
        let mut before_losses = Vec::with_capacity(pack.query.len());
        for q in &pack.query {
            match run_chunk(
                graph,
                &topo,
                &incoming,
                q,
                Phase::Query,
                &mut params,
                &mut mem_slots,
                &mut trace,
                &self.budget,
                registry,
                native_rt.as_mut(),
            ) {
                Ok(loss) => before_losses.push(loss),
                Err(stop) => {
                    return fail_report(stop, trace, 0);
                }
            }
        }

        // Reset candidate state to initial before actual support/query trajectory.
        params = init_params(graph);
        mem_slots = init_mem(graph);

        let mut support_first = true;
        for s in &pack.support {
            let loss = match run_chunk(
                graph,
                &topo,
                &incoming,
                s,
                Phase::Support,
                &mut params,
                &mut mem_slots,
                &mut trace,
                &self.budget,
                registry,
                native_rt.as_mut(),
            ) {
                Ok(loss) => loss,
                Err(stop) => {
                    return fail_report(stop, trace, 0);
                }
            };

            if support_first {
                trace.support_loss_first = loss;
                support_first = false;
            }
            trace.support_loss_last = loss;
        }

        let mut query_losses = Vec::with_capacity(pack.query.len());
        let mut query_scores = Vec::with_capacity(pack.query.len());
        for q in &pack.query {
            let loss = match run_chunk(
                graph,
                &topo,
                &incoming,
                q,
                Phase::Query,
                &mut params,
                &mut mem_slots,
                &mut trace,
                &self.budget,
                registry,
                native_rt.as_mut(),
            ) {
                Ok(loss) => loss,
                Err(stop) => {
                    return fail_report(stop, trace, query_losses.len() as u32);
                }
            };
            if query_losses.is_empty() {
                trace.query_loss_first = loss;
            }
            trace.query_loss_last = loss;
            trace.query_loss_min = trace.query_loss_min.min(loss);
            query_scores.push(-loss);
            query_losses.push(loss);
        }

        let query_score_mean = mean_f32(&query_scores);
        let query_score_var = var_f32(&query_scores, query_score_mean);
        let query_loss_before_support = mean_f32(&before_losses);
        let query_loss_after_support = mean_f32(&query_losses);

        ExecReport {
            query_score_mean,
            query_score_var,
            query_scores,
            query_loss_before_support,
            query_loss_after_support,
            stop: ExecStop::Ok,
            failure_label: None,
            trace,
            episodes: query_losses.len() as u32,
        }
    }
}

#[allow(clippy::too_many_arguments)]
fn run_chunk(
    graph: &AALGraph,
    topo: &[NodeId],
    incoming: &HashMap<NodeId, Vec<(u16, NodeId, u16)>>,
    chunk: &Chunk,
    phase: Phase,
    params: &mut [Vec<f32>],
    mem_slots: &mut [Vec<f32>],
    trace: &mut TraceStats,
    budget_cfg: &ExecBudget,
    registry: Option<&NativeBlockRegistry>,
    mut native_rt: Option<&mut NativeRuntime>,
) -> Result<f32, ExecStop> {
    let mut values: HashMap<(NodeId, u16), Value> = HashMap::new();
    let mut budget = BudgetState {
        fuel_left: budget_cfg.fuel_max,
        op_used: 0,
        op_max: budget_cfg.op_max,
    };

    for &node_id in topo {
        let node = graph
            .node_kind(node_id)
            .ok_or(ExecStop::InvalidGraph("missing node kind"))?;
        let inports = incoming.get(&node_id).cloned().unwrap_or_default();

        let mut inmap = HashMap::<u16, Value>::new();
        for (dst_port, src_id, src_port) in inports {
            let v = values
                .get(&(src_id, src_port))
                .cloned()
                .ok_or(ExecStop::InvalidGraph("missing source value"))?;
            inmap.insert(dst_port, v);
        }

        charge_cost(1, &mut budget)?;

        match node {
            NodeKind::Input { index, ty } => {
                let v = read_io_by_type(&chunk.x, *index, *ty)
                    .ok_or(ExecStop::InvalidGraph("input index/shape out of bounds"))?;
                values.insert((node_id, 0), v);
            }
            NodeKind::Target { index, ty } => {
                let v = read_io_by_type(&chunk.y, *index, *ty)
                    .ok_or(ExecStop::InvalidGraph("target index/shape out of bounds"))?;
                values.insert((node_id, 0), v);
            }
            NodeKind::ConstF32 { v } => {
                values.insert((node_id, 0), Value::F32(*v));
            }
            NodeKind::Add => {
                let a = inmap
                    .remove(&0)
                    .ok_or(ExecStop::InvalidGraph("Add missing input 0"))?;
                let b = inmap
                    .remove(&1)
                    .ok_or(ExecStop::InvalidGraph("Add missing input 1"))?;
                let out = add_values(a, b)?;
                charge_vec_cost(&out, &mut budget)?;
                ensure_finite(&out)?;
                values.insert((node_id, 0), out);
            }
            NodeKind::Mul => {
                let a = inmap
                    .remove(&0)
                    .ok_or(ExecStop::InvalidGraph("Mul missing input 0"))?;
                let b = inmap
                    .remove(&1)
                    .ok_or(ExecStop::InvalidGraph("Mul missing input 1"))?;
                let out = mul_values(a, b)?;
                charge_vec_cost(&out, &mut budget)?;
                ensure_finite(&out)?;
                values.insert((node_id, 0), out);
            }
            NodeKind::Linear {
                in_len,
                out_len,
                w,
                b,
            } => {
                let x = inmap
                    .remove(&0)
                    .ok_or(ExecStop::InvalidGraph("Linear missing input"))?;
                let x = as_vec(x)?;
                if x.len() != *in_len as usize {
                    return Err(ExecStop::InvalidGraph("Linear input len mismatch"));
                }

                let w_idx = w.0 as usize;
                let b_idx = b.0 as usize;
                if w_idx >= params.len() || b_idx >= params.len() {
                    return Err(ExecStop::InvalidGraph("Linear param ref out of range"));
                }
                let wv = &params[w_idx];
                let bv = &params[b_idx];

                let out_n = *out_len as usize;
                if wv.len() != x.len().saturating_mul(out_n) || bv.len() != out_n {
                    return Err(ExecStop::InvalidGraph("Linear param shape mismatch"));
                }

                charge_cost(
                    (x.len() as u64 / 8).saturating_add(out_n as u64 / 8),
                    &mut budget,
                )?;

                let mut out = vec![0.0_f32; out_n];
                for o in 0..out_n {
                    let mut acc = bv[o];
                    let row = o * x.len();
                    for i in 0..x.len() {
                        acc += wv[row + i] * x[i];
                    }
                    out[o] = acc;
                }
                ensure_slice_finite(&out)?;
                values.insert((node_id, 0), Value::Vec(out));
            }
            NodeKind::ActTanh => {
                let x = inmap
                    .remove(&0)
                    .ok_or(ExecStop::InvalidGraph("ActTanh missing input"))?;
                let out = map_activation(x, |v| v.tanh())?;
                charge_vec_cost(&out, &mut budget)?;
                ensure_finite(&out)?;
                values.insert((node_id, 0), out);
            }
            NodeKind::ActSigmoid => {
                let x = inmap
                    .remove(&0)
                    .ok_or(ExecStop::InvalidGraph("ActSigmoid missing input"))?;
                let out = map_activation(x, |v| 1.0 / (1.0 + (-v).exp()))?;
                charge_vec_cost(&out, &mut budget)?;
                ensure_finite(&out)?;
                values.insert((node_id, 0), out);
            }
            NodeKind::ReadMem { slot, len } => {
                let idx = slot.0 as usize;
                if idx >= mem_slots.len() || mem_slots[idx].len() != *len as usize {
                    return Err(ExecStop::InvalidGraph("ReadMem slot/len mismatch"));
                }
                trace.mem_reads = trace.mem_reads.saturating_add(*len as u64);
                values.insert((node_id, 0), Value::Vec(mem_slots[idx].clone()));
            }
            NodeKind::WriteMem { slot, len } => {
                if matches!(phase, Phase::Support) {
                    let idx = slot.0 as usize;
                    if idx >= mem_slots.len() || mem_slots[idx].len() != *len as usize {
                        return Err(ExecStop::InvalidGraph("WriteMem slot/len mismatch"));
                    }
                    let x = inmap
                        .remove(&0)
                        .ok_or(ExecStop::InvalidGraph("WriteMem missing input"))?;
                    let x = as_vec(x)?;
                    if x.len() != *len as usize {
                        return Err(ExecStop::InvalidGraph("WriteMem vector len mismatch"));
                    }
                    trace.mem_writes = trace.mem_writes.saturating_add(*len as u64);
                    mem_slots[idx].copy_from_slice(&x);
                }
            }
            NodeKind::DeltaUpdate { lr, w, x, err } => {
                if matches!(phase, Phase::Support) {
                    let w_idx = w.0 as usize;
                    if w_idx >= params.len() {
                        return Err(ExecStop::InvalidGraph("DeltaUpdate param out of range"));
                    }
                    let xv = values
                        .get(x)
                        .cloned()
                        .ok_or(ExecStop::InvalidGraph("DeltaUpdate missing x ref"))?;
                    let ev = values
                        .get(err)
                        .cloned()
                        .ok_or(ExecStop::InvalidGraph("DeltaUpdate missing err ref"))?;
                    let x_vec = as_vec(xv)?;
                    let e_vec = as_vec(ev)?;

                    let expected = x_vec.len().saturating_mul(e_vec.len());
                    if params[w_idx].len() != expected {
                        return Err(ExecStop::InvalidGraph("DeltaUpdate param length mismatch"));
                    }

                    charge_cost((expected as u64 / 8).saturating_add(1), &mut budget)?;
                    let mut l1 = 0.0_f64;
                    let mut k = 0_usize;
                    for &e in &e_vec {
                        for &xv in &x_vec {
                            let delta = *lr * e * xv;
                            params[w_idx][k] += delta;
                            l1 += f64::from(delta.abs());
                            k += 1;
                        }
                    }
                    trace.update_l1 += l1;
                    ensure_slice_finite(&params[w_idx])?;
                }
            }
            NodeKind::NativeBlock { spec_digest, len } => {
                let rv = registry.ok_or(ExecStop::InvalidGraph("missing native registry"))?;
                let rt = native_rt
                    .as_deref_mut()
                    .ok_or(ExecStop::InvalidGraph("missing native runtime"))?;
                let x = inmap
                    .remove(&0)
                    .ok_or(ExecStop::InvalidGraph("NativeBlock missing input"))?;
                let x = as_vec(x)?;
                if x.len() != *len as usize || x.len() > rt.len {
                    return Err(ExecStop::InvalidGraph("NativeBlock len mismatch"));
                }

                // SAFETY: pointers come from SFI bump allocator and are in-bounds.
                unsafe {
                    ptr_copy_f32(rt.in_ptr, &x);
                    zero_f32(rt.out_ptr, x.len());
                    ptr::write_bytes(rt.sfi.state, 0, rt.sfi.layout.state_size);

                    let ctx = &mut *rt.ctx_ptr;
                    ctx.phase = if matches!(phase, Phase::Support) {
                        0
                    } else {
                        1
                    };
                    ctx.fuel_left = budget.fuel_left;
                    ctx.state_ptr = rt.sfi.state;
                    ctx.state_len = rt.sfi.layout.state_size as u32;
                    ctx.heap_ptr = rt.sfi.heap;
                    ctx.heap_len = rt.sfi.layout.heap_size as u32;
                    ctx.in_ptr = rt.in_ptr;
                    ctx.out_ptr = rt.out_ptr;
                    ctx.len = x.len() as u32;
                    ctx.reserved = 0;
                }

                let status = match rv.execute(*spec_digest, rt.ctx_ptr, &rt.sfi, &rt.sandbox) {
                    Ok(code) => code,
                    Err(NativeExecError::Timeout) => {
                        trace.native_timeouts = trace.native_timeouts.saturating_add(1);
                        return Err(ExecStop::NativeBlockTimeout);
                    }
                    Err(
                        NativeExecError::Fault { .. }
                        | NativeExecError::MissingBlock
                        | NativeExecError::PointerEscape,
                    ) => {
                        trace.native_faults = trace.native_faults.saturating_add(1);
                        return Err(ExecStop::NativeBlockFault);
                    }
                };
                if status != 0 {
                    trace.native_faults = trace.native_faults.saturating_add(1);
                    return Err(ExecStop::NativeBlockFault);
                }

                // SAFETY: out_ptr points to x.len() initialized f32 values.
                let out = unsafe { slice_from_ptr_f32(rt.out_ptr, x.len()) };
                ensure_slice_finite(&out)?;
                values.insert((node_id, 0), Value::Vec(out));
            }
        }
    }

    let pred = collect_outputs(graph, &values)?;
    let loss = mse(&pred, &chunk.y);
    if !loss.is_finite() {
        return Err(ExecStop::NonFinite);
    }

    Ok(loss)
}

fn prepare_native_runtime(
    layout: SfiLayout,
    timeout_us: u64,
    len: usize,
) -> Result<NativeRuntime, String> {
    let mut sfi = SfiContext::new(layout)?;

    let ctx_ptr = sfi.alloc_heap(mem::size_of::<NativeCtx>(), mem::align_of::<NativeCtx>());
    if ctx_ptr.is_null() {
        return Err("SFI heap exhausted for NativeCtx".to_string());
    }

    let in_ptr = sfi.alloc_heap(len * mem::size_of::<f32>(), mem::align_of::<f32>()) as *mut f32;
    if in_ptr.is_null() {
        return Err("SFI heap exhausted for input buffer".to_string());
    }

    let out_ptr = sfi.alloc_heap(len * mem::size_of::<f32>(), mem::align_of::<f32>()) as *mut f32;
    if out_ptr.is_null() {
        return Err("SFI heap exhausted for output buffer".to_string());
    }

    let sandbox = NativeSandbox::new(timeout_us);

    Ok(NativeRuntime {
        sfi,
        sandbox,
        ctx_ptr: ctx_ptr as *mut NativeCtx,
        in_ptr,
        out_ptr,
        len,
    })
}

fn fail_report(stop: ExecStop, trace: TraceStats, episodes: u32) -> ExecReport {
    let label = match stop {
        ExecStop::NativeBlockFault | ExecStop::NativeBlockTimeout => Some("NativeBlockFailure"),
        ExecStop::FuelExhausted | ExecStop::NonFinite => Some("UpdateFailure"),
        ExecStop::InvalidGraph(_) => Some("UpdateFailure"),
        ExecStop::Ok => None,
    };

    ExecReport {
        query_score_mean: 0.0,
        query_score_var: 0.0,
        query_scores: Vec::new(),
        query_loss_before_support: f32::INFINITY,
        query_loss_after_support: f32::INFINITY,
        stop,
        failure_label: label,
        trace,
        episodes,
    }
}

fn build_incoming(edges: &[crate::apf3::aal_ir::Edge]) -> HashMap<NodeId, Vec<(u16, NodeId, u16)>> {
    let mut incoming: HashMap<NodeId, Vec<(u16, NodeId, u16)>> = HashMap::new();
    for edge in edges {
        incoming
            .entry(edge.dst.0)
            .or_default()
            .push((edge.dst.1, edge.src.0, edge.src.1));
    }
    incoming
}

fn init_params(graph: &AALGraph) -> Vec<Vec<f32>> {
    graph
        .params
        .params
        .iter()
        .map(|spec| match spec.init {
            ParamInit::Zeros => vec![0.0; spec.len as usize],
        })
        .collect()
}

fn init_mem(graph: &AALGraph) -> Vec<Vec<f32>> {
    graph
        .mem
        .iter()
        .map(|spec| match spec.init {
            MemInit::Zeros => vec![0.0; spec.len as usize],
        })
        .collect()
}

fn read_io_by_type(io: &[f32], index: u32, ty: ValueTy) -> Option<Value> {
    match ty {
        ValueTy::F32 => io.get(index as usize).copied().map(Value::F32),
        ValueTy::VecF32 { len } => {
            let start = index as usize * len as usize;
            let end = start.checked_add(len as usize)?;
            io.get(start..end).map(|s| Value::Vec(s.to_vec()))
        }
    }
}

fn collect_outputs(
    graph: &AALGraph,
    values: &HashMap<(NodeId, u16), Value>,
) -> Result<Vec<f32>, ExecStop> {
    let mut out = Vec::new();
    for &(node, port) in &graph.outputs {
        let v = values
            .get(&(node, port))
            .cloned()
            .ok_or(ExecStop::InvalidGraph("missing graph output value"))?;
        match v {
            Value::F32(x) => out.push(x),
            Value::Vec(vs) => out.extend(vs),
        }
    }
    Ok(out)
}

fn add_values(a: Value, b: Value) -> Result<Value, ExecStop> {
    match (a, b) {
        (Value::F32(x), Value::F32(y)) => Ok(Value::F32(x + y)),
        (Value::Vec(x), Value::Vec(y)) => {
            if x.len() != y.len() {
                return Err(ExecStop::InvalidGraph("vector add len mismatch"));
            }
            let out = x.iter().zip(y.iter()).map(|(a, b)| a + b).collect();
            Ok(Value::Vec(out))
        }
        _ => Err(ExecStop::InvalidGraph("add type mismatch")),
    }
}

fn mul_values(a: Value, b: Value) -> Result<Value, ExecStop> {
    match (a, b) {
        (Value::F32(x), Value::F32(y)) => Ok(Value::F32(x * y)),
        (Value::Vec(x), Value::Vec(y)) => {
            if x.len() != y.len() {
                return Err(ExecStop::InvalidGraph("vector mul len mismatch"));
            }
            let out = x.iter().zip(y.iter()).map(|(a, b)| a * b).collect();
            Ok(Value::Vec(out))
        }
        _ => Err(ExecStop::InvalidGraph("mul type mismatch")),
    }
}

fn map_activation(v: Value, f: impl Fn(f32) -> f32) -> Result<Value, ExecStop> {
    match v {
        Value::F32(x) => Ok(Value::F32(f(x))),
        Value::Vec(xs) => Ok(Value::Vec(xs.into_iter().map(f).collect())),
    }
}

fn as_vec(v: Value) -> Result<Vec<f32>, ExecStop> {
    match v {
        Value::Vec(v) => Ok(v),
        _ => Err(ExecStop::InvalidGraph("expected vector value")),
    }
}

fn ensure_finite(v: &Value) -> Result<(), ExecStop> {
    match v {
        Value::F32(x) => {
            if x.is_finite() {
                Ok(())
            } else {
                Err(ExecStop::NonFinite)
            }
        }
        Value::Vec(xs) => ensure_slice_finite(xs),
    }
}

fn ensure_slice_finite(xs: &[f32]) -> Result<(), ExecStop> {
    if xs.iter().all(|x| x.is_finite()) {
        Ok(())
    } else {
        Err(ExecStop::NonFinite)
    }
}

fn charge_vec_cost(v: &Value, budget: &mut BudgetState) -> Result<(), ExecStop> {
    let len = match v {
        Value::F32(_) => 1_u64,
        Value::Vec(v) => v.len() as u64,
    };
    charge_cost(len / 8, budget)
}

fn charge_cost(cost: u64, budget: &mut BudgetState) -> Result<(), ExecStop> {
    let cost = cost.max(1);
    if budget.op_used.saturating_add(cost) > budget.op_max {
        return Err(ExecStop::FuelExhausted);
    }
    if budget.fuel_left < cost {
        return Err(ExecStop::FuelExhausted);
    }
    budget.fuel_left -= cost;
    budget.op_used = budget.op_used.saturating_add(cost);
    Ok(())
}

fn mean_f32(xs: &[f32]) -> f32 {
    if xs.is_empty() {
        0.0
    } else {
        xs.iter().copied().sum::<f32>() / xs.len() as f32
    }
}

fn var_f32(xs: &[f32], mean: f32) -> f32 {
    if xs.len() <= 1 {
        0.0
    } else {
        xs.iter()
            .map(|x| {
                let d = *x - mean;
                d * d
            })
            .sum::<f32>()
            / xs.len() as f32
    }
}

fn mse(pred: &[f32], target: &[f32]) -> f32 {
    let n = pred.len().min(target.len());
    if n == 0 {
        return 0.0;
    }

    let mut acc = 0.0_f32;
    for i in 0..n {
        let d = pred[i] - target[i];
        acc += d * d;
    }
    acc / n as f32
}

unsafe fn ptr_copy_f32(dst: *mut f32, src: &[f32]) {
    // SAFETY: caller guarantees destination points to at least src.len() f32 values.
    unsafe {
        std::ptr::copy_nonoverlapping(src.as_ptr(), dst, src.len());
    }
}

unsafe fn zero_f32(dst: *mut f32, len: usize) {
    // SAFETY: caller guarantees destination points to at least len f32 values.
    unsafe {
        std::ptr::write_bytes(dst, 0, len);
    }
}

unsafe fn slice_from_ptr_f32(src: *const f32, len: usize) -> Vec<f32> {
    // SAFETY: caller guarantees source points to at least len initialized f32 values.
    unsafe { std::slice::from_raw_parts(src, len).to_vec() }
}
