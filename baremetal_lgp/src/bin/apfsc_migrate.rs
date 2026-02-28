use std::path::PathBuf;

use baremetal_lgp::apfsc::prod::migration::migrate_control_db;
use clap::Parser;

#[derive(Debug, Parser)]
struct Args {
    #[arg(long, default_value = ".apfsc/control/control.db")]
    control_db: PathBuf,
    #[arg(long)]
    from: u32,
    #[arg(long)]
    to: u32,
    #[arg(long)]
    dry_run: bool,
}

fn main() -> Result<(), String> {
    let a = Args::parse();
    migrate_control_db(&a.control_db, a.from, a.to, a.dry_run).map_err(|e| e.to_string())
}
