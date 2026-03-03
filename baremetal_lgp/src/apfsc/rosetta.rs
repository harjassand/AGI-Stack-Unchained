use std::collections::BTreeMap;
use std::path::Path;

use rand::{Rng, SeedableRng};
use rand_chacha::ChaCha8Rng;
use serde::{Deserialize, Serialize};

use crate::apfsc::artifacts::{
    append_jsonl_atomic, digest_json, list_json_files_sorted_by_mtime_desc, read_json,
    receipt_path, write_discovery_artifact, write_json_atomic,
};
use crate::apfsc::candidate::load_active_candidate;
use crate::apfsc::errors::Result;
use crate::apfsc::scir::ast::{ScirOp, ScirProgram};
use crate::apfsc::scir::interp::run_program;

const SURPRISAL_WINDOW: usize = 12;
const SURPRISAL_MIN_SUSTAINED: usize = 4;
const SURPRISAL_MAX_BITS: f64 = 0.08;
const PROBE_SAMPLES: usize = 96;

const SGP_STEPS: usize = 4096;
const SGP_MAX_DEPTH: usize = 4;
const SGP_TEMP_START: f64 = 0.08;
const SGP_TEMP_END: f64 = 0.001;
const SGP_R2_MIN: f64 = 0.55;
const SGP_COMBINATORIAL_MSE_MAX: f64 = 1.0e-9;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct RosettaDiscoveryArtifact {
    pub discovery_id: String,
    pub epoch: u64,
    pub candidate_hash: String,
    pub discovery_class: String,
    pub symbolic_pde_equation: String,
    pub thermal_afferent_baseline: serde_json::Value,
    pub aleph_holographic_geometry_representation: serde_json::Value,
    pub class_r_surprisal_bits_mean: f64,
    pub class_r_surprisal_bits_min: f64,
    pub class_r_surprisal_bits_max: f64,
    pub probe_r2: f64,
    pub sgp_mse: f64,
    pub combinatorially_proven: bool,
    pub sgp_iterations: usize,
    pub samples: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
struct RosettaProbeReceipt {
    epoch: u64,
    candidate_hash: String,
    symbolic_pde_equation: String,
    probe_r2: f64,
    sgp_mse: f64,
    combinatorially_proven: bool,
    sgp_iterations: usize,
    samples: usize,
    sustained_surprisal_mean_bits: f64,
    sustained_surprisal_min_bits: f64,
    sustained_surprisal_max_bits: f64,
}

#[derive(Debug, Clone, Deserialize)]
struct DethroningAuditSample {
    candidate_hash: String,
    #[serde(default)]
    class_r_surprisal_bits: Option<f64>,
}

#[derive(Debug, Clone, Copy)]
struct SurprisalStats {
    min: f64,
    max: f64,
    mean: f64,
}

#[derive(Debug, Clone)]
struct SgpFit {
    equation: String,
    mse: f64,
    r2: f64,
    combinatorially_proven: bool,
    iterations: usize,
}

#[derive(Debug, Clone)]
enum SgpExpr {
    Var,
    Const(f64),
    Add(Box<SgpExpr>, Box<SgpExpr>),
    Sub(Box<SgpExpr>, Box<SgpExpr>),
    Mul(Box<SgpExpr>, Box<SgpExpr>),
    Div(Box<SgpExpr>, Box<SgpExpr>),
    Sin(Box<SgpExpr>),
    Cos(Box<SgpExpr>),
    Log(Box<SgpExpr>),
    Exp(Box<SgpExpr>),
    Step(Box<SgpExpr>),
}

#[derive(Debug, Clone, Copy)]
struct SgpScore {
    mse: f64,
    r2: f64,
}

pub fn attempt_symbolic_extraction(
    root: &Path,
    epoch: u64,
) -> Result<Option<RosettaDiscoveryArtifact>> {
    let active = load_active_candidate(root)?;
    if !contains_aleph_or_alien(&active.arch_program) {
        return Ok(None);
    }
    let surprisal = sustained_surprisal_for_candidate(root, &active.manifest.candidate_hash)?;
    let Some(stats) = surprisal else {
        return Ok(None);
    };

    let fit = probe_symbolic_fit(&active.arch_program, epoch, &active.manifest.candidate_hash)?;
    if !fit.r2.is_finite() || fit.r2 < SGP_R2_MIN {
        return Ok(None);
    }

    let symbolic = fit.equation;
    let discovery_class =
        classify_discovery(&active.build_meta.notes, &active.build_meta.mutation_type);
    let thermal_afferent_baseline = serde_json::to_value(
        crate::apfsc::afferent::load_snapshot(root)
            .unwrap_or_else(crate::apfsc::afferent::sample_macos_telemetry),
    )?;
    let geometry = build_geometry(&active.arch_program);
    let discovery_id = digest_json(&(
        epoch,
        &active.manifest.candidate_hash,
        &symbolic,
        discovery_class.as_str(),
    ))?;
    if root
        .join("discoveries")
        .join(format!("{discovery_id}.json"))
        .exists()
    {
        return Ok(None);
    }

    let artifact = RosettaDiscoveryArtifact {
        discovery_id: discovery_id.clone(),
        epoch,
        candidate_hash: active.manifest.candidate_hash.clone(),
        discovery_class,
        symbolic_pde_equation: symbolic.clone(),
        thermal_afferent_baseline,
        aleph_holographic_geometry_representation: geometry,
        class_r_surprisal_bits_mean: stats.mean,
        class_r_surprisal_bits_min: stats.min,
        class_r_surprisal_bits_max: stats.max,
        probe_r2: fit.r2,
        sgp_mse: fit.mse,
        combinatorially_proven: fit.combinatorially_proven,
        sgp_iterations: fit.iterations,
        samples: PROBE_SAMPLES,
    };

    write_discovery_artifact(root, &discovery_id, &artifact)?;
    append_jsonl_atomic(&root.join("archives").join("discoveries.jsonl"), &artifact)?;
    write_json_atomic(
        &receipt_path(root, "rosetta", &format!("{discovery_id}.json")),
        &RosettaProbeReceipt {
            epoch,
            candidate_hash: active.manifest.candidate_hash,
            symbolic_pde_equation: symbolic,
            probe_r2: fit.r2,
            sgp_mse: fit.mse,
            combinatorially_proven: fit.combinatorially_proven,
            sgp_iterations: fit.iterations,
            samples: PROBE_SAMPLES,
            sustained_surprisal_mean_bits: stats.mean,
            sustained_surprisal_min_bits: stats.min,
            sustained_surprisal_max_bits: stats.max,
        },
    )?;
    Ok(Some(artifact))
}

fn contains_aleph_or_alien(program: &ScirProgram) -> bool {
    program
        .nodes
        .iter()
        .any(|n| matches!(n.op, ScirOp::AlephZero { .. } | ScirOp::Alien { .. }))
}

fn classify_discovery(notes: &Option<String>, mutation_type: &str) -> String {
    let mut t = mutation_type.to_ascii_lowercase();
    if let Some(n) = notes {
        t.push(' ');
        t.push_str(&n.to_ascii_lowercase());
    }
    if t.contains("tokamak") || t.contains("plasma") || t.contains("fusion") {
        "Stable Plasma Equivariance".to_string()
    } else if t.contains("superconductor") || t.contains("resonance") {
        "Non-Linear Material Resonance Constraint".to_string()
    } else if t.contains("schrodinger") || t.contains("hamiltonian") {
        "Hamiltonian Wavefield Closure".to_string()
    } else {
        "Fractal PDE Closure".to_string()
    }
}

fn build_geometry(program: &ScirProgram) -> serde_json::Value {
    let mut op_dist = BTreeMap::<String, u64>::new();
    let mut aleph_nodes = Vec::<u32>::new();
    let mut alien_nodes = Vec::<u32>::new();
    for n in &program.nodes {
        let key = match n.op {
            ScirOp::AlephZero { .. } => "AlephZero",
            ScirOp::Alien { .. } => "Alien",
            ScirOp::Subcortex { .. } => "Subcortex",
            ScirOp::SimpleScan { .. } => "SimpleScan",
            ScirOp::SparseRouter { .. } => "SparseRouter",
            ScirOp::SymbolicTape { .. } => "SymbolicTape",
            ScirOp::HdcBind
            | ScirOp::HdcBundle
            | ScirOp::HdcPermute { .. }
            | ScirOp::HdcThreshold { .. } => "HDC",
            _ => "Other",
        };
        *op_dist.entry(key.to_string()).or_insert(0) += 1;
        match n.op {
            ScirOp::AlephZero { .. } => aleph_nodes.push(n.id),
            ScirOp::Alien { .. } => alien_nodes.push(n.id),
            _ => {}
        }
    }
    serde_json::json!({
        "node_count": program.nodes.len(),
        "input_len": program.input_len,
        "feature_node": program.outputs.feature_node,
        "operator_distribution": op_dist,
        "aleph_nodes": aleph_nodes,
        "alien_nodes": alien_nodes,
    })
}

fn sustained_surprisal_for_candidate(
    root: &Path,
    candidate_hash: &str,
) -> Result<Option<SurprisalStats>> {
    let dir = root.join("receipts").join("dethroning_audit");
    if !dir.exists() {
        return Ok(None);
    }
    let files = list_json_files_sorted_by_mtime_desc(&dir, SURPRISAL_WINDOW * 8)?;
    let mut kept = Vec::<f64>::new();
    for path in files {
        let sample: DethroningAuditSample = match read_json(&path) {
            Ok(v) => v,
            Err(_) => continue,
        };
        if sample.candidate_hash != candidate_hash {
            continue;
        }
        let Some(bits) = sample.class_r_surprisal_bits else {
            continue;
        };
        if bits.is_finite() {
            kept.push(bits);
        }
        if kept.len() >= SURPRISAL_WINDOW {
            break;
        }
    }
    if kept.len() < SURPRISAL_MIN_SUSTAINED {
        return Ok(None);
    }
    let sustained = kept
        .iter()
        .copied()
        .filter(|v| *v <= SURPRISAL_MAX_BITS)
        .count();
    if sustained < SURPRISAL_MIN_SUSTAINED {
        return Ok(None);
    }
    let min = kept.iter().copied().fold(f64::INFINITY, f64::min);
    let max = kept.iter().copied().fold(f64::NEG_INFINITY, f64::max);
    let mean = kept.iter().sum::<f64>() / kept.len() as f64;
    Ok(Some(SurprisalStats { min, max, mean }))
}

fn probe_symbolic_fit(program: &ScirProgram, epoch: u64, candidate_hash: &str) -> Result<SgpFit> {
    let mut xs = Vec::<f64>::with_capacity(PROBE_SAMPLES);
    let mut ys = Vec::<f64>::with_capacity(PROBE_SAMPLES);
    for i in 0..PROBE_SAMPLES {
        let x = i as f64 / (PROBE_SAMPLES.saturating_sub(1).max(1)) as f64;
        let window = probe_window(program.input_len as usize, x);
        let trace = run_program(program, &window)?;
        let y = trace.feature.first().copied().unwrap_or(0.0_f32) as f64;
        xs.push(x);
        ys.push(y);
    }

    let mut target_x = Vec::<f64>::with_capacity(PROBE_SAMPLES.saturating_sub(1));
    let mut target_y = Vec::<f64>::with_capacity(PROBE_SAMPLES.saturating_sub(1));
    for i in 1..ys.len() {
        target_y.push(ys[i] - ys[i - 1]);
        target_x.push((xs[i] + xs[i - 1]) * 0.5);
    }

    let seed_hex = digest_json(&(
        epoch,
        candidate_hash,
        program.nodes.len(),
        program.input_len,
    ))?;
    let seed = u64::from_str_radix(&seed_hex[..16], 16).unwrap_or(0x51A2_79B4_0D7F_1234);
    let mut rng = ChaCha8Rng::seed_from_u64(seed);

    let mut current = SgpExpr::random(&mut rng, SGP_MAX_DEPTH / 2);
    let mut current_score = score_expr(&current, &target_x, &target_y);
    let mut best = current.clone();
    let mut best_score = current_score;
    let mut iterations = 0usize;

    for step in 0..SGP_STEPS {
        iterations = step + 1;
        let t = if SGP_STEPS <= 1 {
            SGP_TEMP_END
        } else {
            let frac = step as f64 / (SGP_STEPS - 1) as f64;
            (SGP_TEMP_START * (1.0 - frac) + SGP_TEMP_END * frac).max(1.0e-6)
        };
        let proposal = current.mutated(&mut rng, SGP_MAX_DEPTH);
        let proposal_score = score_expr(&proposal, &target_x, &target_y);
        let delta = proposal_score.mse - current_score.mse;
        let accept = if delta <= 0.0 {
            true
        } else {
            let p = (-delta / t).exp().clamp(0.0, 1.0);
            rng.gen::<f64>() < p
        };
        if accept {
            current = proposal.clone();
            current_score = proposal_score;
        }
        if proposal_score.mse < best_score.mse {
            best = proposal;
            best_score = proposal_score;
            if best_score.mse <= SGP_COMBINATORIAL_MSE_MAX {
                break;
            }
        }
    }

    Ok(SgpFit {
        equation: format!("dphi/dt = {}", best.to_symbolic(0)),
        mse: best_score.mse,
        r2: best_score.r2,
        combinatorially_proven: best_score.mse <= SGP_COMBINATORIAL_MSE_MAX,
        iterations,
    })
}

fn probe_window(len: usize, x: f64) -> Vec<u8> {
    let n = len.max(8);
    let phase = (x * std::f64::consts::TAU).sin();
    let mut out = vec![0u8; n];
    for (i, b) in out.iter_mut().enumerate() {
        let t = i as f64 / n as f64;
        let wave = ((phase + t * std::f64::consts::TAU).sin() * 0.5 + 0.5).clamp(0.0, 1.0);
        *b = (wave * 255.0).round() as u8;
    }
    out
}

fn score_expr(expr: &SgpExpr, xs: &[f64], ys: &[f64]) -> SgpScore {
    if xs.is_empty() || ys.is_empty() || xs.len() != ys.len() {
        return SgpScore {
            mse: f64::INFINITY,
            r2: -1.0,
        };
    }
    let mut ss_res = 0.0_f64;
    let mean_y = ys.iter().sum::<f64>() / ys.len() as f64;
    let mut ss_tot = 0.0_f64;
    for (&x, &y) in xs.iter().zip(ys.iter()) {
        let pred = expr.eval(x);
        let err = if pred.is_finite() { y - pred } else { 1.0e6 };
        ss_res += err * err;
        let centered = y - mean_y;
        ss_tot += centered * centered;
    }
    let mse = ss_res / ys.len() as f64;
    let r2 = if ss_tot <= 1.0e-12 {
        1.0
    } else {
        (1.0 - ss_res / ss_tot).clamp(-1.0, 1.0)
    };
    SgpScore { mse, r2 }
}

impl SgpExpr {
    fn random(rng: &mut ChaCha8Rng, depth: usize) -> Self {
        if depth == 0 {
            return if rng.gen_bool(0.5) {
                Self::Var
            } else {
                Self::Const(rng.gen_range(-2.0_f64..2.0_f64))
            };
        }
        match rng.gen_range(0..11) {
            0 => Self::Var,
            1 => Self::Const(rng.gen_range(-4.0_f64..4.0_f64)),
            2 => Self::Add(
                Box::new(Self::random(rng, depth - 1)),
                Box::new(Self::random(rng, depth - 1)),
            ),
            3 => Self::Sub(
                Box::new(Self::random(rng, depth - 1)),
                Box::new(Self::random(rng, depth - 1)),
            ),
            4 => Self::Mul(
                Box::new(Self::random(rng, depth - 1)),
                Box::new(Self::random(rng, depth - 1)),
            ),
            5 => Self::Div(
                Box::new(Self::random(rng, depth - 1)),
                Box::new(Self::random(rng, depth - 1)),
            ),
            6 => Self::Sin(Box::new(Self::random(rng, depth - 1))),
            7 => Self::Cos(Box::new(Self::random(rng, depth - 1))),
            8 => Self::Log(Box::new(Self::random(rng, depth - 1))),
            9 => Self::Exp(Box::new(Self::random(rng, depth - 1))),
            _ => Self::Step(Box::new(Self::random(rng, depth - 1))),
        }
    }

    fn mutated(&self, rng: &mut ChaCha8Rng, max_depth: usize) -> Self {
        let mut out = self.clone();
        if rng.gen_bool(0.25) {
            // Subtree replacement mutation.
            let repl_depth = rng.gen_range(1..=max_depth.max(1));
            let repl = Self::random(rng, repl_depth);
            out.replace_random_subtree(rng, repl);
            return out;
        }
        out.mutate_in_place(rng, max_depth, 0);
        if rng.gen_bool(0.2) {
            // Occasional topology growth.
            let right = Self::random(rng, max_depth / 2);
            out = match rng.gen_range(0..3) {
                0 => Self::Add(Box::new(out), Box::new(right)),
                1 => Self::Mul(Box::new(out), Box::new(right)),
                _ => Self::Sub(Box::new(out), Box::new(right)),
            };
        }
        out
    }

    fn eval(&self, x: f64) -> f64 {
        let v = match self {
            Self::Var => x,
            Self::Const(c) => *c,
            Self::Add(a, b) => a.eval(x) + b.eval(x),
            Self::Sub(a, b) => a.eval(x) - b.eval(x),
            Self::Mul(a, b) => a.eval(x) * b.eval(x),
            Self::Div(a, b) => {
                let den = b.eval(x);
                let safe = if den.abs() < 1.0e-6 {
                    if den.is_sign_negative() {
                        -1.0e-6
                    } else {
                        1.0e-6
                    }
                } else {
                    den
                };
                a.eval(x) / safe
            }
            Self::Sin(a) => a.eval(x).sin(),
            Self::Cos(a) => a.eval(x).cos(),
            Self::Log(a) => (a.eval(x).abs() + 1.0e-6).ln(),
            Self::Exp(a) => a.eval(x).clamp(-20.0, 20.0).exp(),
            Self::Step(a) => {
                if a.eval(x) >= 0.0 {
                    1.0
                } else {
                    0.0
                }
            }
        };
        if v.is_finite() {
            v.clamp(-1.0e6, 1.0e6)
        } else {
            0.0
        }
    }

    fn mutate_in_place(&mut self, rng: &mut ChaCha8Rng, max_depth: usize, depth: usize) {
        match self {
            Self::Const(c) => {
                if rng.gen_bool(0.8) {
                    *c += rng.gen_range(-0.5_f64..0.5_f64);
                } else {
                    *c = rng.gen_range(-4.0_f64..4.0_f64);
                }
            }
            Self::Var => {
                if rng.gen_bool(0.2) {
                    *self = Self::Const(rng.gen_range(-2.0_f64..2.0_f64));
                }
            }
            Self::Add(a, b) | Self::Sub(a, b) | Self::Mul(a, b) | Self::Div(a, b) => {
                if depth < max_depth && rng.gen_bool(0.5) {
                    a.mutate_in_place(rng, max_depth, depth + 1);
                } else if depth < max_depth {
                    b.mutate_in_place(rng, max_depth, depth + 1);
                }
                if rng.gen_bool(0.08) {
                    let lhs = (**a).clone();
                    let rhs = (**b).clone();
                    *self = match rng.gen_range(0..4) {
                        0 => Self::Add(Box::new(lhs), Box::new(rhs)),
                        1 => Self::Sub(Box::new(lhs), Box::new(rhs)),
                        2 => Self::Mul(Box::new(lhs), Box::new(rhs)),
                        _ => Self::Div(Box::new(lhs), Box::new(rhs)),
                    };
                }
            }
            Self::Sin(a) | Self::Cos(a) | Self::Log(a) | Self::Exp(a) | Self::Step(a) => {
                if depth < max_depth {
                    a.mutate_in_place(rng, max_depth, depth + 1);
                }
                if rng.gen_bool(0.12) {
                    let child = (**a).clone();
                    *self = match rng.gen_range(0..5) {
                        0 => Self::Sin(Box::new(child)),
                        1 => Self::Cos(Box::new(child)),
                        2 => Self::Log(Box::new(child)),
                        3 => Self::Exp(Box::new(child)),
                        _ => Self::Step(Box::new(child)),
                    };
                }
            }
        }
    }

    fn replace_random_subtree(&mut self, rng: &mut ChaCha8Rng, replacement: SgpExpr) {
        if rng.gen_bool(0.2) {
            *self = replacement;
            return;
        }
        match self {
            Self::Add(a, b) | Self::Sub(a, b) | Self::Mul(a, b) | Self::Div(a, b) => {
                if rng.gen_bool(0.5) {
                    a.replace_random_subtree(rng, replacement);
                } else {
                    b.replace_random_subtree(rng, replacement);
                }
            }
            Self::Sin(a) | Self::Cos(a) | Self::Log(a) | Self::Exp(a) | Self::Step(a) => {
                a.replace_random_subtree(rng, replacement)
            }
            Self::Var | Self::Const(_) => *self = replacement,
        }
    }

    fn to_symbolic(&self, depth: usize) -> String {
        if depth > 16 {
            return "x".to_string();
        }
        match self {
            Self::Var => "phi".to_string(),
            Self::Const(c) => format!("{c:.6}"),
            Self::Add(a, b) => format!(
                "({} + {})",
                a.to_symbolic(depth + 1),
                b.to_symbolic(depth + 1)
            ),
            Self::Sub(a, b) => format!(
                "({} - {})",
                a.to_symbolic(depth + 1),
                b.to_symbolic(depth + 1)
            ),
            Self::Mul(a, b) => format!(
                "({} * {})",
                a.to_symbolic(depth + 1),
                b.to_symbolic(depth + 1)
            ),
            Self::Div(a, b) => format!(
                "({} / ({} + 1e-6))",
                a.to_symbolic(depth + 1),
                b.to_symbolic(depth + 1)
            ),
            Self::Sin(a) => format!("sin({})", a.to_symbolic(depth + 1)),
            Self::Cos(a) => format!("cos({})", a.to_symbolic(depth + 1)),
            Self::Log(a) => format!("log(abs({}) + 1e-6)", a.to_symbolic(depth + 1)),
            Self::Exp(a) => format!("exp(clamp({}, -20, 20))", a.to_symbolic(depth + 1)),
            Self::Step(a) => format!("step({})", a.to_symbolic(depth + 1)),
        }
    }
}
