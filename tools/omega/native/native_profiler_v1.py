#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import importlib


def _canon_bytes(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha256_prefixed(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _load_json(path: Path) -> dict[str, Any]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise RuntimeError("SCHEMA_FAIL")
    return obj


def _load_policy_registry(repo_root: Path) -> dict[str, Any]:
    path = repo_root / "orchestrator" / "native" / "native_policy_registry_v1.json"
    obj = _load_json(path)
    if obj.get("schema_version") != "omega_native_policy_registry_v1":
        raise RuntimeError("SCHEMA_FAIL")
    return obj


def _import_callable(spec: str):
    mod_name, _, attr = spec.partition(":")
    if not mod_name or not attr:
        raise RuntimeError("SCHEMA_FAIL")
    mod = importlib.import_module(mod_name)
    fn = getattr(mod, attr, None)
    if not callable(fn):
        raise RuntimeError("SCHEMA_FAIL")
    return fn


def _py_impl_import_for_op(*, repo_root: Path, op_id: str) -> str:
    reg = _load_policy_registry(repo_root)
    ops = reg.get("ops")
    if not isinstance(ops, list):
        raise RuntimeError("SCHEMA_FAIL")
    for row in ops:
        if isinstance(row, dict) and str(row.get("op_id", "")).strip() == op_id:
            spec = row.get("py_impl_import")
            if isinstance(spec, str) and spec.strip():
                return spec
    raise RuntimeError("UNKNOWN_OP")


def _hex_to_bytes(hexstr: str) -> bytes:
    s = str(hexstr).strip()
    if s == "":
        return b""
    return bytes.fromhex(s)


def profile_pinned_workload(
    *,
    repo_root: Path,
    pinned_workload: dict[str, Any],
    candidate_ops: list[str],
) -> dict[str, Any]:
    workload_id = str(pinned_workload.get("workload_id", "")).strip() or "pinned_workload"
    cases = pinned_workload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise RuntimeError("SCHEMA_FAIL")

    results: list[dict[str, Any]] = []
    for op_id in candidate_ops:
        py_spec = _py_impl_import_for_op(repo_root=repo_root, op_id=op_id)
        fn = _import_callable(py_spec)

        calls = 0
        bytes_in = 0
        for case in cases:
            if not isinstance(case, dict):
                raise RuntimeError("SCHEMA_FAIL")
            argv_hex = case.get("argv_hex")
            reps = int(case.get("repeat_u32", 1) or 1)
            if not isinstance(argv_hex, list) or reps <= 0:
                raise RuntimeError("SCHEMA_FAIL")
            argv = [_hex_to_bytes(x) for x in argv_hex]
            for _ in range(reps):
                _ = fn(*argv)
                calls += 1
                bytes_in += sum(len(a) for a in argv)

        # Phase 1 scoring: deterministic, simple.
        score = int(calls) * int(bytes_in)
        results.append(
            {
                "op_id": op_id,
                "calls_u64": int(calls),
                "bytes_in_u64": int(bytes_in),
                "score_u64": int(score),
            }
        )

    results.sort(key=lambda r: (int(r["score_u64"]), r["op_id"]))
    results.reverse()
    selected = results[0]["op_id"] if results else None

    report_wo_id = {
        "schema_version": "omega_native_hotspot_report_v1",
        "report_id": "sha256:" + ("0" * 64),
        "pinned_workload_id": workload_id,
        "ops": results,
        "selected_op_id": selected,
    }
    report = dict(report_wo_id)
    report["report_id"] = _sha256_prefixed(_canon_bytes({k: v for k, v in report.items() if k != "report_id"}))
    return report


def main() -> None:
    ap = argparse.ArgumentParser(prog="native_profiler_v1")
    ap.add_argument("--pinned_workload_json", required=True)
    ap.add_argument("--candidate_op", action="append", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parents[3]
    pinned = _load_json(Path(args.pinned_workload_json).resolve())
    report = profile_pinned_workload(
        repo_root=repo_root,
        pinned_workload=pinned,
        candidate_ops=[str(x) for x in args.candidate_op],
    )
    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(_canon_bytes(report))
    print(json.dumps({"status": "OK", "report_id": report["report_id"], "selected_op_id": report["selected_op_id"]}, separators=(",", ":")))


if __name__ == "__main__":
    main()
