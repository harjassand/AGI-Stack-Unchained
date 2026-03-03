use std::collections::BTreeMap;
use std::path::Path;

use crate::apfsc::artifacts::{
    create_dir_all_if_persistent, digest_json, path_exists, read_json, write_json_atomic,
};
use crate::apfsc::errors::Result;
use crate::apfsc::types::{MorphologyDescriptor, QdCellRecord};

fn pioneer_mode_active(root: &Path) -> bool {
    crate::apfsc::artifacts::read_pointer(root, "active_epoch_mode")
        .map(|m| m.eq_ignore_ascii_case("pioneer"))
        .unwrap_or(false)
}

fn qd_dir(root: &Path, snapshot_hash: &str) -> std::path::PathBuf {
    if pioneer_mode_active(root) {
        root.join("qd_archive")
            .join("incubator")
            .join(snapshot_hash)
    } else {
        root.join("qd_archive").join(snapshot_hash)
    }
}

pub fn load_cells(root: &Path, snapshot_hash: &str) -> Result<Vec<QdCellRecord>> {
    let p = qd_dir(root, snapshot_hash).join("cells.jsonl");
    if !path_exists(&p) {
        return Ok(Vec::new());
    }
    read_json(&p)
}

pub fn persist_cells(root: &Path, snapshot_hash: &str, cells: &[QdCellRecord]) -> Result<()> {
    let dir = qd_dir(root, snapshot_hash);
    create_dir_all_if_persistent(&dir)?;
    write_json_atomic(&dir.join("cells.jsonl"), cells)?;
    write_json_atomic(
        &dir.join("occupancy.json"),
        &serde_json::json!({
            "snapshot_hash": snapshot_hash,
            "occupied": cells.len(),
        }),
    )?;
    Ok(())
}

pub fn descriptor_cell_id(desc: &MorphologyDescriptor) -> Result<String> {
    digest_json(&(
        &desc.scheduler_class,
        &desc.memory_law_kind,
        &desc.macro_density_bin,
        &desc.state_bytes_bin,
        &desc.family_profile_bin,
        &desc.paradigm_signature_hash,
    ))
}

pub fn upsert_cell(root: &Path, snapshot_hash: &str, mut candidate: QdCellRecord) -> Result<bool> {
    if candidate.cell_id.is_empty() {
        candidate.cell_id = descriptor_cell_id(&candidate.descriptor)?;
    }

    let mut cells = load_cells(root, snapshot_hash)?;
    let mut replaced = false;

    if let Some(idx) = cells.iter().position(|c| c.cell_id == candidate.cell_id) {
        let cur = &cells[idx];
        let dominates = candidate.public_quality_score > cur.public_quality_score
            || (candidate.public_quality_score >= cur.public_quality_score
                && candidate.novelty_score > cur.novelty_score + 0.05);
        if dominates {
            cells[idx] = candidate;
            replaced = true;
        }
    } else {
        cells.push(candidate);
        replaced = true;
    }

    cells.sort_by(|a, b| a.cell_id.cmp(&b.cell_id));
    persist_cells(root, snapshot_hash, &cells)?;
    crate::apfsc::artifacts::append_jsonl_atomic(
        &if pioneer_mode_active(root) {
            root.join("archives").join("incubator_qd_archive.jsonl")
        } else {
            root.join("archives").join("qd_archive.jsonl")
        },
        &serde_json::json!({
            "snapshot_hash": snapshot_hash,
            "replaced": replaced,
            "cells": cells.iter().map(|c| c.cell_id.clone()).collect::<Vec<_>>(),
        }),
    )?;
    Ok(replaced)
}

pub fn underfilled_cells(root: &Path, snapshot_hash: &str, max_hint: usize) -> Result<Vec<String>> {
    let cells = load_cells(root, snapshot_hash)?;
    let mut bins = BTreeMap::<String, usize>::new();
    for c in &cells {
        *bins.entry(c.cell_id.clone()).or_insert(0) += 1;
    }
    let mut underfilled: Vec<String> = bins
        .into_iter()
        .filter(|(_, n)| *n <= 1)
        .map(|(k, _)| k)
        .collect();
    underfilled.sort();
    underfilled.truncate(max_hint);
    Ok(underfilled)
}
