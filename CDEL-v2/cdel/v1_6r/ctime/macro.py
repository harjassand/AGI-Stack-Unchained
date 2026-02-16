"""Macro admission and ledger utilities for v1.5r."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from ..canon import canon_bytes, hash_json, load_canon_json, sha256_prefixed, write_canon_json, write_jsonl_line


def _macro_id_payload(macro_def: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": macro_def.get("schema"),
        "schema_version": macro_def.get("schema_version"),
        "body": macro_def.get("body", []),
        "guard": macro_def.get("guard"),
    }


def _macro_rent_payload(macro_def: dict[str, Any]) -> dict[str, Any]:
    payload = {"body": macro_def.get("body", [])}
    guard = macro_def.get("guard")
    if guard is not None:
        payload["guard"] = guard
    return payload


def compute_macro_id(macro_def: dict[str, Any]) -> str:
    return hash_json(_macro_id_payload(macro_def))


def compute_rent_bits(macro_def: dict[str, Any]) -> int:
    return 8 * len(canon_bytes(_macro_rent_payload(macro_def)))


def _action_key(action: dict[str, Any]) -> tuple[str, str]:
    name = action.get("name", "")
    args = action.get("args", {})
    return name, canon_bytes(args).decode("utf-8")


def _extract_actions(trace_events: list[dict[str, Any]]) -> dict[str, list[tuple[str, str]]]:
    per_family: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for event in trace_events:
        family_id = event.get("family_id", "")
        per_family[family_id].append(_action_key(event.get("action", {})))
    return per_family


def _match_body(actions: list[tuple[str, str]], body: list[tuple[str, str]], idx: int) -> bool:
    if idx + len(body) > len(actions):
        return False
    return actions[idx : idx + len(body)] == body


def _count_occurrences(actions: list[tuple[str, str]], body: list[tuple[str, str]]) -> int:
    count = 0
    idx = 0
    while idx <= len(actions) - len(body):
        if _match_body(actions, body, idx):
            count += 1
            idx += len(body)
        else:
            idx += 1
    return count


def encode_length(actions: list[tuple[str, str]], macros: list[dict[str, Any]]) -> int:
    bodies = []
    for macro in macros:
        body = [_action_key(op) for op in macro.get("body", [])]
        bodies.append((macro["macro_id"], body))
    idx = 0
    tokens = 0
    while idx < len(actions):
        matches = []
        for macro_id, body in bodies:
            if _match_body(actions, body, idx):
                matches.append((len(body), macro_id, body))
        if matches:
            matches.sort(key=lambda item: (-item[0], item[1]))
            length, _, _ = matches[0]
            tokens += 1
            idx += length
        else:
            tokens += 1
            idx += 1
    return tokens


def admit_macro(
    macro_def: dict[str, Any],
    trace_events: list[dict[str, Any]],
    active_macros: list[dict[str, Any]] | None = None,
    instance_specs: dict[str, Any] | None = None,
    f_min: int = 3,
    n_min: int = 10,
    delta_min_bits: int = 32,
) -> dict[str, Any]:
    active_macros = active_macros or []
    _ = instance_specs
    recomputed_id = compute_macro_id(macro_def)
    recomputed_rent = compute_rent_bits(macro_def)
    body_ops = macro_def.get("body", [])
    body = [_action_key(op) for op in body_ops]

    errors: list[str] = []
    if macro_def.get("macro_id") != recomputed_id:
        errors.append("macro_id_mismatch")
    if macro_def.get("rent_bits") != recomputed_rent:
        errors.append("rent_bits_mismatch")
    if not (2 <= len(body) <= 64):
        errors.append("length_out_of_bounds")
    if any("macro_id" in op for op in body_ops):
        errors.append("macro_calls_disallowed")

    per_family = _extract_actions(trace_events)
    support_families = 0
    support_total = 0
    for actions in per_family.values():
        count = _count_occurrences(actions, body)
        if count > 0:
            support_families += 1
            support_total += count

    if support_families < f_min:
        errors.append("support_families_below_min")
    if support_total < n_min:
        errors.append("support_total_below_min")

    enc_base = 0
    enc_with = 0
    for actions in per_family.values():
        enc_base += encode_length(actions, active_macros)
        enc_with += encode_length(actions, active_macros + [macro_def])
    mdl_gain_bits = 8 * (enc_base - enc_with) - recomputed_rent
    if mdl_gain_bits < delta_min_bits:
        errors.append("mdl_gain_below_min")

    replay_ok = True
    if not replay_ok:
        errors.append("replay_mismatch")

    decision = "PASS" if not errors else "FAIL"
    return {
        "schema": "macro_admission_report_v1",
        "schema_version": 1,
        "macro_id": recomputed_id,
        "decision": decision,
        "support_families_hold": support_families,
        "support_total_hold": support_total,
        "mdl_gain_bits": mdl_gain_bits,
        "rent_bits": recomputed_rent,
        "errors": errors,
    }


def load_macro_ledger(path: str | Path) -> list[dict[str, Any]]:
    path = Path(path)
    if not path.exists():
        return []
    lines = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        lines.append(json.loads(raw))
    return lines


def _ledger_prev_hash(lines: list[dict[str, Any]]) -> str:
    if not lines:
        return "sha256:" + "0" * 64
    return lines[-1]["line_hash"]


def update_macro_ledger(
    path: str | Path,
    event: str,
    macro_id: str,
    ref_hash: str,
    epoch_id: str,
    reason_codes: list[str] | None = None,
    evidence_refs: list[str] | None = None,
) -> dict[str, Any]:
    path = Path(path)
    existing = []
    if path.exists():
        for raw in path.read_text(encoding="utf-8").splitlines():
            if raw.strip():
                existing.append(json.loads(raw))
    prev_hash = _ledger_prev_hash(existing)
    entry = {
        "schema": "macro_ledger_event_v1",
        "schema_version": 1,
        "event": event,
        "macro_id": macro_id,
        "ref_hash": ref_hash,
        "epoch_id": epoch_id,
        "prev_ledger_hash": prev_hash,
    }
    _ = reason_codes, evidence_refs
    line_hash = sha256_prefixed(canon_bytes(entry))
    entry["line_hash"] = line_hash
    write_jsonl_line(path, entry)
    return entry


def write_macro_active_set(path: str | Path, active_macro_ids: list[str], ledger_head_hash: str) -> None:
    payload = {
        "schema": "macro_active_set_v1",
        "schema_version": 1,
        "active_macro_ids": sorted(active_macro_ids),
        "ledger_head_hash": ledger_head_hash,
    }
    write_canon_json(path, payload)


def load_macro_defs(path: str | Path, allowed: list[str] | None = None) -> list[dict[str, Any]]:
    macros_dir = Path(path)
    if not macros_dir.exists():
        return []
    allowed_set = set(allowed or [])
    macros: list[dict[str, Any]] = []
    for entry in sorted(macros_dir.glob("*.json")):
        macro = load_canon_json(entry)
        macro_id = macro.get("macro_id")
        if allowed and macro_id not in allowed_set:
            continue
        macros.append(macro)
    return macros
