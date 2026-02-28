use std::path::PathBuf;

use baremetal_lgp::apfsc::config::Phase1Config;
use baremetal_lgp::apfsc::ingress::substrate::ingest_substrate;
use clap::Parser;

#[derive(Debug, Parser)]
struct Args {
    #[arg(long, default_value = ".apfsc")]
    root: PathBuf,
    #[arg(long)]
    manifest: PathBuf,
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
    let receipt = ingest_substrate(&args.root, &cfg, &args.manifest).map_err(|e| e.to_string())?;
    println!("ingested substrate pack {}", receipt.pack_hash);
    Ok(())
}
