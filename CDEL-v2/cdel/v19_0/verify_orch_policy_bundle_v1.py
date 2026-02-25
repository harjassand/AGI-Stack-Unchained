"""RE2 verifier for orch policy bundle evaluation against pinned holdout transitions."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from ..v18_0.authority.authority_hash_v1 import load_authority_pins
from ..v18_0.omega_common_v1 import (
    canon_hash_obj,
    ensure_sha256,
    fail,
    load_canon_dict,
    repo_root,
    require_relpath,
    validate_schema,
    write_hashed_json,
)
from .common_v1 import validate_schema as validate_schema_v19
from orchestrator.omega_v19_0.orch_bandit.bandit_v1 import (
    BanditError as OrchBanditError,
    select_capability_id,
)


_Q32_ONE = 1 << 32
_ZERO_SHA256 = "sha256:" + ("0" * 64)


def _sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _load_jsonl_rows(path: Path) -> list[dict[str, Any]]:
    raw = path.read_text(encoding="utf-8")
    rows: list[dict[str, Any]] = []
    for line in raw.splitlines():
        text = str(line).strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except Exception:
            fail("SCHEMA_FAIL")
        if not isinstance(payload, dict):
            fail("SCHEMA_FAIL")
        rows.append(payload)
    return rows


def _normalized_eligible_capability_ids(value: Any) -> list[str]:
    if not isinstance(value, list) or not value:
        fail("SCHEMA_FAIL")
    out = sorted({str(row).strip() for row in value if str(row).strip()})
    if not out:
        fail("SCHEMA_FAIL")
    return out


def _validate_holdout_row(row: dict[str, Any]) -> dict[str, Any]:
    context_key = ensure_sha256(row.get("context_key"), reason="SCHEMA_FAIL")
    action = str(row.get("action_capability_id", "")).strip()
    if not action:
        fail("SCHEMA_FAIL")
    reward_q32 = row.get("reward_q32")
    if not isinstance(reward_q32, int):
        fail("SCHEMA_FAIL")
    toxic_fail_b = row.get("toxic_fail_b")
    if not isinstance(toxic_fail_b, bool):
        fail("SCHEMA_FAIL")
    eligible = _normalized_eligible_capability_ids(row.get("eligible_capability_ids"))
    return {
        "context_key": context_key,
        "action_capability_id": action,
        "reward_q32": int(reward_q32),
        "toxic_fail_b": bool(toxic_fail_b),
        "eligible_capability_ids": eligible,
    }


def _load_and_pin_eval_config(*, config_dir: Path, state_root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    pack = load_canon_dict(config_dir / "rsi_omega_daemon_pack_v1.json")
    validate_schema(pack, str(pack.get("schema_version", "")))

    rel_raw = str(pack.get("orch_policy_eval_config_rel", "")).strip()
    if not rel_raw:
        fail("MISSING_STATE_INPUT")
    rel = require_relpath(rel_raw)
    config_path = (config_dir / rel).resolve()
    if not config_path.exists() or not config_path.is_file():
        fail("MISSING_STATE_INPUT")

    config_payload = load_canon_dict(config_path)
    validate_schema_v19(config_payload, "orch_policy_eval_config_v1")
    config_id = canon_hash_obj(config_payload)

    pins = load_authority_pins(repo_root())
    pinned_config_id = str(pins.get("orch_policy_eval_config_id", "")).strip()
    pinned_holdout_id = str(pins.get("orch_policy_eval_holdout_dataset_id", "")).strip()
    if not pinned_config_id or not pinned_holdout_id:
        fail("SCHEMA_FAIL")
    ensure_sha256(pinned_config_id, reason="SCHEMA_FAIL")
    ensure_sha256(pinned_holdout_id, reason="SCHEMA_FAIL")
    if config_id != pinned_config_id:
        fail("PIN_HASH_MISMATCH")

    holdout_dataset_id = ensure_sha256(config_payload.get("holdout_dataset_id"), reason="SCHEMA_FAIL")
    if holdout_dataset_id != pinned_holdout_id:
        fail("PIN_HASH_MISMATCH")

    holdout_hex = holdout_dataset_id.split(":", 1)[1]
    holdout_path = (
        repo_root()
        / "authority"
        / "holdouts"
        / "orch_policy_eval"
        / f"sha256_{holdout_hex}.orch_transition_dataset_v1.jsonl"
    )
    if not holdout_path.exists() or not holdout_path.is_file():
        fail("MISSING_STATE_INPUT")
    holdout_bytes = holdout_path.read_bytes()
    if _sha256_bytes(holdout_bytes) != holdout_dataset_id:
        fail("PIN_HASH_MISMATCH")

    rows = [_validate_holdout_row(row) for row in _load_jsonl_rows(holdout_path)]
    if not rows:
        fail("SCHEMA_FAIL")
    if not state_root.exists() or not state_root.is_dir():
        fail("MISSING_STATE_INPUT")
    return config_payload, rows


def _normalized_ranked_capabilities(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        fail("SCHEMA_FAIL")
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in value:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        capability_id = str(row.get("capability_id", "")).strip()
        if not capability_id:
            fail("SCHEMA_FAIL")
        if capability_id in seen:
            continue
        score_q32 = row.get("score_q32")
        if not isinstance(score_q32, int):
            fail("SCHEMA_FAIL")
        out.append({"capability_id": capability_id, "score_q32": int(score_q32)})
        seen.add(capability_id)
    if not out:
        fail("SCHEMA_FAIL")
    return out


def _build_policy_lookup(table_payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    rows_raw = table_payload.get("rows")
    if not isinstance(rows_raw, list):
        fail("SCHEMA_FAIL")
    lookup: dict[str, list[dict[str, Any]]] = {}
    for row in rows_raw:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        context_key = ensure_sha256(row.get("context_key"), reason="SCHEMA_FAIL")
        ranked = _normalized_ranked_capabilities(row.get("ranked_capabilities"))
        if context_key in lookup:
            fail("NONDETERMINISTIC")
        lookup[context_key] = ranked
    return lookup


def _verify_policy_bundle_hashes(bundle_payload: dict[str, Any]) -> tuple[str, dict[str, Any], dict[str, list[dict[str, Any]]]]:
    validate_schema_v19(bundle_payload, "orch_policy_bundle_v1")

    policy_bundle_id = ensure_sha256(bundle_payload.get("policy_bundle_id"), reason="SCHEMA_FAIL")
    bundle_no_id = dict(bundle_payload)
    bundle_no_id.pop("policy_bundle_id", None)
    if canon_hash_obj(bundle_no_id) != policy_bundle_id:
        fail("NONDETERMINISTIC")

    table_payload_raw = bundle_payload.get("policy_table")
    if not isinstance(table_payload_raw, dict):
        fail("SCHEMA_FAIL")
    table_payload = dict(table_payload_raw)
    validate_schema_v19(table_payload, "orch_policy_table_v1")

    declared_table_id = ensure_sha256(bundle_payload.get("policy_table_id"), reason="SCHEMA_FAIL")
    table_id = ensure_sha256(table_payload.get("policy_table_id"), reason="SCHEMA_FAIL")
    if table_id != declared_table_id:
        fail("NONDETERMINISTIC")
    table_no_id = dict(table_payload)
    table_no_id.pop("policy_table_id", None)
    if canon_hash_obj(table_no_id) != table_id:
        fail("NONDETERMINISTIC")

    lookup = _build_policy_lookup(table_payload)
    return policy_bundle_id, table_payload, lookup


def _evaluate_against_selector(
    *,
    holdout_rows: list[dict[str, Any]],
    context_to_selected_action: Callable[[dict[str, Any]], str | None],
    coverage_lookup: dict[str, list[dict[str, Any]]] | None,
) -> tuple[int, int, int, int]:
    total = int(len(holdout_rows))
    matched_count = 0
    value_sum_q32 = 0
    toxic_count = 0
    coverage_count = 0

    for row in holdout_rows:
        context_key = str(row["context_key"])
        if isinstance(coverage_lookup, dict) and context_key in coverage_lookup:
            coverage_count += 1
        selected = context_to_selected_action(row)
        if selected is None:
            continue
        if str(selected) != str(row["action_capability_id"]):
            continue
        matched_count += 1
        value_sum_q32 += int(row["reward_q32"])
        if bool(row["toxic_fail_b"]):
            toxic_count += 1

    value_q32 = int(value_sum_q32 // total) if total > 0 else 0
    toxic_rate_q32 = int((toxic_count * _Q32_ONE) // matched_count) if matched_count > 0 else 0
    coverage_q32 = int((coverage_count * _Q32_ONE) // total) if total > 0 else 0
    return value_q32, toxic_rate_q32, coverage_q32, matched_count


def _load_active_policy_lookup(*, state_root: Path) -> tuple[str, dict[str, list[dict[str, Any]]]]:
    daemon_root = state_root.parent.parent
    pointer_path = daemon_root / "orch_policy" / "active" / "ORCH_POLICY_V1.json"
    if not pointer_path.exists() or not pointer_path.is_file():
        fail("MISSING_STATE_INPUT")
    pointer = load_canon_dict(pointer_path)
    validate_schema_v19(pointer, "orch_policy_pointer_v1")
    bundle_id = ensure_sha256(pointer.get("active_policy_bundle_id"), reason="SCHEMA_FAIL")

    bundle_path = daemon_root / "orch_policy" / "store" / f"sha256_{bundle_id.split(':', 1)[1]}.orch_policy_bundle_v1.json"
    if not bundle_path.exists() or not bundle_path.is_file():
        fail("MISSING_STATE_INPUT")
    bundle_payload = load_canon_dict(bundle_path)
    observed_bundle_id, _table_payload, lookup = _verify_policy_bundle_hashes(bundle_payload)
    if observed_bundle_id != bundle_id:
        fail("NONDETERMINISTIC")
    return bundle_id, lookup


def _load_bandit_baseline_selector(*, config_dir: Path, state_root: Path) -> Callable[[dict[str, Any]], str | None]:
    pack = load_canon_dict(config_dir / "rsi_omega_daemon_pack_v1.json")
    validate_schema(pack, str(pack.get("schema_version", "")))
    bandit_rel_raw = str(pack.get("orch_bandit_config_rel", "")).strip()
    if not bandit_rel_raw:
        fail("MISSING_STATE_INPUT")
    bandit_rel = require_relpath(bandit_rel_raw)
    bandit_cfg_path = config_dir / bandit_rel
    if not bandit_cfg_path.exists() or not bandit_cfg_path.is_file():
        fail("MISSING_STATE_INPUT")
    bandit_cfg = load_canon_dict(bandit_cfg_path)
    validate_schema_v19(bandit_cfg, "orch_bandit_config_v1")

    pointer_path = state_root / "orch_bandit" / "state" / "ACTIVE_ORCH_BANDIT_STATE"
    if not pointer_path.exists() or not pointer_path.is_file():
        fail("MISSING_STATE_INPUT")
    state_id = ensure_sha256(pointer_path.read_text(encoding="utf-8").strip(), reason="SCHEMA_FAIL")
    state_path = state_root / "orch_bandit" / "state" / f"sha256_{state_id.split(':', 1)[1]}.orch_bandit_state_v1.json"
    if not state_path.exists() or not state_path.is_file():
        fail("MISSING_STATE_INPUT")
    bandit_state = load_canon_dict(state_path)
    validate_schema_v19(bandit_state, "orch_bandit_state_v1")
    if canon_hash_obj(bandit_state) != state_id:
        fail("NONDETERMINISTIC")

    def _selector(row: dict[str, Any]) -> str | None:
        try:
            return select_capability_id(
                config=bandit_cfg,
                state=bandit_state,
                context_key=str(row["context_key"]),
                eligible_capability_ids=list(row["eligible_capability_ids"]),
            )
        except OrchBanditError:
            fail("SCHEMA_FAIL")
        return None

    return _selector


def verify_orch_policy_bundle_v1(
    *,
    tick_u64: int,
    dispatch_ctx: dict[str, Any],
    candidate_bundle_path: Path,
) -> tuple[dict[str, Any], str]:
    state_root_raw = dispatch_ctx.get("state_root")
    if not isinstance(state_root_raw, (str, Path)):
        fail("MISSING_STATE_INPUT")
    state_root = Path(state_root_raw).resolve()

    config_dir_candidates = [
        state_root.parent / "config",
        state_root / "config",
    ]
    config_dir = next((row for row in config_dir_candidates if row.exists() and row.is_dir()), None)
    if config_dir is None:
        fail("MISSING_STATE_INPUT")

    eval_cfg, holdout_rows = _load_and_pin_eval_config(config_dir=config_dir, state_root=state_root)

    if not candidate_bundle_path.exists() or not candidate_bundle_path.is_file():
        fail("MISSING_STATE_INPUT")
    bundle_payload = load_canon_dict(candidate_bundle_path)
    candidate_policy_bundle_id, _candidate_table, candidate_lookup = _verify_policy_bundle_hashes(bundle_payload)

    def _candidate_selector(row: dict[str, Any]) -> str | None:
        ranked = candidate_lookup.get(str(row["context_key"]))
        if not ranked:
            return None
        return str(ranked[0]["capability_id"])

    baseline_kind = str(eval_cfg.get("baseline_kind", "")).strip().upper()
    if baseline_kind not in {"ACTIVE_POLICY", "CURRENT_BANDIT_STATE"}:
        fail("SCHEMA_FAIL")

    baseline_lookup: dict[str, list[dict[str, Any]]] | None = None
    baseline_bundle_id: str | None = None
    if baseline_kind == "ACTIVE_POLICY":
        baseline_bundle_id, baseline_lookup = _load_active_policy_lookup(state_root=state_root)

        def _baseline_selector(row: dict[str, Any]) -> str | None:
            ranked = baseline_lookup.get(str(row["context_key"]))
            if not ranked:
                return None
            return str(ranked[0]["capability_id"])

    else:
        _baseline_selector = _load_bandit_baseline_selector(config_dir=config_dir, state_root=state_root)

    candidate_value_q32, candidate_toxic_rate_q32, coverage_q32, _candidate_matched = _evaluate_against_selector(
        holdout_rows=holdout_rows,
        context_to_selected_action=_candidate_selector,
        coverage_lookup=candidate_lookup,
    )
    baseline_value_q32, baseline_toxic_rate_q32, _unused_coverage, _baseline_matched = _evaluate_against_selector(
        holdout_rows=holdout_rows,
        context_to_selected_action=_baseline_selector,
        coverage_lookup=baseline_lookup,
    )

    delta_q32 = int(candidate_value_q32 - baseline_value_q32)
    toxic_delta_q32 = int(candidate_toxic_rate_q32 - baseline_toxic_rate_q32)

    status = "PASS"
    reason_code = "OK"

    min_coverage_q32 = int(eval_cfg.get("min_coverage_q32", 0))
    min_delta_q32 = int(eval_cfg.get("min_delta_q32", 0))
    max_toxic_increase_q32 = int(eval_cfg.get("max_toxic_increase_q32", 0))

    if int(coverage_q32) < int(min_coverage_q32):
        status = "FAIL"
        reason_code = "EVAL_FAIL:LOW_COVERAGE"
    elif int(delta_q32) < int(min_delta_q32):
        status = "FAIL"
        reason_code = "EVAL_FAIL:NO_IMPROVEMENT"
    elif int(toxic_delta_q32) > int(max_toxic_increase_q32):
        status = "FAIL"
        reason_code = "EVAL_FAIL:TOXIC_INCREASE"

    receipt_payload = {
        "schema_version": "orch_policy_eval_receipt_v1",
        "candidate_policy_bundle_id": str(candidate_policy_bundle_id),
        "baseline_kind": str(baseline_kind),
        "status": str(status),
        "reason_code": str(reason_code),
        "metrics": {
            "candidate_value_q32": int(candidate_value_q32),
            "baseline_value_q32": int(baseline_value_q32),
            "delta_q32": int(delta_q32),
            "coverage_q32": int(coverage_q32),
            "candidate_toxic_rate_q32": int(candidate_toxic_rate_q32),
            "baseline_toxic_rate_q32": int(baseline_toxic_rate_q32),
            "toxic_delta_q32": int(toxic_delta_q32),
        },
    }
    validate_schema_v19(receipt_payload, "orch_policy_eval_receipt_v1")

    out_dir = Path(dispatch_ctx["dispatch_dir"]) / "promotion"
    _, receipt, receipt_id = write_hashed_json(out_dir, "orch_policy_eval_receipt_v1.json", receipt_payload)
    validate_schema_v19(receipt, "orch_policy_eval_receipt_v1")

    # Keep side-effect-free: only aggregate metrics leak into receipt payload.
    _ = baseline_bundle_id
    _ = _ZERO_SHA256
    _ = tick_u64
    return receipt, receipt_id


__all__ = ["verify_orch_policy_bundle_v1"]
