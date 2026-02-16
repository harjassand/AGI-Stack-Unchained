from __future__ import annotations

from pathlib import Path

from cdel.v18_0.ek import ek_runner_v1


def test_score_stage_rejects_when_no_improvement(monkeypatch, tmp_path: Path) -> None:
    def _fake_score_once(**kwargs):
        run_label = str(kwargs.get("run_label", "")).strip()
        summary = {
            "median_stps_non_noop_q32": 1_000,
            "non_noop_ticks_per_min_f64": 2.0,
            "promotions_u64": 3,
            "activation_success_u64": 1,
        }
        if run_label == "cand":
            summary = dict(summary)
        return {
            "ok": True,
            "score_run_hash": "sha256:" + ("a" * 64 if run_label == "base" else "b" * 64),
            "scorecard_summary": summary,
        }

    monkeypatch.setattr(ek_runner_v1, "_run_score_stage_once", _fake_score_once)

    result = ek_runner_v1._run_score_stage(
        base_repo_root=tmp_path,
        candidate_repo_root=tmp_path,
        work_dir=tmp_path,
        ccap_id="sha256:" + ("1" * 64),
        ek={
            "scoring_impl": {
                "accept_policy": {
                    "stps_delta_min_q32": 1,
                    "require_any_improvement_b": True,
                }
            }
        },
    )

    assert bool(result.get("ok", True)) is False
    refutation = result.get("refutation")
    assert isinstance(refutation, dict)
    assert str(refutation.get("code", "")) == "NO_IMPROVEMENT"
    assert isinstance(result.get("score_base_summary"), dict)
    assert isinstance(result.get("score_cand_summary"), dict)
    assert isinstance(result.get("score_delta_summary"), dict)


def test_score_stage_accepts_when_promotions_improve(monkeypatch, tmp_path: Path) -> None:
    def _fake_score_once(**kwargs):
        run_label = str(kwargs.get("run_label", "")).strip()
        summary = {
            "median_stps_non_noop_q32": 1_000,
            "non_noop_ticks_per_min_f64": 2.0,
            "promotions_u64": 3,
            "activation_success_u64": 1,
        }
        if run_label == "cand":
            summary = dict(summary)
            summary["promotions_u64"] = 4
        return {
            "ok": True,
            "score_run_hash": "sha256:" + ("c" * 64 if run_label == "base" else "d" * 64),
            "scorecard_summary": summary,
        }

    monkeypatch.setattr(ek_runner_v1, "_run_score_stage_once", _fake_score_once)

    result = ek_runner_v1._run_score_stage(
        base_repo_root=tmp_path,
        candidate_repo_root=tmp_path,
        work_dir=tmp_path,
        ccap_id="sha256:" + ("2" * 64),
        ek={
            "scoring_impl": {
                "accept_policy": {
                    "stps_delta_min_q32": 1 << 62,
                    "require_any_improvement_b": True,
                }
            }
        },
    )

    assert bool(result.get("ok", False)) is True
    assert isinstance(result.get("score_base_summary"), dict)
    assert isinstance(result.get("score_cand_summary"), dict)
    assert isinstance(result.get("score_delta_summary"), dict)
