"""Dev-only diagnostics helpers for nuisance regimes (CAOE v1.2)."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Any, Iterable
import math

base_dir = Path(__file__).resolve().parents[1]
repo_root = base_dir.parents[1]
cdel_root = repo_root / "CDEL-v2"
if cdel_root.exists() and str(cdel_root) not in sys.path:
    sys.path.insert(0, str(cdel_root))

from api_v1 import canonical_json_bytes  # noqa: E402

try:  # noqa: E402
    from extensions.caoe_v1.dsl.bounded_program_v1 import execute
    from extensions.caoe_v1.eval.phi_inputs_v1 import build_phi_inputs, push_obs_history, push_do_history
    from extensions.caoe_v1.eval.ccai_x_core_v1 import _macro_state_from_phi
    from extensions.caoe_v1.eval.switchboard_env_v1 import SwitchboardEnv
except Exception:  # pragma: no cover - dev-only dependency
    execute = None
    build_phi_inputs = None
    push_obs_history = None
    push_do_history = None
    _macro_state_from_phi = None
    SwitchboardEnv = None


def _is_primitive(value: Any) -> bool:
    return value is None or isinstance(value, (int, float, str, bool))


def _json_primitive(value: Any) -> bool:
    if _is_primitive(value):
        return True
    if isinstance(value, list):
        return all(_json_primitive(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _json_primitive(val) for key, val in value.items())
    return False


def stable_repr(value: Any) -> Any:
    """Return a stable JSON-serializable representation for trace fields."""
    if _json_primitive(value):
        return value
    try:
        payload = canonical_json_bytes(value)
        digest = hashlib.sha256(payload).hexdigest()
        desc = f"{type(value).__name__}:{len(payload)}"
        return {"sha256": digest, "desc": desc}
    except Exception:
        payload = repr(value).encode("utf-8")
        digest = hashlib.sha256(payload).hexdigest()
        desc = f"{type(value).__name__}:{len(payload)}"
        return {"sha256": digest, "desc": desc}


def _episode_index(suitepack: dict[str, Any]) -> dict[str, dict[str, Any]]:
    episodes = suitepack.get("episodes")
    if not isinstance(episodes, list):
        return {}
    by_id: dict[str, dict[str, Any]] = {}
    for ep in episodes:
        if not isinstance(ep, dict):
            continue
        ep_id = ep.get("episode_id")
        if isinstance(ep_id, str) and ep_id:
            by_id[ep_id] = ep
    return by_id


def _episode_seed(ep: dict[str, Any]) -> int:
    seed = ep.get("seed")
    if seed is None:
        seed = ep.get("episode_seed")
    try:
        return int(seed)
    except (TypeError, ValueError):
        return 0


def _goal_reached(goal: dict[str, Any], macro_state: dict[str, Any]) -> bool:
    for key, value in goal.items():
        if key not in macro_state:
            continue
        if macro_state.get(key) != value:
            return False
    return True


def _compute_success_from_records(
    *,
    records: list[dict[str, Any]],
    base_ontology: dict[str, Any],
    suitepack: dict[str, Any],
    episode: dict[str, Any],
) -> tuple[bool, int | None]:
    if execute is None or build_phi_inputs is None or push_obs_history is None or push_do_history is None:
        return False, None
    phi_prog = base_ontology.get("measurement_phi") or {}
    symbols = base_ontology.get("symbols") or []
    limits = base_ontology.get("complexity_limits") or {}
    max_state_history = int(limits.get("max_state_history", 1))
    suite_token = suitepack.get("suite_token")
    goal = episode.get("goal")
    if goal is None:
        goal_latent = episode.get("goal_latent")
        if isinstance(goal_latent, list):
            goal = {f"x{i}": int(goal_latent[i]) for i in range(len(goal_latent))}
    if not isinstance(goal, dict):
        return False, None

    obs_history: list[list[int]] = []
    obs_trace: list[list[int]] = []
    do_history: list[dict[str, Any]] = []
    first_success_t: int | None = None

    for idx, rec in enumerate(records):
        if idx > 0:
            prev = records[idx - 1]
            do_type = str(prev.get("do_event_type") or "NOOP")
            do_payload = prev.get("do_event_payload") or {}
            if not isinstance(do_payload, dict):
                do_payload = {}
            push_do_history(do_history, do_type, do_payload)
        obs = rec.get("o_t")
        if not isinstance(obs, list):
            continue
        obs_trace.append([int(v) for v in obs])
        push_obs_history(obs_history, obs_trace[-1], max_state_history)
        try:
            phi_out = execute(
                phi_prog,
                build_phi_inputs(
                    phi_prog,
                    obs_history,
                    int(rec.get("t", idx)),
                    suite_token,
                    obs_trace=obs_trace,
                    do_event_history=do_history,
                ),
            )
            macro_state = _macro_state_from_phi(phi_out, symbols)
        except Exception:
            continue
        if idx > 0 and _goal_reached(goal, macro_state):
            first_success_t = int(rec.get("t", idx))
            break

    return first_success_t is not None, first_success_t


def _action_tuple(action: dict[str, Any]) -> tuple | None:
    if not isinstance(action, dict):
        return None
    typ = action.get("type")
    if typ == "SET_X":
        idx = action.get("index")
        val = action.get("value")
        if isinstance(idx, int) and isinstance(val, int):
            return ("SET_X", int(idx), int(val))
    if typ == "TOGGLE_N":
        idx = action.get("index")
        if isinstance(idx, int):
            return ("TOGGLE_N", int(idx))
    if typ == "NOOP":
        return ("NOOP",)
    return None


def _action_id(action: dict[str, Any]) -> int | None:
    if SwitchboardEnv is None:
        return None
    tup = _action_tuple(action)
    if tup is None or tup == ("NOOP",):
        return None
    actions = SwitchboardEnv.action_set()
    try:
        return actions.index(tup)
    except ValueError:
        return None


def _is_bitvec(obs: list[Any]) -> bool:
    if not isinstance(obs, list) or not obs:
        return False
    for val in obs:
        if isinstance(val, bool):
            continue
        if isinstance(val, int) and val in (0, 1):
            continue
        return False
    return True


def _stable_bytes(value: Any) -> bytes:
    try:
        return canonical_json_bytes(value)
    except Exception:
        return repr(value).encode("utf-8")


def _bucket_diff_indices(a: Any, b: Any, bucket_size: int = 8) -> tuple[list[int], int]:
    a_bytes = _stable_bytes(a)
    b_bytes = _stable_bytes(b)
    total_len = max(len(a_bytes), len(b_bytes))
    if total_len == 0:
        return [], 0
    bucket_count = int(math.ceil(total_len / float(bucket_size)))
    changed: list[int] = []
    for idx in range(bucket_count):
        start = idx * bucket_size
        end = start + bucket_size
        if a_bytes[start:end] != b_bytes[start:end]:
            changed.append(idx)
    return changed, bucket_count


def _obs_change_indices(obs: Any, nxt_obs: Any) -> tuple[list[int], int]:
    if isinstance(obs, list) and isinstance(nxt_obs, list) and _is_bitvec(obs) and _is_bitvec(nxt_obs):
        changed = [i for i, (a, b) in enumerate(zip(obs, nxt_obs)) if int(a) != int(b)]
        return changed, len(obs)
    return _bucket_diff_indices(obs, nxt_obs)


def _flip_rate_summary(changes: list[list[int]], width: int) -> dict[str, Any]:
    total = len(changes)
    counts = [0] * width
    for idxs in changes:
        for idx in idxs:
            if 0 <= idx < width:
                counts[idx] += 1
    rates = {
        str(i): (counts[i] / total if total else 0.0)
        for i in range(width)
        if counts[i] > 0 or total == 0
    }
    return {
        "total_transitions": int(total),
        "per_index_flip_rate": rates,
        "per_index_flip_count": {str(i): int(counts[i]) for i in range(width) if counts[i] > 0},
    }


def _action_conditioned_effect_map(
    records: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, int], dict[str, Any]]:
    action_map: dict[str, dict[str, Any]] = {}
    action_hits: dict[str, int] = {}
    transitions: list[tuple[int | None, list[int]]] = []
    for idx in range(len(records) - 1):
        rec = records[idx]
        nxt = records[idx + 1]
        obs = rec.get("o_t")
        nxt_obs = nxt.get("o_t")
        if obs is None or nxt_obs is None:
            continue
        changed, _width = _obs_change_indices(obs, nxt_obs)
        act = rec.get("a_applied")
        act_id = _action_id(act if isinstance(act, dict) else {})
        transitions.append((act_id, changed))
        if act_id is None:
            continue
        key = f"action_{act_id}"
        entry = action_map.setdefault(key, {"changed_indices": set(), "n": 0})
        for idx_changed in changed:
            entry["changed_indices"].add(int(idx_changed))
        entry["n"] = int(entry["n"]) + 1
        action_hits[key] = action_hits.get(key, 0) + 1
    out_map: dict[str, Any] = {}
    for key, entry in action_map.items():
        out_map[key] = {
            "changed_indices": sorted(entry["changed_indices"]),
            "n": int(entry["n"]),
        }

    total_changes = 0
    action_changes = 0
    noise_changes = 0
    prev_action: int | None = None
    for act_id, changed in transitions:
        delta = len(changed)
        total_changes += delta
        if prev_action is None or act_id != prev_action:
            action_changes += delta
        else:
            noise_changes += delta
        prev_action = act_id
    action_corr = (action_changes / total_changes) if total_changes else 0.0
    noise_score = (noise_changes / total_changes) if total_changes else 0.0
    score_meta = {
        "action_correlation_score": float(action_corr),
        "noise_score": float(noise_score),
    }
    return out_map, action_hits, score_meta


def build_failure_signatures(
    *,
    base_ontology: dict[str, Any],
    suitepack_dev: dict[str, Any],
    dev_logs: list[dict[str, Any]],
    regime_filter: Iterable[str] | None = None,
) -> dict[str, Any]:
    episode_by_id = _episode_index(suitepack_dev)
    target_regimes = set(regime_filter or [])
    signatures: dict[str, Any] = {}

    by_regime: dict[str, list[dict[str, Any]]] = {}
    for log in dev_logs:
        if not isinstance(log, dict):
            continue
        regime_id = str(log.get("regime_id") or "")
        episode_id = str(log.get("episode_id") or "")
        records = log.get("records")
        if not regime_id or not episode_id or not isinstance(records, list):
            continue
        if target_regimes and regime_id not in target_regimes:
            continue
        entry = {
            "regime_id": regime_id,
            "episode_id": episode_id,
            "records": records,
            "episode": episode_by_id.get(episode_id, {}),
        }
        ep = entry["episode"]
        entry["seed"] = _episode_seed(ep) if isinstance(ep, dict) else 0
        success, _first_success_t = _compute_success_from_records(
            records=records,
            base_ontology=base_ontology,
            suitepack=suitepack_dev,
            episode=ep if isinstance(ep, dict) else {},
        )
        entry["success"] = bool(success)
        by_regime.setdefault(regime_id, []).append(entry)

    for regime_id, entries in by_regime.items():
        failing = [e for e in entries if not e.get("success", False)]
        if not failing:
            continue
        failing.sort(key=lambda e: (e["episode_id"], int(e.get("seed", 0))))
        picked = failing[0]
        records = picked["records"]
        if not records:
            continue
        obs0 = records[0].get("o_t")
        if obs0 is None:
            continue
        width = 0
        changes: list[list[int]] = []
        for idx in range(len(records) - 1):
            obs = records[idx].get("o_t")
            nxt_obs = records[idx + 1].get("o_t")
            if obs is None or nxt_obs is None:
                continue
            changed, width_candidate = _obs_change_indices(obs, nxt_obs)
            if width_candidate > width:
                width = width_candidate
            changes.append(changed)
        if width == 0:
            continue
        flip_rate_summary = _flip_rate_summary(changes, width)
        action_map, _action_hits, scores = _action_conditioned_effect_map(records)
        episode_len = max(len(records) - 1, 0)
        ep = picked.get("episode") or {}
        max_steps = int(ep.get("max_steps", 0)) if isinstance(ep, dict) else 0
        done_reason = "goal_not_reached"
        if max_steps and episode_len >= max_steps:
            done_reason = "max_steps"
        signatures[regime_id] = {
            "flip_rate_summary": flip_rate_summary,
            "action_conditioned_effect_map": action_map,
            "terminal_reason": done_reason,
            "episode_len": int(episode_len),
            "dev_episode_ids_used": [picked["episode_id"]],
            "action_correlation_score": scores["action_correlation_score"],
            "noise_score": scores["noise_score"],
            "obs_width": int(width),
        }
    return signatures


def build_witness_trace(
    *,
    base_ontology: dict[str, Any],
    suitepack_dev: dict[str, Any],
    dev_logs: list[dict[str, Any]],
    regime_id: str,
) -> dict[str, Any] | None:
    episode_by_id = _episode_index(suitepack_dev)
    entries: list[dict[str, Any]] = []
    for log in dev_logs:
        if not isinstance(log, dict):
            continue
        if str(log.get("regime_id") or "") != regime_id:
            continue
        ep_id = str(log.get("episode_id") or "")
        records = log.get("records")
        if not ep_id or not isinstance(records, list):
            continue
        ep = episode_by_id.get(ep_id, {})
        seed = _episode_seed(ep) if isinstance(ep, dict) else 0
        success, first_success_t = _compute_success_from_records(
            records=records,
            base_ontology=base_ontology,
            suitepack=suitepack_dev,
            episode=ep if isinstance(ep, dict) else {},
        )
        entries.append(
            {
                "episode_id": ep_id,
                "seed": seed,
                "records": records,
                "success": bool(success),
                "first_success_t": first_success_t,
                "episode": ep if isinstance(ep, dict) else {},
            }
        )
    failing = [e for e in entries if not e.get("success", False)]
    if not failing:
        return None
    failing.sort(key=lambda e: (e["episode_id"], int(e.get("seed", 0))))
    picked = failing[0]
    records = picked["records"]
    steps: list[dict[str, Any]] = []
    for idx, rec in enumerate(records):
        steps.append(
            {
                "t": int(rec.get("t", idx)),
                "o": stable_repr(rec.get("o_t")),
                "a": stable_repr(rec.get("a_applied")),
                "r": 0,
                "done": False,
                "info": {},
            }
        )
    if steps:
        steps[-1]["done"] = True
    ep = picked.get("episode") or {}
    max_steps = int(ep.get("max_steps", 0)) if isinstance(ep, dict) else 0
    episode_len = max(len(records) - 1, 0)
    done_reason = "goal_not_reached"
    if max_steps and episode_len >= max_steps:
        done_reason = "max_steps"
    trace = {
        "schema": "caoe_dev_witness_trace_v1",
        "regime_id": regime_id,
        "episode_id": picked["episode_id"],
        "seed": int(picked["seed"]),
        "t_max": int(max_steps if max_steps else 0),
        "steps": steps,
        "summary": {
            "success": 1 if picked.get("success") else 0,
            "done_reason": done_reason,
            "first_failure_t": int(steps[-1]["t"]) if steps else 0,
        },
    }
    return trace


def compute_episode_successes(
    *,
    ontology: dict[str, Any],
    suitepack: dict[str, Any],
    logs: list[dict[str, Any]],
) -> dict[str, bool]:
    episode_by_id = _episode_index(suitepack)
    results: dict[str, bool] = {}
    for log in logs:
        if not isinstance(log, dict):
            continue
        ep_id = str(log.get("episode_id") or "")
        records = log.get("records")
        if not ep_id or not isinstance(records, list):
            continue
        episode = episode_by_id.get(ep_id, {})
        success, _ = _compute_success_from_records(
            records=records,
            base_ontology=ontology,
            suitepack=suitepack,
            episode=episode if isinstance(episode, dict) else {},
        )
        results[ep_id] = bool(success)
    return results
