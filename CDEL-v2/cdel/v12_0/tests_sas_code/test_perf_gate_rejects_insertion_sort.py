from __future__ import annotations

from pathlib import Path

from cdel.v1_7r.canon import load_canon_json, sha256_prefixed, canon_bytes
from cdel.v12_0.sas_code_ir_v1 import compute_algo_id
from cdel.v12_0.sas_code_workmeter_v1 import compute_perf_report


def test_perf_gate_rejects_insertion_sort() -> None:
    repo_root = Path(__file__).resolve().parents[4]
    baseline_path = repo_root / "campaigns" / "rsi_sas_code_v12_0" / "baseline_bubble_sort_v1.sas_code_ir_v1.json"
    baseline_ir = load_canon_json(baseline_path)

    insertion_ir = dict(baseline_ir)
    insertion_ir["algo_kind"] = "INSERTION_SORT_V1"
    insertion_ir["tags"] = ["n2", "local_swap"]
    insertion_ir["algo_id"] = compute_algo_id(insertion_ir)

    suite = load_canon_json(repo_root / "campaigns" / "rsi_sas_code_v12_0" / "sas_code_suitepack_heldout_v1.json")
    suite["suitepack_hash"] = sha256_prefixed(canon_bytes(suite))
    policy = load_canon_json(repo_root / "campaigns" / "rsi_sas_code_v12_0" / "sas_code_perf_policy_v1.json")

    report = compute_perf_report(
        eval_kind="HELDOUT",
        suitepack=suite,
        baseline_algo_id=baseline_ir["algo_id"],
        baseline_algo_kind=baseline_ir["algo_kind"],
        candidate_algo_id=insertion_ir["algo_id"],
        candidate_algo_kind=insertion_ir["algo_kind"],
        policy=policy,
    )
    assert report["gate"]["passed"] is False
    assert "NO_PERF_GAIN" in report["gate"]["reasons"]
