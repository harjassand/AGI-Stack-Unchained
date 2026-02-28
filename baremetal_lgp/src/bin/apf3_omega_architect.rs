use std::fs;
use std::path::{Path, PathBuf};

use baremetal_lgp::apf3::aal_exec::AALExecutor;
use baremetal_lgp::apf3::aal_ir::AALGraph;
use baremetal_lgp::apf3::digest::{DigestBuilder, TAG_APF3_RUN_V1};
use baremetal_lgp::apf3::metachunkpack::MetaChunkPack;
use baremetal_lgp::apf3::morphisms::{identity_check, AllowedMorphisms, ArchitectureDiff};
use baremetal_lgp::apf3::profiler::{render_omega_prompt, ProfilerReport};
use baremetal_lgp::apf3::{omega, write_atomic};
use clap::{Parser, ValueEnum};

#[derive(Clone, Copy, Debug, ValueEnum)]
enum LlmMode {
    #[value(name = "off")]
    Off,
    #[value(name = "prompt_only", alias = "prompt-only")]
    PromptOnly,
    #[value(name = "polymath")]
    Polymath,
}

#[derive(Parser, Debug)]
#[command(name = "apf3_omega_architect")]
#[command(about = "APF-v3 Omega architect")]
struct Args {
    #[arg(long, default_value_t = 0)]
    seed: u64,
    #[arg(long)]
    run_dir: PathBuf,
    #[arg(long)]
    profiler_report: Option<PathBuf>,
    #[arg(long)]
    graph: PathBuf,
    #[arg(long)]
    out_diff: PathBuf,
    #[arg(long, value_enum, default_value_t = LlmMode::Off)]
    llm_mode: LlmMode,
    #[arg(long)]
    prompt_out: Option<PathBuf>,
}

fn main() {
    if let Err(err) = run() {
        eprintln!("apf3_omega_architect failed: {err}");
        std::process::exit(1);
    }
}

fn run() -> Result<(), String> {
    let args = Args::parse();
    let apf3_dir = args.run_dir.join("apf3");
    fs::create_dir_all(&apf3_dir).map_err(|e| e.to_string())?;

    let profile_path = args
        .profiler_report
        .clone()
        .unwrap_or_else(|| apf3_dir.join("reports/latest.json"));

    let graph: AALGraph =
        serde_json::from_slice(&fs::read(&args.graph).map_err(|e| e.to_string())?)
            .map_err(|e| e.to_string())?;
    let graph_digest = graph.digest();

    let report = if profile_path.exists() {
        serde_json::from_slice::<ProfilerReport>(
            &fs::read(&profile_path).map_err(|e| e.to_string())?,
        )
        .ok()
    } else {
        None
    };

    match args.llm_mode {
        LlmMode::PromptOnly => {
            let report = report.ok_or_else(|| {
                format!(
                    "profiler report missing or invalid: {}",
                    profile_path.display()
                )
            })?;
            let prompt = render_omega_prompt(
                &report,
                &[
                    "InsertResidualBlock",
                    "WidenLayer",
                    "AddMemorySlot",
                    "AddHead",
                    "SwapActivationIdentityApprox",
                ],
            );
            let out = args
                .prompt_out
                .as_ref()
                .ok_or_else(|| "--prompt-out is required in prompt_only mode".to_string())?;
            write_atomic(out, prompt.as_bytes())?;
            write_run_digest(
                &apf3_dir,
                args.seed,
                "prompt_only",
                graph_digest,
                None,
                Some(&report),
                0,
            )?;
            return Ok(());
        }
        LlmMode::Polymath => {
            write_run_digest(
                &apf3_dir,
                args.seed,
                "polymath",
                graph_digest,
                None,
                report.as_ref(),
                0,
            )?;
            return Err(
                "polymath bridge is not available in this repository; use --llm-mode prompt_only"
                    .to_string(),
            );
        }
        LlmMode::Off => {}
    }

    let mut reject_reasons = Vec::new();
    let diff_bytes = fs::read(&args.out_diff)
        .map_err(|e| format!("--llm-mode off expects existing --out-diff JSON: {e}"))?;
    let diff: ArchitectureDiff = match serde_json::from_slice(&diff_bytes) {
        Ok(v) => v,
        Err(e) => {
            reject_reasons.push(format!("parse diff: {e}"));
            write_reject(&args.out_diff, &reject_reasons)?;
            write_run_digest(
                &apf3_dir,
                args.seed,
                "off",
                graph_digest,
                None,
                report.as_ref(),
                reject_reasons.len() as u32,
            )?;
            return Ok(());
        }
    };

    let allowed = AllowedMorphisms::default();
    if let Err(e) = diff.validate_against_graph(&allowed, &graph) {
        reject_reasons.push(format!("validate: {e:?}"));
    }

    let candidate = match diff.apply(&graph, None) {
        Ok(g) => g,
        Err(e) => {
            reject_reasons.push(format!("apply: {e:?}"));
            graph.clone()
        }
    };

    let mut exec = AALExecutor::default();
    let probe = load_probe_packs(&apf3_dir.join("packs/train"))?;
    if let Err(e) = identity_check(&mut exec, &graph, &candidate, &probe, 1e-6, None) {
        reject_reasons.push(format!("identity_check: {e:?}"));
    }

    if !reject_reasons.is_empty() {
        write_reject(&args.out_diff, &reject_reasons)?;
        write_run_digest(
            &apf3_dir,
            args.seed,
            "off",
            graph_digest,
            None,
            report.as_ref(),
            reject_reasons.len() as u32,
        )?;
        return Ok(());
    }

    write_atomic(
        &args.out_diff,
        &serde_json::to_vec_pretty(&diff).map_err(|e| e.to_string())?,
    )?;
    write_run_digest(
        &apf3_dir,
        args.seed,
        "off",
        graph_digest,
        Some(diff.digest().hex()),
        report.as_ref(),
        0,
    )?;
    Ok(())
}

fn write_run_digest(
    apf3_dir: &Path,
    seed: u64,
    mode: &str,
    graph_digest: baremetal_lgp::apf3::digest::Digest32,
    diff_digest_hex: Option<String>,
    report: Option<&ProfilerReport>,
    reject_count: u32,
) -> Result<(), String> {
    let mut b = DigestBuilder::new(TAG_APF3_RUN_V1);
    b.u64(seed);
    b.bytes(mode.as_bytes());
    b.digest32(graph_digest);
    if let Some(diff) = &diff_digest_hex {
        b.bytes(diff.as_bytes());
    }
    if let Some(report) = report {
        b.digest32(report.candidate_hash);
        b.digest32(report.pack_digest);
        b.f32(report.metrics.adapt_gain);
        b.f32(report.metrics.forgetting_index);
        b.f32(report.metrics.mem_rw_ratio);
        b.f32(report.metrics.native_fault_rate);
        b.f64(report.metrics.update_mag);
        b.u64(report.trace.mem_reads);
        b.u64(report.trace.mem_writes);
    }
    b.u32(reject_count);
    let run = b.finish();

    let (candidate_hash, pack_digest, adapt_gain, forgetting_index, native_fault_rate) =
        if let Some(r) = report {
            (
                r.candidate_hash.hex(),
                r.pack_digest.hex(),
                format!("{:.6}", r.metrics.adapt_gain),
                format!("{:.6}", r.metrics.forgetting_index),
                format!("{:.6}", r.metrics.native_fault_rate),
            )
        } else {
            (
                "none".to_string(),
                "none".to_string(),
                "none".to_string(),
                "none".to_string(),
                "none".to_string(),
            )
        };

    let body = format!(
        "version=1\nseed={}\nmode={}\ngraph_digest={}\ndiff_digest={}\ncandidate_hash={}\npack_digest={}\nadapt_gain={}\nforgetting_index={}\nnative_fault_rate={}\nreject_count={}\nrun_digest={}\n",
        seed,
        mode,
        graph_digest.hex(),
        diff_digest_hex.unwrap_or_else(|| "none".to_string()),
        candidate_hash,
        pack_digest,
        adapt_gain,
        forgetting_index,
        native_fault_rate,
        reject_count,
        run.hex(),
    );
    write_atomic(&apf3_dir.join("run_digest.txt"), body.as_bytes())
}

fn load_probe_packs(dir: &Path) -> Result<Vec<MetaChunkPack>, String> {
    if !dir.exists() {
        return Ok(Vec::new());
    }

    let mut files = fs::read_dir(dir)
        .map_err(|e| e.to_string())?
        .filter_map(|e| e.ok())
        .map(|e| e.path())
        .filter(|p| p.extension().and_then(|x| x.to_str()) == Some("json"))
        .collect::<Vec<_>>();
    files.sort();

    let mut out = Vec::new();
    for path in files.into_iter().take(2) {
        out.push(MetaChunkPack::from_json_file(&path)?);
    }
    Ok(out)
}

fn write_reject(out_diff: &Path, reasons: &[String]) -> Result<(), String> {
    let reject_path = out_diff.with_extension("reject.json");
    omega::write_reject(&reject_path, reasons)
}
