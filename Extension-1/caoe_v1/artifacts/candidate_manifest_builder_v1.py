"""Candidate manifest construction for CAOE v1 proposer."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

base_dir = Path(__file__).resolve().parents[1]
if str(base_dir) not in sys.path:
    sys.path.insert(0, str(base_dir))

from api_v1 import canonical_json_bytes  # noqa: E402
from artifacts.ids_v1 import candidate_id as compute_candidate_id  # noqa: E402
from artifacts.ids_v1 import mechanism_hash, ontology_hash  # noqa: E402

ZERO_HASH = "0" * 64


def extract_suite_id(suitepack: Any) -> str:
    if isinstance(suitepack, dict):
        for key in ("suite_id", "suitepack_id"):
            if key in suitepack and isinstance(suitepack[key], str):
                return suitepack[key]
        if "suite_manifest" in suitepack and isinstance(suitepack["suite_manifest"], dict):
            nested = suitepack["suite_manifest"]
            for key in ("suite_id", "suitepack_id"):
                if key in nested and isinstance(nested[key], str):
                    return nested[key]
    raise ValueError("suitepack_dev missing suite_id/suitepack_id")


def build_manifest(
    base_ontology: Any,
    base_mech: Any,
    suite_id_dev: str,
    suite_id_heldout: str,
    claimed_supports_macro_do: bool,
    ontology_patch: Any,
    mechanism_diff: Any | None,
    programs_by_path: dict[str, bytes],
) -> dict[str, Any]:
    base_ontology_hash = ontology_hash(base_ontology)
    base_mech_hash = mechanism_hash(base_mech)
    isa_version = (
        base_ontology.get("isa_version")
        if isinstance(base_ontology, dict)
        else "caoe_absop_isa_v1_2"
    )
    manifest = {
        "format": "caoe_candidate_manifest_v1_1",
        "schema_version": 1,
        "candidate_id": ZERO_HASH,
        "isa_version": str(isa_version or "caoe_absop_isa_v1_2"),
        "base_ontology_hash": base_ontology_hash,
        "base_mech_hash": base_mech_hash,
        "target_env_id": "switchboard_v1",
        "suite_ids": {"dev": suite_id_dev, "heldout": suite_id_heldout},
        "claimed_supports_macro_do": bool(claimed_supports_macro_do),
    }
    # Compute candidate_id using the manifest placeholder value for determinism.
    cid = compute_candidate_id(manifest, ontology_patch, mechanism_diff, programs_by_path)
    manifest["candidate_id"] = cid
    return manifest


def canonical_manifest_bytes(manifest: dict[str, Any]) -> bytes:
    return canonical_json_bytes(manifest)
