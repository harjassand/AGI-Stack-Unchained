use std::fs;
use std::path::Path;

use crate::apfsc::artifacts::{ensure_layout, store_snapshot, write_bytes_atomic, write_pointer};
use crate::apfsc::candidate::{
    build_candidate, default_resource_envelope, save_candidate, BuildMeta, CandidateBuildInput,
};
use crate::apfsc::config::Phase1Config;
use crate::apfsc::constants::FAST_WEIGHT_MAX_BYTES;
use crate::apfsc::errors::{io_err, Result};
use crate::apfsc::protocol::{initialize_protocol_files, materialize_snapshot};
use crate::apfsc::schedule_pack::default_schedule;
use crate::apfsc::scir::ast::{ProgramOutputs, ScirBounds, ScirNode, ScirOp, ScirProgram};
use crate::apfsc::types::{HeadPack, PromotionClass, StatePack};

pub fn seed_init(
    root: &Path,
    cfg: &Phase1Config,
    fixtures: Option<&Path>,
    force: bool,
) -> Result<String> {
    if force && root.exists() {
        fs::remove_dir_all(root).map_err(|e| io_err(root, e))?;
    }

    ensure_layout(root)?;
    initialize_protocol_files(root, cfg)?;

    if let Some(fixtures_dir) = fixtures {
        // Keep seed init deterministic by copying only static fixture files if requested.
        let dst = root.join("fixtures_snapshot");
        copy_tree(fixtures_dir, &dst)?;
    }

    let snapshot = materialize_snapshot(
        Vec::new(),
        Vec::new(),
        Vec::new(),
        cfg.protocol.version.clone(),
    );
    store_snapshot(root, &snapshot)?;

    let program = seed_program();
    let feature_dim = 68u32;
    let state_pack = StatePack {
        core_weights: vec![0.0; 128],
        resid_weights: vec![0.0; feature_dim as usize],
        fast_weight_budget_bytes: FAST_WEIGHT_MAX_BYTES,
        init_state: vec![0.0; 32],
        codec_version: "apfsc-state-v1".to_string(),
    };
    let head_pack = HeadPack::deterministic(feature_dim, 0);
    let schedule_pack = default_schedule(cfg);

    let mut envelope = default_resource_envelope();
    envelope.max_state_bytes = cfg.limits.state_tile_bytes_max;
    envelope.max_mapped_bytes = cfg.limits.max_concurrent_mapped_bytes;
    envelope.peak_rss_limit_bytes = cfg.limits.rss_hard_limit_bytes;

    let input = CandidateBuildInput {
        parent_hashes: Vec::new(),
        snapshot_hash: snapshot.snapshot_hash.clone(),
        promotion_class: PromotionClass::S,
        arch_program: program,
        state_pack,
        head_pack,
        bridge_pack: None,
        schedule_pack,
        prior_deps: Vec::new(),
        substrate_deps: Vec::new(),
        resource_envelope: envelope,
        build_meta: BuildMeta {
            lane: "seed".to_string(),
            mutation_type: "seed_incumbent".to_string(),
            created_unix_s: 0,
            notes: Some("deterministic phase1 seed incumbent".to_string()),
            phase2: None,
            phase3: None,
        },
    };

    let candidate = build_candidate(input)?;
    let hash = candidate.manifest.candidate_hash.clone();
    save_candidate(root, &candidate)?;

    write_pointer(root, "active_candidate", &hash)?;
    write_pointer(root, "rollback_candidate", &hash)?;
    write_pointer(root, "active_snapshot", &snapshot.snapshot_hash)?;

    init_archives(root)?;
    Ok(hash)
}

fn seed_program() -> ScirProgram {
    ScirProgram {
        input_len: 256,
        nodes: vec![
            ScirNode {
                id: 1,
                op: ScirOp::ByteEmbedding {
                    vocab: 256,
                    dim: 32,
                },
                inputs: Vec::new(),
                out_dim: 32,
                mutable: true,
            },
            ScirNode {
                id: 2,
                op: ScirOp::LagBytes {
                    lags: vec![1, 2, 4, 8],
                },
                inputs: Vec::new(),
                out_dim: 4,
                mutable: false,
            },
            ScirNode {
                id: 3,
                op: ScirOp::Concat,
                inputs: vec![1, 2],
                out_dim: 36,
                mutable: false,
            },
            ScirNode {
                id: 4,
                op: ScirOp::SimpleScan {
                    in_dim: 36,
                    hidden_dim: 32,
                },
                inputs: vec![3],
                out_dim: 32,
                mutable: false,
            },
            ScirNode {
                id: 5,
                op: ScirOp::Concat,
                inputs: vec![3, 4],
                out_dim: 68,
                mutable: false,
            },
        ],
        outputs: ProgramOutputs {
            feature_node: 5,
            shadow_feature_nodes: Vec::new(),
            probe_nodes: vec![2, 4],
        },
        bounds: ScirBounds {
            max_state_bytes: 2 * 1024 * 1024,
            max_param_bits: 64 * 1024 * 1024,
            max_steps: 1_000_000,
        },
    }
}

fn init_archives(root: &Path) -> Result<()> {
    let files = [
        root.join("archive/genealogy.jsonl"),
        root.join("archive/error_atlas.jsonl"),
        root.join("archive/failure_morph.jsonl"),
        root.join("archive/family_scores.jsonl"),
        root.join("archive/transfer_trace.jsonl"),
        root.join("archive/robustness_trace.jsonl"),
        root.join("archive/hardware_trace.jsonl"),
        root.join("queues/canary_queue.json"),
    ];
    for f in files {
        if !f.exists() {
            if f.extension().and_then(|v| v.to_str()) == Some("json") {
                write_bytes_atomic(&f, b"[]")?;
            } else {
                write_bytes_atomic(&f, b"")?;
            }
        }
    }
    Ok(())
}

fn copy_tree(src: &Path, dst: &Path) -> Result<()> {
    if !src.exists() {
        return Ok(());
    }
    if src.is_file() {
        if let Some(parent) = dst.parent() {
            fs::create_dir_all(parent).map_err(|e| io_err(parent, e))?;
        }
        let bytes = fs::read(src).map_err(|e| io_err(src, e))?;
        write_bytes_atomic(dst, &bytes)?;
        return Ok(());
    }

    fs::create_dir_all(dst).map_err(|e| io_err(dst, e))?;
    for entry in fs::read_dir(src).map_err(|e| io_err(src, e))? {
        let entry = entry.map_err(|e| io_err(src, e))?;
        let path = entry.path();
        let target = dst.join(entry.file_name());
        if entry.file_type().map_err(|e| io_err(&path, e))?.is_dir() {
            copy_tree(&path, &target)?;
        } else {
            let bytes = fs::read(&path).map_err(|e| io_err(&path, e))?;
            write_bytes_atomic(&target, &bytes)?;
        }
    }
    Ok(())
}
