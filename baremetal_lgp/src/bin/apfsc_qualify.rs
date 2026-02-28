use std::path::PathBuf;

use baremetal_lgp::apfsc::prod::service::run_qualification;
use clap::Parser;

#[derive(Debug, Parser)]
struct Args {
    #[arg(long, default_value = ".apfsc")]
    root: PathBuf,
    #[arg(long, default_value = "release")]
    mode: String,
}

fn main() -> Result<(), String> {
    let args = Args::parse();
    let r = run_qualification(&args.root, &args.mode).map_err(|e| e.to_string())?;
    println!(
        "{}",
        serde_json::to_string_pretty(&r).map_err(|e| e.to_string())?
    );
    if r.passed {
        Ok(())
    } else {
        Err("qualification failed".to_string())
    }
}
