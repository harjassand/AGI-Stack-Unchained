use super::{sample_len, usize_to_u32, EpisodeSpec, META_P0, META_SLOTS};
use crate::oracle::SplitMix64;

pub fn sample(rng: &mut SplitMix64, difficulty_weight: f32) -> EpisodeSpec {
    let l = sample_len(rng, 32, 384, difficulty_weight);
    let a = rng.range_f32(1.2, 1.6);
    let b = rng.range_f32(0.2, 0.4);

    let mut in_data = Vec::with_capacity(2 * l);
    for _ in 0..l {
        in_data.push(rng.range_f32(-1.0, 1.0));
    }
    for _ in 0..l {
        in_data.push(rng.range_f32(-1.0, 1.0));
    }

    let target = compute_target_from_input(&in_data, l, a, b);
    let mut meta_u32 = [0_u32; META_SLOTS];
    let mut meta_f32 = [0.0_f32; META_SLOTS];
    meta_u32[META_P0] = usize_to_u32(l);
    meta_f32[0] = a;
    meta_f32[1] = b;

    EpisodeSpec {
        family: 0,
        in_data,
        out_len: target.len(),
        work_len: 64.max(l / 2),
        target,
        meta_u32,
        meta_f32,
        robustness_bonus_scale: 0.0,
    }
}

pub fn compute_target_from_input(input: &[f32], l: usize, a: f32, b: f32) -> Vec<f32> {
    let l = l.min(input.len() / 2);
    let mut target = vec![0.0_f32; 2 * l];
    for idx in 0..l {
        let x = input[idx];
        let y = input[l + idx];
        target[idx] = 1.0 - a * x * x + y;
        target[l + idx] = b * x;
    }
    target
}
