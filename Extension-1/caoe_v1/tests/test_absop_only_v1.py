import sys
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from sleep.absop_isa_v1_2 import ALLOWED_OP_IDS, propose_candidates, validate_op_ids  # noqa: E402
from state.proposer_state_store_v1 import default_state  # noqa: E402


def _base_objects():
    base_ontology = {
        "format": "ontology_spec_v1_1",
        "schema_version": 1,
        "ontology_hash": "0" * 64,
        "isa_version": "caoe_absop_isa_v1_2",
        "symbols": [],
        "measurement_phi": {
            "format": "bounded_program_v1",
            "schema_version": 1,
            "inputs": [],
            "outputs": [{"name": "y", "type": "bit"}],
            "ops": [],
            "max_ops": 1,
        },
        "lowering_lambda": {
            "format": "bounded_program_v1",
            "schema_version": 1,
            "inputs": [],
            "outputs": [{"name": "x", "type": "bit"}],
            "ops": [],
            "max_ops": 1,
        },
        "supports_macro_do": False,
        "supports_repeat_action_options": False,
        "lifting_psi": None,
        "complexity_limits": {
            "phi_max_ops": 1,
            "lambda_max_ops": 1,
            "psi_max_ops": 1,
            "max_constants": 4,
            "max_state_history": 1,
        },
    }
    base_mech = {"format": "mechanism_registry_v1_1", "schema_version": 1, "mechanisms": []}
    anomaly_buffer = {
        "format": "caoe_anomaly_buffer_v1",
        "schema_version": 1,
        "epoch_id": "e1",
        "base_ontology_hash": "0" * 64,
        "signals": {
            "worst_regimes": [
                {"regime_id": "r1", "success": 0.2, "efficiency": 0.3}
            ],
            "worst_families": [],
            "global": {
                "heldout_worst_case_success": 0.2,
                "heldout_worst_case_efficiency": 0.3,
                "heldout_mdl_bits": 100,
                "leakage_sensitivity": 0.1,
                "relabel_sensitivity": 0.1,
            },
        },
    }
    return base_ontology, base_mech, anomaly_buffer


def test_absop_only_v1():
    base_ontology, base_mech, anomaly_buffer = _base_objects()
    state = default_state()
    proposals = propose_candidates(
        anomaly_buffer=anomaly_buffer,
        base_ontology=base_ontology,
        base_mech=base_mech,
        proposer_state=state,
        epoch_num=1,
    )
    for proposal in proposals:
        assert proposal["op_id"] in ALLOWED_OP_IDS

    with pytest.raises(Exception):
        validate_op_ids([{"op_id": "BAD_OP"}])
