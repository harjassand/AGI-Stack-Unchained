use rand_chacha::ChaCha8Rng;
use rand_core::{RngCore, SeedableRng};

use super::ast::{eval_program, AstEvalError};
use super::chunkpack::{compute_chunk_digest, ChunkPack};
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
