use std::collections::BTreeSet;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Mutex, OnceLock};
use std::time::{Instant, SystemTime, UNIX_EPOCH};

use serde::{Deserialize, Serialize};

use crate::apfsc::artifacts::{
    append_jsonl_atomic, create_dir_all_if_persistent, digest_bytes, read_json, read_jsonl,
    write_json_atomic,
};
use crate::apfsc::config::Phase1Config;
use crate::apfsc::errors::{ApfscError, Result};

const ARXIV_QUERY: &str = "cat:cond-mat.supr-con+OR+cat:physics.chem-ph";
const ARXIV_ENDPOINT: &str = "https://export.arxiv.org/api/query";
const ARXIV_DEFAULT_MAX_RESULTS: usize = 24;
const ARXIV_STALE_S: u64 = 6 * 60 * 60;
const ARXIV_RETRY_COOLDOWN_S: u64 = 15 * 60;
const MAX_SEMANTIC_FORMULAS: usize = 64;
const MAX_SEMANTIC_TEMPERATURES: usize = 24;
const MAX_TENSOR_SEED_ATOMS: usize = 128;

pub fn arxiv_staleness_threshold_seconds(cfg: &Phase1Config, default_seconds: u64) -> u64 {
    let _ = cfg;
    default_seconds
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct AfferentTelemetry {
    pub unix_s: u64,
    pub loadavg_1m: f32,
    pub cpu_speed_limit_pct: f32,
    pub thermal_pressure: f32,
    pub power_proxy_watts: f32,
    pub available_cores: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct AfferentEpochSample {
    pub epoch: u64,
    pub telemetry: AfferentTelemetry,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ArxivPaper {
    pub id: String,
    pub title: String,
    pub summary: String,
    pub published: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct AfferentExternalSnapshot {
    pub unix_s: u64,
    pub source: String,
    pub query: String,
    pub max_results: u32,
    pub entry_count: u32,
    pub payload_hash: String,
    pub formula_density: f32,
    pub eigen_signal: f32,
    pub boundary_signal: f32,
    pub novelty_signal: f32,
    pub composite_signal: f32,
    #[serde(default)]
    pub semantic_formula_count: u32,
    #[serde(default)]
    pub semantic_formula_examples: Vec<String>,
    #[serde(default)]
    pub semantic_tc_kelvin: Vec<f32>,
    #[serde(default)]
    pub semantic_lattice_hints: Vec<String>,
    #[serde(default = "default_alien_target_objective")]
    pub alien_target_objective: String,
    #[serde(default)]
    pub tensor_seed: Option<AfferentTensorSeed>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct AfferentTensorSeed {
    pub formula: String,
    pub atomic_numbers: Vec<u8>,
    pub normalized_atomic_vector: Vec<f32>,
    pub lattice_hint: Option<String>,
    pub tc_kelvin: Option<f32>,
    pub source_paper_id: String,
    pub source_title: String,
    pub topology: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct SyntheticHardwareBaseline {
    pub unix_s: u64,
    pub material_id: String,
    pub candidate_hash: String,
    pub conductivity_gain: f32,
    pub thermal_stability_gain: f32,
    pub quantum_latency_gain: f32,
    pub provenance: String,
}

impl Default for AfferentTelemetry {
    fn default() -> Self {
        Self {
            unix_s: now_unix_s(),
            loadavg_1m: 0.0,
            cpu_speed_limit_pct: 100.0,
            thermal_pressure: 0.0,
            power_proxy_watts: 0.0,
            available_cores: std::thread::available_parallelism()
                .map(|v| v.get() as u32)
                .unwrap_or(1),
        }
    }
}

fn now_unix_s() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0)
}

fn default_alien_target_objective() -> String {
    "EigenvalueApproximation".to_string()
}

fn run(cmd: &str, args: &[&str]) -> Option<String> {
    let out = Command::new(cmd).args(args).output().ok()?;
    if !out.status.success() {
        return None;
    }
    Some(String::from_utf8_lossy(&out.stdout).trim().to_string())
}

fn parse_first_float(s: &str) -> Option<f32> {
    let mut cur = String::new();
    for ch in s.chars() {
        if ch.is_ascii_digit() || ch == '.' || ch == '-' {
            cur.push(ch);
        } else if !cur.is_empty() {
            break;
        }
    }
    cur.parse::<f32>().ok()
}

fn parse_cpu_speed_limit_pct(s: &str) -> Option<f32> {
    for line in s.lines() {
        if line.to_ascii_lowercase().contains("cpu_speed_limit") {
            if let Some(v) = line.split('=').nth(1).and_then(parse_first_float) {
                return Some(v.clamp(1.0, 100.0));
            }
        }
    }
    None
}

pub fn sample_macos_telemetry() -> AfferentTelemetry {
    let mut t = AfferentTelemetry::default();
    t.available_cores = std::thread::available_parallelism()
        .map(|v| v.get() as u32)
        .unwrap_or(1);
    if let Some(load) = run("sysctl", &["-n", "vm.loadavg"]).and_then(|v| parse_first_float(&v)) {
        t.loadavg_1m = load.max(0.0);
    }
    if let Some(speed) = run("pmset", &["-g", "therm"]).and_then(|v| parse_cpu_speed_limit_pct(&v))
    {
        t.cpu_speed_limit_pct = speed;
    }
    t.thermal_pressure = (100.0 - t.cpu_speed_limit_pct).max(0.0) / 100.0;
    // Lightweight power proxy for closed-loop sensing when direct watts are unavailable.
    t.power_proxy_watts = (t.loadavg_1m / t.available_cores.max(1) as f32).clamp(0.0, 4.0) * 12.0;
    t
}

fn runtime_snapshot_path(root: &Path) -> PathBuf {
    root.join("runtime").join("afferent_snapshot.json")
}

fn runtime_history_path(root: &Path) -> PathBuf {
    root.join("runtime").join("afferent_history.jsonl")
}

fn runtime_external_snapshot_path(root: &Path) -> PathBuf {
    root.join("runtime").join("afferent_external_snapshot.json")
}

fn runtime_external_history_path(root: &Path) -> PathBuf {
    root.join("runtime").join("afferent_external_history.jsonl")
}

fn runtime_synthetic_baseline_path(root: &Path) -> PathBuf {
    root.join("runtime")
        .join("synthetic_hardware_baseline.json")
}

fn inferred_root() -> PathBuf {
    if let Ok(root) = std::env::var("APFSC_ROOT") {
        return PathBuf::from(root);
    }
    if let Ok(home) = std::env::var("HOME") {
        return Path::new(&home).join(".apfsc");
    }
    PathBuf::from(".apfsc")
}

pub fn write_snapshot(root: &Path) -> Result<AfferentTelemetry> {
    let t = sample_macos_telemetry();
    let runtime = root.join("runtime");
    create_dir_all_if_persistent(&runtime)?;
    write_json_atomic(&runtime_snapshot_path(root), &t)?;
    Ok(t)
}

pub fn append_epoch_sample(root: &Path, epoch: u64) -> Result<AfferentEpochSample> {
    let telemetry = write_snapshot(root)?;
    let sample = AfferentEpochSample { epoch, telemetry };
    let runtime = root.join("runtime");
    create_dir_all_if_persistent(&runtime)?;
    append_jsonl_atomic(&runtime_history_path(root), &sample)?;
    Ok(sample)
}

pub fn load_recent_samples(root: &Path, max_items: usize) -> Vec<AfferentEpochSample> {
    let path = runtime_history_path(root);
    let all: Vec<AfferentEpochSample> = read_jsonl(&path).unwrap_or_default();
    let keep = max_items.max(1);
    if all.len() <= keep {
        return all;
    }
    all[all.len() - keep..].to_vec()
}

pub fn load_snapshot(root: &Path) -> Option<AfferentTelemetry> {
    let path = runtime_snapshot_path(root);
    read_json::<AfferentTelemetry>(&path).ok()
}

pub fn load_external_snapshot(root: &Path) -> Option<AfferentExternalSnapshot> {
    let path = runtime_external_snapshot_path(root);
    read_json::<AfferentExternalSnapshot>(&path).ok()
}

pub fn load_external_tensor_seed(root: &Path) -> Option<AfferentTensorSeed> {
    load_external_snapshot(root).and_then(|s| s.tensor_seed)
}

pub fn write_external_snapshot(root: &Path, snapshot: &AfferentExternalSnapshot) -> Result<()> {
    let runtime = root.join("runtime");
    create_dir_all_if_persistent(&runtime)?;
    write_json_atomic(&runtime_external_snapshot_path(root), snapshot)?;
    append_jsonl_atomic(&runtime_external_history_path(root), snapshot)?;
    Ok(())
}

pub fn write_synthetic_hardware_baseline(
    root: &Path,
    baseline: &SyntheticHardwareBaseline,
) -> Result<()> {
    let runtime = root.join("runtime");
    create_dir_all_if_persistent(&runtime)?;
    write_json_atomic(&runtime_synthetic_baseline_path(root), baseline)?;
    append_jsonl_atomic(
        &runtime.join("synthetic_hardware_baseline_history.jsonl"),
        baseline,
    )?;
    Ok(())
}

pub fn load_synthetic_hardware_baseline(root: &Path) -> Option<SyntheticHardwareBaseline> {
    read_json::<SyntheticHardwareBaseline>(&runtime_synthetic_baseline_path(root)).ok()
}

pub fn channel_seed_vector_from_root(root: &Path, channel: u8, out_dim: usize) -> Option<Vec<f32>> {
    if channel != 3 || out_dim == 0 {
        return None;
    }
    let seed = load_external_tensor_seed(root)?;
    if seed.normalized_atomic_vector.is_empty() {
        return None;
    }
    let src = seed.normalized_atomic_vector;
    let mut out = Vec::with_capacity(out_dim);
    for i in 0..out_dim {
        out.push(src[i % src.len()].clamp(0.0, 1.0));
    }
    Some(out)
}

pub fn channel_seed_vector(channel: u8, out_dim: usize) -> Option<Vec<f32>> {
    let root = inferred_root();
    channel_seed_vector_from_root(&root, channel, out_dim)
}

fn fetch_arxiv_atom(max_results: usize) -> Result<String> {
    let capped = max_results.clamp(1, 200);
    let url = format!(
        "{ARXIV_ENDPOINT}?search_query={ARXIV_QUERY}&start=0&max_results={capped}&sortBy=submittedDate&sortOrder=descending"
    );
    let out = Command::new("curl")
        .args([
            "-fsSL",
            "--max-time",
            "20",
            "--retry",
            "2",
            "--retry-delay",
            "1",
            "-A",
            "apfsc-ingest-external/1.0",
        ])
        .arg(&url)
        .output()
        .map_err(|e| ApfscError::Protocol(format!("curl launch failed: {e}")))?;
    if !out.status.success() {
        return Err(ApfscError::Protocol(format!(
            "curl request failed for arXiv API with status {}",
            out.status
        )));
    }
    let body = String::from_utf8_lossy(&out.stdout).to_string();
    if body.trim().is_empty() {
        return Err(ApfscError::Protocol(
            "arXiv API returned an empty body".to_string(),
        ));
    }
    Ok(body)
}

fn normalize_ws(s: &str) -> String {
    s.split_whitespace().collect::<Vec<_>>().join(" ")
}

fn xml_unescape(s: &str) -> String {
    s.replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&amp;", "&")
        .replace("&quot;", "\"")
        .replace("&apos;", "'")
}

fn extract_xml_tag(block: &str, tag: &str) -> Option<String> {
    let open = format!("<{tag}>");
    let close = format!("</{tag}>");
    let start = block.find(&open)? + open.len();
    let end = block[start..].find(&close)? + start;
    Some(xml_unescape(block[start..end].trim()))
}

fn parse_arxiv_feed(xml: &str) -> Vec<ArxivPaper> {
    let mut out = Vec::<ArxivPaper>::new();
    for section in xml.split("<entry>").skip(1) {
        let Some(end) = section.find("</entry>") else {
            continue;
        };
        let entry = &section[..end];
        let Some(id) = extract_xml_tag(entry, "id") else {
            continue;
        };
        let title = extract_xml_tag(entry, "title").unwrap_or_default();
        let summary = extract_xml_tag(entry, "summary").unwrap_or_default();
        let published = extract_xml_tag(entry, "published").unwrap_or_default();
        out.push(ArxivPaper {
            id: normalize_ws(&id),
            title: normalize_ws(&title),
            summary: normalize_ws(&summary),
            published: normalize_ws(&published),
        });
    }
    out
}

#[derive(Debug, Clone)]
struct SemanticExtraction {
    formulas: Vec<String>,
    tc_kelvin: Vec<f32>,
    lattice_hints: Vec<String>,
    tensor_seed: Option<AfferentTensorSeed>,
}

fn normalize_formula_token(raw: &str) -> String {
    let mut out = String::new();
    for ch in raw.chars() {
        match ch {
            '$' | '{' | '}' | '(' | ')' | '[' | ']' | ',' | ';' | ':' | '"' | '\'' | '`' | '\\'
            | '_' => {}
            c if c.is_ascii_alphanumeric() => out.push(c),
            _ => {}
        }
    }
    out
}

fn looks_like_chemical_formula(token: &str) -> bool {
    if token.len() < 3 || token.len() > 32 {
        return false;
    }
    if !token
        .chars()
        .next()
        .map(|c| c.is_ascii_uppercase())
        .unwrap_or(false)
    {
        return false;
    }
    if !token.chars().all(|c| c.is_ascii_alphanumeric()) {
        return false;
    }
    let has_upper = token.chars().any(|c| c.is_ascii_uppercase());
    let has_digit = token.chars().any(|c| c.is_ascii_digit());
    has_upper && has_digit
}

fn extract_formula_candidates_from_text(text: &str) -> Vec<String> {
    let mut out = Vec::<String>::new();
    let mut seen = BTreeSet::<String>::new();
    for raw in text.split_whitespace() {
        let token = normalize_formula_token(raw);
        if token.is_empty() {
            continue;
        }
        let token_lower = token.to_ascii_lowercase();
        if token_lower.starts_with("http") || token_lower.contains("arxiv") {
            continue;
        }
        if !looks_like_chemical_formula(&token) {
            continue;
        }
        if seen.insert(token.clone()) {
            out.push(token);
        }
        if out.len() >= MAX_SEMANTIC_FORMULAS {
            break;
        }
    }
    out
}

fn atomic_number_for_symbol(symbol: &str) -> Option<u8> {
    match symbol {
        "H" => Some(1),
        "He" => Some(2),
        "Li" => Some(3),
        "Be" => Some(4),
        "B" => Some(5),
        "C" => Some(6),
        "N" => Some(7),
        "O" => Some(8),
        "F" => Some(9),
        "Ne" => Some(10),
        "Na" => Some(11),
        "Mg" => Some(12),
        "Al" => Some(13),
        "Si" => Some(14),
        "P" => Some(15),
        "S" => Some(16),
        "Cl" => Some(17),
        "Ar" => Some(18),
        "K" => Some(19),
        "Ca" => Some(20),
        "Sc" => Some(21),
        "Ti" => Some(22),
        "V" => Some(23),
        "Cr" => Some(24),
        "Mn" => Some(25),
        "Fe" => Some(26),
        "Co" => Some(27),
        "Ni" => Some(28),
        "Cu" => Some(29),
        "Zn" => Some(30),
        "Ga" => Some(31),
        "Ge" => Some(32),
        "As" => Some(33),
        "Se" => Some(34),
        "Br" => Some(35),
        "Kr" => Some(36),
        "Rb" => Some(37),
        "Sr" => Some(38),
        "Y" => Some(39),
        "Zr" => Some(40),
        "Nb" => Some(41),
        "Mo" => Some(42),
        "Tc" => Some(43),
        "Ru" => Some(44),
        "Rh" => Some(45),
        "Pd" => Some(46),
        "Ag" => Some(47),
        "Cd" => Some(48),
        "In" => Some(49),
        "Sn" => Some(50),
        "Sb" => Some(51),
        "Te" => Some(52),
        "I" => Some(53),
        "Xe" => Some(54),
        "Cs" => Some(55),
        "Ba" => Some(56),
        "La" => Some(57),
        "Ce" => Some(58),
        "Pr" => Some(59),
        "Nd" => Some(60),
        "Pm" => Some(61),
        "Sm" => Some(62),
        "Eu" => Some(63),
        "Gd" => Some(64),
        "Tb" => Some(65),
        "Dy" => Some(66),
        "Ho" => Some(67),
        "Er" => Some(68),
        "Tm" => Some(69),
        "Yb" => Some(70),
        "Lu" => Some(71),
        "Hf" => Some(72),
        "Ta" => Some(73),
        "W" => Some(74),
        "Re" => Some(75),
        "Os" => Some(76),
        "Ir" => Some(77),
        "Pt" => Some(78),
        "Au" => Some(79),
        "Hg" => Some(80),
        "Tl" => Some(81),
        "Pb" => Some(82),
        "Bi" => Some(83),
        "Po" => Some(84),
        "At" => Some(85),
        "Rn" => Some(86),
        "Fr" => Some(87),
        "Ra" => Some(88),
        "Ac" => Some(89),
        "Th" => Some(90),
        "Pa" => Some(91),
        "U" => Some(92),
        "Np" => Some(93),
        "Pu" => Some(94),
        "Am" => Some(95),
        "Cm" => Some(96),
        "Bk" => Some(97),
        "Cf" => Some(98),
        "Es" => Some(99),
        "Fm" => Some(100),
        "Md" => Some(101),
        "No" => Some(102),
        "Lr" => Some(103),
        "Rf" => Some(104),
        "Db" => Some(105),
        "Sg" => Some(106),
        "Bh" => Some(107),
        "Hs" => Some(108),
        "Mt" => Some(109),
        "Ds" => Some(110),
        "Rg" => Some(111),
        "Cn" => Some(112),
        "Nh" => Some(113),
        "Fl" => Some(114),
        "Mc" => Some(115),
        "Lv" => Some(116),
        "Ts" => Some(117),
        "Og" => Some(118),
        _ => None,
    }
}

fn parse_formula_to_atomic_numbers(formula: &str) -> Option<Vec<u8>> {
    let chars = formula.chars().collect::<Vec<_>>();
    let mut i = 0usize;
    let mut out = Vec::<u8>::new();
    while i < chars.len() {
        let c = chars[i];
        if !c.is_ascii_uppercase() {
            return None;
        }
        let mut symbol = String::new();
        symbol.push(c);
        i += 1;
        if i < chars.len() && chars[i].is_ascii_lowercase() {
            symbol.push(chars[i]);
            i += 1;
        }
        let mut count = 0usize;
        while i < chars.len() && chars[i].is_ascii_digit() {
            count = count
                .saturating_mul(10)
                .saturating_add((chars[i] as u8 - b'0') as usize);
            i += 1;
        }
        let repeat = if count == 0 { 1 } else { count.clamp(1, 24) };
        let z = atomic_number_for_symbol(&symbol)?;
        for _ in 0..repeat {
            out.push(z);
            if out.len() >= MAX_TENSOR_SEED_ATOMS {
                break;
            }
        }
        if out.len() >= MAX_TENSOR_SEED_ATOMS {
            break;
        }
    }
    if out.is_empty() {
        None
    } else {
        Some(out)
    }
}

fn parse_numeric_prefix(s: &str) -> Option<f32> {
    let mut num = String::new();
    for ch in s.chars() {
        if ch.is_ascii_digit() || ch == '.' || ch == '-' {
            num.push(ch);
        } else {
            break;
        }
    }
    if num.is_empty() {
        None
    } else {
        num.parse::<f32>().ok()
    }
}

fn extract_tc_kelvin_candidates(text: &str) -> Vec<f32> {
    let mut out = Vec::<f32>::new();
    let mut seen = BTreeSet::<i32>::new();
    let normalized = text
        .chars()
        .map(|c| {
            if c.is_ascii_alphanumeric() || c == '.' || c == '_' || c == '-' {
                c.to_ascii_lowercase()
            } else {
                ' '
            }
        })
        .collect::<String>();
    let tokens = normalized.split_whitespace().collect::<Vec<_>>();
    for i in 0..tokens.len() {
        let tc_token = tokens[i];
        let is_tc_anchor = tc_token == "tc" || tc_token == "t_c";
        if !is_tc_anchor {
            continue;
        }
        for j in (i + 1)..tokens.len().min(i + 8) {
            let v = match parse_numeric_prefix(tokens[j]) {
                Some(v) if v.is_finite() => v,
                _ => continue,
            };
            if !(0.0..=800.0).contains(&v) {
                continue;
            }
            let unit_window = &tokens[j..tokens.len().min(j + 3)];
            let has_kelvin_unit = unit_window
                .iter()
                .any(|u| *u == "k" || u.starts_with('k') || *u == "kelvin");
            if !has_kelvin_unit {
                continue;
            }
            let key = (v * 100.0).round() as i32;
            if seen.insert(key) {
                out.push(v);
            }
            if out.len() >= MAX_SEMANTIC_TEMPERATURES {
                return out;
            }
        }
    }
    out
}

fn extract_lattice_hints(corpus_lower: &str) -> Vec<String> {
    let mut out = Vec::<String>::new();
    let mut seen = BTreeSet::<String>::new();
    let pairs = [
        ("a15", "A15"),
        ("perovskite", "Perovskite"),
        ("tetragonal", "Tetragonal"),
        ("orthorhombic", "Orthorhombic"),
        ("hexagonal", "Hexagonal"),
        ("trigonal", "Trigonal"),
        ("cubic", "Cubic"),
        ("monoclinic", "Monoclinic"),
        ("honeycomb", "Honeycomb"),
        ("spinel", "Spinel"),
        ("rocksalt", "Rocksalt"),
    ];
    for (needle, canonical) in pairs {
        if corpus_lower.contains(needle) && seen.insert(canonical.to_string()) {
            out.push(canonical.to_string());
        }
    }
    out
}

fn select_tensor_seed(
    papers: &[ArxivPaper],
    all_lattice_hints: &[String],
    tc_kelvin: &[f32],
) -> Option<AfferentTensorSeed> {
    let mut best: Option<(i32, AfferentTensorSeed)> = None;
    for paper in papers {
        let text = format!("{} {}", paper.title, paper.summary);
        let text_lower = text.to_ascii_lowercase();
        let paper_lattice = extract_lattice_hints(&text_lower);
        let paper_tc = extract_tc_kelvin_candidates(&text);
        for formula in extract_formula_candidates_from_text(&text) {
            let atomic_numbers = match parse_formula_to_atomic_numbers(&formula) {
                Some(v) => v,
                None => continue,
            };
            let mut score = atomic_numbers.len() as i32;
            if text_lower.contains("superconduct") {
                score += 10;
            }
            if text_lower.contains("lattice") {
                score += 4;
            }
            if !paper_lattice.is_empty() {
                score += 3;
            }
            if !paper_tc.is_empty() {
                score += 3;
            }
            if formula.contains('H') {
                score += 1;
            }
            let lattice_hint = paper_lattice
                .first()
                .cloned()
                .or_else(|| all_lattice_hints.first().cloned());
            let tc_hint = paper_tc
                .first()
                .copied()
                .or_else(|| tc_kelvin.first().copied());
            let normalized_atomic_vector = atomic_numbers
                .iter()
                .map(|z| (*z as f32 / 118.0).clamp(0.0, 1.0))
                .collect::<Vec<_>>();
            let seed = AfferentTensorSeed {
                formula: formula.clone(),
                atomic_numbers,
                normalized_atomic_vector,
                lattice_hint,
                tc_kelvin: tc_hint,
                source_paper_id: paper.id.clone(),
                source_title: paper.title.clone(),
                topology: "MERA::BoundarySeed".to_string(),
            };
            match &best {
                Some((best_score, _)) if score <= *best_score => {}
                _ => best = Some((score, seed)),
            }
        }
    }
    best.map(|(_, seed)| seed)
}

fn extract_semantic_features(papers: &[ArxivPaper]) -> SemanticExtraction {
    let mut formula_examples = Vec::<String>::new();
    let mut formula_seen = BTreeSet::<String>::new();
    let mut tc_kelvin = Vec::<f32>::new();
    let mut tc_seen = BTreeSet::<i32>::new();
    let mut lattice_hints = Vec::<String>::new();
    let mut lattice_seen = BTreeSet::<String>::new();

    for paper in papers {
        let text = format!("{} {}", paper.title, paper.summary);
        for f in extract_formula_candidates_from_text(&text) {
            if parse_formula_to_atomic_numbers(&f).is_none() {
                continue;
            }
            if formula_seen.insert(f.clone()) {
                formula_examples.push(f);
            }
            if formula_examples.len() >= MAX_SEMANTIC_FORMULAS {
                break;
            }
        }
        for tc in extract_tc_kelvin_candidates(&text) {
            let key = (tc * 100.0).round() as i32;
            if tc_seen.insert(key) {
                tc_kelvin.push(tc);
            }
            if tc_kelvin.len() >= MAX_SEMANTIC_TEMPERATURES {
                break;
            }
        }
        let lower = text.to_ascii_lowercase();
        for hint in extract_lattice_hints(&lower) {
            if lattice_seen.insert(hint.clone()) {
                lattice_hints.push(hint);
            }
        }
    }

    let tensor_seed = select_tensor_seed(papers, &lattice_hints, &tc_kelvin);
    SemanticExtraction {
        formulas: formula_examples,
        tc_kelvin,
        lattice_hints,
        tensor_seed,
    }
}

pub fn scrape_arxiv_papers(max_results: usize) -> Result<Vec<ArxivPaper>> {
    let xml = fetch_arxiv_atom(max_results)?;
    let papers = parse_arxiv_feed(&xml);
    if papers.is_empty() {
        return Err(ApfscError::Protocol(
            "arXiv scrape produced no entries".to_string(),
        ));
    }
    Ok(papers)
}

pub fn render_arxiv_formula_payload(papers: &[ArxivPaper]) -> Vec<u8> {
    let semantic = extract_semantic_features(papers);
    let mut text = String::new();
    text.push_str("### ARXIV_SEMANTIC_EXTRACT\n");
    text.push_str(&format!(
        "alien_target_objective: {}\n",
        default_alien_target_objective()
    ));
    text.push_str(&format!("formula_count: {}\n", semantic.formulas.len()));
    if !semantic.formulas.is_empty() {
        text.push_str("formula_examples: ");
        text.push_str(&semantic.formulas.join(","));
        text.push('\n');
    }
    if !semantic.tc_kelvin.is_empty() {
        let temps = semantic
            .tc_kelvin
            .iter()
            .map(|v| format!("{v:.3}"))
            .collect::<Vec<_>>()
            .join(",");
        text.push_str(&format!("tc_kelvin: {temps}\n"));
    }
    if !semantic.lattice_hints.is_empty() {
        text.push_str(&format!(
            "lattice_hints: {}\n",
            semantic.lattice_hints.join(",")
        ));
    }
    if let Some(seed) = semantic.tensor_seed {
        text.push_str(&format!("tensor_seed_formula: {}\n", seed.formula));
        text.push_str("tensor_seed_atomic_numbers: ");
        text.push_str(
            &seed
                .atomic_numbers
                .iter()
                .map(|z| z.to_string())
                .collect::<Vec<_>>()
                .join(","),
        );
        text.push('\n');
        if let Some(lattice) = seed.lattice_hint {
            text.push_str(&format!("tensor_seed_lattice: {lattice}\n"));
        }
        if let Some(tc) = seed.tc_kelvin {
            text.push_str(&format!("tensor_seed_tc_kelvin: {tc:.3}\n"));
        }
    }
    text.push('\n');
    for paper in papers {
        text.push_str("### ARXIV_PAPER\n");
        text.push_str(&format!("id: {}\n", paper.id));
        text.push_str(&format!("published: {}\n", paper.published));
        text.push_str(&format!("title: {}\n", paper.title));
        text.push_str(&format!("summary: {}\n", paper.summary));
        text.push('\n');
    }
    text.into_bytes()
}

fn keyword_hits(haystack_lower: &str, keywords: &[&str]) -> usize {
    keywords
        .iter()
        .map(|kw| haystack_lower.matches(kw).count())
        .sum()
}

pub fn build_external_snapshot_from_papers(
    papers: &[ArxivPaper],
    max_results: usize,
    payload: &[u8],
) -> AfferentExternalSnapshot {
    let semantic = extract_semantic_features(papers);
    let corpus = papers
        .iter()
        .map(|p| format!("{} {}", p.title, p.summary))
        .collect::<Vec<_>>()
        .join("\n");
    let corpus_lower = corpus.to_ascii_lowercase();
    let corpus_chars = corpus.len().max(1) as f32;

    let formula_chars = corpus
        .chars()
        .filter(|c| {
            matches!(
                c,
                '=' | '+' | '-' | '*' | '/' | '^' | '_' | '{' | '}' | '\\' | '(' | ')' | '[' | ']'
            )
        })
        .count() as f32;
    let formula_density = (formula_chars / corpus_chars).clamp(0.0, 1.0);

    let eigen_hits = keyword_hits(
        &corpus_lower,
        &[
            "eigen",
            "ground state",
            "hamiltonian",
            "superconduct",
            "wavefunction",
            "schrodinger",
        ],
    ) as f32;
    let boundary_hits = keyword_hits(
        &corpus_lower,
        &[
            "holograph",
            "ads/cft",
            "boundary",
            "tensor network",
            "mera",
            "renormalization",
        ],
    ) as f32;
    let token_count = corpus_lower.split_whitespace().count().max(1) as f32;
    let unique_tokens = corpus_lower
        .split_whitespace()
        .collect::<std::collections::BTreeSet<_>>()
        .len() as f32;
    let lexical_novelty = (unique_tokens / token_count).clamp(0.0, 1.0);
    let coverage = (papers.len() as f32 / max_results.max(1) as f32).clamp(0.0, 1.0);
    let novelty_signal = (0.6 * lexical_novelty + 0.4 * coverage).clamp(0.0, 1.0);

    let eigen_signal = (eigen_hits / 12.0
        + if !semantic.tc_kelvin.is_empty() {
            0.08
        } else {
            0.0
        })
    .clamp(0.0, 1.0);
    let boundary_signal = (boundary_hits / 10.0
        + if semantic.tensor_seed.is_some() {
            0.2
        } else {
            0.0
        })
    .clamp(0.0, 1.0);
    let composite_signal = (0.45 * formula_density
        + 0.30 * eigen_signal
        + 0.15 * boundary_signal
        + 0.10 * novelty_signal)
        .clamp(0.0, 1.0);

    let semantic_formula_examples = semantic.formulas.into_iter().take(12).collect::<Vec<_>>();
    let semantic_tc_kelvin = semantic
        .tc_kelvin
        .into_iter()
        .take(MAX_SEMANTIC_TEMPERATURES)
        .collect::<Vec<_>>();
    let semantic_lattice_hints = semantic
        .lattice_hints
        .into_iter()
        .take(8)
        .collect::<Vec<_>>();
    let semantic_formula_count = semantic_formula_examples.len() as u32;
    let tensor_seed = semantic.tensor_seed;

    AfferentExternalSnapshot {
        unix_s: now_unix_s(),
        source: "arxiv_api".to_string(),
        query: ARXIV_QUERY.to_string(),
        max_results: max_results.max(1) as u32,
        entry_count: papers.len() as u32,
        payload_hash: digest_bytes(payload),
        formula_density,
        eigen_signal,
        boundary_signal,
        novelty_signal,
        composite_signal,
        semantic_formula_count,
        semantic_formula_examples,
        semantic_tc_kelvin,
        semantic_lattice_hints,
        alien_target_objective: default_alien_target_objective(),
        tensor_seed,
    }
}

pub fn scrape_arxiv_formula_payload(
    max_results: usize,
) -> Result<(Vec<u8>, AfferentExternalSnapshot)> {
    let papers = scrape_arxiv_papers(max_results)?;
    let payload = render_arxiv_formula_payload(&papers);
    let snapshot = build_external_snapshot_from_papers(&papers, max_results, &payload);
    Ok((payload, snapshot))
}

pub fn refresh_arxiv_external_snapshot(
    root: &Path,
    max_results: usize,
) -> Result<AfferentExternalSnapshot> {
    let (_payload, snapshot) = scrape_arxiv_formula_payload(max_results)?;
    write_external_snapshot(root, &snapshot)?;
    Ok(snapshot)
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
pub struct ArxivRefreshProfile {
    pub calls: u64,
    pub network_attempts: u64,
    pub refreshed: u64,
    pub failures: u64,
    pub total_ms: u64,
    pub last_ms: u64,
}

static ARXIV_REFRESH_CALLS: AtomicU64 = AtomicU64::new(0);
static ARXIV_REFRESH_NETWORK_ATTEMPTS: AtomicU64 = AtomicU64::new(0);
static ARXIV_REFRESH_SUCCESSES: AtomicU64 = AtomicU64::new(0);
static ARXIV_REFRESH_FAILURES: AtomicU64 = AtomicU64::new(0);
static ARXIV_REFRESH_TOTAL_MS: AtomicU64 = AtomicU64::new(0);
static ARXIV_REFRESH_LAST_MS: AtomicU64 = AtomicU64::new(0);

fn record_arxiv_refresh_timing(elapsed_ms: u64, attempted_network: bool, refreshed: bool, failed: bool) {
    ARXIV_REFRESH_CALLS.fetch_add(1, Ordering::Relaxed);
    if attempted_network {
        ARXIV_REFRESH_NETWORK_ATTEMPTS.fetch_add(1, Ordering::Relaxed);
    }
    if refreshed {
        ARXIV_REFRESH_SUCCESSES.fetch_add(1, Ordering::Relaxed);
    }
    if failed {
        ARXIV_REFRESH_FAILURES.fetch_add(1, Ordering::Relaxed);
    }
    ARXIV_REFRESH_TOTAL_MS.fetch_add(elapsed_ms, Ordering::Relaxed);
    ARXIV_REFRESH_LAST_MS.store(elapsed_ms, Ordering::Relaxed);
}

pub fn arxiv_refresh_profile() -> ArxivRefreshProfile {
    ArxivRefreshProfile {
        calls: ARXIV_REFRESH_CALLS.load(Ordering::Relaxed),
        network_attempts: ARXIV_REFRESH_NETWORK_ATTEMPTS.load(Ordering::Relaxed),
        refreshed: ARXIV_REFRESH_SUCCESSES.load(Ordering::Relaxed),
        failures: ARXIV_REFRESH_FAILURES.load(Ordering::Relaxed),
        total_ms: ARXIV_REFRESH_TOTAL_MS.load(Ordering::Relaxed),
        last_ms: ARXIV_REFRESH_LAST_MS.load(Ordering::Relaxed),
    }
}

pub fn refresh_arxiv_external_snapshot_if_stale(
    root: &Path,
    max_age_s: u64,
    max_results: usize,
) -> Result<Option<AfferentExternalSnapshot>> {
    let t0 = Instant::now();
    if let Some(existing) = load_external_snapshot(root) {
        let age = now_unix_s().saturating_sub(existing.unix_s);
        if age <= max_age_s {
            record_arxiv_refresh_timing(
                t0.elapsed().as_millis().min(u128::from(u64::MAX)) as u64,
                false,
                false,
                false,
            );
            return Ok(None);
        }
    }
    match refresh_arxiv_external_snapshot(root, max_results) {
        Ok(refreshed) => {
            record_arxiv_refresh_timing(
                t0.elapsed().as_millis().min(u128::from(u64::MAX)) as u64,
                true,
                true,
                false,
            );
            Ok(Some(refreshed))
        }
        Err(e) => {
            record_arxiv_refresh_timing(
                t0.elapsed().as_millis().min(u128::from(u64::MAX)) as u64,
                true,
                false,
                true,
            );
            Err(e)
        }
    }
}

static CACHE: OnceLock<Mutex<(u64, AfferentTelemetry)>> = OnceLock::new();
static EXTERNAL_CACHE: OnceLock<Mutex<(u64, f32)>> = OnceLock::new();
static EXTERNAL_REFRESH_ATTEMPT: OnceLock<Mutex<u64>> = OnceLock::new();
static SYNTHETIC_CACHE: OnceLock<Mutex<(u64, Option<SyntheticHardwareBaseline>)>> = OnceLock::new();

pub fn sample_cached() -> AfferentTelemetry {
    let now = now_unix_s();
    let lock = CACHE.get_or_init(|| Mutex::new((0, AfferentTelemetry::default())));
    let mut guard = lock.lock().unwrap_or_else(|e| e.into_inner());
    if now.saturating_sub(guard.0) <= 1 {
        return guard.1.clone();
    }
    let root = inferred_root();
    let fresh = load_snapshot(&root).unwrap_or_else(sample_macos_telemetry);
    *guard = (now, fresh.clone());
    fresh
}

fn channel3_exogenous_value(now_unix: u64, root: &Path) -> f32 {
    let lock = EXTERNAL_CACHE.get_or_init(|| Mutex::new((0, 0.0)));
    let mut guard = lock.lock().unwrap_or_else(|e| e.into_inner());
    if now_unix.saturating_sub(guard.0) <= 5 {
        return guard.1;
    }

    let mut snapshot = load_external_snapshot(root);
    let snapshot_is_stale = snapshot
        .as_ref()
        .map(|s| now_unix.saturating_sub(s.unix_s) > ARXIV_STALE_S)
        .unwrap_or(true);

    if snapshot_is_stale {
        let attempt_lock = EXTERNAL_REFRESH_ATTEMPT.get_or_init(|| Mutex::new(0));
        let mut last_attempt = attempt_lock.lock().unwrap_or_else(|e| e.into_inner());
        if now_unix.saturating_sub(*last_attempt) >= ARXIV_RETRY_COOLDOWN_S {
            *last_attempt = now_unix;
            if let Ok(fresh) = refresh_arxiv_external_snapshot(root, ARXIV_DEFAULT_MAX_RESULTS) {
                snapshot = Some(fresh);
            }
        }
    }

    let fallback = (now_unix % 1024) as f32 / 1024.0;
    let value = snapshot
        .map(|s| s.composite_signal.clamp(0.0, 1.0))
        .unwrap_or(fallback);
    *guard = (now_unix, value);
    value
}

fn synthetic_hardware_cached(now_unix: u64, root: &Path) -> Option<SyntheticHardwareBaseline> {
    let lock = SYNTHETIC_CACHE.get_or_init(|| Mutex::new((0, None)));
    let mut guard = lock.lock().unwrap_or_else(|e| e.into_inner());
    if now_unix.saturating_sub(guard.0) <= 5 {
        return guard.1.clone();
    }
    let baseline = load_synthetic_hardware_baseline(root);
    *guard = (now_unix, baseline.clone());
    baseline
}

pub fn channel_value(channel: u8) -> f32 {
    let t = sample_cached();
    let root = inferred_root();
    let synthetic = synthetic_hardware_cached(t.unix_s, &root);
    let conductivity_gain = synthetic
        .as_ref()
        .map(|b| b.conductivity_gain.clamp(0.0, 4.0))
        .unwrap_or(0.0);
    let thermal_gain = synthetic
        .as_ref()
        .map(|b| b.thermal_stability_gain.clamp(0.0, 4.0))
        .unwrap_or(0.0);
    let quantum_gain = synthetic
        .as_ref()
        .map(|b| b.quantum_latency_gain.clamp(0.0, 4.0))
        .unwrap_or(0.0);
    let load_norm =
        (t.loadavg_1m / t.available_cores.max(1) as f32 / (1.0 + 0.5 * conductivity_gain))
            .clamp(0.0, 1.0);
    let thermal_norm = (t.thermal_pressure * (1.0 - 0.65 * (thermal_gain / 4.0))).clamp(0.0, 1.0);
    let power_norm = ((t.power_proxy_watts / 12.0) / (1.0 + 0.5 * quantum_gain)).clamp(0.0, 1.0);
    let exogenous_norm =
        (channel3_exogenous_value(t.unix_s, &root) + 0.15 * (quantum_gain / 4.0)).clamp(0.0, 1.0);
    match channel {
        0 => load_norm,
        1 => thermal_norm,
        2 => power_norm,
        3 => exogenous_norm,
        _ => 0.0,
    }
}

#[cfg(test)]
mod tests {
    use super::{
        build_external_snapshot_from_papers, extract_formula_candidates_from_text,
        extract_semantic_features, parse_arxiv_feed, parse_formula_to_atomic_numbers,
        render_arxiv_formula_payload,
    };

    #[test]
    fn parse_arxiv_feed_extracts_entries() {
        let xml = r#"
        <feed>
          <entry>
            <id>http://arxiv.org/abs/1234.5678v1</id>
            <published>2026-03-01T00:00:00Z</published>
            <title>Holographic Tensor Network</title>
            <summary>We solve H = Psi using MERA.</summary>
          </entry>
        </feed>
        "#;
        let papers = parse_arxiv_feed(xml);
        assert_eq!(papers.len(), 1);
        assert!(papers[0].title.contains("Holographic"));
        assert!(papers[0].summary.contains("MERA"));
    }

    #[test]
    fn external_snapshot_signals_are_finite() {
        let papers = vec![super::ArxivPaper {
            id: "id1".to_string(),
            title: "Ground state eigenvector in superconducting lattice".to_string(),
            summary: "Hamiltonian H=Psi with tensor network MERA boundary map".to_string(),
            published: "2026-03-01T00:00:00Z".to_string(),
        }];
        let payload = render_arxiv_formula_payload(&papers);
        let snapshot = build_external_snapshot_from_papers(&papers, 8, &payload);
        assert!(snapshot.formula_density.is_finite());
        assert!(snapshot.eigen_signal.is_finite());
        assert!(snapshot.boundary_signal.is_finite());
        assert!(snapshot.composite_signal.is_finite());
        assert!(snapshot.composite_signal > 0.0);
    }

    #[test]
    fn formula_extraction_yields_atomic_numbers() {
        let text = "CeRh$_2$As$_2$ and Mg2IrH7 remain stable.";
        let formulas = extract_formula_candidates_from_text(text);
        assert!(formulas.iter().any(|f| f == "CeRh2As2"));
        assert!(formulas.iter().any(|f| f == "Mg2IrH7"));
        let cerh = parse_formula_to_atomic_numbers("CeRh2As2").expect("CeRh2As2 parse");
        let mgirh = parse_formula_to_atomic_numbers("Mg2IrH7").expect("Mg2IrH7 parse");
        assert_eq!(cerh, vec![58, 45, 45, 33, 33]);
        assert_eq!(mgirh, vec![12, 12, 77, 1, 1, 1, 1, 1, 1, 1]);
    }

    #[test]
    fn snapshot_contains_tensor_seed_semantics() {
        let papers = vec![super::ArxivPaper {
            id: "id_sem".to_string(),
            title: "High-pressure stabilization of Mg2IrH7".to_string(),
            summary: "Tc = 39 K in a tetragonal superconducting lattice with Hamiltonian closure."
                .to_string(),
            published: "2026-03-01T00:00:00Z".to_string(),
        }];
        let payload = render_arxiv_formula_payload(&papers);
        let snapshot = build_external_snapshot_from_papers(&papers, 8, &payload);
        assert!(snapshot.semantic_formula_count >= 1);
        assert!(snapshot
            .semantic_formula_examples
            .iter()
            .any(|f| f == "Mg2IrH7"));
        assert!(!snapshot.semantic_tc_kelvin.is_empty());
        assert!(snapshot
            .semantic_lattice_hints
            .iter()
            .any(|h| h == "Tetragonal"));
        let seed = snapshot.tensor_seed.expect("tensor seed present");
        assert_eq!(seed.formula, "Mg2IrH7");
        assert_eq!(seed.atomic_numbers[0], 12);
        assert_eq!(seed.topology, "MERA::BoundarySeed");
    }

    #[test]
    fn semantic_formula_examples_require_parseable_chemistry() {
        let papers = vec![super::ArxivPaper {
            id: "id_filter".to_string(),
            title: "D4h symmetry and X2C-corr model for CeRh$_2$As$_2$".to_string(),
            summary: "Formalism discusses A15-type tensor terms but material is CeRh2As2."
                .to_string(),
            published: "2026-03-01T00:00:00Z".to_string(),
        }];
        let semantic = extract_semantic_features(&papers);
        assert!(semantic.formulas.iter().any(|f| f == "CeRh2As2"));
        assert!(!semantic.formulas.iter().any(|f| f == "D4h"));
        assert!(!semantic.formulas.iter().any(|f| f == "X2Ccorr"));
    }
}
