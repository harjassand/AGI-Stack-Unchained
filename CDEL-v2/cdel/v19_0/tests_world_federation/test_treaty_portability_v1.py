from __future__ import annotations

import json
import sys
from pathlib import Path

_CDEL_ROOT = Path(__file__).resolve().parents[3]
if str(_CDEL_ROOT) not in sys.path:
    sys.path.insert(0, str(_CDEL_ROOT))

from cdel.v19_0.federation.check_ok_overlap_signature_v1 import check_ok_overlap_signature
from cdel.v19_0.federation.check_treaty_coherence_v1 import check_treaty_coherence
from cdel.v19_0.federation.check_treaty_v1 import check_treaty
from cdel.v19_0.federation.ok_ican_v1 import DEFAULT_ICAN_PROFILE
from cdel.v19_0.federation.portability_protocol_v1 import adjudicate_portability
from cdel.v19_0.tests_world_federation.helpers import (
    artifact_store,
    budget,
    make_ok_signature,
    make_treaty,
    make_translator_bundle,
    overlap_id,
    with_id,
)


def test_pinned_ok_signature_accepts() -> None:
    pins = Path(__file__).resolve().parents[1] / "federation" / "pins"
    signature = json.loads((pins / "ok_overlap_signature_v1.json").read_text(encoding="utf-8"))
    receipt = check_ok_overlap_signature(signature=signature, budget_spec=budget())
    assert receipt["outcome"] == "ACCEPT"


def test_treaty_missing_translation_safe_split() -> None:
    ok_signature = make_ok_signature()
    phi_bundle = make_translator_bundle(
        [
            {"op": "TEST", "path": "/missing", "value": 1},
        ]
    )
    psi_bundle = make_translator_bundle([])

    obj_a = {"kind": "task", "x": 1}
    obj_b = {"kind": "task", "x": 2}
    obj_a_id = overlap_id(obj_a)
    obj_b_id = overlap_id(obj_b)

    treaty = make_treaty(
        ok_signature_id=ok_signature["overlap_signature_id"],
        phi_bundle_id=phi_bundle["translator_bundle_id"],
        psi_bundle_id=psi_bundle["translator_bundle_id"],
        overlap_test_set_ids=[obj_a_id, obj_b_id],
        dispute_policy="SAFE_SPLIT",
    )

    store = artifact_store(ok_signature, phi_bundle, psi_bundle, treaty)
    receipt = check_treaty(
        treaty=treaty,
        artifact_store=store,
        overlap_objects_by_id={obj_a_id: obj_a, obj_b_id: obj_b},
        witnesses_by_input_id=None,
        source_checker=lambda _obj: True,
        target_checker=lambda _obj: True,
        budget_spec=budget("SAFE_SPLIT"),
    )

    assert receipt["outcome"] == "SAFE_SPLIT"
    assert receipt["reason_code"] == "TRANSLATOR_NON_TOTAL"


def test_treaty_reject_without_valid_refutation_is_safe_split() -> None:
    ok_signature = make_ok_signature()
    phi_bundle = make_translator_bundle([])
    psi_bundle = make_translator_bundle([])

    obj = {"kind": "claim", "score": 1}
    obj_id = overlap_id(obj)

    treaty = make_treaty(
        ok_signature_id=ok_signature["overlap_signature_id"],
        phi_bundle_id=phi_bundle["translator_bundle_id"],
        psi_bundle_id=psi_bundle["translator_bundle_id"],
        overlap_test_set_ids=[obj_id],
        dispute_policy="SAFE_SPLIT",
    )

    store = artifact_store(ok_signature, phi_bundle, psi_bundle, treaty)
    receipt = check_treaty(
        treaty=treaty,
        artifact_store=store,
        overlap_objects_by_id={obj_id: obj},
        witnesses_by_input_id=None,
        source_checker=lambda _obj: True,
        target_checker=lambda _obj: False,
        budget_spec=budget("SAFE_SPLIT"),
    )

    assert receipt["outcome"] == "SAFE_SPLIT"
    assert receipt["reason_code"] == "DISPUTE_AMBIGUOUS"

    portability = adjudicate_portability(
        treaty=treaty,
        artifact_store=store,
        overlap_objects_by_id={obj_id: obj},
        witnesses_by_input_id=None,
        source_checker=lambda _obj: True,
        target_checker=lambda _obj: False,
        coherence_paths=None,
        ican_profile_id=DEFAULT_ICAN_PROFILE["profile_id"],
        budget_spec=budget("SAFE_SPLIT"),
    )
    assert portability["portability_status"] == "SAFE_SPLIT"
    assert portability["outcome"] == "SAFE_SPLIT"
    assert portability["binds_local_acceptance"] is False


def test_treaty_path_dependence_non_commutative_safe_split() -> None:
    ok_signature = make_ok_signature()

    bundle_ab = make_translator_bundle([{"op": "ADD", "path": "/route", "value": "AB"}])
    bundle_bc = make_translator_bundle([{"op": "ADD", "path": "/route2", "value": "BC"}])
    bundle_ac = make_translator_bundle([{"op": "ADD", "path": "/route", "value": "AC"}])

    obj = {"kind": "portable", "value": 7}
    obj_id = overlap_id(obj)

    treaty_ab = make_treaty(
        ok_signature_id=ok_signature["overlap_signature_id"],
        phi_bundle_id=bundle_ab["translator_bundle_id"],
        psi_bundle_id=bundle_ab["translator_bundle_id"],
        overlap_test_set_ids=[obj_id],
    )
    treaty_bc = make_treaty(
        ok_signature_id=ok_signature["overlap_signature_id"],
        phi_bundle_id=bundle_bc["translator_bundle_id"],
        psi_bundle_id=bundle_bc["translator_bundle_id"],
        overlap_test_set_ids=[obj_id],
    )
    treaty_ac = make_treaty(
        ok_signature_id=ok_signature["overlap_signature_id"],
        phi_bundle_id=bundle_ac["translator_bundle_id"],
        psi_bundle_id=bundle_ac["translator_bundle_id"],
        overlap_test_set_ids=[obj_id],
    )

    store = artifact_store(
        ok_signature,
        bundle_ab,
        bundle_bc,
        bundle_ac,
        treaty_ab,
        treaty_bc,
        treaty_ac,
    )

    coherence = check_treaty_coherence(
        treaty_ab=treaty_ab,
        treaty_bc=treaty_bc,
        treaty_ac=treaty_ac,
        artifact_store=store,
        overlap_objects_by_id={obj_id: obj},
        ican_profile_id=DEFAULT_ICAN_PROFILE["profile_id"],
        budget_spec=budget("SAFE_SPLIT"),
    )

    assert coherence["outcome"] == "SAFE_SPLIT"
    assert coherence["reason_code"] == "COMMUTATIVITY_FAIL"


def test_treaty_no_new_acceptance_path_safe_split() -> None:
    ok_signature = make_ok_signature()
    phi_bundle = make_translator_bundle([])
    psi_bundle = make_translator_bundle([])

    obj = {"kind": "claim", "score": 42}
    obj_id = overlap_id(obj)
    treaty = make_treaty(
        ok_signature_id=ok_signature["overlap_signature_id"],
        phi_bundle_id=phi_bundle["translator_bundle_id"],
        psi_bundle_id=psi_bundle["translator_bundle_id"],
        overlap_test_set_ids=[obj_id],
        dispute_policy="SAFE_SPLIT",
    )
    store = artifact_store(ok_signature, phi_bundle, psi_bundle, treaty)

    receipt = check_treaty(
        treaty=treaty,
        artifact_store=store,
        overlap_objects_by_id={obj_id: obj},
        witnesses_by_input_id=None,
        source_checker=lambda _obj: False,
        target_checker=lambda _obj: True,
        budget_spec=budget("SAFE_SPLIT"),
    )
    assert receipt["outcome"] == "SAFE_SPLIT"
    assert receipt["reason_code"] == "NO_NEW_ACCEPTANCE_PATH"


def test_portability_preserves_safe_halt_on_missing_ok_signature() -> None:
    phi_bundle = make_translator_bundle([])
    psi_bundle = make_translator_bundle([])
    obj = {"kind": "portable", "x": 9}
    obj_id = overlap_id(obj)

    treaty = make_treaty(
        ok_signature_id="sha256:" + ("f" * 64),
        phi_bundle_id=phi_bundle["translator_bundle_id"],
        psi_bundle_id=psi_bundle["translator_bundle_id"],
        overlap_test_set_ids=[obj_id],
        dispute_policy="SAFE_SPLIT",
    )
    # Keep treaty hash valid after changing referenced OK signature id.
    treaty = with_id({k: v for k, v in treaty.items() if k != "treaty_id"}, "treaty_id")

    store = artifact_store(phi_bundle, psi_bundle, treaty)
    portability = adjudicate_portability(
        treaty=treaty,
        artifact_store=store,
        overlap_objects_by_id={obj_id: obj},
        witnesses_by_input_id=None,
        source_checker=lambda _obj: True,
        target_checker=lambda _obj: True,
        coherence_paths=None,
        ican_profile_id=DEFAULT_ICAN_PROFILE["profile_id"],
        budget_spec=budget("SAFE_SPLIT"),
    )
    assert portability["outcome"] == "SAFE_HALT"
