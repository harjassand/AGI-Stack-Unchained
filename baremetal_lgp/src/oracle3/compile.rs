use rand_chacha::ChaCha8Rng;
use rand_core::{RngCore, SeedableRng};
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Mutex, OnceLock};
use std::time::Instant;

use super::ast::{eval_program, AstEvalError};
use super::chunkpack::{compute_chunk_digest, ChunkPack, NumericSubstrate};
use super::cost::{compute_cost, CostViolation, EPS_DIV};
use super::spec::{spec_hash_32, InputDistSpec, RegimeSpec, ScheduleSegment};

pub const SPEC_VERSION: u32 = 3;
pub const MIN_META_U32_LEN: u32 = 16;
pub const MAX_META_U32_LEN: u32 = 16;
pub const MAX_META_F32_LEN: u32 = 16;
pub const MAX_INPUT_LEN: u32 = 4096;
pub const MAX_OUTPUT_LEN: u32 = 4096;

#[derive(Clone, Copy, Debug)]
pub struct CompileCfg {
    pub episode_count: u32,
    pub layout_words: u32,
    pub layout_attempts: u32,
}

pub const VALIDITY_COMPILE_CFG: CompileCfg = CompileCfg {
    episode_count: 12,
    layout_words: 16384,
    layout_attempts: 32,
};

pub const FULL_COMPILE_CFG: CompileCfg = CompileCfg {
    episode_count: 128,
    layout_words: 16384,
    layout_attempts: 32,
};

#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct AlienJitSynthesisProfile {
    pub calls: u64,
    pub total_ms: u64,
    pub last_ms: u64,
}

static ALIEN_JIT_SYNTHESIS_CALLS: AtomicU64 = AtomicU64::new(0);
static ALIEN_JIT_SYNTHESIS_TOTAL_MS: AtomicU64 = AtomicU64::new(0);
static ALIEN_JIT_SYNTHESIS_LAST_MS: AtomicU64 = AtomicU64::new(0);
static ALIEN_JIT_BLOB_CACHE: OnceLock<Mutex<BTreeMap<String, AlienJitBlob>>> = OnceLock::new();

pub fn alien_jit_synthesis_profile() -> AlienJitSynthesisProfile {
    AlienJitSynthesisProfile {
        calls: ALIEN_JIT_SYNTHESIS_CALLS.load(Ordering::Relaxed),
        total_ms: ALIEN_JIT_SYNTHESIS_TOTAL_MS.load(Ordering::Relaxed),
        last_ms: ALIEN_JIT_SYNTHESIS_LAST_MS.load(Ordering::Relaxed),
    }
}

fn jit_blob_cache() -> &'static Mutex<BTreeMap<String, AlienJitBlob>> {
    ALIEN_JIT_BLOB_CACHE.get_or_init(|| Mutex::new(BTreeMap::new()))
}

fn validate_seed_record_for_jit(seed_record: &AlienSeedRecord) -> std::result::Result<(), String> {
    let fused = effective_fused_ops(seed_record);
    if seed_record.seed_hash.trim().is_empty() {
        return Err("missing_seed_hash".to_string());
    }
    if fused > 16_384 {
        return Err(format!("excessive_bond_dimension:{fused}"));
    }
    if seed_record.max_fixpoint_iters == 0 {
        return Err("zero_fixpoint_iters".to_string());
    }
    if seed_record.max_fixpoint_iters > 1_048_576 {
        return Err(format!(
            "excessive_fixpoint_iters:{}",
            seed_record.max_fixpoint_iters
        ));
    }
    if !seed_record.epsilon.is_finite() || seed_record.epsilon <= 0.0 {
        return Err("invalid_epsilon".to_string());
    }
    Ok(())
}

pub fn synthesize_alien_jit_blob_cached(
    ast_hash: &str,
    seed_record: &AlienSeedRecord,
) -> std::result::Result<AlienJitBlob, String> {
    if ast_hash.trim().is_empty() {
        return Err("missing_ast_hash".to_string());
    }
    if let Some(hit) = {
        let guard = jit_blob_cache().lock().unwrap_or_else(|e| e.into_inner());
        guard.get(ast_hash).cloned()
    } {
        return Ok(hit);
    }
    validate_seed_record_for_jit(seed_record)?;
    let blob = synthesize_alien_jit_blob_from_seed(seed_record);
    {
        let mut guard = jit_blob_cache().lock().unwrap_or_else(|e| e.into_inner());
        guard.insert(ast_hash.to_string(), blob.clone());
    }
    Ok(blob)
}

#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub enum AlienTargetObjective {
    TemporalPrediction,
    EigenvalueApproximation,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct AlienJitBlob {
    pub alien_hash: String,
    #[serde(default)]
    pub seed_hash: String,
    #[serde(default = "default_alien_isa")]
    pub isa: String,
    pub fused_op_count: u32,
    #[serde(default = "default_alien_max_fixpoint_iters")]
    pub max_fixpoint_iters: u32,
    #[serde(default = "default_alien_epsilon")]
    pub epsilon: f32,
    #[serde(default)]
    pub simd_enabled: bool,
    #[serde(default = "default_alien_simd_lane_bytes")]
    pub simd_lane_bytes: u32,
    #[serde(default)]
    pub self_mutating: bool,
    #[serde(default)]
    pub aleph_mode: bool,
    #[serde(default = "default_alien_target_objective")]
    pub target_objective: AlienTargetObjective,
    #[serde(default)]
    pub objective_note: String,
    pub blob_hash: String,
    pub blob_bytes: Vec<u8>,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct AlienSeedRecord {
    pub seed_hash: String,
    #[serde(default)]
    pub ops_added: Vec<String>,
    #[serde(default)]
    pub ops_removed: Vec<String>,
    #[serde(default)]
    pub fused_ops_hint: u32,
    #[serde(default)]
    pub compile_seed: u64,
    #[serde(default = "default_alien_max_fixpoint_iters")]
    pub max_fixpoint_iters: u32,
    #[serde(default = "default_alien_epsilon")]
    pub epsilon: f32,
}

fn default_alien_isa() -> String {
    "aarch64-fused-opaque-v2".to_string()
}

fn default_alien_max_fixpoint_iters() -> u32 {
    64
}

fn default_alien_epsilon() -> f32 {
    1.0 / 1024.0
}

fn default_alien_simd_lane_bytes() -> u32 {
    16
}

fn default_alien_target_objective() -> AlienTargetObjective {
    AlienTargetObjective::TemporalPrediction
}

fn effective_fused_ops(record: &AlienSeedRecord) -> u32 {
    let structural = record
        .ops_added
        .len()
        .saturating_add(record.ops_removed.len()) as u32;
    structural.max(record.fused_ops_hint).max(1)
}

fn alien_seed_digest(record: &AlienSeedRecord) -> String {
    let mut h = blake3::Hasher::new();
    h.update(record.seed_hash.as_bytes());
    h.update(&record.compile_seed.to_le_bytes());
    h.update(&effective_fused_ops(record).to_le_bytes());
    h.update(&record.max_fixpoint_iters.max(1).to_le_bytes());
    h.update(&record.epsilon.to_le_bytes());
    for op in &record.ops_added {
        h.update(&[0xA1]);
        h.update(op.as_bytes());
    }
    for op in &record.ops_removed {
        h.update(&[0xB2]);
        h.update(op.as_bytes());
    }
    h.finalize().to_hex().to_string()
}

fn seed_has_tag(record: &AlienSeedRecord, mut pred: impl FnMut(&str) -> bool) -> bool {
    record
        .ops_added
        .iter()
        .chain(record.ops_removed.iter())
        .any(|s| pred(&s.to_ascii_lowercase()))
}

fn seed_requests_simd(record: &AlienSeedRecord) -> bool {
    seed_has_tag(record, |t| {
        t.contains("int4")
            || t.contains("int2")
            || t.contains("posit")
            || t.contains("neon")
            || t.contains("simd")
    })
}

fn seed_requests_self_mutate(record: &AlienSeedRecord) -> bool {
    seed_has_tag(record, |t| {
        t.contains("self-mutate")
            || t.contains("self_mutate")
            || t.contains("intralayer_mutation")
            || t.contains("jit_morph")
            || t.contains("opcode[self-mutate]")
    })
}

fn seed_requests_aleph_zero(record: &AlienSeedRecord) -> bool {
    seed_has_tag(record, |t| {
        t.contains("alephzero")
            || t.contains("aleph_zero")
            || t.contains("fractal")
            || t.contains("logistic_map")
            || t.contains("cellular_automaton")
    })
}

fn seed_requests_class_m(record: &AlienSeedRecord) -> bool {
    seed_has_tag(record, |t| {
        t.contains("classm")
            || t.contains("class_m")
            || t.contains("material")
            || t.contains("superconductor")
            || t.contains("lattice")
    })
}

fn seed_requests_eigen_oracle(record: &AlienSeedRecord) -> bool {
    seed_has_tag(record, |t| {
        t.contains("eigen")
            || t.contains("groundstate")
            || t.contains("ground_state")
            || t.contains("wavefunction")
            || t.contains("hamiltonian")
            || t.contains("no temporal rollout")
            || t.contains("notemporal")
    })
}

fn seed_target_objective(record: &AlienSeedRecord) -> AlienTargetObjective {
    if seed_requests_eigen_oracle(record) || seed_requests_class_m(record) {
        AlienTargetObjective::EigenvalueApproximation
    } else {
        AlienTargetObjective::TemporalPrediction
    }
}

#[cfg(all(target_os = "macos", target_arch = "aarch64"))]
unsafe extern "C" {
    fn pthread_jit_write_protect_np(enabled: libc::c_int);
}

fn with_macos_jit_write_window(f: impl FnOnce()) {
    #[cfg(all(target_os = "macos", target_arch = "aarch64"))]
    unsafe {
        pthread_jit_write_protect_np(0);
        f();
        pthread_jit_write_protect_np(1);
    }
    #[cfg(not(all(target_os = "macos", target_arch = "aarch64")))]
    {
        f();
    }
}

fn apply_polymorphic_self_mutation(
    out: &mut [u8],
    seed_record: &AlienSeedRecord,
    basis: &[u8; 32],
) -> bool {
    if out.is_empty() || !seed_requests_self_mutate(seed_record) {
        return false;
    }
    let budget = effective_fused_ops(seed_record).clamp(1, 64) as usize;
    let seed_mix = seed_record.compile_seed ^ (seed_record.max_fixpoint_iters as u64);
    with_macos_jit_write_window(|| {
        for i in 0..budget {
            let step = (seed_mix as usize)
                .wrapping_add(i.wrapping_mul(37))
                .wrapping_add((basis[i % basis.len()] as usize).wrapping_mul(13));
            let ix = step % out.len();
            let iy =
                (ix + (basis[(i.wrapping_mul(5)) % basis.len()] as usize % 17) + 1) % out.len();
            let mask = basis[(i.wrapping_mul(11) + 7) % basis.len()]
                ^ ((seed_mix.rotate_left((i % 31) as u32) & 0xFF) as u8);
            out[ix] ^= mask;
            if i % 3 == 0 {
                out.swap(ix, iy);
            }
            if i % 5 == 0 {
                out[iy] = out[iy].rotate_left(((i % 7) + 1) as u32);
            }
        }
    });
    true
}

fn apply_eigenstate_oracle_bias(out: &mut [u8], basis: &[u8; 32], fused_ops: u32) {
    if out.is_empty() {
        return;
    }
    let n = out.len();
    let mut psi = vec![0.0_f32; n];
    for i in 0..n {
        let b = basis[i % basis.len()] as f32 / 255.0;
        psi[i] = (2.0 * b - 1.0).tanh();
    }

    let iters = fused_ops.clamp(4, 24) as usize;
    let coupling = 0.12 + (fused_ops.min(64) as f32 / 64.0) * 0.18;
    for _ in 0..iters {
        let mut next = vec![0.0_f32; n];
        for i in 0..n {
            let left = psi[(i + n - 1) % n];
            let center = psi[i];
            let right = psi[(i + 1) % n];
            let diag = 0.60 + (basis[(i.wrapping_mul(7) + 3) % basis.len()] as f32 / 255.0) * 0.30;
            next[i] = (diag * center + coupling * 0.5 * (left + right)).tanh();
        }
        let norm = next.iter().map(|v| v * v).sum::<f32>().sqrt().max(1.0e-6);
        for v in &mut next {
            *v /= norm;
        }
        psi = next;
    }

    for (i, lane) in out.iter_mut().enumerate() {
        let amp = ((psi[i] * 0.5 + 0.5).clamp(0.0, 1.0) * 255.0) as u8;
        let phase = basis[(i.wrapping_mul(3) + 11) % basis.len()].rotate_left(((i % 7) + 1) as u32);
        *lane ^= amp ^ phase;
        if i % 11 == 0 {
            *lane = lane.rotate_left(1);
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub enum CompileError {
    InvalidVersion {
        got: u32,
        expected: u32,
    },
    CostViolation(CostViolation),
    MetaF32TooShort {
        meta_f32_len: u32,
        episode_param_count: u32,
    },
    MetaU32TooShort {
        meta_u32_len: u32,
        min_required: u32,
    },
    MetaU32TooLarge {
        meta_u32_len: u32,
        max_supported: u32,
    },
    MetaF32TooLarge {
        meta_f32_len: u32,
        max_supported: u32,
    },
    InputLenOutOfRange {
        input_len: u32,
        max_supported: u32,
    },
    OutputLenOutOfRange {
        output_len: u32,
        max_supported: u32,
    },
    InvalidScheduleSegment {
        index: usize,
        start_episode: u32,
        end_episode: u32,
    },
    OverlappingScheduleSegment {
        prev_index: usize,
        next_index: usize,
    },
    LayoutTooSmall {
        layout_words: u32,
        needed_words: u32,
    },
    Ast(AstEvalError),
    NonFiniteTarget {
        episode: u32,
    },
}

pub fn synthesize_alien_jit_blob(alien_hash: &str, fused_op_count: u32, seed: u64) -> AlienJitBlob {
    let seed_record = AlienSeedRecord {
        seed_hash: alien_hash.to_string(),
        ops_added: Vec::new(),
        ops_removed: Vec::new(),
        fused_ops_hint: fused_op_count,
        compile_seed: seed,
        max_fixpoint_iters: default_alien_max_fixpoint_iters(),
        epsilon: default_alien_epsilon(),
    };
    synthesize_alien_jit_blob_from_seed(&seed_record)
}

pub fn synthesize_alien_jit_blob_from_seed(seed_record: &AlienSeedRecord) -> AlienJitBlob {
    let started = Instant::now();
    // Deterministic pseudo-JIT payload used as a reproducible fused-kernel stand-in.
    let fused_op_count = effective_fused_ops(seed_record);
    let alien_hash = alien_seed_digest(seed_record);
    let target_objective = seed_target_objective(seed_record);
    let eigen_objective = matches!(
        target_objective,
        AlienTargetObjective::EigenvalueApproximation
    );
    let mut out =
        Vec::with_capacity((64 + fused_op_count.saturating_mul(8)).clamp(64, 512) as usize);
    let mut h = blake3::Hasher::new();
    h.update(alien_hash.as_bytes());
    h.update(seed_record.seed_hash.as_bytes());
    h.update(&seed_record.compile_seed.to_le_bytes());
    h.update(&fused_op_count.to_le_bytes());
    h.update(&seed_record.max_fixpoint_iters.max(1).to_le_bytes());
    h.update(&seed_record.epsilon.to_le_bytes());
    let simd_enabled = seed_requests_simd(seed_record);
    let aleph_mode = seed_requests_aleph_zero(seed_record) || eigen_objective;
    let simd_lane_bytes = if simd_enabled { 16 } else { 1 };
    h.update(&[simd_enabled as u8]);
    h.update(&[aleph_mode as u8]);
    h.update(&[eigen_objective as u8]);
    h.update(&(simd_lane_bytes as u32).to_le_bytes());
    let basis = *h.finalize().as_bytes();
    let mut blob_len = if eigen_objective {
        (128 + fused_op_count.saturating_mul(24)).clamp(128, 1024)
    } else if aleph_mode {
        (96 + fused_op_count.saturating_mul(16)).clamp(96, 768)
    } else {
        (64 + fused_op_count.saturating_mul(8)).clamp(64, 512)
    };
    if simd_enabled {
        let rem = blob_len % simd_lane_bytes;
        if rem != 0 {
            blob_len = blob_len.saturating_add(simd_lane_bytes - rem);
        }
    }
    for i in 0..blob_len {
        let base = basis[(i as usize) % basis.len()];
        let mix = if simd_enabled {
            // SIMD-friendly pattern: 16-byte lane splats plus deterministic MAC-like phase.
            let lane_ix = i % simd_lane_bytes;
            let lane_base = basis[(lane_ix as usize) % basis.len()];
            let mac = i
                .wrapping_mul(17)
                .wrapping_add(fused_op_count.wrapping_mul(3))
                .wrapping_add((lane_ix + 1).wrapping_mul(11));
            lane_base ^ ((mac & 0xFF) as u8)
        } else {
            ((i.wrapping_mul(29).wrapping_add(fused_op_count)) & 0xFF) as u8
        };
        out.push(base ^ mix);
    }
    let self_mutating = apply_polymorphic_self_mutation(&mut out, seed_record, &basis);
    if eigen_objective {
        apply_eigenstate_oracle_bias(&mut out, &basis, fused_op_count);
    }
    let max_fixpoint_iters = if eigen_objective {
        seed_record.max_fixpoint_iters.max(512)
    } else if aleph_mode {
        seed_record.max_fixpoint_iters.max(256)
    } else {
        seed_record.max_fixpoint_iters.max(1)
    };

    let blob_hash = blake3::hash(&out).to_hex().to_string();
    let out_blob = AlienJitBlob {
        alien_hash,
        seed_hash: seed_record.seed_hash.clone(),
        isa: if eigen_objective && simd_enabled {
            "aarch64-fused-opaque-v2-eigen-neon16".to_string()
        } else if eigen_objective {
            "aarch64-fused-opaque-v2-eigen".to_string()
        } else if aleph_mode && simd_enabled {
            "aarch64-fused-opaque-v2-aleph-neon16".to_string()
        } else if aleph_mode {
            "aarch64-fused-opaque-v2-aleph".to_string()
        } else if simd_enabled {
            "aarch64-fused-opaque-v2-neon16".to_string()
        } else {
            default_alien_isa()
        },
        fused_op_count,
        max_fixpoint_iters,
        epsilon: seed_record.epsilon,
        simd_enabled,
        simd_lane_bytes,
        self_mutating,
        aleph_mode,
        target_objective,
        objective_note: if eigen_objective {
            "Class-M objective shifted to EigenvalueApproximation (ground-state eigenvector oracle)"
                .to_string()
        } else {
            "TemporalPrediction objective".to_string()
        },
        blob_hash,
        blob_bytes: out,
    };
    let elapsed_ms = started.elapsed().as_millis().min(u128::from(u64::MAX)) as u64;
    ALIEN_JIT_SYNTHESIS_CALLS.fetch_add(1, Ordering::Relaxed);
    ALIEN_JIT_SYNTHESIS_TOTAL_MS.fetch_add(elapsed_ms, Ordering::Relaxed);
    ALIEN_JIT_SYNTHESIS_LAST_MS.store(elapsed_ms, Ordering::Relaxed);
    out_blob
}

impl From<CostViolation> for CompileError {
    fn from(value: CostViolation) -> Self {
        Self::CostViolation(value)
    }
}

pub fn compile_chunkpack(
    spec: &RegimeSpec,
    compile_seed: u64,
    cfg: CompileCfg,
) -> Result<ChunkPack, CompileError> {
    if spec.version != SPEC_VERSION {
        return Err(CompileError::InvalidVersion {
            got: spec.version,
            expected: SPEC_VERSION,
        });
    }

    let _cost = compute_cost(spec)?;

    if spec.meta_f32_len < spec.episode_param_count {
        return Err(CompileError::MetaF32TooShort {
            meta_f32_len: spec.meta_f32_len,
            episode_param_count: spec.episode_param_count,
        });
    }
    if spec.meta_u32_len < MIN_META_U32_LEN {
        return Err(CompileError::MetaU32TooShort {
            meta_u32_len: spec.meta_u32_len,
            min_required: MIN_META_U32_LEN,
        });
    }
    if spec.meta_u32_len > MAX_META_U32_LEN {
        return Err(CompileError::MetaU32TooLarge {
            meta_u32_len: spec.meta_u32_len,
            max_supported: MAX_META_U32_LEN,
        });
    }
    if spec.meta_f32_len > MAX_META_F32_LEN {
        return Err(CompileError::MetaF32TooLarge {
            meta_f32_len: spec.meta_f32_len,
            max_supported: MAX_META_F32_LEN,
        });
    }
    if spec.input_len == 0 || spec.input_len > MAX_INPUT_LEN {
        return Err(CompileError::InputLenOutOfRange {
            input_len: spec.input_len,
            max_supported: MAX_INPUT_LEN,
        });
    }
    if spec.output_len == 0 || spec.output_len > MAX_OUTPUT_LEN {
        return Err(CompileError::OutputLenOutOfRange {
            output_len: spec.output_len,
            max_supported: MAX_OUTPUT_LEN,
        });
    }

    validate_schedule(spec, cfg.episode_count)?;

    let spec_hash = spec_hash_32(spec);

    let input_stride = spec.input_len as usize;
    let output_stride = spec.output_len as usize;
    let meta_u32_stride = spec.meta_u32_len as usize;
    let meta_f32_stride = spec.meta_f32_len as usize;

    let mut inputs = vec![0.0_f32; cfg.episode_count as usize * input_stride];
    let mut targets = vec![0.0_f32; cfg.episode_count as usize * output_stride];
    let mut meta_u32 = vec![0_u32; cfg.episode_count as usize * meta_u32_stride];
    let mut meta_f32 = vec![0.0_f32; cfg.episode_count as usize * meta_f32_stride];

    for ep in 0..cfg.episode_count {
        let mut rng = episode_rng(spec_hash, compile_seed, ep);
        let seg = active_segment(spec, ep);

        let meta_start = ep as usize * meta_f32_stride;
        let meta_slice = &mut meta_f32[meta_start..meta_start + meta_f32_stride];
        sample_meta_params(
            meta_slice,
            spec.episode_param_count as usize,
            seg.param_scale,
            &mut rng,
        );

        let input_start = ep as usize * input_stride;
        let input_slice = &mut inputs[input_start..input_start + input_stride];
        sample_input(input_slice, &spec.input_dist, seg.input_scale, &mut rng);

        let layout = allocate_layout(
            spec.input_len,
            spec.output_len,
            cfg.layout_words,
            cfg.layout_attempts,
            &mut rng,
        )?;

        let meta_u32_start = ep as usize * meta_u32_stride;
        let meta_u32_slice = &mut meta_u32[meta_u32_start..meta_u32_start + meta_u32_stride];
        write_meta_u32_schema(meta_u32_slice, layout, spec.input_len, spec.output_len, ep);

        let target = eval_program(
            &spec.ast,
            input_slice,
            meta_slice,
            spec.input_len,
            spec.output_len,
            EPS_DIV,
        )
        .map_err(CompileError::Ast)?;

        if target.iter().any(|v| !v.is_finite()) {
            return Err(CompileError::NonFiniteTarget { episode: ep });
        }

        let target_start = ep as usize * output_stride;
        targets[target_start..target_start + output_stride].copy_from_slice(&target);
    }

    let mut chunk = ChunkPack {
        spec_hash,
        compile_seed,
        episode_count: cfg.episode_count,
        numeric_substrate: NumericSubstrate::Fp32,
        input_len: spec.input_len,
        output_len: spec.output_len,
        meta_u32_len: spec.meta_u32_len,
        meta_f32_len: spec.meta_f32_len,
        inputs,
        targets,
        meta_u32,
        meta_f32,
        digest: [0_u8; 32],
    };
    chunk.digest = compute_chunk_digest(&chunk);
    Ok(chunk)
}

#[derive(Clone, Copy)]
struct Layout {
    in_base_word: u32,
    out_base_word: u32,
    work_base_word: u32,
    work_len_words: u32,
}

fn allocate_layout(
    input_len: u32,
    output_len: u32,
    layout_words: u32,
    attempts: u32,
    rng: &mut ChaCha8Rng,
) -> Result<Layout, CompileError> {
    let work_len_words = input_len.saturating_add(output_len).saturating_mul(2);
    let needed_words = input_len
        .saturating_add(output_len)
        .saturating_add(work_len_words);
    if needed_words > layout_words {
        return Err(CompileError::LayoutTooSmall {
            layout_words,
            needed_words,
        });
    }

    let align = 64_u32;
    for _ in 0..attempts.max(1) {
        let in_base = sample_aligned_base(layout_words, input_len, align, rng);
        let out_base = sample_aligned_base(layout_words, output_len, align, rng);
        let work_base = sample_aligned_base(layout_words, work_len_words, align, rng);

        if !overlaps(in_base, input_len, out_base, output_len)
            && !overlaps(in_base, input_len, work_base, work_len_words)
            && !overlaps(out_base, output_len, work_base, work_len_words)
        {
            return Ok(Layout {
                in_base_word: in_base,
                out_base_word: out_base,
                work_base_word: work_base,
                work_len_words,
            });
        }
    }

    // Deterministic fallback.
    let in_base_word = 0_u32;
    let out_base_word = align_up(input_len, align);
    let work_base_word = align_up(out_base_word.saturating_add(output_len), align);
    let end = work_base_word.saturating_add(work_len_words);
    if end > layout_words {
        return Err(CompileError::LayoutTooSmall {
            layout_words,
            needed_words: end,
        });
    }

    Ok(Layout {
        in_base_word,
        out_base_word,
        work_base_word,
        work_len_words,
    })
}

fn sample_aligned_base(layout_words: u32, len: u32, align: u32, rng: &mut ChaCha8Rng) -> u32 {
    if len >= layout_words {
        return 0;
    }
    let max_start = layout_words.saturating_sub(len);
    let slots = max_start / align + 1;
    let slot = (rng.next_u32() % slots.max(1)) as u32;
    slot.saturating_mul(align)
}

fn align_up(value: u32, align: u32) -> u32 {
    if align == 0 {
        return value;
    }
    let rem = value % align;
    if rem == 0 {
        value
    } else {
        value.saturating_add(align - rem)
    }
}

fn overlaps(a_base: u32, a_len: u32, b_base: u32, b_len: u32) -> bool {
    a_base < b_base.saturating_add(b_len) && b_base < a_base.saturating_add(a_len)
}

fn write_meta_u32_schema(
    meta_u32: &mut [u32],
    layout: Layout,
    input_len: u32,
    output_len: u32,
    episode_index: u32,
) {
    meta_u32.fill(0);
    meta_u32[0] = layout.in_base_word;
    meta_u32[1] = layout.out_base_word;
    meta_u32[2] = layout.work_base_word;
    meta_u32[3] = input_len;
    meta_u32[4] = output_len;
    meta_u32[5] = layout.work_len_words;
    meta_u32[6] = episode_index;
    meta_u32[7] = 0;
}

fn sample_meta_params(out: &mut [f32], count: usize, scale: f32, rng: &mut ChaCha8Rng) {
    for slot in out.iter_mut() {
        *slot = 0.0;
    }
    let n = count.min(out.len());
    for slot in out.iter_mut().take(n) {
        let u = (rng.next_u32() as f64) / ((u32::MAX as f64) + 1.0);
        *slot = ((u as f32) * 2.0 - 1.0) * scale;
    }
}

fn sample_input(out: &mut [f32], dist: &InputDistSpec, scale: f32, rng: &mut ChaCha8Rng) {
    for slot in out.iter_mut() {
        let sampled = match *dist {
            InputDistSpec::Uniform { lo, hi } => {
                let u = (rng.next_u32() as f64) / ((u32::MAX as f64) + 1.0);
                lo + (hi - lo) * u as f32
            }
            InputDistSpec::Normal { mean, std } => {
                let u1 = ((rng.next_u32() as f64) / ((u32::MAX as f64) + 1.0)).max(f64::EPSILON);
                let u2 = (rng.next_u32() as f64) / ((u32::MAX as f64) + 1.0);
                let z = (-2.0 * u1.ln()).sqrt() * (std::f64::consts::TAU * u2).cos();
                mean + std * z as f32
            }
            InputDistSpec::Rademacher { scale: r_scale } => {
                if (rng.next_u32() & 1) == 0 {
                    -r_scale
                } else {
                    r_scale
                }
            }
        };
        *slot = sampled * scale;
    }
}

fn episode_rng(spec_hash: [u8; 32], compile_seed: u64, episode: u32) -> ChaCha8Rng {
    let mut hasher = blake3::Hasher::new();
    hasher.update(&spec_hash);
    hasher.update(&compile_seed.to_le_bytes());
    hasher.update(&episode.to_le_bytes());
    let digest = hasher.finalize();
    let digest_bytes = digest.as_bytes();
    let episode_seed = u64::from_le_bytes(digest_bytes[0..8].try_into().unwrap_or([0_u8; 8]));

    let seed_digest = blake3::hash(&episode_seed.to_le_bytes());
    let mut seed = [0_u8; 32];
    seed.copy_from_slice(seed_digest.as_bytes());
    ChaCha8Rng::from_seed(seed)
}

fn validate_schedule(spec: &RegimeSpec, episode_count: u32) -> Result<(), CompileError> {
    let mut prev: Option<(usize, &ScheduleSegment)> = None;
    for (idx, seg) in spec.schedule.segments.iter().enumerate() {
        if seg.start_episode >= seg.end_episode || seg.end_episode > episode_count {
            return Err(CompileError::InvalidScheduleSegment {
                index: idx,
                start_episode: seg.start_episode,
                end_episode: seg.end_episode,
            });
        }
        if let Some((prev_idx, prev_seg)) = prev {
            if seg.start_episode < prev_seg.end_episode {
                return Err(CompileError::OverlappingScheduleSegment {
                    prev_index: prev_idx,
                    next_index: idx,
                });
            }
        }
        prev = Some((idx, seg));
    }
    Ok(())
}

fn active_segment(spec: &RegimeSpec, episode: u32) -> ScheduleSegment {
    for seg in &spec.schedule.segments {
        if episode >= seg.start_episode && episode < seg.end_episode {
            return seg.clone();
        }
    }
    ScheduleSegment {
        start_episode: 0,
        end_episode: u32::MAX,
        param_scale: 1.0,
        input_scale: 1.0,
    }
}

#[cfg(test)]
mod tests {
    use super::{synthesize_alien_jit_blob_from_seed, AlienSeedRecord, AlienTargetObjective};

    #[test]
    fn class_m_seed_switches_to_eigen_objective() {
        let seed = AlienSeedRecord {
            seed_hash: "seed".to_string(),
            ops_added: vec![
                "ClassM::Objective::EigenvalueApproximation".to_string(),
                "ClassM::Oracle::GroundStateEigenvector".to_string(),
            ],
            ops_removed: vec!["TemporalRollout::T_to_Tplus1".to_string()],
            fused_ops_hint: 12,
            compile_seed: 7,
            max_fixpoint_iters: 64,
            epsilon: 1.0 / 1024.0,
        };
        let blob = synthesize_alien_jit_blob_from_seed(&seed);
        assert_eq!(
            blob.target_objective,
            AlienTargetObjective::EigenvalueApproximation
        );
        assert!(blob.max_fixpoint_iters >= 512);
        assert!(blob.isa.contains("eigen"));
    }

    #[test]
    fn default_seed_keeps_temporal_objective() {
        let seed = AlienSeedRecord {
            seed_hash: "seed".to_string(),
            ops_added: vec!["generic_op".to_string()],
            ops_removed: vec![],
            fused_ops_hint: 4,
            compile_seed: 9,
            max_fixpoint_iters: 64,
            epsilon: 1.0 / 1024.0,
        };
        let blob = synthesize_alien_jit_blob_from_seed(&seed);
        assert_eq!(
            blob.target_objective,
            AlienTargetObjective::TemporalPrediction
        );
    }
}
