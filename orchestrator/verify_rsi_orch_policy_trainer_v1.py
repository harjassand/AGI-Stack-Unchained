"""Fail-closed subverifier for rsi_orch_policy_trainer_v1 artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from cdel.v18_0.omega_common_v1 import canon_hash_obj, ensure_sha256
from cdel.v19_0.common_v1 import validate_schema as validate_schema_v19


def _invalid(reason: str) -> int:
    sys.stdout.write(f"INVALID:{reason}\n")
    return 1


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("SCHEMA_FAIL") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("SCHEMA_FAIL")
    return payload


def _verify_bundle_hashes(bundle: dict[str, Any]) -> str:
    validate_schema_v19(bundle, "orch_policy_bundle_v1")
    bundle_id = ensure_sha256(bundle.get("policy_bundle_id"), reason="SCHEMA_FAIL")
    bundle_no_id = dict(bundle)
    bundle_no_id.pop("policy_bundle_id", None)
    if str(canon_hash_obj(bundle_no_id)) != bundle_id:
        raise RuntimeError("NONDETERMINISTIC")

    table_raw = bundle.get("policy_table")
    if not isinstance(table_raw, dict):
        raise RuntimeError("SCHEMA_FAIL")
    table = dict(table_raw)
    validate_schema_v19(table, "orch_policy_table_v1")
    table_id = ensure_sha256(table.get("policy_table_id"), reason="SCHEMA_FAIL")
    declared_table_id = ensure_sha256(bundle.get("policy_table_id"), reason="SCHEMA_FAIL")
    if table_id != declared_table_id:
        raise RuntimeError("NONDETERMINISTIC")

    table_no_id = dict(table)
    table_no_id.pop("policy_table_id", None)
    if str(canon_hash_obj(table_no_id)) != table_id:
        raise RuntimeError("NONDETERMINISTIC")

    return bundle_id


def _resolve_state_dir(path: Path) -> Path:
    root = path.resolve()
    candidates = [
        root,
        root / "orch_policy_trainer_v1",
    ]
    for candidate in candidates:
        if (candidate / "orch_policy_trainer_campaign_summary_v1.json").exists():
            return candidate
    raise RuntimeError("MISSING_STATE_INPUT")


def _verify(state_dir: Path) -> None:
    campaign_summary_path = state_dir / "orch_policy_trainer_campaign_summary_v1.json"
    if not campaign_summary_path.exists() or not campaign_summary_path.is_file():
        raise RuntimeError("MISSING_STATE_INPUT")

    campaign_summary = _load_json(campaign_summary_path)
    if str(campaign_summary.get("schema_version", "")).strip() != "orch_policy_trainer_campaign_summary_v1":
        raise RuntimeError("SCHEMA_FAIL")

    dispatch_summary_path = state_dir / "orch_policy_trainer_dispatch_summary_v1.json"
    if not dispatch_summary_path.exists() or not dispatch_summary_path.is_file():
        raise RuntimeError("MISSING_STATE_INPUT")
    dispatch_summary = _load_json(dispatch_summary_path)
    if str(dispatch_summary.get("schema_version", "")).strip() != "orch_policy_trainer_dispatch_summary_v1":
        raise RuntimeError("SCHEMA_FAIL")

    promotion_dir = state_dir / "promotion"
    if not promotion_dir.exists() or not promotion_dir.is_dir():
        raise RuntimeError("MISSING_STATE_INPUT")
    candidates = sorted(promotion_dir.glob("sha256_*.orch_policy_bundle_v1.json"), key=lambda row: row.as_posix())
    if len(candidates) != 1:
        raise RuntimeError("NONDETERMINISTIC")

    bundle = _load_json(candidates[0])
    bundle_id = _verify_bundle_hashes(bundle)
    summary_bundle_id = ensure_sha256(dispatch_summary.get("policy_bundle_id"), reason="SCHEMA_FAIL")
    if bundle_id != summary_bundle_id:
        raise RuntimeError("NONDETERMINISTIC")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="verify_rsi_orch_policy_trainer_v1")
    parser.add_argument("--mode", required=True, choices=["full", "fast"])
    parser.add_argument("--state_dir", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        state_dir = _resolve_state_dir(Path(str(args.state_dir)))
        _verify(state_dir)
    except Exception as exc:  # noqa: BLE001
        reason = str(exc).strip().upper() or "VERIFY_ERROR"
        if reason.startswith("INVALID:"):
            reason = reason.split(":", 1)[1].strip()
        if not reason:
            reason = "VERIFY_ERROR"
        return _invalid(reason)

    sys.stdout.write("VALID\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
