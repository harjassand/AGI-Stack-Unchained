use std::path::PathBuf;

use baremetal_lgp::apfsc::artifacts::{read_pointer, write_json_atomic};
use baremetal_lgp::apfsc::tool_shadow::{
    evaluate_tool_shadow, write_candidate_tool_shadow_receipt,
};
use clap::Parser;

#[derive(Debug, Parser)]
struct Args {
    #[arg(long, default_value = ".apfsc")]
    root: PathBuf,
    #[arg(long)]
    toolpack: String,
    #[arg(long)]
    candidate: Option<String>,
}

fn main() -> Result<(), String> {
    let args = Args::parse();
    let snapshot = read_pointer(&args.root, "active_snapshot").map_err(|e| e.to_string())?;
    let constellation = read_pointer(&args.root, "active_constellation").unwrap_or_default();
    let protocol = "apfsc-phase4-final-v1".to_string();

    let receipt = evaluate_tool_shadow(
        &args.root,
        &args.toolpack,
        args.candidate.as_deref(),
        &snapshot,
        &constellation,
        &protocol,
    )
    .map_err(|e| e.to_string())?;

    let tdir = args.root.join("toolpacks").join(&args.toolpack);
    write_json_atomic(&tdir.join("microbench_receipt.json"), &receipt)
        .map_err(|e| e.to_string())?;
    if let Some(ch) = &args.candidate {
        write_candidate_tool_shadow_receipt(&args.root, ch, &receipt).map_err(|e| e.to_string())?;
    }
    println!(
        "tool shadow toolpack={} status={:?}",
        args.toolpack, receipt.status
    );
    Ok(())
}
