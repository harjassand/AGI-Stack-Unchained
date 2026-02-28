use baremetal_lgp::apf3::aal_exec::TraceStats;
use baremetal_lgp::apf3::profiler::{
    classify_failures, compute_metrics, FailureLabel, ProfilerThresholds,
};

#[test]
fn apf3_profiler_labels_expected_failures() {
    let trace = TraceStats {
        query_loss_last: 1.0,
        query_loss_min: 0.2,
        mem_reads: 10,
        mem_writes: 2_000,
        update_l1: 1e-9,
        native_faults: 5,
        native_timeouts: 1,
        ..TraceStats::default()
    };

    let metrics = compute_metrics(&trace, 100, 0.20, 0.195, 0.8, Some(0.7));
    let labels = classify_failures(&metrics, &trace, &ProfilerThresholds::default(), false);

    assert!(labels.contains(&FailureLabel::CapacityFailure));
    assert!(labels.contains(&FailureLabel::MemoryFailure));
    assert!(labels.contains(&FailureLabel::UpdateFailure));
    assert!(labels.contains(&FailureLabel::NativeBlockFailure));
    assert!(labels.contains(&FailureLabel::OverfitFailure));
}
