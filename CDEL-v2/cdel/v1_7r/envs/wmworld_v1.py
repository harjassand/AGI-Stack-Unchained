from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from cdel.v1_7r.canon import canon_bytes, sha256_prefixed
from cdel.v1_7r.science.eval_v1 import action_is_valid, decode_rational, encode_rational, eval_wmworld


class SuiteRowValidationError(ValueError):
    def __init__(self, reason_code: str, message: str = "") -> None:
        super().__init__(reason_code if not message else f"{reason_code}: {message}")
        self.reason_code = reason_code


def _is_x_key(k: str) -> bool:
    return k.startswith("x-")


def _require_dict(x: Any, ctx: str) -> dict:
    if not isinstance(x, dict):
        raise SuiteRowValidationError("WM_SUITE_ROW_TYPE", f"{ctx} must be dict")
    return x


def _require_list(x: Any, ctx: str) -> list:
    if not isinstance(x, list):
        raise SuiteRowValidationError("WM_SUITE_ROW_TYPE", f"{ctx} must be list")
    return x


def _require_int(x: Any, ctx: str) -> int:
    if isinstance(x, bool) or not isinstance(x, int):
        raise SuiteRowValidationError("WM_SUITE_ROW_TYPE", f"{ctx} must be int")
    return x


def _require_str(x: Any, ctx: str) -> str:
    if not isinstance(x, str):
        raise SuiteRowValidationError("WM_SUITE_ROW_TYPE", f"{ctx} must be str")
    return x


def _check_allowed_keys(obj: dict, allowed: set[str], ctx: str) -> None:
    for k in obj.keys():
        if k in allowed or _is_x_key(k):
            continue
        raise SuiteRowValidationError("WM_SUITE_ROW_EXTRA_KEY", f"{ctx} has extra key {k!r}")


def validate_wmworld_suite_row(suite_row: dict) -> None:
    sr = _require_dict(suite_row, "suite_row")
    _check_allowed_keys(sr, {"env", "max_steps", "generator", "params", "start", "objective"}, "suite_row")

    env = _require_str(sr.get("env"), "suite_row.env")
    if env != "wmworld-v1":
        raise SuiteRowValidationError("WM_SUITE_ROW_ENV", "env must be wmworld-v1")

    max_steps = _require_int(sr.get("max_steps"), "suite_row.max_steps")
    if max_steps <= 0 or max_steps > 4096:
        raise SuiteRowValidationError("WM_SUITE_ROW_MAX_STEPS", "max_steps out of bounds")

    gen = _require_dict(sr.get("generator"), "suite_row.generator")
    _check_allowed_keys(
        gen,
        {
            "kind",
            "n",
            "d",
            "x_min",
            "x_max",
            "w_true_min",
            "w_true_max",
            "b_true_min",
            "b_true_max",
            "noise_ppm",
        },
        "suite_row.generator",
    )
    kind = _require_str(gen.get("kind"), "generator.kind")
    if kind != "wm_linear_sep_int_v1":
        raise SuiteRowValidationError("WM_SUITE_ROW_GEN_KIND", "generator.kind mismatch")

    n = _require_int(gen.get("n"), "generator.n")
    d = _require_int(gen.get("d"), "generator.d")
    if n < 1 or n > 4096:
        raise SuiteRowValidationError("WM_SUITE_ROW_N", "n out of bounds")
    if d < 1 or d > 64:
        raise SuiteRowValidationError("WM_SUITE_ROW_D", "d out of bounds")

    x_min = _require_int(gen.get("x_min"), "generator.x_min")
    x_max = _require_int(gen.get("x_max"), "generator.x_max")
    if x_min > x_max:
        raise SuiteRowValidationError("WM_SUITE_ROW_RANGE", "x_min > x_max")

    w_true_min = _require_int(gen.get("w_true_min"), "generator.w_true_min")
    w_true_max = _require_int(gen.get("w_true_max"), "generator.w_true_max")
    if w_true_min > w_true_max:
        raise SuiteRowValidationError("WM_SUITE_ROW_RANGE", "w_true_min > w_true_max")

    b_true_min = _require_int(gen.get("b_true_min"), "generator.b_true_min")
    b_true_max = _require_int(gen.get("b_true_max"), "generator.b_true_max")
    if b_true_min > b_true_max:
        raise SuiteRowValidationError("WM_SUITE_ROW_RANGE", "b_true_min > b_true_max")

    noise_ppm = _require_int(gen.get("noise_ppm"), "generator.noise_ppm")
    if noise_ppm < 0 or noise_ppm > 1_000_000:
        raise SuiteRowValidationError("WM_SUITE_ROW_NOISE", "noise_ppm out of bounds")

    params = _require_list(sr.get("params"), "suite_row.params")
    if len(params) != d + 1:
        raise SuiteRowValidationError("WM_SUITE_ROW_PARAMS_LEN", "d != len(params)-1")

    seen_ids: set[str] = set()
    for i, p in enumerate(params):
        pd = _require_dict(p, f"params[{i}]")
        _check_allowed_keys(pd, {"param_id", "values_int"}, f"params[{i}]")
        pid = _require_str(pd.get("param_id"), f"params[{i}].param_id")
        if pid in seen_ids:
            raise SuiteRowValidationError("WM_SUITE_ROW_PARAM_ID_DUP", "param_id not unique")
        seen_ids.add(pid)
        vals = _require_list(pd.get("values_int"), f"params[{i}].values_int")
        if len(vals) < 2 or len(vals) > 64:
            raise SuiteRowValidationError("WM_SUITE_ROW_VALUES_LEN", "values_int length out of bounds")
        for j, v in enumerate(vals):
            _require_int(v, f"params[{i}].values_int[{j}]")

    start = _require_dict(sr.get("start"), "suite_row.start")
    _check_allowed_keys(start, {"p_idx", "param_value_idxs"}, "suite_row.start")
    p_idx = _require_int(start.get("p_idx"), "start.p_idx")
    if p_idx < 0 or p_idx >= len(params):
        raise SuiteRowValidationError("WM_SUITE_ROW_PIDX", "p_idx out of range")
    pv = _require_list(start.get("param_value_idxs"), "start.param_value_idxs")
    if len(pv) != len(params):
        raise SuiteRowValidationError("WM_SUITE_ROW_START_LEN", "start.param_value_idxs length mismatch")
    for i, idx in enumerate(pv):
        idx_i = _require_int(idx, f"start.param_value_idxs[{i}]")
        vals_len = len(_require_list(_require_dict(params[i], f"params[{i}]").get("values_int"), f"params[{i}].values_int"))
        if idx_i < 0 or idx_i >= vals_len:
            raise SuiteRowValidationError("WM_SUITE_ROW_START_RANGE", "start.param_value_idxs out of range")

    obj = _require_dict(sr.get("objective"), "suite_row.objective")
    _check_allowed_keys(obj, {"metric_name", "min_accuracy"}, "suite_row.objective")
    metric_name = _require_str(obj.get("metric_name"), "objective.metric_name")
    if metric_name != "accuracy":
        raise SuiteRowValidationError("WM_SUITE_ROW_METRIC", "metric_name must be accuracy")
    min_acc_raw = _require_str(obj.get("min_accuracy"), "objective.min_accuracy")
    try:
        thr_dec = decode_rational(min_acc_raw)
    except Exception as exc:  # noqa: BLE001
        raise SuiteRowValidationError("WM_SUITE_ROW_MINACC", "min_accuracy parse fail") from exc
    thr = Fraction(thr_dec, 1) if isinstance(thr_dec, int) else thr_dec
    if thr < 0 or thr > 1:
        raise SuiteRowValidationError("WM_SUITE_ROW_MINACC", "min_accuracy out of [0,1]")


@dataclass
class _State:
    t: int
    p_idx: int
    param_value_idxs: list[int]
    last_eval: dict
    trace: list[dict]
    dataset: list[dict] | None


class WMWorldV1Env:
    def __init__(self, suite_row: dict, epoch_key: bytes, inst_hash: bytes):
        validate_wmworld_suite_row(suite_row)
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
        self.param_value_lens = [len(p["values_int"]) for p in self.params]

        start = suite_row["start"]
        self.start_p_idx = int(start["p_idx"])
        self.start_param_value_idxs = [int(x) for x in start["param_value_idxs"]]

        obj = suite_row["objective"]
        thr_dec = decode_rational(str(obj["min_accuracy"]))
        thr = Fraction(thr_dec, 1) if isinstance(thr_dec, int) else thr_dec
        self._init_last_eval = {
            "has_value": False,
            "pass": False,
            "metric_name": str(obj["metric_name"]),
            "metric_value": "",
            "threshold": encode_rational(thr),
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
        )
        # Dataset is generated on reset (spec), but eval helper regenerates deterministically too.
        from cdel.v1_7r.science.generators_v1 import gen_wm_linear_sep_int_v1

        self._state.dataset = gen_wm_linear_sep_int_v1(
            epoch_key=self.epoch_key,
            inst_hash=self.inst_hash,
            gen_cfg=self.suite_row["generator"],
        )
        return self._obs()

    def _obs(self) -> dict:
        assert self._state is not None
        gen = self.suite_row["generator"]
        task_summary = {"n": int(gen["n"]), "d": int(gen["d"]), "noise_ppm": int(gen["noise_ppm"])}
        return {
            "env": "wmworld-v1",
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
        # Store canonical action
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
            self._state.last_eval = eval_wmworld(
                suite_row=self.suite_row,
                epoch_key=self.epoch_key,
                inst_hash=self.inst_hash,
                param_value_idxs=list(self._state.param_value_idxs),
            )
        else:
            # action_is_valid should prevent this, but fail-closed.
            raise ValueError("INVALID_ACTION")

        # Advance time
        self._state.t += 1

        done = False
        if name == "EVAL" and bool(self._state.last_eval.get("pass")):
            done = True
        if self._state.t >= self.max_steps:
            done = True

        self._done = done
        info = {"trace_hash": self.trace_hash()}
        return self._obs(), done, info
