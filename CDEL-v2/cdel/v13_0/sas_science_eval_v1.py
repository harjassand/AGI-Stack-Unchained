"""Evaluation metrics for SAS-Science v13.0."""

from __future__ import annotations

import math
from typing import Any

from ..v1_7r.canon import canon_bytes, sha256_prefixed
from .sas_science_math_v1 import (
    Q,
    q32_mul,
    q32_obj_from_int,
    parse_q32_obj,
    round_half_even,
)
from .sas_science_workmeter_v1 import Workmeter, work_cost


class SASScienceEvalError(RuntimeError):
    pass


def _fail(reason: str) -> None:
    raise SASScienceEvalError(reason)


def _sqrt_q64_to_q32(value_q64: int) -> int:
    if value_q64 < 0:
        _fail("EVAL_NEGATIVE_SQRT")
    r = math.isqrt(value_q64)
    lower = r * r
    upper = (r + 1) * (r + 1)
    if value_q64 - lower < upper - value_q64:
        return r
    if value_q64 - lower > upper - value_q64:
        return r + 1
    return r if (r % 2 == 0) else (r + 1)


def _accel_obs_q32(dataset: Any, body: str, k: int) -> list[int]:
    dt_q = dataset.dt_q32
    r_prev = dataset.positions_q32[body][k - 1]
    r_cur = dataset.positions_q32[body][k]
    r_next = dataset.positions_q32[body][k + 1]
    out: list[int] = []
    dt2 = int(dt_q) * int(dt_q)
    for idx in range(len(r_cur)):
        diff2 = int(r_next[idx]) - 2 * int(r_cur[idx]) + int(r_prev[idx])
        # a_q32 = diff2 * Q^2 / dt^2
        num = diff2 * (1 << 64)
        a_q = round_half_even(num, dt2)
        out.append(int(a_q))
    return out


def _predict_accel_central(
    *,
    dataset: Any,
    body: str,
    k: int,
    mu_q: int,
    p: int,
    source: str,
    workmeter: Workmeter | None,
    override_pos: dict[str, list[int]] | None = None,
) -> list[int]:
    dim = len(dataset.positions_q32[body][k])
    if override_pos is not None:
        pos_body = override_pos[body]
    else:
        pos_body = dataset.positions_q32[body][k]
    if source == "Origin":
        displacement = [-int(v) for v in pos_body]
    else:
        if override_pos is not None:
            pos_src = override_pos.get(source)
        else:
            pos_src = dataset.positions_q32[source][k]
        displacement = [int(pos_src[i]) - int(pos_body[i]) for i in range(dim)]

    sum_d2 = 0
    for comp in displacement:
        sum_d2 += int(comp) * int(comp)
    norm_q = _sqrt_q64_to_q32(sum_d2)
    if norm_q == 0:
        _fail("EVAL_NORM_ZERO")
    norm_pow = int(norm_q) ** int(p)

    if workmeter is not None:
        workmeter.add_term(dim=dim, norm_pow=p)

    out: list[int] = []
    q_pow = 1 << (32 * int(p))
    for comp in displacement:
        num = int(comp) * q_pow
        term_q = round_half_even(num, norm_pow)
        contrib = q32_mul(int(mu_q), int(term_q))
        out.append(int(contrib))
    return out


def _predict_accel_nbody(
    *,
    dataset: Any,
    body: str,
    k: int,
    mus_q: list[int],
    p: int,
    sources: list[str],
    workmeter: Workmeter | None,
    override_pos: dict[str, list[int]] | None = None,
) -> list[int]:
    dim = len(dataset.positions_q32[body][k])
    if override_pos is not None:
        pos_body = override_pos[body]
    else:
        pos_body = dataset.positions_q32[body][k]
    acc = [0 for _ in range(dim)]
    for idx, src in enumerate(sources):
        if src == body:
            continue
        if override_pos is not None and src in override_pos:
            pos_src = override_pos[src]
        else:
            pos_src = dataset.positions_q32[src][k]
        displacement = [int(pos_src[i]) - int(pos_body[i]) for i in range(dim)]
        sum_d2 = 0
        for comp in displacement:
            sum_d2 += int(comp) * int(comp)
        norm_q = _sqrt_q64_to_q32(sum_d2)
        if norm_q == 0:
            _fail("EVAL_NORM_ZERO")
        norm_pow = int(norm_q) ** int(p)
        if workmeter is not None:
            workmeter.add_term(dim=dim, norm_pow=p)
        q_pow = 1 << (32 * int(p))
        mu_q = int(mus_q[idx]) if idx < len(mus_q) else 0
        for d in range(dim):
            num = int(displacement[d]) * q_pow
            term_q = round_half_even(num, norm_pow)
            contrib = q32_mul(mu_q, int(term_q))
            acc[d] = int(acc[d]) + int(contrib)
    return acc


def _predict_accel_hooke(
    *,
    dataset: Any,
    body: str,
    k: int,
    k_q: int,
    workmeter: Workmeter | None,
    override_pos: dict[str, list[int]] | None = None,
) -> list[int]:
    if override_pos is not None:
        pos_body = override_pos[body]
    else:
        pos_body = dataset.positions_q32[body][k]
    out: list[int] = []
    for comp in pos_body:
        val = -q32_mul(int(k_q), int(comp))
        out.append(int(val))
    if workmeter is not None:
        workmeter.add_hooke(dim=len(pos_body))
    return out


def _params_from_fit(ir: dict[str, Any], fit: dict[str, Any]) -> dict[str, Any]:
    params = {}
    fit_params = fit.get("params_fitted") if isinstance(fit, dict) else None
    if isinstance(fit_params, dict):
        params.update(fit_params)
    # fall back to IR parameters for baselines
    ir_params = ir.get("parameters") if isinstance(ir.get("parameters"), dict) else {}
    for key, val in ir_params.items():
        params.setdefault(key, val)
    return params


def eval_metrics(
    *,
    dataset: Any,
    ir: dict[str, Any],
    fit_receipt: dict[str, Any],
    eval_start: int,
    eval_end: int,
    roll_steps: list[int],
) -> tuple[dict[str, Any], dict[str, int]]:
    workmeter = Workmeter()
    dim = len(next(iter(dataset.positions_q32.values()))[0])
    targets = list(ir.get("target_bodies") or [])
    sources = list(ir.get("source_bodies") or [])
    p = int(ir.get("force_law", {}).get("norm_pow_p") or 1)
    kind = ir.get("theory_kind")

    params = _params_from_fit(ir, fit_receipt)
    mus = params.get("mu_sources_q32") or []
    mus_q = [parse_q32_obj(m) if isinstance(m, dict) else int(m) for m in mus]
    k_param = params.get("k_param_q32")

    # Accel and pos1 metrics
    sum_err2_accel = 0
    sum_err2_pos1 = 0
    count_accel = 0
    count_pos1 = 0
    dt_q = dataset.dt_q32
    dt2 = int(dt_q) * int(dt_q)

    for k in range(eval_start, eval_end + 1):
        for body in targets:
            try:
                if kind == "BASELINE_CONST_VEL_V1":
                    accel_pred = [0 for _ in range(dim)]
                elif kind == "BASELINE_HOOKE_CENTRAL_V1":
                    accel_pred = _predict_accel_hooke(dataset=dataset, body=body, k=k, k_q=parse_k(k_param), workmeter=workmeter)
                elif kind == "CANDIDATE_CENTRAL_POWERLAW_V1":
                    src = sources[0] if sources else "Origin"
                    accel_pred = _predict_accel_central(
                        dataset=dataset,
                        body=body,
                        k=k,
                        mu_q=int(mus_q[0]) if mus_q else 0,
                        p=p,
                        source=src,
                        workmeter=workmeter,
                    )
                else:
                    accel_pred = _predict_accel_nbody(
                        dataset=dataset,
                        body=body,
                        k=k,
                        mus_q=[int(v) for v in mus_q],
                        p=p,
                        sources=sources,
                        workmeter=workmeter,
                    )
                accel_obs = _accel_obs_q32(dataset, body, k)
            except Exception:
                # Mark invalid by forcing negative metric later
                return _invalid_metrics(), workmeter.snapshot()

            for d in range(dim):
                err = int(accel_pred[d]) - int(accel_obs[d])
                sum_err2_accel += err * err
                count_accel += 1

            # one-step position prediction
            r_prev = dataset.positions_q32[body][k - 1]
            r_cur = dataset.positions_q32[body][k]
            r_next = dataset.positions_q32[body][k + 1]
            for d in range(dim):
                # term_q32 = a_q32 * dt^2 / Q^2
                term_q32 = round_half_even(int(accel_pred[d]) * dt2, 1 << 64)
                r_pred = 2 * int(r_cur[d]) - int(r_prev[d]) + int(term_q32)
                err_pos = int(r_pred) - int(r_next[d])
                sum_err2_pos1 += err_pos * err_pos
                count_pos1 += 1

    mse_accel_q = _mse_q32(sum_err2_accel, count_accel)
    rmse_pos1_q = _rmse_q32(sum_err2_pos1, count_pos1)

    # Rollouts
    rmse_rolls: dict[int, int] = {}
    for steps in roll_steps:
        rmse_rolls[steps] = _rollout_rmse(
            dataset=dataset,
            ir=ir,
            params=params,
            eval_start=eval_start,
            eval_end=eval_end,
            steps=steps,
            workmeter=workmeter,
        )

    metrics = {
        "mse_accel_q32": q32_obj_from_int(mse_accel_q),
        "rmse_pos1_q32": q32_obj_from_int(rmse_pos1_q),
        "rmse_roll_64_q32": q32_obj_from_int(rmse_rolls.get(64, -1)),
        "rmse_roll_128_q32": q32_obj_from_int(rmse_rolls.get(128, -1)),
        "rmse_roll_256_q32": q32_obj_from_int(rmse_rolls.get(256, -1)),
    }
    return metrics, workmeter.snapshot()


def parse_k(k_param: Any) -> int:
    if k_param is None:
        return 0
    if isinstance(k_param, dict):
        return parse_q32_obj(k_param)
    if isinstance(k_param, int):
        return int(k_param)
    return 0


def _invalid_metrics() -> dict[str, Any]:
    neg = q32_obj_from_int(-1)
    return {
        "mse_accel_q32": neg,
        "rmse_pos1_q32": neg,
        "rmse_roll_64_q32": neg,
        "rmse_roll_128_q32": neg,
        "rmse_roll_256_q32": neg,
    }


def _mse_q32(sum_err2: int, count: int) -> int:
    if count <= 0:
        return -1
    # err^2 scale Q^2; MSE_q32 = sum_err2 / (count * Q)
    return round_half_even(int(sum_err2), int(count) * int(Q))


def _rmse_q32(sum_err2: int, count: int) -> int:
    if count <= 0:
        return -1
    mse_q = _mse_q32(sum_err2, count)
    if mse_q < 0:
        return -1
    # rmse_q32 = sqrt(mse_q * Q)
    return _sqrt_q64_to_q32(int(mse_q) * int(Q))


def _rollout_rmse(
    *,
    dataset: Any,
    ir: dict[str, Any],
    params: dict[str, Any],
    eval_start: int,
    eval_end: int,
    steps: int,
    workmeter: Workmeter,
) -> int:
    if steps <= 0:
        return -1
    k0 = eval_start
    if k0 - 1 < 0:
        return -1
    if k0 + steps > eval_end:
        return -1

    targets = list(ir.get("target_bodies") or [])
    sources = list(ir.get("source_bodies") or [])
    kind = ir.get("theory_kind")
    p = int(ir.get("force_law", {}).get("norm_pow_p") or 1)
    mus = params.get("mu_sources_q32") or []
    mus_q = [parse_q32_obj(m) if isinstance(m, dict) else int(m) for m in mus]
    k_param = params.get("k_param_q32")

    # initialize positions
    pos_prev = {b: list(dataset.positions_q32[b][k0 - 1]) for b in targets}
    pos_cur = {b: list(dataset.positions_q32[b][k0]) for b in targets}

    dt_q = dataset.dt_q32
    dt2 = int(dt_q) * int(dt_q)

    sum_err2 = 0
    count = 0

    for step in range(1, steps + 1):
        idx = k0 + step - 1
        # build override positions for sources if needed
        override: dict[str, list[int]] = {b: pos_cur[b] for b in targets}
        # include external sources (e.g., Sun) from observed data
        for src in sources:
            if src not in override and src in dataset.positions_q32:
                override[src] = list(dataset.positions_q32[src][idx])

        pos_next: dict[str, list[int]] = {}
        for body in targets:
            if kind == "BASELINE_CONST_VEL_V1":
                accel_pred = [0 for _ in pos_cur[body]]
            elif kind == "BASELINE_HOOKE_CENTRAL_V1":
                accel_pred = _predict_accel_hooke(
                    dataset=dataset,
                    body=body,
                    k=idx,
                    k_q=parse_k(k_param),
                    workmeter=workmeter,
                    override_pos=override,
                )
            elif kind == "CANDIDATE_CENTRAL_POWERLAW_V1":
                src = sources[0] if sources else "Origin"
                accel_pred = _predict_accel_central(
                    dataset=dataset,
                    body=body,
                    k=idx,
                    mu_q=int(mus_q[0]) if mus_q else 0,
                    p=p,
                    source=src,
                    workmeter=workmeter,
                    override_pos=override,
                )
            else:
                accel_pred = _predict_accel_nbody(
                    dataset=dataset,
                    body=body,
                    k=idx,
                    mus_q=[int(v) for v in mus_q],
                    p=p,
                    sources=sources,
                    workmeter=workmeter,
                    override_pos=override,
                )

            r_prev = pos_prev[body]
            r_cur = pos_cur[body]
            next_vec: list[int] = []
            for d in range(len(r_cur)):
                term_q32 = round_half_even(int(accel_pred[d]) * dt2, 1 << 64)
                r_next = 2 * int(r_cur[d]) - int(r_prev[d]) + int(term_q32)
                next_vec.append(int(r_next))
            pos_next[body] = next_vec

            # error vs observed
            obs = dataset.positions_q32[body][idx + 1]
            for d in range(len(obs)):
                err = int(next_vec[d]) - int(obs[d])
                sum_err2 += err * err
                count += 1

        pos_prev = pos_cur
        pos_cur = pos_next

    return _rmse_q32(sum_err2, count)


def compute_eval_report(
    *,
    dataset: Any,
    ir: dict[str, Any],
    fit_receipt: dict[str, Any],
    eval_kind: str,
    split_receipt: dict[str, Any],
) -> dict[str, Any]:
    if eval_kind not in ("DEV", "HELDOUT"):
        _fail("EVAL_KIND_INVALID")
    if eval_kind == "DEV":
        eval_start = int(split_receipt.get("dev_eval_start"))
        eval_end = int(split_receipt.get("dev_eval_end"))
    else:
        eval_start = int(split_receipt.get("heldout_eval_start"))
        eval_end = int(split_receipt.get("heldout_eval_end"))

    metrics, counts = eval_metrics(
        dataset=dataset,
        ir=ir,
        fit_receipt=fit_receipt,
        eval_start=eval_start,
        eval_end=eval_end,
        roll_steps=[64, 128, 256],
    )
    counts["work_cost_total"] = work_cost(counts)

    report = {
        "schema_version": "sas_science_eval_report_v1",
        "theory_id": ir.get("theory_id"),
        "eval_kind": eval_kind,
        "dataset_id": split_receipt.get("dataset_id"),
        "split_id": split_receipt.get("split_id"),
        "fit_receipt_hash": fit_receipt.get("receipt_id"),
        "metrics": metrics,
        "workmeter": counts,
    }
    return report


def compute_report_hash(report: dict[str, Any]) -> str:
    return sha256_prefixed(canon_bytes(report))


__all__ = [
    "compute_eval_report",
    "compute_report_hash",
]
