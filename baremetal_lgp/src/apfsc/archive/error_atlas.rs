use std::collections::BTreeMap;
use std::path::Path;

use serde::{Deserialize, Serialize};

use crate::apfsc::artifacts::{append_jsonl_atomic, read_jsonl};
use crate::apfsc::constants::ERROR_ATLAS_BINS;
use crate::apfsc::errors::Result;
use crate::apfsc::protocol::now_unix_s;
use crate::apfsc::types::{
    ConstellationManifest, FamilyWitnessSelection, WindowRef, WitnessSelection,
};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ErrorAtlasEntry {
    pub epoch_unix_s: u64,
    pub bin_counts: BTreeMap<String, usize>,
    pub witness_count: usize,
    pub witness_starts: Vec<u64>,
}

pub fn update_error_atlas(
    root: &Path,
    public_windows: &[WindowRef],
    witness_count: usize,
    rotation: usize,
) -> Result<WitnessSelection> {
    let mut bins: BTreeMap<String, usize> = ERROR_ATLAS_BINS
        .iter()
        .map(|k| ((*k).to_string(), 0usize))
        .collect();

    for w in public_windows {
        let key = ERROR_ATLAS_BINS[(w.start as usize) % ERROR_ATLAS_BINS.len()];
        *bins.entry(key.to_string()).or_insert(0) += 1;
    }

    let history: Vec<ErrorAtlasEntry> = read_jsonl(&root.join("archive/error_atlas.jsonl"))?;
    let offset = history.len().saturating_mul(rotation);

    let mut selected = Vec::new();
    if !public_windows.is_empty() {
        for i in 0..witness_count.min(public_windows.len()) {
            let idx = (offset + i) % public_windows.len();
            selected.push(public_windows[idx].clone());
        }
    }

    let entry = ErrorAtlasEntry {
        epoch_unix_s: now_unix_s(),
        bin_counts: bins.clone(),
        witness_count: selected.len(),
        witness_starts: selected.iter().map(|w| w.start).collect(),
    };
    append_jsonl_atomic(&root.join("archive/error_atlas.jsonl"), &entry)?;

    Ok(WitnessSelection { selected, bins })
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct FamilyErrorBin {
    pub family_id: String,
    pub failure_class: String,
    pub window_hash: String,
    pub severity_bucket: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct FamilyErrorAtlasEntry {
    pub epoch_unix_s: u64,
    pub bins: Vec<FamilyErrorBin>,
    pub selected_count: usize,
}

pub fn update_family_error_atlas(
    root: &Path,
    constellation: &ConstellationManifest,
    windows_by_family: &BTreeMap<String, Vec<WindowRef>>,
) -> Result<FamilyWitnessSelection> {
    let classes = crate::apfsc::constants::ERROR_ATLAS_BINS;
    let mut bins = Vec::<FamilyErrorBin>::new();
    let mut selected = Vec::<WindowRef>::new();
    let mut counts = BTreeMap::<String, usize>::new();

    for fam in &constellation.family_specs {
        let windows = windows_by_family
            .get(&fam.family_id)
            .cloned()
            .unwrap_or_default();
        for w in &windows {
            let class = classes[(w.start as usize) % classes.len()].to_string();
            bins.push(FamilyErrorBin {
                family_id: fam.family_id.clone(),
                failure_class: class.clone(),
                window_hash: format!("{}:{}", w.seq_hash, w.start),
                severity_bucket: if w.start % 3 == 0 {
                    "high".to_string()
                } else if w.start % 3 == 1 {
                    "mid".to_string()
                } else {
                    "low".to_string()
                },
            });
        }

        let needed = if fam.floors.protected { 2 } else { 1 };
        for i in 0..needed.min(windows.len()) {
            selected.push(windows[i].clone());
            *counts.entry(fam.family_id.clone()).or_insert(0) += 1;
        }
    }

    // Add two deterministic global witnesses if available.
    let mut all = Vec::new();
    for rows in windows_by_family.values() {
        all.extend(rows.iter().cloned());
    }
    all.sort_by(|a, b| {
        a.seq_hash
            .cmp(&b.seq_hash)
            .then_with(|| a.start.cmp(&b.start))
    });
    for w in all.into_iter().take(2) {
        selected.push(w);
    }

    let mut bin_counts = BTreeMap::<String, usize>::new();
    for b in &bins {
        let key = format!("{}:{}", b.family_id, b.failure_class);
        *bin_counts.entry(key).or_insert(0) += 1;
    }

    let row = FamilyErrorAtlasEntry {
        epoch_unix_s: now_unix_s(),
        bins,
        selected_count: selected.len(),
    };
    append_jsonl_atomic(&root.join("archive/error_atlas.jsonl"), &row)?;

    Ok(FamilyWitnessSelection {
        selected,
        bins: bin_counts,
        per_family_counts: counts,
    })
}
