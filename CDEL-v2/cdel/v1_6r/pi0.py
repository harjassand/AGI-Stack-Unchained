"""Pi0 baseline programs for v1.5r."""

from __future__ import annotations

from typing import Any

from cdel.kernel.parse import parse_definition

from .canon import hash_json


_POLICY_PARAMS = [
    {"name": "agent_x", "type": {"tag": "int"}},
    {"name": "agent_y", "type": {"tag": "int"}},
    {"name": "goal_x", "type": {"tag": "int"}},
    {"name": "goal_y", "type": {"tag": "int"}},
]


def _const_action_def(name: str, action_value: int) -> dict[str, Any]:
    return {
        "name": name,
        "params": list(_POLICY_PARAMS),
        "ret_type": {"tag": "int"},
        "body": {"tag": "int", "value": int(action_value)},
        "termination": {"kind": "structural", "decreases_param": None},
    }


def _greedy_axis_def(name: str) -> dict[str, Any]:
    return {
        "name": name,
        "params": list(_POLICY_PARAMS),
        "ret_type": {"tag": "int"},
        "body": {
            "tag": "if",
            "cond": {
                "tag": "prim",
                "op": "lt_int",
                "args": [
                    {"tag": "var", "name": "agent_x"},
                    {"tag": "var", "name": "goal_x"},
                ],
            },
            "then": {"tag": "int", "value": 3},
            "else": {
                "tag": "if",
                "cond": {
                    "tag": "prim",
                    "op": "lt_int",
                    "args": [
                        {"tag": "var", "name": "goal_y"},
                        {"tag": "var", "name": "agent_y"},
                    ],
                },
                "then": {"tag": "int", "value": 1},
                "else": {
                    "tag": "if",
                    "cond": {
                        "tag": "prim",
                        "op": "lt_int",
                        "args": [
                            {"tag": "var", "name": "agent_y"},
                            {"tag": "var", "name": "goal_y"},
                        ],
                    },
                    "then": {"tag": "int", "value": 0},
                    "else": {
                        "tag": "if",
                        "cond": {
                            "tag": "prim",
                            "op": "lt_int",
                            "args": [
                                {"tag": "var", "name": "goal_x"},
                                {"tag": "var", "name": "agent_x"},
                            ],
                        },
                        "then": {"tag": "int", "value": 2},
                        "else": {"tag": "int", "value": 0},
                    },
                },
            },
        },
        "termination": {"kind": "structural", "decreases_param": None},
    }


def baseline_definition() -> dict[str, Any]:
    return _const_action_def("pi0_baseline_fail", 99)


def program_definitions() -> list[dict[str, Any]]:
    return [
        _const_action_def("pi0_up", 0),
        _const_action_def("pi0_right", 3),
        _greedy_axis_def("pi0_greedy"),
    ]


def programs() -> list[dict[str, Any]]:
    programs_out: list[dict[str, Any]] = []
    for defn in program_definitions():
        payload = {
            "schema": "pi0_program_v1",
            "schema_version": 1,
            "program_version": 1,
            "definition": defn,
        }
        program_id = hash_json(payload)
        payload["program_id"] = program_id
        programs_out.append(payload)
    return programs_out


def parsed_definitions() -> dict[str, object]:
    defs: dict[str, object] = {}
    baseline = baseline_definition()
    defs[baseline["name"]] = parse_definition(baseline)
    for program in program_definitions():
        defs[program["name"]] = parse_definition(program)
    return defs
