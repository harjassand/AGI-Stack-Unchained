use std::fs;
use std::path::PathBuf;

use baremetal_lgp::apfsc::bank::{load_bank, WindowBank};
use baremetal_lgp::apfsc::canary::drain_queue;
use baremetal_lgp::apfsc::config::Phase1Config;
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
    let banks = load_all_banks(&args.root).map_err(|e| e.to_string())?;
    let report = drain_queue(&args.root, &banks, &cfg).map_err(|e| e.to_string())?;
    println!(
        "canary evaluated={} activated={}",
        report.evaluated.len(),
        report.activated.unwrap_or_else(|| "none".to_string())
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
