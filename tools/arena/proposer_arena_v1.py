#!/usr/bin/env python3
"""Agentic Proposer Arena (APA) v1 runtime.

Surrogate ranking / sovereign promotion:
- RE3 generates and ranks many candidates.
- RE2 sovereignly adjudicates only one winner per tick.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from cdel.v1_7r.canon import canon_bytes, write_canon_json
from cdel.v18_0.authority.authority_hash_v1 import auth_hash, load_authority_pins
from cdel.v18_0.ccap_runtime_v1 import (
    apply_patch_bytes,
    ccap_payload_id,
    compute_repo_base_tree_id_tolerant,
    materialize_repo_snapshot,
)
from cdel.v18_0.omega_common_v1 import (
    canon_hash_obj,
    load_canon_dict,
    repo_root,
    require_relpath,
    validate_schema,
    write_hashed_json,
)
from cdel.v18_0.patch_diff_v1 import build_unified_patch_bytes
from cdel.v19_0.common_v1 import validate_schema as validate_schema_v19


_Q32_ONE = 1 << 32
_SHA256_ZERO = "sha256:" + ("0" * 64)
_CANDIDATE_KIND_PATCH = "PATCH"
_CANDIDATE_KIND_EXT = "KERNEL_EXT_PROPOSAL"
_RISK_RANK = {"LOW": 0, "MED": 1, "HIGH": 2, "FRONTIER_HEAVY": 3}

_DROP_PATCH_PREFLIGHT = "ARENA_DROP:PATCH_APPLY_PREFLIGHT_FAILED"
_DROP_ALLOWLIST = "ARENA_DROP:ALLOWLIST_VIOLATION"
_DROP_FORBID_LOCK = "ARENA_DROP:FORBID_LOCK_TOUCH"
_DROP_WIRING = "ARENA_DROP:WIRING_EVIDENCE_REQUIRED"
_DROP_NONTRIVIALITY = "ARENA_DROP:NONTRIVIALITY_CERT_REQUIRED"
_DROP_OVERSIZE = "ARENA_DROP:OVERSIZE_PATCH"
_DROP_INVALID_SCHEMA_EDIT = "ARENA_DROP:INVALID_SCHEMA_EDIT"
_DROP_AGENT_QUARANTINED = "ARENA_DROP:AGENT_QUARANTINED"
_DROP_FT_MODEL_UNAVAILABLE = "ARENA_DROP:FT_MODEL_UNAVAILABLE"

_SELECT_WINNER_FROM_BACKLOG = "ARENA_SELECT:WINNER_FROM_BACKLOG"
_SELECT_TIEBREAK_CANDIDATE_ID = "ARENA_SELECT:TIEBREAK_BY_CANDIDATE_ID"

_QUARANTINE_REASON_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^HOLDOUT_"),
    re.compile(r"^PHASE1_PUBLIC_ONLY_VIOLATION"),
    re.compile(r"^SANDBOX_REQUIRED_BUT_NOT_ENFORCED"),
    re.compile(r"^ALLOWLIST_VIOLATION$"),
)
_QUARANTINE_COOLDOWN_TICKS_U64 = 10_000

_DEFAULT_PATCH_TARGETS: tuple[str, ...] = (
    "campaigns/rsi_proposer_arena_v1/proposer_arena_spec_v1.json",
    "campaigns/rsi_proposer_arena_v1/proposer_arena_surrogate_policy_v1.json",
)
_DEFAULT_EXTENSION_SUITE_RUNNER = "tools/omega/omega_benchmark_suite_composite_v1.py"


def _load_json(path: Path) -> dict[str, Any]:
    payload = load_canon_dict(path)
    if not isinstance(payload, dict):
        raise RuntimeError("SCHEMA_FAIL")
    return payload


def _sha256_prefixed(data: bytes) -> str:
    import hashlib

    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _is_sha256(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    if not value.startswith("sha256:"):
        return False
    hexd = value.split(":", 1)[1]
    return bool(re.fullmatch(r"[0-9a-f]{64}", hexd))


def _canonical_relpath(path_value: Any) -> str:
    rel = str(path_value).strip().replace("\\", "/")
    if rel.startswith("./"):
        rel = rel[2:]
    return require_relpath(rel)


def _parse_patch_touched_paths(patch_bytes: bytes) -> list[str]:
    touched: list[str] = []
    seen: set[str] = set()
    for raw in patch_bytes.decode("utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line.startswith("+++ "):
            continue
        if line == "+++ /dev/null":
            continue
        if not line.startswith("+++ b/"):
            continue
        rel = line[len("+++ b/") :].split("\t", 1)[0].strip()
        if rel.startswith('"') and rel.endswith('"') and len(rel) >= 2:
            rel = rel[1:-1]
        try:
            rel = _canonical_relpath(rel)
        except Exception:
            continue
        if rel not in seen:
            seen.add(rel)
            touched.append(rel)
    return sorted(touched)


def _risk_rank(value: str) -> int:
    return int(_RISK_RANK.get(str(value).strip().upper(), 99))


def _latest(path_glob: str) -> Path | None:
    import glob

    rows = sorted(glob.glob(path_glob))
    if not rows:
        return None
    return Path(rows[-1]).resolve()


def _enforce_wallclock_budget(*, started_s: float, max_seconds: int) -> None:
    if int(max_seconds) <= 0:
        return
    if (time.monotonic() - float(started_s)) > float(max_seconds):
        raise RuntimeError("BUDGET_EXCEEDED")


def _dir_size_bytes(root: Path) -> int:
    if not root.exists() or not root.is_dir():
        return 0
    total = 0
    stack = [root]
    while stack:
        cur = stack.pop()
        for entry in cur.iterdir():
            if entry.is_symlink():
                continue
            if entry.is_dir():
                stack.append(entry)
                continue
            if entry.is_file():
                total += int(entry.stat().st_size)
    return int(total)


def _enforce_total_written_budget(*, max_bytes: int, roots: list[Path]) -> None:
    if int(max_bytes) <= 0:
        return
    written = 0
    for root in roots:
        written += _dir_size_bytes(root)
    if int(written) > int(max_bytes):
        raise RuntimeError("BUDGET_EXCEEDED")


def _load_pack(path: Path) -> dict[str, Any]:
    payload = _load_json(path)
    validate_schema_v19(payload, "rsi_proposer_arena_pack_v1")
    if int(payload.get("max_winners_u32", 0)) != 1:
        raise RuntimeError("SCHEMA_FAIL")
    budgets = payload.get("budgets")
    if not isinstance(budgets, dict):
        raise RuntimeError("SCHEMA_FAIL")
    if int(budgets.get("max_winners_u32", 0)) != 1:
        raise RuntimeError("SCHEMA_FAIL")
    return payload


def _load_structured_configs(root: Path, pack: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    arena_spec = _load_json(root / _canonical_relpath(pack.get("arena_spec_rel")))
    agent_registry = _load_json(root / _canonical_relpath(pack.get("agent_registry_rel")))
    task_distribution = _load_json(root / _canonical_relpath(pack.get("task_distribution_rel")))
    surrogate_policy = _load_json(root / _canonical_relpath(pack.get("surrogate_policy_rel")))
    validate_schema_v19(arena_spec, "proposer_arena_spec_v1")
    validate_schema_v19(agent_registry, "proposer_arena_agent_registry_v1")
    validate_schema_v19(task_distribution, "proposer_arena_task_distribution_v1")
    validate_schema_v19(surrogate_policy, "proposer_arena_surrogate_policy_v1")
    return arena_spec, agent_registry, task_distribution, surrogate_policy


def _load_ccap_patch_allowlists(root: Path) -> dict[str, Any]:
    payload = _load_json(root / "authority" / "ccap_patch_allowlists_v1.json")
    allow_prefixes = payload.get("allow_prefixes")
    forbid_prefixes = payload.get("forbid_prefixes")
    forbid_exact = payload.get("forbid_exact_paths")
    if not isinstance(allow_prefixes, list) or not isinstance(forbid_prefixes, list) or not isinstance(forbid_exact, list):
        raise RuntimeError("SCHEMA_FAIL")
    return payload


def _path_allowed_by_ccap_allowlist(path_rel: str, allowlists: dict[str, Any]) -> bool:
    rel = _canonical_relpath(path_rel)
    forbid_exact = {str(row).strip() for row in allowlists.get("forbid_exact_paths", [])}
    if rel in forbid_exact:
        return False
    for prefix in allowlists.get("forbid_prefixes", []):
        if rel.startswith(str(prefix)):
            return False
    for prefix in allowlists.get("allow_prefixes", []):
        if rel.startswith(str(prefix)):
            return True
    return False


def _load_lane_requires_wiring(daemon_state_root: Path) -> bool:
    lane_dir = daemon_state_root / "long_run" / "lane"
    final_path = lane_dir / "lane_decision_receipt_v1.json"
    payload = _load_json(final_path) if final_path.exists() else None
    if payload is None:
        latest_lane = _latest(str(lane_dir / "sha256_*.lane_decision_receipt_v1.json"))
        payload = _load_json(latest_lane) if latest_lane is not None else None
    if not isinstance(payload, dict):
        return False
    lane_name = str(payload.get("lane_name", "")).strip().upper()
    return lane_name == "FRONTIER"


def _arena_persistent_root(daemon_state_root: Path) -> Path:
    return (daemon_state_root / "proposer_arena" / "state").resolve()


def _bootstrap_arena_state(*, tick_u64: int, agent_registry: dict[str, Any], arena_spec: dict[str, Any]) -> dict[str, Any]:
    initial_bankroll_q32 = int(arena_spec.get("initial_bankroll_q32", _Q32_ONE))
    initial_cred_q32 = int(arena_spec.get("initial_credibility_q32", _Q32_ONE // 2))
    agents_raw = agent_registry.get("agents")
    if not isinstance(agents_raw, list):
        raise RuntimeError("SCHEMA_FAIL")
    agent_states: list[dict[str, Any]] = []
    for row in sorted(agents_raw, key=lambda r: str((r or {}).get("agent_id", ""))):
        if not isinstance(row, dict):
            raise RuntimeError("SCHEMA_FAIL")
        if not bool(row.get("enabled", True)):
            continue
        agent_id = str(row.get("agent_id", "")).strip()
        if not agent_id:
            raise RuntimeError("SCHEMA_FAIL")
        agent_states.append(
            {
                "agent_id": agent_id,
                "credibility_q32": int(initial_cred_q32),
                "bankroll_q32": int(initial_bankroll_q32),
                "wins_u64": 0,
                "losses_u64": 0,
                "last_submitted_tick_u64": 0,
                "last_promoted_tick_u64": 0,
                "cooldown_until_tick_u64": int(tick_u64),
                "quarantined_b": False,
                "quarantine_reason_code": None,
            }
        )
    state = {
        "schema_version": "proposer_arena_state_v1",
        "tick_u64": int(tick_u64),
        "parent_state_hash": _SHA256_ZERO,
        "agent_states": agent_states,
        "candidate_backlog": [],
    }
    validate_schema_v19(state, "proposer_arena_state_v1")
    return state


def _load_latest_arena_state(*, arena_root: Path, tick_u64: int, agent_registry: dict[str, Any], arena_spec: dict[str, Any]) -> tuple[dict[str, Any], str]:
    latest_path = arena_root / "latest.json"
    if latest_path.exists() and latest_path.is_file():
        payload = _load_json(latest_path)
        validate_schema_v19(payload, "proposer_arena_state_v1")
        return payload, canon_hash_obj(payload)
    state = _bootstrap_arena_state(
        tick_u64=tick_u64,
        agent_registry=agent_registry,
        arena_spec=arena_spec,
    )
    return state, canon_hash_obj(state)


def _load_last_official_promotion(daemon_state_root: Path) -> dict[str, Any] | None:
    path = _latest(str(daemon_state_root / "dispatch" / "*" / "promotion" / "sha256_*.omega_promotion_receipt_v1.json"))
    if path is None:
        return None
    try:
        payload = _load_json(path)
        validate_schema(payload, "omega_promotion_receipt_v1")
        return payload
    except Exception:
        return None


def _load_last_arena_run_receipt(arena_root: Path) -> dict[str, Any] | None:
    latest_run = arena_root / "latest_run_receipt.json"
    if latest_run.exists() and latest_run.is_file():
        payload = _load_json(latest_run)
        try:
            validate_schema_v19(payload, "proposer_arena_run_receipt_v1")
            return payload
        except Exception:
            return None
    return None


def _matches_quarantine_reason(reason_code: str) -> bool:
    text = str(reason_code).strip().upper()
    for pattern in _QUARANTINE_REASON_PATTERNS:
        if pattern.match(text):
            return True
    return False


def _apply_official_outcome_to_agents(
    *,
    tick_u64: int,
    agent_states: list[dict[str, Any]],
    last_run_receipt: dict[str, Any] | None,
    last_promotion_receipt: dict[str, Any] | None,
) -> None:
    if not isinstance(last_run_receipt, dict):
        return
    winner_agent = str(last_run_receipt.get("winner_agent_id", "")).strip()
    if not winner_agent:
        return
    target: dict[str, Any] | None = None
    for row in agent_states:
        if str(row.get("agent_id", "")).strip() == winner_agent:
            target = row
            break
    if target is None:
        return
    result = (last_promotion_receipt or {}).get("result")
    status = str((result or {}).get("status", "")).strip().upper()
    reason_code = str((result or {}).get("reason_code", "")).strip()
    if status == "PROMOTED":
        target["wins_u64"] = int(max(0, int(target.get("wins_u64", 0)))) + 1
        target["bankroll_q32"] = int(max(0, int(target.get("bankroll_q32", 0)))) + int(_Q32_ONE // 4)
        target["credibility_q32"] = min(_Q32_ONE, int(max(0, int(target.get("credibility_q32", 0)))) + int(_Q32_ONE // 20))
        target["last_promoted_tick_u64"] = int(max(0, int(tick_u64 - 1)))
    elif status == "REJECTED":
        target["losses_u64"] = int(max(0, int(target.get("losses_u64", 0)))) + 1
        target["bankroll_q32"] = max(0, int(target.get("bankroll_q32", 0)) - int(_Q32_ONE // 8))
        target["credibility_q32"] = max(0, int(target.get("credibility_q32", 0)) - int(_Q32_ONE // 20))

    if _matches_quarantine_reason(reason_code):
        target["quarantined_b"] = True
        target["quarantine_reason_code"] = reason_code
        target["cooldown_until_tick_u64"] = int(tick_u64) + int(_QUARANTINE_COOLDOWN_TICKS_U64)
        target["bankroll_q32"] = 0


def _agent_weights(task_distribution: dict[str, Any], agents: list[dict[str, Any]]) -> dict[str, int]:
    weights_obj = task_distribution.get("weights")
    out: dict[str, int] = {}
    if isinstance(weights_obj, dict):
        for row in agents:
            agent_id = str(row.get("agent_id", "")).strip()
            if not agent_id:
                continue
            out[agent_id] = max(1, int(weights_obj.get(agent_id, 1)))
    else:
        for row in agents:
            agent_id = str(row.get("agent_id", "")).strip()
            if agent_id:
                out[agent_id] = 1
    return out


def _bankroll_allocations(*, tick_u64: int, max_candidates_u32: int, agent_states: list[dict[str, Any]], task_distribution: dict[str, Any]) -> dict[str, int]:
    eligible = []
    for row in agent_states:
        if bool(row.get("quarantined_b", False)):
            continue
        if int(row.get("cooldown_until_tick_u64", 0)) > int(tick_u64):
            continue
        bankroll = int(max(0, int(row.get("bankroll_q32", 0))))
        if bankroll <= 0:
            continue
        eligible.append((str(row.get("agent_id", "")).strip(), bankroll))
    if not eligible:
        return {}
    total = sum(v for _, v in eligible)
    if total <= 0:
        return {}
    weights = _agent_weights(task_distribution, agent_states)
    weighted_rows: list[tuple[str, int]] = []
    for agent_id, bankroll in eligible:
        w = int(max(1, weights.get(agent_id, 1)))
        weighted_rows.append((agent_id, int(bankroll * w)))
    weighted_total = sum(v for _, v in weighted_rows)
    if weighted_total <= 0:
        return {}
    alloc: dict[str, int] = {agent_id: 0 for agent_id, _ in weighted_rows}
    remainders: list[tuple[int, str]] = []
    assigned = 0
    for agent_id, value in weighted_rows:
        scaled = int(max_candidates_u32) * int(value)
        whole = int(scaled // weighted_total)
        rem = int(scaled % weighted_total)
        alloc[agent_id] = whole
        assigned += whole
        remainders.append((rem, agent_id))
    for _ in range(max(0, int(max_candidates_u32) - assigned)):
        if not remainders:
            break
        remainders.sort(key=lambda row: (-row[0], row[1]))
        _rem, winner = remainders.pop(0)
        alloc[winner] = int(alloc.get(winner, 0)) + 1
    return {k: int(v) for k, v in alloc.items() if int(v) > 0}


def _agent_registry_by_id(agent_registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = agent_registry.get("agents")
    if not isinstance(rows, list):
        raise RuntimeError("SCHEMA_FAIL")
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        if not bool(row.get("enabled", True)):
            continue
        agent_id = str(row.get("agent_id", "")).strip()
        if not agent_id:
            continue
        out[agent_id] = dict(row)
    return out


def _patch_targets(task_distribution: dict[str, Any]) -> list[str]:
    targets_raw = task_distribution.get("patch_targets")
    targets = [str(row).strip() for row in targets_raw] if isinstance(targets_raw, list) and targets_raw else list(_DEFAULT_PATCH_TARGETS)
    targets = [require_relpath(row) for row in targets if str(row).strip()]
    if not targets:
        raise RuntimeError("SCHEMA_FAIL")
    return targets


def _candidate_kind_for_agent(*, agent_id: str, agent_def: dict[str, Any] | None) -> str:
    kind = str((agent_def or {}).get("agent_kind", "")).strip().upper()
    if kind == "KERNEL_EXT_PROPOSER":
        return _CANDIDATE_KIND_EXT
    if kind == "PATCH_PROPOSER":
        return _CANDIDATE_KIND_PATCH
    return _CANDIDATE_KIND_PATCH if "kernel" not in str(agent_id).lower() else _CANDIDATE_KIND_EXT


def _build_patch_candidate_via_sh1(
    *,
    root: Path,
    tick_u64: int,
    ordinal_u32: int,
    agent_id: str,
    task_distribution: dict[str, Any],
) -> dict[str, Any]:
    from tools.genesis_engine import ge_symbiotic_optimizer_v0_3 as sh1_mod

    targets = _patch_targets(task_distribution)
    target_rel = targets[int(ordinal_u32) % len(targets)]
    marker = f"apa_v1|sh1|{int(tick_u64)}|{agent_id}|{int(ordinal_u32)}"
    template_order = ["COMMENT_APPEND"]
    if target_rel.endswith(".json"):
        template_order = [
            "JSON_TWEAK_COOLDOWN",
            "JSON_TWEAK_BUDGET_HINT",
            "JSON_TWEAK_COOLDOWN_MINUS_1",
            "JSON_TWEAK_BUDGET_HINT_MINUS_1STEP",
            "COMMENT_APPEND",
        ]
    elif target_rel.endswith(".py"):
        template_order = ["CODE_FASTPATH_GUARD", "COMMENT_APPEND"]

    patch_bytes: bytes | None = None
    for template_id in template_order:
        try:
            if not bool(sh1_mod._template_supports_target(template_id=template_id, target_relpath=target_rel)):
                continue
            patch_bytes = sh1_mod._build_patch_bytes_for_template(
                template_id=template_id,
                target_relpath=target_rel,
                marker=marker,
                repo_root=root,
            )
            if patch_bytes:
                break
        except Exception:
            continue
    if not patch_bytes:
        raise RuntimeError("SH1_TEMPLATE_GENERATION_FAILED")

    touched = _parse_patch_touched_paths(patch_bytes)
    return {
        "agent_id": str(agent_id),
        "candidate_kind": _CANDIDATE_KIND_PATCH,
        "declared_touched_paths": (touched if touched else [target_rel]),
        "patch_bytes": bytes(patch_bytes),
        "nontriviality_cert_id": None,
        "oracle_trace_id": None,
        "base_tree_id": compute_repo_base_tree_id_tolerant(root),
    }


def _build_patch_candidate_via_coordinator_mutator(
    *,
    root: Path,
    tick_u64: int,
    ordinal_u32: int,
    agent_id: str,
) -> dict[str, Any]:
    import orchestrator.rsi_coordinator_mutator_v1 as coord_mut

    target_rel = require_relpath(str(coord_mut._LOCKED_TARGET_RELPATH))
    target_abs = (root / target_rel).resolve()
    if not target_abs.exists() or not target_abs.is_file():
        raise RuntimeError("MISSING_STATE_INPUT")
    target_text = target_abs.read_text(encoding="utf-8")
    patch_bytes = coord_mut._template_patch_for_target(
        target_relpath=target_rel,
        target_text=target_text,
        tick_u64=int(tick_u64 + ordinal_u32),
    )
    if not patch_bytes:
        raise RuntimeError("NO_PATCH")
    touched = _parse_patch_touched_paths(bytes(patch_bytes))
    return {
        "agent_id": str(agent_id),
        "candidate_kind": _CANDIDATE_KIND_PATCH,
        "declared_touched_paths": (touched if touched else [target_rel]),
        "patch_bytes": bytes(patch_bytes),
        "nontriviality_cert_id": None,
        "oracle_trace_id": None,
        "base_tree_id": compute_repo_base_tree_id_tolerant(root),
    }


def _build_patch_candidate_via_market_mutator(
    *,
    root: Path,
    tick_u64: int,
    ordinal_u32: int,
    agent_id: str,
) -> dict[str, Any]:
    import orchestrator.rsi_market_rules_mutator_v1 as market_mut

    target_rel = require_relpath(str(market_mut._LOCKED_TARGET_RELPATH))
    target_abs = (root / target_rel).resolve()
    if not target_abs.exists() or not target_abs.is_file():
        raise RuntimeError("MISSING_STATE_INPUT")
    target_text = target_abs.read_text(encoding="utf-8")
    patch_text = market_mut._template_patch_for_target(
        target_relpath=target_rel,
        target_text=target_text,
        tick_u64=int(tick_u64 + ordinal_u32),
    )
    patch_bytes = str(patch_text).encode("utf-8")
    if not patch_bytes:
        raise RuntimeError("NO_PATCH")
    touched = _parse_patch_touched_paths(patch_bytes)
    return {
        "agent_id": str(agent_id),
        "candidate_kind": _CANDIDATE_KIND_PATCH,
        "declared_touched_paths": (touched if touched else [target_rel]),
        "patch_bytes": bytes(patch_bytes),
        "nontriviality_cert_id": None,
        "oracle_trace_id": None,
        "base_tree_id": compute_repo_base_tree_id_tolerant(root),
    }


def _stable_u64_seed(payload: dict[str, Any]) -> int:
    digest = canon_hash_obj(payload).split(":", 1)[1]
    return int(digest[:16], 16)


def _build_ft_patch_prompt(*, tick_u64: int, ordinal_u32: int, agent_id: str, task_distribution: dict[str, Any]) -> str:
    targets = _patch_targets(task_distribution)
    target_rel = targets[int(ordinal_u32) % len(targets)]
    return (
        "role: PATCH_DRAFTER_V1\n"
        f"tick_u64: {int(tick_u64)}\n"
        f"agent_id: {str(agent_id)}\n"
        "constraints:\n"
        "- Output only one unified diff patch.\n"
        "- Touch only allowlisted files.\n"
        "- Avoid trivial no-op edits.\n"
        f"target_file: {target_rel}\n"
        "recent_reason_codes: []\n"
    )


def _build_patch_candidate_via_ft_patch_drafter_v1(
    *,
    root: Path,
    tick_u64: int,
    ordinal_u32: int,
    agent_id: str,
    task_distribution: dict[str, Any],
    agent_def: dict[str, Any] | None,
) -> dict[str, Any]:
    from tools.proposer_models import pointers_v1, runtime_v1

    model_role = str((agent_def or {}).get("model_role", "")).strip()
    if model_role != "PATCH_DRAFTER_V1":
        raise RuntimeError(_DROP_FT_MODEL_UNAVAILABLE)

    active_root = (root / "daemon" / "proposer_models" / "active").resolve()
    try:
        pointer = pointers_v1.load_active_pointer(active_root=active_root, role=model_role)
    except Exception:
        raise RuntimeError(_DROP_FT_MODEL_UNAVAILABLE)
    if not isinstance(pointer, dict):
        raise RuntimeError(_DROP_FT_MODEL_UNAVAILABLE)

    active_bundle_id = str(pointer.get("active_bundle_id", "")).strip()
    if not _is_sha256(active_bundle_id):
        raise RuntimeError(_DROP_FT_MODEL_UNAVAILABLE)

    max_new_tokens = int(max(1, int((agent_def or {}).get("max_new_tokens_u32", 1024))))
    seed_u64 = _stable_u64_seed(
        {
            "schema_version": "apa_ft_patch_seed_v1",
            "tick_u64": int(tick_u64),
            "ordinal_u32": int(ordinal_u32),
            "agent_id": str(agent_id),
            "bundle_id": active_bundle_id,
        }
    )
    prompt_text = _build_ft_patch_prompt(
        tick_u64=tick_u64,
        ordinal_u32=ordinal_u32,
        agent_id=agent_id,
        task_distribution=task_distribution,
    )

    try:
        patch_text = runtime_v1.generate_patch_deterministic(
            role=model_role,
            prompt_text=prompt_text,
            model_bundle_id=active_bundle_id,
            seed_u64=seed_u64,
            max_new_tokens_u32=max_new_tokens,
        )
    except Exception:
        raise RuntimeError(_DROP_FT_MODEL_UNAVAILABLE)

    patch_bytes = str(patch_text).encode("utf-8")
    touched = _parse_patch_touched_paths(patch_bytes)
    targets = _patch_targets(task_distribution)
    fallback_target = targets[int(ordinal_u32) % len(targets)]
    return {
        "agent_id": str(agent_id),
        "candidate_kind": _CANDIDATE_KIND_PATCH,
        "declared_touched_paths": (touched if touched else [fallback_target]),
        "patch_bytes": bytes(patch_bytes),
        "nontriviality_cert_id": None,
        "oracle_trace_id": None,
        "base_tree_id": compute_repo_base_tree_id_tolerant(root),
    }


def _generate_candidate_for_agent(
    *,
    root: Path,
    tick_u64: int,
    ordinal_u32: int,
    agent_id: str,
    task_distribution: dict[str, Any],
    pins: dict[str, Any],
    agent_def: dict[str, Any] | None,
) -> dict[str, Any]:
    kind = _candidate_kind_for_agent(agent_id=agent_id, agent_def=agent_def)
    if kind == _CANDIDATE_KIND_EXT:
        return _build_extension_candidate(
            tick_u64=tick_u64,
            ordinal_u32=ordinal_u32,
            agent_id=agent_id,
            pins=pins,
        )

    entry_module = str((agent_def or {}).get("entry_module", "")).strip()
    agent_method = str((agent_def or {}).get("agent_method", "")).strip()
    model_role = str((agent_def or {}).get("model_role", "")).strip()
    if agent_method == "ft_patch_drafter_v1" or model_role == "PATCH_DRAFTER_V1":
        return _build_patch_candidate_via_ft_patch_drafter_v1(
            root=root,
            tick_u64=tick_u64,
            ordinal_u32=ordinal_u32,
            agent_id=agent_id,
            task_distribution=task_distribution,
            agent_def=agent_def,
        )
    if agent_id == "sh1_v0_3" or entry_module == "tools.genesis_engine.ge_symbiotic_optimizer_v0_3":
        return _build_patch_candidate_via_sh1(
            root=root,
            tick_u64=tick_u64,
            ordinal_u32=ordinal_u32,
            agent_id=agent_id,
            task_distribution=task_distribution,
        )
    if agent_id == "coordinator_mutator_v1" or entry_module == "orchestrator.rsi_coordinator_mutator_v1":
        return _build_patch_candidate_via_coordinator_mutator(
            root=root,
            tick_u64=tick_u64,
            ordinal_u32=ordinal_u32,
            agent_id=agent_id,
        )
    if agent_id == "market_rules_mutator_v1" or entry_module == "orchestrator.rsi_market_rules_mutator_v1":
        return _build_patch_candidate_via_market_mutator(
            root=root,
            tick_u64=tick_u64,
            ordinal_u32=ordinal_u32,
            agent_id=agent_id,
        )
    return _build_patch_candidate(
        root=root,
        tick_u64=tick_u64,
        ordinal_u32=ordinal_u32,
        agent_id=agent_id,
        task_distribution=task_distribution,
    )


def _build_patch_candidate(
    *,
    root: Path,
    tick_u64: int,
    ordinal_u32: int,
    agent_id: str,
    task_distribution: dict[str, Any],
) -> dict[str, Any]:
    targets_raw = task_distribution.get("patch_targets")
    targets = [str(row).strip() for row in targets_raw] if isinstance(targets_raw, list) and targets_raw else list(_DEFAULT_PATCH_TARGETS)
    targets = [require_relpath(row) for row in targets if str(row).strip()]
    if not targets:
        raise RuntimeError("SCHEMA_FAIL")
    target_rel = targets[int(ordinal_u32) % len(targets)]
    target_abs = (root / target_rel).resolve()
    if not target_abs.exists() or not target_abs.is_file():
        raise RuntimeError("MISSING_STATE_INPUT")
    before = target_abs.read_text(encoding="utf-8")
    after = before
    if target_rel.endswith(".json"):
        data = json.loads(before)
        if not isinstance(data, dict):
            raise RuntimeError("SCHEMA_FAIL")
        if "candidate_ttl_ticks_u64" in data:
            delta = int((int(tick_u64) + int(ordinal_u32)) % 3) - 1
            data["candidate_ttl_ticks_u64"] = max(1, int(data.get("candidate_ttl_ticks_u64", 1)) + int(delta))
        else:
            data["arena_touch_tick_u64"] = int(tick_u64)
            data["arena_touch_agent_id"] = str(agent_id)
        after = json.dumps(data, sort_keys=True, indent=2, ensure_ascii=True) + "\n"
    else:
        marker = f"# apa_v1 tick={int(tick_u64)} agent={agent_id} i={int(ordinal_u32)}"
        if marker in before:
            marker = marker + "_dup"
        if before.endswith("\n"):
            after = before + marker + "\n"
        else:
            after = before + "\n" + marker + "\n"
    patch_bytes = build_unified_patch_bytes(relpath=target_rel, before_text=before, after_text=after)
    if not patch_bytes:
        raise RuntimeError("NO_PATCH")
    return {
        "agent_id": str(agent_id),
        "candidate_kind": _CANDIDATE_KIND_PATCH,
        "declared_touched_paths": [target_rel],
        "patch_bytes": bytes(patch_bytes),
        "nontriviality_cert_id": None,
        "oracle_trace_id": None,
        "base_tree_id": compute_repo_base_tree_id_tolerant(root),
    }


def _with_declared_id(payload: dict[str, Any], id_field: str) -> dict[str, Any]:
    out = dict(payload)
    out.pop(id_field, None)
    out[id_field] = canon_hash_obj(out)
    return out


def _declared_id_matches(payload: dict[str, Any], id_field: str) -> bool:
    declared = str(payload.get(id_field, "")).strip()
    if not _is_sha256(declared):
        return False
    material = dict(payload)
    material.pop(id_field, None)
    return str(canon_hash_obj(material)) == declared


def _build_extension_candidate(
    *,
    tick_u64: int,
    ordinal_u32: int,
    agent_id: str,
    pins: dict[str, Any],
) -> dict[str, Any]:
    suffix = canon_hash_obj(
        {
            "schema_version": "apa_ext_seed_v1",
            "tick_u64": int(tick_u64),
            "ordinal_u32": int(ordinal_u32),
            "agent_id": str(agent_id),
        }
    )
    short = suffix.split(":", 1)[1][:16]
    suite_manifest = _with_declared_id(
        {
            "schema_version": "benchmark_suite_manifest_v1",
            "suite_name": f"apa_public_suite_{short}",
            "suite_runner_relpath": _DEFAULT_EXTENSION_SUITE_RUNNER,
            "visibility": "PUBLIC",
            "labels": ["apa", "public"],
            "metrics": {
                "q32_metric_ids": ["accuracy_q32", "coverage_q32"],
                "public_only_b": True,
            },
        },
        "suite_id",
    )
    suite_manifest_id = str(suite_manifest["suite_id"])
    suite_set = _with_declared_id(
        {
            "schema_version": "benchmark_suite_set_v1",
            "suite_set_kind": "EXTENSION",
            "anchor_ek_id": str(pins.get("active_ek_id", _SHA256_ZERO)),
            "suites": [
                {
                    "suite_id": suite_manifest_id,
                    "suite_manifest_id": suite_manifest_id,
                    "suite_manifest_relpath": "benchmark_suite_manifest_v1.json",
                    "ordinal_u64": 0,
                }
            ],
        },
        "suite_set_id",
    )
    suite_set_id = str(suite_set["suite_set_id"])
    ext_spec = _with_declared_id(
        {
            "schema_version": "kernel_extension_spec_v1",
            "anchor_ek_id": str(pins.get("active_ek_id", _SHA256_ZERO)),
            "extension_name": f"apa_extension_{short}",
            "suite_set_id": suite_set_id,
            "suite_set_relpath": "benchmark_suite_set_v1.json",
            "additive_only_b": True,
        },
        "extension_spec_id",
    )
    return {
        "agent_id": str(agent_id),
        "candidate_kind": _CANDIDATE_KIND_EXT,
        "declared_touched_paths": [],
        "nontriviality_cert_id": None,
        "oracle_trace_id": None,
        "base_tree_id": str(pins.get("active_ek_id", _SHA256_ZERO)),
        "extension_spec": ext_spec,
        "benchmark_suite_manifest": suite_manifest,
        "benchmark_suite_set": suite_set,
    }


def _candidate_payload_hashes(candidate: dict[str, Any]) -> dict[str, str]:
    kind = str(candidate.get("candidate_kind", "")).strip()
    if kind == _CANDIDATE_KIND_PATCH:
        patch_bytes = bytes(candidate.get("patch_bytes", b""))
        return {"patch_blob_id": _sha256_prefixed(patch_bytes)}
    if kind == _CANDIDATE_KIND_EXT:
        ext_spec = dict(candidate.get("extension_spec") or {})
        suite_manifest = dict(candidate.get("benchmark_suite_manifest") or {})
        suite_set = dict(candidate.get("benchmark_suite_set") or {})
        if not _declared_id_matches(ext_spec, "extension_spec_id"):
            raise RuntimeError("SCHEMA_FAIL")
        if not _declared_id_matches(suite_manifest, "suite_id"):
            raise RuntimeError("SCHEMA_FAIL")
        if not _declared_id_matches(suite_set, "suite_set_id"):
            raise RuntimeError("SCHEMA_FAIL")
        return {
            "extension_spec_id": str(ext_spec.get("extension_spec_id", "")),
            "suite_manifest_id": str(suite_manifest.get("suite_id", "")),
            "suite_set_id": str(suite_set.get("suite_set_id", "")),
        }
    raise RuntimeError("SCHEMA_FAIL")


def _candidate_id_from_material(candidate: dict[str, Any], *, derived_touched_paths: list[str], payload_hashes: dict[str, str]) -> str:
    material = {
        "schema_version": "arena_candidate_material_v1",
        "agent_id": str(candidate.get("agent_id", "")).strip(),
        "candidate_kind": str(candidate.get("candidate_kind", "")).strip(),
        "declared_touched_paths": sorted(str(row) for row in list(candidate.get("declared_touched_paths") or [])),
        "derived_touched_paths": sorted(str(row) for row in list(derived_touched_paths or [])),
        "base_tree_id": str(candidate.get("base_tree_id", "")).strip(),
        "nontriviality_cert_id": candidate.get("nontriviality_cert_id"),
        "oracle_trace_id": candidate.get("oracle_trace_id"),
        "payload_hashes": dict(payload_hashes),
    }
    return canon_hash_obj(material)


def _admission_allowlist_and_preflight(
    *,
    root: Path,
    candidate: dict[str, Any],
    allowlists: dict[str, Any],
    arena_spec: dict[str, Any],
    lane_requires_wiring_b: bool,
    max_patch_bytes_u32: int,
) -> tuple[bool, str, list[str], dict[str, str]]:
    kind = str(candidate.get("candidate_kind", "")).strip()
    payload_hashes = _candidate_payload_hashes(candidate)
    if kind == _CANDIDATE_KIND_EXT:
        return True, "PASS", [], payload_hashes

    patch_bytes = bytes(candidate.get("patch_bytes", b""))
    if len(patch_bytes) > int(max_patch_bytes_u32):
        return False, _DROP_OVERSIZE, _parse_patch_touched_paths(patch_bytes), payload_hashes

    derived_touched = _parse_patch_touched_paths(patch_bytes)
    if not derived_touched:
        return False, _DROP_PATCH_PREFLIGHT, derived_touched, payload_hashes

    forbid_lock_prefixes = arena_spec.get("forbid_lock_prefixes")
    if isinstance(forbid_lock_prefixes, list):
        for rel in derived_touched:
            if any(rel.startswith(str(prefix)) for prefix in forbid_lock_prefixes):
                return False, _DROP_FORBID_LOCK, derived_touched, payload_hashes

    for rel in derived_touched:
        if not _path_allowed_by_ccap_allowlist(rel, allowlists):
            return False, _DROP_ALLOWLIST, derived_touched, payload_hashes

    if lane_requires_wiring_b and candidate.get("oracle_trace_id") is None:
        return False, _DROP_WIRING, derived_touched, payload_hashes
    if lane_requires_wiring_b and candidate.get("nontriviality_cert_id") is None:
        return False, _DROP_NONTRIVIALITY, derived_touched, payload_hashes

    with tempfile.TemporaryDirectory(prefix="apa_preflight_") as tmp:
        tmp_root = Path(tmp).resolve()
        workspace = tmp_root / "workspace"
        materialize_repo_snapshot(root, workspace)
        try:
            apply_patch_bytes(workspace_root=workspace, patch_bytes=patch_bytes)
        except Exception:
            return False, _DROP_PATCH_PREFLIGHT, derived_touched, payload_hashes
    return True, "PASS", derived_touched, payload_hashes


def _write_arena_candidate_precheck(
    *,
    out_dir: Path,
    candidate_id: str,
    agent_id: str,
    admitted_b: bool,
    decision_code: str,
    reason_codes: list[str],
) -> tuple[dict[str, Any], str]:
    payload = {
        "schema_version": "arena_candidate_precheck_receipt_v1",
        "receipt_id": _SHA256_ZERO,
        "candidate_id": str(candidate_id),
        "agent_id": str(agent_id),
        "admitted_b": bool(admitted_b),
        "decision_code": str(decision_code),
        "reason_codes": sorted({str(row).strip() for row in reason_codes if str(row).strip()}),
    }
    validate_schema_v19(payload, "arena_candidate_precheck_receipt_v1")
    _, receipt, digest = write_hashed_json(out_dir, "arena_candidate_precheck_receipt_v1.json", payload, id_field="receipt_id")
    validate_schema_v19(receipt, "arena_candidate_precheck_receipt_v1")
    return receipt, digest


def _build_arena_candidate_payload(
    *,
    candidate_id: str,
    candidate: dict[str, Any],
    derived_touched_paths: list[str],
    precheck_receipt_id: str,
    surrogate_eval_receipt_id: str | None,
) -> dict[str, Any]:
    payload = {
        "schema_version": "arena_candidate_v1",
        "candidate_id": str(candidate_id),
        "agent_id": str(candidate.get("agent_id", "")).strip(),
        "candidate_kind": str(candidate.get("candidate_kind", "")).strip(),
        "declared_touched_paths": sorted(str(row) for row in list(candidate.get("declared_touched_paths") or [])),
        "derived_touched_paths": sorted(str(row) for row in list(derived_touched_paths or [])),
        "base_tree_id": str(candidate.get("base_tree_id", "")).strip(),
        "nontriviality_cert_id": candidate.get("nontriviality_cert_id"),
        "candidate_precheck_receipt_id": str(precheck_receipt_id),
        "oracle_trace_id": candidate.get("oracle_trace_id"),
        "surrogate_eval_receipt_id": surrogate_eval_receipt_id,
    }
    validate_schema_v19(payload, "arena_candidate_v1")
    return payload


def _run_cmd(cmd: list[str], *, timeout_s: int) -> int:
    run = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=max(1, int(timeout_s)))
    return int(run.returncode)


def _surrogate_eval_candidate(
    *,
    root: Path,
    candidate_payload: dict[str, Any],
    surrogate_policy: dict[str, Any],
    per_candidate_timeout_s: int,
) -> tuple[dict[str, Any], str, int, int, str, list[str]]:
    checks: list[dict[str, Any]] = []
    reason_codes: list[str] = []
    fail_count = 0

    touched = [str(row) for row in list(candidate_payload.get("derived_touched_paths") or [])]
    if bool(surrogate_policy.get("enable_py_compile_b", True)):
        for rel in touched:
            if not rel.endswith(".py"):
                continue
            rc = _run_cmd(["python3", "-m", "py_compile", str((root / rel).resolve())], timeout_s=per_candidate_timeout_s)
            verdict = "PASS" if rc == 0 else "FAIL"
            checks.append({"kind": f"PY_COMPILE:{rel}", "verdict": verdict})
            if verdict != "PASS":
                fail_count += 1
                reason_codes.append("SURROGATE:PY_COMPILE_FAIL")

    if bool(surrogate_policy.get("enable_json_schema_check_b", True)):
        for rel in touched:
            if not rel.endswith(".json"):
                continue
            verdict = "PASS"
            try:
                parsed = json.loads((root / rel).read_text(encoding="utf-8"))
                if not isinstance(parsed, dict):
                    raise RuntimeError("JSON_NOT_OBJECT")
                schema_version = str(parsed.get("schema_version", "")).strip()
                if not schema_version:
                    raise RuntimeError("SCHEMA_VERSION_MISSING")
                validated = False
                for validator in (validate_schema_v19, validate_schema):
                    try:
                        validator(parsed, schema_version)
                        validated = True
                        break
                    except Exception:
                        continue
                if not validated:
                    raise RuntimeError("SCHEMA_INVALID")
            except Exception:
                verdict = "FAIL"
            checks.append({"kind": f"JSON_SCHEMA:{rel}", "verdict": verdict})
            if verdict != "PASS":
                fail_count += 1
                reason_codes.append("SURROGATE:JSON_SCHEMA_FAIL")

    fast_cmd = str(surrogate_policy.get("anchor_public_fast_cmd", "")).strip()
    fast_timeout = int(max(1, int(surrogate_policy.get("anchor_public_fast_timeout_s", per_candidate_timeout_s))))
    if fast_cmd:
        rc = subprocess.run(
            fast_cmd,
            cwd=str(root),
            shell=True,
            capture_output=True,
            text=True,
            check=False,
            timeout=max(1, min(fast_timeout, per_candidate_timeout_s)),
        ).returncode
        verdict = "PASS" if int(rc) == 0 else "FAIL"
        checks.append({"kind": "ANCHOR_PUBLIC_FAST", "verdict": verdict})
        if verdict != "PASS":
            fail_count += 1
            reason_codes.append("SURROGATE:ANCHOR_FAST_FAIL")

    kind = str(candidate_payload.get("candidate_kind", "")).strip().upper()
    defaults = surrogate_policy.get("risk_class_defaults")
    risk_class = "MED"
    if isinstance(defaults, dict):
        risk_class = str(defaults.get(kind, "MED")).strip().upper() or "MED"
    if risk_class not in _RISK_RANK:
        risk_class = "MED"

    score_q32 = max(0, int(_Q32_ONE - fail_count * (_Q32_ONE // 4)))
    cost_q32 = int(max(1, len(checks)) * (_Q32_ONE // 16))
    if fail_count == 0:
        reason_codes.append("SURROGATE:OK")

    receipt_payload = {
        "schema_version": "arena_surrogate_eval_receipt_v1",
        "receipt_id": _SHA256_ZERO,
        "candidate_id": str(candidate_payload.get("candidate_id", "")),
        "surrogate_checks": checks,
        "surrogate_score_q32": int(score_q32),
        "surrogate_cost_q32": int(cost_q32),
        "risk_class": str(risk_class),
        "reason_codes": sorted({str(row).strip() for row in reason_codes if str(row).strip()}),
    }
    validate_schema_v19(receipt_payload, "arena_surrogate_eval_receipt_v1")
    return receipt_payload, str(receipt_payload["candidate_id"]), score_q32, cost_q32, risk_class, receipt_payload["reason_codes"]  # type: ignore[index]


def _trim_backlog(rows: list[dict[str, Any]], *, backlog_max_u32: int) -> list[dict[str, Any]]:
    ordered = sorted(
        rows,
        key=lambda row: (
            int(row.get("surrogate_score_q32", 0)),
            -int(row.get("surrogate_cost_q32", 0)),
            str(row.get("candidate_id", "")),
        ),
    )
    if len(ordered) <= int(backlog_max_u32):
        return ordered
    return ordered[len(ordered) - int(backlog_max_u32) :]


def _selection_sort_key(row: dict[str, Any]) -> tuple[int, int, int, str]:
    return (
        -int(row.get("surrogate_score_q32", 0)),
        _risk_rank(str(row.get("risk_class", "")).strip().upper()),
        int(row.get("surrogate_cost_q32", 0)),
        str(row.get("candidate_id", "")),
    )


def _deterministic_rank_and_select(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    ranked = sorted(rows, key=_selection_sort_key)
    return ranked, (ranked[0] if ranked else None)


def _load_active_ek_by_hash(root: Path, ek_id: str) -> dict[str, Any]:
    for path in sorted((root / "authority" / "evaluation_kernels").glob("*.json"), key=lambda row: row.as_posix()):
        payload = _load_json(path)
        if str(payload.get("schema_version", "")).strip() != "evaluation_kernel_v1":
            continue
        if canon_hash_obj(payload) == str(ek_id):
            validate_schema(payload, "evaluation_kernel_v1")
            return payload
    raise RuntimeError("MISSING_STATE_INPUT")


def _load_first_build_recipe_id(root: Path) -> str:
    payload = _load_json(root / "authority" / "build_recipes" / "build_recipes_v1.json")
    recipes = payload.get("recipes")
    if str(payload.get("schema_version", "")).strip() != "build_recipes_v1" or not isinstance(recipes, list) or not recipes:
        raise RuntimeError("SCHEMA_FAIL")
    ids = sorted(str(row.get("recipe_id", "")).strip() for row in recipes if isinstance(row, dict))
    ids = [row for row in ids if _is_sha256(row)]
    if not ids:
        raise RuntimeError("SCHEMA_FAIL")
    return ids[0]


def _emit_patch_winner_payload(
    *,
    root: Path,
    state_root: Path,
    promotion_dir: Path,
    winner_candidate_id: str,
    patch_bytes: bytes,
    touched_paths: list[str],
    pins: dict[str, Any],
) -> tuple[str, str]:
    patch_blob_id = _sha256_prefixed(patch_bytes)
    patch_hex = patch_blob_id.split(":", 1)[1]
    patch_rel = Path("patches") / f"sha256_{patch_hex}.patch"
    patch_abs = (promotion_dir / patch_rel).resolve()
    patch_abs.parent.mkdir(parents=True, exist_ok=True)
    patch_abs.write_bytes(patch_bytes)

    ek_id = str(pins.get("active_ek_id", _SHA256_ZERO))
    op_pool_ids = pins.get("active_op_pool_ids")
    dsbx_profile_ids = pins.get("active_dsbx_profile_ids")
    if not isinstance(op_pool_ids, list) or not op_pool_ids:
        raise RuntimeError("SCHEMA_FAIL")
    if not isinstance(dsbx_profile_ids, list) or not dsbx_profile_ids:
        raise RuntimeError("SCHEMA_FAIL")
    op_pool_id = str(op_pool_ids[0])
    dsbx_profile_id = str(dsbx_profile_ids[0])
    if not _is_sha256(op_pool_id) or not _is_sha256(dsbx_profile_id) or not _is_sha256(ek_id):
        raise RuntimeError("SCHEMA_FAIL")

    ek_payload = _load_active_ek_by_hash(root, ek_id)
    build_recipe_id = _load_first_build_recipe_id(root)
    ccap_payload = {
        "meta": {
            "ccap_version": 1,
            "base_tree_id": compute_repo_base_tree_id_tolerant(root),
            "auth_hash": auth_hash(pins),
            "dsbx_profile_id": dsbx_profile_id,
            "env_contract_id": str(pins.get("env_contract_id", _SHA256_ZERO)),
            "toolchain_root_id": str(pins.get("toolchain_root_id", _SHA256_ZERO)),
            "ek_id": ek_id,
            "op_pool_id": op_pool_id,
            "canon_version_ids": dict(pins.get("canon_version_ids") or {}),
        },
        "payload": {
            "kind": "PATCH",
            "patch_blob_id": patch_blob_id,
        },
        "build": {
            "build_recipe_id": build_recipe_id,
            "build_targets": [],
            "artifact_bindings": {},
        },
        "eval": {
            "stages": list(ek_payload.get("stages") or []),
            "final_suite_id": str(pins.get("anchor_suite_set_id", _SHA256_ZERO)),
        },
        "budgets": {
            "cpu_ms_max": 60_000,
            "wall_ms_max": 60_000,
            "mem_mb_max": 4096,
            "disk_mb_max": 1024,
            "fds_max": 256,
            "procs_max": 32,
            "threads_max": 64,
            "net": "forbidden",
        },
    }
    validate_schema(ccap_payload, "ccap_v1")
    ccap_id = ccap_payload_id(ccap_payload)
    ccap_rel = Path("ccap") / f"sha256_{ccap_id.split(':', 1)[1]}.ccap_v1.json"
    ccap_abs = (promotion_dir / ccap_rel).resolve()
    ccap_abs.parent.mkdir(parents=True, exist_ok=True)
    write_canon_json(ccap_abs, ccap_payload)

    bundle_payload = {
        "schema_version": "omega_promotion_bundle_ccap_v1",
        "ccap_id": ccap_id,
        "ccap_relpath": ccap_rel.as_posix(),
        "patch_relpath": patch_rel.as_posix(),
        "touched_paths": sorted({str(row) for row in touched_paths if str(row).strip()}),
        "activation_key": str(winner_candidate_id),
    }
    validate_schema(bundle_payload, "omega_promotion_bundle_ccap_v1")
    _, _bundle_obj, bundle_hash = write_hashed_json(
        promotion_dir,
        "omega_promotion_bundle_ccap_v1.json",
        bundle_payload,
    )
    return ccap_id, bundle_hash


def _emit_extension_winner_payload(*, promotion_dir: Path, extension_payload: dict[str, Any]) -> str:
    ext_spec = dict(extension_payload.get("extension_spec") or {})
    suite_manifest = dict(extension_payload.get("benchmark_suite_manifest") or {})
    suite_set = dict(extension_payload.get("benchmark_suite_set") or {})
    validate_schema_v19(ext_spec, "kernel_extension_spec_v1")
    validate_schema_v19(suite_manifest, "benchmark_suite_manifest_v1")
    validate_schema_v19(suite_set, "benchmark_suite_set_v1")

    if not _declared_id_matches(ext_spec, "extension_spec_id"):
        raise RuntimeError("NONDETERMINISTIC")
    if not _declared_id_matches(suite_manifest, "suite_id"):
        raise RuntimeError("NONDETERMINISTIC")
    if not _declared_id_matches(suite_set, "suite_set_id"):
        raise RuntimeError("NONDETERMINISTIC")
    ext_spec_id = str(ext_spec.get("extension_spec_id", "")).strip()

    write_canon_json(promotion_dir / "kernel_extension_spec_v1.json", ext_spec)
    write_canon_json(promotion_dir / "benchmark_suite_manifest_v1.json", suite_manifest)
    write_canon_json(promotion_dir / "benchmark_suite_set_v1.json", suite_set)
    write_hashed_json(promotion_dir, "kernel_extension_spec_v1.json", ext_spec)
    write_hashed_json(promotion_dir, "benchmark_suite_manifest_v1.json", suite_manifest)
    write_hashed_json(promotion_dir, "benchmark_suite_set_v1.json", suite_set)
    return ext_spec_id


def _store_candidate_payload(*, arena_root: Path, candidate_id: str, candidate: dict[str, Any]) -> None:
    payload_root = (arena_root / "payloads" / candidate_id.split(":", 1)[1]).resolve()
    payload_root.mkdir(parents=True, exist_ok=True)
    kind = str(candidate.get("candidate_kind", "")).strip()
    if kind == _CANDIDATE_KIND_PATCH:
        patch_bytes = bytes(candidate.get("patch_bytes", b""))
        (payload_root / "candidate.patch").write_bytes(patch_bytes)
    elif kind == _CANDIDATE_KIND_EXT:
        write_canon_json(payload_root / "kernel_extension_spec_v1.json", dict(candidate.get("extension_spec") or {}))
        write_canon_json(payload_root / "benchmark_suite_manifest_v1.json", dict(candidate.get("benchmark_suite_manifest") or {}))
        write_canon_json(payload_root / "benchmark_suite_set_v1.json", dict(candidate.get("benchmark_suite_set") or {}))
    manifest = {
        "schema_version": "arena_candidate_payload_manifest_v1",
        "candidate_id": str(candidate_id),
        "candidate_kind": kind,
    }
    write_canon_json(payload_root / "payload_manifest_v1.json", manifest)


def _load_candidate_payload(*, arena_root: Path, candidate_id: str) -> dict[str, Any] | None:
    payload_root = (arena_root / "payloads" / candidate_id.split(":", 1)[1]).resolve()
    manifest_path = payload_root / "payload_manifest_v1.json"
    if not manifest_path.exists() or not manifest_path.is_file():
        return None
    manifest = _load_json(manifest_path)
    kind = str(manifest.get("candidate_kind", "")).strip()
    if kind == _CANDIDATE_KIND_PATCH:
        patch_path = payload_root / "candidate.patch"
        if not patch_path.exists() or not patch_path.is_file():
            return None
        return {
            "candidate_kind": _CANDIDATE_KIND_PATCH,
            "patch_bytes": patch_path.read_bytes(),
        }
    if kind == _CANDIDATE_KIND_EXT:
        ext_path = payload_root / "kernel_extension_spec_v1.json"
        manifest_path2 = payload_root / "benchmark_suite_manifest_v1.json"
        set_path = payload_root / "benchmark_suite_set_v1.json"
        if not (ext_path.exists() and manifest_path2.exists() and set_path.exists()):
            return None
        return {
            "candidate_kind": _CANDIDATE_KIND_EXT,
            "extension_spec": _load_json(ext_path),
            "benchmark_suite_manifest": _load_json(manifest_path2),
            "benchmark_suite_set": _load_json(set_path),
        }
    return None


def run(*, campaign_pack: Path, out_dir: Path) -> None:
    root = repo_root().resolve()
    pack = _load_pack(campaign_pack.resolve())
    arena_spec, agent_registry, task_distribution, surrogate_policy = _load_structured_configs(root, pack)
    allowlists = _load_ccap_patch_allowlists(root)
    pins = load_authority_pins(root)

    tick_u64 = int(max(0, int(os.environ.get("OMEGA_TICK_U64", "0") or "0")))
    daemon_state_raw = str(os.environ.get("OMEGA_DAEMON_STATE_ROOT", "")).strip()
    if not daemon_state_raw:
        raise RuntimeError("MISSING_STATE_INPUT")
    daemon_state_root = Path(daemon_state_raw).resolve()

    state_root = (out_dir.resolve() / "daemon" / "rsi_proposer_arena_v1" / "state").resolve()
    precheck_dir = state_root / "precheck"
    candidate_dir = state_root / "candidates"
    surrogate_dir = state_root / "surrogate"
    arena_dir = state_root / "arena"
    promotion_dir = state_root / "promotion"
    for path in [precheck_dir, candidate_dir, surrogate_dir, arena_dir, promotion_dir]:
        path.mkdir(parents=True, exist_ok=True)

    arena_root = _arena_persistent_root(daemon_state_root)
    arena_root.mkdir(parents=True, exist_ok=True)
    state_in, state_in_hash = _load_latest_arena_state(
        arena_root=arena_root,
        tick_u64=tick_u64,
        agent_registry=agent_registry,
        arena_spec=arena_spec,
    )
    agent_defs_by_id = _agent_registry_by_id(agent_registry)
    agent_states = [dict(row) for row in list(state_in.get("agent_states") or []) if isinstance(row, dict)]

    last_promotion = _load_last_official_promotion(daemon_state_root)
    last_run_receipt = _load_last_arena_run_receipt(arena_root)
    _apply_official_outcome_to_agents(
        tick_u64=tick_u64,
        agent_states=agent_states,
        last_run_receipt=last_run_receipt,
        last_promotion_receipt=last_promotion,
    )

    max_candidates_u32 = int(pack.get("max_candidates_u32", 16))
    budgets = dict(pack.get("budgets") or {})
    max_patch_bytes_u32 = int(budgets.get("max_patch_bytes_u32", 200_000))
    max_admitted_u32 = int(budgets.get("max_admitted_u32", 8))
    backlog_max_u32 = int(budgets.get("backlog_max_u32", 128))
    arena_total_wallclock_s = int(budgets.get("arena_total_wallclock_s", 120))
    per_agent_wallclock_s = int(budgets.get("per_agent_wallclock_s", 20))
    per_candidate_surrogate_wallclock_s = int(budgets.get("per_candidate_surrogate_wallclock_s", 8))
    max_total_written_bytes_u64 = int(budgets.get("max_total_written_bytes_u64", 50_000_000))
    candidate_ttl_u64 = int(max(1, int(arena_spec.get("candidate_ttl_ticks_u64", 32))))
    lane_requires_wiring_b = _load_lane_requires_wiring(daemon_state_root)
    arena_started_s = time.monotonic()

    allocations = _bankroll_allocations(
        tick_u64=tick_u64,
        max_candidates_u32=max_candidates_u32,
        agent_states=agent_states,
        task_distribution=task_distribution,
    )

    generated: list[dict[str, Any]] = []
    generated_count_u64 = 0
    for row in sorted(agent_states, key=lambda x: str(x.get("agent_id", ""))):
        _enforce_wallclock_budget(started_s=arena_started_s, max_seconds=arena_total_wallclock_s)
        agent_id = str(row.get("agent_id", "")).strip()
        agent_def = dict(agent_defs_by_id.get(agent_id) or {})
        quota = int(max(0, allocations.get(agent_id, 0)))
        if quota <= 0:
            continue
        agent_started_s = time.monotonic()
        for idx in range(quota):
            _enforce_wallclock_budget(started_s=arena_started_s, max_seconds=arena_total_wallclock_s)
            _enforce_wallclock_budget(started_s=agent_started_s, max_seconds=per_agent_wallclock_s)
            generated_count_u64 += 1
            kind = _candidate_kind_for_agent(agent_id=agent_id, agent_def=agent_def)
            try:
                candidate = _generate_candidate_for_agent(
                    root=root,
                    tick_u64=tick_u64,
                    ordinal_u32=int(idx),
                    agent_id=agent_id,
                    task_distribution=task_distribution,
                    pins=pins,
                    agent_def=agent_def,
                )
                generated.append(candidate)
            except Exception as exc:
                reason_code = str(exc).strip()
                if not reason_code.startswith("ARENA_DROP:"):
                    reason_code = _DROP_INVALID_SCHEMA_EDIT
                generated.append(
                    {
                        "agent_id": agent_id,
                        "candidate_kind": kind,
                        "declared_touched_paths": [],
                        "base_tree_id": _SHA256_ZERO,
                        "nontriviality_cert_id": None,
                        "oracle_trace_id": None,
                        "generation_error_b": True,
                        "generation_error_code": reason_code,
                    }
                )
    if not generated:
        fallback_agent_id = "kernel_ext_mutator_v1" if "kernel_ext_mutator_v1" in agent_defs_by_id else "sh1_v0_3"
        fallback_agent_def = dict(agent_defs_by_id.get(fallback_agent_id) or {})
        generated.append(
            _generate_candidate_for_agent(
                root=root,
                tick_u64=tick_u64,
                ordinal_u32=0,
                agent_id=fallback_agent_id,
                task_distribution=task_distribution,
                pins=pins,
                agent_def=fallback_agent_def,
            )
        )
        generated_count_u64 = 1

    drop_hist: dict[str, int] = {}
    admitted_candidates: list[dict[str, Any]] = []
    metadata_by_candidate_id: dict[str, dict[str, Any]] = {}
    raw_by_candidate_id: dict[str, dict[str, Any]] = {}

    for candidate in generated:
        _enforce_wallclock_budget(started_s=arena_started_s, max_seconds=arena_total_wallclock_s)
        agent_id = str(candidate.get("agent_id", "")).strip()
        quarantined_b = False
        for row in agent_states:
            if str(row.get("agent_id", "")).strip() == agent_id:
                quarantined_b = bool(row.get("quarantined_b", False))
                break

        decision_code = "PASS"
        admitted_b = True
        derived_touched_paths: list[str] = []
        payload_hashes = _candidate_payload_hashes(candidate)
        if quarantined_b:
            admitted_b = False
            decision_code = _DROP_AGENT_QUARANTINED
        elif bool(candidate.get("generation_error_b", False)):
            admitted_b = False
            decision_code = str(candidate.get("generation_error_code", _DROP_INVALID_SCHEMA_EDIT))
        else:
            admitted_b, decision_code, derived_touched_paths, payload_hashes = _admission_allowlist_and_preflight(
                root=root,
                candidate=candidate,
                allowlists=allowlists,
                arena_spec=arena_spec,
                lane_requires_wiring_b=lane_requires_wiring_b,
                max_patch_bytes_u32=max_patch_bytes_u32,
            )

        candidate_id = _candidate_id_from_material(
            candidate,
            derived_touched_paths=derived_touched_paths,
            payload_hashes=payload_hashes,
        )
        reason_codes = [decision_code] if decision_code != "PASS" else ["PASS"]
        _precheck_payload, precheck_hash = _write_arena_candidate_precheck(
            out_dir=precheck_dir,
            candidate_id=candidate_id,
            agent_id=agent_id,
            admitted_b=admitted_b,
            decision_code=decision_code,
            reason_codes=reason_codes,
        )

        if admitted_b and len(admitted_candidates) >= int(max_admitted_u32):
            admitted_b = False
            decision_code = _DROP_INVALID_SCHEMA_EDIT
        if not admitted_b:
            drop_hist[decision_code] = int(drop_hist.get(decision_code, 0)) + 1
            continue

        candidate_payload = _build_arena_candidate_payload(
            candidate_id=candidate_id,
            candidate=candidate,
            derived_touched_paths=derived_touched_paths,
            precheck_receipt_id=precheck_hash,
            surrogate_eval_receipt_id=None,
        )
        _, candidate_payload_obj, _candidate_hash = write_hashed_json(
            candidate_dir,
            "arena_candidate_v1.json",
            candidate_payload,
        )
        validate_schema_v19(candidate_payload_obj, "arena_candidate_v1")
        _store_candidate_payload(arena_root=arena_root, candidate_id=candidate_id, candidate=candidate)
        admitted_candidates.append(candidate_payload_obj)
        metadata_by_candidate_id[candidate_id] = candidate_payload_obj
        raw_by_candidate_id[candidate_id] = candidate
        _enforce_total_written_budget(
            max_bytes=max_total_written_bytes_u64,
            roots=[state_root, arena_root],
        )
        for row in agent_states:
            if str(row.get("agent_id", "")).strip() == agent_id:
                row["last_submitted_tick_u64"] = int(tick_u64)
                break

    surrogate_eval_rows: list[dict[str, Any]] = []
    for payload in admitted_candidates:
        _enforce_wallclock_budget(started_s=arena_started_s, max_seconds=arena_total_wallclock_s)
        receipt_payload, candidate_id, score_q32, cost_q32, risk_class, reason_codes = _surrogate_eval_candidate(
            root=root,
            candidate_payload=payload,
            surrogate_policy=surrogate_policy,
            per_candidate_timeout_s=per_candidate_surrogate_wallclock_s,
        )
        _, receipt_obj, receipt_hash = write_hashed_json(
            surrogate_dir,
            "arena_surrogate_eval_receipt_v1.json",
            receipt_payload,
            id_field="receipt_id",
        )
        validate_schema_v19(receipt_obj, "arena_surrogate_eval_receipt_v1")
        row = dict(payload)
        row["surrogate_eval_receipt_id"] = receipt_hash
        row["surrogate_score_q32"] = int(score_q32)
        row["surrogate_cost_q32"] = int(cost_q32)
        row["risk_class"] = str(risk_class)
        row["reason_codes"] = list(reason_codes)
        surrogate_eval_rows.append(row)
        write_hashed_json(candidate_dir, "arena_candidate_v1.json", row)
        metadata_by_candidate_id[candidate_id] = row
        _enforce_total_written_budget(
            max_bytes=max_total_written_bytes_u64,
            roots=[state_root, arena_root],
        )

    backlog_rows: list[dict[str, Any]] = []
    for row in list(state_in.get("candidate_backlog") or []):
        if not isinstance(row, dict):
            continue
        expires_tick = int(max(0, int(row.get("expires_tick_u64", 0))))
        if expires_tick < int(tick_u64):
            drop_hist["ARENA_DROP:EXPIRED"] = int(drop_hist.get("ARENA_DROP:EXPIRED", 0)) + 1
            continue
        backlog_rows.append(dict(row))
    for row in surrogate_eval_rows:
        backlog_rows.append(
            {
                "candidate_id": str(row.get("candidate_id", "")),
                "agent_id": str(row.get("agent_id", "")),
                "candidate_kind": str(row.get("candidate_kind", "")),
                "surrogate_score_q32": int(row.get("surrogate_score_q32", 0)),
                "surrogate_cost_q32": int(row.get("surrogate_cost_q32", 0)),
                "created_tick_u64": int(tick_u64),
                "expires_tick_u64": int(tick_u64 + candidate_ttl_u64),
                "status": "PENDING",
                "risk_class": str(row.get("risk_class", "MED")),
            }
        )

    dedup: dict[str, dict[str, Any]] = {}
    for row in backlog_rows:
        cid = str(row.get("candidate_id", "")).strip()
        if not _is_sha256(cid):
            continue
        prev = dedup.get(cid)
        if prev is None:
            dedup[cid] = dict(row)
            continue
        keep = sorted([prev, row], key=_selection_sort_key)[0]
        dedup[cid] = dict(keep)
    backlog_rows = [dict(row) for row in dedup.values()]
    backlog_rows = _trim_backlog(backlog_rows, backlog_max_u32=backlog_max_u32)
    ranked, winner_row = _deterministic_rank_and_select(backlog_rows)
    winner_row = ranked[0] if ranked else None
    if winner_row is None:
        raise RuntimeError("MISSING_STATE_INPUT")

    winner_candidate_id = str(winner_row.get("candidate_id", "")).strip()
    winner_agent_id = str(winner_row.get("agent_id", "")).strip()
    winner_kind = str(winner_row.get("candidate_kind", "")).strip()
    if winner_kind not in {_CANDIDATE_KIND_PATCH, _CANDIDATE_KIND_EXT}:
        raise RuntimeError("SCHEMA_FAIL")

    inputs_descriptor_id = canon_hash_obj(
        {
            "schema_version": "proposer_arena_inputs_descriptor_v1",
            "tick_u64": int(tick_u64),
            "arena_state_in_id": str(state_in_hash),
            "candidate_ids": [str(row.get("candidate_id", "")) for row in ranked],
        }
    )

    ranked_ids = [str(row.get("candidate_id", "")) for row in ranked]
    tie_break_codes = [_SELECT_WINNER_FROM_BACKLOG]
    if len(ranked) >= 2:
        first_key = _selection_sort_key(ranked[0])[:-1]
        second_key = _selection_sort_key(ranked[1])[:-1]
        if first_key == second_key:
            tie_break_codes.append(_SELECT_TIEBREAK_CANDIDATE_ID)
    tie_seed = canon_hash_obj(
        {
            "schema_version": "arena_selection_seed_v1",
            "inputs_descriptor_id": inputs_descriptor_id,
            "arena_state_in_id": state_in_hash,
            "ranked_candidate_ids": ranked_ids,
        }
    )
    selection_payload = {
        "schema_version": "arena_selection_receipt_v1",
        "receipt_id": _SHA256_ZERO,
        "inputs_descriptor_id": inputs_descriptor_id,
        "arena_state_in_id": state_in_hash,
        "candidates_considered": [
            {
                "candidate_id": str(row.get("candidate_id", "")),
                "score_q32": int(row.get("surrogate_score_q32", 0)),
                "cost_q32": int(row.get("surrogate_cost_q32", 0)),
                "risk_class": str(row.get("risk_class", "MED")).upper(),
            }
            for row in ranked
        ],
        "ranked_candidate_ids": ranked_ids,
        "winner_candidate_id": winner_candidate_id,
        "tie_break_proof": {
            "seed": tie_seed,
            "ordered_candidate_ids": ranked_ids,
            "chosen_candidate_id": winner_candidate_id,
        },
        "selection_reason_codes": tie_break_codes,
    }
    validate_schema_v19(selection_payload, "arena_selection_receipt_v1")
    _, selection_obj, selection_hash = write_hashed_json(
        arena_dir,
        "arena_selection_receipt_v1.json",
        selection_payload,
        id_field="receipt_id",
    )
    validate_schema_v19(selection_obj, "arena_selection_receipt_v1")

    winner_payload = raw_by_candidate_id.get(winner_candidate_id)
    if winner_payload is None:
        winner_payload = _load_candidate_payload(arena_root=arena_root, candidate_id=winner_candidate_id)
        if winner_payload is None:
            raise RuntimeError("MISSING_STATE_INPUT")

    if winner_kind == _CANDIDATE_KIND_PATCH:
        patch_bytes = bytes(winner_payload.get("patch_bytes", b""))
        touched_paths = _parse_patch_touched_paths(patch_bytes)
        _ccap_id, _bundle_hash = _emit_patch_winner_payload(
            root=root,
            state_root=state_root,
            promotion_dir=promotion_dir,
            winner_candidate_id=winner_candidate_id,
            patch_bytes=patch_bytes,
            touched_paths=touched_paths,
            pins=pins,
        )
    else:
        _ext_id = _emit_extension_winner_payload(
            promotion_dir=promotion_dir,
            extension_payload=winner_payload,
        )

    backlog_out = [dict(row) for row in backlog_rows if str(row.get("candidate_id", "")) != winner_candidate_id]
    arena_state_out = {
        "schema_version": "proposer_arena_state_v1",
        "tick_u64": int(tick_u64),
        "parent_state_hash": str(state_in_hash),
        "agent_states": sorted(agent_states, key=lambda row: str(row.get("agent_id", ""))),
        "candidate_backlog": sorted(
            [
                {
                    "candidate_id": str(row.get("candidate_id", "")),
                    "agent_id": str(row.get("agent_id", "")),
                    "candidate_kind": str(row.get("candidate_kind", "")),
                    "surrogate_score_q32": int(row.get("surrogate_score_q32", 0)),
                    "surrogate_cost_q32": int(row.get("surrogate_cost_q32", 0)),
                    "created_tick_u64": int(row.get("created_tick_u64", 0)),
                    "expires_tick_u64": int(row.get("expires_tick_u64", 0)),
                    "status": "PENDING",
                }
                for row in backlog_out
            ],
            key=lambda row: str(row.get("candidate_id", "")),
        ),
    }
    validate_schema_v19(arena_state_out, "proposer_arena_state_v1")
    _, arena_state_obj, arena_state_hash = write_hashed_json(
        arena_dir,
        "proposer_arena_state_v1.json",
        arena_state_out,
    )
    validate_schema_v19(arena_state_obj, "proposer_arena_state_v1")
    write_hashed_json(arena_root, "proposer_arena_state_v1.json", arena_state_out)
    write_canon_json(arena_root / "latest.json", arena_state_out)

    run_receipt_payload = {
        "schema_version": "proposer_arena_run_receipt_v1",
        "receipt_id": _SHA256_ZERO,
        "tick_u64": int(tick_u64),
        "arena_state_out_id": arena_state_hash,
        "n_generated_u64": int(generated_count_u64),
        "n_admitted_u64": int(len(admitted_candidates)),
        "n_backlogged_u64": int(len(arena_state_out.get("candidate_backlog") or [])),
        "n_considered_u64": int(len(ranked)),
        "winner_kind": winner_kind,
        "winner_candidate_id": winner_candidate_id,
        "winner_agent_id": winner_agent_id,
        "drop_reason_histogram": {str(k): int(v) for k, v in sorted(drop_hist.items())},
        "notes": "",
    }
    validate_schema_v19(run_receipt_payload, "proposer_arena_run_receipt_v1")
    _, run_receipt_obj, run_receipt_hash = write_hashed_json(
        arena_dir,
        "proposer_arena_run_receipt_v1.json",
        run_receipt_payload,
        id_field="receipt_id",
    )
    validate_schema_v19(run_receipt_obj, "proposer_arena_run_receipt_v1")
    write_canon_json(arena_root / "latest_run_receipt.json", run_receipt_obj)

    # Keep explicit copies in campaign state for easier replay scans.
    write_canon_json(arena_dir / "arena_selection_receipt_v1.json", selection_obj)
    write_canon_json(arena_dir / "proposer_arena_run_receipt_v1.json", run_receipt_obj)
    write_canon_json(arena_dir / "proposer_arena_state_v1.json", arena_state_obj)

    # Lightweight outcome marker for humans/operators.
    marker = {
        "schema_version": "proposer_arena_outcome_marker_v1",
        "tick_u64": int(tick_u64),
        "winner_candidate_id": winner_candidate_id,
        "winner_agent_id": winner_agent_id,
        "winner_kind": winner_kind,
        "selection_receipt_id": selection_hash,
        "run_receipt_id": run_receipt_hash,
    }
    write_canon_json(state_root / "proposer_arena_outcome_marker_v1.json", marker)
    _enforce_total_written_budget(
        max_bytes=max_total_written_bytes_u64,
        roots=[state_root, arena_root],
    )

    print("OK")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="proposer_arena_v1")
    parser.add_argument("--campaign_pack", required=True)
    parser.add_argument("--out_dir", required=True)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    run(
        campaign_pack=Path(args.campaign_pack).resolve(),
        out_dir=Path(args.out_dir).resolve(),
    )


if __name__ == "__main__":
    main()
