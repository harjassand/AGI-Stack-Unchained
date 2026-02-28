use std::fs;
use std::path::PathBuf;

use baremetal_lgp::apfsc::bank::{load_bank, WindowBank};
use baremetal_lgp::apfsc::candidate::load_candidate;
use baremetal_lgp::apfsc::judge::{evaluate_candidate_split, write_split_receipt};
use baremetal_lgp::apfsc::types::SplitKind;
use clap::Parser;

#[derive(Debug, Parser)]
struct Args {
    #[arg(long, default_value = ".apfsc")]
    root: PathBuf,
    #[arg(long)]
    candidate: String,
    #[arg(long, default_value = "public")]
    split: String,
}

fn main() -> Result<(), String> {
    let args = Args::parse();
    let candidate = load_candidate(&args.root, &args.candidate).map_err(|e| e.to_string())?;
    let banks = load_all_banks(&args.root).map_err(|e| e.to_string())?;
    let split = parse_split(&args.split)?;
    let receipt = evaluate_candidate_split(&args.root, &candidate, split, &banks)
        .map_err(|e| e.to_string())?;
    write_split_receipt(&args.root, &receipt).map_err(|e| e.to_string())?;
    println!(
        "{} total_bits={:.4}",
        receipt.candidate_hash, receipt.total_bits
    );
    Ok(())
}

fn parse_split(v: &str) -> Result<SplitKind, String> {
    match v {
        "public" => Ok(SplitKind::Public),
        "holdout" => Ok(SplitKind::Holdout),
        "anchor" => Ok(SplitKind::Anchor),
        "canary" => Ok(SplitKind::Canary),
        "train" => Ok(SplitKind::Train),
        "transfer_train" => Ok(SplitKind::TransferTrain),
        "transfer_eval" => Ok(SplitKind::TransferEval),
        other => Err(format!("unknown split: {other}")),
    }
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
