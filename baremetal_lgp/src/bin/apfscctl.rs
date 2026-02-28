use std::io::{Read, Write};
use std::os::unix::net::UnixStream;
use std::path::PathBuf;

use baremetal_lgp::apfsc::prod::control_api::{ControlCommand, ControlRequest, ControlResponse};
use clap::{Parser, Subcommand};

#[derive(Debug, Subcommand)]
enum IngestKind {
    Reality { manifest_path: String },
    Prior { manifest_path: String },
    Substrate { manifest_path: String },
    Formal { manifest_path: String },
    Tool { manifest_path: String },
}

#[derive(Debug, Subcommand)]
enum Cmd {
    Status,
    Health,
    Ingest {
        #[command(subcommand)]
        kind: IngestKind,
    },
    StartRun {
        #[arg(long, default_value = "phase4")]
        profile: String,
        #[arg(long, default_value_t = 1)]
        epochs: u32,
    },
    Pause,
    Resume,
    CancelRun {
        run_id: String,
    },
    BackupCreate,
    BackupVerify {
        backup_id: String,
    },
    RestoreDryRun {
        backup_id: String,
    },
    RestoreApply {
        backup_id: String,
    },
    GcDryRun,
    GcApply,
    Compact,
    Qualify {
        #[arg(long, default_value = "release")]
        mode: String,
    },
    DiagDump,
    ReleaseVerify {
        manifest_path: String,
    },
    ActiveShow,
    Rollback,
}

#[derive(Debug, Parser)]
struct Args {
    #[arg(long, default_value = ".apfsc/run/apfscd.sock")]
    socket: PathBuf,
    #[arg(long, default_value = "operator")]
    actor: String,
    #[arg(long)]
    token: Option<String>,
    #[command(subcommand)]
    cmd: Cmd,
}

fn main() -> Result<(), String> {
    let args = Args::parse();
    let command = match args.cmd {
        Cmd::Status => ControlCommand::Status,
        Cmd::Health => ControlCommand::Health,
        Cmd::Ingest { kind } => match kind {
            IngestKind::Reality { manifest_path } => {
                ControlCommand::IngestReality { manifest_path }
            }
            IngestKind::Prior { manifest_path } => ControlCommand::IngestPrior { manifest_path },
            IngestKind::Substrate { manifest_path } => {
                ControlCommand::IngestSubstrate { manifest_path }
            }
            IngestKind::Formal { manifest_path } => ControlCommand::IngestFormal { manifest_path },
            IngestKind::Tool { manifest_path } => ControlCommand::IngestTool { manifest_path },
        },
        Cmd::StartRun { profile, epochs } => ControlCommand::StartRun { profile, epochs },
        Cmd::Pause => ControlCommand::Pause,
        Cmd::Resume => ControlCommand::Resume,
        Cmd::CancelRun { run_id } => ControlCommand::CancelRun { run_id },
        Cmd::BackupCreate => ControlCommand::BackupCreate,
        Cmd::BackupVerify { backup_id } => ControlCommand::BackupVerify { backup_id },
        Cmd::RestoreDryRun { backup_id } => ControlCommand::RestoreDryRun { backup_id },
        Cmd::RestoreApply { backup_id } => ControlCommand::RestoreApply { backup_id },
        Cmd::GcDryRun => ControlCommand::GcDryRun,
        Cmd::GcApply => ControlCommand::GcApply,
        Cmd::Compact => ControlCommand::Compact,
        Cmd::Qualify { mode } => ControlCommand::Qualify { mode },
        Cmd::DiagDump => ControlCommand::DiagDump,
        Cmd::ReleaseVerify { manifest_path } => ControlCommand::ReleaseVerify { manifest_path },
        Cmd::ActiveShow => ControlCommand::ActiveShow,
        Cmd::Rollback => ControlCommand::Rollback,
    };

    let req = ControlRequest {
        request_id: format!("req-{}", baremetal_lgp::apfsc::prod::jobs::now_unix_s()),
        actor: args.actor,
        token: args.token,
        command,
    };

    let mut stream = UnixStream::connect(&args.socket).map_err(|e| e.to_string())?;
    let body = serde_json::to_vec(&req).map_err(|e| e.to_string())?;
    stream.write_all(&body).map_err(|e| e.to_string())?;
    stream
        .shutdown(std::net::Shutdown::Write)
        .map_err(|e| e.to_string())?;

    let mut out = Vec::new();
    stream.read_to_end(&mut out).map_err(|e| e.to_string())?;
    let resp: ControlResponse = serde_json::from_slice(&out).map_err(|e| e.to_string())?;
    println!(
        "{}",
        serde_json::to_string_pretty(&resp).map_err(|e| e.to_string())?
    );
    if resp.ok {
        Ok(())
    } else {
        Err(resp.message)
    }
}
