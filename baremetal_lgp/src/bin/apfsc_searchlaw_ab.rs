use std::path::PathBuf;

use baremetal_lgp::apfsc::config::Phase1Config;
use baremetal_lgp::apfsc::constellation::load_active_constellation;
use baremetal_lgp::apfsc::law_archive::load_records;
use baremetal_lgp::apfsc::search_law::load_search_law;
use baremetal_lgp::apfsc::searchlaw_eval::{evaluate_searchlaw_ab, evaluate_searchlaw_offline};
use clap::Parser;

#[derive(Debug, Parser)]
struct Args {
    #[arg(long, default_value = ".apfsc")]
    root: PathBuf,
    #[arg(long)]
    candidate: String,
    #[arg(long)]
    incumbent: String,
    #[arg(long, default_value_t = 2)]
    epochs: u32,
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
    let cand = load_search_law(&args.root, &args.candidate).map_err(|e| e.to_string())?;
    let inc = load_search_law(&args.root, &args.incumbent).map_err(|e| e.to_string())?;
    let records = load_records(&args.root).map_err(|e| e.to_string())?;
    let constellation = load_active_constellation(&args.root).map_err(|e| e.to_string())?;
    let offline = evaluate_searchlaw_offline(
        &args.root,
        &cand,
        &records,
        &constellation.snapshot_hash,
        &constellation.constellation_id,
        &cfg.protocol.version,
    )
    .map_err(|e| e.to_string())?;
    let ab = evaluate_searchlaw_ab(
        &args.root,
        &cand,
        &inc,
        &offline,
        &records,
        args.epochs,
        &cfg,
        &constellation.snapshot_hash,
        &constellation.constellation_id,
        &cfg.protocol.version,
    )
    .map_err(|e| e.to_string())?;
    println!(
        "ab candidate={} incumbent={} pass={} ypc_cand={:.6} ypc_inc={:.6}",
        ab.candidate_searchlaw_hash,
        ab.incumbent_searchlaw_hash,
        ab.pass,
        ab.candidate_yield_per_compute,
        ab.incumbent_yield_per_compute
    );
    Ok(())
}
