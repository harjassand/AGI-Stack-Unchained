from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from cdel.v1_7r.canon import canon_bytes, load_canon_json, write_canon_json


def _recompute_config_id(config: dict) -> dict:
    out = copy.deepcopy(config)
    out["ge_config_id"] = "sha256:" + ("0" * 64)
    digest = hashlib.sha256(canon_bytes(out)).hexdigest()
    out["ge_config_id"] = f"sha256:{digest}"
    return out


def test_ge_bucket_nonfungible_v1(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    tool = repo_root / "tools" / "genesis_engine" / "ge_symbiotic_optimizer_v0_3.py"
    base_config = json.loads((repo_root / "tools" / "genesis_engine" / "config" / "ge_config_v1.json").read_text(encoding="utf-8"))

    cfg = copy.deepcopy(base_config)
    cfg["bucket_fracs_q32"] = {
        "opt_q32": 2147483648,
        "nov_q32": 1288490189,
        "grow_q32": 858993459,
    }
    cfg["proposal_space_patch"]["allowed_target_relpaths"] = [
        "tools/omega/omega_benchmark_suite_v1.py",
        "tools/omega/omega_overnight_runner_v1.py",
        "orchestrator/omega_v18_0/decider_v1.py",
        "tools/genesis_engine/ge_symbiotic_optimizer_v0_2.py",
        "orchestrator/common/run_invoker_v1.py",
    ]
    cfg["proposal_space_patch"]["templates"] = [
        {"template_id": "COMMENT_APPEND", "bucket": "opt"},
        {"template_id": "COMMENT_APPEND", "bucket": "nov"},
        {"template_id": "UNSUPPORTED_TEMPLATE", "bucket": "grow"},
    ]
    cfg = _recompute_config_id(cfg)

    config_path = tmp_path / "ge_config_custom.json"
    write_canon_json(config_path, cfg)

    runs_root = tmp_path / "runs"
    runs_root.mkdir(parents=True, exist_ok=True)

    out_dir = tmp_path / "out"
    cmd = [
        sys.executable,
        str(tool),
        "--subrun_out_dir",
        str(out_dir),
        "--ge_config_path",
        str(config_path),
        "--authority_pins_path",
        str(repo_root / "authority" / "authority_pins_v1.json"),
        "--recent_runs_root",
        str(runs_root),
        "--seed",
        "9",
        "--model_id",
        "ge-v0_3-buckets",
        "--max_ccaps",
        "6",
    ]
    result = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr

    summary = load_canon_json(out_dir / "ge_symbiotic_optimizer_summary_v0_3.json")
    assert summary["bucket_plan"] == {"opt_u64": 4, "nov_u64": 1, "grow_u64": 1}

    buckets = [str(row.get("bucket", "")) for row in summary.get("ccaps", [])]
    assert buckets.count("grow") == 0
    assert len(buckets) == 5
