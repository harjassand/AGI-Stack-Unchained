#!/usr/bin/env python3
"""Meta-verify EK upgrades: old EK judges new EK over pinned corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def _canon_bytes(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha256_prefixed(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("SCHEMA_FAIL")
    return payload


def _ek_id(payload: dict[str, Any]) -> str:
    return _sha256_prefixed(_canon_bytes(payload))


def _gate_mapping_check(old_ek: dict[str, Any], new_ek: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    old_stages = [str(row.get("stage_name", "")) for row in old_ek.get("stages", []) if isinstance(row, dict)]
    new_stages = [str(row.get("stage_name", "")) for row in new_ek.get("stages", []) if isinstance(row, dict)]
    if old_stages == new_stages:
        return True, {"status": "PASS", "mode": "equal", "old_stages": old_stages, "new_stages": new_stages}
    if len(new_stages) >= len(old_stages) and new_stages[: len(old_stages)] == old_stages:
        return True, {"status": "PASS", "mode": "monotone_extension", "old_stages": old_stages, "new_stages": new_stages}
    return False, {"status": "FAIL", "mode": "incompatible", "old_stages": old_stages, "new_stages": new_stages}


def _load_boundary_set(repo_root: Path, set_id: str) -> set[str] | None:
    root = repo_root / "authority" / "boundary_event_sets"
    if not root.exists() or not root.is_dir():
        return None
    for path in sorted(root.glob("*.json"), key=lambda row: row.as_posix()):
        try:
            payload = _load_json(path)
        except Exception:  # noqa: BLE001
            continue
        if str(payload.get("set_id", "")) != set_id:
            continue
        events = payload.get("events")
        if not isinstance(events, list):
            continue
        return {str(row) for row in events}
    return None


def _boundary_coverage_check(*, repo_root: Path, old_ek: dict[str, Any], new_ek: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    old_id = str(old_ek.get("boundary_event_set_id", ""))
    new_id = str(new_ek.get("boundary_event_set_id", ""))
    old_set = _load_boundary_set(repo_root, old_id)
    new_set = _load_boundary_set(repo_root, new_id)
    if old_set is None or new_set is None:
        ok = old_id == new_id
        return ok, {
            "status": "PASS" if ok else "FAIL",
            "mode": "id_only",
            "old_id": old_id,
            "new_id": new_id,
            "coverage_non_decrease_b": ok,
        }
    ok = old_set.issubset(new_set)
    return ok, {
        "status": "PASS" if ok else "FAIL",
        "mode": "set_compare",
        "old_count_u64": len(old_set),
        "new_count_u64": len(new_set),
        "coverage_non_decrease_b": ok,
    }


def _obs_canon_stability_check(*, golden_runs_root: Path, old_ek: dict[str, Any], new_ek: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    old_obs_canon_id = str(old_ek.get("obs_canon_id", ""))
    new_obs_canon_id = str(new_ek.get("obs_canon_id", ""))
    canon_id_equal = old_obs_canon_id == new_obs_canon_id

    unstable = 0
    checked = 0
    for path in sorted(golden_runs_root.rglob("*omega_observation_report_v1.json"), key=lambda row: row.as_posix()):
        checked += 1
        raw = path.read_bytes()
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:  # noqa: BLE001
            unstable += 1
            continue
        if _canon_bytes(payload) != raw.rstrip(b"\n"):
            unstable += 1
    ok = canon_id_equal and unstable == 0
    return ok, {
        "status": "PASS" if ok else "FAIL",
        "obs_canon_id_equal_b": canon_id_equal,
        "files_checked_u64": checked,
        "unstable_files_u64": unstable,
    }


def _build_receipt(
    *,
    old_ek: dict[str, Any],
    new_ek: dict[str, Any],
    gate_check: tuple[bool, dict[str, Any]],
    boundary_check: tuple[bool, dict[str, Any]],
    obs_check: tuple[bool, dict[str, Any]],
) -> dict[str, Any]:
    ok = bool(gate_check[0] and boundary_check[0] and obs_check[0])
    reasons: list[str] = []
    if not gate_check[0]:
        reasons.append("GATE_MAPPING_FAIL")
    if not boundary_check[0]:
        reasons.append("BOUNDARY_COVERAGE_DECREASE")
    if not obs_check[0]:
        reasons.append("OBS_CANON_STABILITY_FAIL")
    receipt_wo_id = {
        "schema_version": "ek_meta_verify_receipt_v1",
        "old_ek_id": _ek_id(old_ek),
        "new_ek_id": _ek_id(new_ek),
        "result": {
            "status": "PASS" if ok else "FAIL",
            "reason_codes": reasons,
        },
        "checks": {
            "gate_mapping": gate_check[1],
            "boundary_coverage": boundary_check[1],
            "obs_canonical_stability": obs_check[1],
        },
    }
    receipt = dict(receipt_wo_id)
    receipt["receipt_id"] = _sha256_prefixed(_canon_bytes(receipt_wo_id))
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(prog="ek_meta_verify_v1")
    parser.add_argument("--old_ek_path", required=True)
    parser.add_argument("--new_ek_path", required=True)
    parser.add_argument("--golden_runs_root", required=True)
    parser.add_argument("--out", default="ek_meta_verify_receipt_v1.json")
    args = parser.parse_args()

    old_ek_path = Path(args.old_ek_path).resolve()
    new_ek_path = Path(args.new_ek_path).resolve()
    golden_runs_root = Path(args.golden_runs_root).resolve()
    repo_root = Path(__file__).resolve().parents[2]

    old_ek = _load_json(old_ek_path)
    new_ek = _load_json(new_ek_path)
    gate_check = _gate_mapping_check(old_ek, new_ek)
    boundary_check = _boundary_coverage_check(repo_root=repo_root, old_ek=old_ek, new_ek=new_ek)
    obs_check = _obs_canon_stability_check(golden_runs_root=golden_runs_root, old_ek=old_ek, new_ek=new_ek)
    receipt = _build_receipt(
        old_ek=old_ek,
        new_ek=new_ek,
        gate_check=gate_check,
        boundary_check=boundary_check,
        obs_check=obs_check,
    )
    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(_canon_bytes(receipt))
    print(json.dumps({"status": receipt["result"]["status"], "receipt_id": receipt["receipt_id"]}, separators=(",", ":")))


if __name__ == "__main__":
    main()
