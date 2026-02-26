#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _entry in (_REPO_ROOT, _REPO_ROOT / "CDEL-v2"):
    _value = str(_entry)
    if _value not in sys.path:
        sys.path.insert(0, _value)


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("SCHEMA_FAIL")
    return payload


def _normalize_feature_ids(value: Any) -> list[str]:
    if isinstance(value, dict):
        rows = value.get("feature_ids")
    else:
        rows = value
    if not isinstance(rows, list):
        raise RuntimeError("SCHEMA_FAIL:feature_ids")
    out = sorted({str(v).strip() for v in rows if str(v).strip()})
    return out


def _pick_rule(feature_id: str, rules: list[dict[str, Any]]) -> dict[str, Any] | None:
    for row in rules:
        prefix = str(row.get("match_prefix", "")).strip()
        if prefix and str(feature_id).startswith(prefix):
            return row
    return None


def derive_queries(*, feature_ids: list[str], rules_payload: dict[str, Any]) -> list[str]:
    rules_raw = rules_payload.get("rules")
    if not isinstance(rules_raw, list):
        raise RuntimeError("SCHEMA_FAIL:rules")
    rules: list[dict[str, Any]] = [dict(row) for row in rules_raw if isinstance(row, dict)]

    default_templates_raw = rules_payload.get("default_query_templates")
    if not isinstance(default_templates_raw, list) or not default_templates_raw:
        default_templates = ["research summary {feature}"]
    else:
        default_templates = [str(v) for v in default_templates_raw if str(v).strip()]

    queries: list[str] = []
    seen: set[str] = set()
    for feature_id in sorted(feature_ids):
        chosen = _pick_rule(feature_id, rules)
        templates_raw = chosen.get("query_templates") if isinstance(chosen, dict) else default_templates
        if not isinstance(templates_raw, list) or not templates_raw:
            templates_raw = default_templates
        templates = [str(v) for v in templates_raw if str(v).strip()]
        for template in templates:
            query = template.replace("{feature}", feature_id)
            if query in seen:
                continue
            seen.add(query)
            queries.append(query)
    return queries


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="query_router_v1")
    ap.add_argument("--feature_ids_json", required=True)
    ap.add_argument("--rules_json", default=str((Path(__file__).resolve().parent / "query_router_rules_v1.json").as_posix()))
    ap.add_argument("--out", default="")
    return ap.parse_args()


def main() -> None:
    args = _parse_args()
    feature_payload = json.loads(Path(args.feature_ids_json).resolve().read_text(encoding="utf-8"))
    feature_ids = _normalize_feature_ids(feature_payload)
    rules_payload = _load_json(Path(args.rules_json).resolve())
    queries = derive_queries(feature_ids=feature_ids, rules_payload=rules_payload)
    out = {
        "schema_version": "query_router_output_v1",
        "feature_ids": feature_ids,
        "queries": queries,
    }
    if str(args.out).strip():
        out_path = Path(str(args.out)).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(out, sort_keys=True, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    print(json.dumps(out, sort_keys=True, separators=(",", ":"), ensure_ascii=False))


if __name__ == "__main__":
    main()
