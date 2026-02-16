from __future__ import annotations

from typing import Any

from ..canon import hash_json
from ..family_dsl.runtime import compute_signature, compute_family_id


ACTIONS_DEFAULT = ["UP", "DOWN", "LEFT", "RIGHT"]


def _is_call(op: Any) -> bool:
    return isinstance(op, dict) and (
        (op.get("op") == "CALL_MACRO" and isinstance(op.get("macro_id"), str))
        or (
            op.get("name") == "CALL_MACRO"
            and isinstance(op.get("args"), dict)
            and isinstance(op["args"].get("macro_id"), str)
        )
    )


def _call_id(op: dict[str, Any]) -> str:
    if op.get("op") == "CALL_MACRO":
        return op["macro_id"]
    return op["args"]["macro_id"]


def expand_macro_to_primitives(mid: str, macro_map: dict[str, dict[str, Any]], stack: list[str] | None = None) -> list[str]:
    if stack is None:
        stack = []
    if mid in stack:
        raise RuntimeError("macro cycle: " + " -> ".join(stack + [mid]))
    m = macro_map.get(mid)
    if not m:
        return []
    body = m.get("body", [])
    if not isinstance(body, list):
        return []
    out: list[str] = []
    st = stack + [mid]
    for op in body:
        if _is_call(op):
            out.extend(expand_macro_to_primitives(_call_id(op), macro_map, st))
        elif isinstance(op, dict) and isinstance(op.get("name"), str):
            out.append(op["name"])
    return out


def build_anti_motif(expansion: list[str], *, actions: list[str] | None = None) -> list[str]:
    if actions is None:
        actions = ACTIONS_DEFAULT
    if not expansion:
        return ["NOOP"]
    a0 = expansion[0]
    a1 = expansion[1] if len(expansion) > 1 else a0
    sep = None
    for a in actions:
        if a != a0 and a != a1:
            sep = a
            break
    if sep is None:
        sep = "NOOP"
    # Break contiguous matching by inserting sep between every action
    anti: list[str] = []
    for a in expansion[:8]:
        anti.append(a)
        anti.append(sep)
    # Trim trailing sep
    if anti and anti[-1] == sep:
        anti.pop()
    return anti


def make_adversarial_family(*, target_macro_id: str, expansion: list[str], motif_len: int = 40) -> dict[str, Any]:
    anti = build_anti_motif(expansion)
    motif: list[str] = []
    while len(motif) < motif_len:
        motif.extend(anti)
    motif = motif[:motif_len]

    fam = {
        "schema": "family_dsl_v1",
        "schema_version": 1,
        "dsl_version": 1,
        "params_schema": [],
        "resource_bounds": {
            "max_env_steps_per_instance": 64,
            "max_instance_bytes": 1024,
            "max_instantiation_gas": 128,
            "max_shrink_gas": 128,
        },
        "instantiator": {
            "op": "CONST",
            "value": {
                "motif_action_names": motif,
                "adversary_target_macro_id": target_macro_id,
                "adversary_kind": "ANTI_MOTIF_V1",
                "signature_salt": "adv:" + target_macro_id,
            },
        },
        "pressure_rule": {"op": "CONST", "value": {}},
    }

    fam["signature"] = compute_signature(fam)
    fam["family_id"] = compute_family_id(fam)
    return fam
