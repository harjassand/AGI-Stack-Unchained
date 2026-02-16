from __future__ import annotations

from cdel.v1_8r.metabolism_v1.workvec import WorkVec
import os

from cdel.v2_0 import constants as v2_constants
from cdel.v2_0.constants import require_constants
from cdel.v2_0.efficiency import scalar_gate, vector_dominance, work_cost


def test_efficiency_gate_scalar_and_vector() -> None:
    os.environ.pop("META_CORE_ROOT", None)
    v2_constants.require_constants.cache_clear()
    v2_constants.meta_identities.cache_clear()
    constants = require_constants()
    weights = constants["WORK_COST_WEIGHTS_V1"]
    rho_min_num = int(constants["RHO_MET_MIN_NUM"])
    rho_min_den = int(constants["RHO_MET_MIN_DEN"])

    base = WorkVec(
        sha256_calls_total=100,
        canon_calls_total=100,
        sha256_bytes_total=1000,
        canon_bytes_total=1000,
        onto_ctx_hash_compute_calls_total=100,
    )
    patch = WorkVec(
        sha256_calls_total=90,
        canon_calls_total=100,
        sha256_bytes_total=900,
        canon_bytes_total=1000,
        onto_ctx_hash_compute_calls_total=90,
    )

    assert vector_dominance(base, patch) is True

    worse = WorkVec(
        sha256_calls_total=101,
        canon_calls_total=100,
        sha256_bytes_total=1000,
        canon_bytes_total=1000,
        onto_ctx_hash_compute_calls_total=100,
    )
    assert vector_dominance(base, worse) is False

    w_base = work_cost(base, weights)
    w_patch = work_cost(patch, weights)
    assert w_patch < w_base
    assert scalar_gate(w_base, w_patch, rho_min_num=rho_min_num, rho_min_den=rho_min_den) is True

    assert scalar_gate(w_base, w_base, rho_min_num=rho_min_num, rho_min_den=rho_min_den) is False
    assert scalar_gate(w_base, w_base + 1, rho_min_num=rho_min_num, rho_min_den=rho_min_den) is False
