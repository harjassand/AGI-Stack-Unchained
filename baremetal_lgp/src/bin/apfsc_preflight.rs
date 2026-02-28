use std::path::PathBuf;

use baremetal_lgp::apfsc::prod::preflight::run_preflight;
use baremetal_lgp::apfsc::prod::profiles::{load_layered_config, resolve_paths};
use clap::Parser;

#[derive(Debug, Parser)]
struct Args {
    #[arg(long, default_value = "config/base.toml")]
    base_config: PathBuf,
    #[arg(long, default_value = "config/profiles/prod_single_node.toml")]
    profile_config: PathBuf,
    #[arg(long)]
    local_override: Option<PathBuf>,
}

fn main() -> Result<(), String> {
    let args = Args::parse();
    let cfg = load_layered_config(
        &args.base_config,
        &args.profile_config,
        args.local_override.as_deref(),
    )
    .map_err(|e| e.to_string())?;
    let (root, _, _) = resolve_paths(&cfg);
    let report = run_preflight(&root, &cfg).map_err(|e| e.to_string())?;
    println!(
        "{}",
        serde_json::to_string_pretty(&report).map_err(|e| e.to_string())?
    );
    if report.ok {
        Ok(())
    } else {
        Err("preflight failed".to_string())
    }
}
