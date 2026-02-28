use std::path::{Path, PathBuf};

use baremetal_lgp::apf3::aal_ir::{
    AALGraph, NodeId, NodeKind, ParamBankSpec, ParamInit, ParamRef, ParamSpec, ValueTy,
};
use baremetal_lgp::apf3::metachunkpack::{Chunk, MetaChunkPack};
use baremetal_lgp::apf3::morphisms::{ArchitectureDiff, Morphism};

#[test]
fn apf3_wake_workers1_replay_digest_matches() {
    let bin = env!("CARGO_BIN_EXE_apf3_wake_hotloop");

    let dir1 = unique_temp_dir("apf3_replay_a");
    let dir2 = unique_temp_dir("apf3_replay_b");
    std::fs::create_dir_all(&dir1).expect("mkdir dir1");
    std::fs::create_dir_all(&dir2).expect("mkdir dir2");

    seed_inputs(&dir1);
    seed_inputs(&dir2);

    run_once(bin, &dir1);
    run_once(bin, &dir2);

    let digest1 = std::fs::read_to_string(dir1.join("apf3/run_digest.txt")).expect("read digest1");
    let digest2 = std::fs::read_to_string(dir2.join("apf3/run_digest.txt")).expect("read digest2");
    assert_eq!(digest1, digest2, "workers=1 replay digest mismatch");

    let _ = std::fs::remove_dir_all(&dir1);
    let _ = std::fs::remove_dir_all(&dir2);
}

fn run_once(bin: &str, dir: &Path) {
    let train = dir.join("apf3/packs/train");
    let proposals = dir.join("apf3/proposals");

    let status = std::process::Command::new(bin)
        .arg("--seed")
        .arg("20260227")
        .arg("--run-dir")
        .arg(dir)
        .arg("--workers")
        .arg("1")
        .arg("--max-candidates")
        .arg("1")
        .arg("--train-pack-dir")
        .arg(train)
        .arg("--proposal-dir")
        .arg(proposals)
        .status()
        .expect("run apf3 wake");
    assert!(status.success(), "apf3 wake run failed");
}

fn seed_inputs(run_dir: &Path) {
    let base_graph = AALGraph {
        version: 1,
        nodes: vec![
            (
                NodeId(0),
                NodeKind::Input {
                    index: 0,
                    ty: ValueTy::VecF32 { len: 1 },
                },
            ),
            (
                NodeId(1),
                NodeKind::Linear {
                    in_len: 1,
                    out_len: 1,
                    w: ParamRef(0),
                    b: ParamRef(1),
                },
            ),
        ],
        edges: vec![baremetal_lgp::apf3::aal_ir::Edge {
            src: (NodeId(0), 0),
            dst: (NodeId(1), 0),
        }],
        params: ParamBankSpec {
            params: vec![
                ParamSpec {
                    len: 1,
                    init: ParamInit::Zeros,
                },
                ParamSpec {
                    len: 1,
                    init: ParamInit::Zeros,
                },
            ],
        },
        mem: vec![],
        outputs: vec![(NodeId(1), 0)],
    };

    let pack = MetaChunkPack::new(
        1,
        vec![Chunk {
            x: vec![1.0],
            y: vec![1.0],
            meta: vec![],
        }],
        vec![Chunk {
            x: vec![1.0],
            y: vec![1.0],
            meta: vec![],
        }],
        99,
    );

    let diff = ArchitectureDiff {
        version: 1,
        base_graph: base_graph.digest(),
        morphisms: vec![Morphism::AddMemorySlot {
            len: 4,
            init_closed: true,
        }],
    };

    let base_path = run_dir.join("apf3/registry/base_graph.json");
    let pack_path = run_dir.join("apf3/packs/train/train_0.json");
    let diff_path = run_dir.join("apf3/proposals/p0.json");

    std::fs::create_dir_all(base_path.parent().expect("base parent")).expect("mkdir base parent");
    std::fs::create_dir_all(pack_path.parent().expect("pack parent")).expect("mkdir pack parent");
    std::fs::create_dir_all(diff_path.parent().expect("diff parent")).expect("mkdir diff parent");

    std::fs::write(
        base_path,
        serde_json::to_vec_pretty(&base_graph).expect("serialize graph"),
    )
    .expect("write base graph");
    pack.to_json_file(&pack_path).expect("write pack");
    std::fs::write(
        diff_path,
        serde_json::to_vec_pretty(&diff).expect("serialize diff"),
    )
    .expect("write diff");
}

fn unique_temp_dir(prefix: &str) -> PathBuf {
    let mut path = std::env::temp_dir();
    let pid = std::process::id();
    let nanos = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map_or(0_u128, |d| d.as_nanos());
    path.push(format!("{prefix}_{pid}_{nanos}"));
    path
}
