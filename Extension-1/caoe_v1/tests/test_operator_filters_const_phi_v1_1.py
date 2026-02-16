from __future__ import annotations

from sleep.operators.coarse_grain_merge_v1 import propose
from sleep.synth.degeneracy_v1 import is_degenerate_phi


def test_operator_filters_const_phi_v1_1() -> None:
    base_ontology = {
        "format": "ontology_spec_v1_1",
        "schema_version": 1,
        "ontology_hash": "0" * 64,
        "isa_version": "caoe_absop_isa_v1_2",
        "symbols": [{"name": "x0", "type": "bit", "domain": {"kind": "bit"}}],
        "measurement_phi": {
            "format": "bounded_program_v1",
            "schema_version": 1,
            "inputs": [
                {"name": "o_t", "type": "bitvec", "width": 32},
                {"name": "t", "type": "int"},
            ],
            "outputs": [{"name": "x0", "type": "bit"}],
            "ops": [{"dst": "x0", "op": "CONST", "args": [{"bit": 0}]}],
            "max_ops": 4,
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
            "phi_max_ops": 16,
            "lambda_max_ops": 8,
            "psi_max_ops": 8,
            "max_constants": 16,
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
        assert not is_degenerate_phi(phi_prog)
