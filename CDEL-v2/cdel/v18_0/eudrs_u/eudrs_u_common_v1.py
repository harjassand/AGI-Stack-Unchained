"""Shared constants/helpers for EUDRS-U v1.

This module is RE2 and must remain deterministic and fail-closed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..omega_common_v1 import OmegaV18Error, fail, repo_root
from .eudrs_u_hash_v1 import gcj1_loads_and_verify_canonical

SCHEMA_EUDRS_U_PROMOTION_SUMMARY_V1 = "eudrs_u_promotion_summary_v1"
SCHEMA_EUDRS_U_ROOT_TUPLE_V1 = "eudrs_u_root_tuple_v1"
SCHEMA_EUDRS_U_SYSTEM_MANIFEST_V1 = "eudrs_u_system_manifest_v1"

SCHEMA_ACTIVE_ROOT_TUPLE_REF_V1 = "active_root_tuple_ref_v1"

EUDRS_U_STATE_DIRNAME = "eudrs_u"
EUDRS_U_EVIDENCE_DIR_REL = f"{EUDRS_U_STATE_DIRNAME}/evidence"
EUDRS_U_STAGED_REGISTRY_TREE_REL = f"{EUDRS_U_STATE_DIRNAME}/staged_registry_tree"

EUDRS_U_REGISTRY_PREFIX = "polymath/registry/eudrs_u"
EUDRS_U_ACTIVE_POINTER_REL = f"{EUDRS_U_REGISTRY_PREFIX}/active/active_root_tuple_ref_v1.json"


def load_active_root_tuple_pointer(*, root: Path | None = None) -> dict[str, Any] | None:
    """Load the currently-active root tuple pointer from the repo (if present).

    Returns None if the pointer file does not exist.
    """

    base = repo_root() if root is None else Path(root).resolve()
    path = base / EUDRS_U_ACTIVE_POINTER_REL
    if not path.exists():
        return None
    if not path.is_file():
        fail("SCHEMA_FAIL")
    payload = gcj1_loads_and_verify_canonical(path.read_bytes())
    if not isinstance(payload, dict):
        fail("SCHEMA_FAIL")
    return dict(payload)


__all__ = [
    "EUDRS_U_ACTIVE_POINTER_REL",
    "EUDRS_U_EVIDENCE_DIR_REL",
    "EUDRS_U_REGISTRY_PREFIX",
    "EUDRS_U_STAGED_REGISTRY_TREE_REL",
    "EUDRS_U_STATE_DIRNAME",
    "OmegaV18Error",
    "SCHEMA_ACTIVE_ROOT_TUPLE_REF_V1",
    "SCHEMA_EUDRS_U_PROMOTION_SUMMARY_V1",
    "SCHEMA_EUDRS_U_ROOT_TUPLE_V1",
    "SCHEMA_EUDRS_U_SYSTEM_MANIFEST_V1",
    "load_active_root_tuple_pointer",
]
