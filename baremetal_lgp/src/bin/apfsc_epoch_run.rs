use std::path::PathBuf;

use baremetal_lgp::apfsc::config::Phase1Config;
use baremetal_lgp::apfsc::orchestrator::run_epoch;
use clap::Parser;

#[derive(Debug, Parser)]
struct Args {
    #[arg(long, default_value = ".apfsc")]
    root: PathBuf,
    #[arg(long)]
    config: Option<PathBuf>,
    #[arg(long, default_value_t = 1)]
    epochs: u32,
}

fn main() -> Result<(), String> {
    let args = Args::parse();
    let cfg = if let Some(path) = &args.config {
        Phase1Config::from_path(path).map_err(|e| e.to_string())?
    } else {
        Phase1Config::default()
    };

    for i in 0..args.epochs {
        let report = run_epoch(&args.root, &cfg).map_err(|e| e.to_string())?;
        println!(
            "epoch={} public={} judge={} canary={}",
            i + 1,
            report.public_receipts.len(),
            report.judge_report.receipts.len(),
            report.canary_report.evaluated.len()
        );
    }
    Ok(())
}
