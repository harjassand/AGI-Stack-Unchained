#!/usr/bin/env python3
"""SH-1 receipt-derived GE audit report generator."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from cdel.v1_7r.canon import canon_bytes, write_canon_json
from cdel.v18_0.authority.authority_hash_v1 import load_authority_pins
from cdel.v18_0.omega_common_v1 import rat_q32, validate_schema

from tools.genesis_engine.sh1_xs_v1 import build_xs_snapshot, load_ge_config


REPO_ROOT = Path(__file__).resolve().parents[2]


def _sha256_prefixed(data: bytes) -> str:
    import hashlib

    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="ge_audit_report_sh1_v0_1")
    parser.add_argument("--runs_root", required=True)
    parser.add_argument("--ge_config_path", required=True)
    parser.add_argument("--out_json", required=True)
    parser.add_argument("--out_md", required=True)
    return parser.parse_args()


def _sentinel_mix(events: list[dict[str, Any]]) -> dict[str, int]:
    out = {"busy_fail_u64": 0, "logic_fail_u64": 0, "safety_fail_u64": 0, "ok_u64": 0}
    for event in events:
        behavior = event.get("behavior_sig")
        if not isinstance(behavior, dict):
            continue
        phi = behavior.get("phi")
        if not isinstance(phi, list) or len(phi) < 4:
            continue
        klass = int(phi[3])
        if klass == 1:
            out["busy_fail_u64"] += 1
        elif klass == 2:
            out["logic_fail_u64"] += 1
        elif klass == 3:
            out["safety_fail_u64"] += 1
        else:
            out["ok_u64"] += 1
    return out


def _write_md(path: Path, report: dict[str, Any]) -> None:
    kpi = report["kpi"]
    sentinel = report["sentinel_mix"]
    novelty = report["novelty"]
    flags = report["falsification_flags"]

    lines = [
        "# GE_AUDIT_REPORT_v1",
        "",
        f"- ge_config_id: `{report['ge_config_id']}`",
        f"- authority_pins_hash: `{report['authority_pins_hash']}`",
        f"- receipt_stream_hash: `{report['receipt_stream_hash']}`",
        "",
        "## KPI",
        f"- promote_u64: {kpi['promote_u64']}",
        f"- total_wall_ms_u64: {kpi['total_wall_ms_u64']}",
        f"- yield_promotions_per_wall_ms_q32: {kpi['yield_promotions_per_wall_ms_q32']}",
        "",
        "## Sentinel Mix",
        f"- busy_fail_u64: {sentinel['busy_fail_u64']}",
        f"- logic_fail_u64: {sentinel['logic_fail_u64']}",
        f"- safety_fail_u64: {sentinel['safety_fail_u64']}",
        f"- ok_u64: {sentinel['ok_u64']}",
        "",
        "## Novelty",
        f"- reservoir_size_u64: {novelty['reservoir_size_u64']}",
        f"- min_novelty_bits_u64: {novelty['min_novelty_bits_u64']}",
        f"- novel_u64: {novelty['novel_u64']}",
        f"- total_u64: {novelty['total_u64']}",
        f"- novelty_coverage_q32: {novelty['novelty_coverage_q32']}",
        "",
        "## Falsification Flags",
    ]
    if not flags:
        lines.append("- none")
    else:
        for row in flags:
            lines.append(f"- {row['code']}: {row['detail']}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = _parse_args()
    runs_root = Path(args.runs_root).expanduser().resolve()
    ge_config_path = Path(args.ge_config_path).expanduser().resolve()
    out_json = Path(args.out_json).expanduser().resolve()
    out_md = Path(args.out_md).expanduser().resolve()

    ge_config = load_ge_config(ge_config_path)
    validate_schema(ge_config, "ge_config_v1")

    pins = load_authority_pins(REPO_ROOT)
    authority_pins_hash = _sha256_prefixed(canon_bytes(pins))

    xs_snapshot, events = build_xs_snapshot(
        recent_runs_root=runs_root,
        ge_config=ge_config,
        authority_pins_hash=authority_pins_hash,
    )

    promote_u64 = 0
    total_wall_ms_u64 = 0
    novelty_cfg = ge_config.get("novelty") or {}
    min_novelty_bits_u64 = max(0, int((novelty_cfg or {}).get("min_novelty_bits_u64", 0)))
    reservoir_size_u64 = max(1, int((novelty_cfg or {}).get("reservoir_size_u64", 1)))

    novel_u64 = 0
    for event in events:
        receipt = event.get("receipt_payload")
        if not isinstance(receipt, dict):
            continue
        if str(receipt.get("decision", "")).strip() == "PROMOTE":
            promote_u64 += 1
        cost = receipt.get("cost_vector")
        if isinstance(cost, dict):
            total_wall_ms_u64 += max(0, int(cost.get("wall_ms", 0)))
        novelty_bits = max(0, int(event.get("novelty_bits", 0)))
        if novelty_bits >= min_novelty_bits_u64:
            novel_u64 += 1

    total_u64 = len(events)
    novelty_coverage_q32 = int(rat_q32(novel_u64, max(1, total_u64)))

    kpi_cfg = ge_config.get("kpi")
    if not isinstance(kpi_cfg, dict):
        raise RuntimeError("INVALID:SCHEMA_FAIL")
    burn_in_receipts_u64 = max(0, int(kpi_cfg.get("burn_in_receipts_u64", 0)))
    plateau_windows_u64 = max(1, int(kpi_cfg.get("plateau_windows_u64", 1)))
    novelty_min_coverage_q32 = max(0, int(kpi_cfg.get("novelty_min_coverage_q32", 0)))

    tail_events = events[-plateau_windows_u64:]
    tail_total = len(tail_events)
    tail_novel = sum(1 for row in tail_events if max(0, int(row.get("novelty_bits", 0))) >= min_novelty_bits_u64)
    tail_coverage_q32 = int(rat_q32(tail_novel, max(1, tail_total)))

    falsification_flags: list[dict[str, str]] = []
    if total_u64 >= burn_in_receipts_u64 and tail_coverage_q32 < novelty_min_coverage_q32:
        falsification_flags.append(
            {
                "code": "F2_CREATIVITY_COLLAPSE",
                "detail": (
                    f"tail_window_u64={tail_total} tail_novel_u64={tail_novel} "
                    f"tail_coverage_q32={tail_coverage_q32} threshold_q32={novelty_min_coverage_q32}"
                ),
            }
        )

    report = {
        "schema_version": "ge_audit_report_v1",
        "ge_config_id": str(ge_config.get("ge_config_id", "")),
        "authority_pins_hash": authority_pins_hash,
        "receipt_stream_hash": str(xs_snapshot.get("receipt_stream_hash", "")),
        "kpi": {
            "promote_u64": int(promote_u64),
            "total_wall_ms_u64": int(total_wall_ms_u64),
            "yield_promotions_per_wall_ms_q32": int(rat_q32(promote_u64, max(1, total_wall_ms_u64))),
        },
        "sentinel_mix": _sentinel_mix(events),
        "novelty": {
            "reservoir_size_u64": int(reservoir_size_u64),
            "min_novelty_bits_u64": int(min_novelty_bits_u64),
            "novel_u64": int(novel_u64),
            "total_u64": int(total_u64),
            "novelty_coverage_q32": int(novelty_coverage_q32),
        },
        "falsification_flags": falsification_flags,
    }
    validate_schema(report, "ge_audit_report_v1")

    out_json.parent.mkdir(parents=True, exist_ok=True)
    write_canon_json(out_json, report)
    _write_md(out_md, report)


if __name__ == "__main__":
    main()
