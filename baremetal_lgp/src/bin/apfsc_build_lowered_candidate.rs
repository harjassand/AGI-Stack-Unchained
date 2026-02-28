use std::collections::BTreeMap;
use std::path::PathBuf;

use baremetal_lgp::apfsc::artifacts::{candidate_dir, read_json, write_json_atomic};
use baremetal_lgp::apfsc::candidate::load_candidate;
use baremetal_lgp::apfsc::config::Phase1Config;
use baremetal_lgp::apfsc::macro_lib::load_or_build_active_registry;
use baremetal_lgp::apfsc::scir::canonical::canonicalize_v2;
use baremetal_lgp::apfsc::scir::lower::lower_v2_with_macros;
use baremetal_lgp::apfsc::scir::verify::verify_scir_v2;
use baremetal_lgp::apfsc::types::{
    AdaptHook, BoundSpec, ChannelDef, CoreBlock, CoreOp, ReadoutDef, ScheduleDef, ScirV2Program,
    StateSchema,
};
use clap::Parser;

#[derive(Debug, Parser)]
struct Args {
    #[arg(long, default_value = ".apfsc")]
    root: PathBuf,
    #[arg(long)]
    candidate: String,
    #[arg(long)]
    config: Option<PathBuf>,
}

fn main() -> Result<(), String> {
    let args = Args::parse();
    let cfg = if let Some(path) = &args.config {
        Phase1Config::from_path(path).map_err(|e| e.to_string())?
    } else {
        Phase1Config::default()
    };

    let candidate = load_candidate(&args.root, &args.candidate).map_err(|e| e.to_string())?;
    let cdir = candidate_dir(&args.root, &candidate.manifest.candidate_hash);

    let scir_v2_path = cdir.join("scir_v2.json");
    let scir_v2: ScirV2Program = if scir_v2_path.exists() {
        read_json(&scir_v2_path).map_err(|e| e.to_string())?
    } else {
        let v2 = derive_v2_from_candidate(&candidate);
        write_json_atomic(&scir_v2_path, &v2).map_err(|e| e.to_string())?;
        v2
    };

    let registry = load_or_build_active_registry(
        &args.root,
        &candidate.manifest.snapshot_hash,
        &cfg.protocol.version,
    )
    .map_err(|e| e.to_string())?;

    let canonical = canonicalize_v2(scir_v2);
    write_json_atomic(&cdir.join("scir_canonical.json"), &canonical).map_err(|e| e.to_string())?;

    let (lowered, receipt) = lower_v2_with_macros(&candidate.manifest.candidate_hash, &canonical, &registry)
        .map_err(|e| e.to_string())?;
    verify_scir_v2(&lowered).map_err(|e| e.to_string())?;

    write_json_atomic(&cdir.join("scir_lowered.json"), &lowered).map_err(|e| e.to_string())?;
    write_json_atomic(&cdir.join("compile_receipt.json"), &receipt).map_err(|e| e.to_string())?;

    println!(
        "candidate={} lowered_hash={} graph_eligible={}",
        candidate.manifest.candidate_hash, receipt.lowered_hash, receipt.graph_backend_eligible
    );
    Ok(())
}

fn derive_v2_from_candidate(candidate: &baremetal_lgp::apfsc::candidate::CandidateBundle) -> ScirV2Program {
    let mut ops = Vec::new();
    for node in &candidate.arch_program.nodes {
        let mut args = BTreeMap::new();
        args.insert("node_id".to_string(), node.id.to_string());
        args.insert("op".to_string(), format!("{:?}", node.op));
        ops.push(CoreOp {
            op: "LinearMix".to_string(),
            args,
        });
    }

    ScirV2Program {
        version: "scir-v2".to_string(),
        state_schema: StateSchema {
            schema_id: "default_state".to_string(),
            bytes: ((candidate.state_pack.core_weights.len()
                + candidate.state_pack.resid_weights.len()
                + candidate.state_pack.init_state.len())
                * 4) as u64,
        },
        channels: vec![ChannelDef {
            id: "byte_in".to_string(),
            width: 1,
        }],
        core_blocks: vec![CoreBlock {
            id: "main".to_string(),
            ops,
        }],
        macro_calls: Vec::new(),
        schedule: ScheduleDef {
            scheduler_class: candidate
                .schedule_pack
                .scheduler_class
                .unwrap_or(baremetal_lgp::apfsc::types::SchedulerClass::SerialScan),
            backend_hint: baremetal_lgp::apfsc::types::BackendKind::InterpTier0,
        },
        readouts: vec![ReadoutDef {
            id: "native".to_string(),
            head: "native_head".to_string(),
        }],
        adapt_hooks: vec![AdaptHook {
            id: "transfer".to_string(),
            target: "nuisance_head".to_string(),
        }],
        bounds: BoundSpec {
            max_core_ops: baremetal_lgp::apfsc::constants::MAX_SCIR_CORE_OPS,
            max_state_bytes: baremetal_lgp::apfsc::constants::STATE_TILE_BYTES_MAX,
            max_macro_calls: baremetal_lgp::apfsc::constants::MAX_MACRO_CALLS_PER_PROGRAM,
        },
    }
}
