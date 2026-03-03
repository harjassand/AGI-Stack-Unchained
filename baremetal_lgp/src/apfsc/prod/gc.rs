use std::collections::BTreeSet;
use std::path::Path;

use crate::apfsc::artifacts::{read_json, read_pointer, write_json_atomic};
use crate::apfsc::errors::{io_err, Result};
use crate::apfsc::types::CandidateManifest;

pub const DEFAULT_TOMBSTONE_DAYS: u64 = 0;

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize, PartialEq)]
pub struct TombstoneEntry {
    pub object_kind: String,
    pub object_hash: String,
    pub tombstoned_at_unix_s: u64,
    pub grace_days: u64,
}

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize, PartialEq)]
pub struct GcReport {
    pub dry_run: bool,
    pub tombstone_days: u64,
    // Backward-compatible alias for older report consumers/tests.
    pub candidates_marked: usize,
    pub candidates_marked_reachable: usize,
    pub candidates_tombstoned: usize,
    pub tombstones_existing: usize,
}

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize, PartialEq)]
pub struct TombstoneSweepReport {
    pub dry_run: bool,
    pub tombstone_days: u64,
    pub eligible_for_delete: usize,
    pub deleted: usize,
}

pub fn gc_candidates(root: &Path, dry_run: bool) -> Result<GcReport> {
    let now_s = crate::apfsc::prod::jobs::now_unix_s();
    let reachable = reachable_candidate_set(root)?;
    let candidates_dir = root.join("candidates");
    let tombstone_dir = tombstone_candidates_dir(root);
    let tombstone_index_dir = tombstone_index_dir(root);
    std::fs::create_dir_all(&tombstone_dir).map_err(|e| io_err(&tombstone_dir, e))?;
    std::fs::create_dir_all(&tombstone_index_dir).map_err(|e| io_err(&tombstone_index_dir, e))?;

    let mut marked = 0usize;
    let mut tombstoned = 0usize;
    if candidates_dir.exists() {
        for e in std::fs::read_dir(&candidates_dir).map_err(|e| io_err(&candidates_dir, e))? {
            let e = e.map_err(|e| io_err(&candidates_dir, e))?;
            let p = e.path();
            if !e.file_type().map_err(|e| io_err(&p, e))?.is_dir() {
                continue;
            }
            let hash = e.file_name().to_string_lossy().to_string();
            if reachable.contains(&hash) {
                marked += 1;
                continue;
            }

            let tomb = tombstone_dir.join(&hash);
            let idx = tombstone_index_dir.join(format!("{}.json", hash));
            if !dry_run {
                if tomb.exists() {
                    std::fs::remove_dir_all(&tomb).map_err(|e| io_err(&tomb, e))?;
                }
                std::fs::rename(&p, &tomb).map_err(|e| io_err(&p, e))?;
                write_json_atomic(
                    &idx,
                    &TombstoneEntry {
                        object_kind: "candidate".to_string(),
                        object_hash: hash.clone(),
                        tombstoned_at_unix_s: now_s,
                        grace_days: DEFAULT_TOMBSTONE_DAYS,
                    },
                )?;
            }
            tombstoned += 1;
        }
    }

    // Aggressive ephemeral policy: sweep immediately after tombstoning.
    let _sweep = sweep_tombstones(root, dry_run, DEFAULT_TOMBSTONE_DAYS)?;

    let report = GcReport {
        dry_run,
        tombstone_days: DEFAULT_TOMBSTONE_DAYS,
        candidates_marked: marked,
        candidates_marked_reachable: marked,
        candidates_tombstoned: tombstoned,
        tombstones_existing: count_entries(&tombstone_index_dir)?,
    };
    write_json_atomic(&root.join("archives").join("gc_last_report.json"), &report)?;
    Ok(report)
}

pub fn sweep_tombstones(
    root: &Path,
    dry_run: bool,
    tombstone_days: u64,
) -> Result<TombstoneSweepReport> {
    let now_s = crate::apfsc::prod::jobs::now_unix_s();
    let idx_dir = tombstone_index_dir(root);
    let tomb_dir = tombstone_candidates_dir(root);
    std::fs::create_dir_all(&idx_dir).map_err(|e| io_err(&idx_dir, e))?;
    std::fs::create_dir_all(&tomb_dir).map_err(|e| io_err(&tomb_dir, e))?;

    let grace_s = tombstone_days.saturating_mul(86_400);
    let mut eligible = 0usize;
    let mut deleted = 0usize;
    for e in std::fs::read_dir(&idx_dir).map_err(|e| io_err(&idx_dir, e))? {
        let e = e.map_err(|e| io_err(&idx_dir, e))?;
        let p = e.path();
        if !e.file_type().map_err(|e| io_err(&p, e))?.is_file() {
            continue;
        }
        let entry: TombstoneEntry = read_json(&p)?;
        if now_s.saturating_sub(entry.tombstoned_at_unix_s) < grace_s {
            continue;
        }
        eligible += 1;
        if !dry_run {
            let obj = tomb_dir.join(&entry.object_hash);
            if obj.exists() {
                std::fs::remove_dir_all(&obj).map_err(|e| io_err(&obj, e))?;
            }
            std::fs::remove_file(&p).map_err(|e| io_err(&p, e))?;
            deleted += 1;
        }
    }

    let report = TombstoneSweepReport {
        dry_run,
        tombstone_days,
        eligible_for_delete: eligible,
        deleted,
    };
    write_json_atomic(
        &root
            .join("archives")
            .join("gc_tombstone_sweep_last_report.json"),
        &report,
    )?;
    Ok(report)
}

fn reachable_candidate_set(root: &Path) -> Result<BTreeSet<String>> {
    let mut out = BTreeSet::<String>::new();
    for p in [
        "active_candidate",
        "active_incubator_pointer",
        "rollback_candidate",
        "active_constellation",
        "active_snapshot",
    ] {
        if let Ok(v) = read_pointer(root, p) {
            let candidate_dir = root.join("candidates").join(&v);
            if candidate_dir.exists() {
                collect_candidate_ancestors(root, &v, &mut out)?;
            }
        }
    }
    Ok(out)
}

fn collect_candidate_ancestors(
    root: &Path,
    candidate_hash: &str,
    out: &mut BTreeSet<String>,
) -> Result<()> {
    if !out.insert(candidate_hash.to_string()) {
        return Ok(());
    }
    let manifest_path = root
        .join("candidates")
        .join(candidate_hash)
        .join("manifest.json");
    if !manifest_path.exists() {
        return Ok(());
    }
    let manifest: CandidateManifest = read_json(&manifest_path)?;
    for parent in manifest.parent_hashes {
        collect_candidate_ancestors(root, &parent, out)?;
    }
    Ok(())
}

fn count_entries(root: &Path) -> Result<usize> {
    if !root.exists() {
        return Ok(0);
    }
    let mut n = 0usize;
    for e in std::fs::read_dir(root).map_err(|e| io_err(root, e))? {
        let e = e.map_err(|e| io_err(root, e))?;
        let p = e.path();
        if e.file_type().map_err(|e| io_err(&p, e))?.is_file() {
            n += 1;
        }
    }
    Ok(n)
}

fn tombstone_candidates_dir(root: &Path) -> std::path::PathBuf {
    root.join("artifacts").join("tombstones").join("candidates")
}

fn tombstone_index_dir(root: &Path) -> std::path::PathBuf {
    root.join("artifacts")
        .join("tombstones")
        .join("index")
        .join("candidates")
}
