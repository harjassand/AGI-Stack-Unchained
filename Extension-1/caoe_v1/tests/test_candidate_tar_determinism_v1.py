import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from api_v1 import canonical_json_bytes  # noqa: E402
from artifacts.candidate_manifest_builder_v1 import build_manifest  # noqa: E402
from artifacts.candidate_tar_writer_v1 import build_candidate_tar_bytes  # noqa: E402


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
    return base_ontology, base_mech


def test_candidate_tar_determinism_v1():
    base_ontology, base_mech = _base_objects()
    ontology_patch = {
        "format": "ontology_patch_v1_1",
        "schema_version": 1,
        "base_ontology_hash": "0" * 64,
        "isa_version": "caoe_absop_isa_v1_2",
        "ops": [],
        "claimed_obligations": {
            "requires_c_do": False,
            "requires_c_mdl": True,
            "requires_c_inv": True,
            "requires_c_anti": True,
        },
        "predicted_gains": {
            "delta_mdl_bits": 0,
            "delta_worst_case_success": 0.0,
            "delta_efficiency": 0.0,
        },
    }
    mech_diff = {
        "format": "mechanism_registry_diff_v1_1",
        "schema_version": 1,
        "base_mech_hash": "0" * 64,
        "ops": [],
    }
    programs = {"programs/phi.bp": canonical_json_bytes({"p": 1})}

    manifest = build_manifest(
        base_ontology=base_ontology,
        base_mech=base_mech,
        suite_id_dev="dev_suite",
        suite_id_heldout="heldout_suite",
        claimed_supports_macro_do=False,
        ontology_patch=ontology_patch,
        mechanism_diff=mech_diff,
        programs_by_path=programs,
    )

    tar1 = build_candidate_tar_bytes(manifest, ontology_patch, mech_diff, programs)
    tar2 = build_candidate_tar_bytes(manifest, ontology_patch, mech_diff, programs)
    assert tar1 == tar2
