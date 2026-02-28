use std::fs;
use std::path::PathBuf;

use baremetal_lgp::apfsc::bank::{load_bank, WindowBank};
use baremetal_lgp::apfsc::candidate::{load_active_candidate, load_candidate};
use baremetal_lgp::apfsc::config::Phase1Config;
use baremetal_lgp::apfsc::constellation::resolve_constellation;
use baremetal_lgp::apfsc::judge::{
    evaluate_phase2_candidate, judge_phase2_candidate, run_pending_batch,
};
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

    if args.profile == "phase2" {
        let candidate_hash = args
            .candidate
            .ok_or_else(|| "--candidate is required for phase2".to_string())?;
        let incumbent_hash = if let Some(v) = args.incumbent {
            v
        } else {
            baremetal_lgp::apfsc::artifacts::read_pointer(&args.root, "active_candidate")
                .map_err(|e| e.to_string())?
        };

        let candidate = load_candidate(&args.root, &candidate_hash).map_err(|e| e.to_string())?;
        let incumbent = load_candidate(&args.root, &incumbent_hash).map_err(|e| e.to_string())?;
        let constellation = resolve_constellation(&args.root, args.constellation.as_deref())
            .map_err(|e| e.to_string())?;

        let evals = evaluate_phase2_candidate(&args.root, &candidate, &incumbent, &constellation)
            .map_err(|e| e.to_string())?;
        let receipt = judge_phase2_candidate(
            &args.root,
            &candidate,
            &incumbent,
            &constellation,
            &cfg,
            &evals,
        )
        .map_err(|e| e.to_string())?;

        baremetal_lgp::apfsc::artifacts::write_json_atomic(
            &baremetal_lgp::apfsc::artifacts::receipt_path(
                &args.root,
                "judge",
                &format!("{}.json", candidate.manifest.candidate_hash),
            ),
            &receipt,
        )
        .map_err(|e| e.to_string())?;

        println!(
            "judge decision={} reason={}",
            match receipt.decision {
                baremetal_lgp::apfsc::types::JudgeDecision::Promote => "promote",
                baremetal_lgp::apfsc::types::JudgeDecision::Reject => "reject",
            },
            receipt.reason
        );
        return Ok(());
    }

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
        if root
            .join("banks")
            .join(&family)
            .join("manifest.json")
            .exists()
        {
            out.push(load_bank(root, &family)?);
        }
    }
    Ok(out)
}
