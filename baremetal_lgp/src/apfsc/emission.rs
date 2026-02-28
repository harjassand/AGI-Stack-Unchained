use crate::apfsc::constants::{EPSILON_MASS, U16_MASS_TOTAL};
use crate::apfsc::headpack::apply_linear;
use crate::apfsc::types::HeadPack;

pub fn emit_freq_u16(heads: &HeadPack, features: &[f32]) -> [u16; 256] {
    let native = apply_linear(&heads.native_head, features);
    let nuisance = apply_linear(&heads.nuisance_head, features);
    let residual = apply_linear(&heads.residual_head, features);

    let mut mass = vec![0.0f64; 256];
    for i in 0..256 {
        let m = softplus(native[i]) + softplus(nuisance[i]) + softplus(residual[i]) + EPSILON_MASS;
        mass[i] = m as f64;
    }

    normalize_to_u16_mass_65536(&mass)
}

pub fn bits_for_target(freq: &[u16; 256], target: u8) -> f64 {
    let p = (freq[target as usize] as f64).max(1.0) / U16_MASS_TOTAL as f64;
    -p.log2()
}

fn softplus(x: f32) -> f32 {
    if x > 20.0 {
        x
    } else {
        (1.0 + x.exp()).ln()
    }
}

fn normalize_to_u16_mass_65536(mass: &[f64]) -> [u16; 256] {
    let total: f64 = mass.iter().sum::<f64>().max(1e-12);
    let mut scaled = vec![0.0f64; 256];
    for (i, m) in mass.iter().enumerate() {
        scaled[i] = (*m / total) * U16_MASS_TOTAL as f64;
    }

    let mut base = [0u16; 256];
    let mut used: u32 = 0;
    let mut frac = Vec::with_capacity(256);
    for i in 0..256 {
        let floored = scaled[i].floor() as u32;
        base[i] = floored.min(u16::MAX as u32) as u16;
        used += base[i] as u32;
        frac.push((scaled[i] - floored as f64, i));
    }

    let mut remain = U16_MASS_TOTAL.saturating_sub(used);
    frac.sort_by(|a, b| b.0.partial_cmp(&a.0).unwrap_or(std::cmp::Ordering::Equal));
    let mut idx = 0usize;
    while remain > 0 {
        let i = frac[idx % frac.len()].1;
        base[i] = base[i].saturating_add(1);
        remain -= 1;
        idx += 1;
    }

    base
}
