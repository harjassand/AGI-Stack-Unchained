use bincode::Options;
use serde::{Deserialize, Serialize};

use super::ast::AstProgram;

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct RegimeSpec {
    pub version: u32,
    pub spec_seed_salt: u64,

    pub input_len: u32,
    pub output_len: u32,

    pub meta_u32_len: u32,
    pub meta_f32_len: u32,

    pub episode_param_count: u32,
    pub input_dist: InputDistSpec,

    pub ast: AstProgram,

    pub schedule: PiecewiseScheduleSpec,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub enum InputDistSpec {
    Uniform { lo: f32, hi: f32 },
    Normal { mean: f32, std: f32 },
    Rademacher { scale: f32 },
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct PiecewiseScheduleSpec {
    pub segments: Vec<ScheduleSegment>,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct ScheduleSegment {
    pub start_episode: u32,
    pub end_episode: u32,
    pub param_scale: f32,
    pub input_scale: f32,
}

pub fn spec_hash_32(spec: &RegimeSpec) -> [u8; 32] {
    let bytes = bincode::DefaultOptions::new()
        .with_fixint_encoding()
        .with_little_endian()
        .serialize(spec)
        .expect("failed to serialize RegimeSpec for hashing");
    *blake3::hash(&bytes).as_bytes()
}
