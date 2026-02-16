"""Deterministic artifact loaders for v19 continuity checks."""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any, TypedDict

from ...v1_7r.canon import canon_bytes, load_canon_json
from .common_v1 import canon_hash_obj, ensure_sha256, fail, make_budget_tracker, require_relpath


class ArtifactRef(TypedDict):
    artifact_id: str
    artifact_relpath: str


class RegimeRef(TypedDict):
    C: ArtifactRef
    K: ArtifactRef
    E: ArtifactRef
    W: ArtifactRef
    T: ArtifactRef


class BudgetBundleV1(TypedDict):
    continuity_budget: dict[str, Any]
    translator_budget: dict[str, Any]
    receipt_translation_budget: dict[str, Any]
    totality_budget: dict[str, Any]


@dataclasses.dataclass(frozen=True)
class LoadedArtifact:
    ref: ArtifactRef
    path: Path
    payload: Any
    canonical_size: int


def _validate_artifact_ref(ref: dict[str, Any]) -> ArtifactRef:
    if not isinstance(ref, dict):
        fail("SCHEMA_ERROR", safe_halt=True)
    artifact_id = ensure_sha256(ref.get("artifact_id"), reason="ID_MISMATCH")
    artifact_relpath = require_relpath(ref.get("artifact_relpath"), reason="SCHEMA_ERROR")
    return ArtifactRef(artifact_id=artifact_id, artifact_relpath=artifact_relpath)


def canonical_artifact_id(payload: Any) -> str:
    return canon_hash_obj(payload)


def load_artifact_ref(store_root: Path, ref_raw: dict[str, Any]) -> LoadedArtifact:
    ref = _validate_artifact_ref(ref_raw)
    path = (store_root / ref["artifact_relpath"]).resolve()
    root = store_root.resolve()
    try:
        path.relative_to(root)
    except ValueError:
        fail("MISSING_ARTIFACT", safe_halt=True)

    if not path.exists() or not path.is_file():
        fail("MISSING_ARTIFACT", safe_halt=True)

    try:
        payload = load_canon_json(path)
    except Exception:
        fail("SCHEMA_ERROR", safe_halt=True)

    digest = canonical_artifact_id(payload)
    if digest != ref["artifact_id"]:
        fail("ID_MISMATCH", safe_halt=True)

    return LoadedArtifact(ref=ref, path=path, payload=payload, canonical_size=len(canon_bytes(payload)))


def maybe_load_artifact_ref(store_root: Path, ref_raw: dict[str, Any] | None) -> LoadedArtifact | None:
    if ref_raw is None:
        return None
    return load_artifact_ref(store_root, ref_raw)


def regime_ref_id(regime_ref: RegimeRef) -> str:
    return canon_hash_obj(regime_ref)


def load_regime_ref(store_root: Path, regime_raw: dict[str, Any]) -> tuple[RegimeRef, dict[str, LoadedArtifact]]:
    if not isinstance(regime_raw, dict):
        fail("SCHEMA_ERROR", safe_halt=True)
    keys = ["C", "K", "E", "W", "T"]
    if sorted(regime_raw.keys()) != sorted(keys):
        fail("SCHEMA_ERROR", safe_halt=True)

    loaded: dict[str, LoadedArtifact] = {}
    normalized: dict[str, ArtifactRef] = {}
    for key in keys:
        row = regime_raw.get(key)
        if not isinstance(row, dict):
            fail("SCHEMA_ERROR", safe_halt=True)
        loaded_artifact = load_artifact_ref(store_root, row)
        loaded[key] = loaded_artifact
        normalized[key] = loaded_artifact.ref

    return RegimeRef(
        C=normalized["C"],
        K=normalized["K"],
        E=normalized["E"],
        W=normalized["W"],
        T=normalized["T"],
    ), loaded


def load_budget_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(bundle, dict):
        fail("MISSING_BUDGET", safe_halt=True)
    required = [
        "continuity_budget",
        "translator_budget",
        "receipt_translation_budget",
        "totality_budget",
    ]
    out: dict[str, Any] = {}
    for key in required:
        value = bundle.get(key)
        if not isinstance(value, dict):
            fail("MISSING_BUDGET", safe_halt=True)
        out[key] = dict(value)
        make_budget_tracker(out[key])
    return out


def ensure_mapping(value: Any, *, reason: str = "SCHEMA_ERROR") -> dict[str, Any]:
    if not isinstance(value, dict):
        fail(reason, safe_halt=True)
    return value


def ensure_list(value: Any, *, reason: str = "SCHEMA_ERROR") -> list[Any]:
    if not isinstance(value, list):
        fail(reason, safe_halt=True)
    return value


__all__ = [
    "ArtifactRef",
    "BudgetBundleV1",
    "LoadedArtifact",
    "RegimeRef",
    "canonical_artifact_id",
    "ensure_list",
    "ensure_mapping",
    "load_artifact_ref",
    "load_budget_bundle",
    "load_regime_ref",
    "maybe_load_artifact_ref",
    "regime_ref_id",
]
