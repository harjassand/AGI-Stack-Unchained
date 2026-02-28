use std::fs;
use std::path::PathBuf;

use baremetal_lgp::apfsc::bank::{load_bank, WindowBank};
use baremetal_lgp::apfsc::canary::{drain_queue, run_phase3_canary};
use baremetal_lgp::apfsc::config::Phase1Config;
use clap::Parser;

#[derive(Debug, Parser)]
struct Args {
    #[arg(long, default_value = ".apfsc")]
    root: PathBuf,
    #[arg(long)]
    config: Option<PathBuf>,
    #[arg(long, default_value = "phase1")]
    profile: String,
    #[arg(long)]
    candidate: Option<String>,
    #[arg(long)]
    incumbent: Option<String>,
    #[arg(long)]
    constellation: Option<String>,
}

fn main() -> Result<(), String> {
    let args = Args::parse();
    let cfg = if let Some(path) = &args.config {
        Phase1Config::from_path(path).map_err(|e| e.to_string())?
    } else {
        Phase1Config::default()
    };
    if args.profile == "phase3" || args.profile == "phase4" {
        let candidate = args
            .candidate
            .ok_or_else(|| "--candidate is required for --profile phase3/phase4".to_string())?;
        let incumbent = if let Some(v) = args.incumbent {
            v
        } else {
            baremetal_lgp::apfsc::artifacts::read_pointer(&args.root, "active_candidate")
                .map_err(|e| e.to_string())?
        };
        let constellation = if let Some(v) = args.constellation {
            v
        } else {
            baremetal_lgp::apfsc::artifacts::read_pointer(&args.root, "active_constellation")
                .map_err(|e| e.to_string())?
        };
        let receipt = run_phase3_canary(
            &args.root,
            &candidate,
            &incumbent,
            &constellation,
            if args.profile == "phase4" {
                cfg.phase4.searchlaw_max_ab_epochs.max(1) * cfg.phase3.canary.warm_windows.min(32)
            } else {
                cfg.phase3.canary.warm_windows
            },
            &cfg,
        )
        .map_err(|e| e.to_string())?;
        println!(
            "canary pass={} reason={} candidate={}",
            receipt.pass, receipt.reason, receipt.candidate_hash
        );
    } else {
        let banks = load_all_banks(&args.root).map_err(|e| e.to_string())?;
        let report = drain_queue(&args.root, &banks, &cfg).map_err(|e| e.to_string())?;
        println!(
            "canary evaluated={} activated={}",
            report.evaluated.len(),
            report.activated.unwrap_or_else(|| "none".to_string())
        );
    }
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
