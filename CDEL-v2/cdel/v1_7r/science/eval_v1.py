"""SCI-RSI v1.7r: deterministic evaluation helpers (rational codec + action validation + evaluators).

Non-negotiables:
- No floats for decision-critical logic.
- Canonical rational encoding:
  - integers: "k"
  - rationals: "p/q" (reduced, q>0)
- Strict action schema for SCI envs.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from math import gcd
from typing import Any

from cdel.v1_7r.science.generators_v1 import gen_scm_backdoor_int_v1, gen_wm_linear_sep_int_v1


SCI_PRIMITIVE_ACTION_NAMES_V1 = (
    "PREV_PARAM",
    "NEXT_PARAM",
    "DEC_VALUE",
    "INC_VALUE",
    "EVAL",
)


def _is_canon_int_str(s: str) -> bool:
    # Canonical integer string:
    # - "0" allowed
    # - no leading '+'
    # - no leading zeros (except "0")
    # - "-0" forbidden
    if s == "0":
        return True
    if not s:
        return False
    if s[0] == "+":
        return False
    if s[0] == "-":
        if len(s) == 2 and s[1] == "0":
            return False
        digits = s[1:]
        if not digits or not digits.isdigit():
            return False
        return digits[0] != "0"
    if not s.isdigit():
        return False
    return s[0] != "0"


def _parse_canon_int_str(s: str) -> int:
    if not isinstance(s, str):
        raise TypeError("expected str")
    if s != s.strip():
        raise ValueError("whitespace not allowed in integer encoding")
    if not _is_canon_int_str(s):
        raise ValueError("non-canonical integer encoding")
    return int(s)


def encode_rational(x: Fraction | int) -> str:
    """Encode Fraction|int as canonical ASCII: "k" or "p/q" (reduced, q>0)."""
    if isinstance(x, bool):
        raise TypeError("bool not allowed")
    if isinstance(x, int):
        return str(x)
    if isinstance(x, Fraction):
        if x.denominator == 1:
            return str(x.numerator)
        # Fraction is reduced and denominator > 0.
        return f"{x.numerator}/{x.denominator}"
    raise TypeError("encode_rational expects Fraction|int")


def decode_rational(s: str) -> Fraction | int:
    """Decode canonical "k" or "p/q" into int or Fraction.

    Fail-closed:
    - rejects whitespace
    - rejects unreduced rationals
    - rejects q<=0
    - rejects non-canonical integer strings (leading zeros, +, -0)
    """
    if not isinstance(s, str):
        raise TypeError("expected str")
    if s != s.strip():
        raise ValueError("whitespace not allowed in rational encoding")
    if "/" not in s:
        return _parse_canon_int_str(s)

    parts = s.split("/")
    if len(parts) != 2:
        raise ValueError("invalid rational encoding")
    p_str, q_str = parts
    p = _parse_canon_int_str(p_str)
    q = _parse_canon_int_str(q_str)

    if q <= 0:
        raise ValueError("rational denominator must be > 0")
    if gcd(abs(p), q) != 1:
        raise ValueError("rational encoding must be reduced")

    return Fraction(p, q)


def action_is_valid(action: dict) -> bool:
    """Strict action schema check for SCI envs.

    Required structure:
      {"name": <one of SCI_PRIMITIVE_ACTION_NAMES_V1>, "args": {}}

    - No extra keys.
    - args must be an empty dict ({}).
    """
    if not isinstance(action, dict):
        return False
    if set(action.keys()) != {"name", "args"}:
        return False
    name = action.get("name")
    args = action.get("args")
    if not isinstance(name, str):
        return False
    if name not in SCI_PRIMITIVE_ACTION_NAMES_V1:
        return False
    if not isinstance(args, dict):
        return False
    if args:
        return False
    return True


def _as_int(x: Any, *, name: str) -> int:
    if isinstance(x, bool) or not isinstance(x, int):
        raise TypeError(f"{name} must be int")
    return x


def _select_values_int(params: list[dict], idxs: list[int]) -> list[int]:
    if not isinstance(idxs, list):
        raise TypeError("param_value_idxs must be list")
    if len(idxs) != len(params):
        raise ValueError("param_value_idxs length mismatch")
    out: list[int] = []
    for i, p in enumerate(params):
        if not isinstance(p, dict):
            raise TypeError("params entries must be dict")
        values = p.get("values_int")
        if not isinstance(values, list) or not values:
            raise TypeError("values_int must be list[int]")
        j = _as_int(idxs[i], name="param_value_idx")
        if j < 0 or j >= len(values):
            raise ValueError("param_value_idx out of range")
        v = values[j]
        v_int = _as_int(v, name="values_int item")
        out.append(v_int)
    return out


def _select_values_enum(params: list[dict], idxs: list[int], *, param_pos: int) -> str:
    p = params[param_pos]
    if not isinstance(p, dict):
        raise TypeError("params entry must be dict")
    values = p.get("values_enum")
    if not isinstance(values, list) or not values:
        raise TypeError("values_enum must be list[str]")
    j = _as_int(idxs[param_pos], name="param_value_idx")
    if j < 0 or j >= len(values):
        raise ValueError("param_value_idx out of range")
    v = values[j]
    if not isinstance(v, str):
        raise TypeError("values_enum item must be str")
    return v


def eval_wmworld(*, suite_row: dict, epoch_key: bytes, inst_hash: bytes, param_value_idxs: list[int]) -> dict:
    """Evaluate wmworld-v1 candidate weights/bias for accuracy and nontriviality.

    Returns last_eval object (dict) with fields required by the SCI observation schema.
    """
    if not isinstance(suite_row, dict):
        raise TypeError("suite_row must be dict")
    params = suite_row.get("params")
    if not isinstance(params, list):
        raise TypeError("suite_row.params must be list")
    gen_cfg = suite_row.get("generator")
    if not isinstance(gen_cfg, dict):
        raise TypeError("suite_row.generator must be dict")
    obj = suite_row.get("objective")
    if not isinstance(obj, dict):
        raise TypeError("suite_row.objective must be dict")

    # Candidate parameter values (ints).
    values = _select_values_int(params, param_value_idxs)

    d = _as_int(gen_cfg.get("d"), name="generator.d")
    n = _as_int(gen_cfg.get("n"), name="generator.n")

    if d != len(params) - 1:
        raise ValueError("wmworld invariant violated: d != len(params)-1")
    if d < 0:
        raise ValueError("d must be >= 0")
    if n <= 0:
        raise ValueError("n must be >= 1")

    w_hat = values[:d]
    b_hat = values[d]

    rows = gen_wm_linear_sep_int_v1(epoch_key=epoch_key, inst_hash=inst_hash, gen_cfg=gen_cfg)

    correct = 0
    pred_has_0 = False
    pred_has_1 = False

    for r in rows:
        x = r.get("x")
        y = r.get("y")
        if not isinstance(x, list) or len(x) != d:
            raise ValueError("row.x invalid")
        y_int = _as_int(y, name="row.y")
        if y_int not in (0, 1):
            raise ValueError("row.y must be 0/1")

        score = b_hat
        for wi, xi in zip(w_hat, x):
            xi_int = _as_int(xi, name="x item")
            score += wi * xi_int

        y_hat = 1 if score >= 0 else 0
        if y_hat == 0:
            pred_has_0 = True
        else:
            pred_has_1 = True

        if y_hat == y_int:
            correct += 1

    acc = Fraction(correct, n)

    thr_raw = obj.get("min_accuracy")
    if not isinstance(thr_raw, str):
        raise TypeError("objective.min_accuracy must be str")
    thr_dec = decode_rational(thr_raw)
    thr = Fraction(thr_dec, 1) if isinstance(thr_dec, int) else thr_dec
    if thr < 0 or thr > 1:
        raise ValueError("min_accuracy out of [0,1]")

    reason_codes: list[str] = []

    # Nontriviality gates (§6.1)
    all_zero_model = (d >= 1 and n >= 16 and all(w == 0 for w in w_hat) and b_hat == 0)
    const_pred = not (pred_has_0 and pred_has_1)  # unique_labels == 1

    nontriv_fail = False
    if all_zero_model:
        nontriv_fail = True
        reason_codes.append("NONTRIVIALITY_FAIL_ZERO_MODEL")
    if const_pred:
        nontriv_fail = True
        reason_codes.append("NONTRIVIALITY_FAIL_CONST_PRED")

    passed = (acc >= thr) and (not nontriv_fail)
    if nontriv_fail:
        # Stable umbrella code used by witness layer.
        reason_codes.append("NONTRIVIALITY_FAIL")

    return {
        "has_value": True,
        "pass": bool(passed),
        "metric_name": "accuracy",
        "metric_value": encode_rational(acc),
        "threshold": encode_rational(thr),
        "reason_codes": reason_codes,
    }


def _solve_linear_system_gj(A: list[list[Fraction]], b: list[Fraction]) -> list[Fraction] | None:
    """Solve A x = b using deterministic Gauss-Jordan with first-nonzero pivot rule.

    Returns solution vector or None if singular.
    """
    k = len(A)
    if k == 0:
        return []
    # Build augmented matrix [A | b]
    aug: list[list[Fraction]] = []
    for i in range(k):
        if len(A[i]) != k:
            raise ValueError("A must be square")
        aug.append([A[i][j] for j in range(k)] + [b[i]])

    for col in range(k):
        pivot_row = None
        for r in range(col, k):
            if aug[r][col] != 0:
                pivot_row = r
                break
        if pivot_row is None:
            return None
        if pivot_row != col:
            aug[col], aug[pivot_row] = aug[pivot_row], aug[col]

        pivot = aug[col][col]
        # Normalize pivot row
        for j in range(col, k + 1):
            aug[col][j] = aug[col][j] / pivot

        # Eliminate other rows
        for r in range(k):
            if r == col:
                continue
            factor = aug[r][col]
            if factor == 0:
                continue
            for j in range(col, k + 1):
                aug[r][j] = aug[r][j] - factor * aug[col][j]

    return [aug[i][k] for i in range(k)]


def _ols_coef_t_fraction(rows: list[dict], *, adjust_z: int, adjust_w: int) -> Fraction | None:
    """OLS coefficient on T with optional covariates Z/W, using Fraction end-to-end.
    Returns coef on T or None if singular.
    """
    if adjust_z not in (0, 1) or adjust_w not in (0, 1):
        raise ValueError("adjust_z/adjust_w must be 0/1")

    # Columns: intercept, T, [Z], [W]
    k = 2 + adjust_z + adjust_w
    A = [[Fraction(0, 1) for _ in range(k)] for _ in range(k)]
    b = [Fraction(0, 1) for _ in range(k)]

    for r in rows:
        T = _as_int(r.get("T"), name="row.T")
        Z = _as_int(r.get("Z"), name="row.Z")
        W = _as_int(r.get("W"), name="row.W")
        Y = _as_int(r.get("Y"), name="row.Y")

        xrow: list[int] = [1, T]
        if adjust_z == 1:
            xrow.append(Z)
        if adjust_w == 1:
            xrow.append(W)

        # Update normal equations
        for i in range(k):
            xi = xrow[i]
            b[i] += Fraction(xi * Y, 1)
            for j in range(k):
                A[i][j] += Fraction(xi * xrow[j], 1)

    sol = _solve_linear_system_gj(A, b)
    if sol is None:
        return None
    # Coefficient on T is index 1.
    return sol[1]


def eval_causalworld(*, suite_row: dict, epoch_key: bytes, inst_hash: bytes, param_value_idxs: list[int]) -> dict:
    """Evaluate causalworld-v1 estimator config (diff-in-means or Fraction OLS)."""
    if not isinstance(suite_row, dict):
        raise TypeError("suite_row must be dict")
    params = suite_row.get("params")
    if not isinstance(params, list):
        raise TypeError("suite_row.params must be list")
    gen_cfg = suite_row.get("generator")
    if not isinstance(gen_cfg, dict):
        raise TypeError("suite_row.generator must be dict")
    obj = suite_row.get("objective")
    if not isinstance(obj, dict):
        raise TypeError("suite_row.objective must be dict")

    if not isinstance(param_value_idxs, list) or len(param_value_idxs) != len(params):
        raise ValueError("param_value_idxs length mismatch")

    estimator = _select_values_enum(params, param_value_idxs, param_pos=0)
    adjust_z = _select_values_int([params[1]], [param_value_idxs[1]])[0]
    adjust_w = _select_values_int([params[2]], [param_value_idxs[2]])[0]
    if adjust_z not in (0, 1) or adjust_w not in (0, 1):
        raise ValueError("adjust_z/adjust_w must be 0/1")

    max_abs_raw = obj.get("max_abs_error")
    if not isinstance(max_abs_raw, str):
        raise TypeError("objective.max_abs_error must be str")
    max_abs_dec = decode_rational(max_abs_raw)
    if isinstance(max_abs_dec, Fraction):
        if max_abs_dec.denominator != 1:
            raise ValueError("max_abs_error must be integer")
        max_abs_err = int(max_abs_dec.numerator)
    else:
        max_abs_err = int(max_abs_dec)
    if max_abs_err < 0:
        raise ValueError("max_abs_error must be >= 0")

    rows, meta = gen_scm_backdoor_int_v1(epoch_key=epoch_key, inst_hash=inst_hash, gen_cfg=gen_cfg)
    true_ate = _as_int(meta.get("true_ate"), name="meta.true_ate")

    reason_codes: list[str] = []
    invalid_cfg = False

    # Nontriviality / semantic validity (§6.2)
    if estimator == "diff_in_means" and (adjust_z == 1 or adjust_w == 1):
        invalid_cfg = True
        reason_codes.append("ESTIMATOR_INVALID")

    ate_hat: Fraction | None = None
    singular = False

    if estimator == "diff_in_means":
        sum1 = 0
        sum0 = 0
        n1 = 0
        n0 = 0
        for r in rows:
            T = _as_int(r.get("T"), name="row.T")
            Y = _as_int(r.get("Y"), name="row.Y")
            if T not in (0, 1):
                raise ValueError("row.T must be 0/1")
            if T == 1:
                sum1 += Y
                n1 += 1
            else:
                sum0 += Y
                n0 += 1
        if n1 == 0 or n0 == 0:
            invalid_cfg = True
            reason_codes.append("NO_T_VARIATION")
        else:
            ate_hat = Fraction(sum1, n1) - Fraction(sum0, n0)

    elif estimator == "ols_adjustment":
        coef = _ols_coef_t_fraction(rows, adjust_z=adjust_z, adjust_w=adjust_w)
        if coef is None:
            singular = True
            reason_codes.append("SINGULAR_MATRIX")
        else:
            ate_hat = coef

    else:
        invalid_cfg = True
        reason_codes.append("ESTIMATOR_INVALID")

    # Metric is abs error; if undefined/singular/invalid we force metric_value > threshold.
    if ate_hat is None:
        abs_error = Fraction(max_abs_err + 1, 1)
    else:
        abs_error = abs(ate_hat - Fraction(true_ate, 1))

    passed = (abs_error <= Fraction(max_abs_err, 1)) and (not invalid_cfg) and (not singular)

    return {
        "has_value": True,
        "pass": bool(passed),
        "metric_name": "ate_abs_error",
        "metric_value": encode_rational(abs_error if abs_error.denominator != 1 else int(abs_error.numerator)),
        "threshold": encode_rational(max_abs_err),
        "reason_codes": reason_codes,
    }


@dataclass(frozen=True)
class SciLastEvalV1:
    """Optional typed helper for internal use. The on-wire last_eval is a dict."""
    has_value: bool
    passed: bool
    metric_name: str
    metric_value: str
    threshold: str
    reason_codes: tuple[str, ...]
