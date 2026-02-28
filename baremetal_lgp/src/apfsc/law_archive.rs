use std::collections::BTreeMap;
use std::path::Path;

use crate::apfsc::artifacts::{append_jsonl_atomic, digest_json, read_jsonl, write_json_atomic};
use crate::apfsc::errors::Result;
use crate::apfsc::types::{LawArchiveRecord, LawArchiveSummary};

pub fn append_record(root: &Path, mut rec: LawArchiveRecord) -> Result<LawArchiveRecord> {
    if rec.record_id.is_empty() {
        rec.record_id = digest_json(&(
            rec.candidate_hash.clone(),
            rec.searchlaw_hash.clone(),
            rec.snapshot_hash.clone(),
            rec.constellation_id.clone(),
        ))?;
    }
    append_jsonl_atomic(&root.join("archive/law_archive.jsonl"), &rec)?;
    append_jsonl_atomic(&root.join("archives/law_archive.jsonl"), &rec)?;
    Ok(rec)
}

pub fn load_records(root: &Path) -> Result<Vec<LawArchiveRecord>> {
    let mut rows: Vec<LawArchiveRecord> = read_jsonl(&root.join("archive/law_archive.jsonl"))?;
    rows.sort_by(|a, b| a.record_id.cmp(&b.record_id));
    Ok(rows)
}

pub fn build_summary(root: &Path, active_searchlaw_hash: &str) -> Result<LawArchiveSummary> {
    let rows = load_records(root)?;
    let mut failure = BTreeMap::<String, u64>::new();
    let mut qd = BTreeMap::<String, u64>::new();
    let mut stale = BTreeMap::<String, i64>::new();

    for r in &rows {
        if r.challenge_bucket < 0 {
            *failure.entry("challenge_regress".to_string()).or_insert(0) += 1;
        }
        if r.yield_points == 0 {
            *failure.entry("zero_yield".to_string()).or_insert(0) += 1;
        }
        *qd.entry(r.qd_cell_id.clone()).or_insert(0) += 1;
        for (f, b) in &r.family_outcome_buckets {
            if *b <= 0 {
                *stale.entry(f.clone()).or_insert(0) += 1;
            }
        }
    }

    let mut dominant_failure_modes: Vec<String> = failure.keys().cloned().collect();
    dominant_failure_modes.sort();

    let mut underfilled_qd_cells = Vec::new();
    for (cell, c) in qd {
        if c <= 1 {
            underfilled_qd_cells.push(cell);
        }
    }
    underfilled_qd_cells.sort();

    let mut stale_family_ids: Vec<String> = stale
        .into_iter()
        .filter(|(_, v)| *v > 0)
        .map(|(k, _)| k)
        .collect();
    stale_family_ids.sort();

    let summary = LawArchiveSummary {
        total_records: rows.len() as u64,
        total_tokens: 0,
        active_searchlaw_hash: active_searchlaw_hash.to_string(),
        dominant_failure_modes,
        underfilled_qd_cells,
        stale_family_ids,
    };

    let hash = digest_json(&summary)?;
    let dir = root.join("law_archive").join(hash);
    std::fs::create_dir_all(&dir).map_err(|e| crate::apfsc::errors::io_err(&dir, e))?;
    write_json_atomic(&dir.join("summary.json"), &summary)?;

    Ok(summary)
}
