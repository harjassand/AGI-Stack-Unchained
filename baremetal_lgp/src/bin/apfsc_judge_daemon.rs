use std::fs;
use std::path::PathBuf;

use baremetal_lgp::apfsc::bank::{load_bank, WindowBank};
use baremetal_lgp::apfsc::candidate::load_active_candidate;
use baremetal_lgp::apfsc::config::Phase1Config;
use baremetal_lgp::apfsc::judge::run_pending_batch;
use clap::Parser;

#[derive(Debug, Parser)]
struct Args {
    #[arg(long, default_value = ".apfsc")]
    root: PathBuf,
    #[arg(long)]
    config: Option<PathBuf>,
}

fn main() -> Result<(), String> {
    let args = Args::parse();
    let cfg = if let Some(path) = &args.config {
        Phase1Config::from_path(path).map_err(|e| e.to_string())?
    } else {
        Phase1Config::default()
    };

    let active = load_active_candidate(&args.root).map_err(|e| e.to_string())?;
    let banks = load_all_banks(&args.root).map_err(|e| e.to_string())?;
    let report = run_pending_batch(&args.root, &active, &banks, &cfg).map_err(|e| e.to_string())?;
    println!(
        "judge receipts={} queued_for_canary={}",
        report.receipts.len(),
        report.queued_for_canary.len()
    );
    Ok(())
}

fn load_all_banks(root: &PathBuf) -> baremetal_lgp::apfsc::Result<Vec<WindowBank>> {
    let dir = root.join("banks");
    if !dir.exists() {
        return Ok(Vec::new());
    }
    let mut out = Vec::new();
    let mut names = Vec::new();
    for entry in fs::read_dir(&dir).map_err(|e| baremetal_lgp::apfsc::errors::io_err(&dir, e))? {
        let entry = entry.map_err(|e| baremetal_lgp::apfsc::errors::io_err(&dir, e))?;
        if entry
            .file_type()
            .map_err(|e| baremetal_lgp::apfsc::errors::io_err(entry.path(), e))?
            .is_dir()
        {
            names.push(entry.file_name().to_string_lossy().to_string());
        }
    }
    names.sort();
    for family in names {
        out.push(load_bank(root, &family)?);
    }
    Ok(out)
}
