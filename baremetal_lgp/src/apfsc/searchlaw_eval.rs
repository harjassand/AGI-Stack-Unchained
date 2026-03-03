use std::path::Path;

use crate::apfsc::active::{write_active_incubator_search_law, write_active_search_law};
use crate::apfsc::artifacts::{digest_json, read_pointer, write_json_atomic, write_pointer};
use crate::apfsc::config::Phase1Config;
use crate::apfsc::errors::{ApfscError, Result};
use crate::apfsc::types::{
    LawArchiveRecord, SearchLawAbReceipt, SearchLawOfflineReceipt, SearchLawPack,
    SearchLawPromotionReceipt,
};

fn pioneer_mode_active(root: &Path) -> bool {
    crate::apfsc::artifacts::read_pointer(root, "active_epoch_mode")
        .map(|m| m.eq_ignore_ascii_case("pioneer"))
        .unwrap_or(false)
}

fn searchlaw_trace_path(root: &Path) -> std::path::PathBuf {
    if pioneer_mode_active(root) {
        root.join("archives")
            .join("incubator_searchlaw_trace.jsonl")
    } else {
        root.join("archives").join("searchlaw_trace.jsonl")
    }
}

const THERMAL_SPIKE_TEMP_PTR: &str = "searchlaw_thermal_spike_temp_bpb";
const THERMAL_SPIKE_EPOCHS_REMAINING_PTR: &str = "searchlaw_thermal_spike_epochs_remaining";
const THERMAL_SPIKE_COOLDOWN_PTR: &str = "searchlaw_thermal_spike_cooldown_temp_bpb";

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize, PartialEq)]
pub struct ThermalSpikeState {
    pub active: bool,
    pub temp: Option<f64>,
    pub epochs_remaining: u32,
    pub cooldown_temp: Option<f64>,
}

fn read_ptr_f64(root: &Path, key: &str) -> Option<f64> {
    let raw = read_pointer(root, key).ok()?;
    let v = raw.parse::<f64>().ok()?;
    if v.is_finite() {
        Some(v)
    } else {
        None
    }
}

fn read_ptr_u32(root: &Path, key: &str) -> Option<u32> {
    let raw = read_pointer(root, key).ok()?;
    raw.parse::<u32>().ok()
}

pub fn force_thermal_spike(
    root: &Path,
    temp: f64,
    epochs: u32,
    cooldown_temp: f64,
) -> Result<serde_json::Value> {
    if !temp.is_finite() || temp <= 0.0 {
        return Err(ApfscError::Validation(
            "thermal spike temp must be finite and > 0".to_string(),
        ));
    }
    if !cooldown_temp.is_finite() || cooldown_temp <= 0.0 {
        return Err(ApfscError::Validation(
            "thermal cooldown temp must be finite and > 0".to_string(),
        ));
    }
    let epochs = epochs.max(1);
    write_pointer(root, THERMAL_SPIKE_TEMP_PTR, &format!("{temp:.6}"))?;
    write_pointer(
        root,
        THERMAL_SPIKE_EPOCHS_REMAINING_PTR,
        &epochs.to_string(),
    )?;
    write_pointer(
        root,
        THERMAL_SPIKE_COOLDOWN_PTR,
        &format!("{cooldown_temp:.6}"),
    )?;
    Ok(serde_json::json!({
        "temp": temp,
        "epochs_remaining": epochs,
        "cooldown_temp": cooldown_temp
    }))
}

pub fn thermal_spike_active(root: &Path) -> bool {
    read_ptr_u32(root, THERMAL_SPIKE_EPOCHS_REMAINING_PTR).unwrap_or(0) > 0
}

pub fn thermal_spike_state(root: &Path) -> ThermalSpikeState {
    let epochs_remaining = read_ptr_u32(root, THERMAL_SPIKE_EPOCHS_REMAINING_PTR).unwrap_or(0);
    ThermalSpikeState {
        active: epochs_remaining > 0,
        temp: read_ptr_f64(root, THERMAL_SPIKE_TEMP_PTR),
        epochs_remaining,
        cooldown_temp: read_ptr_f64(root, THERMAL_SPIKE_COOLDOWN_PTR),
    }
}

pub fn advance_thermal_spike_epoch(root: &Path) -> Result<Option<serde_json::Value>> {
    let Some(remaining) = read_ptr_u32(root, THERMAL_SPIKE_EPOCHS_REMAINING_PTR) else {
        return Ok(None);
    };
    if remaining == 0 {
        return Ok(None);
    }
    let next = remaining.saturating_sub(1);
    write_pointer(root, THERMAL_SPIKE_EPOCHS_REMAINING_PTR, &next.to_string())?;
    if next == 0 {
        let cooldown = read_ptr_f64(root, THERMAL_SPIKE_COOLDOWN_PTR).unwrap_or(0.1);
        write_pointer(root, THERMAL_SPIKE_TEMP_PTR, &format!("{cooldown:.6}"))?;
    }
    let temp = read_ptr_f64(root, THERMAL_SPIKE_TEMP_PTR);
    Ok(Some(serde_json::json!({
        "epochs_remaining": next,
        "temp": temp
    })))
}

fn runtime_thermal_temperature_override(root: &Path) -> Option<f64> {
    let remaining = read_ptr_u32(root, THERMAL_SPIKE_EPOCHS_REMAINING_PTR).unwrap_or(0);
    let temp = read_ptr_f64(root, THERMAL_SPIKE_TEMP_PTR)?;
    if remaining > 0 {
        return Some(temp.max(1e-6));
    }
    // After spike expiry keep the explicit cooldown value in effect.
    if remaining == 0 {
        return Some(temp.max(1e-6));
    }
    None
}

pub fn audit_forbidden_inputs(candidate: &SearchLawPack) -> Result<()> {
    let payload = serde_json::to_string(candidate)
        .map_err(|e| ApfscError::Protocol(format!("search law serialize failed: {e}")))?;
    let lowered = payload.to_lowercase();
    let forbidden = [
        "holdout_raw",
        "holdout_scalar",
        "challenge_raw",
        "hidden_challenge_content",
        "canary_raw",
        "judge_private",
        "protocol_private",
    ];
    if forbidden.iter().any(|k| lowered.contains(k)) {
        return Err(ApfscError::Validation(
            "search law references forbidden private judge inputs".to_string(),
        ));
    }
    Ok(())
}

fn yield_per_compute(points: i32, compute: u64) -> f64 {
    if compute == 0 {
        return 0.0;
    }
    points as f64 / compute as f64
}

fn load_ectoderm_paradigm_temperature(root: &Path, cfg: &Phase1Config) -> f64 {
    if let Some(temp) = runtime_thermal_temperature_override(root) {
        return temp
            .max(cfg.phase4.searchlaw_ergodic_temperature_floor)
            .max(1e-6);
    }
    let fallback = cfg
        .phase3
        .promotion
        .paradigm_shift_allowance_bpb
        .max(cfg.phase4.searchlaw_ergodic_temperature_floor)
        .max(1e-6);
    let dir = root.join("receipts").join("ectoderm");
    if !dir.exists() {
        return fallback;
    }
    let mut latest: Option<(u64, std::path::PathBuf)> = None;
    if let Ok(rd) = std::fs::read_dir(&dir) {
        for e in rd.flatten() {
            let p = e.path();
            if p.extension().and_then(|v| v.to_str()) != Some("json") {
                continue;
            }
            let modified = std::fs::metadata(&p)
                .ok()
                .and_then(|m| m.modified().ok())
                .and_then(|t| t.duration_since(std::time::UNIX_EPOCH).ok())
                .map(|d| d.as_secs())
                .unwrap_or(0);
            match latest {
                Some((best, _)) if best >= modified => {}
                _ => latest = Some((modified, p)),
            }
        }
    }
    let Some((_, latest_path)) = latest else {
        return fallback;
    };
    let Ok(text) = std::fs::read_to_string(latest_path) else {
        return fallback;
    };
    let Ok(v) = serde_json::from_str::<serde_json::Value>(&text) else {
        return fallback;
    };
    v.get("applied")
        .and_then(|x| x.get("paradigm_shift_allowance_bpb"))
        .and_then(|x| x.as_f64())
        .unwrap_or(fallback)
        .max(cfg.phase4.searchlaw_ergodic_temperature_floor)
        .max(1e-6)
}

fn normalized_weights(pack: &SearchLawPack) -> Vec<f64> {
    let mut out = Vec::new();
    out.extend(pack.lane_weights_q16.values().map(|v| *v as f64 / 65535.0));
    out.extend(pack.class_weights_q16.values().map(|v| *v as f64 / 65535.0));
    out.extend(
        pack.family_weights_q16
            .values()
            .map(|v| *v as f64 / 65535.0),
    );
    out.push(pack.qd_explore_rate_q16 as f64 / 65535.0);
    out.push(pack.recombination_rate_q16 as f64 / 65535.0);
    out.push(pack.fresh_family_bias_q16 as f64 / 65535.0);
    out
}

fn structural_sparsity_score(pack: &SearchLawPack) -> f64 {
    let weights = normalized_weights(pack);
    if weights.is_empty() {
        return 0.0;
    }
    let nonzero = weights.iter().filter(|w| **w > 1e-6).count() as f64;
    let total = weights.len() as f64;
    let sum = weights.iter().sum::<f64>().max(1e-9);
    let peak = weights.iter().copied().fold(0.0, f64::max);
    let concentration = (peak / sum).clamp(0.0, 1.0);
    let zero_mass = (1.0 - nonzero / total).clamp(0.0, 1.0);
    // Higher score = sparser / more concentrated routing policy.
    (0.6 * zero_mass + 0.4 * concentration).clamp(0.0, 1.0)
}

fn metropolis_acceptance_probability(loss_delta: f64, temperature: f64) -> f64 {
    if loss_delta <= 0.0 {
        return 1.0;
    }
    (-loss_delta / temperature.max(1e-9)).exp().clamp(0.0, 1.0)
}

fn deterministic_unit_sample(parts: &[&str]) -> f64 {
    let mut h = blake3::Hasher::new();
    for p in parts {
        h.update(p.as_bytes());
        h.update(&[0x1F]);
    }
    let digest = h.finalize();
    let b = digest.as_bytes();
    let raw = u64::from_le_bytes([b[0], b[1], b[2], b[3], b[4], b[5], b[6], b[7]]);
    (raw as f64) / (u64::MAX as f64)
}

pub fn evaluate_searchlaw_offline(
    root: &Path,
    candidate: &SearchLawPack,
    records: &[LawArchiveRecord],
    snapshot_hash: &str,
    constellation_id: &str,
    protocol_version: &str,
) -> Result<SearchLawOfflineReceipt> {
    audit_forbidden_inputs(candidate)?;

    let replay_records_used = records.len() as u64;
    let hist_points: i32 = records.iter().map(|r| r.yield_points).sum();
    let hist_compute: u64 = records.iter().map(|r| r.compute_units).sum::<u64>().max(1);
    let baseline = yield_per_compute(hist_points, hist_compute);

    let truth_bias = candidate
        .lane_weights_q16
        .get("truth")
        .copied()
        .unwrap_or(0) as f64
        / 65535.0;
    let recomb_bias = candidate.recombination_rate_q16 as f64 / 65535.0;
    let mult = 0.90 + (truth_bias * 0.20) + (recomb_bias * 0.05);

    let projected_yield_per_compute = baseline * mult;
    let projected_compute_units = hist_compute;
    let projected_yield_points =
        (projected_yield_per_compute * projected_compute_units as f64).round() as i32;

    let pass = projected_yield_per_compute >= baseline;
    let receipt = SearchLawOfflineReceipt {
        searchlaw_hash: candidate.manifest_hash.clone(),
        replay_records_used,
        projected_yield_points,
        projected_compute_units,
        projected_yield_per_compute,
        pass,
        reason: if pass {
            "OfflinePass".to_string()
        } else {
            "OfflineProjectedRegression".to_string()
        },
        snapshot_hash: snapshot_hash.to_string(),
        constellation_id: constellation_id.to_string(),
        protocol_version: protocol_version.to_string(),
    };

    let dir = root.join("search_laws").join(&candidate.manifest_hash);
    std::fs::create_dir_all(&dir).map_err(|e| crate::apfsc::errors::io_err(&dir, e))?;
    write_json_atomic(&dir.join("offline_eval_receipt.json"), &receipt)?;
    crate::apfsc::artifacts::append_jsonl_atomic(&searchlaw_trace_path(root), &receipt)?;
    Ok(receipt)
}

pub fn evaluate_searchlaw_ab(
    root: &Path,
    candidate: &SearchLawPack,
    incumbent: &SearchLawPack,
    offline: &SearchLawOfflineReceipt,
    records: &[LawArchiveRecord],
    ab_epochs: u32,
    cfg: &Phase1Config,
    snapshot_hash: &str,
    constellation_id: &str,
    protocol_version: &str,
) -> Result<SearchLawAbReceipt> {
    if ab_epochs < cfg.phase4.searchlaw_min_ab_epochs
        || ab_epochs > cfg.phase4.searchlaw_max_ab_epochs
    {
        return Err(ApfscError::Validation(format!(
            "ab_epochs={} outside configured range {}..={}",
            ab_epochs, cfg.phase4.searchlaw_min_ab_epochs, cfg.phase4.searchlaw_max_ab_epochs
        )));
    }

    if !offline.pass {
        return Ok(SearchLawAbReceipt {
            candidate_searchlaw_hash: candidate.manifest_hash.clone(),
            incumbent_searchlaw_hash: incumbent.manifest_hash.clone(),
            ab_epochs,
            incumbent_yield_points: 0,
            candidate_yield_points: 0,
            incumbent_compute_units: 1,
            candidate_compute_units: 1,
            incumbent_yield_per_compute: 0.0,
            candidate_yield_per_compute: 0.0,
            challenge_regression: true,
            safety_regression: true,
            metropolis_acceptance_probability: 0.0,
            metropolis_temperature_bpb: 0.0,
            structural_sparsity_gain: 0.0,
            ergodic_drift_accepted: false,
            pareto_dominates_incumbent: false,
            pass: false,
            reason: "ABSkippedOfflineFail".to_string(),
            snapshot_hash: snapshot_hash.to_string(),
            constellation_id: constellation_id.to_string(),
            protocol_version: protocol_version.to_string(),
        });
    }

    let hist_points: i32 = records.iter().map(|r| r.yield_points).sum();
    let hist_compute: u64 = records.iter().map(|r| r.compute_units).sum::<u64>().max(1);
    let base = yield_per_compute(hist_points, hist_compute);

    let candidate_compute_units = (hist_compute / 2).saturating_mul(ab_epochs as u64).max(1);
    let incumbent_compute_units = candidate_compute_units;
    let candidate_yield_per_compute = offline.projected_yield_per_compute;
    let incumbent_yield_per_compute = base;
    let candidate_yield_points =
        (candidate_yield_per_compute * candidate_compute_units as f64).round() as i32;
    let incumbent_yield_points =
        (incumbent_yield_per_compute * incumbent_compute_units as f64).round() as i32;

    let required =
        incumbent_yield_per_compute * (1.0 + cfg.phase4.searchlaw_required_yield_improvement);
    let total = records.len().max(1) as f64;
    let canary_failure_rate = records.iter().filter(|r| !r.canary_survived).count() as f64 / total;
    let family_signal: i64 = records
        .iter()
        .map(|r| {
            r.family_outcome_buckets
                .values()
                .copied()
                .map(i64::from)
                .sum::<i64>()
        })
        .sum();
    let holdout_regression = family_signal < 0;
    let challenge_mean = records
        .iter()
        .map(|r| r.challenge_bucket as f64)
        .sum::<f64>()
        / total;
    let safety_regression = canary_failure_rate > cfg.phase4.searchlaw_max_safety_regression;
    let challenge_regression = challenge_mean < 0.0 || holdout_regression;
    let strict_nonzero_gain = candidate_yield_per_compute > incumbent_yield_per_compute
        && candidate_yield_per_compute > 0.0
        && candidate_yield_per_compute > required
        && !safety_regression
        && !challenge_regression;

    // Ergodic drift (Metropolis-Hastings): allow annealing-style exploration to survive
    // mild temporary regressions when safety constraints still hold.
    let incumbent_pos = incumbent_yield_per_compute.max(1e-9);
    let loss_delta = (incumbent_yield_per_compute - candidate_yield_per_compute).max(0.0);
    let loss_ratio = loss_delta / incumbent_pos;
    let temperature = load_ectoderm_paradigm_temperature(root, cfg);
    let acceptance_probability = metropolis_acceptance_probability(loss_ratio, temperature);
    let structural_sparsity_gain =
        structural_sparsity_score(candidate) - structural_sparsity_score(incumbent);
    let drift_candidate = cfg.phase4.searchlaw_ergodic_enabled
        && !safety_regression
        && loss_ratio <= cfg.phase4.searchlaw_ergodic_max_loss_ratio;
    let sample = deterministic_unit_sample(&[
        &candidate.manifest_hash,
        &incumbent.manifest_hash,
        &ab_epochs.to_string(),
        snapshot_hash,
        constellation_id,
    ]);
    let ergodic_drift_accepted = drift_candidate && sample <= acceptance_probability;

    let incumbent_struct_complexity = 1.0 - structural_sparsity_score(incumbent);
    let candidate_struct_complexity = 1.0 - structural_sparsity_score(candidate);
    let incumbent_exec_speed =
        incumbent_compute_units as f64 / (incumbent_yield_points.abs() as f64 + 1.0);
    let candidate_exec_speed =
        candidate_compute_units as f64 / (candidate_yield_points.abs() as f64 + 1.0);
    let incumbent_thermo_surprisal = 0.0;
    let candidate_thermo_surprisal = loss_ratio;
    let pareto_dominates_incumbent = candidate_struct_complexity <= incumbent_struct_complexity
        && candidate_thermo_surprisal <= incumbent_thermo_surprisal
        && candidate_exec_speed <= incumbent_exec_speed
        && (candidate_struct_complexity < incumbent_struct_complexity
            || candidate_thermo_surprisal < incumbent_thermo_surprisal
            || candidate_exec_speed < incumbent_exec_speed);

    let pass = strict_nonzero_gain || ergodic_drift_accepted || pareto_dominates_incumbent;

    let receipt = SearchLawAbReceipt {
        candidate_searchlaw_hash: candidate.manifest_hash.clone(),
        incumbent_searchlaw_hash: incumbent.manifest_hash.clone(),
        ab_epochs,
        incumbent_yield_points,
        candidate_yield_points,
        incumbent_compute_units,
        candidate_compute_units,
        incumbent_yield_per_compute,
        candidate_yield_per_compute,
        challenge_regression,
        safety_regression,
        metropolis_acceptance_probability: acceptance_probability,
        metropolis_temperature_bpb: temperature,
        structural_sparsity_gain,
        ergodic_drift_accepted,
        pareto_dominates_incumbent,
        pass,
        reason: if strict_nonzero_gain {
            "ABPass".to_string()
        } else if ergodic_drift_accepted {
            "ABPassMetropolis".to_string()
        } else if pareto_dominates_incumbent {
            "ABPassPareto".to_string()
        } else if safety_regression || challenge_regression {
            "ABSafetyOrHoldoutRegression".to_string()
        } else {
            "ABInsufficientYield".to_string()
        },
        snapshot_hash: snapshot_hash.to_string(),
        constellation_id: constellation_id.to_string(),
        protocol_version: protocol_version.to_string(),
    };

    let dir = root.join("search_laws").join(&candidate.manifest_hash);
    std::fs::create_dir_all(&dir).map_err(|e| crate::apfsc::errors::io_err(&dir, e))?;
    write_json_atomic(&dir.join("ab_eval_receipt.json"), &receipt)?;
    crate::apfsc::artifacts::append_jsonl_atomic(&searchlaw_trace_path(root), &receipt)?;
    Ok(receipt)
}

pub fn promote_search_law_if_pass(
    root: &Path,
    candidate: &SearchLawPack,
    incumbent: &SearchLawPack,
    ab: &SearchLawAbReceipt,
    snapshot_hash: &str,
    constellation_id: &str,
    protocol_version: &str,
) -> Result<SearchLawPromotionReceipt> {
    let ab_receipt_hash = digest_json(ab)?;
    let applied = ab.pass;
    if applied {
        if pioneer_mode_active(root) {
            write_active_incubator_search_law(root, &candidate.manifest_hash)?;
        } else {
            write_active_search_law(root, &candidate.manifest_hash)?;
        }
    }
    let receipt = SearchLawPromotionReceipt {
        candidate_searchlaw_hash: candidate.manifest_hash.clone(),
        incumbent_searchlaw_hash: incumbent.manifest_hash.clone(),
        decision: if applied {
            "Promote".to_string()
        } else {
            "Reject".to_string()
        },
        reason: if applied {
            "Promote".to_string()
        } else {
            "Reject(SearchLawAbFail)".to_string()
        },
        ab_receipt_hash,
        applied,
        snapshot_hash: snapshot_hash.to_string(),
        constellation_id: constellation_id.to_string(),
        protocol_version: protocol_version.to_string(),
    };
    let dir = root.join("search_laws").join(&candidate.manifest_hash);
    std::fs::create_dir_all(&dir).map_err(|e| crate::apfsc::errors::io_err(&dir, e))?;
    write_json_atomic(&dir.join("promotion_receipt.json"), &receipt)?;
    crate::apfsc::artifacts::append_jsonl_atomic(&searchlaw_trace_path(root), &receipt)?;
    Ok(receipt)
}
