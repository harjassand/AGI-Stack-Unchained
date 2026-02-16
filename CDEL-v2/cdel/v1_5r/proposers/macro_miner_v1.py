"""Deterministic macro miner v1 for RSI integrity campaigns."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..canon import canon_bytes, hash_json, loads, sha256_prefixed, write_canon_json
from ..constants import meta_identities, require_constants
from ..ctime.macro import admit_macro, compute_macro_id, compute_rent_bits


def _trace_hash(path: Path) -> str:
    return sha256_prefixed(path.read_bytes())


def _collect_actions(trace_paths: list[Path]) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    events: list[dict[str, Any]] = []
    per_family: dict[str, list[dict[str, Any]]] = {}
    for path in sorted(trace_paths, key=lambda p: p.name):
        for raw in path.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            event = loads(raw)
            events.append(event)
            family_id = event.get("family_id")
            action = event.get("action")
            if not isinstance(family_id, str) or not isinstance(action, dict):
                continue
            body_action = {"name": action.get("name"), "args": action.get("args", {})}
            per_family.setdefault(family_id, []).append(body_action)
    return events, per_family


def mine_macros(
    *,
    trace_paths: list[Path],
    active_macros: list[dict[str, Any]],
    out_dir: Path,
    diagnostics_dir: Path,
    epoch_id: str,
    top_k: int,
) -> dict[str, Any]:
    constants = require_constants()
    meta = meta_identities()
    ctime = constants.get("ctime", {})
    f_min = int(ctime.get("F_min", 3))
    n_min = int(ctime.get("N_min", 10))
    l_min = int(ctime.get("L_min", 2))
    l_max = int(ctime.get("L_max", 12))
    delta_min_bits = int(ctime.get("delta_min_time_bits", 32))

    trace_paths = [path for path in trace_paths if path.exists()]
    trace_hashes = [_trace_hash(path) for path in trace_paths]
    events, per_family = _collect_actions(trace_paths)

    candidate_bodies: dict[bytes, list[dict[str, Any]]] = {}
    for actions in per_family.values():
        for idx in range(len(actions)):
            for length in range(l_min, l_max + 1):
                if idx + length > len(actions):
                    break
                body = actions[idx : idx + length]
                key = canon_bytes(body)
                if key not in candidate_bodies:
                    candidate_bodies[key] = body

    mining_report = {
        "schema": "macro_mining_report_v1",
        "schema_version": 1,
        "epoch_id": epoch_id,
        "trace_hashes": trace_hashes,
        "candidate_count": len(candidate_bodies),
        "top_k": int(top_k),
        "constants": {
            "F_min": f_min,
            "N_min": n_min,
            "L_min": l_min,
            "L_max": l_max,
            "delta_min_time_bits": delta_min_bits,
        },
    }
    mining_report["x-meta"] = meta
    report_hash = hash_json(mining_report)
    write_canon_json(diagnostics_dir / "macro_mining_report_v1.json", mining_report)

    candidates: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for body in candidate_bodies.values():
        macro_def = {
            "schema": "macro_def_v1",
            "schema_version": 1,
            "body": body,
            "guard": None,
            "admission_epoch": 0,
            "x-provenance": "macro_miner_v1",
            "x-mining_report_hash": report_hash,
        }
        macro_def["rent_bits"] = compute_rent_bits(macro_def)
        macro_def["macro_id"] = compute_macro_id(macro_def)
        report = admit_macro(
            macro_def,
            events,
            active_macros=active_macros,
            f_min=f_min,
            n_min=n_min,
            delta_min_bits=delta_min_bits,
        )
        if report.get("decision") == "PASS":
            candidates.append((macro_def, report))

    def _sort_key(item: tuple[dict[str, Any], dict[str, Any]]) -> tuple[int, int, str]:
        macro_def, report = item
        return (
            -int(report.get("mdl_gain_bits", 0)),
            -int(report.get("support_families_hold", 0)),
            str(macro_def.get("macro_id", "")),
        )

    candidates.sort(key=_sort_key)
    selected = candidates[: max(0, int(top_k))]

    out_dir.mkdir(parents=True, exist_ok=True)
    for macro_def, _report in selected:
        content_hash = hash_json(macro_def).split(":", 1)[1]
        write_canon_json(out_dir / f"{content_hash}.json", macro_def)

    return mining_report
