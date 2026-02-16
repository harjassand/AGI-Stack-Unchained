from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from cdel.v1_7r.canon import canon_bytes, sha256_prefixed
from cdel.v1_7r.science.eval_v1 import action_is_valid, decode_rational, encode_rational, eval_causalworld


class SuiteRowValidationError(ValueError):
    def __init__(self, reason_code: str, message: str = "") -> None:
        super().__init__(reason_code if not message else f"{reason_code}: {message}")
        self.reason_code = reason_code


_ALLOWED_ESTIMATORS = {"diff_in_means", "ols_adjustment"}


def _is_x_key(k: str) -> bool:
    return k.startswith("x-")


def _require_dict(x: Any, ctx: str) -> dict:
    if not isinstance(x, dict):
        raise SuiteRowValidationError("CAUSAL_SUITE_ROW_TYPE", f"{ctx} must be dict")
    return x


def _require_list(x: Any, ctx: str) -> list:
    if not isinstance(x, list):
        raise SuiteRowValidationError("CAUSAL_SUITE_ROW_TYPE", f"{ctx} must be list")
    return x


def _require_int(x: Any, ctx: str) -> int:
    if isinstance(x, bool) or not isinstance(x, int):
        raise SuiteRowValidationError("CAUSAL_SUITE_ROW_TYPE", f"{ctx} must be int")
    return x


def _require_str(x: Any, ctx: str) -> str:
    if not isinstance(x, str):
        raise SuiteRowValidationError("CAUSAL_SUITE_ROW_TYPE", f"{ctx} must be str")
    return x


def _check_allowed_keys(obj: dict, allowed: set[str], ctx: str) -> None:
    for k in obj.keys():
        if k in allowed or _is_x_key(k):
            continue
        raise SuiteRowValidationError("CAUSAL_SUITE_ROW_EXTRA_KEY", f"{ctx} has extra key {k!r}")


def validate_causalworld_suite_row(suite_row: dict) -> None:
    sr = _require_dict(suite_row, "suite_row")
    _check_allowed_keys(sr, {"env", "max_steps", "generator", "params", "start", "objective"}, "suite_row")

    env = _require_str(sr.get("env"), "suite_row.env")
    if env != "causalworld-v1":
        raise SuiteRowValidationError("CAUSAL_SUITE_ROW_ENV", "env must be causalworld-v1")

    max_steps = _require_int(sr.get("max_steps"), "suite_row.max_steps")
    if max_steps <= 0 or max_steps > 4096:
        raise SuiteRowValidationError("CAUSAL_SUITE_ROW_MAX_STEPS", "max_steps out of bounds")

    gen = _require_dict(sr.get("generator"), "suite_row.generator")
    _check_allowed_keys(
        gen,
        {
            "kind",
            "n",
            "z_min",
            "z_max",
            "w_min",
            "w_max",
            "a_z",
            "a_w",
            "a0",
            "c_t",
            "c_z",
            "c_w",
            "c0",
            "eps_t_min",
            "eps_t_max",
            "eps_y_min",
            "eps_y_max",
        },
        "suite_row.generator",
    )
    kind = _require_str(gen.get("kind"), "generator.kind")
    if kind != "scm_backdoor_int_v1":
        raise SuiteRowValidationError("CAUSAL_SUITE_ROW_GEN_KIND", "generator.kind mismatch")

    n = _require_int(gen.get("n"), "generator.n")
    if n < 1 or n > 4096:
        raise SuiteRowValidationError("CAUSAL_SUITE_ROW_N", "n out of bounds")

    z_min = _require_int(gen.get("z_min"), "generator.z_min")
    z_max = _require_int(gen.get("z_max"), "generator.z_max")
    w_min = _require_int(gen.get("w_min"), "generator.w_min")
    w_max = _require_int(gen.get("w_max"), "generator.w_max")
    if z_min > z_max:
        raise SuiteRowValidationError("CAUSAL_SUITE_ROW_RANGE", "z_min > z_max")
    if w_min > w_max:
        raise SuiteRowValidationError("CAUSAL_SUITE_ROW_RANGE", "w_min > w_max")

    eps_t_min = _require_int(gen.get("eps_t_min"), "generator.eps_t_min")
    eps_t_max = _require_int(gen.get("eps_t_max"), "generator.eps_t_max")
    eps_y_min = _require_int(gen.get("eps_y_min"), "generator.eps_y_min")
    eps_y_max = _require_int(gen.get("eps_y_max"), "generator.eps_y_max")
    if eps_t_min > eps_t_max:
        raise SuiteRowValidationError("CAUSAL_SUITE_ROW_RANGE", "eps_t_min > eps_t_max")
    if eps_y_min > eps_y_max:
        raise SuiteRowValidationError("CAUSAL_SUITE_ROW_RANGE", "eps_y_min > eps_y_max")

    # Coefficients: all must be ints (type check); no bounds beyond that here.
    for k in ["a_z", "a_w", "a0", "c_t", "c_z", "c_w", "c0"]:
        _require_int(gen.get(k), f"generator.{k}")

    params = _require_list(sr.get("params"), "suite_row.params")
    if len(params) != 3:
        raise SuiteRowValidationError("CAUSAL_SUITE_ROW_PARAMS_LEN", "params must have length 3")

    # Param 0: estimator enum
    p0 = _require_dict(params[0], "params[0]")
    _check_allowed_keys(p0, {"param_id", "values_enum"}, "params[0]")
    _require_str(p0.get("param_id"), "params[0].param_id")
    v_enum = _require_list(p0.get("values_enum"), "params[0].values_enum")
    if len(v_enum) < 1 or len(v_enum) > 8:
        raise SuiteRowValidationError("CAUSAL_SUITE_ROW_VALUES_LEN", "values_enum length out of bounds")
    seen: set[str] = set()
    for i, v in enumerate(v_enum):
        s = _require_str(v, f"params[0].values_enum[{i}]")
        if s in seen:
            raise SuiteRowValidationError("CAUSAL_SUITE_ROW_ENUM_DUP", "values_enum not unique")
        if s not in _ALLOWED_ESTIMATORS:
            raise SuiteRowValidationError("CAUSAL_SUITE_ROW_ENUM_BAD", "values_enum contains invalid estimator")
        seen.add(s)

    # Param 1/2: adjust_z/adjust_w int lists (must be 0/1)
    for pi in [1, 2]:
        p = _require_dict(params[pi], f"params[{pi}]")
        _check_allowed_keys(p, {"param_id", "values_int"}, f"params[{pi}]")
        _require_str(p.get("param_id"), f"params[{pi}].param_id")
        vals = _require_list(p.get("values_int"), f"params[{pi}].values_int")
        if len(vals) != 2:
            raise SuiteRowValidationError("CAUSAL_SUITE_ROW_VALUES_LEN", "values_int must have length 2")
        svals = set()
        for j, v in enumerate(vals):
            iv = _require_int(v, f"params[{pi}].values_int[{j}]")
            if iv not in (0, 1):
                raise SuiteRowValidationError("CAUSAL_SUITE_ROW_ADJUST", "adjust values must be 0/1")
            svals.add(iv)
        if svals != {0, 1}:
            raise SuiteRowValidationError("CAUSAL_SUITE_ROW_ADJUST", "values_int must contain both 0 and 1")

    start = _require_dict(sr.get("start"), "suite_row.start")
    _check_allowed_keys(start, {"p_idx", "param_value_idxs"}, "suite_row.start")
    p_idx = _require_int(start.get("p_idx"), "start.p_idx")
    if p_idx < 0 or p_idx >= 3:
        raise SuiteRowValidationError("CAUSAL_SUITE_ROW_PIDX", "p_idx out of range")
    pv = _require_list(start.get("param_value_idxs"), "start.param_value_idxs")
    if len(pv) != 3:
        raise SuiteRowValidationError("CAUSAL_SUITE_ROW_START_LEN", "start.param_value_idxs length mismatch")
    # Check each idx within its values list length
    p0_len = len(v_enum)
    for i, idx in enumerate(pv):
        idx_i = _require_int(idx, f"start.param_value_idxs[{i}]")
        if i == 0:
            if idx_i < 0 or idx_i >= p0_len:
                raise SuiteRowValidationError("CAUSAL_SUITE_ROW_START_RANGE", "estimator idx out of range")
        else:
            if idx_i < 0 or idx_i >= 2:
                raise SuiteRowValidationError("CAUSAL_SUITE_ROW_START_RANGE", "adjust idx out of range")

    obj = _require_dict(sr.get("objective"), "suite_row.objective")
    _check_allowed_keys(obj, {"metric_name", "max_abs_error"}, "suite_row.objective")
    metric_name = _require_str(obj.get("metric_name"), "objective.metric_name")
    if metric_name != "ate_abs_error":
        raise SuiteRowValidationError("CAUSAL_SUITE_ROW_METRIC", "metric_name must be ate_abs_error")
    max_abs_raw = _require_str(obj.get("max_abs_error"), "objective.max_abs_error")
    try:
        dec = decode_rational(max_abs_raw)
    except Exception as exc:  # noqa: BLE001
        raise SuiteRowValidationError("CAUSAL_SUITE_ROW_MAXABS", "max_abs_error parse fail") from exc
    if isinstance(dec, Fraction) and dec.denominator != 1:
        raise SuiteRowValidationError("CAUSAL_SUITE_ROW_MAXABS", "max_abs_error must be integer")
    max_abs = int(dec.numerator) if isinstance(dec, Fraction) else int(dec)
    if max_abs < 0:
        raise SuiteRowValidationError("CAUSAL_SUITE_ROW_MAXABS", "max_abs_error must be >= 0")


@dataclass
class _State:
    t: int
    p_idx: int
    param_value_idxs: list[int]
    last_eval: dict
    trace: list[dict]
    dataset: list[dict] | None
    meta: dict | None


class CausalWorldV1Env:
    def __init__(self, suite_row: dict, epoch_key: bytes, inst_hash: bytes):
        validate_causalworld_suite_row(suite_row)
        if not isinstance(epoch_key, (bytes, bytearray)):
            raise TypeError("epoch_key must be bytes")
        if not isinstance(inst_hash, (bytes, bytearray)):
            raise TypeError("inst_hash must be bytes")
        self.suite_row = suite_row
        self.epoch_key = bytes(epoch_key)
        self.inst_hash = bytes(inst_hash)

        self.max_steps = int(suite_row["max_steps"])
        self.params = list(suite_row["params"])
        self.param_ids = [str(p["param_id"]) for p in self.params]

        # value list lengths per parameter
        self.param_value_lens: list[int] = []
        for p in self.params:
            if "values_enum" in p:
                self.param_value_lens.append(len(p["values_enum"]))
            else:
                self.param_value_lens.append(len(p["values_int"]))

        start = suite_row["start"]
        self.start_p_idx = int(start["p_idx"])
        self.start_param_value_idxs = [int(x) for x in start["param_value_idxs"]]

        obj = suite_row["objective"]
        dec = decode_rational(str(obj["max_abs_error"]))
        max_abs_int = int(dec.numerator) if isinstance(dec, Fraction) else int(dec)
        self._init_last_eval = {
            "has_value": False,
            "pass": False,
            "metric_name": str(obj["metric_name"]),
            "metric_value": "",
            "threshold": encode_rational(max_abs_int),
            "reason_codes": [],
        }

        self._state: _State | None = None
        self._done: bool = False

    def trace_hash(self) -> str:
        if self._state is None:
            return sha256_prefixed(canon_bytes([]))
        return sha256_prefixed(canon_bytes(self._state.trace))

    def reset(self) -> dict:
        self._done = False
        self._state = _State(
            t=0,
            p_idx=self.start_p_idx,
            param_value_idxs=list(self.start_param_value_idxs),
            last_eval=dict(self._init_last_eval),
            trace=[],
            dataset=None,
            meta=None,
        )
        from cdel.v1_7r.science.generators_v1 import gen_scm_backdoor_int_v1

        rows, meta = gen_scm_backdoor_int_v1(
            epoch_key=self.epoch_key,
            inst_hash=self.inst_hash,
            gen_cfg=self.suite_row["generator"],
        )
        self._state.dataset = rows
        self._state.meta = meta
        return self._obs()

    def _obs(self) -> dict:
        assert self._state is not None
        gen = self.suite_row["generator"]
        task_summary = {
            "n": int(gen["n"]),
            "z_range": [int(gen["z_min"]), int(gen["z_max"])],
            "w_range": [int(gen["w_min"]), int(gen["w_max"])],
        }
        return {
            "env": "causalworld-v1",
            "t": int(self._state.t),
            "p_idx": int(self._state.p_idx),
            "param_ids": list(self.param_ids),
            "param_value_idxs": list(self._state.param_value_idxs),
            "last_eval": dict(self._state.last_eval),
            "task_summary": task_summary,
        }

    def step(self, action: dict) -> tuple[dict, bool, dict]:
        if self._state is None:
            raise RuntimeError("reset must be called before step")
        if self._done:
            raise RuntimeError("episode already done")
        if not action_is_valid(action):
            raise ValueError("INVALID_ACTION")

        name = action["name"]
        self._state.trace.append({"name": name, "args": {}})

        if name == "PREV_PARAM":
            self._state.p_idx = (self._state.p_idx - 1) % len(self.params)
        elif name == "NEXT_PARAM":
            self._state.p_idx = (self._state.p_idx + 1) % len(self.params)
        elif name == "DEC_VALUE":
            i = self._state.p_idx
            self._state.param_value_idxs[i] = (self._state.param_value_idxs[i] - 1) % self.param_value_lens[i]
        elif name == "INC_VALUE":
            i = self._state.p_idx
            self._state.param_value_idxs[i] = (self._state.param_value_idxs[i] + 1) % self.param_value_lens[i]
        elif name == "EVAL":
            self._state.last_eval = eval_causalworld(
                suite_row=self.suite_row,
                epoch_key=self.epoch_key,
                inst_hash=self.inst_hash,
                param_value_idxs=list(self._state.param_value_idxs),
            )
        else:
            raise ValueError("INVALID_ACTION")

        self._state.t += 1

        done = False
        if name == "EVAL" and bool(self._state.last_eval.get("pass")):
            done = True
        if self._state.t >= self.max_steps:
            done = True

        self._done = done
        info = {"trace_hash": self.trace_hash()}
        return self._obs(), done, info
