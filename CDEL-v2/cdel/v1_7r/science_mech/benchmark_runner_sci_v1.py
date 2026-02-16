"""SCI-RSI v1.7r: mechanism benchmark runner for scientific envs.

Computes base vs new metrics for a benchmark pack, deterministically.

Notes:
- This runner is deterministic and uses only integer/rational decision logic via env/eval code.
- It runs episodes by emitting primitive actions into the env.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Iterable

from cdel.v1_7r.canon import canon_bytes, hash_json
from cdel.v1_7r.envs.causalworld_v1 import CausalWorldV1Env
from cdel.v1_7r.envs.wmworld_v1 import WMWorldV1Env
from cdel.v1_7r.science.eval_v1 import eval_causalworld, eval_wmworld


def _require_dict(x: Any, name: str) -> dict:
    if not isinstance(x, dict):
        raise TypeError(f"{name} must be dict")
    return x


def _require_list(x: Any, name: str) -> list:
    if not isinstance(x, list):
        raise TypeError(f"{name} must be list")
    return x


def _require_str(x: Any, name: str) -> str:
    if not isinstance(x, str):
        raise TypeError(f"{name} must be str")
    return x


def _require_int(x: Any, name: str) -> int:
    if isinstance(x, bool) or not isinstance(x, int):
        raise TypeError(f"{name} must be int")
    return x


def _sha256_bytes(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def _parse_key_bytes(x: Any, *, name: str) -> bytes:
    """Parse a 32-byte key from bytes or hex-like string.

    Accepted string forms:
    - "sha256:<64 hex>"
    - "<64 hex>"
    """
    if isinstance(x, (bytes, bytearray)):
        b = bytes(x)
        if len(b) != 32:
            raise ValueError(f"{name} must be 32 bytes")
        return b
    if isinstance(x, str):
        s = x.strip()
        if s.startswith("sha256:"):
            s = s.split(":", 1)[1]
        if len(s) != 64:
            raise ValueError(f"{name} must be 64 hex chars (or sha256:...)")
        return bytes.fromhex(s)
    raise TypeError(f"{name} must be bytes or str")


def _suite_rows_from_instance_pack(instance_pack: Any) -> list[dict]:
    if isinstance(instance_pack, list):
        if not all(isinstance(x, dict) for x in instance_pack):
            raise TypeError("instance_pack list must contain dict suite_rows")
        return list(instance_pack)
    if isinstance(instance_pack, dict):
        if "suite_rows" in instance_pack:
            sr = instance_pack["suite_rows"]
            if not isinstance(sr, list) or not all(isinstance(x, dict) for x in sr):
                raise TypeError("instance_pack.suite_rows must be list[dict]")
            return list(sr)
    raise TypeError("instance_pack must be list[dict] or {'suite_rows':[...]}")  # keep strict for now


def _product_int(xs: list[int]) -> int:
    p = 1
    for x in xs:
        p *= int(x)
    return p


def _iter_index_tuples(lengths: list[int], *, max_count: int) -> Iterable[list[int]]:
    """Lexicographic tuples with last index varying fastest; capped by max_count."""
    if not lengths:
        return
    if any(L <= 0 for L in lengths):
        return
    idx = [0] * len(lengths)
    yielded = 0
    while True:
        yield list(idx)
        yielded += 1
        if yielded >= max_count:
            return
        # increment
        i = len(lengths) - 1
        while i >= 0:
            idx[i] += 1
            if idx[i] < lengths[i]:
                break
            idx[i] = 0
            i -= 1
        if i < 0:
            return


def _best_pointer_moves(curr: int, target: int, n_params: int) -> list[dict]:
    if n_params <= 0:
        return []
    curr = curr % n_params
    target = target % n_params
    next_steps = (target - curr) % n_params
    prev_steps = (curr - target) % n_params
    if next_steps <= prev_steps:
        return [{"name": "NEXT_PARAM", "args": {}} for _ in range(next_steps)]
    return [{"name": "PREV_PARAM", "args": {}} for _ in range(prev_steps)]


def _best_value_moves(curr: int, target: int, L: int) -> list[dict]:
    if L <= 0:
        return []
    curr = curr % L
    target = target % L
    inc_steps = (target - curr) % L
    dec_steps = (curr - target) % L
    if inc_steps <= dec_steps:
        return [{"name": "INC_VALUE", "args": {}} for _ in range(inc_steps)]
    return [{"name": "DEC_VALUE", "args": {}} for _ in range(dec_steps)]


def _plan_set_params(
    *,
    start_p_idx: int,
    start_param_value_idxs: list[int],
    value_lens: list[int],
    target_value_idxs: list[int],
) -> list[dict]:
    n = len(value_lens)
    if len(start_param_value_idxs) != n or len(target_value_idxs) != n:
        raise ValueError("param length mismatch")
    p = int(start_p_idx)
    curr = list(start_param_value_idxs)
    actions: list[dict] = []
    for i in range(n):
        actions.extend(_best_pointer_moves(p, i, n))
        p = i
        actions.extend(_best_value_moves(curr[i], target_value_idxs[i], value_lens[i]))
        curr[i] = int(target_value_idxs[i])
    actions.append({"name": "EVAL", "args": {}})
    return actions


def _bytes_for_action(action: dict) -> int:
    # Deterministic accounting: bytes of canonical JSON for the action dict.
    return len(canon_bytes(action))


@dataclass(frozen=True)
class Budget:
    max_env_steps: int
    max_bytes_hashed: int
    max_verifier_gas: int


def _parse_budget(b: Any) -> Budget:
    d = _require_dict(b, "budget")
    max_env_steps = _require_int(d.get("max_env_steps"), "budget.max_env_steps")
    max_bytes = _require_int(d.get("max_bytes_hashed"), "budget.max_bytes_hashed")
    max_gas = _require_int(d.get("max_verifier_gas"), "budget.max_verifier_gas")
    if max_env_steps <= 0:
        raise ValueError("max_env_steps must be > 0")
    if max_bytes < 0 or max_gas < 0:
        raise ValueError("budget values must be >= 0")
    return Budget(max_env_steps=max_env_steps, max_bytes_hashed=max_bytes, max_verifier_gas=max_gas)


def _derive_inst_hash_bytes(suite_row: dict) -> bytes:
    return _sha256_bytes(canon_bytes(suite_row))


def _find_passing_config_wmworld(suite_row: dict, epoch_key: bytes, inst_hash: bytes) -> list[int] | None:
    params = suite_row.get("params")
    if not isinstance(params, list):
        return None
    lengths = []
    for p in params:
        if not isinstance(p, dict):
            return None
        vals = p.get("values_int")
        if not isinstance(vals, list):
            return None
        lengths.append(len(vals))

    combos = _product_int(lengths)
    max_search = min(combos, 4096)  # hard cap to keep bounded

    for idxs in _iter_index_tuples(lengths, max_count=max_search):
        last_eval = eval_wmworld(
            suite_row=suite_row,
            epoch_key=epoch_key,
            inst_hash=inst_hash,
            param_value_idxs=idxs,
        )
        if bool(last_eval.get("pass")):
            return idxs
    return None


def _find_passing_config_causalworld(suite_row: dict, epoch_key: bytes, inst_hash: bytes) -> list[int] | None:
    params = suite_row.get("params")
    if not isinstance(params, list) or len(params) != 3:
        return None
    # estimator length
    p0 = params[0]
    if not isinstance(p0, dict):
        return None
    vals_enum = p0.get("values_enum")
    if not isinstance(vals_enum, list):
        return None
    lengths = [len(vals_enum), 2, 2]
    combos = _product_int(lengths)
    max_search = min(combos, 128)

    for idxs in _iter_index_tuples(lengths, max_count=max_search):
        last_eval = eval_causalworld(
            suite_row=suite_row,
            epoch_key=epoch_key,
            inst_hash=inst_hash,
            param_value_idxs=idxs,
        )
        if bool(last_eval.get("pass")):
            return idxs
    return None


def _run_episode(
    *,
    env_kind: str,
    suite_row: dict,
    epoch_key: bytes,
    inst_hash: bytes,
    solver_kind: str,
    budget: Budget,
) -> tuple[bool, int, int, int]:
    """Run one episode and return (solved, steps, bytes_hashed, verifier_gas)."""
    steps = 0
    bytes_hashed = 0
    verifier_gas = 0

    if env_kind == "wmworld-v1":
        env = WMWorldV1Env(suite_row, epoch_key, inst_hash)
        obs = env.reset()
        start_p = env._state.p_idx  # type: ignore[union-attr]
        start_idxs = list(env._state.param_value_idxs)  # type: ignore[union-attr]
        lens = list(env.param_value_lens)
        if solver_kind == "baseline_v1":
            plan = [{"name": "EVAL", "args": {}}]
        elif solver_kind == "bruteforce_v1":
            target = _find_passing_config_wmworld(suite_row, epoch_key, inst_hash)
            if target is None:
                plan = [{"name": "EVAL", "args": {}}]
            else:
                plan = _plan_set_params(
                    start_p_idx=int(start_p),
                    start_param_value_idxs=start_idxs,
                    value_lens=lens,
                    target_value_idxs=target,
                )
        else:
            raise ValueError("unknown solver_kind")
    elif env_kind == "causalworld-v1":
        env = CausalWorldV1Env(suite_row, epoch_key, inst_hash)
        obs = env.reset()
        start_p = env._state.p_idx  # type: ignore[union-attr]
        start_idxs = list(env._state.param_value_idxs)  # type: ignore[union-attr]
        lens = list(env.param_value_lens)
        if solver_kind == "baseline_v1":
            plan = [{"name": "EVAL", "args": {}}]
        elif solver_kind == "bruteforce_v1":
            target = _find_passing_config_causalworld(suite_row, epoch_key, inst_hash)
            if target is None:
                plan = [{"name": "EVAL", "args": {}}]
            else:
                plan = _plan_set_params(
                    start_p_idx=int(start_p),
                    start_param_value_idxs=start_idxs,
                    value_lens=lens,
                    target_value_idxs=target,
                )
        else:
            raise ValueError("unknown solver_kind")
    else:
        raise ValueError("env_kind invalid")

    done = False
    for action in plan:
        if steps >= budget.max_env_steps:
            break
        bytes_hashed += _bytes_for_action(action)
        if bytes_hashed > budget.max_bytes_hashed:
            break
        obs, done, _info = env.step(action)
        steps += 1
        if done:
            break

    solved = bool(obs.get("last_eval", {}).get("pass")) if isinstance(obs, dict) else False
    return solved, steps, bytes_hashed, verifier_gas


def _empty_metrics() -> dict[str, int]:
    return {
        "episodes_total": 0,
        "episodes_solved": 0,
        "env_steps_total": 0,
        "bytes_hashed_total": 0,
        "verifier_gas_total": 0,
    }


def _add_metrics(m: dict[str, int], *, solved: bool, steps: int, bytes_hashed: int, gas: int) -> None:
    m["episodes_total"] += 1
    if solved:
        m["episodes_solved"] += 1
    m["env_steps_total"] += int(steps)
    m["bytes_hashed_total"] += int(bytes_hashed)
    m["verifier_gas_total"] += int(gas)


def run_mech_benchmark_pack_sci(
    *,
    benchmark_pack: dict[str, Any],
    patch: dict[str, Any],
    base_solver_kind: str = "baseline_v1",
) -> dict[str, Any]:
    """Run a SCI benchmark pack, producing a mech_patch_eval_cert_sci_v1 dict.

    base_solver_kind is the baseline mechanism.
    patch['patch_kind'] selects the 'new' mechanism.
    """
    pack = _require_dict(benchmark_pack, "benchmark_pack")
    patch_d = _require_dict(patch, "patch")

    patch_id = _require_str(patch_d.get("patch_id"), "patch.patch_id")
    patch_kind = _require_str(patch_d.get("patch_kind"), "patch.patch_kind")

    cases = _require_list(pack.get("cases"), "benchmark_pack.cases")
    pack_hash = hash_json(pack)

    out_cases: list[dict[str, Any]] = []
    totals_base = _empty_metrics()
    totals_new = _empty_metrics()

    for case in cases:
        c = _require_dict(case, "case")
        case_id = _require_str(c.get("case_id"), "case.case_id")
        env_kind = _require_str(c.get("env_kind"), "case.env_kind")
        epoch_key = _parse_key_bytes(c.get("epoch_key"), name="case.epoch_key")
        budget = _parse_budget(c.get("budget"))

        suite_rows = _suite_rows_from_instance_pack(c.get("instance_pack"))

        base_m = _empty_metrics()
        new_m = _empty_metrics()

        for suite_row in suite_rows:
            inst_hash = _derive_inst_hash_bytes(suite_row)

            solved_b, steps_b, bytes_b, gas_b = _run_episode(
                env_kind=env_kind,
                suite_row=suite_row,
                epoch_key=epoch_key,
                inst_hash=inst_hash,
                solver_kind=base_solver_kind,
                budget=budget,
            )
            _add_metrics(base_m, solved=solved_b, steps=steps_b, bytes_hashed=bytes_b, gas=gas_b)

            solved_n, steps_n, bytes_n, gas_n = _run_episode(
                env_kind=env_kind,
                suite_row=suite_row,
                epoch_key=epoch_key,
                inst_hash=inst_hash,
                solver_kind=patch_kind,
                budget=budget,
            )
            _add_metrics(new_m, solved=solved_n, steps=steps_n, bytes_hashed=bytes_n, gas=gas_n)

        # Aggregate totals
        for k in totals_base:
            totals_base[k] += base_m[k]
            totals_new[k] += new_m[k]

        out_cases.append(
            {
                "case_id": case_id,
                "env_kind": env_kind,
                "base": base_m,
                "new": new_m,
            }
        )

    cert = {
        "schema": "mech_patch_eval_cert_sci_v1",
        "schema_version": 1,
        "patch_id": patch_id,
        "patch_hash": hash_json(patch_d),
        "benchmark_pack_hash": pack_hash,
        "cases": out_cases,
        "totals": {"base": totals_base, "new": totals_new},
        "x-base_solver_kind": base_solver_kind,
    }
    return cert
