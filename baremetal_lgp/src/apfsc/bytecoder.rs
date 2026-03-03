use std::collections::BTreeMap;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::Instant;

use serde::{Deserialize, Serialize};

use crate::apfsc::bank::{window_bytes, window_target};
use crate::apfsc::emission::{bits_for_target, emit_freq_u16};
use crate::apfsc::errors::{ApfscError, Result};
use crate::apfsc::headpack::apply_linear;
use crate::apfsc::scir::ast::{ScirOp, ScirProgram};
use crate::apfsc::types::{HeadPack, WindowRef};
use crate::oracle3::compile::{
    synthesize_alien_jit_blob_cached, AlienJitBlob, AlienSeedRecord,
};

const JIT_COMPILE_FAIL_BITS_PER_WINDOW: f64 = 1.0e9;
const DE_EVOLUTION_FAIL_BITS_PER_WINDOW: f64 = 1.0e9;

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
pub struct CandidateEvaluateProfile {
    pub calls: u64,
    pub total_ms: u64,
    pub last_ms: u64,
}

static CANDIDATE_EVALUATE_CALLS: AtomicU64 = AtomicU64::new(0);
static CANDIDATE_EVALUATE_TOTAL_MS: AtomicU64 = AtomicU64::new(0);
static CANDIDATE_EVALUATE_LAST_MS: AtomicU64 = AtomicU64::new(0);

pub fn candidate_evaluate_profile() -> CandidateEvaluateProfile {
    CandidateEvaluateProfile {
        calls: CANDIDATE_EVALUATE_CALLS.load(Ordering::Relaxed),
        total_ms: CANDIDATE_EVALUATE_TOTAL_MS.load(Ordering::Relaxed),
        last_ms: CANDIDATE_EVALUATE_LAST_MS.load(Ordering::Relaxed),
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ScoreSummary {
    pub family_scores_bits: BTreeMap<String, f64>,
    pub total_bits: f64,
    pub mean_bits_per_byte: f64,
    pub replay_hash: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct WindowScore {
    pub start: u64,
    pub target: u8,
    pub bits: f64,
}

pub fn score_panel(
    program: &ScirProgram,
    heads: &HeadPack,
    payloads_by_seq_hash: &BTreeMap<String, Vec<u8>>,
    windows: &[WindowRef],
) -> Result<ScoreSummary> {
    score_panel_with_resid_scales(program, heads, None, payloads_by_seq_hash, windows)
}

pub fn score_panel_with_resid_scales(
    program: &ScirProgram,
    heads: &HeadPack,
    resid_scales: Option<&[f32]>,
    payloads_by_seq_hash: &BTreeMap<String, Vec<u8>>,
    windows: &[WindowRef],
) -> Result<ScoreSummary> {
    let started = Instant::now();
    if windows.is_empty() {
        let out = ScoreSummary {
            family_scores_bits: BTreeMap::new(),
            total_bits: 0.0,
            mean_bits_per_byte: 0.0,
            replay_hash: crate::apfsc::artifacts::digest_bytes(b"empty_panel"),
        };
        let elapsed_ms = started.elapsed().as_millis().min(u128::from(u64::MAX)) as u64;
        CANDIDATE_EVALUATE_CALLS.fetch_add(1, Ordering::Relaxed);
        CANDIDATE_EVALUATE_TOTAL_MS.fetch_add(elapsed_ms, Ordering::Relaxed);
        CANDIDATE_EVALUATE_LAST_MS.store(elapsed_ms, Ordering::Relaxed);
        return Ok(out);
    }

    let forced_jit = if should_force_jit(program) {
        let ast_hash = crate::apfsc::artifacts::digest_json(program)?;
        let seed = build_jit_seed_record(program, &ast_hash);
        match synthesize_alien_jit_blob_cached(&ast_hash, &seed) {
            Ok(blob) => Some((blob, feature_out_dim(program))),
            Err(reason) => {
                let out = jit_compile_fail_summary(windows, &reason);
                let elapsed_ms = started.elapsed().as_millis().min(u128::from(u64::MAX)) as u64;
                CANDIDATE_EVALUATE_CALLS.fetch_add(1, Ordering::Relaxed);
                CANDIDATE_EVALUATE_TOTAL_MS.fetch_add(elapsed_ms, Ordering::Relaxed);
                CANDIDATE_EVALUATE_LAST_MS.store(elapsed_ms, Ordering::Relaxed);
                return Ok(out);
            }
        }
    } else {
        let out = de_evolution_detected_summary(windows);
        let elapsed_ms = started.elapsed().as_millis().min(u128::from(u64::MAX)) as u64;
        CANDIDATE_EVALUATE_CALLS.fetch_add(1, Ordering::Relaxed);
        CANDIDATE_EVALUATE_TOTAL_MS.fetch_add(elapsed_ms, Ordering::Relaxed);
        CANDIDATE_EVALUATE_LAST_MS.store(elapsed_ms, Ordering::Relaxed);
        return Ok(out);
    };
    let mut family_scores = BTreeMap::<String, f64>::new();
    let mut total_bits = 0.0f64;
    let mut replay_log = Vec::<WindowScore>::with_capacity(windows.len());

    for w in windows {
        let payload = payloads_by_seq_hash.get(&w.seq_hash).ok_or_else(|| {
            ApfscError::Missing(format!("missing payload seq_hash {}", w.seq_hash))
        })?;

        let input = window_bytes(payload, w)?;
        let target = window_target(payload, w)?;
        let (blob, out_dim) = forced_jit
            .as_ref()
            .expect("forced_jit must be present after DeEvolution fast-fail gate");
        let feature = jit_feature_from_blob(blob, input, *out_dim);
        let mut adapted = adapt_feature_dim(&feature, heads.native_head.in_dim as usize);
        if let Some(scales) = resid_scales {
            for (i, x) in adapted.iter_mut().enumerate() {
                if i < scales.len() {
                    *x *= 1.0 + scales[i];
                }
            }
        }

        // Force deterministic evaluation order of the native path.
        let _ = apply_linear(&heads.native_head, &adapted);
        let freq = emit_freq_u16(heads, &adapted);
        let bits = bits_for_target(&freq, target);
        total_bits += bits;
        *family_scores.entry(w.family_id.clone()).or_insert(0.0) += bits;
        replay_log.push(WindowScore {
            start: w.start,
            target,
            bits,
        });
    }

    let replay_hash = crate::apfsc::artifacts::digest_json(&replay_log)?;
    let out = ScoreSummary {
        family_scores_bits: family_scores,
        total_bits,
        mean_bits_per_byte: total_bits / windows.len() as f64,
        replay_hash,
    };
    let elapsed_ms = started.elapsed().as_millis().min(u128::from(u64::MAX)) as u64;
    CANDIDATE_EVALUATE_CALLS.fetch_add(1, Ordering::Relaxed);
    CANDIDATE_EVALUATE_TOTAL_MS.fetch_add(elapsed_ms, Ordering::Relaxed);
    CANDIDATE_EVALUATE_LAST_MS.store(elapsed_ms, Ordering::Relaxed);
    Ok(out)
}

fn should_force_jit(program: &ScirProgram) -> bool {
    program.nodes.iter().any(|node| match &node.op {
        ScirOp::AlephZero { .. } => true,
        ScirOp::Alien { mutation_vector, .. } => mutation_vector
            .ops_added
            .iter()
            .chain(mutation_vector.ops_removed.iter())
            .any(|tag| {
                let t = tag.to_ascii_lowercase();
                t.contains("classm")
                    || t.contains("class_m")
                    || t.contains("mera")
                    || t.contains("groundstateeigenvector")
                    || t.contains("demonlane")
            }),
        _ => false,
    })
}

fn feature_out_dim(program: &ScirProgram) -> usize {
    program
        .nodes
        .iter()
        .find(|n| n.id == program.outputs.feature_node)
        .map(|n| n.out_dim as usize)
        .unwrap_or(16)
        .max(1)
}

fn build_jit_seed_record(program: &ScirProgram, ast_hash: &str) -> AlienSeedRecord {
    let mut seed_hash = format!("ast:{ast_hash}");
    let mut ops_added = Vec::<String>::new();
    let mut ops_removed = Vec::<String>::new();
    let mut fused_ops_hint = 1u32;
    let mut max_aleph_depth = 0u32;

    for node in &program.nodes {
        match &node.op {
            ScirOp::Alien {
                seed_hash: alien_seed,
                mutation_vector,
                fused_ops_hint: hint,
            } => {
                if seed_hash.starts_with("ast:") && !alien_seed.is_empty() {
                    seed_hash = alien_seed.clone();
                }
                fused_ops_hint = fused_ops_hint.max(*hint);
                ops_added.extend(mutation_vector.ops_added.clone());
                ops_removed.extend(mutation_vector.ops_removed.clone());
            }
            ScirOp::AlephZero { recursion_depth } => {
                max_aleph_depth = max_aleph_depth.max(*recursion_depth);
            }
            _ => {}
        }
    }
    if max_aleph_depth > 0 {
        ops_added.push(format!("AlephZero::RecursionDepth::{max_aleph_depth}"));
        fused_ops_hint = fused_ops_hint.max(16);
    }
    let compile_seed = u64::from_str_radix(ast_hash.get(0..16).unwrap_or(ast_hash), 16).unwrap_or(0);
    let max_fixpoint_iters = max_aleph_depth.clamp(64, 4096).max(64);
    let epsilon = if max_aleph_depth > 0 {
        1.0 / 8192.0
    } else {
        1.0 / 1024.0
    };
    AlienSeedRecord {
        seed_hash,
        ops_added,
        ops_removed,
        fused_ops_hint,
        compile_seed,
        max_fixpoint_iters,
        epsilon,
    }
}

fn jit_feature_from_blob(blob: &AlienJitBlob, window: &[u8], out_dim: usize) -> Vec<f32> {
    if out_dim == 0 {
        return Vec::new();
    }
    let basis = if blob.blob_bytes.is_empty() {
        &[0u8][..]
    } else {
        blob.blob_bytes.as_slice()
    };
    let mut out = Vec::with_capacity(out_dim);
    for i in 0..out_dim {
        let b = basis[i % basis.len()];
        let w = if window.is_empty() {
            0
        } else {
            window[i % window.len()]
        };
        let mixed = (b ^ w).wrapping_add((i as u8).wrapping_mul(17));
        let v = (mixed as f32 / 255.0) * 2.0 - 1.0;
        out.push(v);
    }
    out
}

fn jit_compile_fail_summary(windows: &[WindowRef], reason: &str) -> ScoreSummary {
    let mut family_scores = BTreeMap::<String, f64>::new();
    let mut total_bits = 0.0f64;
    for w in windows {
        total_bits += JIT_COMPILE_FAIL_BITS_PER_WINDOW;
        *family_scores.entry(w.family_id.clone()).or_insert(0.0) += JIT_COMPILE_FAIL_BITS_PER_WINDOW;
    }
    ScoreSummary {
        family_scores_bits: family_scores,
        total_bits,
        mean_bits_per_byte: if windows.is_empty() {
            JIT_COMPILE_FAIL_BITS_PER_WINDOW
        } else {
            total_bits / windows.len() as f64
        },
        replay_hash: format!("Reject(JITCompileFail:{reason})"),
    }
}

fn de_evolution_detected_summary(windows: &[WindowRef]) -> ScoreSummary {
    let mut family_scores = BTreeMap::<String, f64>::new();
    let mut total_bits = 0.0f64;
    for w in windows {
        total_bits += DE_EVOLUTION_FAIL_BITS_PER_WINDOW;
        *family_scores.entry(w.family_id.clone()).or_insert(0.0) +=
            DE_EVOLUTION_FAIL_BITS_PER_WINDOW;
    }
    ScoreSummary {
        family_scores_bits: family_scores,
        total_bits,
        mean_bits_per_byte: if windows.is_empty() {
            DE_EVOLUTION_FAIL_BITS_PER_WINDOW
        } else {
            total_bits / windows.len() as f64
        },
        replay_hash: "Reject(DeEvolutionDetected)".to_string(),
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
