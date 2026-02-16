from __future__ import annotations

import sys
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BASE_DIR.parents[1]
CDEL_ROOT = REPO_ROOT / "CDEL-v2"
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
if str(CDEL_ROOT) not in sys.path:
    sys.path.insert(0, str(CDEL_ROOT))

from extensions.caoe_v1.eval import ccai_x_core_v1 as core  # noqa: E402
from extensions.caoe_v1.eval.suitepack_reader_v1 import EpisodeSpec, RegimeSpec, SuitepackV1  # noqa: E402
from extensions.caoe_v1.ids_v1 import ontology_hash  # noqa: E402
from extensions.caoe_v1.tests.helpers_v1 import make_base_ontology, make_lambda_constant  # noqa: E402


def _empty_transition() -> dict:
    return {
        "format": "bounded_program_v1",
        "schema_version": 1,
        "inputs": [],
        "outputs": [],
        "ops": [],
        "max_ops": 0,
    }


def test_macro_duration_accounting_v1_2(monkeypatch: pytest.MonkeyPatch) -> None:
    phi = {
        "format": "bounded_program_v1",
        "schema_version": 1,
        "inputs": [
            {"name": "o_t", "type": "bitvec", "width": 32},
            {"name": "t", "type": "int"},
        ],
        "outputs": [{"name": "x", "type": "bit"}],
        "ops": [{"dst": "x", "op": "CONST", "args": [{"bit": 0}]}],
        "max_ops": 4,
    }
    limits = {
        "phi_max_ops": 16,
        "lambda_max_ops": 8,
        "psi_max_ops": 8,
        "max_constants": 16,
        "max_state_history": 1,
    }
    base_ontology = make_base_ontology(phi, make_lambda_constant(0), None, False, limits)
    base_ontology["supports_repeat_action_options"] = True
    base_ontology["ontology_hash"] = ontology_hash(base_ontology)

    mechanism_registry = {
        "format": "mechanism_registry_v1",
        "schema_version": 1,
        "ontology_hash": base_ontology["ontology_hash"],
        "mechanisms": [
            {
                "mechanism_id": "repeat_action_option_v1_2",
                "inputs": [],
                "outputs": [],
                "transition": _empty_transition(),
                "params": {"action_id": 1, "repeat_steps": 4},
            }
        ],
    }

    regime = RegimeSpec(
        regime_id="r1",
        shift_family="fam",
        perm=list(range(20)),
        mask=[0] * 20,
    )
    episode = EpisodeSpec(
        episode_id="e1",
        regime_id="r1",
        goal={"x": 1},
        max_steps=4,
        initial_x=[0, 0, 0, 0],
        initial_n=[0] * 16,
    )
    suitepack = SuitepackV1(
        suite_id="suite",
        target_env_id="switchboard_v1",
        episodes=[episode],
        regimes={"r1": regime},
        shift_families={"fam": ["r1"]},
        suite_token=None,
    )

    def _plan_stub(*_args, **_kwargs):
        action_set = core.SwitchboardEnv.action_set()
        return {"type": "repeat_option", "id": 1, "repeat": 4, "action": action_set[1]}, (0, 0, 0, 0)

    monkeypatch.setattr(core, "_plan", _plan_stub)
    results = core.evaluate_suite(base_ontology, mechanism_registry, suitepack)
    assert results[0].steps_taken == 4
