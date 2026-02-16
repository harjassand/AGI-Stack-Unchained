from __future__ import annotations

import json
import subprocess
from pathlib import Path

from self_improve_code_v1.domains.flagship_code_rsi_v1.domain import run_flagship


def _init_git_repo(repo_dir: Path) -> str:
    subprocess.run(["git", "init", str(repo_dir)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo_dir), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(repo_dir), "config", "user.name", "Test"], check=True)
    (repo_dir / "a.py").write_text(
        "def f(data, items):\n    if data:\n        return data['x'] + items[0]\n    return 0\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "-C", str(repo_dir), "add", "a.py"], check=True)
    subprocess.run(["git", "-C", str(repo_dir), "commit", "-m", "init"], check=True, capture_output=True)
    proc = subprocess.run(["git", "-C", str(repo_dir), "rev-parse", "HEAD"], check=True, capture_output=True)
    return (proc.stdout or b"").decode("utf-8").strip()


def test_min_eligible_per_epoch_behavior(tmp_path: Path) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    commit = _init_git_repo(repo_dir)

    runs_root = tmp_path / "runs"
    config = {
        "schema_version": "flagship_code_rsi_v1",
        "run_id": "AUTO",
        "seed": 3,
        "target_repo_id": "test-repo",
        "target_repo_path": str(repo_dir),
        "baseline_commit": commit,
        "candidate": {"format": "repo_patch_candidate_v1", "patch_format": "unidiff", "max_patch_bytes": 200000},
        "curriculum": {
            "ladder": [{"name": "t0", "sealed_dev_plan": "plan_t0", "devscreen_suite": "stub"}],
            "advance_rule": {"type": "pass_rate_threshold", "threshold": 1, "min_epochs": 1},
            "min_submissions_before_advancing": 1,
            "deescalate_after_epochs": 1,
            "rolling_window": 1,
        },
        "proposal": {
            "candidates_per_epoch": 1,
            "topk_to_sealed_dev": 1,
            "explore_fraction": 0,
            "max_attempts_per_slot": 4,
            "max_total_attempts": 20,
            "min_eligible_per_epoch": 2,
            "template_allowlist": ["fix_bool_condition_v1", "return_early_on_invalid_v1"],
        },
        "devscreen": {"enabled": True, "suite_id": "stub", "timeout_s": 1, "max_evals_per_epoch": 2},
        "sealed_dev": {"enabled": False, "cdel_endpoint": "", "cdel_root": "", "eval_plan_id": "plan_t0", "timeout_s": 1},
        "sealed_heldout": {"enabled": False, "eval_plan_id": "", "timeout_s": 1},
        "output": {"runs_root": str(runs_root), "write_canonical_json": True},
    }

    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config, sort_keys=True), encoding="utf-8")

    run_dir = Path(run_flagship(str(config_path), epochs=1))
    summary = json.loads((run_dir / "epochs" / "epoch_0000" / "epoch_summary.json").read_text(encoding="utf-8"))
    rejections = json.loads((run_dir / "epochs" / "epoch_0000" / "rejections.json").read_text(encoding="utf-8"))
    assert int(summary.get("candidates_total", 0)) >= 2
    assert int(rejections["counts"].get("ELIGIBLE", 0)) >= 1
