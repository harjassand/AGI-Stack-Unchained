use std::path::PathBuf;

use baremetal_lgp::apfsc::config::Phase1Config;
use baremetal_lgp::apfsc::recombination::materialize_recombination_candidate;
use clap::Parser;

#[derive(Debug, Parser)]
struct Args {
    #[arg(long, default_value = ".apfsc")]
    root: PathBuf,
    #[arg(long = "parent-a")]
    parent_a: String,
    #[arg(long = "parent-b")]
    parent_b: String,
    #[arg(long, default_value = "block_swap")]
    mode: String,
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
    let (cand, spec) = materialize_recombination_candidate(
        &args.root,
        &args.parent_a,
        &args.parent_b,
        &args.mode,
        &cfg,
    )
    .map_err(|e| e.to_string())?;
    println!(
        "recombined candidate={} mode={} compat={}",
        cand.manifest.candidate_hash, spec.merge_mode, spec.compatibility_hash
    );
    Ok(())
}
