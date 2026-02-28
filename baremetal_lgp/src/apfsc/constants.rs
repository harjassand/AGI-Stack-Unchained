use std::collections::BTreeMap;

pub const DEFAULT_PROTOCOL_VERSION: &str = "apfsc-phase1-mvp-v1";
pub const DEFAULT_ARTIFACT_ROOT: &str = ".apfsc";

pub const RSS_HARD_LIMIT_BYTES: u64 = 12 * 1024 * 1024 * 1024;
pub const RSS_ABORT_LIMIT_BYTES: u64 = 14 * 1024 * 1024 * 1024;
pub const MAX_CONCURRENT_MAPPED_BYTES: u64 = 2 * 1024 * 1024 * 1024;
pub const SEGMENT_BYTES: u64 = 256 * 1024 * 1024;
pub const STATE_TILE_BYTES_MAX: u64 = 2 * 1024 * 1024;
pub const MAX_PUBLIC_WORKERS: u32 = 2;
pub const MAX_INCUBATOR_WORKERS: u32 = 1;
pub const MAX_CANARY_WORKERS: u32 = 1;
pub const MAX_PUBLIC_CANDIDATES: usize = 32;
pub const MAX_HOLDOUT_ADMISSIONS: usize = 8;
pub const MAX_RESIDENT_INCUBATORS: usize = 12;
pub const FAST_WEIGHT_MAX_BYTES: u64 = 2 * 1024 * 1024;

pub const DEFAULT_WINDOW_LEN: u32 = 256;
pub const DEFAULT_STRIDE: u32 = 64;
pub const DEFAULT_WITNESS_COUNT: usize = 32;
pub const DEFAULT_WITNESS_ROTATION: usize = 8;

pub const EPSILON_MASS: f32 = 1e-4;
pub const U16_MASS_TOTAL: u32 = 65_536;

pub const SPLIT_KEYS: [&str; 7] = [
    "train",
    "public",
    "holdout",
    "anchor",
    "canary",
    "transfer_train",
    "transfer_eval",
];

pub fn default_split_ratios() -> BTreeMap<String, f64> {
    let mut m = BTreeMap::new();
    m.insert("train".to_string(), 0.60);
    m.insert("public".to_string(), 0.15);
    m.insert("holdout".to_string(), 0.10);
    m.insert("anchor".to_string(), 0.05);
    m.insert("canary".to_string(), 0.05);
    m.insert("transfer_train".to_string(), 0.03);
    m.insert("transfer_eval".to_string(), 0.02);
    m
}

pub const ERROR_ATLAS_BINS: [&str; 6] = [
    "periodicity_miss",
    "copy_span_miss",
    "delimiter_reset_miss",
    "entropy_overspread",
    "long_memory_miss",
    "other",
];
