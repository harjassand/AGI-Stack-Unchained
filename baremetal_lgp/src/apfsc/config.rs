use std::collections::BTreeMap;
use std::path::Path;

use serde::{Deserialize, Serialize};

use crate::apfsc::constants;
use crate::apfsc::errors::{io_err, Result};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Phase1Config {
    #[serde(default)]
    pub root: RootConfig,
    #[serde(default)]
    pub protocol: ProtocolConfig,
    #[serde(default)]
    pub bank: BankConfig,
    #[serde(default)]
    pub limits: LimitsConfig,
    #[serde(default)]
    pub train: TrainConfig,
    #[serde(default)]
    pub judge: JudgeConfig,
    #[serde(default)]
    pub lanes: LanesConfig,
    #[serde(default)]
    pub incubator: IncubatorConfig,
    #[serde(default)]
    pub witness: WitnessConfig,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct RootConfig {
    #[serde(default = "default_artifact_root")]
    pub artifact_root: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ProtocolConfig {
    #[serde(default = "default_protocol_version")]
    pub version: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct BankConfig {
    #[serde(default = "default_window_len")]
    pub window_len: u32,
    #[serde(default = "default_stride")]
    pub stride: u32,
    #[serde(default = "constants::default_split_ratios")]
    pub split_ratios: BTreeMap<String, f64>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct LimitsConfig {
    #[serde(default = "default_rss_hard_limit_bytes")]
    pub rss_hard_limit_bytes: u64,
    #[serde(default = "default_rss_abort_limit_bytes")]
    pub rss_abort_limit_bytes: u64,
    #[serde(default = "default_max_concurrent_mapped_bytes")]
    pub max_concurrent_mapped_bytes: u64,
    #[serde(default = "default_segment_bytes")]
    pub segment_bytes: u64,
    #[serde(default = "default_state_tile_bytes_max")]
    pub state_tile_bytes_max: u64,
    #[serde(default = "default_max_public_workers")]
    pub max_public_workers: u32,
    #[serde(default = "default_max_incubator_workers")]
    pub max_incubator_workers: u32,
    #[serde(default = "default_max_canary_workers")]
    pub max_canary_workers: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct TrainConfig {
    #[serde(default = "default_train_steps")]
    pub steps: u32,
    #[serde(default = "default_train_lr")]
    pub lr: f32,
    #[serde(default = "default_train_eps")]
    pub eps: f32,
    #[serde(default = "default_train_l2")]
    pub l2: f32,
    #[serde(default = "default_train_clip_grad")]
    pub clip_grad: f32,
    #[serde(default = "default_train_batch_windows")]
    pub batch_windows: usize,
    #[serde(default)]
    pub shuffle: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct JudgeConfig {
    #[serde(default = "default_public_min_delta_bits")]
    pub public_min_delta_bits: f64,
    #[serde(default = "default_holdout_min_delta_bits")]
    pub holdout_min_delta_bits: f64,
    #[serde(default)]
    pub anchor_max_regress_bits: f64,
    #[serde(default)]
    pub mini_transfer_min_delta_bits: f64,
    #[serde(default = "default_require_canary_for_a")]
    pub require_canary_for_a: bool,
    #[serde(default = "default_max_holdout_admissions")]
    pub max_holdout_admissions: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct LanesConfig {
    #[serde(default = "default_max_truth_candidates")]
    pub max_truth_candidates: usize,
    #[serde(default = "default_max_equivalence_candidates")]
    pub max_equivalence_candidates: usize,
    #[serde(default = "default_max_incubator_candidates")]
    pub max_incubator_candidates: usize,
    #[serde(default = "default_max_public_candidates")]
    pub max_public_candidates: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct IncubatorConfig {
    #[serde(default = "default_incubator_min_utility_bits")]
    pub incubator_min_utility_bits: f64,
    #[serde(default = "default_incubator_lambda_code")]
    pub lambda_code: f64,
    #[serde(default = "default_incubator_lambda_risk")]
    pub lambda_risk: f64,
    #[serde(default = "default_incubator_shadow_steps")]
    pub shadow_steps: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct WitnessConfig {
    #[serde(default = "default_witness_count")]
    pub count: usize,
    #[serde(default = "default_witness_rotation")]
    pub rotation: usize,
}

impl Default for Phase1Config {
    fn default() -> Self {
        Self {
            root: RootConfig::default(),
            protocol: ProtocolConfig::default(),
            bank: BankConfig::default(),
            limits: LimitsConfig::default(),
            train: TrainConfig::default(),
            judge: JudgeConfig::default(),
            lanes: LanesConfig::default(),
            incubator: IncubatorConfig::default(),
            witness: WitnessConfig::default(),
        }
    }
}

impl Default for RootConfig {
    fn default() -> Self {
        Self {
            artifact_root: default_artifact_root(),
        }
    }
}

impl Default for ProtocolConfig {
    fn default() -> Self {
        Self {
            version: default_protocol_version(),
        }
    }
}

impl Default for BankConfig {
    fn default() -> Self {
        Self {
            window_len: default_window_len(),
            stride: default_stride(),
            split_ratios: constants::default_split_ratios(),
        }
    }
}

impl Default for LimitsConfig {
    fn default() -> Self {
        Self {
            rss_hard_limit_bytes: default_rss_hard_limit_bytes(),
            rss_abort_limit_bytes: default_rss_abort_limit_bytes(),
            max_concurrent_mapped_bytes: default_max_concurrent_mapped_bytes(),
            segment_bytes: default_segment_bytes(),
            state_tile_bytes_max: default_state_tile_bytes_max(),
            max_public_workers: default_max_public_workers(),
            max_incubator_workers: default_max_incubator_workers(),
            max_canary_workers: default_max_canary_workers(),
        }
    }
}

impl Default for TrainConfig {
    fn default() -> Self {
        Self {
            steps: default_train_steps(),
            lr: default_train_lr(),
            eps: default_train_eps(),
            l2: default_train_l2(),
            clip_grad: default_train_clip_grad(),
            batch_windows: default_train_batch_windows(),
            shuffle: false,
        }
    }
}

impl Default for JudgeConfig {
    fn default() -> Self {
        Self {
            public_min_delta_bits: default_public_min_delta_bits(),
            holdout_min_delta_bits: default_holdout_min_delta_bits(),
            anchor_max_regress_bits: 0.0,
            mini_transfer_min_delta_bits: 0.0,
            require_canary_for_a: default_require_canary_for_a(),
            max_holdout_admissions: default_max_holdout_admissions(),
        }
    }
}

impl Default for LanesConfig {
    fn default() -> Self {
        Self {
            max_truth_candidates: default_max_truth_candidates(),
            max_equivalence_candidates: default_max_equivalence_candidates(),
            max_incubator_candidates: default_max_incubator_candidates(),
            max_public_candidates: default_max_public_candidates(),
        }
    }
}

impl Default for IncubatorConfig {
    fn default() -> Self {
        Self {
            incubator_min_utility_bits: default_incubator_min_utility_bits(),
            lambda_code: default_incubator_lambda_code(),
            lambda_risk: default_incubator_lambda_risk(),
            shadow_steps: default_incubator_shadow_steps(),
        }
    }
}

impl Default for WitnessConfig {
    fn default() -> Self {
        Self {
            count: default_witness_count(),
            rotation: default_witness_rotation(),
        }
    }
}

impl Phase1Config {
    pub fn from_path(path: &Path) -> Result<Self> {
        let body = std::fs::read_to_string(path).map_err(|e| io_err(path, e))?;
        Ok(toml::from_str(&body)?)
    }

    pub fn to_toml_string(&self) -> Result<String> {
        Ok(toml::to_string_pretty(self)?)
    }
}

fn default_artifact_root() -> String {
    constants::DEFAULT_ARTIFACT_ROOT.to_string()
}

fn default_protocol_version() -> String {
    constants::DEFAULT_PROTOCOL_VERSION.to_string()
}

fn default_window_len() -> u32 {
    constants::DEFAULT_WINDOW_LEN
}

fn default_stride() -> u32 {
    constants::DEFAULT_STRIDE
}

fn default_rss_hard_limit_bytes() -> u64 {
    constants::RSS_HARD_LIMIT_BYTES
}

fn default_rss_abort_limit_bytes() -> u64 {
    constants::RSS_ABORT_LIMIT_BYTES
}

fn default_max_concurrent_mapped_bytes() -> u64 {
    constants::MAX_CONCURRENT_MAPPED_BYTES
}

fn default_segment_bytes() -> u64 {
    constants::SEGMENT_BYTES
}

fn default_state_tile_bytes_max() -> u64 {
    constants::STATE_TILE_BYTES_MAX
}

fn default_max_public_workers() -> u32 {
    constants::MAX_PUBLIC_WORKERS
}

fn default_max_incubator_workers() -> u32 {
    constants::MAX_INCUBATOR_WORKERS
}

fn default_max_canary_workers() -> u32 {
    constants::MAX_CANARY_WORKERS
}

fn default_train_steps() -> u32 {
    200
}

fn default_train_lr() -> f32 {
    0.05
}

fn default_train_eps() -> f32 {
    1e-8
}

fn default_train_l2() -> f32 {
    1e-5
}

fn default_train_clip_grad() -> f32 {
    1.0
}

fn default_train_batch_windows() -> usize {
    8
}

fn default_public_min_delta_bits() -> f64 {
    32.0
}

fn default_holdout_min_delta_bits() -> f64 {
    16.0
}

fn default_require_canary_for_a() -> bool {
    true
}

fn default_max_holdout_admissions() -> usize {
    constants::MAX_HOLDOUT_ADMISSIONS
}

fn default_max_truth_candidates() -> usize {
    12
}

fn default_max_equivalence_candidates() -> usize {
    8
}

fn default_max_incubator_candidates() -> usize {
    8
}

fn default_max_public_candidates() -> usize {
    constants::MAX_PUBLIC_CANDIDATES
}

fn default_incubator_min_utility_bits() -> f64 {
    8.0
}

fn default_incubator_lambda_code() -> f64 {
    0.1
}

fn default_incubator_lambda_risk() -> f64 {
    0.1
}

fn default_incubator_shadow_steps() -> u32 {
    100
}

fn default_witness_count() -> usize {
    constants::DEFAULT_WITNESS_COUNT
}

fn default_witness_rotation() -> usize {
    constants::DEFAULT_WITNESS_ROTATION
}
