use std::fs;
use std::path::PathBuf;

use baremetal_lgp::apfsc::bank::{load_bank, WindowBank};
use baremetal_lgp::apfsc::candidate::load_candidate;
use baremetal_lgp::apfsc::constellation::resolve_constellation;
use baremetal_lgp::apfsc::judge::{evaluate_candidate_split, write_split_receipt};
use baremetal_lgp::apfsc::normalization::evaluate_static_panel;
use baremetal_lgp::apfsc::robustness::evaluate_robustness;
use baremetal_lgp::apfsc::transfer::evaluate_transfer;
use baremetal_lgp::apfsc::types::{EvalMode, PanelKind, SplitKind};
use clap::Parser;

#[derive(Debug, Parser)]
struct Args {
    #[arg(long, default_value = ".apfsc")]
    root: PathBuf,
    #[arg(long)]
    candidate: String,
    #[arg(long)]
    incumbent: Option<String>,
    #[arg(long)]
    constellation: Option<String>,
    #[arg(long, default_value = "phase1")]
    profile: String,
    #[arg(long, default_value = "static")]
    mode: String,
    #[arg(long, default_value = "public")]
    split: String,
}

fn main() -> Result<(), String> {
    let args = Args::parse();
    if args.profile == "phase2" || args.profile == "phase3" || args.profile == "phase4" {
        return run_phase2(args);
    }
    run_phase1(args)
}

fn run_phase1(args: Args) -> Result<(), String> {
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

fn run_phase2(args: Args) -> Result<(), String> {
    let candidate = load_candidate(&args.root, &args.candidate).map_err(|e| e.to_string())?;
    let incumbent_hash = args
        .incumbent
        .ok_or_else(|| "--incumbent is required for phase2".to_string())?;
    let incumbent = load_candidate(&args.root, &incumbent_hash).map_err(|e| e.to_string())?;
    let constellation = resolve_constellation(&args.root, args.constellation.as_deref())
        .map_err(|e| e.to_string())?;

    match args.mode.as_str() {
        "static" => {
            let cmp = evaluate_static_panel(
                &args.root,
                &candidate,
                &incumbent,
                &constellation,
                PanelKind::StaticPublic,
            )
            .map_err(|e| e.to_string())?;
            baremetal_lgp::apfsc::artifacts::write_json_atomic(
                &baremetal_lgp::apfsc::artifacts::receipt_path(
                    &args.root,
                    "public_static",
                    &format!("{}.json", candidate.manifest.candidate_hash),
                ),
                &cmp.receipt,
            )
            .map_err(|e| e.to_string())?;
            println!(
                "{} weighted_static_delta_bpb={:.6}",
                candidate.manifest.candidate_hash, cmp.delta_bpb
            );
        }
        "transfer" => {
            let eval = evaluate_transfer(
                &args.root,
                &candidate,
                &incumbent,
                &constellation,
                EvalMode::Public,
            )
            .map_err(|e| e.to_string())?;
            baremetal_lgp::apfsc::artifacts::write_json_atomic(
                &baremetal_lgp::apfsc::artifacts::receipt_path(
                    &args.root,
                    "public_transfer",
                    &format!("{}.json", candidate.manifest.candidate_hash),
                ),
                &eval.receipt,
            )
            .map_err(|e| e.to_string())?;
            println!(
                "{} weighted_transfer_delta_bpb={:.6}",
                candidate.manifest.candidate_hash, eval.delta_bpb
            );
        }
        "robust" => {
            let eval = evaluate_robustness(
                &args.root,
                &candidate,
                &incumbent,
                &constellation,
                EvalMode::Public,
            )
            .map_err(|e| e.to_string())?;
            baremetal_lgp::apfsc::artifacts::write_json_atomic(
                &baremetal_lgp::apfsc::artifacts::receipt_path(
                    &args.root,
                    "public_robust",
                    &format!("{}.json", candidate.manifest.candidate_hash),
                ),
                &eval.receipt,
            )
            .map_err(|e| e.to_string())?;
            println!(
                "{} weighted_robust_delta_bpb={:.6}",
                candidate.manifest.candidate_hash, eval.delta_bpb
            );
        }
        other => return Err(format!("unknown --mode for phase2: {other}")),
    }
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
        "robust_public" => Ok(SplitKind::RobustPublic),
        "robust_holdout" => Ok(SplitKind::RobustHoldout),
        "challenge_stub" => Ok(SplitKind::ChallengeStub),
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
