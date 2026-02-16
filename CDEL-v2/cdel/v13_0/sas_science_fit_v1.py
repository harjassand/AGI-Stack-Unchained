"""Deterministic fitting for SAS-Science v13.0."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from fractions import Fraction
from typing import Any

from ..v1_7r.canon import canon_bytes, sha256_prefixed
from .sas_science_math_v1 import q32_from_fraction, q32_mul, q32_obj_from_int, round_half_even, parse_q32_obj


class SASScienceFitError(RuntimeError):
    pass


def _fail(reason: str) -> None:
    raise SASScienceFitError(reason)


def _now_utc() -> str:
    # Deterministic timestamp to keep content-addressed artifacts stable.
    return "1970-01-01T00:00:00Z"


def _accel_obs_q32(dataset: Any, body: str, k: int) -> list[int]:
    dt_q = dataset.dt_q32
    r_prev = dataset.positions_q32[body][k - 1]
    r_cur = dataset.positions_q32[body][k]
    r_next = dataset.positions_q32[body][k + 1]
    out: list[int] = []
    dt2 = int(dt_q) * int(dt_q)
    for idx in range(len(r_cur)):
        diff2 = int(r_next[idx]) - 2 * int(r_cur[idx]) + int(r_prev[idx])
        num = diff2 * (1 << 64)
        a_q = round_half_even(num, dt2) if dt2 != 0 else 0
        out.append(int(a_q))
    return out


def _sqrt_q64_to_q32(value_q64: int) -> int:
    import math
    r = math.isqrt(value_q64)
    lower = r * r
    upper = (r + 1) * (r + 1)
    if value_q64 - lower < upper - value_q64:
        return r
    if value_q64 - lower > upper - value_q64:
        return r + 1
    return r if (r % 2 == 0) else (r + 1)


def _term_vector(dataset: Any, body: str, k: int, *, source: str, p: int) -> list[int]:
    dim = len(dataset.positions_q32[body][k])
    pos_body = dataset.positions_q32[body][k]
    if source == "Origin":
        displacement = [-int(v) for v in pos_body]
    else:
        pos_src = dataset.positions_q32[source][k]
        displacement = [int(pos_src[i]) - int(pos_body[i]) for i in range(dim)]
    sum_d2 = 0
    for comp in displacement:
        sum_d2 += int(comp) * int(comp)
    if sum_d2 == 0:
        return [0 for _ in range(dim)]
    norm_q = _sqrt_q64_to_q32(sum_d2)
    if norm_q == 0:
        return [0 for _ in range(dim)]
    norm_pow = int(norm_q) ** int(p)
    q_pow = 1 << (32 * int(p))
    out: list[int] = []
    for comp in displacement:
        num = int(comp) * q_pow
        term_q = round_half_even(num, norm_pow) if norm_pow != 0 else 0
        out.append(int(term_q))
    return out


def _solve_linear_system(A: list[list[Fraction]], b: list[Fraction]) -> list[Fraction] | None:
    n = len(A)
    if n == 0:
        return []
    # augment
    aug = [list(A[i]) + [b[i]] for i in range(n)]
    for col in range(n):
        pivot = None
        for r in range(col, n):
            if aug[r][col] != 0:
                pivot = r
                break
        if pivot is None:
            return None
        if pivot != col:
            aug[col], aug[pivot] = aug[pivot], aug[col]
        pivot_val = aug[col][col]
        for j in range(col, n + 1):
            aug[col][j] = aug[col][j] / pivot_val
        for r in range(n):
            if r == col:
                continue
            factor = aug[r][col]
            if factor == 0:
                continue
            for j in range(col, n + 1):
                aug[r][j] = aug[r][j] - factor * aug[col][j]
    return [aug[i][n] for i in range(n)]


def _fit_linear(
    *,
    dataset: Any,
    targets: list[str],
    sources: list[str],
    p: int,
    eval_start: int,
    eval_end: int,
) -> list[int] | None:
    P = len(sources)
    if P <= 0:
        return []
    # normal equations (integer numerators)
    A_num = [[0 for _ in range(P)] for _ in range(P)]
    b_num = [0 for _ in range(P)]

    for k in range(eval_start, eval_end + 1):
        for body in targets:
            a_obs = _accel_obs_q32(dataset, body, k)
            # build feature vectors for each source
            feats: list[list[int]] = []
            for src in sources:
                if src == body:
                    feats.append([0 for _ in a_obs])
                else:
                    feats.append(_term_vector(dataset, body, k, source=src, p=p))
            for d in range(len(a_obs)):
                y = int(a_obs[d])
                x_vec = [int(feats[j][d]) for j in range(P)]
                for i in range(P):
                    b_num[i] += x_vec[i] * y
                    for j in range(P):
                        A_num[i][j] += x_vec[i] * x_vec[j]

    # convert to Fractions
    A = [[Fraction(val, 1) for val in row] for row in A_num]
    b = [Fraction(val, 1) for val in b_num]
    sol = _solve_linear_system(A, b)
    if sol is None:
        return None
    return [q32_from_fraction(s) for s in sol]


def _fit_hooke(
    *,
    dataset: Any,
    targets: list[str],
    eval_start: int,
    eval_end: int,
) -> int | None:
    # a_obs ≈ -k r -> solve for k
    num = 0
    den = 0
    for k in range(eval_start, eval_end + 1):
        for body in targets:
            a_obs = _accel_obs_q32(dataset, body, k)
            r_cur = dataset.positions_q32[body][k]
            for d in range(len(r_cur)):
                x = -int(r_cur[d])
                y = int(a_obs[d])
                num += x * y
                den += x * x
    if den == 0:
        return None
    return q32_from_fraction(Fraction(num, den))


def _predict_accel_fit(dataset: Any, ir: dict[str, Any], params: dict[str, Any], body: str, k: int) -> list[int]:
    kind = ir.get("theory_kind")
    dim = len(dataset.positions_q32[body][k])
    if kind == "BASELINE_CONST_VEL_V1":
        return [0 for _ in range(dim)]
    if kind == "BASELINE_HOOKE_CENTRAL_V1":
        k_param = params.get("k_param_q32")
        k_q = parse_q32_obj(k_param) if isinstance(k_param, dict) else 0
        out = []
        for comp in dataset.positions_q32[body][k]:
            out.append(-q32_mul(int(k_q), int(comp)))
        return out
    p = int(ir.get("force_law", {}).get("norm_pow_p") or 1)
    sources = list(ir.get("source_bodies") or [])
    mus = params.get("mu_sources_q32") or []
    mus_q = [parse_q32_obj(m) if isinstance(m, dict) else int(m) for m in mus]
    if kind == "CANDIDATE_CENTRAL_POWERLAW_V1":
        src = sources[0] if sources else "Origin"
        term = _term_vector(dataset, body, k, source=src, p=p)
        mu_q = mus_q[0] if mus_q else 0
        return [q32_mul(mu_q, t) for t in term]
    acc = [0 for _ in range(dim)]
    for idx, src in enumerate(sources):
        if src == body:
            continue
        term = _term_vector(dataset, body, k, source=src, p=p)
        mu_q = mus_q[idx] if idx < len(mus_q) else 0
        for d in range(dim):
            acc[d] = int(acc[d]) + int(q32_mul(mu_q, term[d]))
    return acc


def _residual_sum_q64(
    dataset: Any,
    ir: dict[str, Any],
    params: dict[str, Any],
    eval_start: int,
    eval_end: int,
) -> int:
    targets = list(ir.get("target_bodies") or [])
    total = 0
    for k in range(eval_start, eval_end + 1):
        for body in targets:
            a_obs = _accel_obs_q32(dataset, body, k)
            a_pred = _predict_accel_fit(dataset, ir, params, body, k)
            for d in range(len(a_obs)):
                err = int(a_pred[d]) - int(a_obs[d])
                total += err * err
    return int(total)


def compute_precision_hash(ir_policy: dict[str, Any]) -> str:
    payload = {
        "numeric_mode": ir_policy.get("numeric_mode"),
        "q32_rounding": ir_policy.get("q32_rounding"),
        "param_factorization_kind": ir_policy.get("param_factorization_kind"),
    }
    return sha256_prefixed(canon_bytes(payload))


def fit_theory(
    *,
    dataset: Any,
    ir: dict[str, Any],
    split_receipt: dict[str, Any],
    ir_policy: dict[str, Any],
) -> dict[str, Any]:
    kind = ir.get("theory_kind")
    targets = list(ir.get("target_bodies") or [])
    sources = list(ir.get("source_bodies") or [])
    p = int(ir.get("force_law", {}).get("norm_pow_p") or 1)
    eval_start = int(split_receipt.get("dev_eval_start"))
    eval_end = int(split_receipt.get("dev_eval_end"))

    status = "OK"
    params: dict[str, Any] = {}
    if kind == "BASELINE_CONST_VEL_V1":
        params = {}
    elif kind == "BASELINE_HOOKE_CENTRAL_V1":
        k_q = _fit_hooke(dataset=dataset, targets=targets, eval_start=eval_start, eval_end=eval_end)
        if k_q is None:
            status = "SINGULAR"
            params = {"k_param_q32": q32_obj_from_int(0)}
        else:
            params = {"k_param_q32": q32_obj_from_int(int(k_q))}
    else:
        fitted = _fit_linear(dataset=dataset, targets=targets, sources=sources, p=p, eval_start=eval_start, eval_end=eval_end)
        if fitted is None:
            status = "SINGULAR"
            params = {"mu_sources_q32": []}
        else:
            params = {"mu_sources_q32": [q32_obj_from_int(int(v)) for v in fitted]}

    receipt = {
        "schema_version": "sas_science_fit_receipt_v1",
        "receipt_id": "",
        "created_utc": _now_utc(),
        "theory_id": ir.get("theory_id"),
        "dataset_id": split_receipt.get("dataset_id"),
        "split_id": split_receipt.get("split_id"),
        "fit_kind": "DEV",
        "status": status,
        "params_fitted": params,
        "numeric_mode": ir_policy.get("numeric_mode"),
        "precision_config_hash": compute_precision_hash(ir_policy),
        "fit_residual_sum_q64": 0,
    }
    receipt["fit_residual_sum_q64"] = _residual_sum_q64(dataset, ir, params, eval_start, eval_end)
    receipt["receipt_id"] = sha256_prefixed(
        canon_bytes({k: v for k, v in receipt.items() if k not in ("receipt_id", "created_utc")})
    )
    return receipt


__all__ = ["fit_theory", "compute_precision_hash"]
