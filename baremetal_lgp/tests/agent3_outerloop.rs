use std::fs;
use std::path::PathBuf;

use baremetal_lgp::search::ir::CandidateCfg;
use baremetal_lgp::search::topk_trace::{TopKTraceManager, TraceOracle, TraceSummary};
use baremetal_lgp::types::CandidateId;

struct DummyTraceOracle;

impl TraceOracle for DummyTraceOracle {
    fn run_trace(&mut self, candidate: &CandidateCfg) -> TraceSummary {
        TraceSummary {
            blocks: (0..candidate.blocks.len()).map(|x| x as u16).collect(),
            edges: Vec::new(),
            checkpoints: 1,
            score: 1.0,
            fuel_used: 1,
        }
    }
}

#[test]
fn agent3_topk_trace_writes_only_on_entry() {
    let run_dir = unique_temp_dir("agent3_topk");
    fs::create_dir_all(&run_dir).expect("create run dir");
    let mut manager = TopKTraceManager::new(&run_dir, 2).expect("create manager");
    let mut tracer = DummyTraceOracle;
    let cfg = CandidateCfg::default();

    let entered = manager
        .consider(CandidateId(1), 0.2, &cfg, &mut tracer)
        .expect("trace run");
    assert!(entered);
    assert!(run_dir.join("traces/1.bin").exists());

    let entered_again = manager
        .consider(CandidateId(1), 0.19, &cfg, &mut tracer)
        .expect("second trace");
    assert!(!entered_again);
}

#[test]
fn agent3_topk_rejects_low_score_when_full() {
    let run_dir = unique_temp_dir("agent3_topk_full");
    fs::create_dir_all(&run_dir).expect("create run dir");
    let mut manager = TopKTraceManager::new(&run_dir, 1).expect("create manager");
    let mut tracer = DummyTraceOracle;
    let cfg = CandidateCfg::default();

    assert!(manager
        .consider(CandidateId(1), 0.5, &cfg, &mut tracer)
        .expect("first"));
    assert!(!manager
        .consider(CandidateId(2), 0.1, &cfg, &mut tracer)
        .expect("second"));
    assert!(!run_dir.join("traces/2.bin").exists());
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
