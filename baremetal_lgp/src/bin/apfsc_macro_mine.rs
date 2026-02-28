use std::path::PathBuf;

use baremetal_lgp::apfsc::config::Phase1Config;
use baremetal_lgp::apfsc::macro_mine::mine_macros;
use clap::Parser;

#[derive(Debug, Parser)]
struct Args {
    #[arg(long, default_value = ".apfsc")]
    root: PathBuf,
    #[arg(long)]
    snapshot: Option<String>,
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

    let (registry, receipts) = mine_macros(
        &args.root,
        &snapshot,
        &cfg.protocol.version,
        cfg.phase3.macro_cfg.min_macro_support,
        cfg.phase3.macro_cfg.min_macro_public_gain_bpb,
        cfg.phase3.macro_cfg.min_macro_reduction_ratio,
        cfg.phase3.macro_cfg.max_induced_macros_per_epoch,
    )
    .map_err(|e| e.to_string())?;

    println!(
        "macro_registry={} macro_defs={} induction_receipts={}",
        registry.registry_id,
        registry.macro_defs.len(),
        receipts.len()
    );
    Ok(())
}
