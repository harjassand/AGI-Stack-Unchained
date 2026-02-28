use std::path::Path;

use crate::apfsc::errors::{io_err, Result};

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize, PartialEq)]
pub struct CompactionReport {
    pub dry_run: bool,
    pub files_compacted: usize,
    pub bytes_before: u64,
    pub bytes_after: u64,
}

pub fn compact_archives(root: &Path, dry_run: bool) -> Result<CompactionReport> {
    let adir = root.join("archives");
    let mut files_compacted = 0usize;
    let mut before = 0u64;
    let mut after = 0u64;

    if adir.exists() {
        for e in std::fs::read_dir(&adir).map_err(|e| io_err(&adir, e))? {
            let e = e.map_err(|e| io_err(&adir, e))?;
            let p = e.path();
            if !p.extension().map(|x| x == "jsonl").unwrap_or(false) {
                continue;
            }
            let m = std::fs::metadata(&p).map_err(|e| io_err(&p, e))?;
            before += m.len();
            let compacted = p.with_extension("jsonl.zst");
            if !dry_run {
                let body = std::fs::read(&p).map_err(|e| io_err(&p, e))?;
                crate::apfsc::artifacts::write_bytes_atomic(&compacted, &body)?;
                std::fs::remove_file(&p).map_err(|e| io_err(&p, e))?;
                let m2 = std::fs::metadata(&compacted).map_err(|e| io_err(&compacted, e))?;
                after += m2.len();
            } else {
                after += m.len();
            }
            files_compacted += 1;
        }
    }

    Ok(CompactionReport {
        dry_run,
        files_compacted,
        bytes_before: before,
        bytes_after: after,
    })
}
