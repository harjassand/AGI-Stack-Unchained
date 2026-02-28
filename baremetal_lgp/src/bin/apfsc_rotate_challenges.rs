use std::path::PathBuf;

use baremetal_lgp::apfsc::config::Phase1Config;
use baremetal_lgp::apfsc::retirement::{rotate_hidden_challenges, rotate_hidden_challenges_for};
use clap::Parser;

#[derive(Debug, Parser)]
struct Args {
    #[arg(long, default_value = ".apfsc")]
    root: PathBuf,
    #[arg(long)]
    snapshot: Option<String>,
    #[arg(long)]
    constellation: Option<String>,
    #[arg(long)]
    config: Option<PathBuf>,
    #[arg(long, default_value_t = 0)]
    epoch: u64,
}

fn main() -> Result<(), String> {
    let args = Args::parse();
    let cfg = if let Some(path) = &args.config {
        Phase1Config::from_path(path).map_err(|e| e.to_string())?
    } else {
        Phase1Config::default()
    };
    let manifest = match (&args.snapshot, &args.constellation) {
        (Some(snapshot), Some(constellation)) => {
            rotate_hidden_challenges_for(&args.root, &cfg, snapshot, constellation, args.epoch)
                .map_err(|e| e.to_string())?
        }
        (None, None) => {
            rotate_hidden_challenges(&args.root, &cfg, args.epoch).map_err(|e| e.to_string())?
        }
        _ => {
            return Err("both --snapshot and --constellation must be provided together".to_string())
        }
    };
    println!(
        "challenge manifest={} active={} retired={}",
        manifest.manifest_hash,
        manifest.active_hidden_families.len(),
        manifest.retired_hidden_families.len()
    );
    Ok(())
}
