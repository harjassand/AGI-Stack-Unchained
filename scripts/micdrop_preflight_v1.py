#!/usr/bin/env python3
"""Micdrop preflight checks."""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
for entry in (REPO_ROOT, REPO_ROOT / "CDEL-v2"):
    text = str(entry)
    if text not in sys.path:
        sys.path.insert(0, text)

from cdel.v18_0.authority.authority_hash_v1 import auth_hash, load_authority_pins
from cdel.v18_0.omega_common_v1 import canon_hash_obj
from cdel.v19_0.common_v1 import validate_schema as validate_schema_v19


def _fail(msg: str, *, code: int = 1) -> int:
    print(msg)
    return code


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"payload is not object: {path}")
    return payload


def _verify_pack(pack_id: str) -> Path:
    if not isinstance(pack_id, str) or not pack_id.startswith("sha256:"):
        raise RuntimeError(f"invalid pack id: {pack_id!r}")
    pack_path = REPO_ROOT / "authority" / "holdouts" / "packs" / f"sha256_{pack_id.split(':', 1)[1]}.json"
    if not pack_path.exists() or not pack_path.is_file():
        raise RuntimeError(f"missing pack file: {pack_path.as_posix()}")
    payload = _load_json(pack_path)
    if "pack_id" in payload:
        declared = str(payload.get("pack_id", "")).strip()
        payload_no_id = dict(payload)
        payload_no_id.pop("pack_id", None)
        observed = canon_hash_obj(payload_no_id)
        if declared != observed:
            raise RuntimeError(f"declared pack_id mismatch: {pack_path.as_posix()}")
        if declared != pack_id:
            raise RuntimeError(f"pack id mismatch in store: {pack_path.as_posix()}")
    else:
        observed = canon_hash_obj(payload)
        if observed != pack_id:
            raise RuntimeError(f"pack hash mismatch in store: {pack_path.as_posix()}")
    return pack_path


def main() -> int:
    pins_rel = str(os.environ.get("OMEGA_AUTHORITY_PINS_REL", "")).strip()
    allowlists_rel = str(os.environ.get("OMEGA_CCAP_PATCH_ALLOWLISTS_REL", "")).strip()

    if not pins_rel:
        return _fail("OMEGA_AUTHORITY_PINS_REL is not set")
    if not allowlists_rel:
        return _fail("OMEGA_CCAP_PATCH_ALLOWLISTS_REL is not set")

    pins_path = (REPO_ROOT / pins_rel).resolve()
    allowlists_path = (REPO_ROOT / allowlists_rel).resolve()
    if not pins_path.exists() or not pins_path.is_file():
        return _fail(f"missing authority pins file: {pins_path.as_posix()}")
    if not allowlists_path.exists() or not allowlists_path.is_file():
        return _fail(f"missing ccap allowlists file: {allowlists_path.as_posix()}")

    try:
        pins = load_authority_pins(REPO_ROOT)
        auth_hash_value = auth_hash(pins)
    except Exception as exc:  # noqa: BLE001
        return _fail(f"failed loading authority pins/auth_hash: {exc}")

    suite_paths = [
        REPO_ROOT / "authority" / "benchmark_suites" / "micdrop_math_suite_v1.json",
        REPO_ROOT / "authority" / "benchmark_suites" / "micdrop_algo_suite_v1.json",
        REPO_ROOT / "authority" / "benchmark_suites" / "micdrop_logic_suite_v1.json",
        REPO_ROOT / "authority" / "benchmark_suites" / "micdrop_planning_suite_v1.json",
    ]

    required_packs: set[str] = set()
    try:
        for suite_path in suite_paths:
            if not suite_path.exists() or not suite_path.is_file():
                raise RuntimeError(f"missing suite manifest: {suite_path.as_posix()}")
            suite_payload = _load_json(suite_path)
            validate_schema_v19(suite_payload, "benchmark_suite_manifest_v1")
            inputs_pack_id = str(suite_payload.get("inputs_pack_id", "")).strip()
            labels_pack_id = str(suite_payload.get("labels_pack_id", "")).strip()
            hidden_pack_id = str(suite_payload.get("hidden_tests_pack_id", "")).strip()
            if inputs_pack_id:
                required_packs.add(inputs_pack_id)
            if labels_pack_id:
                required_packs.add(labels_pack_id)
            if hidden_pack_id:
                required_packs.add(hidden_pack_id)
        pack_paths = [_verify_pack(pack_id) for pack_id in sorted(required_packs)]
    except Exception as exc:  # noqa: BLE001
        return _fail(str(exc))

    runner_path = REPO_ROOT / "tools" / "omega" / "agi_micdrop_candidate_runner_v1.py"
    if not runner_path.exists() or not runner_path.is_file():
        return _fail(f"missing candidate runner: {runner_path.as_posix()}")

    if shutil.which("sandbox-exec") is None:
        return _fail("SANDBOX_MISSING")

    summary = {
        "schema_version": "MICDROP_PREFLIGHT_SUMMARY_v1",
        "authority_pins_rel": pins_rel,
        "ccap_patch_allowlists_rel": allowlists_rel,
        "auth_hash": str(auth_hash_value),
        "pinned_ids": {
            "active_ek_id": str(pins.get("active_ek_id", "")),
            "anchor_suite_set_id": str(pins.get("anchor_suite_set_id", "")),
            "active_kernel_extensions_ledger_id": str(pins.get("active_kernel_extensions_ledger_id", "")),
            "holdout_policy_id": str(pins.get("holdout_policy_id", "")),
            "ccap_patch_allowlists_id": str(pins.get("ccap_patch_allowlists_id", "")),
            "suite_runner_id": str(pins.get("suite_runner_id", "")),
        },
        "suite_manifest_relpaths": [path.relative_to(REPO_ROOT).as_posix() for path in suite_paths],
        "required_pack_ids": sorted(required_packs),
        "required_pack_relpaths": [path.relative_to(REPO_ROOT).as_posix() for path in pack_paths],
    }
    print(json.dumps(summary, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
