use std::path::PathBuf;

use baremetal_lgp::apfsc::prod::gc::gc_candidates;
use clap::Parser;

#[derive(Debug, Parser)]
struct Args {
    #[arg(long, default_value = ".apfsc")]
    root: PathBuf,
    #[arg(long)]
    apply: bool,
}

fn main() -> Result<(), String> {
    let args = Args::parse();
    let r = gc_candidates(&args.root, !args.apply).map_err(|e| e.to_string())?;
    println!(
        "{}",
        serde_json::to_string_pretty(&r).map_err(|e| e.to_string())?
    );
    Ok(())
}
