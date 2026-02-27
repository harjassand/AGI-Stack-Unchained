use super::{sample_len, usize_to_u32, EpisodeSpec, META_P0, META_P1, META_SLOTS};
use crate::oracle::SplitMix64;

pub fn sample(rng: &mut SplitMix64, difficulty_weight: f32) -> EpisodeSpec {
    let l = sample_len(rng, 64, 768, difficulty_weight);
    let rule_id = rng.next_usize(4) as u32;

    let mut in_data = Vec::with_capacity(l);
    for _ in 0..l {
        in_data.push(rng.range_f32(-2.0, 2.0));
    }
    let target = compute_target_from_input(&in_data, rule_id);

    let mut meta_u32 = [0_u32; META_SLOTS];
    let meta_f32 = [0.0_f32; META_SLOTS];
    meta_u32[META_P0] = rule_id;
    meta_u32[META_P1] = usize_to_u32(l);

    EpisodeSpec {
        family: 1,
        in_data,
        out_len: target.len(),
        work_len: 128,
        target,
        meta_u32,
        meta_f32,
        robustness_bonus_scale: 0.0,
    }
}

pub fn compute_target_from_input(input: &[f32], rule_id: u32) -> Vec<f32> {
    input
        .iter()
        .copied()
        .map(|x| apply_rule(x, rule_id))
        .collect()
}

fn apply_rule(x: f32, rule_id: u32) -> f32 {
    match rule_id & 3 {
        0 => x * x,
        1 => x + 0.1,
        2 => x.tanh(),
        _ => x * (1.0 - x),
    }
}
