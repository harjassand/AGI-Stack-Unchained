"""Bundle helpers for SAS v11.0."""

from __future__ import annotations

from typing import Any

from ..v1_7r.canon import canon_bytes, sha256_prefixed


def _compute_bundle_id(bundle: dict[str, Any]) -> str:
    payload = dict(bundle)
    payload.pop("bundle_id", None)
    payload.pop("promotion_bundle_id", None)
    return sha256_prefixed(canon_bytes(payload))


def compute_architecture_bundle_id(bundle: dict[str, Any]) -> str:
    return _compute_bundle_id(bundle)


def compute_weights_bundle_id(bundle: dict[str, Any]) -> str:
    return _compute_bundle_id(bundle)


def compute_promotion_bundle_id(bundle: dict[str, Any]) -> str:
    return _compute_bundle_id(bundle)


__all__ = [
    "compute_architecture_bundle_id",
    "compute_weights_bundle_id",
    "compute_promotion_bundle_id",
]
