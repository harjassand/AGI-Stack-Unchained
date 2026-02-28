use serde::{Deserialize, Serialize};

use crate::apf3::aal_exec::TraceStats;
use crate::apf3::digest::Digest32;

#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub enum FailureLabel {
    CapacityFailure,
    ForgettingFailure,
    RoutingFailure,
    MemoryFailure,
    UpdateFailure,
    NativeBlockFailure,
    OverfitFailure,
}

#[derive(Clone, Copy, Debug, Serialize, Deserialize)]
pub struct ProfilerThresholds {
    pub adapt_gain_min: f32,
    pub forgetting_index_max: f32,
    pub high_loss_threshold: f32,
    pub mem_write_threshold: u64,
    pub mem_rw_ratio_min: f32,
    pub update_mag_min: f64,
    pub update_mag_max: f64,
    pub native_fault_rate_max: f32,
    pub overfit_margin: f32,
}

impl Default for ProfilerThresholds {
    fn default() -> Self {
        Self {
            adapt_gain_min: 0.01,
            forgetting_index_max: 0.25,
            high_loss_threshold: 0.35,
            mem_write_threshold: 1000,
            mem_rw_ratio_min: 0.2,
            update_mag_min: 1e-6,
            update_mag_max: 1e3,
            native_fault_rate_max: 1e-3,
            overfit_margin: 0.02,
        }
    }
}

#[derive(Clone, Copy, Debug, Serialize, Deserialize)]
pub struct ProfilerMetrics {
    pub adapt_gain: f32,
    pub forgetting_index: f32,
    pub mem_rw_ratio: f32,
    pub native_fault_rate: f32,
    pub update_mag: f64,
    pub train_query_mean: f32,
    pub heldout_query_mean: Option<f32>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ProfilerReport {
    pub candidate_hash: Digest32,
    pub graph_digest: Digest32,
    pub pack_digest: Digest32,
    pub metrics: ProfilerMetrics,
    pub trace: TraceStats,
    pub top_failures: Vec<FailureLabel>,
}

pub fn compute_metrics(
    trace: &TraceStats,
    episodes: u32,
    query_loss_before_support: f32,
    query_loss_after_support: f32,
    train_query_mean: f32,
    heldout_query_mean: Option<f32>,
) -> ProfilerMetrics {
    let eps = 1e-6_f32;
    let adapt_gain = query_loss_before_support - query_loss_after_support;
    let forgetting_index =
        (trace.query_loss_last - trace.query_loss_min) / (trace.query_loss_min.abs() + eps);
    let mem_rw_ratio = trace.mem_reads as f32 / (trace.mem_writes.max(1) as f32);
    let native_fault_rate = (trace.native_faults as f32) / (episodes.max(1) as f32);
    let update_mag = trace.update_l1 / (episodes.max(1) as f64);

    ProfilerMetrics {
        adapt_gain,
        forgetting_index,
        mem_rw_ratio,
        native_fault_rate,
        update_mag,
        train_query_mean,
        heldout_query_mean,
    }
}

pub fn classify_failures(
    metrics: &ProfilerMetrics,
    trace: &TraceStats,
    thresholds: &ProfilerThresholds,
    has_routing_nodes: bool,
) -> Vec<FailureLabel> {
    let mut labels = Vec::new();

    if metrics.adapt_gain <= thresholds.adapt_gain_min
        && metrics.train_query_mean > thresholds.high_loss_threshold
    {
        labels.push(FailureLabel::CapacityFailure);
    }

    if metrics.adapt_gain > 0.02 && metrics.forgetting_index > thresholds.forgetting_index_max {
        labels.push(FailureLabel::ForgettingFailure);
    }

    if trace.mem_writes > thresholds.mem_write_threshold
        && metrics.mem_rw_ratio < thresholds.mem_rw_ratio_min
    {
        labels.push(FailureLabel::MemoryFailure);
    }

    if metrics.update_mag < thresholds.update_mag_min
        || metrics.update_mag > thresholds.update_mag_max
    {
        labels.push(FailureLabel::UpdateFailure);
    }

    if metrics.native_fault_rate > thresholds.native_fault_rate_max || trace.native_timeouts > 0 {
        labels.push(FailureLabel::NativeBlockFailure);
    }

    if has_routing_nodes && metrics.forgetting_index > 1.0 {
        labels.push(FailureLabel::RoutingFailure);
    }

    if let Some(heldout) = metrics.heldout_query_mean {
        if heldout + thresholds.overfit_margin < metrics.train_query_mean {
            labels.push(FailureLabel::OverfitFailure);
        }
    }

    labels
}

pub fn build_report(
    candidate_hash: Digest32,
    graph_digest: Digest32,
    pack_digest: Digest32,
    metrics: ProfilerMetrics,
    trace: TraceStats,
    labels: Vec<FailureLabel>,
) -> ProfilerReport {
    ProfilerReport {
        candidate_hash,
        graph_digest,
        pack_digest,
        metrics,
        trace,
        top_failures: labels,
    }
}

pub fn render_omega_prompt(report: &ProfilerReport, allowed_morphisms: &[&str]) -> String {
    let failures = if report.top_failures.is_empty() {
        "[]".to_string()
    } else {
        let joined = report
            .top_failures
            .iter()
            .map(|f| format!("{:?}", f))
            .collect::<Vec<_>>()
            .join(", ");
        format!("[{joined}]")
    };

    let allowed = format!("[{}]", allowed_morphisms.join(","));

    format!(
        "[APF3_OMEGA_PROMPT_V1]\n\
candidate_hash={}\n\
graph_digest={}\n\
pack_digest={}\n\
top_failures={}\n\
metrics:\n\
  adapt_gain={:.6}\n\
  forgetting_index={:.6}\n\
  mem_reads={}\n\
  mem_writes={}\n\
constraints:\n\
  allowed_morphisms={}\n\
  identity_required=true\n\
recommendations:\n\
  - propose: AddMemorySlot(len=64, init_closed=true)\n\
  - propose: InsertResidualBlock(anchor=(NodeId(0),0), template=LinearActLinear(hidden=16), alpha_init=0)\n\
output_format:\n\
  json ArchitectureDiff\n",
        report.candidate_hash.hex(),
        report.graph_digest.hex(),
        report.pack_digest.hex(),
        failures,
        report.metrics.adapt_gain,
        report.metrics.forgetting_index,
        report.trace.mem_reads,
        report.trace.mem_writes,
        allowed,
    )
}
