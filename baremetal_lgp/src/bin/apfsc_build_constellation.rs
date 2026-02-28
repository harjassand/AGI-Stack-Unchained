use std::path::PathBuf;

use baremetal_lgp::apfsc::config::Phase1Config;
use baremetal_lgp::apfsc::constellation::{build_constellation, pack_hashes_from_snapshot};
use clap::Parser;

#[derive(Debug, Parser)]
struct Args {
    #[arg(long, default_value = ".apfsc")]
    root: PathBuf,
    #[arg(long)]
    snapshot: Option<String>,
    #[arg(long = "pack")]
    packs: Vec<String>,
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

    let snapshot = if let Some(s) = args.snapshot {
        s
    } else {
        baremetal_lgp::apfsc::artifacts::read_pointer(&args.root, "active_snapshot")
            .map_err(|e| e.to_string())?
    };

    let packs = if args.packs.is_empty() {
        pack_hashes_from_snapshot(&args.root, &snapshot).map_err(|e| e.to_string())?
    } else {
        args.packs
    };

    let manifest =
        build_constellation(&args.root, &cfg, &snapshot, &packs).map_err(|e| e.to_string())?;
    println!(
        "constellation={} families={} snapshot={}",
        manifest.constellation_id,
        manifest.family_specs.len(),
        manifest.snapshot_hash
    );
    Ok(())
}
