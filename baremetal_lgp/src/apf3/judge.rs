use std::fs;
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

use crate::apf3::aal_exec::{AALExecutor, ExecStop};
use crate::apf3::aal_ir::AALGraph;
use crate::apf3::digest::{Digest32, DigestBuilder, TAG_APF3_RUN_V1};
use crate::apf3::metachunkpack::{Chunk, MetaChunkPack};
use crate::apf3::write_atomic;
use crate::apf3::{mix_seed, splitmix64};

#[derive(Clone, Debug)]
pub struct JudgeConfig {
    pub seed: u64,
    pub run_dir: PathBuf,
    pub heldout_salt_file: PathBuf,
    pub heldout_pack_dir: PathBuf,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct JudgeDecisionReceipt {
    pub candidate_hash: Digest32,
    pub decision: String,
    pub delta_vs_baseline: f32,
    pub heldout_mean: f32,
    pub baseline_mean: f32,
    pub anchor_mean: f32,
    pub baseline_anchor_mean: f32,
    pub evidence_digests: Vec<Digest32>,
    pub config_seed: u64,
    pub timestamp_unix: u64,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ActiveCandidatePointer {
    pub candidate_hash: Digest32,
    pub graph_path: String,
    pub diff_path: Option<String>,
    pub decision_receipt_path: String,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
struct PackEvalCache {
    candidate_hash: Digest32,
    pack_digest: Digest32,
    query_score_mean: f32,
    stop: String,
    failure_label: Option<String>,
}

pub fn run_judge(cfg: &JudgeConfig) -> Result<(), String> {
    let apf3_dir = cfg.run_dir.join("apf3");
    let registry_candidates = apf3_dir.join("registry/candidates");
    let registry_diffs = apf3_dir.join("registry/diffs");
    let receipts_dir = apf3_dir.join("receipts/judge");
    let cache_root = apf3_dir.join("cache");
    let anchor_pack_dir = apf3_dir.join("packs/anchors");

    fs::create_dir_all(&receipts_dir).map_err(|e| e.to_string())?;
    fs::create_dir_all(&cache_root).map_err(|e| e.to_string())?;

    let heldout_salt = load_or_create_heldout_salt(&cfg.heldout_salt_file, cfg.seed)?;
    let heldout_packs = load_or_create_heldout_packs(&cfg.heldout_pack_dir, heldout_salt)?;
    let anchor_salt = mix_seed(heldout_salt, 0x414E_4348_4F52, 0);
    let anchor_packs = load_or_create_anchor_packs(&anchor_pack_dir, anchor_salt)?;

    let candidates = load_candidate_graphs(&registry_candidates)?;
    if candidates.is_empty() {
        let run_digest = build_run_digest(
            cfg,
            heldout_salt,
            &heldout_packs,
            &anchor_packs,
            None,
            None,
            0.0,
            0.0,
        );
        write_atomic(
            &apf3_dir.join("summary_latest.txt"),
            b"evaluated=0 promoted=none reason=no_candidates",
        )?;
        write_atomic(
            &apf3_dir.join("snapshot_latest.json"),
            b"{\"evaluated\":0,\"promoted\":null,\"reason\":\"no_candidates\"}",
        )?;
        write_atomic(
            &apf3_dir.join("run_digest.txt"),
            format!(
                "version=1\nseed={}\nheldout_salt={}\nanchor_salt={}\npromoted=none\nrun_digest={}\n",
                cfg.seed,
                heldout_salt,
                anchor_salt,
                run_digest.hex()
            )
            .as_bytes(),
        )?;
        return Ok(());
    }

    let mut exec = AALExecutor::default();

    let baseline_hash = load_active_hash(&apf3_dir.join("registry/active_candidate.json"));
    let baseline_heldout_mean = if let Some(hash) = baseline_hash {
        if let Some((_, graph)) = candidates.iter().find(|(h, _)| *h == hash) {
            eval_mean_cached(&mut exec, &cache_root, hash, graph, &heldout_packs)?
        } else {
            f32::NEG_INFINITY
        }
    } else {
        f32::NEG_INFINITY
    };
    let baseline_anchor_mean = if let Some(hash) = baseline_hash {
        if let Some((_, graph)) = candidates.iter().find(|(h, _)| *h == hash) {
            eval_mean_cached(&mut exec, &cache_root, hash, graph, &anchor_packs)?
        } else {
            f32::NEG_INFINITY
        }
    } else {
        f32::NEG_INFINITY
    };

    let identity_gate = load_identity_gate(&apf3_dir.join("receipts/wake"))?;

    let mut best_hash = None;
    let mut best_graph: Option<AALGraph> = None;
    let mut best_heldout_mean = baseline_heldout_mean;
    let mut best_anchor_mean = baseline_anchor_mean;

    for (cand_hash, graph) in &candidates {
        let identity_ok = identity_gate.get(cand_hash).copied().unwrap_or(false);
        let heldout_mean =
            eval_mean_cached(&mut exec, &cache_root, *cand_hash, graph, &heldout_packs)?;
        let anchor_mean =
            eval_mean_cached(&mut exec, &cache_root, *cand_hash, graph, &anchor_packs)?;
        let heldout_ok = eval_all_ok(&cache_root, *cand_hash, &heldout_packs)?;
        let anchor_ok = eval_all_ok(&cache_root, *cand_hash, &anchor_packs)?;

        let improves_heldout = heldout_mean > baseline_heldout_mean + 1e-4;
        let anchor_non_regressed = anchor_mean + 1e-6 >= baseline_anchor_mean;
        if identity_ok
            && heldout_ok
            && anchor_ok
            && improves_heldout
            && anchor_non_regressed
            && heldout_mean > best_heldout_mean + 1e-9
        {
            best_heldout_mean = heldout_mean;
            best_anchor_mean = anchor_mean;
            best_hash = Some(*cand_hash);
            best_graph = Some(graph.clone());
        }
    }

    let promoted = if let Some(hash) = best_hash {
        let delta = best_heldout_mean - baseline_heldout_mean;
        let receipt = JudgeDecisionReceipt {
            candidate_hash: hash,
            decision: "promote".to_string(),
            delta_vs_baseline: delta,
            heldout_mean: best_heldout_mean,
            baseline_mean: baseline_heldout_mean,
            anchor_mean: best_anchor_mean,
            baseline_anchor_mean,
            evidence_digests: heldout_packs
                .iter()
                .chain(anchor_packs.iter())
                .map(|p| p.pack_digest)
                .collect(),
            config_seed: cfg.seed,
            timestamp_unix: splitmix64(cfg.seed ^ u64::from(hash.0[0])),
        };

        let receipt_path = receipts_dir.join(format!("{}.json", hash.hex()));
        write_json_atomic(&receipt_path, &receipt)?;

        let diff_path = registry_diffs.join(format!("{}.json", hash.hex()));
        let ptr = ActiveCandidatePointer {
            candidate_hash: hash,
            graph_path: registry_candidates
                .join(format!("{}.json", hash.hex()))
                .to_string_lossy()
                .to_string(),
            diff_path: diff_path
                .exists()
                .then(|| diff_path.to_string_lossy().to_string()),
            decision_receipt_path: receipt_path.to_string_lossy().to_string(),
        };
        write_json_atomic(&apf3_dir.join("registry/active_candidate.json"), &ptr)?;

        Some((hash, delta))
    } else {
        // Emit a deterministic reject receipt for the currently best-known baseline.
        let hash = baseline_hash.unwrap_or(Digest32::zero());
        let receipt = JudgeDecisionReceipt {
            candidate_hash: hash,
            decision: "reject".to_string(),
            delta_vs_baseline: 0.0,
            heldout_mean: baseline_heldout_mean,
            baseline_mean: baseline_heldout_mean,
            anchor_mean: baseline_anchor_mean,
            baseline_anchor_mean,
            evidence_digests: heldout_packs
                .iter()
                .chain(anchor_packs.iter())
                .map(|p| p.pack_digest)
                .collect(),
            config_seed: cfg.seed,
            timestamp_unix: splitmix64(cfg.seed ^ 0xAA55_AA55_AA55_AA55),
        };
        write_json_atomic(
            &receipts_dir.join(format!("reject_{}.json", hash.hex())),
            &receipt,
        )?;
        None
    };

    let promoted_hash_str = promoted
        .map(|(h, _)| h.hex())
        .unwrap_or_else(|| "none".to_string());
    let summary = format!(
        "evaluated={} promoted={} heldout_best={:.6} heldout_baseline={:.6} anchor_best={:.6} anchor_baseline={:.6}",
        candidates.len(),
        promoted_hash_str,
        best_heldout_mean,
        baseline_heldout_mean,
        best_anchor_mean,
        baseline_anchor_mean
    );
    write_atomic(&apf3_dir.join("summary_latest.txt"), summary.as_bytes())?;

    let snapshot = serde_json::json!({
        "evaluated": candidates.len(),
        "promoted": promoted.map(|(h, delta)| serde_json::json!({"candidate_hash": h.hex(), "delta": delta})),
        "heldout_best": best_heldout_mean,
        "heldout_baseline": baseline_heldout_mean,
        "anchor_best": best_anchor_mean,
        "anchor_baseline": baseline_anchor_mean,
    });
    write_atomic(
        &apf3_dir.join("snapshot_latest.json"),
        serde_json::to_string_pretty(&snapshot)
            .map_err(|e| e.to_string())?
            .as_bytes(),
    )?;

    let run_digest = build_run_digest(
        cfg,
        heldout_salt,
        &heldout_packs,
        &anchor_packs,
        baseline_hash,
        promoted.map(|(h, _)| h),
        best_heldout_mean,
        best_anchor_mean,
    );
    write_atomic(
        &apf3_dir.join("run_digest.txt"),
        format!(
            "version=1\nseed={}\nheldout_salt={}\nanchor_salt={}\nbaseline={}\npromoted={}\nheldout_best={:.6}\nanchor_best={:.6}\nrun_digest={}\n",
            cfg.seed,
            heldout_salt,
            anchor_salt,
            baseline_hash
                .map(|h| h.hex())
                .unwrap_or_else(|| "none".to_string()),
            promoted
                .map(|(h, _)| h.hex())
                .unwrap_or_else(|| "none".to_string()),
            best_heldout_mean,
            best_anchor_mean,
            run_digest.hex()
        )
        .as_bytes(),
    )?;

    let _ = best_graph;
    Ok(())
}

fn build_run_digest(
    cfg: &JudgeConfig,
    heldout_salt: u64,
    heldout_packs: &[MetaChunkPack],
    anchor_packs: &[MetaChunkPack],
    baseline: Option<Digest32>,
    promoted: Option<Digest32>,
    best_heldout_mean: f32,
    best_anchor_mean: f32,
) -> Digest32 {
    let mut b = DigestBuilder::new(TAG_APF3_RUN_V1);
    b.u64(cfg.seed);
    b.u64(heldout_salt);
    b.u64(heldout_packs.len() as u64);
    for p in heldout_packs {
        b.digest32(p.pack_digest);
    }
    b.u64(anchor_packs.len() as u64);
    for p in anchor_packs {
        b.digest32(p.pack_digest);
    }
    if let Some(p) = baseline {
        b.digest32(p);
    }
    if let Some(p) = promoted {
        b.digest32(p);
    }
    b.f32(best_heldout_mean);
    b.f32(best_anchor_mean);
    b.finish()
}

fn load_or_create_heldout_salt(path: &Path, seed: u64) -> Result<u64, String> {
    if path.exists() {
        let data = fs::read(path).map_err(|e| e.to_string())?;
        if data.len() >= 8 {
            let mut arr = [0_u8; 8];
            arr.copy_from_slice(&data[..8]);
            return Ok(u64::from_le_bytes(arr));
        }
        return Err("heldout salt file exists but is too short".to_string());
    }

    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }

    let salt = mix_seed(seed, 0x48454C444F5554_u64, 0);
    write_atomic(path, &salt.to_le_bytes())?;
    Ok(salt)
}

fn load_or_create_heldout_packs(dir: &Path, salt: u64) -> Result<Vec<MetaChunkPack>, String> {
    fs::create_dir_all(dir).map_err(|e| e.to_string())?;

    let mut files = fs::read_dir(dir)
        .map_err(|e| e.to_string())?
        .filter_map(|e| e.ok())
        .map(|e| e.path())
        .filter(|p| p.extension().and_then(|x| x.to_str()) == Some("json"))
        .collect::<Vec<_>>();
    files.sort();

    if files.is_empty() {
        let support = vec![Chunk {
            x: vec![0.0, 1.0],
            y: vec![0.0],
            meta: vec![1],
        }];
        let query = vec![Chunk {
            x: vec![1.0, 0.0],
            y: vec![1.0],
            meta: vec![2],
        }];
        let pack = MetaChunkPack::new(1, support, query, salt);
        pack.to_json_file(&dir.join("heldout_default.json"))?;
        return Ok(vec![pack]);
    }

    let mut out = Vec::with_capacity(files.len());
    for p in files {
        out.push(MetaChunkPack::from_json_file(&p)?);
    }
    Ok(out)
}

fn load_or_create_anchor_packs(dir: &Path, salt: u64) -> Result<Vec<MetaChunkPack>, String> {
    fs::create_dir_all(dir).map_err(|e| e.to_string())?;

    let mut files = fs::read_dir(dir)
        .map_err(|e| e.to_string())?
        .filter_map(|e| e.ok())
        .map(|e| e.path())
        .filter(|p| p.extension().and_then(|x| x.to_str()) == Some("json"))
        .collect::<Vec<_>>();
    files.sort();

    if files.is_empty() {
        let support = vec![Chunk {
            x: vec![1.0, 1.0],
            y: vec![1.0],
            meta: vec![11],
        }];
        let query = vec![Chunk {
            x: vec![0.0, 1.0],
            y: vec![0.5],
            meta: vec![12],
        }];
        let pack = MetaChunkPack::new(1, support, query, salt);
        pack.to_json_file(&dir.join("anchor_default.json"))?;
        return Ok(vec![pack]);
    }

    let mut out = Vec::with_capacity(files.len());
    for p in files {
        out.push(MetaChunkPack::from_json_file(&p)?);
    }
    Ok(out)
}

fn load_candidate_graphs(dir: &Path) -> Result<Vec<(Digest32, AALGraph)>, String> {
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

    let mut out = Vec::new();
    for path in files {
        let stem = path
            .file_stem()
            .and_then(|s| s.to_str())
            .ok_or_else(|| format!("invalid candidate filename: {}", path.display()))?;
        let hash = parse_digest_hex(stem)?;
        let graph: AALGraph = serde_json::from_slice(&fs::read(&path).map_err(|e| e.to_string())?)
            .map_err(|e| format!("parse {}: {e}", path.display()))?;
        out.push((hash, graph));
    }
    Ok(out)
}

fn eval_mean_cached(
    exec: &mut AALExecutor,
    cache_root: &Path,
    candidate_hash: Digest32,
    graph: &AALGraph,
    packs: &[MetaChunkPack],
) -> Result<f32, String> {
    let mut samples = Vec::with_capacity(packs.len());

    for pack in packs {
        let cache_path = cache_root
            .join(candidate_hash.hex())
            .join(format!("{}.json", pack.pack_digest.hex()));

        let row = if cache_path.exists() {
            serde_json::from_slice::<PackEvalCache>(
                &fs::read(&cache_path).map_err(|e| e.to_string())?,
            )
            .map_err(|e| e.to_string())?
        } else {
            let rep = exec.eval_pack(graph, pack, None);
            let row = PackEvalCache {
                candidate_hash,
                pack_digest: pack.pack_digest,
                query_score_mean: rep.query_score_mean,
                stop: format!("{:?}", rep.stop),
                failure_label: rep.failure_label.map(|s| s.to_string()),
            };
            if let Some(parent) = cache_path.parent() {
                fs::create_dir_all(parent).map_err(|e| e.to_string())?;
            }
            write_json_atomic(&cache_path, &row)?;
            row
        };

        samples.push(row.query_score_mean);
    }

    Ok(if samples.is_empty() {
        f32::NEG_INFINITY
    } else {
        samples.iter().copied().sum::<f32>() / samples.len() as f32
    })
}

fn eval_all_ok(
    cache_root: &Path,
    candidate_hash: Digest32,
    packs: &[MetaChunkPack],
) -> Result<bool, String> {
    for pack in packs {
        let cache_path = cache_root
            .join(candidate_hash.hex())
            .join(format!("{}.json", pack.pack_digest.hex()));
        let row: PackEvalCache =
            serde_json::from_slice(&fs::read(&cache_path).map_err(|e| e.to_string())?)
                .map_err(|e| e.to_string())?;
        if row.stop != format!("{:?}", ExecStop::Ok) || row.failure_label.is_some() {
            return Ok(false);
        }
    }
    Ok(true)
}

fn load_active_hash(path: &Path) -> Option<Digest32> {
    let data = fs::read(path).ok()?;
    let ptr: ActiveCandidatePointer = serde_json::from_slice(&data).ok()?;
    Some(ptr.candidate_hash)
}

fn load_identity_gate(dir: &Path) -> Result<std::collections::HashMap<Digest32, bool>, String> {
    let mut out = std::collections::HashMap::new();
    if !dir.exists() {
        return Ok(out);
    }

    let mut files = fs::read_dir(dir)
        .map_err(|e| e.to_string())?
        .filter_map(|e| e.ok())
        .map(|e| e.path())
        .filter(|p| p.extension().and_then(|x| x.to_str()) == Some("json"))
        .collect::<Vec<_>>();
    files.sort();

    for path in files {
        let receipt: crate::apf3::wake::WakeReceipt =
            serde_json::from_slice(&fs::read(&path).map_err(|e| e.to_string())?)
                .map_err(|e| e.to_string())?;
        out.insert(receipt.candidate_hash, receipt.identity_passed);
    }

    Ok(out)
}

fn parse_digest_hex(hex: &str) -> Result<Digest32, String> {
    if hex.len() != 64 {
        return Err(format!("invalid digest hex length: {hex}"));
    }
    let mut out = [0_u8; 32];
    for (i, chunk) in hex.as_bytes().chunks_exact(2).enumerate() {
        out[i] = (hex_val(chunk[0])? << 4) | hex_val(chunk[1])?;
    }
    Ok(Digest32(out))
}

fn hex_val(c: u8) -> Result<u8, String> {
    match c {
        b'0'..=b'9' => Ok(c - b'0'),
        b'a'..=b'f' => Ok(10 + c - b'a'),
        b'A'..=b'F' => Ok(10 + c - b'A'),
        _ => Err(format!("invalid hex byte: {}", c as char)),
    }
}

fn write_json_atomic<T: Serialize>(path: &Path, value: &T) -> Result<(), String> {
    let body = serde_json::to_vec_pretty(value).map_err(|e| e.to_string())?;
    write_atomic(path, &body)
}
