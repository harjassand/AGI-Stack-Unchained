use std::path::PathBuf;

use baremetal_lgp::apfsc::constellation::load_active_constellation;
use baremetal_lgp::apfsc::law_archive::load_records;
use baremetal_lgp::apfsc::search_law::load_search_law;
use baremetal_lgp::apfsc::searchlaw_eval::evaluate_searchlaw_offline;
use clap::Parser;

#[derive(Debug, Parser)]
struct Args {
    #[arg(long, default_value = ".apfsc")]
    root: PathBuf,
    #[arg(long)]
    searchlaw: String,
    #[arg(long)]
    archive: Option<String>,
}

fn main() -> Result<(), String> {
    let args = Args::parse();
    let law = load_search_law(&args.root, &args.searchlaw).map_err(|e| e.to_string())?;
    let records = load_records(&args.root).map_err(|e| e.to_string())?;
    let constellation = load_active_constellation(&args.root).map_err(|e| e.to_string())?;
    let receipt = evaluate_searchlaw_offline(
        &args.root,
        &law,
        &records,
        &constellation.snapshot_hash,
        &constellation.constellation_id,
        "apfsc-phase4-final-v1",
    )
    .map_err(|e| e.to_string())?;
    println!(
        "offline searchlaw={} pass={} ypc={:.6}",
        receipt.searchlaw_hash, receipt.pass, receipt.projected_yield_per_compute
    );
    Ok(())
}
