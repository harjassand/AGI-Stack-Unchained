use super::{
    chaotic, complex_linear, regime_shift, EpisodeSpec, META_P0, META_P1, META_P2, NUM_FAMILIES,
};
use crate::oracle::SplitMix64;

const PERMUTE_BLOCK_WORDS: usize = 64;

pub fn sample(
    rng: &mut SplitMix64,
    mixture_weights: [f32; NUM_FAMILIES],
    difficulty_weight: f32,
) -> EpisodeSpec {
    let wrapped_family = sample_wrapped_family(rng, mixture_weights);
    let mut base = match wrapped_family {
        0 => chaotic::sample(rng, difficulty_weight),
        1 => regime_shift::sample(rng, difficulty_weight),
        _ => complex_linear::sample(rng, difficulty_weight),
    };

    let scale = rng.range_f32(0.5, 2.0);
    let sigma = rng.range_f32(0.0, 0.05);
    perturb_inputs(rng, &mut base.in_data, scale, sigma);

    if rng.next_f32() < 0.5 {
        permute_blocks(rng, &mut base.in_data, PERMUTE_BLOCK_WORDS);
    }

    base.target = recompute_target(&base, wrapped_family);
    base.out_len = base.target.len();
    base.family = 3;
    base.meta_u32[META_P2] = u32::from(wrapped_family);
    base.meta_f32[2] = scale;
    base.meta_f32[3] = sigma;
    base.robustness_bonus_scale = 0.02 + 0.04 * difficulty_weight.clamp(0.05, 0.95);
    base
}

fn sample_wrapped_family(rng: &mut SplitMix64, weights: [f32; NUM_FAMILIES]) -> u8 {
    let wrapped_weights = [
        weights[0].max(0.0),
        weights[1].max(0.0),
        weights[2].max(0.0),
    ];
    let total = wrapped_weights.iter().sum::<f32>();
    if total <= f32::EPSILON {
        return 0;
    }

    let mut draw = rng.next_f32() * total;
    for (idx, weight) in wrapped_weights.iter().enumerate() {
        draw -= *weight;
        if draw <= 0.0 {
            return idx as u8;
        }
    }
    2
}

fn perturb_inputs(rng: &mut SplitMix64, values: &mut [f32], scale: f32, sigma: f32) {
    for value in values.iter_mut() {
        let noise = rng.gaussian() * sigma;
        *value = (*value * scale) + noise;
    }
}

fn permute_blocks(rng: &mut SplitMix64, data: &mut [f32], block_words: usize) {
    if block_words == 0 || data.len() < block_words || !data.len().is_multiple_of(block_words) {
        return;
    }

    let block_count = data.len() / block_words;
    let mut order: Vec<usize> = (0..block_count).collect();
    for idx in (1..order.len()).rev() {
        let swap_idx = rng.next_usize(idx + 1);
        order.swap(idx, swap_idx);
    }

    let original = data.to_vec();
    for (dst_block, src_block) in order.iter().copied().enumerate() {
        let dst_start = dst_block * block_words;
        let src_start = src_block * block_words;
        data[dst_start..dst_start + block_words]
            .copy_from_slice(&original[src_start..src_start + block_words]);
    }
}

fn recompute_target(base: &EpisodeSpec, wrapped_family: u8) -> Vec<f32> {
    match wrapped_family {
        0 => {
            let l = usize::try_from(base.meta_u32[META_P0]).unwrap_or(0);
            let a = base.meta_f32[0];
            let b = base.meta_f32[1];
            chaotic::compute_target_from_input(&base.in_data, l, a, b)
        }
        1 => {
            let l = usize::try_from(base.meta_u32[META_P1]).unwrap_or(0);
            let rule_id = base.meta_u32[META_P0];
            regime_shift::compute_target_from_input(
                &base.in_data[..base.in_data.len().min(l)],
                rule_id,
            )
        }
        _ => {
            let l = usize::try_from(base.meta_u32[META_P0]).unwrap_or(0);
            complex_linear::compute_target_from_input(&base.in_data, l)
        }
    }
}
