use std::path::PathBuf;

use baremetal_lgp::apfsc::config::Phase1Config;
use baremetal_lgp::apfsc::seed::seed_init;
use clap::Parser;

#[derive(Debug, Parser)]
struct Args {
    #[arg(long, default_value = ".apfsc")]
    root: PathBuf,
    #[arg(long, default_value = "phase1")]
    profile: String,
    #[arg(long)]
    fixtures: Option<PathBuf>,
    #[arg(long)]
    config: Option<PathBuf>,
    #[arg(long, default_value_t = false)]
    force: bool,
}

fn main() -> Result<(), String> {
    let args = Args::parse();
    if args.profile != "phase1" && args.profile != "phase2" {
        return Err(format!("unsupported profile: {}", args.profile));
    }
    let cfg = if let Some(path) = &args.config {
        Phase1Config::from_path(path).map_err(|e| e.to_string())?
    } else {
        Phase1Config::default()
    };

    let hash = seed_init(&args.root, &cfg, args.fixtures.as_deref(), args.force)
        .map_err(|e| e.to_string())?;
    println!("seed candidate: {hash}");
    Ok(())
}
