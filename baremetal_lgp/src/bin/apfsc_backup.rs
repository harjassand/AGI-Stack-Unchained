use std::path::PathBuf;

use baremetal_lgp::apfsc::prod::backup::{create_backup, verify_backup};
use baremetal_lgp::apfsc::prod::control_db::open_control_db;
use clap::{Parser, Subcommand};

#[derive(Debug, Subcommand)]
enum Cmd {
    Create,
    Verify { backup_id: String },
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
    let conn = open_control_db(&args.root.join("control/control.db")).map_err(|e| e.to_string())?;
    match args.cmd {
        Cmd::Create => {
            let m = create_backup(&args.root, &args.root.join("backups"), &conn)
                .map_err(|e| e.to_string())?;
            println!(
                "{}",
                serde_json::to_string_pretty(&m).map_err(|e| e.to_string())?
            );
        }
        Cmd::Verify { backup_id } => {
            let m = verify_backup(&args.root.join("backups").join(backup_id))
                .map_err(|e| e.to_string())?;
            println!(
                "{}",
                serde_json::to_string_pretty(&m).map_err(|e| e.to_string())?
            );
        }
    }
    Ok(())
}
