use std::collections::BTreeMap;
use std::path::Path;

use serde::{Deserialize, Serialize};

use crate::apfsc::artifacts::{append_jsonl_atomic, read_jsonl};
use crate::apfsc::constants::ERROR_ATLAS_BINS;
use crate::apfsc::errors::Result;
use crate::apfsc::protocol::now_unix_s;
use crate::apfsc::types::{WindowRef, WitnessSelection};

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
