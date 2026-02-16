import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from dawn.learner_v1 import update_state  # noqa: E402
from state.proposer_state_store_v1 import default_state  # noqa: E402


def test_state_update_determinism_v1():
    state = default_state()
    evaluations = [
        {
            "candidate_id": "a" * 64,
            "op_id": "ABSOP_COARSE_GRAIN_MERGE_V1",
            "decision": "PASS",
            "failed_contract": None,
            "heldout_worst_case_success": 0.6,
            "heldout_worst_case_efficiency": 0.7,
            "heldout_mdl_bits": 90,
            "heldout_mdl_improvement_bits": 10,
            "anti_pass": True,
            "do_pass": True,
        },
        {
            "candidate_id": "b" * 64,
            "op_id": "ABSOP_TEMPLATE_EXTRACT_V1",
            "decision": "FAIL",
            "failed_contract": "C-ANTI",
            "heldout_worst_case_success": 0.4,
            "heldout_worst_case_efficiency": 0.4,
            "heldout_mdl_bits": 110,
            "heldout_mdl_improvement_bits": -10,
            "anti_pass": False,
            "do_pass": True,
        },
    ]
    selection = {"selected_candidate_id": "a" * 64}
    anomaly_buffer = {
        "signals": {
            "worst_regimes": [
                {"regime_id": "r1", "success": 0.1, "efficiency": 0.2},
                {"regime_id": "r2", "success": 0.2, "efficiency": 0.3},
            ],
            "worst_families": [],
        }
    }

    updated = update_state(
        state=state,
        evaluations=evaluations,
        selection=selection,
        epoch_num=1,
        anomaly_buffer=anomaly_buffer,
    )

    assert updated["current_epoch"] == 1
    assert updated["operator_weights"]["ABSOP_COARSE_GRAIN_MERGE_V1"] == 1050
    assert updated["operator_weights"]["ABSOP_TEMPLATE_EXTRACT_V1"] == 800
    assert updated["operator_quarantine_until_epoch"]["ABSOP_TEMPLATE_EXTRACT_V1"] == 4
    assert updated["history"][-1]["decision"] == "PASS"
    assert updated["history"][-1]["selected_candidate_id"] == "a" * 64
    assert updated["history"][-1]["any_c_anti_fail"] is True
