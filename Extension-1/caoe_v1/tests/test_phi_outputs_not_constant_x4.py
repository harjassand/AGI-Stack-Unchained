from __future__ import annotations

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from sleep.operators.coarse_grain_merge_v1 import propose


def _output_depends_on_o_t(program: dict, out_name: str) -> bool:
    ops = program.get("ops") or []
    slice_dsts = set()
    for op in ops:
        if not isinstance(op, dict):
            continue
        if op.get("op") == "SLICE":
            args = op.get("args") or []
            if len(args) >= 1 and args[0] == "o_t":
                dst = op.get("dst")
                if isinstance(dst, str):
                    slice_dsts.add(dst)
    for op in ops:
        if not isinstance(op, dict) or op.get("dst") != out_name:
            continue
        if op.get("op") == "SLICE":
            args = op.get("args") or []
            if len(args) >= 1 and args[0] == "o_t":
                return True
        if op.get("op") == "XOR":
            args = op.get("args") or []
            for arg in args:
                if isinstance(arg, str) and arg in slice_dsts:
                    return True
    return False


def test_phi_outputs_not_constant_x4() -> None:
    base_ontology = {
        "format": "ontology_spec_v1_1",
        "schema_version": 1,
        "ontology_hash": "0" * 64,
        "isa_version": "caoe_absop_isa_v1_2",
        "symbols": [
            {"name": "x0", "type": "bit", "domain": {"kind": "bit"}},
            {"name": "x1", "type": "bit", "domain": {"kind": "bit"}},
            {"name": "x2", "type": "bit", "domain": {"kind": "bit"}},
            {"name": "x3", "type": "bit", "domain": {"kind": "bit"}},
        ],
        "measurement_phi": {
            "format": "bounded_program_v1",
            "schema_version": 1,
            "inputs": [
                {"name": "o_t", "type": "bitvec", "width": 32},
                {"name": "t", "type": "int"},
            ],
            "outputs": [
                {"name": "x0", "type": "bit"},
                {"name": "x1", "type": "bit"},
                {"name": "x2", "type": "bit"},
                {"name": "x3", "type": "bit"},
            ],
            "ops": [
                {"dst": "x0", "op": "CONST", "args": [{"bit": 0}]},
                {"dst": "x1", "op": "CONST", "args": [{"bit": 0}]},
                {"dst": "x2", "op": "CONST", "args": [{"bit": 0}]},
                {"dst": "x3", "op": "CONST", "args": [{"bit": 0}]},
            ],
            "max_ops": 16,
        },
        "lowering_lambda": {
            "format": "bounded_program_v1",
            "schema_version": 1,
            "inputs": [{"name": "psi_0_value", "type": "bit"}],
            "outputs": [{"name": "x0", "type": "bit"}],
            "ops": [{"dst": "x0", "op": "GET", "args": ["psi_0_value"]}],
            "max_ops": 4,
        },
        "supports_macro_do": True,
        "supports_repeat_action_options": False,
        "lifting_psi": None,
        "complexity_limits": {
            "phi_max_ops": 32,
            "lambda_max_ops": 8,
            "psi_max_ops": 8,
            "max_constants": 32,
            "max_state_history": 1,
        },
    }
    anomaly_buffer = {
        "base_ontology_hash": "0" * 64,
        "signals": {"worst_regimes": [], "worst_families": []},
    }
    proposals = propose(anomaly_buffer, base_ontology, {}, {})
    assert proposals
    for prop in proposals:
        patch_ops = prop["ontology_patch"]["ops"]
        phi_ops = [op for op in patch_ops if op.get("op") == "replace_phi"]
        assert phi_ops
        phi_prog = phi_ops[0]["phi"]
        for out_name in ("x0", "x1", "x2", "x3"):
            assert _output_depends_on_o_t(phi_prog, out_name)
