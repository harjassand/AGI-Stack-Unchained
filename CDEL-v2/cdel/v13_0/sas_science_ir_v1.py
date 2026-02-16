"""SAS-Science theory IR helpers (v13.0)."""

from __future__ import annotations

import re
from typing import Any

from ..v1_7r.canon import CanonError, canon_bytes, sha256_prefixed
from .sas_science_math_v1 import parse_q32_obj

SCHEMA_VERSION = "sas_science_theory_ir_v1"

THEORY_KINDS = {
    "BASELINE_CONST_VEL_V1",
    "BASELINE_HOOKE_CENTRAL_V1",
    "CANDIDATE_CENTRAL_POWERLAW_V1",
    "CANDIDATE_NBODY_POWERLAW_V1",
}

VECTOR_FORM = "DISPLACEMENT_OVER_NORM_POW_V1"
COEFF_SHARING = "SOURCE_MASS_ONLY_V1"

_ALLOWED_BODY_RE = re.compile(r"^[A-Za-z0-9_\-]+$")


class SASScienceIRError(CanonError):
    pass


def _fail(reason: str) -> None:
    raise SASScienceIRError(reason)


def compute_theory_id(ir: dict[str, Any]) -> str:
    payload = dict(ir)
    payload["theory_id"] = ""
    return sha256_prefixed(canon_bytes(payload))


def _count_params(params: dict[str, Any]) -> int:
    count = 0
    if "mu_sources_q32" in params:
        mu = params.get("mu_sources_q32")
        if isinstance(mu, list):
            count += len(mu)
    if "mass_params_q32" in params:
        mp = params.get("mass_params_q32")
        if isinstance(mp, list):
            count += len(mp)
    if "G_param_q32" in params and params.get("G_param_q32") is not None:
        count += 1
    if "k_param_q32" in params and params.get("k_param_q32") is not None:
        count += 1
    return int(count)


def compute_complexity(ir: dict[str, Any]) -> dict[str, int]:
    targets = ir.get("target_bodies") or []
    sources = ir.get("source_bodies") or []
    params = ir.get("parameters") or {}
    param_count = _count_params(params)
    if ir.get("theory_kind") == "BASELINE_CONST_VEL_V1":
        term_count = 0
    else:
        term_count = 1
    node_count = 10 + len(targets) + len(sources) + param_count
    return {
        "node_count": int(node_count),
        "term_count": int(term_count),
        "param_count": int(param_count),
    }


def _validate_body_list(name: str, bodies: Any) -> list[str]:
    if not isinstance(bodies, list):
        _fail("INVALID:SCHEMA_FAIL")
    out: list[str] = []
    for item in bodies:
        if not isinstance(item, str) or not item:
            _fail("INVALID:SCHEMA_FAIL")
        if not _ALLOWED_BODY_RE.match(item):
            _fail("INVALID:SCHEMA_FAIL")
        out.append(item)
    return out


def _scan_semantic_tamper(ir: dict[str, Any]) -> None:
    # Reject any keys that hint at time indexing or lookup tables.
    forbidden_keys = {"time", "time_index", "t_index", "lookup", "table"}
    stack: list[Any] = [ir]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            for k, v in cur.items():
                if isinstance(k, str) and k.lower() in forbidden_keys:
                    _fail("INVALID:IR_FORBIDDEN_TIME_DEPENDENCE")
                stack.append(v)
        elif isinstance(cur, list):
            stack.extend(cur)


def validate_ir(
    ir: dict[str, Any],
    *,
    manifest: dict[str, Any] | None = None,
    ir_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(ir, dict) or ir.get("ir_version") != SCHEMA_VERSION:
        _fail("INVALID:SCHEMA_FAIL")
    allowed_top = {
        "ir_version",
        "theory_kind",
        "target_bodies",
        "source_bodies",
        "force_law",
        "parameters",
        "complexity",
        "theory_id",
    }
    if set(ir.keys()) != allowed_top:
        extra = set(ir.keys()) - allowed_top
        if extra:
            _fail(f"INVALID:IR_EXTRA_FIELD:{sorted(extra)[0]}")
        _fail("INVALID:SCHEMA_FAIL")
    theory_kind = ir.get("theory_kind")
    if theory_kind not in THEORY_KINDS:
        _fail("INVALID:SCHEMA_FAIL")

    targets = _validate_body_list("target_bodies", ir.get("target_bodies"))
    sources = _validate_body_list("source_bodies", ir.get("source_bodies"))

    force_law = ir.get("force_law")
    if not isinstance(force_law, dict):
        _fail("INVALID:SCHEMA_FAIL")
    allowed_force = {"vector_form", "norm_pow_p", "coeff_sharing"}
    if set(force_law.keys()) != allowed_force:
        extra = set(force_law.keys()) - allowed_force
        if extra:
            _fail(f"INVALID:IR_EXTRA_FIELD:{sorted(extra)[0]}")
        _fail("INVALID:SCHEMA_FAIL")
    if force_law.get("vector_form") != VECTOR_FORM:
        _fail("INVALID:SCHEMA_FAIL")
    if force_law.get("coeff_sharing") != COEFF_SHARING:
        _fail("INVALID:SCHEMA_FAIL")
    p = force_law.get("norm_pow_p")
    if p not in (1, 2, 3, 4):
        _fail("INVALID:SCHEMA_FAIL")

    params = ir.get("parameters")
    if not isinstance(params, dict):
        _fail("INVALID:SCHEMA_FAIL")
    allowed_params = {"mu_sources_q32", "mass_params_q32", "G_param_q32", "k_param_q32"}
    extra_params = set(params.keys()) - allowed_params
    if extra_params:
        _fail(f"INVALID:IR_EXTRA_FIELD:{sorted(extra_params)[0]}")

    complexity = ir.get("complexity")
    if not isinstance(complexity, dict):
        _fail("INVALID:SCHEMA_FAIL")
    allowed_complexity = {"node_count", "term_count", "param_count"}
    if set(complexity.keys()) != allowed_complexity:
        extra = set(complexity.keys()) - allowed_complexity
        if extra:
            _fail(f"INVALID:IR_EXTRA_FIELD:{sorted(extra)[0]}")
        _fail("INVALID:SCHEMA_FAIL")
    expected = compute_complexity(ir)
    if complexity.get("node_count") != expected["node_count"]:
        _fail("INVALID:COMPLEXITY_GATE_FAIL")
    if complexity.get("term_count") != expected["term_count"]:
        _fail("INVALID:COMPLEXITY_GATE_FAIL")
    if complexity.get("param_count") != expected["param_count"]:
        _fail("INVALID:COMPLEXITY_GATE_FAIL")

    theory_id = ir.get("theory_id")
    if not isinstance(theory_id, str):
        _fail("INVALID:SCHEMA_FAIL")
    expected_id = compute_theory_id(ir)
    if theory_id != expected_id:
        _fail("INVALID:THEORY_ID_MISMATCH")

    _scan_semantic_tamper(ir)

    # Policy-driven constraints
    if ir_policy:
        max_abs = ir_policy.get("max_abs_q32")
        try:
            max_abs_val = int(max_abs) if max_abs is not None else 2**63 - 1
        except Exception:
            max_abs_val = 2**63 - 1
        for key in ("mu_sources_q32", "mass_params_q32"):
            vals = params.get(key)
            if vals is None:
                continue
            if not isinstance(vals, list):
                _fail("INVALID:SCHEMA_FAIL")
            for item in vals:
                q = parse_q32_obj(item)
                if abs(int(q)) > max_abs_val:
                    _fail("INVALID:IR_CONSTANT_TOO_LARGE")
        for key in ("G_param_q32", "k_param_q32"):
            if key in params and params.get(key) is not None:
                q = parse_q32_obj(params.get(key))
                if abs(int(q)) > max_abs_val:
                    _fail("INVALID:IR_CONSTANT_TOO_LARGE")

        if expected["node_count"] > int(ir_policy.get("max_node_count", 80)):
            _fail("INVALID:COMPLEXITY_GATE_FAIL")
        if expected["term_count"] > int(ir_policy.get("max_term_count", 4)):
            _fail("INVALID:COMPLEXITY_GATE_FAIL")
        if expected["param_count"] > int(ir_policy.get("max_param_count", 4)):
            _fail("INVALID:COMPLEXITY_GATE_FAIL")

    # Manifest-driven constraints
    if manifest is not None:
        bodies = manifest.get("bodies")
        if isinstance(bodies, list):
            if targets != bodies:
                _fail("INVALID:SCHEMA_FAIL")
        frame_kind = manifest.get("frame_kind")
        if theory_kind in ("CANDIDATE_CENTRAL_POWERLAW_V1", "BASELINE_HOOKE_CENTRAL_V1"):
            if frame_kind == "HELIOCENTRIC_SUN_AT_ORIGIN_V1":
                if sources != ["Origin"]:
                    _fail("INVALID:SCHEMA_FAIL")
            elif frame_kind == "BARYCENTRIC_WITH_SUN_ROW_V1":
                if sources != ["Sun"]:
                    _fail("INVALID:SCHEMA_FAIL")
        if theory_kind == "CANDIDATE_NBODY_POWERLAW_V1":
            if not isinstance(bodies, list):
                _fail("INVALID:SCHEMA_FAIL")
            expected_sources = list(bodies)
            if frame_kind == "BARYCENTRIC_WITH_SUN_ROW_V1" and "Sun" not in expected_sources:
                expected_sources.append("Sun")
            if sources != expected_sources:
                _fail("INVALID:SCHEMA_FAIL")

    return ir


__all__ = [
    "SCHEMA_VERSION",
    "THEORY_KINDS",
    "compute_theory_id",
    "compute_complexity",
    "validate_ir",
    "SASScienceIRError",
]
