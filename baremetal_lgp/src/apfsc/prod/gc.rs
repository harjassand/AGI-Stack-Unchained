use std::collections::BTreeSet;
use std::path::Path;

use crate::apfsc::artifacts::{read_pointer, write_json_atomic};
use crate::apfsc::errors::{io_err, Result};

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize, PartialEq)]
pub struct GcReport {
    pub dry_run: bool,
    pub candidates_marked: usize,
    pub candidates_tombstoned: usize,
}

pub fn gc_candidates(root: &Path, dry_run: bool) -> Result<GcReport> {
    let mut roots = BTreeSet::<String>::new();
    for p in ["active_candidate", "rollback_candidate"] {
        if let Ok(v) = read_pointer(root, p) {
            roots.insert(v);
        }
    }

    let cdir = root.join("candidates");
    let tdir = root.join("artifacts").join("tombstones");
    std::fs::create_dir_all(&tdir).map_err(|e| io_err(&tdir, e))?;

    let mut marked = 0usize;
    let mut tombstoned = 0usize;
    if cdir.exists() {
        for e in std::fs::read_dir(&cdir).map_err(|e| io_err(&cdir, e))? {
            let e = e.map_err(|e| io_err(&cdir, e))?;
            let p = e.path();
            let h = e.file_name().to_string_lossy().to_string();
            if roots.contains(&h) {
                marked += 1;
                continue;
            }
            if !dry_run {
                let dest = tdir.join(&h);
                if dest.exists() {
                    std::fs::remove_dir_all(&dest).map_err(|e| io_err(&dest, e))?;
                }
                std::fs::rename(&p, &dest).map_err(|e| io_err(&p, e))?;
            }
            tombstoned += 1;
        }
    }

    let report = GcReport {
        dry_run,
        candidates_marked: marked,
        candidates_tombstoned: tombstoned,
    };
    write_json_atomic(&root.join("archives").join("gc_last_report.json"), &report)?;
    Ok(report)
}
