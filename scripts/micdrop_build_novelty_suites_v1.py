#!/usr/bin/env python3
"""Build per-seed micdrop novelty holdout suite manifests and suite set."""

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
from cdel.v18_0.authority.authority_hash_v1 import load_authority_pins
from cdel.v18_0.omega_common_v1 import canon_hash_obj

_SUITES = ("arith", "numbertheory", "graph", "string", "dsl")
_DEFAULT_PACKS_N = {
    "arith": 512,
    "numbertheory": 512,
    "graph": 256,
    "string": 256,
    "dsl": 256,
}
_IO_CONTRACT = {
    "predictions_relpath": "predictions.jsonl",
    "allowed_output_files": ["predictions.jsonl"],
    "max_output_files_u64": 4,
    "max_output_bytes_u64": 131072,
    "max_single_output_bytes_u64": 131072,
    "candidate_mode": "holdout_candidate",
    "min_accuracy_q32": 0,
    "min_coverage_q32": 4294967296,
}


def _ensure_u64(value: int) -> int:
    out = int(value)
    if out < 0 or out >= (1 << 64):
        raise ValueError("seed_u64 must be in [0, 2^64)")
    return out


def _parse_packs_n(raw: str) -> dict[str, int]:
    values: dict[str, int] = {}
    for token in str(raw).split(","):
        text = token.strip()
        if not text:
            continue
        if "=" not in text:
            raise ValueError("packs_n must be comma separated key=value rows")
        key, value = text.split("=", 1)
        suite = key.strip()
        if suite not in _SUITES:
            raise ValueError(f"unsupported suite in packs_n: {suite}")
        count = int(value.strip())
        if count <= 0:
            raise ValueError(f"pack count must be positive: {suite}")
        values[suite] = int(count)
    missing = [suite for suite in _SUITES if suite not in values]
    if missing:
        raise ValueError(f"packs_n missing suites: {','.join(missing)}")
    return values


def _rel(path: Path) -> str:
    return path.resolve().relative_to(_REPO_ROOT.resolve()).as_posix()


def _call_generator(*, seed_u64: int, suite: str, n: int, out_dir: Path) -> dict[str, str]:
    cmd = [
        sys.executable,
        str((_REPO_ROOT / "tools" / "omega" / "micdrop_novelty_packgen_v1.py").resolve()),
        "--seed_u64",
        str(int(seed_u64)),
        "--suite",
        str(suite),
        "--n",
        str(int(n)),
        "--out_dir",
        str(out_dir.resolve()),
    ]
    proc = subprocess.run(
        cmd,
        cwd=_REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"pack generator failed for {suite}: {detail}")
    lines = [row.strip() for row in str(proc.stdout or "").splitlines() if row.strip()]
    if not lines:
        raise RuntimeError(f"pack generator produced no output for {suite}")
    payload = json.loads(lines[-1])
    if not isinstance(payload, dict):
        raise RuntimeError(f"pack generator output malformed for {suite}")
    suite_name = str(payload.get("suite", "")).strip()
    inputs_pack_id = str(payload.get("inputs_pack_id", "")).strip()
    labels_pack_id = str(payload.get("labels_pack_id", "")).strip()
    if suite_name != suite:
        raise RuntimeError(f"pack generator suite mismatch for {suite}")
    if not inputs_pack_id.startswith("sha256:") or not labels_pack_id.startswith("sha256:"):
        raise RuntimeError(f"pack generator ids malformed for {suite}")
    return {
        "inputs_pack_id": inputs_pack_id,
        "labels_pack_id": labels_pack_id,
    }


def _manifest_for_suite(
    *,
    suite: str,
    root_prefix: str,
    inputs_pack_id: str,
    labels_pack_id: str,
) -> dict[str, Any]:
    payload_no_id: dict[str, Any] = {
        "schema_version": "benchmark_suite_manifest_v1",
        "suite_id": "sha256:" + ("0" * 64),
        "suite_name": f"{root_prefix}_{suite}",
        "suite_runner_relpath": "tools/omega/agi_micdrop_candidate_runner_v1.py",
        "visibility": "HOLDOUT",
        "inputs_pack_id": str(inputs_pack_id),
        "labels_pack_id": str(labels_pack_id),
        "labels": ["micdrop_novelty_v2", str(suite), str(root_prefix)],
        "metrics": {
            "q32_metric_ids": ["holdout_accuracy_q32", "holdout_coverage_q32"],
            "gate_ids": [
                "CANDIDATE_EXIT_ZERO",
                "IO_CONTRACT_ENFORCED",
                "HOLDOUT_ACCURACY_MIN_Q32",
                "HOLDOUT_COVERAGE_MIN_Q32",
            ],
            "public_only_b": False,
        },
        "io_contract": dict(_IO_CONTRACT),
    }
    payload = dict(payload_no_id)
    payload_no_id.pop("suite_id", None)
    payload["suite_id"] = canon_hash_obj(payload_no_id)
    return payload


def _suite_set_payload(
    *,
    root_prefix: str,
    anchor_ek_id: str,
    suite_entries: list[dict[str, Any]],
) -> dict[str, Any]:
    payload_no_id: dict[str, Any] = {
        "schema_version": "benchmark_suite_set_v1",
        "suite_set_id": "sha256:" + ("0" * 64),
        "suite_set_kind": "ANCHOR",
        "anchor_ek_id": str(anchor_ek_id),
        "suites": suite_entries,
    }
    payload = dict(payload_no_id)
    payload_no_id.pop("suite_set_id", None)
    payload["suite_set_id"] = canon_hash_obj(payload_no_id)
    return payload


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="micdrop_build_novelty_suites_v1")
    parser.add_argument("--seed_u64", type=int, required=True)
    parser.add_argument("--root_prefix", required=True)
    parser.add_argument(
        "--packs_n",
        default="arith=512,numbertheory=512,graph=256,string=256,dsl=256",
        help="Comma-separated suite counts, for example arith=512,numbertheory=512,graph=256,string=256,dsl=256",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    seed_u64 = _ensure_u64(int(args.seed_u64))
    root_prefix = str(args.root_prefix).strip()
    if not root_prefix:
        raise ValueError("root_prefix is required")
    packs_n = _parse_packs_n(str(args.packs_n))
    for suite, default_n in _DEFAULT_PACKS_N.items():
        if suite not in packs_n:
            packs_n[suite] = int(default_n)

    suites_root = (_REPO_ROOT / "authority" / "benchmark_suites").resolve()
    suite_sets_root = (_REPO_ROOT / "authority" / "benchmark_suite_sets").resolve()
    tmp_out_root = (_REPO_ROOT / "authority" / "holdouts" / "tmp" / root_prefix).resolve()
    suites_root.mkdir(parents=True, exist_ok=True)
    suite_sets_root.mkdir(parents=True, exist_ok=True)
    tmp_out_root.mkdir(parents=True, exist_ok=True)

    pins = load_authority_pins(_REPO_ROOT)
    anchor_ek_id = str(pins.get("active_ek_id", "")).strip()
    if not anchor_ek_id.startswith("sha256:"):
        raise RuntimeError("authority pins missing active_ek_id")

    suite_rows: list[dict[str, Any]] = []
    suite_ids: list[str] = []
    pack_summary: dict[str, dict[str, str]] = {}
    for ordinal, suite in enumerate(_SUITES):
        pack_ids = _call_generator(
            seed_u64=seed_u64,
            suite=suite,
            n=int(packs_n[suite]),
            out_dir=tmp_out_root / suite,
        )
        manifest = _manifest_for_suite(
            suite=suite,
            root_prefix=root_prefix,
            inputs_pack_id=pack_ids["inputs_pack_id"],
            labels_pack_id=pack_ids["labels_pack_id"],
        )
        manifest_path = suites_root / f"{root_prefix}_{suite}.json"
        write_canon_json(manifest_path, manifest)
        suite_id = str(manifest["suite_id"])
        suite_ids.append(suite_id)
        suite_rows.append(
            {
                "ordinal_u64": int(ordinal),
                "suite_id": suite_id,
                "suite_manifest_id": canon_hash_obj(manifest),
                "suite_manifest_relpath": _rel(manifest_path),
            }
        )
        pack_summary[suite] = {
            "inputs": pack_ids["inputs_pack_id"],
            "labels": pack_ids["labels_pack_id"],
        }

    suite_set = _suite_set_payload(root_prefix=root_prefix, anchor_ek_id=anchor_ek_id, suite_entries=suite_rows)
    suite_set_path = suite_sets_root / f"{root_prefix}_suite_set.json"
    write_canon_json(suite_set_path, suite_set)

    summary = {
        "seed_u64": int(seed_u64),
        "suite_set_id": str(suite_set["suite_set_id"]),
        "suite_ids": suite_ids,
        "packs": pack_summary,
    }
    print(json.dumps(summary, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
