use std::fs;
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

use crate::apf3::aal_exec::AALExecutor;
use crate::apf3::aal_ir::AALGraph;
use crate::apf3::digest::{Digest32, DigestBuilder, TAG_APF3_RUN_V1};
use crate::apf3::metachunkpack::MetaChunkPack;
use crate::apf3::morphisms::{identity_check, AllowedMorphisms};
use crate::apf3::profiler::{build_report, classify_failures, compute_metrics, ProfilerThresholds};
use crate::apf3::{omega, write_atomic};
use crate::oracle3::chunkpack::NumericSubstrate;

#[derive(Clone, Debug)]
pub struct WakeConfig {
    pub seed: u64,
    pub run_dir: PathBuf,
    pub workers: usize,
    pub max_candidates: u64,
    pub train_pack_dir: PathBuf,
    pub proposal_dir: PathBuf,
    pub base_graph: Option<PathBuf>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct WakeReceipt {
    pub candidate_hash: Digest32,
    pub base_graph_digest: Digest32,
    pub diff_digest: Digest32,
    pub train_pack_digests: Vec<Digest32>,
    pub train_pack_set_digest: Digest32,
    pub query_score_mean: f32,
    pub query_score_var: f32,
    pub native_fault_rate: f32,
    pub timeout_rate: f32,
    pub identity_passed: bool,
    #[serde(default = "default_numeric_substrate_tag")]
    pub numeric_substrate: String,
    #[serde(default = "default_capacity_multiplier")]
    pub capacity_multiplier_estimate: f32,
    #[serde(default)]
    pub precision_mutation_applied: bool,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct WakeSnapshot {
    pub evaluated_candidates: u64,
    pub accepted_candidates: u64,
    pub latest_candidate_hash: Option<Digest32>,
    pub latest_query_score_mean: f32,
    pub latest_query_score_var: f32,
    #[serde(default = "default_numeric_substrate_tag")]
    pub latest_numeric_substrate: String,
}

pub fn run_wake(cfg: &WakeConfig) -> Result<(), String> {
    let apf3_dir = cfg.run_dir.join("apf3");
    let reports_dir = apf3_dir.join("reports");
    let receipt_dir = apf3_dir.join("receipts/wake");
    let registry_candidates = apf3_dir.join("registry/candidates");
    let registry_diffs = apf3_dir.join("registry/diffs");

    fs::create_dir_all(&reports_dir).map_err(|e| e.to_string())?;
    fs::create_dir_all(&receipt_dir).map_err(|e| e.to_string())?;
    fs::create_dir_all(&registry_candidates).map_err(|e| e.to_string())?;
    fs::create_dir_all(&registry_diffs).map_err(|e| e.to_string())?;

    let base_path = cfg
        .base_graph
        .clone()
        .unwrap_or_else(|| apf3_dir.join("registry/base_graph.json"));
    let base_bytes =
        fs::read(&base_path).map_err(|e| format!("read {}: {e}", base_path.display()))?;
    let base_graph: AALGraph = serde_json::from_slice(&base_bytes)
        .map_err(|e| format!("parse {}: {e}", base_path.display()))?;
    base_graph
        .validate()
        .map_err(|e| format!("base graph invalid: {e:?}"))?;
    let base_digest = base_graph.digest();

    let packs = load_packs(&cfg.train_pack_dir)?;
    if packs.is_empty() {
        return Err("no train packs found".to_string());
    }

    let proposals = omega::load_proposals(&cfg.proposal_dir)?;

    let allowed = AllowedMorphisms::default();
    let thresholds = ProfilerThresholds::default();

    let mut exec = AALExecutor::default();

    let mut run_builder = DigestBuilder::new(TAG_APF3_RUN_V1);
    run_builder.u64(cfg.seed);
    run_builder.u64(cfg.workers as u64);
    run_builder.u64(cfg.max_candidates);
    run_builder.digest32(base_digest);
    run_builder.u64(packs.len() as u64);
    for p in &packs {
        run_builder.digest32(p.pack_digest);
    }

    let mut evaluated = 0_u64;
    let mut accepted = 0_u64;
    let mut latest_hash = None;
    let mut latest_mean = 0.0_f32;
    let mut latest_var = 0.0_f32;
    let mut latest_substrate = NumericSubstrate::Fp32;

    for (_path, diff) in proposals.into_iter().take(cfg.max_candidates as usize) {
        evaluated = evaluated.saturating_add(1);

        let mut reject_reasons = Vec::<String>::new();
        if let Err(e) = diff.validate_against_graph(&allowed, &base_graph) {
            reject_reasons.push(format!("validate: {e:?}"));
        }

        let candidate_graph = match diff.apply(&base_graph, None) {
            Ok(g) => g,
            Err(e) => {
                reject_reasons.push(format!("apply: {e:?}"));
                base_graph.clone()
            }
        };

        let probe = packs.iter().take(2).cloned().collect::<Vec<_>>();
        let identity_ok = if reject_reasons.is_empty() {
            identity_check(&mut exec, &base_graph, &candidate_graph, &probe, 1e-6, None)
                .map(|_| true)
                .map_err(|e| format!("{e:?}"))
                .unwrap_or_else(|e| {
                    reject_reasons.push(format!("identity_check: {e}"));
                    false
                })
        } else {
            false
        };

        if !reject_reasons.is_empty() {
            continue;
        }

        let diff_digest = diff.digest();
        let candidate_hash = candidate_hash(&candidate_graph, diff_digest);
        let substrate = select_numeric_substrate(candidate_hash);

        let mut score_samples = Vec::with_capacity(packs.len());
        let mut query_before = Vec::with_capacity(packs.len());
        let mut query_after = Vec::with_capacity(packs.len());
        let mut trace_sum = crate::apf3::aal_exec::TraceStats::default();
        let mut total_eps = 0_u32;

        for pack in &packs {
            let r = exec.eval_pack(&candidate_graph, pack, None);
            score_samples.push(quantize_metric(r.query_score_mean, substrate));
            query_before.push(quantize_metric(r.query_loss_before_support, substrate));
            query_after.push(quantize_metric(r.query_loss_after_support, substrate));
            trace_sum.mem_reads = trace_sum.mem_reads.saturating_add(r.trace.mem_reads);
            trace_sum.mem_writes = trace_sum.mem_writes.saturating_add(r.trace.mem_writes);
            trace_sum.update_l1 += r.trace.update_l1;
            trace_sum.native_faults = trace_sum
                .native_faults
                .saturating_add(r.trace.native_faults);
            trace_sum.native_timeouts = trace_sum
                .native_timeouts
                .saturating_add(r.trace.native_timeouts);
            total_eps = total_eps.saturating_add(r.episodes);
        }

        let mean = mean_f32(&score_samples);
        let var = var_f32(&score_samples, mean);
        let metrics = compute_metrics(
            &trace_sum,
            total_eps,
            mean_f32(&query_before),
            mean_f32(&query_after),
            mean,
            None,
        );
        let labels = classify_failures(&metrics, &trace_sum, &thresholds, false);
        let report = build_report(
            candidate_hash,
            candidate_graph.digest(),
            pack_set_digest(&packs),
            metrics,
            trace_sum,
            labels,
        );

        let report_path = reports_dir.join(format!("{}.json", candidate_hash.hex()));
        write_json_atomic(&report_path, &report)?;
        write_json_atomic(&reports_dir.join("latest.json"), &report)?;

        let receipt = WakeReceipt {
            candidate_hash,
            base_graph_digest: base_digest,
            diff_digest,
            train_pack_digests: packs.iter().map(|p| p.pack_digest).collect(),
            train_pack_set_digest: pack_set_digest(&packs),
            query_score_mean: mean,
            query_score_var: var,
            native_fault_rate: if total_eps == 0 {
                0.0
            } else {
                trace_sum.native_faults as f32 / total_eps as f32
            },
            timeout_rate: if total_eps == 0 {
                0.0
            } else {
                trace_sum.native_timeouts as f32 / total_eps as f32
            },
            identity_passed: identity_ok,
            numeric_substrate: substrate.as_tag().to_string(),
            capacity_multiplier_estimate: substrate.capacity_multiplier_estimate(),
            precision_mutation_applied: substrate != NumericSubstrate::Fp32,
        };

        let receipt_path = receipt_dir.join(format!(
            "{}_{}.json",
            candidate_hash.hex(),
            receipt.train_pack_set_digest.hex()
        ));
        write_json_atomic(&receipt_path, &receipt)?;

        write_json_atomic(
            &registry_candidates.join(format!("{}.json", candidate_hash.hex())),
            &candidate_graph,
        )?;
        write_json_atomic(
            &registry_diffs.join(format!("{}.json", candidate_hash.hex())),
            &diff,
        )?;

        run_builder.digest32(candidate_hash);
        run_builder.digest32(receipt.train_pack_set_digest);
        run_builder.f32(receipt.query_score_mean);
        run_builder.f32(receipt.query_score_var);
        run_builder.f32(receipt.native_fault_rate);
        run_builder.f32(receipt.timeout_rate);

        accepted = accepted.saturating_add(1);
        latest_hash = Some(candidate_hash);
        latest_mean = mean;
        latest_var = var;
        latest_substrate = substrate;

        if accepted % 16 == 0 {
            write_wake_snapshot(
                &apf3_dir,
                evaluated,
                accepted,
                latest_hash,
                latest_mean,
                latest_var,
                latest_substrate,
            )?;
        }
    }

    write_wake_snapshot(
        &apf3_dir,
        evaluated,
        accepted,
        latest_hash,
        latest_mean,
        latest_var,
        latest_substrate,
    )?;

    run_builder.u64(evaluated);
    run_builder.u64(accepted);
    if let Some(h) = latest_hash {
        run_builder.digest32(h);
    }
    run_builder.f32(latest_mean);
    run_builder.f32(latest_var);
    run_builder.u64(latest_substrate.capacity_multiplier_estimate().to_bits() as u64);
    let run_digest = run_builder.finish();
    let digest_text = format!(
        "version=1\nseed={}\nworkers={}\nmax_candidates={}\nbase_graph={}\ntrain_pack_set_digest={}\nevaluated={}\naccepted={}\nlatest_candidate_hash={}\nlatest_query_score_mean={:.6}\nlatest_query_score_var={:.6}\nrun_digest={}\n",
        cfg.seed,
        cfg.workers,
        cfg.max_candidates,
        base_digest.hex(),
        pack_set_digest(&packs).hex(),
        evaluated,
        accepted,
        latest_hash
            .map(|h| h.hex())
            .unwrap_or_else(|| "none".to_string()),
        latest_mean,
        latest_var,
        run_digest.hex(),
    );
    write_atomic(&apf3_dir.join("run_digest.txt"), digest_text.as_bytes())?;

    Ok(())
}

fn load_packs(dir: &Path) -> Result<Vec<MetaChunkPack>, String> {
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

    let mut packs = Vec::with_capacity(files.len());
    for path in files {
        packs.push(MetaChunkPack::from_json_file(&path)?);
    }
    Ok(packs)
}

fn write_wake_snapshot(
    apf3_dir: &Path,
    evaluated: u64,
    accepted: u64,
    latest_hash: Option<Digest32>,
    latest_mean: f32,
    latest_var: f32,
    latest_substrate: NumericSubstrate,
) -> Result<(), String> {
    let summary = format!(
        "evaluated={} accepted={} latest_candidate_hash={} query_score_mean={:.6} query_score_var={:.6} substrate={}",
        evaluated,
        accepted,
        latest_hash.map_or_else(|| "none".to_string(), |d| d.hex()),
        latest_mean,
        latest_var,
        latest_substrate.as_tag(),
    );

    let snap = WakeSnapshot {
        evaluated_candidates: evaluated,
        accepted_candidates: accepted,
        latest_candidate_hash: latest_hash,
        latest_query_score_mean: latest_mean,
        latest_query_score_var: latest_var,
        latest_numeric_substrate: latest_substrate.as_tag().to_string(),
    };

    write_atomic(&apf3_dir.join("summary_latest.txt"), summary.as_bytes())?;
    write_json_atomic(&apf3_dir.join("snapshot_latest.json"), &snap)
}

fn write_json_atomic<T: Serialize>(path: &Path, value: &T) -> Result<(), String> {
    let body = serde_json::to_vec_pretty(value).map_err(|e| e.to_string())?;
    write_atomic(path, &body)
}

fn candidate_hash(graph: &AALGraph, diff_digest: Digest32) -> Digest32 {
    let mut b = DigestBuilder::new(b"APF3_CANDIDATE_V1");
    b.digest32(graph.digest());
    b.digest32(diff_digest);
    b.finish()
}

fn pack_set_digest(packs: &[MetaChunkPack]) -> Digest32 {
    let mut b = DigestBuilder::new(b"APF3_PACKSET_V1");
    b.u64(packs.len() as u64);
    for p in packs {
        b.digest32(p.pack_digest);
    }
    b.finish()
}

fn mean_f32(xs: &[f32]) -> f32 {
    if xs.is_empty() {
        0.0
    } else {
        xs.iter().copied().sum::<f32>() / xs.len() as f32
    }
}

fn var_f32(xs: &[f32], mean: f32) -> f32 {
    if xs.len() <= 1 {
        0.0
    } else {
        xs.iter()
            .map(|x| {
                let d = *x - mean;
                d * d
            })
            .sum::<f32>()
            / xs.len() as f32
    }
}

fn default_numeric_substrate_tag() -> String {
    "fp32".to_string()
}

fn default_capacity_multiplier() -> f32 {
    1.0
}

fn select_numeric_substrate(candidate_hash: Digest32) -> NumericSubstrate {
    match candidate_hash.0[0] % 5 {
        0 => NumericSubstrate::Fp32,
        1 => NumericSubstrate::Posit16Sim,
        2 => NumericSubstrate::Log8Sim,
        3 => NumericSubstrate::Int4Gate,
        _ => NumericSubstrate::Int2Gate,
    }
}

fn quantize_metric(v: f32, substrate: NumericSubstrate) -> f32 {
    match substrate {
        NumericSubstrate::Fp32 => v,
        NumericSubstrate::Posit16Sim => (v * 1024.0).round() / 1024.0,
        NumericSubstrate::Log8Sim => {
            if v == 0.0 {
                0.0
            } else {
                let sign = if v < 0.0 { -1.0 } else { 1.0 };
                let lv = v.abs().ln_1p();
                let q = (lv * 32.0).round() / 32.0;
                sign * q.exp_m1()
            }
        }
        NumericSubstrate::Int4Gate => (v.clamp(-1.0, 1.0) * 7.0).round() / 7.0,
        NumericSubstrate::Int2Gate => v.clamp(-1.0, 1.0).round(),
    }
}
