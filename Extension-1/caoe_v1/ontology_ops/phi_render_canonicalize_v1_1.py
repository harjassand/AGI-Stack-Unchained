"""Render-canonicalizing phi builder for CAOE v1.1."""

from __future__ import annotations

from typing import Any

from api_v1 import canonical_json_bytes


def _input_decl_for_canon(
    max_obs_dims: int,
    probe_steps_k: int,
    delta_threshold: int,
    *,
    mask_mode: str,
    pattern: str,
) -> dict[str, Any]:
    name = (
        f"o_t_canon_k{probe_steps_k}_thr{delta_threshold}_max{max_obs_dims}_"
        f"mode{mask_mode}_pat{pattern}"
    )
    return {"name": name, "type": "bitvec", "width": max_obs_dims}


def build_phi_program(
    base_phi: dict[str, Any],
    *,
    probe_steps_k: int,
    delta_threshold: int,
    max_obs_dims: int,
    mask_mode: str = "infer",
    pattern: str = "all",
    phi_max_ops: int,
) -> tuple[dict[str, Any], bytes]:
    outputs = base_phi.get("outputs") or []
    ops: list[dict[str, Any]] = []
    input_decl = _input_decl_for_canon(
        max_obs_dims,
        probe_steps_k,
        delta_threshold,
        mask_mode=mask_mode,
        pattern=pattern,
    )
    input_name = input_decl["name"]
    for idx, out_decl in enumerate(outputs):
        out_name = out_decl.get("name")
        if not out_name:
            raise ValueError("phi output name missing")
        ops.append({"dst": out_name, "op": "SELECT_BIT", "args": [input_name, idx]})
    if phi_max_ops and len(ops) > phi_max_ops:
        raise ValueError("phi program exceeds phi_max_ops")
    program = {
        "format": "bounded_program_v1",
        "schema_version": 1,
        "inputs": [input_decl],
        "outputs": outputs,
        "ops": ops,
        "max_ops": phi_max_ops,
    }
    return program, canonical_json_bytes(program)
