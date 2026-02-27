use super::SplitMix64;

pub const NUM_FAMILIES: usize = 4;

pub fn coverage_family(proxy_counter: u64) -> u8 {
    (proxy_counter % NUM_FAMILIES as u64) as u8
}

pub fn next_proxy_families(
    proxy_counter: &mut u64,
    weights: [f32; NUM_FAMILIES],
    rng: &mut SplitMix64,
) -> (u8, u8) {
    let coverage = coverage_family(*proxy_counter);
    let weighted = sample_weighted_excluding(weights, coverage, rng);
    *proxy_counter = proxy_counter.saturating_add(1);
    (coverage, weighted)
}

pub fn sample_weighted_excluding(
    weights: [f32; NUM_FAMILIES],
    coverage_family: u8,
    rng: &mut SplitMix64,
) -> u8 {
    let coverage_idx = usize::from(coverage_family % NUM_FAMILIES as u8);
    let total: f32 = weights
        .iter()
        .enumerate()
        .filter_map(|(idx, value)| {
            if idx != coverage_idx {
                Some(*value)
            } else {
                None
            }
        })
        .sum();

    if total <= f32::EPSILON {
        return ((coverage_idx + 1) % NUM_FAMILIES) as u8;
    }

    let mut draw = rng.next_f32() * total;
    let mut fallback = ((coverage_idx + 1) % NUM_FAMILIES) as u8;
    for (idx, weight) in weights.iter().enumerate() {
        if idx == coverage_idx {
            continue;
        }
        fallback = idx as u8;
        draw -= *weight;
        if draw <= 0.0 {
            return idx as u8;
        }
    }

    fallback
}

pub fn regime_profile_bits(full_by_family: [f32; NUM_FAMILIES], full_mean: f32) -> u8 {
    let mut bits = 0_u8;
    let threshold = full_mean - 0.10;
    for (idx, family_mean) in full_by_family.iter().enumerate() {
        if *family_mean >= threshold {
            bits |= 1_u8 << idx;
        }
    }
    bits
}
