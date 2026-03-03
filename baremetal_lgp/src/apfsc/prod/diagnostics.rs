use std::collections::BTreeMap;
use std::path::{Path, PathBuf};
use std::time::UNIX_EPOCH;

use crate::apfsc::artifacts::{read_pointer, write_json_atomic};
use crate::apfsc::errors::{io_err, Result};
use crate::apfsc::prod::buildinfo::current_build_info;
use crate::apfsc::prod::health::health_report;
use crate::apfsc::prod::telemetry::Telemetry;
use crate::apfsc::types::SearchLawAbReceipt;

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize, PartialEq)]
pub struct DiagnosticsBundle {
    pub bundle_dir: String,
    pub build_info_path: String,
    pub health_path: String,
    pub telemetry_path: String,
    pub pointers_path: String,
    pub class_g_ab_summary_path: String,
}

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize, PartialEq)]
pub struct ClassGAbSummary {
    pub window_size: usize,
    pub total_receipts: usize,
    pub ab_pass: usize,
    pub ab_insufficient_yield: usize,
    pub other_reasons: BTreeMap<String, usize>,
}

fn class_g_ab_summary(root: &Path, window_size: usize) -> Result<ClassGAbSummary> {
    let mut paths = Vec::<(u64, PathBuf)>::new();
    let laws = root.join("search_laws");
    if laws.exists() {
        for e in std::fs::read_dir(&laws).map_err(|err| io_err(&laws, err))? {
            let e = e.map_err(|err| io_err(&laws, err))?;
            let dir = e.path();
            if !e.file_type().map_err(|err| io_err(&dir, err))?.is_dir() {
                continue;
            }
            let ab = dir.join("ab_eval_receipt.json");
            if !ab.exists() {
                continue;
            }
            let modified = std::fs::metadata(&ab)
                .map_err(|err| io_err(&ab, err))?
                .modified()
                .ok()
                .and_then(|t| t.duration_since(UNIX_EPOCH).ok())
                .map(|d| d.as_secs())
                .unwrap_or(0);
            paths.push((modified, ab));
        }
    }
    paths.sort_by(|a, b| b.0.cmp(&a.0));

    let mut summary = ClassGAbSummary {
        window_size,
        total_receipts: 0,
        ab_pass: 0,
        ab_insufficient_yield: 0,
        other_reasons: BTreeMap::new(),
    };
    for (_, p) in paths.into_iter().take(window_size) {
        let data = match std::fs::read(&p) {
            Ok(v) => v,
            Err(_) => continue,
        };
        let receipt = match serde_json::from_slice::<SearchLawAbReceipt>(&data) {
            Ok(r) => r,
            Err(_) => continue,
        };
        summary.total_receipts += 1;
        if receipt.reason == "ABPass" {
            summary.ab_pass += 1;
        } else if receipt.reason == "ABInsufficientYield" {
            summary.ab_insufficient_yield += 1;
        } else {
            *summary.other_reasons.entry(receipt.reason).or_insert(0) += 1;
        }
    }
    Ok(summary)
}

pub fn dump_diagnostics(root: &Path, telemetry: &Telemetry) -> Result<DiagnosticsBundle> {
    let ts = crate::apfsc::prod::jobs::now_unix_s();
    let dir = root.join("diagnostics").join(format!("diag-{}", ts));
    std::fs::create_dir_all(&dir).map_err(|e| io_err(&dir, e))?;

    let build = dir.join("buildinfo.json");
    let health = dir.join("health.json");
    let telem = dir.join("telemetry.json");
    let pointers = dir.join("pointers.json");
    let class_g_ab = dir.join("class_g_ab_summary.json");

    write_json_atomic(&build, &current_build_info())?;
    write_json_atomic(&health, &health_report(root)?)?;
    write_json_atomic(&telem, &telemetry.snapshot())?;

    let mut map = std::collections::BTreeMap::<String, String>::new();
    for p in [
        "active_candidate",
        "active_incubator_pointer",
        "active_incubator_search_law",
        "active_epoch_mode",
        "active_era",
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
    write_json_atomic(&class_g_ab, &class_g_ab_summary(root, 100)?)?;

    Ok(DiagnosticsBundle {
        bundle_dir: dir.display().to_string(),
        build_info_path: build.display().to_string(),
        health_path: health.display().to_string(),
        telemetry_path: telem.display().to_string(),
        pointers_path: pointers.display().to_string(),
        class_g_ab_summary_path: class_g_ab.display().to_string(),
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
