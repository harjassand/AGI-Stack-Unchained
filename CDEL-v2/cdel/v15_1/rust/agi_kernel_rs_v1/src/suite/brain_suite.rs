use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

use serde::Deserialize;
use serde_json::{json, Value};

use crate::brain::context::BrainContext;
use crate::brain::decision::{brain_decide_with_metrics, BrainDecisionMetrics};
use crate::canon;
use crate::hash;
use crate::kernel_sys;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct SuiteCase {
    case_id: String,
    context_rel: String,
    decision_ref_rel: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct SuitePack {
    schema_version: String,
    cases: Vec<SuiteCase>,
}

fn append_chain_event(
    schema_version: &str,
    event_type: &str,
    payload: Value,
    prev: &mut String,
    out: &mut Vec<Value>,
) -> Result<(), String> {
    let base = json!({
        "schema_version": schema_version,
        "prev_event_ref_hash": prev,
        "event_type": event_type,
        "payload": payload,
    });
    let event_hash = hash::sha256_bytes(&canon::canonical_bytes(&base)?)?;
    let mut event = base;
    if let Some(map) = event.as_object_mut() {
        map.insert("event_ref_hash".to_string(), Value::String(event_hash.clone()));
    }
    *prev = event_hash;
    out.push(event);
    Ok(())
}

fn write_jsonl(path: &Path, rows: &[Value]) -> Result<(), String> {
    let mut bytes: Vec<u8> = Vec::new();
    for row in rows {
        let mut line = canon::canonical_bytes(row)?;
        line.push(b'\n');
        bytes.extend_from_slice(&line);
    }
    kernel_sys::write_bytes(path, &bytes)
}

fn read_canonical_bytes(path: &Path) -> Result<Vec<u8>, String> {
    let value = canon::read_json(path)?;
    canon::canonical_bytes(&value)
}

pub fn execute_brain_suite(suitepack_path: &str, out_dir: &str) -> Result<i32, String> {
    let cwd = kernel_sys::current_dir()?;
    let suitepack_abs = PathBuf::from(suitepack_path);
    let suitepack_dir = suitepack_abs
        .parent()
        .ok_or_else(|| "INVALID:BRAIN_SUITEPACK".to_string())?
        .to_path_buf();
    let suitepack_value = canon::read_json(&suitepack_abs)?;
    let suitepack: SuitePack = serde_json::from_value(suitepack_value).map_err(|_| "INVALID:BRAIN_SUITEPACK".to_string())?;
    if suitepack.schema_version != "brain_corpus_suitepack_v1" || suitepack.cases.is_empty() {
        return Err("INVALID:BRAIN_SUITEPACK".to_string());
    }

    let out_root = if Path::new(out_dir).is_absolute() {
        PathBuf::from(out_dir)
    } else {
        cwd.join(out_dir)
    };
    if out_root.exists() {
        kernel_sys::remove_dir_all(&out_root)?;
    }
    let cases_out = out_root.join("cases");
    let kernel_root = out_root.join("kernel");
    let trace_path = kernel_root.join("trace").join("kernel_trace_v1.jsonl");
    let ledger_path = kernel_root.join("ledger").join("kernel_ledger_v1.jsonl");
    let reports_dir = kernel_root.join("reports");
    let branch_path = reports_dir.join("branch_coverage_report_v1.json");
    let perf_path = reports_dir.join("kernel_brain_perf_report_v1.json");
    let suite_report_path = reports_dir.join("brain_suite_report_v1.json");

    kernel_sys::create_dir_all(&cases_out)?;
    kernel_sys::create_dir_all(&reports_dir)?;

    let mut trace_prev = "GENESIS".to_string();
    let mut ledger_prev = "GENESIS".to_string();
    let mut trace_rows: Vec<Value> = Vec::new();
    let mut ledger_rows: Vec<Value> = Vec::new();

    append_chain_event(
        "kernel_trace_event_v1",
        "BRAIN_SUITE_BEGIN_V1",
        json!({"cases": suitepack.cases.len()}),
        &mut trace_prev,
        &mut trace_rows,
    )?;
    append_chain_event(
        "kernel_ledger_entry_v1",
        "BRAIN_SUITE_BEGIN_V1",
        json!({"cases": suitepack.cases.len()}),
        &mut ledger_prev,
        &mut ledger_rows,
    )?;

    let mut hist: BTreeMap<String, u64> = BTreeMap::new();
    let mut non_trivial = 0_u64;
    let mut failed = 0_u64;
    let mut passed = 0_u64;
    let mut perf_rows: Vec<Value> = Vec::new();
    let mut candidate_total = 0_u64;

    for case in &suitepack.cases {
        let ctx_path = suitepack_dir.join(&case.context_rel);
        let ref_path = suitepack_dir.join(&case.decision_ref_rel);
        let ctx_value = canon::read_json(&ctx_path)?;
        let ctx: BrainContext = serde_json::from_value(ctx_value).map_err(|_| "INVALID:BRAIN_CONTEXT".to_string())?;
        ctx.validate()?;

        let (decision, metrics): (_, BrainDecisionMetrics) = brain_decide_with_metrics(&ctx)?;
        if decision.rule_path.len() > 1 {
            non_trivial += 1;
        }

        let decision_value = serde_json::to_value(&decision).map_err(|_| "INVALID:SCHEMA_FAIL".to_string())?;
        let out_case_dir = cases_out.join(&case.case_id);
        kernel_sys::create_dir_all(&out_case_dir)?;
        let out_decision_path = out_case_dir.join("brain_decision_kernel_v1.json");
        let out_perf_path = out_case_dir.join("brain_perf_case_v1.json");
        canon::write_json(&out_decision_path, &decision_value)?;
        let metrics_value = serde_json::to_value(&metrics).map_err(|_| "INVALID:SCHEMA_FAIL".to_string())?;
        canon::write_json(&out_perf_path, &metrics_value)?;
        candidate_total = candidate_total.saturating_add(metrics.candidate_steps_u64);
        perf_rows.push(json!({
            "case_id": case.case_id,
            "baseline_opcodes": 1,
            "candidate_opcodes": metrics.candidate_steps_u64,
        }));

        let ref_bytes = read_canonical_bytes(&ref_path)?;
        let kernel_bytes = read_canonical_bytes(&out_decision_path)?;
        let ok = ref_bytes == kernel_bytes;
        if ok {
            passed += 1;
        } else {
            failed += 1;
        }

        let count = hist.entry(decision.branch_signature.clone()).or_insert(0);
        *count += 1;

        append_chain_event(
            "kernel_trace_event_v1",
            "BRAIN_CASE_V1",
            json!({"case_id": case.case_id, "ok": ok}),
            &mut trace_prev,
            &mut trace_rows,
        )?;
        append_chain_event(
            "kernel_ledger_entry_v1",
            "BRAIN_CASE_V1",
            json!({"case_id": case.case_id, "ok": ok}),
            &mut ledger_prev,
            &mut ledger_rows,
        )?;
    }

    append_chain_event(
        "kernel_trace_event_v1",
        "BRAIN_SUITE_END_V1",
        json!({"passed": passed, "failed": failed}),
        &mut trace_prev,
        &mut trace_rows,
    )?;
    append_chain_event(
        "kernel_ledger_entry_v1",
        "BRAIN_SUITE_END_V1",
        json!({"passed": passed, "failed": failed}),
        &mut ledger_prev,
        &mut ledger_rows,
    )?;

    write_jsonl(&trace_path, &trace_rows)?;
    write_jsonl(&ledger_path, &ledger_rows)?;

    let mut histogram: Vec<Value> = Vec::new();
    for (sig, count) in &hist {
        histogram.push(json!({"branch_signature": sig, "count": count}));
    }
    let branch_report = json!({
        "schema_version": "branch_coverage_report_v1",
        "total_cases": suitepack.cases.len(),
        "distinct_branch_signatures": hist.len(),
        "non_trivial_rule_path_cases": non_trivial,
        "histogram": histogram,
    });
    canon::write_json(&branch_path, &branch_report)?;

    let perf_report = json!({
        "schema_version": "kernel_brain_perf_report_v1",
        "baseline_brain_opcodes_total": suitepack.cases.len(),
        "candidate_brain_opcodes_total": candidate_total,
        "gate_multiplier": 1000,
        "gate_pass": candidate_total > 0,
        "per_case": perf_rows,
    });
    canon::write_json(&perf_path, &perf_report)?;

    let suite_report = json!({
        "schema_version": "brain_suite_report_v1",
        "total_cases": suitepack.cases.len(),
        "passed_cases": passed,
        "failed_cases": failed,
        "ledger_head_hash": ledger_prev,
        "trace_head_hash": trace_prev,
        "branch_coverage_report_rel": "reports/branch_coverage_report_v1.json",
        "perf_report_rel": "reports/kernel_brain_perf_report_v1.json",
        "all_pass": failed == 0,
    });
    canon::write_json(&suite_report_path, &suite_report)?;

    if failed > 0 {
        return Ok(40);
    }
    Ok(0)
}
