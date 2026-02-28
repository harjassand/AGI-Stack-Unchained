use std::path::PathBuf;

use baremetal_lgp::apfsc::candidate::load_candidate;
use baremetal_lgp::apfsc::constellation::resolve_constellation;
use baremetal_lgp::apfsc::transfer::evaluate_transfer;
use baremetal_lgp::apfsc::types::EvalMode;
use clap::Parser;

#[derive(Debug, Parser)]
struct Args {
    #[arg(long, default_value = ".apfsc")]
    root: PathBuf,
    #[arg(long)]
    candidate: String,
    #[arg(long)]
    incumbent: String,
    #[arg(long)]
    snapshot: Option<String>,
    #[arg(long)]
    constellation: Option<String>,
    #[arg(long, default_value = "public")]
    mode: String,
}

fn parse_mode(v: &str) -> Result<EvalMode, String> {
    match v {
        "public" => Ok(EvalMode::Public),
        "holdout" => Ok(EvalMode::Holdout),
        other => Err(format!("unknown mode: {other}")),
    }
}

fn main() -> Result<(), String> {
    let args = Args::parse();
    let mode = parse_mode(&args.mode)?;
    let cand = load_candidate(&args.root, &args.candidate).map_err(|e| e.to_string())?;
    let inc = load_candidate(&args.root, &args.incumbent).map_err(|e| e.to_string())?;

    if let Some(snapshot) = args.snapshot {
        if cand.manifest.snapshot_hash != snapshot || inc.manifest.snapshot_hash != snapshot {
            return Err("candidate/incumbent snapshot mismatch".to_string());
        }
    }

    let constellation = resolve_constellation(&args.root, args.constellation.as_deref())
        .map_err(|e| e.to_string())?;
    let eval = evaluate_transfer(&args.root, &cand, &inc, &constellation, mode)
        .map_err(|e| e.to_string())?;

    let lane = match mode {
        EvalMode::Public => "public_transfer",
        EvalMode::Holdout => "holdout_transfer",
    };
    baremetal_lgp::apfsc::artifacts::write_json_atomic(
        &baremetal_lgp::apfsc::artifacts::receipt_path(
            &args.root,
            lane,
            &format!("{}.json", cand.manifest.candidate_hash),
        ),
        &eval.receipt,
    )
    .map_err(|e| e.to_string())?;

    println!(
        "candidate={} weighted_delta_bpb={:.6}",
        cand.manifest.candidate_hash, eval.delta_bpb
    );
    Ok(())
}
