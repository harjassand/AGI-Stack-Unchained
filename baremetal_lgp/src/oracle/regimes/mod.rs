use super::SplitMix64;

pub mod chaotic;
pub mod complex_linear;
pub mod ood_mix;
pub mod regime_shift;

pub const NUM_FAMILIES: usize = 4;
pub const META_SLOTS: usize = 16;

pub const META_IN_BASE: usize = 0;
pub const META_IN_LEN: usize = 1;
pub const META_OUT_BASE: usize = 2;
pub const META_OUT_LEN: usize = 3;
pub const META_WORK_BASE: usize = 4;
pub const META_WORK_LEN: usize = 5;

pub const META_P0: usize = 6;
pub const META_P1: usize = 7;
pub const META_P2: usize = 8;
pub const META_P3: usize = 9;
pub const META_P4: usize = 10;
pub const META_P5: usize = 11;
pub const META_P6: usize = 12;
pub const META_P7: usize = 13;
pub const META_P8: usize = 14;
pub const META_P9: usize = 15;

#[derive(Clone, Debug)]
pub struct EpisodeSpec {
    pub family: u8,
    pub in_data: Vec<f32>,
    pub out_len: usize,
    pub work_len: usize,
    pub target: Vec<f32>,
    pub meta_u32: [u32; META_SLOTS],
    pub meta_f32: [f32; META_SLOTS],
    pub robustness_bonus_scale: f32,
}

pub fn sample_episode(
    family: u8,
    rng: &mut SplitMix64,
    mixture_weights: [f32; NUM_FAMILIES],
    family_weight: f32,
) -> EpisodeSpec {
    match family {
        0 => chaotic::sample(rng, family_weight),
        1 => regime_shift::sample(rng, family_weight),
        2 => complex_linear::sample(rng, family_weight),
        _ => ood_mix::sample(rng, mixture_weights, family_weight),
    }
}

pub(crate) fn sample_len(
    rng: &mut SplitMix64,
    min_len: usize,
    max_len: usize,
    difficulty_weight: f32,
) -> usize {
    if min_len >= max_len {
        return min_len;
    }
    let span = max_len - min_len;
    let weight = difficulty_weight.clamp(0.05, 0.95);
    let t = weight + (1.0 - weight) * rng.next_f32();
    min_len + (span as f32 * t) as usize
}

pub(crate) fn usize_to_u32(value: usize) -> u32 {
    u32::try_from(value).unwrap_or(u32::MAX)
}
