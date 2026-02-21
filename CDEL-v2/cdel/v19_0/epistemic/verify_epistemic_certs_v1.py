"""Replay verification for epistemic ECAC/EUFC wrapper certificates."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..common_v1 import canon_hash_obj, ensure_sha256, fail, validate_schema, verify_object_id
from .certs_v1 import compute_epistemic_certs


def _load_hash_bound(path: Path, *, schema_name: str, id_field: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        fail("SCHEMA_FAIL")
    if canon_hash_obj(payload) != "sha256:" + path.name.split(".", 1)[0].split("_", 1)[1]:
        fail("NONDETERMINISTIC")
    validate_schema(payload, schema_name)
    verify_object_id(payload, id_field=id_field)
    return payload


def verify_certs_bundle(
    *,
    capsule: dict[str, Any],
    graph: dict[str, Any],
    type_binding: dict[str, Any],
    objective_profile_id: str,
    cert_profile: dict[str, Any] | None,
    ecac: dict[str, Any],
    eufc: dict[str, Any],
    eufc_credit_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    computed = compute_epistemic_certs(
        capsule=capsule,
        graph=graph,
        type_binding=type_binding,
        objective_profile_id=objective_profile_id,
        cert_profile=cert_profile,
        eufc_credit_context=eufc_credit_context,
    )
    if canon_hash_obj(computed["ecac"]) != canon_hash_obj(ecac):
        fail("NONDETERMINISTIC")
    if canon_hash_obj(computed["eufc"]) != canon_hash_obj(eufc):
        fail("NONDETERMINISTIC")
    return {
        "status": "VALID",
        "ecac_id": ensure_sha256(ecac.get("ecac_id"), reason="SCHEMA_FAIL"),
        "eufc_id": ensure_sha256(eufc.get("eufc_id"), reason="SCHEMA_FAIL"),
    }


def verify_certs_state(state_root: Path, *, objective_profile_id: str) -> dict[str, Any]:
    epi_root = state_root / "epistemic"

    cap_path = sorted((epi_root / "capsules").glob("sha256_*.epistemic_capsule_v1.json"), key=lambda p: p.as_posix())
    graph_path = sorted((epi_root / "graphs").glob("sha256_*.qxwmr_graph_v1.json"), key=lambda p: p.as_posix())
    bind_path = sorted((epi_root / "type_bindings").glob("sha256_*.epistemic_type_binding_v1.json"), key=lambda p: p.as_posix())
    ecac_path = sorted((epi_root / "certs").glob("sha256_*.epistemic_ecac_v1.json"), key=lambda p: p.as_posix())
    eufc_path = sorted((epi_root / "certs").glob("sha256_*.epistemic_eufc_v1.json"), key=lambda p: p.as_posix())

    if not (len(cap_path) == len(graph_path) == len(bind_path) == len(ecac_path) == len(eufc_path) == 1):
        fail("MISSING_STATE_INPUT")

    capsule = _load_hash_bound(cap_path[0], schema_name="epistemic_capsule_v1", id_field="capsule_id")
    graph = _load_hash_bound(graph_path[0], schema_name="qxwmr_graph_v1", id_field="graph_id")
    binding = _load_hash_bound(bind_path[0], schema_name="epistemic_type_binding_v1", id_field="binding_id")
    ecac = _load_hash_bound(ecac_path[0], schema_name="epistemic_ecac_v1", id_field="ecac_id")
    eufc = _load_hash_bound(eufc_path[0], schema_name="epistemic_eufc_v1", id_field="eufc_id")
    cert_profile_id = ensure_sha256(ecac.get("cert_profile_id"), reason="SCHEMA_FAIL")
    if ensure_sha256(eufc.get("cert_profile_id"), reason="SCHEMA_FAIL") != cert_profile_id:
        fail("NONDETERMINISTIC")

    cert_profile: dict[str, Any] | None = None
    replay_profile_paths = sorted(
        (state_root / "epistemic" / "replay_inputs" / "contracts").glob("sha256_*.epistemic_cert_profile_v1.json"),
        key=lambda p: p.as_posix(),
    )
    if replay_profile_paths:
        matches: list[dict[str, Any]] = []
        for path in replay_profile_paths:
            payload = _load_hash_bound(
                path,
                schema_name="epistemic_cert_profile_v1",
                id_field="cert_profile_id",
            )
            if ensure_sha256(payload.get("cert_profile_id"), reason="SCHEMA_FAIL") == cert_profile_id:
                matches.append(payload)
        if len(matches) > 1:
            fail("NONDETERMINISTIC")
        if len(matches) == 1:
            cert_profile = matches[0]

    return verify_certs_bundle(
        capsule=capsule,
        graph=graph,
        type_binding=binding,
        objective_profile_id=objective_profile_id,
        cert_profile=cert_profile,
        ecac=ecac,
        eufc=eufc,
        eufc_credit_context=None,
    )


__all__ = ["verify_certs_bundle", "verify_certs_state"]
