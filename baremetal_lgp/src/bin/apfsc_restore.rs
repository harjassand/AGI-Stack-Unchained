use std::path::PathBuf;

use baremetal_lgp::apfsc::prod::restore::{restore_apply, restore_dry_run};
use clap::{Parser, Subcommand};

#[derive(Debug, Subcommand)]
enum Cmd {
    DryRun { backup_id: String },
    Apply { backup_id: String },
}

#[derive(Debug, Parser)]
struct Args {
    #[arg(long, default_value = ".apfsc")]
    root: PathBuf,
    #[command(subcommand)]
    cmd: Cmd,
}

fn main() -> Result<(), String> {
    let args = Args::parse();
    match args.cmd {
        Cmd::DryRun { backup_id } => {
            let r = restore_dry_run(&args.root.join("backups").join(backup_id))
                .map_err(|e| e.to_string())?;
            println!(
                "{}",
                serde_json::to_string_pretty(&r).map_err(|e| e.to_string())?
            );
        }
        Cmd::Apply { backup_id } => {
            let r = restore_apply(&args.root.join("backups").join(backup_id), &args.root)
                .map_err(|e| e.to_string())?;
            println!(
                "{}",
                serde_json::to_string_pretty(&r).map_err(|e| e.to_string())?
            );
        }
    }
    Ok(())
}
