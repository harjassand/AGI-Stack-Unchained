from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from cdel.v1_7r.canon import canon_bytes, load_canon_json, sha256_prefixed
from cdel.v13_0.sas_science_eval_v1 import compute_report_hash

from .utils import DEFAULT_DT, DEFAULT_STEPS, REPO_ROOT, run_campaign, simulate_powerlaw


def _canon_hash(path: Path) -> str:
    return sha256_prefixed(canon_bytes(load_canon_json(path)))


def _python_env() -> dict[str, str]:
    env = os.environ.copy()
    cdel_root = REPO_ROOT / "CDEL-v2"
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(cdel_root) + (os.pathsep + existing if existing else "")
    return env


def test_sealed_eval_worker_matches_cli_single_job(tmp_path: Path) -> None:
    positions = {
        "BodyA": simulate_powerlaw(
            p=3,
            mu=1.0,
            dt=DEFAULT_DT,
            steps=DEFAULT_STEPS,
            x0=1.0,
            y0=0.0,
            vx0=0.0,
            vy0=0.8,
        ),
        "BodyB": simulate_powerlaw(
            p=3,
            mu=1.0,
            dt=DEFAULT_DT,
            steps=DEFAULT_STEPS,
            x0=1.4,
            y0=0.0,
            vx0=0.0,
            vy0=0.65,
        ),
    }
    state = run_campaign(tmp_path=tmp_path, positions=positions)

    state_dir = state.state_dir
    config_dir = state.run_root / "config"
    manifest_path = next(state_dir.glob("data/manifest/sha256_*.sas_science_dataset_manifest_v1.json"))
    csv_path = next(state_dir.glob("data/csv/sha256_*.dataset.csv"))
    dataset_receipt_path = next(state_dir.glob("data/receipts/sha256_*.sas_science_dataset_receipt_v1.json"))
    split_receipt_path = next(state_dir.glob("data/receipts/sha256_*.sas_science_split_receipt_v1.json"))

    selected_theory_id = str(state.result["selected_theory_id"])
    theory_ir_path = state_dir / "theory" / "ir" / f"sha256_{selected_theory_id.split(':',1)[1]}.sas_science_theory_ir_v1.json"

    fit_receipt_path = Path()
    for candidate in sorted((state_dir / "fit" / "receipts").glob("sha256_*.sas_science_fit_receipt_v1.json")):
        payload = load_canon_json(candidate)
        if isinstance(payload, dict) and payload.get("theory_id") == selected_theory_id:
            fit_receipt_path = candidate
            break
    assert fit_receipt_path.exists()

    suitepack_path = config_dir / "sas_science_suitepack_dev_v1.json"
    perf_policy_path = config_dir / "sas_science_perf_policy_v1.json"
    ir_policy_path = config_dir / "sas_science_ir_policy_v1.json"

    out_eval = tmp_path / "cli_eval.json"
    out_sealed = tmp_path / "cli_sealed.json"
    cli_cmd = [
        sys.executable,
        "-m",
        "cdel.v13_0.sealed_science_eval_v1",
        "--dataset_manifest",
        str(manifest_path),
        "--dataset_csv",
        str(csv_path),
        "--dataset_receipt",
        str(dataset_receipt_path),
        "--split_receipt",
        str(split_receipt_path),
        "--theory_ir",
        str(theory_ir_path),
        "--fit_receipt",
        str(fit_receipt_path),
        "--suitepack",
        str(suitepack_path),
        "--perf_policy",
        str(perf_policy_path),
        "--ir_policy",
        str(ir_policy_path),
        "--eval_kind",
        "DEV",
        "--out_eval",
        str(out_eval),
        "--out_sealed",
        str(out_sealed),
    ]
    cli_result = subprocess.run(
        cli_cmd,
        capture_output=True,
        text=True,
        check=False,
        env=_python_env(),
        cwd=REPO_ROOT,
    )
    assert cli_result.returncode == 0

    cli_eval = load_canon_json(out_eval)
    cli_sealed = load_canon_json(out_sealed)
    assert isinstance(cli_eval, dict)
    assert isinstance(cli_sealed, dict)

    job = {
        "schema_version": "sealed_science_eval_job_v1",
        "dataset_manifest": str(manifest_path),
        "dataset_csv": str(csv_path),
        "dataset_receipt": str(dataset_receipt_path),
        "split_receipt": str(split_receipt_path),
        "theory_ir": str(theory_ir_path),
        "fit_receipt": str(fit_receipt_path),
        "suitepack": str(suitepack_path),
        "perf_policy": str(perf_policy_path),
        "ir_policy": str(ir_policy_path),
        "eval_kind": "DEV",
        "lease": None,
        "cache_keys": {
            "dataset_manifest_hash": _canon_hash(manifest_path),
            "dataset_csv_hash": sha256_prefixed(csv_path.read_bytes()),
            "dataset_receipt_hash": _canon_hash(dataset_receipt_path),
            "split_receipt_hash": _canon_hash(split_receipt_path),
            "suitepack_hash": _canon_hash(suitepack_path),
            "perf_policy_hash": _canon_hash(perf_policy_path),
            "ir_policy_hash": _canon_hash(ir_policy_path),
        },
    }

    proc = subprocess.Popen(
        [sys.executable, "-m", "cdel.v13_0.sealed_science_eval_worker_v1", "--mode", "worker"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        env=_python_env(),
        cwd=REPO_ROOT,
    )
    try:
        assert proc.stdin is not None
        assert proc.stdout is not None
        proc.stdin.write(json.dumps(job, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n")
        proc.stdin.flush()
        response_line = proc.stdout.readline()
        assert response_line
        response = json.loads(response_line)
        assert isinstance(response, dict)
    finally:
        if proc.stdin is not None and not proc.stdin.closed:
            proc.stdin.close()

    rc = proc.wait(timeout=5)
    assert rc == 0

    assert response["schema_version"] == "sealed_science_eval_result_v1"
    assert response["eval_report"] == cli_eval
    assert response["sealed_receipt"] == cli_sealed
    assert response["eval_report_hash"] == compute_report_hash(cli_eval)
    assert response["sealed_receipt_hash"] == sha256_prefixed(canon_bytes(cli_sealed))
    assert int(response["work_cost_total"]) == int(cli_eval["workmeter"]["work_cost_total"])
