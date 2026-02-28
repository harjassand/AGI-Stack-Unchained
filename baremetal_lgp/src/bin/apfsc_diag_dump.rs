use std::path::PathBuf;

use baremetal_lgp::apfsc::prod::diagnostics::dump_diagnostics;
use baremetal_lgp::apfsc::prod::telemetry::Telemetry;
use clap::Parser;

#[derive(Debug, Parser)]
struct Args {
    #[arg(long, default_value = ".apfsc")]
    root: PathBuf,
}

fn main() -> Result<(), String> {
    let args = Args::parse();
    let t = Telemetry::default();
    let b = dump_diagnostics(&args.root, &t).map_err(|e| e.to_string())?;
    println!(
        "{}",
        serde_json::to_string_pretty(&b).map_err(|e| e.to_string())?
    );
    Ok(())
}
