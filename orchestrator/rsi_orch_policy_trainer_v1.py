"""Omega-dispatchable wrapper for Step5A orch policy training with v19 policy-bundle emission."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from cdel.v1_7r.canon import write_canon_json
from cdel.v18_0.omega_common_v1 import canon_hash_obj, ensure_sha256
from cdel.v19_0.common_v1 import validate_schema as validate_schema_v19

from tools.orch_worldmodel.campaign_orch_policy_trainer_v1 import CampaignError, run_campaign


def _fail(reason: str) -> None:
    raise RuntimeError(str(reason))


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("SCHEMA_FAIL") from exc
    if not isinstance(payload, dict):
        _fail("SCHEMA_FAIL")
    return payload


def _require_relpath(text: str) -> Path:
    rel = Path(str(text).strip())
    if not str(rel):
        _fail("SCHEMA_FAIL")
    if rel.is_absolute() or ".." in rel.parts:
        _fail("SCHEMA_FAIL")
    return rel


def _normalize_ranked(raw_rows: Any, *, field_name: str) -> list[dict[str, Any]]:
    if not isinstance(raw_rows, list) or not raw_rows:
        _fail("SCHEMA_FAIL")
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in raw_rows:
        if not isinstance(raw, dict):
            _fail("SCHEMA_FAIL")
        capability_id = str(raw.get("capability_id", "")).strip()
        if not capability_id or capability_id in seen:
            continue
        score_q32 = raw.get("score_q32")
        if not isinstance(score_q32, int):
            _fail("SCHEMA_FAIL")
        out.append({"capability_id": capability_id, "score_q32": int(score_q32)})
        seen.add(capability_id)
    if not out:
        _fail("SCHEMA_FAIL")
    out.sort(key=lambda row: (-int(row["score_q32"]), str(row["capability_id"])))
    return out


def _normalize_bootstrap_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if str(payload.get("schema_version", "")).strip() != "orch_policy_bootstrap_rows_v1":
        _fail("SCHEMA_FAIL")
    rows_raw = payload.get("rows")
    if not isinstance(rows_raw, list):
        _fail("SCHEMA_FAIL")
    out: list[dict[str, Any]] = []
    seen_context: set[str] = set()
    for raw in rows_raw:
        if not isinstance(raw, dict):
            _fail("SCHEMA_FAIL")
        context_key = ensure_sha256(raw.get("context_key"), reason="SCHEMA_FAIL")
        if context_key in seen_context:
            _fail("NONDETERMINISTIC")
        ranked = _normalize_ranked(raw.get("ranked_capabilities"), field_name="ranked_capabilities")
        out.append({"context_key": context_key, "ranked_capabilities": ranked})
        seen_context.add(context_key)
    out.sort(key=lambda row: str(row["context_key"]))
    return out


def _load_bootstrap_rows(*, campaign_pack: Path, pack_payload: dict[str, Any]) -> list[dict[str, Any]]:
    rel_raw = str(pack_payload.get("policy_bootstrap_rows_rel", "")).strip()
    if rel_raw:
        rel = _require_relpath(rel_raw)
        path = (campaign_pack.parent / rel).resolve()
        if not path.exists() or not path.is_file():
            _fail("MISSING_STATE_INPUT")
        return _normalize_bootstrap_rows(_load_json(path))

    default_path = (campaign_pack.parent / "orch_policy_bootstrap_rows_v1.json").resolve()
    if not default_path.exists() or not default_path.is_file():
        return []
    return _normalize_bootstrap_rows(_load_json(default_path))


def _apply_bootstrap_rows(table: dict[str, Any], bootstrap_rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not bootstrap_rows:
        return table
    rows_raw = table.get("rows")
    if not isinstance(rows_raw, list):
        _fail("SCHEMA_FAIL")

    merged_by_context: dict[str, dict[str, Any]] = {}
    for raw in rows_raw:
        if not isinstance(raw, dict):
            _fail("SCHEMA_FAIL")
        context_key = ensure_sha256(raw.get("context_key"), reason="SCHEMA_FAIL")
        ranked = _normalize_ranked(raw.get("ranked_capabilities"), field_name="ranked_capabilities")
        merged_by_context[context_key] = {"context_key": context_key, "ranked_capabilities": ranked}

    for row in bootstrap_rows:
        context_key = ensure_sha256(row.get("context_key"), reason="SCHEMA_FAIL")
        ranked = _normalize_ranked(row.get("ranked_capabilities"), field_name="ranked_capabilities")
        merged_by_context[context_key] = {"context_key": context_key, "ranked_capabilities": ranked}

    merged_rows = [merged_by_context[key] for key in sorted(merged_by_context.keys())]
    table_no_id = {
        "schema_version": "orch_policy_table_v1",
        "rows": merged_rows,
    }
    table_id = str(canon_hash_obj(table_no_id))
    out = dict(table_no_id)
    out["policy_table_id"] = table_id
    validate_schema_v19(out, "orch_policy_table_v1")
    return out


def _policy_table_v19_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    schema = str(payload.get("schema_version", "")).strip()
    if schema != "orch_policy_table_v1":
        _fail("SCHEMA_FAIL")

    # New-form policy table: keep semantics but normalize IDs deterministically.
    if "policy_table_id" in payload and "rows" in payload:
        rows_raw = payload.get("rows")
        if not isinstance(rows_raw, list) or not rows_raw:
            _fail("SCHEMA_FAIL")
        rows: list[dict[str, Any]] = []
        seen_context: set[str] = set()
        for raw in rows_raw:
            if not isinstance(raw, dict):
                _fail("SCHEMA_FAIL")
            context_key = ensure_sha256(raw.get("context_key"), reason="SCHEMA_FAIL")
            if context_key in seen_context:
                _fail("NONDETERMINISTIC")
            ranked = _normalize_ranked(raw.get("ranked_capabilities"), field_name="ranked_capabilities")
            rows.append({"context_key": context_key, "ranked_capabilities": ranked})
            seen_context.add(context_key)
        rows.sort(key=lambda row: str(row["context_key"]))
        table_no_id = {
            "schema_version": "orch_policy_table_v1",
            "rows": rows,
        }
        table_id = str(canon_hash_obj(table_no_id))
        table = dict(table_no_id)
        table["policy_table_id"] = table_id
        validate_schema_v19(table, "orch_policy_table_v1")
        return table

    # Legacy-form policy table from Step5A trainer.
    if "policy_id" in payload and "context_rows" in payload:
        policy_id = ensure_sha256(payload.get("policy_id"), reason="SCHEMA_FAIL")
        legacy_no_id = dict(payload)
        legacy_no_id.pop("policy_id", None)
        if str(canon_hash_obj(legacy_no_id)) != policy_id:
            _fail("NONDETERMINISTIC")

        context_rows_raw = payload.get("context_rows")
        if not isinstance(context_rows_raw, list) or not context_rows_raw:
            _fail("SCHEMA_FAIL")
        rows: list[dict[str, Any]] = []
        seen_context: set[str] = set()
        for raw in context_rows_raw:
            if not isinstance(raw, dict):
                _fail("SCHEMA_FAIL")
            context_key = ensure_sha256(raw.get("context_key"), reason="SCHEMA_FAIL")
            if context_key in seen_context:
                _fail("NONDETERMINISTIC")
            ranked = _normalize_ranked(raw.get("ranked_actions"), field_name="ranked_actions")
            rows.append({"context_key": context_key, "ranked_capabilities": ranked})
            seen_context.add(context_key)
        rows.sort(key=lambda row: str(row["context_key"]))

        table_no_id = {
            "schema_version": "orch_policy_table_v1",
            "rows": rows,
        }
        table_id = str(canon_hash_obj(table_no_id))
        table = dict(table_no_id)
        table["policy_table_id"] = table_id
        validate_schema_v19(table, "orch_policy_table_v1")
        return table

    _fail("SCHEMA_FAIL")
    return {}


def _build_bundle_from_table(table: dict[str, Any]) -> dict[str, Any]:
    table_id = ensure_sha256(table.get("policy_table_id"), reason="SCHEMA_FAIL")
    table_no_id = dict(table)
    table_no_id.pop("policy_table_id", None)
    if str(canon_hash_obj(table_no_id)) != table_id:
        _fail("NONDETERMINISTIC")

    bundle_no_id = {
        "schema_version": "orch_policy_bundle_v1",
        "policy_table_id": table_id,
        "policy_table": dict(table),
    }
    bundle_id = str(canon_hash_obj(bundle_no_id))
    bundle = dict(bundle_no_id)
    bundle["policy_bundle_id"] = bundle_id
    validate_schema_v19(bundle, "orch_policy_bundle_v1")
    return bundle


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="rsi_orch_policy_trainer_v1")
    parser.add_argument("--campaign_pack", required=True)
    parser.add_argument("--out_dir", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    campaign_pack = Path(str(args.campaign_pack)).resolve()
    out_dir = Path(str(args.out_dir)).resolve()

    pack = _load_json(campaign_pack)
    if str(pack.get("schema_version", "")).strip() != "rsi_orch_policy_trainer_pack_v1":
        _fail("SCHEMA_FAIL")
    output_dir_rel = _require_relpath(str(pack.get("output_dir_rel", "")))
    campaign_state_dir = (out_dir / output_dir_rel).resolve()

    try:
        campaign_summary = run_campaign(
            campaign_pack=campaign_pack,
            out_dir=out_dir,
            ek_id=None,
            kernel_ledger_id=None,
        )
    except CampaignError as exc:
        _fail(str(exc))

    policy_table_path = Path(str(campaign_summary.get("policy_table_path", ""))).resolve()
    if not policy_table_path.exists() or not policy_table_path.is_file():
        _fail("MISSING_STATE_INPUT")

    table_payload = _load_json(policy_table_path)
    policy_table_v19 = _policy_table_v19_from_payload(table_payload)
    bootstrap_rows = _load_bootstrap_rows(campaign_pack=campaign_pack, pack_payload=pack)
    policy_table_v19 = _apply_bootstrap_rows(policy_table_v19, bootstrap_rows)
    bundle_payload = _build_bundle_from_table(policy_table_v19)
    bundle_id = ensure_sha256(bundle_payload.get("policy_bundle_id"), reason="SCHEMA_FAIL")

    promotion_dir = campaign_state_dir / "promotion"
    promotion_dir.mkdir(parents=True, exist_ok=True)
    bundle_name = f"sha256_{bundle_id.split(':', 1)[1]}.orch_policy_bundle_v1.json"
    bundle_path = promotion_dir / bundle_name
    write_canon_json(bundle_path, bundle_payload)

    write_canon_json(campaign_state_dir / "candidate.orch_policy_bundle_v1.json", bundle_payload)

    dispatch_summary = {
        "schema_version": "orch_policy_trainer_dispatch_summary_v1",
        "status": "OK",
        "reason_code": "OK",
        "policy_bundle_id": bundle_id,
        "policy_bundle_relpath": str(bundle_path.relative_to(out_dir)),
        "policy_table_id": str(policy_table_v19.get("policy_table_id", "")),
        "bootstrap_rows_applied_u64": int(len(bootstrap_rows)),
        "trainer_summary": dict(campaign_summary),
    }
    write_canon_json(campaign_state_dir / "orch_policy_trainer_dispatch_summary_v1.json", dispatch_summary)

    sys.stdout.write(json.dumps(dispatch_summary, sort_keys=True, separators=(",", ":")) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
