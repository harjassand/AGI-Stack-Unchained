use std::path::Path;

use serde::{Deserialize, Serialize};

use crate::apfsc::artifacts::{append_jsonl_atomic, read_json, read_jsonl, write_json_atomic};
use crate::apfsc::config::Phase1Config;
use crate::apfsc::errors::{ApfscError, Result};
use crate::apfsc::types::{BackendKind, ResourceEnvelope};
use crate::apfsc::types::{PredictedCost, SubstrateTrace};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct OracleModel {
    pub model_version: String,
    pub traces_count: usize,
    pub wall_coef: [f64; 5],
    pub rss_coef: [f64; 5],
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq)]
pub struct OracleFeatures {
    pub op_count: f64,
    pub feature_dim: f64,
    pub scan_hidden_dim: f64,
    pub window_len: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct SafetyBudget {
    pub max_state_bytes: u64,
    pub rss_hard_limit_bytes: u64,
    pub max_mapped_bytes: u64,
    pub max_steps: u64,
}

impl OracleModel {
    pub fn default_model() -> Self {
        Self {
            model_version: "apfsc-hw-oracle-v1".to_string(),
            traces_count: 0,
            wall_coef: [0.0; 5],
            rss_coef: [0.0; 5],
        }
    }
}

impl SafetyBudget {
    pub fn from_config(cfg: &Phase1Config) -> Self {
        Self {
            max_state_bytes: cfg.limits.state_tile_bytes_max,
            rss_hard_limit_bytes: cfg.limits.rss_hard_limit_bytes,
            max_mapped_bytes: cfg.limits.max_concurrent_mapped_bytes,
            max_steps: 1_000_000,
        }
    }

    pub fn validate_envelope(&self, env: &ResourceEnvelope) -> Result<()> {
        if !matches!(env.backend, BackendKind::Tier0Cpu | BackendKind::InterpTier0) {
            return Err(ApfscError::Validation(
                "unsupported backend for judged path".to_string(),
            ));
        }
        if env.max_state_bytes > self.max_state_bytes {
            return Err(ApfscError::Validation(
                "state bytes exceed safety budget".to_string(),
            ));
        }
        if env.peak_rss_limit_bytes > self.rss_hard_limit_bytes {
            return Err(ApfscError::Validation(
                "rss limit exceeds safety budget".to_string(),
            ));
        }
        if env.max_mapped_bytes > self.max_mapped_bytes {
            return Err(ApfscError::Validation(
                "mapped bytes exceed safety budget".to_string(),
            ));
        }
        if env.max_steps > self.max_steps {
            return Err(ApfscError::Validation(
                "max steps exceed safety budget".to_string(),
            ));
        }
        Ok(())
    }
}

pub fn update_oracle_cache(root: &Path, traces: &[SubstrateTrace]) -> Result<()> {
    let archive = root.join("archive/hardware_trace_calibration.jsonl");
    for trace in traces {
        append_jsonl_atomic(&archive, trace)?;
    }

    let all: Vec<SubstrateTrace> = read_jsonl(&archive)?;
    let model = fit_oracle_model(&all);
    write_json_atomic(&root.join("archive/hardware_oracle_model.json"), &model)
}

pub fn load_oracle(root: &Path) -> Result<OracleModel> {
    let path = root.join("archive/hardware_oracle_model.json");
    if !path.exists() {
        return Ok(OracleModel::default_model());
    }
    read_json(&path)
}

pub fn predict_cost(model: &OracleModel, f: OracleFeatures) -> PredictedCost {
    let xs = [
        1.0,
        f.op_count,
        f.feature_dim,
        f.scan_hidden_dim,
        f.window_len,
    ];
    let wall = dot(model.wall_coef, xs).max(0.0);
    let rss = dot(model.rss_coef, xs).max(0.0);

    let risk = ((wall / 1000.0) + (rss / (1024.0 * 1024.0 * 1024.0))).min(100.0);
    PredictedCost {
        wall_ms: wall,
        peak_rss_bytes: rss as u64,
        risk_score: risk,
    }
}

pub fn oracle_penalty(model: &OracleModel, f: OracleFeatures) -> f64 {
    let p = predict_cost(model, f);
    p.risk_score
}

fn fit_oracle_model(traces: &[SubstrateTrace]) -> OracleModel {
    if traces.is_empty() {
        return OracleModel::default_model();
    }

    let xs: Vec<[f64; 5]> = traces
        .iter()
        .map(|t| {
            [
                1.0,
                t.op_count as f64,
                t.feature_dim as f64,
                t.scan_hidden_dim as f64,
                t.window_len as f64,
            ]
        })
        .collect();
    let ys_wall: Vec<f64> = traces.iter().map(|t| t.wall_ms as f64).collect();
    let ys_rss: Vec<f64> = traces.iter().map(|t| t.peak_rss_bytes as f64).collect();

    OracleModel {
        model_version: "apfsc-hw-oracle-v1".to_string(),
        traces_count: traces.len(),
        wall_coef: fit_diag_linear(&xs, &ys_wall),
        rss_coef: fit_diag_linear(&xs, &ys_rss),
    }
}

fn fit_diag_linear(xs: &[[f64; 5]], ys: &[f64]) -> [f64; 5] {
    // Deterministic diagonal least-squares approximation; enough for ranking only.
    let mut coeff = [0.0; 5];
    for j in 0..5 {
        let mut num = 0.0;
        let mut den = 0.0;
        for (row, y) in xs.iter().zip(ys.iter().copied()) {
            num += row[j] * y;
            den += row[j] * row[j];
        }
        coeff[j] = if den > 0.0 { num / den } else { 0.0 };
    }
    coeff
}

fn dot(a: [f64; 5], b: [f64; 5]) -> f64 {
    a.iter().zip(b.iter()).map(|(x, y)| x * y).sum()
}
