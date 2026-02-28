use std::path::PathBuf;

use baremetal_lgp::apfsc::config::Phase1Config;
use baremetal_lgp::apfsc::ingress::tool::ingest_tool;
use baremetal_lgp::apfsc::tool_shadow::evaluate_tool_shadow;
use baremetal_lgp::apfsc::types::ToolShadowStatus;
use tempfile::tempdir;

fn fixtures_phase4() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("fixtures/apfsc/phase4")
}

#[test]
fn tool_shadow_promotes_only_on_exact_match() {
    let tmp = tempdir().expect("tmp");
    let root = tmp.path().join(".apfsc");
    let cfg = Phase1Config::default();
    baremetal_lgp::apfsc::seed::seed_init(&root, &cfg, None, true).expect("seed");

    let (ing, _) = ingest_tool(
        &root,
        &cfg,
        &fixtures_phase4().join("tools/tool_graph_shadow/manifest.json"),
    )
    .expect("ingest tool");

    let pass = evaluate_tool_shadow(
        &root,
        &ing.pack_hash,
        None,
        "snap",
        "const",
        "apfsc-phase4-final-v1",
    )
    .expect("eval pass");
    assert_eq!(pass.status, ToolShadowStatus::PublicCanaryEligible);

    std::fs::remove_file(
        root.join("toolpacks")
            .join(&ing.pack_hash)
            .join("gold_traces.jsonl"),
    )
    .expect("remove gold");
    let fail = evaluate_tool_shadow(
        &root,
        &ing.pack_hash,
        None,
        "snap",
        "const",
        "apfsc-phase4-final-v1",
    )
    .expect("eval fail");
    assert!(matches!(
        fail.status,
        ToolShadowStatus::Rejected | ToolShadowStatus::DiscoveryOnly
    ));
}
