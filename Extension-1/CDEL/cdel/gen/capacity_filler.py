"""Deterministic capacity filler generator (pre-certified deltas)."""

from __future__ import annotations

from cdel.gen.enum import Candidate, TaskSpec, _params_for_type, _type_json
from cdel.kernel.types import FunType, Type


class CapacityFillerGenerator:
    def __init__(self) -> None:
        self.last_stats: dict[str, int | None] = {}

    def generate(self, task: TaskSpec, env_symbols: dict[str, Type], env_defs: dict[str, object] | None = None) -> list[Candidate]:
        params = _params_for_type(task.typ)
        ret_type = task.typ.ret if isinstance(task.typ, FunType) else task.typ
        body = _identity_body(params, ret_type)
        definition = {
            "name": task.new_symbol,
            "params": params,
            "ret_type": _type_json(ret_type),
            "body": body,
            "termination": {"kind": "structural", "decreases_param": None},
        }
        self.last_stats = {
            "bodies_enumerated": 1,
            "deduped": 0,
            "output_fail": 0,
            "min_size": None,
            "max_size": None,
            "candidates_returned": 1,
        }
        return [Candidate(definition=definition, declared_deps=[])]


def _identity_body(params: list[dict], ret_type: Type) -> dict:
    if params:
        return {"tag": "var", "name": params[0]["name"]}
    # No params: default literals.
    if _type_json(ret_type) == {"tag": "int"}:
        return {"tag": "int", "value": 0}
    if _type_json(ret_type) == {"tag": "bool"}:
        return {"tag": "bool", "value": True}
    return {"tag": "int", "value": 0}
