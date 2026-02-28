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
pub const MAX_ACTIVE_FAMILIES: usize = 8;
pub const MAX_STATIC_PUBLIC_CANDIDATES: usize = 32;
pub const MAX_TRANSFER_PUBLIC_CANDIDATES: usize = 12;
pub const MAX_ROBUST_PUBLIC_CANDIDATES: usize = 12;
pub const MAX_HOLDOUT_STATIC_ADMISSIONS: usize = 6;
pub const MAX_HOLDOUT_XFER_ROBUST_ADMISSIONS: usize = 4;
pub const MAX_TRANSFER_WORKERS: u32 = 1;
pub const MAX_ROBUST_WORKERS: u32 = 1;
pub const MAX_TRANSFER_FAST_WEIGHT_BYTES: u64 = 256 * 1024;
pub const MAX_TRANSFER_DELTA_BITS: u64 = 524_288;
pub const CODELEN_REF_BYTES: u64 = 4096;
pub const TRANSFER_REF_BYTES: u64 = 4096;
pub const MAX_SCIR_CORE_OPS: u32 = 4096;
pub const MAX_MACRO_CALLS_PER_PROGRAM: u32 = 16;
pub const MAX_MACRO_EXPANSION_OPS: u32 = 256;
pub const MAX_MACRO_DEPTH: u32 = 1;
pub const MAX_EGRAPH_NODES: u32 = 50_000;
pub const MAX_EGRAPH_EXTRACTIONS: u32 = 32;
pub const MAX_PARADIGM_PUBLIC_CANDIDATES: usize = 12;
pub const MAX_PWARM_HOLDOUT_ADMISSIONS: usize = 2;
pub const MAX_PCOLD_HOLDOUT_ADMISSIONS: usize = 1;
pub const MAX_PARADIGM_CANARY_WINDOWS_WARM: u32 = 128;
pub const MAX_PARADIGM_CANARY_WINDOWS_COLD: u32 = 256;
pub const MAX_COMPAT_HEAD_BYTES: u64 = 4 * 1024 * 1024;

pub const MIN_MACRO_SUPPORT: u32 = 3;
pub const MIN_MACRO_PUBLIC_GAIN_BPB: f64 = 0.001;
pub const MIN_MACRO_REDUCTION_RATIO: f64 = 1.20;
pub const MAX_INDUCED_MACROS_PER_EPOCH: u32 = 8;

pub const DEFAULT_WINDOW_LEN: u32 = 256;
pub const DEFAULT_STRIDE: u32 = 64;
pub const DEFAULT_WITNESS_COUNT: usize = 32;
pub const DEFAULT_WITNESS_ROTATION: usize = 8;

pub const EPSILON_MASS: f32 = 1e-4;
pub const U16_MASS_TOTAL: u32 = 65_536;

pub const SPLIT_KEYS: [&str; 10] = [
    "train",
    "public",
    "holdout",
    "anchor",
    "canary",
    "transfer_train",
    "transfer_eval",
    "robust_public",
    "robust_holdout",
    "challenge_stub",
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

pub fn phase2_base_split_ratios() -> BTreeMap<String, f64> {
    let mut m = BTreeMap::new();
    m.insert("train".to_string(), 0.60);
    m.insert("static_public".to_string(), 0.15);
    m.insert("static_holdout".to_string(), 0.10);
    m.insert("anchor".to_string(), 0.05);
    m.insert("canary".to_string(), 0.05);
    m.insert("reserve".to_string(), 0.05);
    m
}

pub fn phase2_transfer_split_ratios() -> BTreeMap<String, f64> {
    let mut m = BTreeMap::new();
    m.insert("transfer_train".to_string(), 0.60);
    m.insert("transfer_eval".to_string(), 0.40);
    m
}

pub fn phase2_robust_split_ratios() -> BTreeMap<String, f64> {
    let mut m = BTreeMap::new();
    m.insert("robust_public".to_string(), 0.60);
    m.insert("robust_holdout".to_string(), 0.40);
    m
}

pub fn phase2_challenge_stub_split_ratios() -> BTreeMap<String, f64> {
    let mut m = BTreeMap::new();
    m.insert("challenge_stub".to_string(), 1.0);
    m
}

pub const ERROR_ATLAS_BINS: [&str; 7] = [
    "periodicity_miss",
    "copy_span_miss",
    "delimiter_reset_miss",
    "entropy_overspread",
    "long_memory_miss",
    "nuisance_mismatch",
    "boundary_phase_miss",
];
