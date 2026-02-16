"""Pressure suite pack builder for v1.5r."""

from __future__ import annotations

from typing import Any

from ..canon import hash_json


def build_pressure_pack(
    *,
    frontier_hash: str,
    families: list[dict[str, Any]],
    n_per_family: int,
    pressure_level: int,
) -> dict[str, Any]:
    n_per_family = max(1, int(n_per_family))
    payload = {
        "schema": "pressure_pack_v1",
        "schema_version": 1,
        "pack_id": "",
        "frontier_hash": frontier_hash,
        "pressure_level": int(pressure_level),
        "families": [
            {"family_id": fam.get("family_id"), "theta_list": [{} for _ in range(n_per_family)]}
            for fam in families
            if isinstance(fam, dict)
        ],
    }
    payload["pack_id"] = hash_json(payload)
    return payload
