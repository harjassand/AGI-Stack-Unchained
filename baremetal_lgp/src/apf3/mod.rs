pub mod a64_scan;
pub mod aal_exec;
pub mod aal_ir;
pub mod digest;
pub mod judge;
pub mod metachunkpack;
pub mod morphisms;
pub mod nativeblock;
pub mod omega;
pub mod profiler;
pub mod sfi;
pub mod wake;

use std::fs;
use std::path::{Path, PathBuf};

use rand::SeedableRng;
use rand_chacha::ChaCha12Rng;

pub fn splitmix64(mut x: u64) -> u64 {
    x = x.wrapping_add(0x9E37_79B9_7F4A_7C15);
    let mut z = x;
    z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
    z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
    z ^ (z >> 31)
}

pub fn mix_seed(base: u64, tag: u64, idx: u64) -> u64 {
    splitmix64(base ^ splitmix64(tag) ^ splitmix64(idx))
}

pub fn seeded_rng(base: u64, tag: u64, idx: u64) -> ChaCha12Rng {
    ChaCha12Rng::seed_from_u64(mix_seed(base, tag, idx))
}

pub fn write_atomic(path: &Path, bytes: &[u8]) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }

    let file_name = path
        .file_name()
        .and_then(|f| f.to_str())
        .ok_or_else(|| "invalid path for atomic write".to_string())?;
    let tmp_name = format!(".{file_name}.tmp");

    let mut tmp_path = PathBuf::from(path);
    tmp_path.set_file_name(tmp_name);

    fs::write(&tmp_path, bytes).map_err(|e| e.to_string())?;
    fs::rename(&tmp_path, path).map_err(|e| e.to_string())
}
