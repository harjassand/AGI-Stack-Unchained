use std::collections::BTreeMap;
use std::fs;
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Mutex, OnceLock};

use serde::de::DeserializeOwned;
use serde::Serialize;

use crate::apf3;
use crate::apfsc::errors::{io_err, ApfscError, Result};
use crate::apfsc::types::{EpochSnapshot, PackKind};

static VOLATILE_FILES: OnceLock<Mutex<BTreeMap<PathBuf, Vec<u8>>>> = OnceLock::new();
static CLASS_M_GENERATION_COUNT: AtomicU64 = AtomicU64::new(0);
static DEMON_LANE_MORTALITY_COUNT: AtomicU64 = AtomicU64::new(0);
static DEMON_LANE_CONSECUTIVE_MORTALITY_COUNT: AtomicU64 = AtomicU64::new(0);
static BEST_DEMON_SURVIVAL_MARGIN_BITS: AtomicU64 =
    AtomicU64::new(f64::NEG_INFINITY.to_bits());
static CURRENT_DEMON_SURVIVAL_MARGIN_BITS: AtomicU64 =
    AtomicU64::new(f64::NEG_INFINITY.to_bits());
static LAST_REJECTED_PROPOSAL_SCORE_BITS: AtomicU64 =
    AtomicU64::new(f64::NEG_INFINITY.to_bits());
static LAST_REJECTED_PROPOSAL_REASON: OnceLock<Mutex<Option<String>>> = OnceLock::new();
static LAST_REJECTED_PROPOSAL_TRACE: OnceLock<Mutex<Option<String>>> = OnceLock::new();

fn volatile_files() -> &'static Mutex<BTreeMap<PathBuf, Vec<u8>>> {
    VOLATILE_FILES.get_or_init(|| Mutex::new(BTreeMap::new()))
}

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize, PartialEq)]
pub struct OmegaVolatileMetrics {
    pub class_m_generation_count: u64,
    pub demon_lane_mortality_count: u64,
    pub demon_lane_consecutive_mortality_count: u64,
    pub best_demon_survival_margin: Option<f64>,
    pub current_demon_survival_margin: Option<f64>,
    pub last_rejected_proposal_score: Option<f64>,
    pub last_rejected_proposal_reason: Option<String>,
    pub last_rejected_proposal_trace: Option<String>,
}

pub fn reset_omega_volatile_metrics() {
    CLASS_M_GENERATION_COUNT.store(0, Ordering::Relaxed);
    DEMON_LANE_MORTALITY_COUNT.store(0, Ordering::Relaxed);
    DEMON_LANE_CONSECUTIVE_MORTALITY_COUNT.store(0, Ordering::Relaxed);
    BEST_DEMON_SURVIVAL_MARGIN_BITS.store(f64::NEG_INFINITY.to_bits(), Ordering::Relaxed);
    CURRENT_DEMON_SURVIVAL_MARGIN_BITS.store(f64::NEG_INFINITY.to_bits(), Ordering::Relaxed);
    LAST_REJECTED_PROPOSAL_SCORE_BITS.store(f64::NEG_INFINITY.to_bits(), Ordering::Relaxed);
    let mut guard = LAST_REJECTED_PROPOSAL_REASON
        .get_or_init(|| Mutex::new(None))
        .lock()
        .unwrap_or_else(|e| e.into_inner());
    *guard = None;
    let mut trace_guard = LAST_REJECTED_PROPOSAL_TRACE
        .get_or_init(|| Mutex::new(None))
        .lock()
        .unwrap_or_else(|e| e.into_inner());
    *trace_guard = None;
}

pub fn note_class_m_generation_attempt() -> u64 {
    CLASS_M_GENERATION_COUNT.fetch_add(1, Ordering::Relaxed) + 1
}

pub fn note_demon_lane_mortality() -> u64 {
    let _ = DEMON_LANE_CONSECUTIVE_MORTALITY_COUNT.fetch_add(1, Ordering::Relaxed) + 1;
    DEMON_LANE_MORTALITY_COUNT.fetch_add(1, Ordering::Relaxed) + 1
}

pub fn note_demon_lane_survival() {
    DEMON_LANE_CONSECUTIVE_MORTALITY_COUNT.store(0, Ordering::Relaxed);
}

pub fn demon_lane_consecutive_mortality_count() -> u64 {
    DEMON_LANE_CONSECUTIVE_MORTALITY_COUNT.load(Ordering::Relaxed)
}

fn decode_best_demon_survival_margin(bits: u64) -> Option<f64> {
    let v = f64::from_bits(bits);
    if v.is_infinite() && v.is_sign_negative() {
        None
    } else if v.is_finite() {
        Some(v)
    } else {
        None
    }
}

pub fn best_demon_survival_margin() -> Option<f64> {
    decode_best_demon_survival_margin(BEST_DEMON_SURVIVAL_MARGIN_BITS.load(Ordering::Relaxed))
}

pub fn current_demon_survival_margin() -> Option<f64> {
    decode_best_demon_survival_margin(CURRENT_DEMON_SURVIVAL_MARGIN_BITS.load(Ordering::Relaxed))
}

pub fn note_current_demon_survival_margin(margin: f64) -> Option<f64> {
    if !margin.is_finite() {
        return current_demon_survival_margin();
    }
    CURRENT_DEMON_SURVIVAL_MARGIN_BITS.store(margin.to_bits(), Ordering::Relaxed);
    Some(margin)
}

pub fn note_best_demon_survival_margin(margin: f64) -> Option<f64> {
    if !margin.is_finite() {
        return best_demon_survival_margin();
    }
    loop {
        let current_bits = BEST_DEMON_SURVIVAL_MARGIN_BITS.load(Ordering::Relaxed);
        let current = f64::from_bits(current_bits);
        if margin <= current {
            return decode_best_demon_survival_margin(current_bits);
        }
        if BEST_DEMON_SURVIVAL_MARGIN_BITS
            .compare_exchange(
                current_bits,
                margin.to_bits(),
                Ordering::Relaxed,
                Ordering::Relaxed,
            )
            .is_ok()
        {
            return Some(margin);
        }
    }
}

pub fn last_rejected_proposal_score() -> Option<f64> {
    decode_best_demon_survival_margin(LAST_REJECTED_PROPOSAL_SCORE_BITS.load(Ordering::Relaxed))
}

pub fn last_rejected_proposal_reason() -> Option<String> {
    LAST_REJECTED_PROPOSAL_REASON
        .get_or_init(|| Mutex::new(None))
        .lock()
        .unwrap_or_else(|e| e.into_inner())
        .clone()
}

pub fn note_last_rejected_proposal(score: f64, reason: impl Into<String>) {
    let score_bits = if score.is_finite() {
        score.to_bits()
    } else {
        f64::NEG_INFINITY.to_bits()
    };
    LAST_REJECTED_PROPOSAL_SCORE_BITS.store(score_bits, Ordering::Relaxed);
    let mut guard = LAST_REJECTED_PROPOSAL_REASON
        .get_or_init(|| Mutex::new(None))
        .lock()
        .unwrap_or_else(|e| e.into_inner());
    let reason = reason.into();
    if reason.trim().is_empty() {
        *guard = None;
    } else {
        *guard = Some(reason);
    }
}

pub fn last_rejected_proposal_trace() -> Option<String> {
    LAST_REJECTED_PROPOSAL_TRACE
        .get_or_init(|| Mutex::new(None))
        .lock()
        .unwrap_or_else(|e| e.into_inner())
        .clone()
}

pub fn note_last_rejected_proposal_trace(trace: impl Into<String>) {
    let mut guard = LAST_REJECTED_PROPOSAL_TRACE
        .get_or_init(|| Mutex::new(None))
        .lock()
        .unwrap_or_else(|e| e.into_inner());
    let trace = trace.into();
    if trace.trim().is_empty() {
        *guard = None;
    } else {
        *guard = Some(trace);
    }
}

pub fn omega_volatile_metrics() -> OmegaVolatileMetrics {
    OmegaVolatileMetrics {
        class_m_generation_count: CLASS_M_GENERATION_COUNT.load(Ordering::Relaxed),
        demon_lane_mortality_count: DEMON_LANE_MORTALITY_COUNT.load(Ordering::Relaxed),
        demon_lane_consecutive_mortality_count: DEMON_LANE_CONSECUTIVE_MORTALITY_COUNT
            .load(Ordering::Relaxed),
        best_demon_survival_margin: best_demon_survival_margin(),
        current_demon_survival_margin: current_demon_survival_margin(),
        last_rejected_proposal_score: last_rejected_proposal_score(),
        last_rejected_proposal_reason: last_rejected_proposal_reason(),
        last_rejected_proposal_trace: last_rejected_proposal_trace(),
    }
}

fn omega_env_enabled() -> bool {
    std::env::var("APFSC_OMEGA_MODE")
        .map(|v| {
            let t = v.to_ascii_lowercase();
            t == "1" || t == "true" || t == "yes" || t == "on"
        })
        .unwrap_or(false)
}

pub fn omega_mode_enabled() -> bool {
    omega_env_enabled()
}

pub fn silent_run_enabled() -> bool {
    omega_mode_enabled()
        || std::env::var("APFSC_SILENT_RUN")
            .map(|v| {
                let t = v.to_ascii_lowercase();
                t == "1" || t == "true" || t == "yes" || t == "on"
            })
            .unwrap_or(false)
}

fn is_discoveries_path(path: &Path) -> bool {
    path.components()
        .any(|c| matches!(c, std::path::Component::Normal(seg) if seg == "discoveries"))
}

fn should_persist_to_disk(path: &Path) -> bool {
    !silent_run_enabled() || is_discoveries_path(path)
}

fn volatile_write(path: &Path, bytes: &[u8]) {
    let mut guard = volatile_files().lock().unwrap_or_else(|e| e.into_inner());
    guard.insert(path.to_path_buf(), bytes.to_vec());
}

fn volatile_read(path: &Path) -> Option<Vec<u8>> {
    let guard = volatile_files().lock().unwrap_or_else(|e| e.into_inner());
    guard.get(path).cloned()
}

fn volatile_remove(path: &Path) {
    let mut guard = volatile_files().lock().unwrap_or_else(|e| e.into_inner());
    guard.remove(path);
}

fn volatile_remove_prefix(prefix: &Path) {
    let mut guard = volatile_files().lock().unwrap_or_else(|e| e.into_inner());
    let keys = guard.keys().cloned().collect::<Vec<_>>();
    for k in keys {
        if k.starts_with(prefix) {
            guard.remove(&k);
        }
    }
}

pub fn path_exists(path: &Path) -> bool {
    if volatile_read(path).is_some() || path.exists() {
        return true;
    }
    let guard = volatile_files().lock().unwrap_or_else(|e| e.into_inner());
    guard.keys().any(|k| k.starts_with(path))
}

pub fn read_bytes(path: &Path) -> Result<Vec<u8>> {
    if let Some(v) = volatile_read(path) {
        return Ok(v);
    }
    fs::read(path).map_err(|e| io_err(path, e))
}

fn read_bytes_if_exists(path: &Path) -> Result<Option<Vec<u8>>> {
    if let Some(v) = volatile_read(path) {
        return Ok(Some(v));
    }
    if !path.exists() {
        return Ok(None);
    }
    Ok(Some(fs::read(path).map_err(|e| io_err(path, e))?))
}

pub fn create_dir_all_if_persistent(dir: &Path) -> Result<()> {
    if silent_run_enabled() && !is_discoveries_path(dir) {
        return Ok(());
    }
    fs::create_dir_all(dir).map_err(|e| io_err(dir, e))
}

pub fn remove_file_if_exists(path: &Path) -> Result<()> {
    if should_persist_to_disk(path) {
        match fs::remove_file(path) {
            Ok(()) => Ok(()),
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(()),
            Err(e) => Err(io_err(path, e)),
        }
    } else {
        volatile_remove(path);
        Ok(())
    }
}

pub fn remove_dir_all_if_exists(path: &Path) -> Result<()> {
    if should_persist_to_disk(path) {
        match fs::remove_dir_all(path) {
            Ok(()) => Ok(()),
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(()),
            Err(e) => Err(io_err(path, e)),
        }
    } else {
        volatile_remove_prefix(path);
        Ok(())
    }
}

pub fn ensure_layout(root: &Path) -> Result<()> {
    let dirs = if silent_run_enabled() {
        vec![root.join("discoveries"), root.join("discoveries/materials")]
    } else {
        vec![
            root.join("protocol"),
            root.join("snapshots"),
            root.join("active"),
            root.join("macro_registry"),
            root.join("constellations"),
            root.join("challenges"),
            root.join("formal_policy"),
            root.join("toolpacks"),
            root.join("law_archive"),
            root.join("search_laws"),
            root.join("portfolios"),
            root.join("qd_archive"),
            root.join("packs/reality"),
            root.join("packs/prior"),
            root.join("packs/substrate"),
            root.join("packs/formal"),
            root.join("packs/tool"),
            root.join("banks"),
            root.join("candidates"),
            root.join("receipts/ingress"),
            root.join("receipts/public"),
            root.join("receipts/holdout"),
            root.join("receipts/public_static"),
            root.join("receipts/public_transfer"),
            root.join("receipts/public_robust"),
            root.join("receipts/fresh_public"),
            root.join("receipts/fresh_holdout"),
            root.join("receipts/holdout_static"),
            root.join("receipts/holdout_transfer"),
            root.join("receipts/holdout_robust"),
            root.join("receipts/bridge"),
            root.join("receipts/judge"),
            root.join("receipts/dethroning_audit"),
            root.join("receipts/canary"),
            root.join("receipts/activation"),
            root.join("receipts/rosetta"),
            root.join("receipts/truth_laws"),
            root.join("receipts/ectoderm"),
            root.join("receipts/extropy"),
            root.join("receipts/resonance_distiller"),
            root.join("discoveries"),
            root.join("discoveries/materials"),
            root.join("pointers"),
            root.join("archive"),
            root.join("archives"),
            root.join("queues"),
        ]
    };
    for dir in dirs {
        create_dir_all_if_persistent(&dir)?;
    }
    Ok(())
}

pub fn digest_bytes(bytes: &[u8]) -> String {
    blake3::hash(bytes).to_hex().to_string()
}

pub fn digest_reader(mut r: impl Read) -> Result<String> {
    let mut hasher = blake3::Hasher::new();
    let mut buf = [0u8; 8192];
    loop {
        let n = r
            .read(&mut buf)
            .map_err(|e| ApfscError::Protocol(format!("hash read failed: {e}")))?;
        if n == 0 {
            break;
        }
        hasher.update(&buf[..n]);
    }
    Ok(hasher.finalize().to_hex().to_string())
}

pub fn digest_file(path: &Path) -> Result<String> {
    let f = fs::File::open(path).map_err(|e| io_err(path, e))?;
    digest_reader(f)
}

pub fn digest_json<T: Serialize>(value: &T) -> Result<String> {
    let body = serde_json::to_vec(value)?;
    Ok(digest_bytes(&body))
}

pub fn write_bytes_atomic(path: &Path, bytes: &[u8]) -> Result<()> {
    if should_persist_to_disk(path) {
        apf3::write_atomic(path, bytes).map_err(ApfscError::Protocol)
    } else {
        volatile_write(path, bytes);
        Ok(())
    }
}

pub fn write_json_atomic<T: Serialize + ?Sized>(path: &Path, value: &T) -> Result<()> {
    let body = serde_json::to_vec_pretty(value)?;
    write_bytes_atomic(path, &body)
}

pub fn read_json<T: DeserializeOwned>(path: &Path) -> Result<T> {
    let body = read_bytes(path)?;
    Ok(serde_json::from_slice(&body)?)
}

pub fn append_jsonl_atomic<T: Serialize>(path: &Path, value: &T) -> Result<()> {
    let mut current = read_bytes_if_exists(path)?.unwrap_or_default();
    let line = serde_json::to_vec(value)?;
    current.extend(line);
    current.push(b'\n');
    write_bytes_atomic(path, &current)
}

pub fn read_jsonl<T: DeserializeOwned>(path: &Path) -> Result<Vec<T>> {
    let Some(body) = read_bytes_if_exists(path)? else {
        return Ok(Vec::new());
    };
    let body = String::from_utf8(body)
        .map_err(|e| ApfscError::Protocol(format!("invalid utf-8 jsonl: {e}")))?;
    let mut out = Vec::new();
    for line in body.lines() {
        if line.trim().is_empty() {
            continue;
        }
        out.push(serde_json::from_str::<T>(line)?);
    }
    Ok(out)
}

pub fn write_pointer(root: &Path, name: &str, value: &str) -> Result<()> {
    let path = root.join("pointers").join(name);
    write_bytes_atomic(&path, value.as_bytes())
}

pub fn read_pointer(root: &Path, name: &str) -> Result<String> {
    let path = root.join("pointers").join(name);
    let body = String::from_utf8(read_bytes(&path)?)
        .map_err(|e| ApfscError::Protocol(format!("pointer utf-8 decode failed: {e}")))?;
    Ok(body.trim().to_string())
}

pub fn pack_kind_dir(kind: PackKind) -> &'static str {
    match kind {
        PackKind::Reality => "reality",
        PackKind::Prior => "prior",
        PackKind::Substrate => "substrate",
        PackKind::Formal => "formal",
        PackKind::Tool => "tool",
    }
}

pub fn pack_dir(root: &Path, kind: PackKind, hash: &str) -> PathBuf {
    root.join("packs").join(pack_kind_dir(kind)).join(hash)
}

pub fn candidate_dir(root: &Path, candidate_hash: &str) -> PathBuf {
    root.join("candidates").join(candidate_hash)
}

pub fn receipt_path(root: &Path, lane: &str, name: &str) -> PathBuf {
    root.join("receipts").join(lane).join(name)
}

pub fn store_snapshot(root: &Path, snapshot: &EpochSnapshot) -> Result<()> {
    let path = root
        .join("snapshots")
        .join(format!("{}.json", snapshot.snapshot_hash));
    write_json_atomic(&path, snapshot)
}

pub fn load_snapshot(root: &Path, snapshot_hash: &str) -> Result<EpochSnapshot> {
    let path = root
        .join("snapshots")
        .join(format!("{}.json", snapshot_hash));
    read_json(&path)
}

pub fn list_pack_hashes(root: &Path, kind: PackKind) -> Result<Vec<String>> {
    let dir = root.join("packs").join(pack_kind_dir(kind));
    let mut names = BTreeMap::<String, ()>::new();
    if dir.exists() {
        for entry in fs::read_dir(&dir).map_err(|e| io_err(&dir, e))? {
            let entry = entry.map_err(|e| io_err(&dir, e))?;
            if entry
                .file_type()
                .map_err(|e| io_err(entry.path(), e))?
                .is_dir()
            {
                names.insert(entry.file_name().to_string_lossy().to_string(), ());
            }
        }
    }
    if silent_run_enabled() {
        let guard = volatile_files().lock().unwrap_or_else(|e| e.into_inner());
        for p in guard.keys() {
            if !p.starts_with(&dir) {
                continue;
            }
            if let Ok(rel) = p.strip_prefix(&dir) {
                if let Some(first) = rel.iter().next() {
                    names.insert(first.to_string_lossy().to_string(), ());
                }
            }
        }
    }
    Ok(names.into_keys().collect())
}

pub fn list_candidate_hashes(root: &Path) -> Result<Vec<String>> {
    let dir = root.join("candidates");
    let mut names = BTreeMap::<String, ()>::new();
    if dir.exists() {
        for entry in fs::read_dir(&dir).map_err(|e| io_err(&dir, e))? {
            let entry = entry.map_err(|e| io_err(&dir, e))?;
            if entry
                .file_type()
                .map_err(|e| io_err(entry.path(), e))?
                .is_dir()
            {
                names.insert(entry.file_name().to_string_lossy().to_string(), ());
            }
        }
    }
    if silent_run_enabled() {
        let guard = volatile_files().lock().unwrap_or_else(|e| e.into_inner());
        for p in guard.keys() {
            if !p.starts_with(&dir) {
                continue;
            }
            if let Ok(rel) = p.strip_prefix(&dir) {
                if let Some(first) = rel.iter().next() {
                    names.insert(first.to_string_lossy().to_string(), ());
                }
            }
        }
    }
    Ok(names.into_keys().collect())
}

pub fn copy_file(src: &Path, dst: &Path) -> Result<()> {
    if let Some(parent) = dst.parent() {
        create_dir_all_if_persistent(parent)?;
    }
    let bytes = read_bytes(src)?;
    write_bytes_atomic(dst, &bytes)
}

pub fn list_json_files_sorted_by_mtime_desc(dir: &Path, limit: usize) -> Result<Vec<PathBuf>> {
    if !path_exists(dir) {
        return Ok(Vec::new());
    }
    if !dir.exists() {
        if !silent_run_enabled() {
            return Ok(Vec::new());
        }
        let guard = volatile_files().lock().unwrap_or_else(|e| e.into_inner());
        let mut paths = guard
            .keys()
            .filter(|p| p.starts_with(dir))
            .filter(|p| p.extension().and_then(|s| s.to_str()) == Some("json"))
            .cloned()
            .collect::<Vec<_>>();
        paths.sort();
        paths.reverse();
        paths.truncate(limit.max(1));
        return Ok(paths);
    }
    let mut rows = Vec::<(u64, PathBuf)>::new();
    for entry in fs::read_dir(dir).map_err(|e| io_err(dir, e))? {
        let entry = entry.map_err(|e| io_err(dir, e))?;
        let path = entry.path();
        if !entry.file_type().map_err(|e| io_err(&path, e))?.is_file()
            || path.extension().and_then(|s| s.to_str()) != Some("json")
        {
            continue;
        }
        let modified = entry
            .metadata()
            .map_err(|e| io_err(&path, e))?
            .modified()
            .ok()
            .and_then(|t| t.duration_since(std::time::UNIX_EPOCH).ok())
            .map(|d| d.as_secs())
            .unwrap_or(0);
        rows.push((modified, path));
    }
    rows.sort_by(|a, b| b.0.cmp(&a.0));
    Ok(rows
        .into_iter()
        .take(limit.max(1))
        .map(|(_, p)| p)
        .collect())
}

pub fn write_discovery_artifact<T: Serialize>(
    root: &Path,
    discovery_id: &str,
    value: &T,
) -> Result<PathBuf> {
    let dir = root.join("discoveries");
    create_dir_all_if_persistent(&dir)?;
    let path = dir.join(format!("{discovery_id}.json"));
    write_json_atomic(&path, value)?;
    append_jsonl_atomic(&dir.join("stream.jsonl"), value)?;
    Ok(path)
}

pub fn write_material_xyz(root: &Path, material_id: &str, xyz_body: &str) -> Result<PathBuf> {
    let dir = root.join("discoveries").join("materials");
    create_dir_all_if_persistent(&dir)?;
    let path = dir.join(format!("{material_id}.xyz"));
    write_bytes_atomic(&path, xyz_body.as_bytes())?;
    emit_material_discovery_notification();
    Ok(path)
}

fn emit_material_discovery_notification() {
    #[cfg(target_os = "macos")]
    {
        let _ = std::process::Command::new("osascript")
            .args(["-e", "beep 1"])
            .status();
    }
    // Terminal bell fallback so long-running RAM-only omega runs still alert operators.
    eprint!("\u{0007}");
    let _ = std::io::stderr().flush();
}
