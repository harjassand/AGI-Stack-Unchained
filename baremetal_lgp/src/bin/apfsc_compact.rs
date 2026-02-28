use std::path::PathBuf;

use baremetal_lgp::apfsc::prod::compaction::compact_archives;
use clap::Parser;

#[derive(Debug, Parser)]
struct Args {
    #[arg(long, default_value = ".apfsc")]
    root: PathBuf,
    #[arg(long)]
    dry_run: bool,
}

fn main() -> Result<(), String> {
    let args = Args::parse();
    let r = compact_archives(&args.root, args.dry_run).map_err(|e| e.to_string())?;
    println!(
        "{}",
        serde_json::to_string_pretty(&r).map_err(|e| e.to_string())?
    );
    Ok(())
}
