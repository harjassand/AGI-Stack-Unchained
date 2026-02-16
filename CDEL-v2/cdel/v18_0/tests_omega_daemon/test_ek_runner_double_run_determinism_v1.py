from __future__ import annotations

from pathlib import Path

from cdel.v18_0.ek import ek_runner_v1


def test_run_ek_refutes_when_double_run_diverges(tmp_path: Path, monkeypatch) -> None:
    ccap = {
        "meta": {
            "ek_id": "sha256:" + ("1" * 64),
        },
        "budgets": {
            "cpu_ms_max": 10_000,
            "wall_ms_max": 10_000,
            "mem_mb_max": 10_000,
            "disk_mb_max": 10_000,
            "fds_max": 1_000,
            "procs_max": 1_000,
            "threads_max": 1_000,
            "net": "forbidden",
        },
    }

    monkeypatch.setattr(
        ek_runner_v1,
        "_load_active_ek",
        lambda _repo_root, _expected: {
            "schema_version": "evaluation_kernel_v1",
            "stages": [
                {"stage_name": "REALIZE"},
                {"stage_name": "SCORE"},
                {"stage_name": "FINAL_AUDIT"},
            ],
            "scoring_impl": {"code_ref": {"path": "tools/omega/omega_benchmark_suite_v1.py"}},
        },
    )

    calls = {"count": 0}

    def _fake_realize_once(**_kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return {
                "ok": True,
                "applied_tree_id": "sha256:" + ("a" * 64),
                "realized_out_id": "sha256:" + ("b" * 64),
                "transcript_id": "sha256:" + ("c" * 64),
                "realize_logs_hash": "sha256:" + ("d" * 64),
                "harness_cost_vector": {},
            }
        return {
            "ok": True,
            "applied_tree_id": "sha256:" + ("a" * 64),
            "realized_out_id": "sha256:" + ("e" * 64),
            "transcript_id": "sha256:" + ("f" * 64),
            "realize_logs_hash": "sha256:" + ("d" * 64),
            "harness_cost_vector": {},
        }

    monkeypatch.setattr(ek_runner_v1, "_realize_once", _fake_realize_once)

    result = ek_runner_v1.run_ek(
        repo_root=tmp_path,
        subrun_root=tmp_path,
        ccap_id="sha256:" + ("9" * 64),
        ccap=ccap,
        out_dir=tmp_path / "ek_out",
    )

    assert result["determinism_check"] == "DIVERGED"
    assert result["eval_status"] == "REFUTED"
    assert result["decision"] == "REJECT"
    assert result["refutation"]["code"] == "NONDETERMINISM_DETECTED"
