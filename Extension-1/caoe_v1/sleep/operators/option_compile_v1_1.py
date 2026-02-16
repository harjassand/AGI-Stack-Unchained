"""ABSOP_OPTION_COMPILE_V1_1 operator implementation (macro-do aware)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

base_dir = Path(__file__).resolve().parents[2]
if str(base_dir) not in sys.path:
    sys.path.insert(0, str(base_dir))

from api_v1 import canonical_json_bytes  # noqa: E402
from artifacts.ids_v1 import mechanism_hash, ontology_hash  # noqa: E402

OP_ID = "ABSOP_OPTION_COMPILE_V1_1"
MECH_ID = "macro_do_transition_v1_1"
POLICY_PARAMS_MECH_ID = "ccai_x_policy_params_v1_1"
MAX_PSI_STEPS = 4


def _psi_variant(symbol: dict[str, Any]) -> dict[str, Any]:
    sym_name = symbol["name"]
    do_name = f"do_{sym_name}"
    ops = [
        {"op": "CONST", "dst": "psi_len", "args": [{"int": 1}]},
        {"op": "CONST", "dst": "psi_0_type", "args": [{"int": 1}]},
        {"op": "CONST", "dst": "psi_0_index", "args": [{"int": 0}]},
        {"op": "GET", "dst": "psi_0_value", "args": [do_name]},
    ]
    return {
        "format": "bounded_program_v1",
        "schema_version": 1,
        "inputs": [{"name": do_name, "type": "bit"}],
        "outputs": [
            {"name": "psi_len", "type": "int"},
            {"name": "psi_0_type", "type": "int"},
            {"name": "psi_0_index", "type": "int"},
            {"name": "psi_0_value", "type": "int"},
        ],
        "ops": ops,
        "max_ops": 8,
    }


def _action_set() -> list[tuple]:
    actions: list[tuple] = []
    for i in range(4):
        actions.append(("SET_X", i, 0))
        actions.append(("SET_X", i, 1))
    for j in range(16):
        actions.append(("TOGGLE_N", j))
    return actions


def _psi_step_from_action(action: tuple, *, use_do_value: bool, do_name: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    step_type = 0
    step_index = 0
    step_value = 0
    if action[0] == "SET_X":
        _, idx, value = action
        step_type = 1
        step_index = int(idx)
        step_value = int(value)
    elif action[0] == "TOGGLE_N":
        _, idx = action
        step_type = 2
        step_index = int(idx)
        step_value = 0
    ops = [
        {"op": "CONST", "dst": "psi_type", "args": [{"int": step_type}]},
        {"op": "CONST", "dst": "psi_index", "args": [{"int": step_index}]},
    ]
    if use_do_value:
        ops.append({"op": "GET", "dst": "psi_value", "args": [do_name]})
    else:
        ops.append({"op": "CONST", "dst": "psi_value", "args": [{"int": int(step_value)}]})
    return ops, {"type": step_type, "index": step_index, "value": step_value}


def _psi_program_from_sequence(symbol: dict[str, Any], action_sequence: list[int]) -> dict[str, Any] | None:
    sym_name = symbol.get("name")
    if not isinstance(sym_name, str) or not sym_name:
        return None
    do_name = f"do_{sym_name}"
    action_set = _action_set()
    if not action_sequence:
        return None
    if len(action_sequence) > MAX_PSI_STEPS:
        return None

    ops: list[dict[str, Any]] = [
        {"op": "GET", "dst": "cond", "args": [do_name]},
        {"op": "CONST", "dst": "psi_len_seq", "args": [{"int": int(len(action_sequence))}]},
        {"op": "CONST", "dst": "psi_len_base", "args": [{"int": 1}]},
        {"op": "MUX", "dst": "psi_len", "args": ["cond", "psi_len_seq", "psi_len_base"]},
    ]
    outputs = [
        {"name": "psi_len", "type": "int"},
        {"name": "psi_0_type", "type": "int"},
        {"name": "psi_0_index", "type": "int"},
        {"name": "psi_0_value", "type": "int"},
        {"name": "psi_1_type", "type": "int"},
        {"name": "psi_1_index", "type": "int"},
        {"name": "psi_1_value", "type": "int"},
        {"name": "psi_2_type", "type": "int"},
        {"name": "psi_2_index", "type": "int"},
        {"name": "psi_2_value", "type": "int"},
        {"name": "psi_3_type", "type": "int"},
        {"name": "psi_3_index", "type": "int"},
        {"name": "psi_3_value", "type": "int"},
    ]

    for k in range(MAX_PSI_STEPS):
        if k < len(action_sequence):
            action_id = int(action_sequence[k])
            if action_id < 0 or action_id >= len(action_set):
                return None
            action = action_set[action_id]
            step_ops, meta = _psi_step_from_action(
                action,
                use_do_value=(k == 0),
                do_name=do_name,
            )
            if k == 0:
                ops.extend(
                    [
                        {"op": step_ops[0]["op"], "dst": f"psi_{k}_type", "args": step_ops[0]["args"]},
                        {"op": step_ops[1]["op"], "dst": f"psi_{k}_index", "args": step_ops[1]["args"]},
                        {"op": step_ops[2]["op"], "dst": f"psi_{k}_value", "args": step_ops[2]["args"]},
                    ]
                )
            else:
                ops.extend(
                    [
                        {"op": "CONST", "dst": f"psi_{k}_type_seq", "args": [{"int": int(meta['type'])}]},
                        {"op": "CONST", "dst": f"psi_{k}_index_seq", "args": [{"int": int(meta['index'])}]},
                        {"op": "CONST", "dst": f"psi_{k}_value_seq", "args": [{"int": int(meta['value'])}]},
                        {"op": "CONST", "dst": f"psi_{k}_type_base", "args": [{"int": 0}]},
                        {"op": "CONST", "dst": f"psi_{k}_index_base", "args": [{"int": 0}]},
                        {"op": "CONST", "dst": f"psi_{k}_value_base", "args": [{"int": 0}]},
                        {"op": "MUX", "dst": f"psi_{k}_type", "args": ["cond", f"psi_{k}_type_seq", f"psi_{k}_type_base"]},
                        {"op": "MUX", "dst": f"psi_{k}_index", "args": ["cond", f"psi_{k}_index_seq", f"psi_{k}_index_base"]},
                        {"op": "MUX", "dst": f"psi_{k}_value", "args": ["cond", f"psi_{k}_value_seq", f"psi_{k}_value_base"]},
                    ]
                )
        else:
            ops.extend(
                [
                    {"op": "CONST", "dst": f"psi_{k}_type", "args": [{"int": 0}]},
                    {"op": "CONST", "dst": f"psi_{k}_index", "args": [{"int": 0}]},
                    {"op": "CONST", "dst": f"psi_{k}_value", "args": [{"int": 0}]},
                ]
            )
    return {
        "format": "bounded_program_v1",
        "schema_version": 1,
        "inputs": [{"name": do_name, "type": "bit"}],
        "outputs": outputs,
        "ops": ops,
        "max_ops": len(ops),
    }


def _sequence_variants(action_sequence: list[int]) -> list[list[int]]:
    variants = [list(action_sequence)]
    if len(action_sequence) > 1:
        rev = list(reversed(action_sequence))
        if rev != action_sequence:
            variants.append(rev)
    return variants


def _macro_transition_mechanism(symbols: list[dict[str, Any]]) -> dict[str, Any]:
    inputs = []
    outputs = []
    ops = []
    for sym in symbols:
        name = sym.get("name")
        if sym.get("type") != "bit" or not isinstance(name, str) or not name:
            raise ValueError("macro transition only supports bit symbols")
        do_name = f"do_{name}"
        inputs.append(do_name)
        outputs.append(name)
        ops.append({"op": "GET", "dst": name, "args": [do_name]})
    return {
        "mechanism_id": MECH_ID,
        "inputs": inputs,
        "outputs": outputs,
        "transition": {
            "format": "bounded_program_v1",
            "schema_version": 1,
            "inputs": [{"name": name, "type": "bit"} for name in inputs],
            "outputs": [{"name": name, "type": "bit"} for name in outputs],
            "ops": ops,
            "max_ops": len(ops),
        },
        "params": {},
    }


def _empty_transition() -> dict[str, Any]:
    return {
        "format": "bounded_program_v1",
        "schema_version": 1,
        "inputs": [],
        "outputs": [],
        "ops": [],
        "max_ops": 0,
    }


def _policy_mechanism(params: dict[str, int]) -> dict[str, Any]:
    return {
        "mechanism_id": POLICY_PARAMS_MECH_ID,
        "inputs": [],
        "outputs": [],
        "transition": _empty_transition(),
        "params": params,
    }


def _policy_param_candidates(*, include_short: bool = False) -> list[dict[str, int]]:
    if include_short:
        base_params = [
            {
                "risk_weight": 1,
                "ambiguity_weight": 1,
                "complexity_weight": 1,
                "exploration_bonus_weight": 0,
                "horizon": 4,
            }
        ]
    else:
        base_params = [
            {
                "risk_weight": 1,
                "ambiguity_weight": 1,
                "complexity_weight": 1,
                "exploration_bonus_weight": 0,
                "horizon": 4,
            },
            {
                "risk_weight": 1,
                "ambiguity_weight": 0,
                "complexity_weight": 4,
                "exploration_bonus_weight": 0,
                "horizon": 2,
            },
        ]
    bias = 1 if include_short else 0
    params: list[dict[str, int]] = []
    for entry in base_params:
        entry = dict(entry)
        entry["goal_action_bias"] = bias
        params.append(entry)
    return params


def propose(
    anomaly_buffer: dict[str, Any],
    base_ontology: dict[str, Any],
    base_mech: dict[str, Any],
    proposer_state: dict[str, Any],
) -> list[dict[str, Any]]:
    if not proposer_state.get("allow_macro_ops", False):
        return []
    if not base_ontology.get("supports_macro_do", False):
        return []
    symbols = base_ontology.get("symbols") or []
    if len(symbols) != 1:
        return []
    if any(sym.get("type") != "bit" for sym in symbols):
        return []

    base_hash = anomaly_buffer.get("base_ontology_hash") or ontology_hash(base_ontology)
    mech_hash = mechanism_hash(base_mech)
    gains = {
        "delta_mdl_bits": 0,
        "delta_worst_case_success": 0.0,
        "delta_efficiency": 0.05,
    }

    psi_variants: list[dict[str, Any]] = []
    psi_prog = _psi_variant(symbols[0])
    psi_variants.append(
        {
            "variant": "macro_option_compile_v1_1",
            "psi": psi_prog,
            "bytes": canonical_json_bytes(psi_prog),
            "sequence": None,
        }
    )
    dev_class = anomaly_buffer.get("dev_classification") or {}
    sequence_oracle = dev_class.get("sequence_oracle") if isinstance(dev_class, dict) else None
    if isinstance(sequence_oracle, dict):
        seq = sequence_oracle.get("action_sequence")
        if isinstance(seq, list) and all(isinstance(x, int) for x in seq):
            seq_base = [int(x) for x in seq]
            for idx, variant_seq in enumerate(_sequence_variants(seq_base)):
                seq_prog = _psi_program_from_sequence(symbols[0], variant_seq)
                if not isinstance(seq_prog, dict):
                    continue
                variant_name = "macro_sequence_oracle_v1_2" if idx == 0 else "macro_sequence_oracle_reversed_v1_2"
                psi_variants.append(
                    {
                        "variant": variant_name,
                        "psi": seq_prog,
                        "bytes": canonical_json_bytes(seq_prog),
                        "sequence": list(variant_seq),
                    }
                )

    mech = _macro_transition_mechanism(symbols)
    has_mech = any(m.get("mechanism_id") == MECH_ID for m in (base_mech.get("mechanisms") or []))
    macro_op = "replace_mechanism" if has_mech else "add_mechanism"
    has_policy = any(m.get("mechanism_id") == POLICY_PARAMS_MECH_ID for m in (base_mech.get("mechanisms") or []))
    policy_op = "replace_mechanism" if has_policy else "add_mechanism"

    proposals: list[dict[str, Any]] = []
    for psi_entry in psi_variants:
        local_gains = dict(gains)
        if psi_entry.get("sequence"):
            local_gains["delta_worst_case_success"] = float(local_gains.get("delta_worst_case_success", 0.0)) + 0.02
        ontology_patch = {
            "format": "ontology_patch_v1_1",
            "schema_version": 1,
            "base_ontology_hash": base_hash,
            "ops": [{"op": "replace_psi", "psi": psi_entry["psi"]}],
            "claimed_obligations": {
                "requires_c_do": True,
                "requires_c_mdl": True,
                "requires_c_inv": True,
                "requires_c_anti": True,
            },
            "predicted_gains": local_gains,
        }
        for params in _policy_param_candidates(include_short=bool(psi_entry.get("sequence"))):
            mech_diff = {
                "format": "mechanism_registry_diff_v1_1",
                "schema_version": 1,
                "base_mech_hash": mech_hash,
                "ops": [
                    {"op": macro_op, "mechanism": mech},
                    {"op": policy_op, "mechanism": _policy_mechanism(params)},
                ],
            }
            derivation = {
                "base_candidate_id": anomaly_buffer.get("identity_candidate_id", ""),
                "used_regime_ids": [
                    item.get("regime_id") for item in anomaly_buffer.get("signals", {}).get("worst_regimes", [])
                ],
                "operator_internal_notes": {
                    "variant": psi_entry["variant"],
                    "mechanism_id": MECH_ID,
                    "policy_params": params,
                    "action_sequence": psi_entry.get("sequence"),
                },
            }
            proposals.append(
                {
                    "op_id": OP_ID,
                    "ontology_patch": ontology_patch,
                    "mech_diff": mech_diff,
                    "program_blobs": {"programs/psi.bp": psi_entry["bytes"]},
                    "claimed_obligations": ontology_patch["claimed_obligations"],
                    "predicted_gains": local_gains,
                    "derivation": derivation,
                }
            )
    return proposals
