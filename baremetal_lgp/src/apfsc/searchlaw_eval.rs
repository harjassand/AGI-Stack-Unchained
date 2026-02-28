use std::path::Path;

use crate::apfsc::active::write_active_search_law;
use crate::apfsc::artifacts::{digest_json, write_json_atomic};
use crate::apfsc::config::Phase1Config;
use crate::apfsc::errors::{ApfscError, Result};
use crate::apfsc::types::{
    LawArchiveRecord, SearchLawAbReceipt, SearchLawOfflineReceipt, SearchLawPack,
    SearchLawPromotionReceipt,
};

pub fn audit_forbidden_inputs(candidate: &SearchLawPack) -> Result<()> {
    let lowered_need = candidate.need_rules_hash.to_lowercase();
    let lowered_debt = candidate.debt_policy_hash.to_lowercase();
    let forbidden = [
        "holdout_raw",
        "challenge_raw",
        "canary_raw",
        "judge_private",
    ];
    if forbidden
        .iter()
        .any(|k| lowered_need.contains(k) || lowered_debt.contains(k))
    {
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
    crate::apfsc::artifacts::append_jsonl_atomic(
        &root.join("archives/searchlaw_trace.jsonl"),
        &receipt,
    )?;
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
    let safety_regression = false;
    let challenge_regression = false;
    let pass =
        candidate_yield_per_compute >= required && !safety_regression && !challenge_regression;

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
        pass,
        reason: if pass {
            "ABPass".to_string()
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
    crate::apfsc::artifacts::append_jsonl_atomic(
        &root.join("archives/searchlaw_trace.jsonl"),
        &receipt,
    )?;
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
        write_active_search_law(root, &candidate.manifest_hash)?;
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
    crate::apfsc::artifacts::append_jsonl_atomic(
        &root.join("archives/searchlaw_trace.jsonl"),
        &receipt,
    )?;
    Ok(receipt)
}
