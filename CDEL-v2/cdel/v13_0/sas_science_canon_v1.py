"""Canonicalization for SAS-Science v13.0."""

from __future__ import annotations

from typing import Any


def canonicalize_law(
    *,
    ir: dict[str, Any],
    fit_receipt: dict[str, Any],
    ir_policy: dict[str, Any],
) -> dict[str, Any]:
    law_kind = "NON_NEWTON_V1"
    kind = ir.get("theory_kind")
    p = int(ir.get("force_law", {}).get("norm_pow_p") or 0)
    coeff = ir.get("force_law", {}).get("coeff_sharing")

    if kind == "CANDIDATE_NBODY_POWERLAW_V1" and p == 3 and coeff == "SOURCE_MASS_ONLY_V1":
        law_kind = "NEWTON_NBODY_V1"
    if kind == "CANDIDATE_CENTRAL_POWERLAW_V1" and p == 3:
        law_kind = "NEWTON_CENTRAL_V1"

    params = {}
    factor = ir_policy.get("param_factorization_kind")
    if factor == "MU_ONLY_V1":
        fit_params = fit_receipt.get("params_fitted") if isinstance(fit_receipt, dict) else {}
        if isinstance(fit_params, dict):
            if "mu_sources_q32" in fit_params:
                params["mu_sources_q32"] = fit_params.get("mu_sources_q32")
            if "k_param_q32" in fit_params:
                params["k_param_q32"] = fit_params.get("k_param_q32")
    return {"law_kind": law_kind, "params": params}


__all__ = ["canonicalize_law"]
