use super::{sample_len, usize_to_u32, EpisodeSpec, META_P0, META_P1, META_SLOTS};
use crate::oracle::SplitMix64;

pub fn sample(rng: &mut SplitMix64, difficulty_weight: f32) -> EpisodeSpec {
    let l = sample_len(rng, 16, 256, difficulty_weight);
    let mut in_data = Vec::with_capacity(4 * l);

    for _ in 0..l {
        in_data.push(rng.range_f32(-1.0, 1.0));
        in_data.push(rng.range_f32(-1.0, 1.0));
    }
    for _ in 0..l {
        in_data.push(rng.range_f32(-1.0, 1.0));
        in_data.push(rng.range_f32(-1.0, 1.0));
    }

    let mut target = compute_target_from_input(&in_data, l);
    if target.iter().all(|value| value.abs() < 1.0e-6) {
        in_data[0] = 1.0;
        in_data[2 * l] = 0.75;
        target = compute_target_from_input(&in_data, l);
    }

    let mut meta_u32 = [0_u32; META_SLOTS];
    let meta_f32 = [0.0_f32; META_SLOTS];
    meta_u32[META_P0] = usize_to_u32(l);
    meta_u32[META_P1] = 1;

    EpisodeSpec {
        family: 2,
        in_data,
        out_len: target.len(),
        work_len: 2 * l,
        target,
        meta_u32,
        meta_f32,
        robustness_bonus_scale: 0.0,
    }
}

pub fn compute_target_from_input(input: &[f32], l: usize) -> Vec<f32> {
    let l = l.min(input.len() / 4);
    let mut target = vec![0.0_f32; 2 * l];
    for idx in 0..l {
        let x_re = input[2 * idx];
        let x_im = input[2 * idx + 1];
        let w_re = input[2 * l + 2 * idx];
        let w_im = input[2 * l + 2 * idx + 1];
        target[2 * idx] = w_re * x_re - w_im * x_im;
        target[2 * idx + 1] = w_re * x_im + w_im * x_re;
    }
    target
}
