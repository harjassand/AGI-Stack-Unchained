#!/usr/bin/env python3
"""Create oracle ladder per-seed suite manifests, suite set, and pins."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
for _entry in (_REPO_ROOT, _REPO_ROOT / "CDEL-v2"):
    _value = str(_entry)
    if _value not in sys.path:
        sys.path.insert(0, _value)

from cdel.v1_7r.canon import write_canon_json
from cdel.v18_0.omega_common_v1 import canon_hash_obj

_IO_CONTRACT = {
    "predictions_relpath": "predictions.jsonl",
    "allowed_output_files": ["predictions.jsonl"],
    "required_output_files": ["predictions.jsonl"],
    "max_output_files_u64": 4,
    "max_output_bytes_u64": 262144,
    "max_single_output_bytes_u64": 262144,
    "candidate_mode": "holdout_candidate",
    "min_accuracy_q32": 0,
    "min_coverage_q32": 4294967296,
}


def _ensure_u64(value: int) -> int:
    out = int(value)
    if out < 0 or out >= (1 << 64):
        raise ValueError("seed_u64 must be in [0, 2^64)")
    return out


def _rel(path: Path) -> str:
    return path.resolve().relative_to(_REPO_ROOT.resolve()).as_posix()


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"payload is not object: {path.as_posix()}")
    return payload


def _packgen(seed_u64: int, kind: str, n_tasks: int) -> dict[str, str]:
    cmd = [
        sys.executable,
        str((_REPO_ROOT / "tools" / "omega" / "oracle_packgen_v1.py").resolve()),
        "--seed_u64",
        str(int(seed_u64)),
        "--kind",
        str(kind),
        "--n_tasks",
        str(int(n_tasks)),
        "--out_dir",
        str((_REPO_ROOT / "authority" / "holdouts" / "packs").resolve()),
    ]
    proc = subprocess.run(cmd, cwd=_REPO_ROOT, check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"packgen failed for {kind}: {detail}")
    lines = [row.strip() for row in str(proc.stdout or "").splitlines() if row.strip()]
    if not lines:
        raise RuntimeError(f"packgen produced no output for {kind}")
    payload = json.loads(lines[-1])
    if not isinstance(payload, dict):
        raise RuntimeError(f"packgen output malformed for {kind}")
    return {
        "inputs_pack_id": str(payload.get("inputs_pack_id", "")).strip(),
        "hidden_tests_pack_id": str(payload.get("hidden_tests_pack_id", "")).strip(),
    }


def _suite_manifest(*, suite_name: str, inputs_pack_id: str, hidden_tests_pack_id: str) -> dict[str, Any]:
    payload = {
        "schema_version": "benchmark_suite_manifest_v1",
        "suite_id": "sha256:" + ("0" * 64),
        "suite_name": str(suite_name),
        "suite_runner_relpath": "tools/omega/oracle_candidate_runner_v1.py",
        "oracle_benchmark_runner_relpath": "tools/omega/omega_benchmark_suite_oracle_v1.py",
        "visibility": "HOLDOUT",
        "inputs_pack_id": str(inputs_pack_id),
        "hidden_tests_pack_id": str(hidden_tests_pack_id),
        "labels": ["oracle_ladder_v1", str(suite_name)],
        "metrics": {
            "q32_metric_ids": [
                "pass_rate_q32",
                "coverage_q32",
                "avg_ast_nodes_q32",
                "avg_eval_steps_q32",
            ],
            "gate_ids": ["CANDIDATE_EXIT_ZERO", "IO_CONTRACT_ENFORCED"],
            "public_only_b": False,
        },
        "io_contract": dict(_IO_CONTRACT),
    }
    no_id = dict(payload)
    no_id.pop("suite_id", None)
    payload["suite_id"] = canon_hash_obj(no_id)
    return payload


def _suite_set(*, anchor_ek_id: str, suites: list[dict[str, Any]]) -> dict[str, Any]:
    payload = {
        "schema_version": "benchmark_suite_set_v1",
        "suite_set_id": "sha256:" + ("0" * 64),
        "suite_set_kind": "ANCHOR",
        "anchor_ek_id": str(anchor_ek_id),
        "suites": suites,
    }
    no_id = dict(payload)
    no_id.pop("suite_set_id", None)
    payload["suite_set_id"] = canon_hash_obj(no_id)
    return payload


def _base_pins() -> dict[str, Any]:
    micdrop_path = (_REPO_ROOT / "authority" / "authority_pins_micdrop_v1.json").resolve()
    default_path = (_REPO_ROOT / "authority" / "authority_pins_v1.json").resolve()
    path = micdrop_path if micdrop_path.exists() else default_path
    return _load_json(path)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="oracle_ladder_setup_run_v1")
    parser.add_argument("--seed_u64", type=int, required=True)
    parser.add_argument("--out_root", required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    seed_u64 = _ensure_u64(int(args.seed_u64))
    out_root = Path(str(args.out_root)).resolve()
    out_root.mkdir(parents=True, exist_ok=True)

    root_prefix = f"oracle_ladder_{int(seed_u64)}"
    list_packs = _packgen(seed_u64=seed_u64, kind="list", n_tasks=256)
    string_packs = _packgen(seed_u64=seed_u64, kind="string", n_tasks=256)

    pins = _base_pins()
    anchor_ek_id = str(pins.get("active_ek_id", "")).strip()
    if not anchor_ek_id.startswith("sha256:"):
        raise RuntimeError("authority pins missing active_ek_id")

    suites_root = (_REPO_ROOT / "authority" / "benchmark_suites").resolve()
    suite_sets_root = (_REPO_ROOT / "authority" / "benchmark_suite_sets").resolve()
    suites_root.mkdir(parents=True, exist_ok=True)
    suite_sets_root.mkdir(parents=True, exist_ok=True)

    suite_rows: list[dict[str, Any]] = []
    suite_pack_rows: list[dict[str, str]] = []

    for ordinal, (kind_name, pack_ids) in enumerate(
        (
            ("list", list_packs),
            ("string", string_packs),
        ),
        start=0,
    ):
        manifest = _suite_manifest(
            suite_name=f"{root_prefix}_{kind_name}",
            inputs_pack_id=str(pack_ids["inputs_pack_id"]),
            hidden_tests_pack_id=str(pack_ids["hidden_tests_pack_id"]),
        )
        manifest_path = suites_root / f"{root_prefix}_{kind_name}.json"
        write_canon_json(manifest_path, manifest)
        suite_rows.append(
            {
                "ordinal_u64": int(ordinal),
                "suite_id": str(manifest["suite_id"]),
                "suite_manifest_id": canon_hash_obj(manifest),
                "suite_manifest_relpath": _rel(manifest_path),
            }
        )
        suite_pack_rows.append(
            {
                "suite": kind_name,
                "inputs_pack_id": str(pack_ids["inputs_pack_id"]),
                "hidden_tests_pack_id": str(pack_ids["hidden_tests_pack_id"]),
            }
        )

    suite_set_payload = _suite_set(anchor_ek_id=anchor_ek_id, suites=suite_rows)
    suite_set_path = suite_sets_root / f"{root_prefix}_suite_set.json"
    write_canon_json(suite_set_path, suite_set_payload)

    tmp_pins_root = (_REPO_ROOT / "authority" / "tmp_oracle_runs").resolve()
    tmp_pins_root.mkdir(parents=True, exist_ok=True)
    pins_payload = dict(pins)
    pins_payload["anchor_suite_set_id"] = str(suite_set_payload["suite_set_id"])
    pins_path = tmp_pins_root / f"authority_pins_oracle_ladder_{int(seed_u64)}.json"
    write_canon_json(pins_path, pins_payload)

    summary = {
        "schema_version": "oracle_ladder_setup_run_v1",
        "seed_u64": int(seed_u64),
        "suite_set_id": str(suite_set_payload["suite_set_id"]),
        "suite_set_relpath": _rel(suite_set_path),
        "pins_relpath": _rel(pins_path),
        "packs": suite_pack_rows,
        "out_root_relpath": out_root.relative_to(_REPO_ROOT).as_posix(),
    }

    write_canon_json(out_root / "ORACLE_SETUP_SUMMARY_v1.json", summary)
    print(json.dumps(summary, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
