use std::path::{Path, PathBuf};

use crate::apfsc::artifacts::{read_pointer, write_json_atomic};
use crate::apfsc::errors::{io_err, Result};
use crate::apfsc::prod::buildinfo::current_build_info;
use crate::apfsc::prod::health::health_report;
use crate::apfsc::prod::telemetry::Telemetry;

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize, PartialEq)]
pub struct DiagnosticsBundle {
    pub bundle_dir: String,
    pub build_info_path: String,
    pub health_path: String,
    pub telemetry_path: String,
    pub pointers_path: String,
}

pub fn dump_diagnostics(root: &Path, telemetry: &Telemetry) -> Result<DiagnosticsBundle> {
    let ts = crate::apfsc::prod::jobs::now_unix_s();
    let dir = root.join("diagnostics").join(format!("diag-{}", ts));
    std::fs::create_dir_all(&dir).map_err(|e| io_err(&dir, e))?;

    let build = dir.join("buildinfo.json");
    let health = dir.join("health.json");
    let telem = dir.join("telemetry.json");
    let pointers = dir.join("pointers.json");

    write_json_atomic(&build, &current_build_info())?;
    write_json_atomic(&health, &health_report(root)?)?;
    write_json_atomic(&telem, &telemetry.snapshot())?;

    let mut map = std::collections::BTreeMap::<String, String>::new();
    for p in [
        "active_candidate",
        "rollback_candidate",
        "active_constellation",
        "active_snapshot",
        "active_search_law",
        "active_formal_policy",
    ] {
        if let Ok(v) = read_pointer(root, p) {
            map.insert(p.to_string(), v);
        }
    }
    write_json_atomic(&pointers, &map)?;

    Ok(DiagnosticsBundle {
        bundle_dir: dir.display().to_string(),
        build_info_path: build.display().to_string(),
        health_path: health.display().to_string(),
        telemetry_path: telem.display().to_string(),
        pointers_path: pointers.display().to_string(),
    })
}

pub fn latest_diagnostics_bundle(root: &Path) -> Result<Option<PathBuf>> {
    let d = root.join("diagnostics");
    if !d.exists() {
        return Ok(None);
    }
    let mut dirs = Vec::new();
    for e in std::fs::read_dir(&d).map_err(|e| io_err(&d, e))? {
        let e = e.map_err(|e| io_err(&d, e))?;
        let p = e.path();
        if e.file_type().map_err(|e| io_err(&p, e))?.is_dir() {
            dirs.push(p);
        }
    }
    dirs.sort();
    Ok(dirs.pop())
}
