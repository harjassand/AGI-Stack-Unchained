use std::collections::BTreeMap;
use std::io::{Read, Write};
use std::os::unix::net::UnixStream;
use std::path::PathBuf;
use std::process::Command;

use baremetal_lgp::apfsc::artifacts::read_pointer;
use baremetal_lgp::apfsc::candidate::load_candidate;
use baremetal_lgp::apfsc::scir::ast::ScirOp;
use baremetal_lgp::apfsc::prod::control_api::{ControlCommand, ControlRequest, ControlResponse};
use clap::{Parser, Subcommand, ValueEnum};
use serde::Serialize;

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
    ForceClearRecovery,
    IngestExternal {
        #[arg(long, default_value = ".apfsc")]
        root: PathBuf,
        #[arg(long)]
        input: PathBuf,
        #[arg(long)]
        family_id: String,
        #[arg(long, value_enum, default_value_t = ExternalFormat::Auto)]
        format: ExternalFormat,
        #[arg(long, value_enum, default_value_t = ExternalFamilyKind::TextCodeLog)]
        family_kind: ExternalFamilyKind,
        #[arg(long, value_enum, default_value_t = ExternalRealityRole::Base)]
        role: ExternalRealityRole,
        #[arg(long)]
        variant_id: Option<String>,
        #[arg(long)]
        base_family_id: Option<String>,
        #[arg(long, default_value = "external_file")]
        source_name: String,
        #[arg(long, default_value = "filesystem")]
        source_type: String,
        #[arg(long)]
        description: Option<String>,
        #[arg(long, default_value_t = 1_048_576)]
        chunk_bytes: usize,
        #[arg(long)]
        config: Option<PathBuf>,
        #[arg(long)]
        out: Option<PathBuf>,
        #[arg(long, default_value_t = false)]
        ingest: bool,
    },
    DumpBrain {
        #[arg(long, default_value = ".apfsc")]
        root: PathBuf,
        #[arg(long, value_enum, default_value_t = BrainTarget::Active)]
        target: BrainTarget,
    },
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

#[derive(Debug, Clone, ValueEnum)]
enum ExternalFormat {
    Auto,
    Bin,
    Csv,
}

impl ExternalFormat {
    fn as_cli(&self) -> &'static str {
        match self {
            ExternalFormat::Auto => "auto",
            ExternalFormat::Bin => "bin",
            ExternalFormat::Csv => "csv",
        }
    }
}

#[derive(Debug, Clone, ValueEnum)]
enum ExternalFamilyKind {
    AlgorithmicSymbolic,
    TextCodeLog,
    SensoryTemporal,
    PhysicalSimulation,
}

impl ExternalFamilyKind {
    fn as_cli(&self) -> &'static str {
        match self {
            ExternalFamilyKind::AlgorithmicSymbolic => "algorithmic-symbolic",
            ExternalFamilyKind::TextCodeLog => "text-code-log",
            ExternalFamilyKind::SensoryTemporal => "sensory-temporal",
            ExternalFamilyKind::PhysicalSimulation => "physical-simulation",
        }
    }
}

#[derive(Debug, Clone, ValueEnum)]
enum ExternalRealityRole {
    Base,
    Transfer,
    Robust,
    ChallengeStub,
}

impl ExternalRealityRole {
    fn as_cli(&self) -> &'static str {
        match self {
            ExternalRealityRole::Base => "base",
            ExternalRealityRole::Transfer => "transfer",
            ExternalRealityRole::Robust => "robust",
            ExternalRealityRole::ChallengeStub => "challenge-stub",
        }
    }
}

#[derive(Debug, Clone, ValueEnum)]
enum BrainTarget {
    Active,
    Rollback,
}

#[derive(Debug, Clone, Serialize)]
struct DumpBrainReport {
    root: String,
    target: String,
    candidate_hash: String,
    candidate_path: String,
    arch_program_path: String,
    node_count: usize,
    operator_distribution: BTreeMap<String, u64>,
    ast_bytes: usize,
    ast_file_bytes: u64,
    arch_program_hash: String,
    promotion_class: String,
    lane: String,
    mutation_type: String,
}

fn main() -> Result<(), String> {
    let args = Args::parse();
    let Args {
        socket,
        actor,
        token,
        cmd,
    } = args;

    let command = match cmd {
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
        Cmd::ForceClearRecovery => ControlCommand::ForceClearRecovery,
        Cmd::IngestExternal {
            root,
            input,
            family_id,
            format,
            family_kind,
            role,
            variant_id,
            base_family_id,
            source_name,
            source_type,
            description,
            chunk_bytes,
            config,
            out,
            ingest,
        } => {
            return run_ingest_external(
                root,
                input,
                family_id,
                format,
                family_kind,
                role,
                variant_id,
                base_family_id,
                source_name,
                source_type,
                description,
                chunk_bytes,
                config,
                out,
                ingest,
            );
        }
        Cmd::DumpBrain { root, target } => {
            return run_dump_brain(root, target);
        }
    };

    let req = ControlRequest {
        request_id: format!("req-{}", baremetal_lgp::apfsc::prod::jobs::now_unix_s()),
        actor,
        token,
        command,
    };

    let mut stream = UnixStream::connect(&socket).map_err(|e| e.to_string())?;
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

fn run_dump_brain(root: PathBuf, target: BrainTarget) -> Result<(), String> {
    let target_ptr = match target {
        BrainTarget::Active => "active_candidate",
        BrainTarget::Rollback => "rollback_candidate",
    };
    let target_name = match target {
        BrainTarget::Active => "active",
        BrainTarget::Rollback => "rollback",
    };

    let candidate_hash = read_pointer(&root, target_ptr).map_err(|e| e.to_string())?;
    let bundle = load_candidate(&root, &candidate_hash).map_err(|e| e.to_string())?;

    let mut operator_distribution: BTreeMap<String, u64> = BTreeMap::new();
    for node in &bundle.arch_program.nodes {
        let key = scir_op_key(&node.op).to_string();
        *operator_distribution.entry(key).or_insert(0) += 1;
    }

    let ast_bytes = serde_json::to_vec(&bundle.arch_program)
        .map_err(|e| format!("failed to serialize arch program: {e}"))?
        .len();
    let arch_program_path = root
        .join("candidates")
        .join(&candidate_hash)
        .join("arch_program.json");
    let ast_file_bytes = std::fs::metadata(&arch_program_path)
        .map_err(|e| e.to_string())?
        .len();

    let report = DumpBrainReport {
        root: root.display().to_string(),
        target: target_name.to_string(),
        candidate_hash: candidate_hash.clone(),
        candidate_path: root.join("candidates").join(&candidate_hash).display().to_string(),
        arch_program_path: arch_program_path.display().to_string(),
        node_count: bundle.arch_program.nodes.len(),
        operator_distribution,
        ast_bytes,
        ast_file_bytes,
        arch_program_hash: bundle.manifest.arch_program_hash,
        promotion_class: format!("{:?}", bundle.manifest.promotion_class),
        lane: bundle.build_meta.lane,
        mutation_type: bundle.build_meta.mutation_type,
    };

    println!(
        "{}",
        serde_json::to_string_pretty(&report).map_err(|e| e.to_string())?
    );
    Ok(())
}

fn scir_op_key(op: &ScirOp) -> &'static str {
    match op {
        ScirOp::ByteEmbedding { .. } => "ByteEmbedding",
        ScirOp::LagBytes { .. } => "LagBytes",
        ScirOp::Linear { .. } => "Linear",
        ScirOp::Add => "Add",
        ScirOp::Mul => "Mul",
        ScirOp::Tanh => "Tanh",
        ScirOp::Sigmoid => "Sigmoid",
        ScirOp::Relu => "Relu",
        ScirOp::Concat => "Concat",
        ScirOp::ReduceMean => "ReduceMean",
        ScirOp::ReduceSum => "ReduceSum",
        ScirOp::ShiftRegister { .. } => "ShiftRegister",
        ScirOp::RunLengthBucket { .. } => "RunLengthBucket",
        ScirOp::ModCounter { .. } => "ModCounter",
        ScirOp::RollingHash { .. } => "RollingHash",
        ScirOp::DelimiterReset { .. } => "DelimiterReset",
        ScirOp::HdcBind => "HdcBind",
        ScirOp::HdcBundle => "HdcBundle",
        ScirOp::HdcPermute { .. } => "HdcPermute",
        ScirOp::HdcThreshold { .. } => "HdcThreshold",
        ScirOp::SparseEventQueue { .. } => "SparseEventQueue",
        ScirOp::SparseRouter { .. } => "SparseRouter",
        ScirOp::SymbolicStack { .. } => "SymbolicStack",
        ScirOp::SymbolicTape { .. } => "SymbolicTape",
        ScirOp::SimpleScan { .. } => "SimpleScan",
        ScirOp::ReadoutNative { .. } => "ReadoutNative",
        ScirOp::ReadoutShadow { .. } => "ReadoutShadow",
    }
}

#[allow(clippy::too_many_arguments)]
fn run_ingest_external(
    root: PathBuf,
    input: PathBuf,
    family_id: String,
    format: ExternalFormat,
    family_kind: ExternalFamilyKind,
    role: ExternalRealityRole,
    variant_id: Option<String>,
    base_family_id: Option<String>,
    source_name: String,
    source_type: String,
    description: Option<String>,
    chunk_bytes: usize,
    config: Option<PathBuf>,
    out: Option<PathBuf>,
    ingest: bool,
) -> Result<(), String> {
    let current_exe = std::env::current_exe().map_err(|e| e.to_string())?;
    let sibling = current_exe
        .parent()
        .ok_or_else(|| "cannot resolve executable directory".to_string())?
        .join("apfsc_ingest_external");

    let mut cmd = if sibling.exists() {
        Command::new(sibling)
    } else {
        Command::new("apfsc_ingest_external")
    };
    cmd.arg("--root")
        .arg(root)
        .arg("--input")
        .arg(input)
        .arg("--family-id")
        .arg(family_id)
        .arg("--format")
        .arg(format.as_cli())
        .arg("--family-kind")
        .arg(family_kind.as_cli())
        .arg("--role")
        .arg(role.as_cli())
        .arg("--source-name")
        .arg(source_name)
        .arg("--source-type")
        .arg(source_type)
        .arg("--chunk-bytes")
        .arg(chunk_bytes.to_string());
    if let Some(v) = variant_id {
        cmd.arg("--variant-id").arg(v);
    }
    if let Some(v) = base_family_id {
        cmd.arg("--base-family-id").arg(v);
    }
    if let Some(v) = description {
        cmd.arg("--description").arg(v);
    }
    if let Some(v) = config {
        cmd.arg("--config").arg(v);
    }
    if let Some(v) = out {
        cmd.arg("--out").arg(v);
    }
    if ingest {
        cmd.arg("--ingest");
    }

    let out = cmd.output().map_err(|e| e.to_string())?;
    if !out.stdout.is_empty() {
        print!("{}", String::from_utf8_lossy(&out.stdout));
    }
    if !out.stderr.is_empty() {
        eprint!("{}", String::from_utf8_lossy(&out.stderr));
    }
    if out.status.success() {
        Ok(())
    } else {
        Err(format!(
            "apfsc_ingest_external failed with status {}",
            out.status
        ))
    }
}
