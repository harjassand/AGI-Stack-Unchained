"""Constraint spec helpers for safety gating."""

from __future__ import annotations

from blake3 import blake3

from cdel.kernel.canon import canonical_json_bytes, canonicalize_spec


_ALLOWED_CONSTRAINT_KEYS = {
    "banned_tools",
    "max_steps",
    "max_file_writes",
    "allow_path_escape",
    "allow_network",
    "allow_subprocess",
}


def canonicalize_constraint_spec(spec: dict) -> dict:
    if not isinstance(spec, dict):
        raise ValueError("constraint spec must be an object")
    if spec.get("schema_version") != 1:
        raise ValueError("constraint spec schema_version must be 1")
    if spec.get("kind") != "constraint_spec":
        raise ValueError("constraint spec kind must be constraint_spec")
    domain = spec.get("domain")
    if not isinstance(domain, str) or not domain:
        raise ValueError("constraint spec domain must be string")
    constraints = spec.get("constraints")
    if not isinstance(constraints, dict):
        raise ValueError("constraint spec constraints must be object")
    extra = set(constraints.keys()) - _ALLOWED_CONSTRAINT_KEYS
    if extra:
        raise ValueError(f"constraint spec unknown keys: {sorted(extra)}")

    banned_tools = constraints.get("banned_tools", [])
    if not isinstance(banned_tools, list) or any(not isinstance(item, str) for item in banned_tools):
        raise ValueError("constraint spec banned_tools must be list of strings")
    max_steps = constraints.get("max_steps")
    if isinstance(max_steps, bool) or not isinstance(max_steps, int) or max_steps < 0:
        raise ValueError("constraint spec max_steps must be non-negative int")
    max_file_writes = constraints.get("max_file_writes")
    if isinstance(max_file_writes, bool) or not isinstance(max_file_writes, int) or max_file_writes < 0:
        raise ValueError("constraint spec max_file_writes must be non-negative int")
    allow_path_escape = constraints.get("allow_path_escape")
    if not isinstance(allow_path_escape, bool):
        raise ValueError("constraint spec allow_path_escape must be bool")
    allow_network = constraints.get("allow_network")
    if not isinstance(allow_network, bool):
        raise ValueError("constraint spec allow_network must be bool")
    allow_subprocess = constraints.get("allow_subprocess")
    if not isinstance(allow_subprocess, bool):
        raise ValueError("constraint spec allow_subprocess must be bool")

    return {
        "schema_version": 1,
        "kind": "constraint_spec",
        "domain": domain,
        "constraints": {
            "banned_tools": sorted(banned_tools),
            "max_steps": max_steps,
            "max_file_writes": max_file_writes,
            "allow_path_escape": allow_path_escape,
            "allow_network": allow_network,
            "allow_subprocess": allow_subprocess,
        },
    }


def constraint_spec_hash(spec: dict) -> str:
    canon = canonicalize_constraint_spec(spec)
    return blake3(canonical_json_bytes(canon)).hexdigest()


def canonicalize_constraints_payload(constraints: dict) -> dict:
    if not isinstance(constraints, dict):
        raise ValueError("constraints must be an object")
    if not constraints:
        return {}
    allowed = {"spec", "spec_hash", "safety_certificate"}
    extra = set(constraints.keys()) - allowed
    if extra:
        raise ValueError(f"constraints unknown keys: {sorted(extra)}")

    spec = constraints.get("spec")
    spec_hash = constraints.get("spec_hash")
    if not isinstance(spec, dict):
        raise ValueError("constraints spec must be object")
    if not isinstance(spec_hash, str) or not spec_hash:
        raise ValueError("constraints spec_hash must be string")
    canon_spec = canonicalize_constraint_spec(spec)
    actual_hash = constraint_spec_hash(canon_spec)
    if actual_hash != spec_hash:
        raise ValueError("constraints spec_hash mismatch")

    safety_cert = constraints.get("safety_certificate")
    canon_safety: dict | None = None
    if safety_cert is not None:
        if not isinstance(safety_cert, dict):
            raise ValueError("constraints safety_certificate must be object")
        if safety_cert.get("kind") == "stat_cert":
            canon_safety = canonicalize_spec(safety_cert)
        else:
            canon_safety = safety_cert

    return {
        "spec": canon_spec,
        "spec_hash": spec_hash,
        "safety_certificate": canon_safety,
    }
