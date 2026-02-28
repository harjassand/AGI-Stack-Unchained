use std::collections::BTreeMap;
use std::path::Path;

use crate::apfsc::errors::Result;
use crate::apfsc::law_archive::load_records;
use crate::apfsc::qd_archive::underfilled_cells;
use crate::apfsc::types::{ConstellationManifest, LawArchiveSummary, SearchLawFeatureVector};

pub fn build_searchlaw_features(
    root: &Path,
    constellation: &ConstellationManifest,
    summary: &LawArchiveSummary,
) -> Result<SearchLawFeatureVector> {
    let records = load_records(root)?;
    let mut recent_public_yield_buckets = BTreeMap::<String, i32>::new();
    let mut recent_judged_yield_points = 0i32;
    let mut recent_compute_units = 0u64;
    let mut recent_canary_failures = 0u32;
    let mut recent_challenge_failures = 0u32;

    let tail = records.iter().rev().take(32).collect::<Vec<_>>();
    for rec in tail {
        *recent_public_yield_buckets
            .entry(format!("{:?}", rec.promotion_class))
            .or_insert(0) += rec.yield_points;
        recent_judged_yield_points += rec.yield_points;
        recent_compute_units = recent_compute_units.saturating_add(rec.compute_units);
        if !rec.canary_survived {
            recent_canary_failures = recent_canary_failures.saturating_add(1);
        }
        if rec.challenge_bucket < 0 {
            recent_challenge_failures = recent_challenge_failures.saturating_add(1);
        }
    }

    let active_family_ids = constellation
        .family_specs
        .iter()
        .map(|f| f.family_id.clone())
        .collect::<Vec<_>>();

    let stale_family_ids = summary.stale_family_ids.clone();
    let mut underfilled_qd_cells = if summary.underfilled_qd_cells.is_empty() {
        underfilled_cells(root, &constellation.snapshot_hash, 16)?
    } else {
        summary.underfilled_qd_cells.clone()
    };
    underfilled_qd_cells.sort();

    let plateau = if recent_judged_yield_points <= 0 {
        2
    } else {
        0
    };

    Ok(SearchLawFeatureVector {
        active_family_ids,
        stale_family_ids,
        underfilled_qd_cells,
        dominant_failure_modes: summary.dominant_failure_modes.clone(),
        recent_public_yield_buckets,
        recent_judged_yield_points,
        recent_compute_units,
        recent_canary_failures,
        recent_challenge_failures,
        public_plateau_epochs: plateau,
    })
}
