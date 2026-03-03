use std::collections::{BTreeMap, HashMap};
use std::io::{Read, Write};
use std::os::unix::net::UnixStream;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::time::{Duration, UNIX_EPOCH};

use baremetal_lgp::apfsc::artifacts::{read_pointer, write_pointer};
use baremetal_lgp::apfsc::candidate::{
    load_active_candidate, load_candidate, rehash_candidate, save_candidate,
};
use baremetal_lgp::apfsc::prod::control_api::{ControlCommand, ControlRequest, ControlResponse};
use baremetal_lgp::apfsc::scir::ast::{ScirNode, ScirOp};
use clap::{ArgAction, Parser, Subcommand, ValueEnum};
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
        #[arg(long, default_value_t = false)]
        infinite: bool,
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
    ForceThermalSpike {
        #[arg(long)]
        temp: f64,
        #[arg(long, default_value_t = 50)]
        epochs: u32,
        #[arg(long, default_value_t = 0.1)]
        cooldown_temp: f64,
    },
    IngestExternal {
        #[arg(long, default_value = ".apfsc")]
        root: PathBuf,
        #[arg(long)]
        input: Option<PathBuf>,
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
        #[arg(long, default_value_t = false)]
        arxiv_sync: bool,
        #[arg(long, default_value_t = 24)]
        arxiv_max_results: usize,
    },
    DumpBrain {
        #[arg(long, default_value = ".apfsc")]
        root: PathBuf,
        #[arg(long, value_enum, default_value_t = BrainTarget::Active)]
        target: BrainTarget,
    },
    AfferentDump {
        #[arg(long, default_value = ".apfsc")]
        root: PathBuf,
    },
    ExtropyStatus {
        #[arg(long, default_value = ".apfsc")]
        root: PathBuf,
    },
    BootstrapEmbodiment {
        #[arg(long, default_value = ".apfsc")]
        root: PathBuf,
    },
    BootstrapAleph {
        #[arg(long, default_value = ".apfsc")]
        root: PathBuf,
    },
    ReadDiscoveryStream {
        #[arg(long, default_value = ".apfsc")]
        root: PathBuf,
        #[arg(long, default_value_t = true, action = ArgAction::Set)]
        follow: bool,
        #[arg(long, default_value_t = 2000)]
        poll_ms: u64,
        #[arg(long, default_value_t = 32)]
        limit: usize,
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

#[derive(Debug, Clone, Serialize)]
struct BootstrapEmbodimentReport {
    root: String,
    old_active_candidate: String,
    new_active_candidate: String,
    rollback_candidate: String,
    injected_nodes: Vec<String>,
    baseline_credit_bpb: f64,
    notes: String,
}

#[derive(Debug, Clone, Serialize)]
struct BootstrapAlephReport {
    root: String,
    old_active_candidate: String,
    new_active_candidate: String,
    rollback_candidate: String,
    aleph_depth: u32,
    injected_nodes: Vec<String>,
    cleared_timeout_keys: Vec<String>,
    daemon_restart: String,
    notes: String,
}

#[derive(Debug, Clone, Serialize)]
struct AfferentDumpReport {
    root: String,
    snapshot_path: String,
    latest_snapshot: Option<serde_json::Value>,
    external_snapshot_path: String,
    latest_external_snapshot: Option<serde_json::Value>,
    live_sample: serde_json::Value,
    channels: BTreeMap<String, f32>,
    channel3_tensor_seed_preview: Option<Vec<f32>>,
}

#[derive(Debug, Clone, Serialize)]
struct ExtropyStatusReport {
    root: String,
    latest_extropy_receipt: Option<serde_json::Value>,
    latest_extropy_receipt_path: Option<String>,
    extropy_panic_epoch_pointer: Option<String>,
    active_candidate: Option<String>,
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
        Cmd::StartRun {
            profile,
            epochs,
            infinite,
        } => ControlCommand::StartRun {
            profile,
            epochs: if infinite { u32::MAX } else { epochs },
        },
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
        Cmd::ForceThermalSpike {
            temp,
            epochs,
            cooldown_temp,
        } => ControlCommand::ForceThermalSpike {
            temp,
            epochs,
            cooldown_temp,
        },
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
            arxiv_sync,
            arxiv_max_results,
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
                arxiv_sync,
                arxiv_max_results,
            );
        }
        Cmd::DumpBrain { root, target } => {
            return run_dump_brain(root, target);
        }
        Cmd::AfferentDump { root } => {
            return run_afferent_dump(root);
        }
        Cmd::ExtropyStatus { root } => {
            return run_extropy_status(root);
        }
        Cmd::BootstrapEmbodiment { root } => {
            return run_bootstrap_embodiment(root);
        }
        Cmd::BootstrapAleph { root } => {
            return run_bootstrap_aleph(root);
        }
        Cmd::ReadDiscoveryStream {
            root,
            follow,
            poll_ms,
            limit,
        } => {
            return run_read_discovery_stream(root, follow, poll_ms, limit);
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

fn next_node_id(program: &baremetal_lgp::apfsc::scir::ast::ScirProgram) -> u32 {
    program
        .nodes
        .iter()
        .map(|n| n.id)
        .max()
        .unwrap_or(0)
        .saturating_add(1)
}

fn ensure_ectoderm_primitives(
    program: &mut baremetal_lgp::apfsc::scir::ast::ScirProgram,
) -> Vec<String> {
    let mut injected = Vec::new();
    let feature = program.outputs.feature_node;
    let mut present = [false; 3];
    for node in &program.nodes {
        if let ScirOp::EctodermPrimitive { channel } = node.op {
            if channel <= 2 {
                present[channel as usize] = true;
                if !program.outputs.probe_nodes.contains(&node.id) {
                    program.outputs.probe_nodes.push(node.id);
                }
            }
        }
    }
    for channel in 0..=2u8 {
        if present[channel as usize] {
            continue;
        }
        let id = next_node_id(program);
        program.nodes.push(ScirNode {
            id,
            op: ScirOp::EctodermPrimitive { channel },
            inputs: vec![feature],
            out_dim: 1,
            mutable: false,
        });
        if !program.outputs.probe_nodes.contains(&id) {
            program.outputs.probe_nodes.push(id);
        }
        injected.push(format!("EctodermPrimitive[{channel}]"));
    }
    injected
}

fn ensure_afferent_node(
    bundle: &mut baremetal_lgp::apfsc::candidate::CandidateBundle,
) -> Vec<String> {
    let mut injected = Vec::new();
    let program = &mut bundle.arch_program;
    let has_afferent = program
        .nodes
        .iter()
        .any(|n| matches!(n.op, ScirOp::AfferentNode { .. }));
    if has_afferent {
        return injected;
    }
    let feature = program.outputs.feature_node;
    let feature_dim = program
        .nodes
        .iter()
        .find(|n| n.id == feature)
        .map(|n| n.out_dim)
        .unwrap_or(1);
    let afferent_id = next_node_id(program);
    program.nodes.push(ScirNode {
        id: afferent_id,
        op: ScirOp::AfferentNode { channel: 2 },
        inputs: Vec::new(),
        out_dim: feature_dim,
        mutable: false,
    });
    let concat_id = next_node_id(program);
    program.nodes.push(ScirNode {
        id: concat_id,
        op: ScirOp::Concat,
        inputs: vec![feature, afferent_id],
        out_dim: feature_dim.saturating_mul(2),
        mutable: false,
    });
    program.outputs.feature_node = concat_id;

    bundle.head_pack.native_head.in_dim = bundle
        .head_pack
        .native_head
        .in_dim
        .saturating_add(feature_dim);
    bundle
        .head_pack
        .native_head
        .weights
        .extend(vec![0.0; (256 * feature_dim) as usize]);
    bundle.head_pack.nuisance_head.in_dim = bundle
        .head_pack
        .nuisance_head
        .in_dim
        .saturating_add(feature_dim);
    bundle
        .head_pack
        .nuisance_head
        .weights
        .extend(vec![0.0; (256 * feature_dim) as usize]);
    bundle.head_pack.residual_head.in_dim = bundle
        .head_pack
        .residual_head
        .in_dim
        .saturating_add(feature_dim);
    bundle
        .head_pack
        .residual_head
        .weights
        .extend(vec![0.0; (256 * feature_dim) as usize]);
    bundle
        .state_pack
        .resid_weights
        .extend(vec![0.0; feature_dim as usize]);

    injected.push("AfferentNode[channel=2]".to_string());
    injected.push("Concat(feature, afferent)".to_string());
    injected
}

fn ensure_subcortex_node(
    bundle: &mut baremetal_lgp::apfsc::candidate::CandidateBundle,
    prior_hash: &str,
) -> Vec<String> {
    let mut injected = Vec::new();
    let program = &mut bundle.arch_program;
    let has_subcortex = program
        .nodes
        .iter()
        .any(|n| matches!(n.op, ScirOp::Subcortex { .. }));
    if has_subcortex {
        return injected;
    }
    let feature = program.outputs.feature_node;
    let out_dim = program
        .nodes
        .iter()
        .find(|n| n.id == feature)
        .map(|n| n.out_dim)
        .unwrap_or(1);
    let id = next_node_id(program);
    program.nodes.push(ScirNode {
        id,
        op: ScirOp::Subcortex {
            prior_hash: prior_hash.to_string(),
            eigen_modulator_vector: vec![1.0, 0.75, 0.5, 0.25],
        },
        inputs: vec![feature],
        out_dim,
        mutable: false,
    });
    program.outputs.feature_node = id;
    injected.push("Subcortex[legacy-s-class]".to_string());
    injected
}

fn splice_aleph_zero(
    bundle: &mut baremetal_lgp::apfsc::candidate::CandidateBundle,
    recursion_depth: u32,
) -> Vec<String> {
    let mut injected = Vec::new();
    let program = &mut bundle.arch_program;
    if let Some(node) = program.nodes.iter().find(|n| {
        n.id == program.outputs.feature_node
            && matches!(n.op, ScirOp::AlephZero { recursion_depth: d } if d == recursion_depth)
    }) {
        injected.push(format!(
            "AlephZero(depth={recursion_depth}) already active @{}",
            node.id
        ));
        return injected;
    }

    let old_feature = program.outputs.feature_node;
    let out_dim = program
        .nodes
        .iter()
        .find(|n| n.id == old_feature)
        .map(|n| n.out_dim)
        .unwrap_or(1);
    let afferent_ids: Vec<u32> = program
        .nodes
        .iter()
        .filter_map(|n| match n.op {
            ScirOp::AfferentNode { .. } => Some(n.id),
            _ => None,
        })
        .collect();
    let aleph_id = next_node_id(program);
    program.nodes.push(ScirNode {
        id: aleph_id,
        op: ScirOp::AlephZero { recursion_depth },
        inputs: vec![old_feature],
        out_dim,
        mutable: false,
    });
    program.outputs.feature_node = aleph_id;

    let mut rewired_ectoderm = 0usize;
    let mut rewired_afferent_concat = 0usize;
    for node in &mut program.nodes {
        match node.op {
            ScirOp::EctodermPrimitive { .. } => {
                for inp in &mut node.inputs {
                    if *inp == old_feature {
                        *inp = aleph_id;
                        rewired_ectoderm = rewired_ectoderm.saturating_add(1);
                    }
                }
            }
            ScirOp::Concat => {
                let has_afferent_input = node.inputs.iter().any(|id| afferent_ids.contains(id));
                if has_afferent_input {
                    for inp in &mut node.inputs {
                        if *inp == old_feature {
                            *inp = aleph_id;
                            rewired_afferent_concat = rewired_afferent_concat.saturating_add(1);
                        }
                    }
                }
            }
            _ => {}
        }
    }

    injected.push(format!("AlephZero(depth={recursion_depth})"));
    if rewired_ectoderm > 0 {
        injected.push(format!("rewired_ectoderm_inputs={rewired_ectoderm}"));
    }
    if rewired_afferent_concat > 0 {
        injected.push(format!(
            "rewired_afferent_concat_inputs={rewired_afferent_concat}"
        ));
    }
    injected
}

fn clear_timeout_pointers(root: &Path) -> Result<Vec<String>, String> {
    let pointers = root.join("pointers");
    let mut cleared = Vec::new();
    if !pointers.exists() {
        return Ok(cleared);
    }
    for ent in std::fs::read_dir(&pointers).map_err(|e| e.to_string())? {
        let ent = ent.map_err(|e| e.to_string())?;
        if !ent.file_type().map_err(|e| e.to_string())?.is_file() {
            continue;
        }
        let name = ent.file_name().to_string_lossy().to_string();
        let lname = name.to_ascii_lowercase();
        let should_clear = lname.contains("timeout")
            || lname.starts_with("sclass_")
            || lname.starts_with("pclass_");
        if !should_clear {
            continue;
        }
        std::fs::remove_file(ent.path()).map_err(|e| e.to_string())?;
        cleared.push(name);
    }
    cleared.sort();
    Ok(cleared)
}

fn restart_daemon_best_effort(root: &Path) -> String {
    let _ = Command::new("pkill").arg("-x").arg("apfscd").status();
    let current_exe = match std::env::current_exe() {
        Ok(p) => p,
        Err(e) => return format!("restart_skipped: cannot resolve current executable ({e})"),
    };
    let daemon_sibling = current_exe
        .parent()
        .map(|p| p.join("apfscd"))
        .unwrap_or_else(|| PathBuf::from("apfscd"));
    let mut cmd = if daemon_sibling.exists() {
        Command::new(daemon_sibling)
    } else {
        Command::new("apfscd")
    };
    cmd.env("APFSC_ROOT", root)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    match cmd.spawn() {
        Ok(child) => format!("restarted(pid={})", child.id()),
        Err(e) => format!("restart_failed: {e}"),
    }
}

fn run_bootstrap_embodiment(root: PathBuf) -> Result<(), String> {
    let mut active = load_active_candidate(&root).map_err(|e| e.to_string())?;
    let old_hash = active.manifest.candidate_hash.clone();
    let mut injected_nodes = Vec::new();

    injected_nodes.extend(ensure_ectoderm_primitives(&mut active.arch_program));
    injected_nodes.extend(ensure_afferent_node(&mut active));
    injected_nodes.extend(ensure_subcortex_node(&mut active, &old_hash));

    if injected_nodes.is_empty() {
        let report = BootstrapEmbodimentReport {
            root: root.display().to_string(),
            old_active_candidate: old_hash.clone(),
            new_active_candidate: old_hash.clone(),
            rollback_candidate: read_pointer(&root, "rollback_candidate")
                .unwrap_or_else(|_| old_hash.clone()),
            injected_nodes,
            baseline_credit_bpb: 1.0,
            notes: "No-op bootstrap: active candidate already has embodiment primitives"
                .to_string(),
        };
        println!(
            "{}",
            serde_json::to_string_pretty(&report).map_err(|e| e.to_string())?
        );
        return Ok(());
    }

    active.build_meta.mutation_type =
        format!("{}+bootstrap_embodiment", active.build_meta.mutation_type);
    active.build_meta.notes = Some(
        "bootstrap-embodiment: injected EctodermPrimitive[0..2], AfferentNode, and Subcortex; baseline_credit_bpb=1.0"
            .to_string(),
    );
    rehash_candidate(&mut active).map_err(|e| e.to_string())?;
    save_candidate(&root, &active).map_err(|e| e.to_string())?;
    write_pointer(&root, "rollback_candidate", &old_hash).map_err(|e| e.to_string())?;
    write_pointer(&root, "active_candidate", &active.manifest.candidate_hash)
        .map_err(|e| e.to_string())?;

    let report = BootstrapEmbodimentReport {
        root: root.display().to_string(),
        old_active_candidate: old_hash.clone(),
        new_active_candidate: active.manifest.candidate_hash.clone(),
        rollback_candidate: old_hash,
        injected_nodes,
        baseline_credit_bpb: 1.0,
        notes: "Embodiment bootstrap complete. Restart/resume daemon loop to evaluate the new active candidate.".to_string(),
    };
    println!(
        "{}",
        serde_json::to_string_pretty(&report).map_err(|e| e.to_string())?
    );
    Ok(())
}

fn run_bootstrap_aleph(root: PathBuf) -> Result<(), String> {
    let mut active = load_active_candidate(&root).map_err(|e| e.to_string())?;
    let old_hash = active.manifest.candidate_hash.clone();
    let mut injected_nodes = Vec::new();

    injected_nodes.extend(ensure_ectoderm_primitives(&mut active.arch_program));
    injected_nodes.extend(ensure_afferent_node(&mut active));
    injected_nodes.extend(splice_aleph_zero(&mut active, 100));
    let changed = !injected_nodes.is_empty()
        && !(injected_nodes.len() == 1 && injected_nodes[0].contains("already active"));
    let cleared_timeout_keys = clear_timeout_pointers(&root)?;
    let daemon_restart = restart_daemon_best_effort(&root);

    if !changed {
        let report = BootstrapAlephReport {
            root: root.display().to_string(),
            old_active_candidate: old_hash.clone(),
            new_active_candidate: old_hash.clone(),
            rollback_candidate: read_pointer(&root, "rollback_candidate")
                .unwrap_or_else(|_| old_hash.clone()),
            aleph_depth: 100,
            injected_nodes,
            cleared_timeout_keys,
            daemon_restart,
            notes: "No-op bootstrap: active candidate already has AlephZero depth=100 at the active feature root."
                .to_string(),
        };
        println!(
            "{}",
            serde_json::to_string_pretty(&report).map_err(|e| e.to_string())?
        );
        return Ok(());
    }

    active.build_meta.mutation_type =
        format!("{}+bootstrap_aleph", active.build_meta.mutation_type);
    active.build_meta.notes = Some(
        "bootstrap-aleph: injected AlephZero(depth=100) upstream of afferent/ectoderm hooks; cleared class timeout pointers."
            .to_string(),
    );
    rehash_candidate(&mut active).map_err(|e| e.to_string())?;
    save_candidate(&root, &active).map_err(|e| e.to_string())?;
    write_pointer(&root, "rollback_candidate", &old_hash).map_err(|e| e.to_string())?;
    write_pointer(&root, "active_candidate", &active.manifest.candidate_hash)
        .map_err(|e| e.to_string())?;

    let report = BootstrapAlephReport {
        root: root.display().to_string(),
        old_active_candidate: old_hash.clone(),
        new_active_candidate: active.manifest.candidate_hash.clone(),
        rollback_candidate: old_hash,
        aleph_depth: 100,
        injected_nodes,
        cleared_timeout_keys,
        daemon_restart,
        notes: "Aleph bootstrap complete. Active pointer moved to the mutated champion; daemon restart attempted (see daemon_restart)."
            .to_string(),
    };
    println!(
        "{}",
        serde_json::to_string_pretty(&report).map_err(|e| e.to_string())?
    );
    Ok(())
}

fn latest_json_receipt(dir: &Path) -> Result<Option<(PathBuf, serde_json::Value)>, String> {
    if !dir.exists() {
        return Ok(None);
    }
    let mut files: Vec<(u64, PathBuf)> = Vec::new();
    for ent in std::fs::read_dir(dir).map_err(|e| e.to_string())? {
        let ent = ent.map_err(|e| e.to_string())?;
        let path = ent.path();
        if !ent.file_type().map_err(|e| e.to_string())?.is_file()
            || path.extension().and_then(|s| s.to_str()) != Some("json")
        {
            continue;
        }
        let modified = std::fs::metadata(&path)
            .map_err(|e| e.to_string())?
            .modified()
            .ok()
            .and_then(|t| t.duration_since(UNIX_EPOCH).ok())
            .map(|d| d.as_secs())
            .unwrap_or(0);
        files.push((modified, path));
    }
    files.sort_by(|a, b| b.0.cmp(&a.0));
    if let Some((_, path)) = files.into_iter().next() {
        let raw = std::fs::read_to_string(&path).map_err(|e| e.to_string())?;
        let value = serde_json::from_str::<serde_json::Value>(&raw).map_err(|e| e.to_string())?;
        Ok(Some((path, value)))
    } else {
        Ok(None)
    }
}

fn run_afferent_dump(root: PathBuf) -> Result<(), String> {
    let snapshot_path = root.join("runtime").join("afferent_snapshot.json");
    let external_snapshot_path = root.join("runtime").join("afferent_external_snapshot.json");
    let latest_snapshot = if snapshot_path.exists() {
        let raw = std::fs::read_to_string(&snapshot_path).map_err(|e| e.to_string())?;
        Some(serde_json::from_str::<serde_json::Value>(&raw).map_err(|e| e.to_string())?)
    } else {
        None
    };
    let latest_external_snapshot = if external_snapshot_path.exists() {
        let raw = std::fs::read_to_string(&external_snapshot_path).map_err(|e| e.to_string())?;
        Some(serde_json::from_str::<serde_json::Value>(&raw).map_err(|e| e.to_string())?)
    } else {
        None
    };
    let live = baremetal_lgp::apfsc::afferent::sample_macos_telemetry();
    let live_sample = serde_json::to_value(&live).map_err(|e| e.to_string())?;
    let mut channels = BTreeMap::new();
    channels.insert(
        "0_loadavg_norm".to_string(),
        baremetal_lgp::apfsc::afferent::channel_value(0),
    );
    channels.insert(
        "1_thermal_pressure".to_string(),
        baremetal_lgp::apfsc::afferent::channel_value(1),
    );
    channels.insert(
        "2_power_proxy_norm".to_string(),
        baremetal_lgp::apfsc::afferent::channel_value(2),
    );
    channels.insert(
        "3_time_phase".to_string(),
        baremetal_lgp::apfsc::afferent::channel_value(3),
    );
    let channel3_tensor_seed_preview =
        baremetal_lgp::apfsc::afferent::channel_seed_vector_from_root(&root, 3, 16);
    let report = AfferentDumpReport {
        root: root.display().to_string(),
        snapshot_path: snapshot_path.display().to_string(),
        latest_snapshot,
        external_snapshot_path: external_snapshot_path.display().to_string(),
        latest_external_snapshot,
        live_sample,
        channels,
        channel3_tensor_seed_preview,
    };
    println!(
        "{}",
        serde_json::to_string_pretty(&report).map_err(|e| e.to_string())?
    );
    Ok(())
}

fn run_extropy_status(root: PathBuf) -> Result<(), String> {
    let latest = latest_json_receipt(&root.join("receipts").join("extropy"))?;
    let (latest_extropy_receipt_path, latest_extropy_receipt) = match latest {
        Some((path, value)) => (Some(path.display().to_string()), Some(value)),
        None => (None, None),
    };
    let extropy_panic_epoch_pointer = read_pointer(&root, "extropy_panic_epoch").ok();
    let active_candidate = read_pointer(&root, "active_candidate").ok();
    let report = ExtropyStatusReport {
        root: root.display().to_string(),
        latest_extropy_receipt,
        latest_extropy_receipt_path,
        extropy_panic_epoch_pointer,
        active_candidate,
    };
    println!(
        "{}",
        serde_json::to_string_pretty(&report).map_err(|e| e.to_string())?
    );
    Ok(())
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
        candidate_path: root
            .join("candidates")
            .join(&candidate_hash)
            .display()
            .to_string(),
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

fn walk_discovery_dir(dir: &Path, out: &mut Vec<(u64, PathBuf)>) -> Result<(), String> {
    if !dir.exists() {
        return Ok(());
    }
    for ent in std::fs::read_dir(dir).map_err(|e| e.to_string())? {
        let ent = ent.map_err(|e| e.to_string())?;
        let path = ent.path();
        let file_type = ent.file_type().map_err(|e| e.to_string())?;
        if file_type.is_dir() {
            walk_discovery_dir(&path, out)?;
            continue;
        }
        if !file_type.is_file() {
            continue;
        }
        let ext = path
            .extension()
            .and_then(|s| s.to_str())
            .unwrap_or_default()
            .to_ascii_lowercase();
        if ext != "json" && ext != "xyz" {
            continue;
        }
        let modified = std::fs::metadata(&path)
            .map_err(|e| e.to_string())?
            .modified()
            .ok()
            .and_then(|t| t.duration_since(UNIX_EPOCH).ok())
            .map(|d| d.as_secs())
            .unwrap_or(0);
        out.push((modified, path));
    }
    Ok(())
}

fn list_discovery_files(root: &Path) -> Result<Vec<(u64, PathBuf)>, String> {
    let dir = root.join("discoveries");
    let mut files = Vec::<(u64, PathBuf)>::new();
    walk_discovery_dir(&dir, &mut files)?;
    files.sort_by(|a, b| a.0.cmp(&b.0));
    Ok(files)
}

fn print_discovery(path: &Path, modified_unix_s: u64) -> Result<(), String> {
    let ext = path
        .extension()
        .and_then(|s| s.to_str())
        .unwrap_or_default()
        .to_ascii_lowercase();
    if ext == "xyz" {
        let raw = std::fs::read_to_string(path).map_err(|e| e.to_string())?;
        let mut lines = raw.lines();
        let atom_count = lines
            .next()
            .and_then(|v| v.trim().parse::<usize>().ok())
            .unwrap_or(0);
        let comment = lines.next().unwrap_or_default().to_string();
        let preview: Vec<String> = lines.take(5).map(|s| s.to_string()).collect();
        let envelope = serde_json::json!({
            "modified_unix_s": modified_unix_s,
            "path": path.display().to_string(),
            "artifact_type": "class_m_xyz",
            "atom_count": atom_count,
            "comment": comment,
            "preview": preview,
        });
        println!(
            "{}",
            serde_json::to_string_pretty(&envelope).map_err(|e| e.to_string())?
        );
        return Ok(());
    }

    let raw = std::fs::read_to_string(path).map_err(|e| e.to_string())?;
    let payload = serde_json::from_str::<serde_json::Value>(&raw).map_err(|e| e.to_string())?;
    let envelope = serde_json::json!({
        "modified_unix_s": modified_unix_s,
        "path": path.display().to_string(),
        "artifact_type": "discovery_json",
        "discovery": payload,
    });
    println!(
        "{}",
        serde_json::to_string_pretty(&envelope).map_err(|e| e.to_string())?
    );
    Ok(())
}

fn run_read_discovery_stream(
    root: PathBuf,
    follow: bool,
    poll_ms: u64,
    limit: usize,
) -> Result<(), String> {
    let dir = root.join("discoveries");
    std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    let mut files = list_discovery_files(&root)?;
    if files.is_empty() {
        println!(
            "{}",
            serde_json::to_string_pretty(&serde_json::json!({
                "root": root.display().to_string(),
                "discoveries_dir": dir.display().to_string(),
                "message": "No discoveries yet",
            }))
            .map_err(|e| e.to_string())?
        );
    } else {
        let start = files.len().saturating_sub(limit.max(1));
        for (modified, path) in files.iter().skip(start) {
            print_discovery(path, *modified)?;
        }
    }
    if !follow {
        return Ok(());
    }
    let mut seen = HashMap::<PathBuf, u64>::new();
    for (modified, path) in files.drain(..) {
        seen.insert(path, modified);
    }
    loop {
        std::thread::sleep(Duration::from_millis(poll_ms.max(250)));
        let files = list_discovery_files(&root)?;
        for (modified, path) in files {
            let prior = seen.get(&path).copied().unwrap_or(0);
            if modified <= prior {
                continue;
            }
            print_discovery(&path, modified)?;
            seen.insert(path, modified);
        }
    }
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
        ScirOp::AfferentNode { .. } => "AfferentNode",
        ScirOp::EctodermPrimitive { .. } => "EctodermPrimitive",
        ScirOp::Subcortex { .. } => "Subcortex",
        ScirOp::Alien { .. } => "Alien",
        ScirOp::AlephZero { .. } => "AlephZero",
        ScirOp::SimpleScan { .. } => "SimpleScan",
        ScirOp::ReadoutNative { .. } => "ReadoutNative",
        ScirOp::ReadoutShadow { .. } => "ReadoutShadow",
    }
}

#[allow(clippy::too_many_arguments)]
fn run_ingest_external(
    root: PathBuf,
    input: Option<PathBuf>,
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
    arxiv_sync: bool,
    arxiv_max_results: usize,
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
    if let Some(v) = input {
        cmd.arg("--input").arg(v);
    }
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
    if arxiv_sync {
        cmd.arg("--arxiv-sync");
        cmd.arg("--arxiv-max-results")
            .arg(arxiv_max_results.to_string());
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
