use crate::types::StopReason;

pub fn mse(output: &[f32], target: &[f32]) -> f32 {
    let len = output.len().min(target.len());
    if len == 0 {
        return 0.0;
    }

    let mut sum = 0.0_f32;
    for idx in 0..len {
        let d = output[idx] - target[idx];
        sum += d * d;
    }
    sum / len as f32
}

pub fn has_non_finite(values: &[f32]) -> bool {
    values.iter().any(|value| !value.is_finite())
}

pub fn score_episode(
    output: &[f32],
    target: &[f32],
    fuel_used: u32,
    stop_reason: StopReason,
    robustness_bonus: f32,
) -> f32 {
    if stop_reason == StopReason::FuelExhausted {
        return -1.0e9;
    }

    let mut score = -mse(output, target);
    if has_non_finite(output) {
        score -= 10.0;
    }
    score -= 0.0001 * fuel_used as f32;
    score + robustness_bonus.max(0.0)
}

pub fn stability_bonus(output: &[f32], scale: f32) -> f32 {
    if output.is_empty() || scale <= 0.0 {
        return 0.0;
    }

    let mean = output.iter().sum::<f32>() / output.len() as f32;
    let mut var = 0.0_f32;
    for value in output {
        let d = *value - mean;
        var += d * d;
    }
    var /= output.len() as f32;
    scale / (1.0 + var)
}
