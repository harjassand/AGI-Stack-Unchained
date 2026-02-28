use std::fs;
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

use crate::apf3::morphisms::ArchitectureDiff;

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ProposalReject {
    pub reasons: Vec<String>,
}

pub fn load_proposals(dir: &Path) -> Result<Vec<(PathBuf, ArchitectureDiff)>, String> {
    if !dir.exists() {
        return Ok(Vec::new());
    }

    let mut files = fs::read_dir(dir)
        .map_err(|e| e.to_string())?
        .filter_map(|e| e.ok())
        .map(|e| e.path())
        .filter(|p| p.extension().and_then(|x| x.to_str()) == Some("json"))
        .collect::<Vec<_>>();
    files.sort();

    let mut out = Vec::new();
    for path in files {
        let body = fs::read(&path).map_err(|e| e.to_string())?;
        let diff: ArchitectureDiff =
            serde_json::from_slice(&body).map_err(|e| format!("{}: {e}", path.display()))?;
        out.push((path, diff));
    }

    Ok(out)
}

pub fn write_reject(path: &Path, reasons: &[String]) -> Result<(), String> {
    let reject = ProposalReject {
        reasons: reasons.to_vec(),
    };
    let body = serde_json::to_vec_pretty(&reject).map_err(|e| e.to_string())?;
    fs::write(path, body).map_err(|e| e.to_string())
}
