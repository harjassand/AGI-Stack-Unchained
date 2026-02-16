from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from cdel.v1_7r.canon import load_canon_json, write_canon_json


def test_ge_symbiotic_optimizer_emits_deterministic_ccap(tmp_path: Path) -> None:
    strategy = {
        "schema_version": "ge_symbiotic_strategy_v0_2",
        "target_relpath": "tools/omega/omega_benchmark_suite_v1.py",
        "build_recipe_name": "REPO_TESTS_FAST",
        "llm_trace": [
            {"prompt": "optimize stage ladder", "response": "prefer deterministic fast path"},
            {"prompt": "suggest patch", "response": "append inert marker comment"},
        ],
    }
    strategy_path = tmp_path / "strategy.json"
    write_canon_json(strategy_path, strategy)

    tool = Path(__file__).resolve().parents[1] / "ge_symbiotic_optimizer_v0_2.py"

    def _run(out_dir: Path) -> dict[str, object]:
        cmd = [
            sys.executable,
            str(tool),
            "--subrun_out_dir",
            str(out_dir),
            "--strategy_config",
            str(strategy_path),
            "--seed",
            "7",
            "--model_id",
            "ge-v0_2-test",
            "--max_ccaps",
            "1",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)

    out_a = tmp_path / "out_a"
    out_b = tmp_path / "out_b"
    run_a = _run(out_a)
    run_b = _run(out_b)

    assert run_a["status"] == "OK"
    assert run_a["inputs_hash"] == run_b["inputs_hash"]
    assert run_a["ccap_count_u64"] == 1

    fp_a = load_canon_json(out_a / "ge_run_inputs_fingerprint_v1.json")
    fp_b = load_canon_json(out_b / "ge_run_inputs_fingerprint_v1.json")
    assert fp_a == fp_b

    sum_a = load_canon_json(out_a / "ge_symbiotic_optimizer_summary_v0_2.json")
    sum_b = load_canon_json(out_b / "ge_symbiotic_optimizer_summary_v0_2.json")
    assert sum_a["ccaps"] == sum_b["ccaps"]

    ccap_rel = sum_a["ccaps"][0]["ccap_relpath"]
    patch_rel = sum_a["ccaps"][0]["patch_relpath"]
    assert (out_a / ccap_rel).read_bytes() == (out_b / ccap_rel).read_bytes()
    assert (out_a / patch_rel).read_bytes() == (out_b / patch_rel).read_bytes()

    hashes_a = load_canon_json(out_a / "ge_prompt_response_hashes_v1.json")
    assert hashes_a["inputs_hash"] == fp_a["inputs_hash"]
    assert len(hashes_a["rows"]) == 2
