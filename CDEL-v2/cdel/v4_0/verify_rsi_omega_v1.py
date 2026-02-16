"""Verifier for RSI Omega protocol v1 (v4.0)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from ..v1_7r.canon import CanonError, canon_bytes, load_canon_json, sha256_prefixed
from ..v2_3.immutable_core import load_lock, validate_lock
from ..v3_3.meta_ledger import compute_meta_policy_hash, compute_meta_state_hash
from ..v3_3.swarm_ledger import load_swarm_ledger
from ..v3_3.verify_rsi_swarm_v4 import verify as verify_swarm
from .constants import meta_identities, require_constants
from .omega_ledger import load_omega_ledger, validate_omega_chain
from .omega_metrics import (
    TaskResult,
    accel_index_v1,
    compute_cumulative,
    compute_new_solves_over_baseline,
    compute_rolling_windows,
    passrate_gain,
    ratio_ge,
)

ROOT_PREFIX = "@ROOT/"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _fail(reason: str) -> None:
    raise CanonError(reason)


def _resolve_path(state_dir: Path, path_str: str) -> Path:
    if path_str.startswith(ROOT_PREFIX):
        return state_dir / path_str[len(ROOT_PREFIX) :]
    path = Path(path_str)
    if path.is_absolute():
        return path
    return state_dir / path


def _resolve_pack_path(state_dir: Path, path_str: str) -> Path:
    repo_root = state_dir.parent.parent
    if path_str.startswith(ROOT_PREFIX):
        rel = path_str[len(ROOT_PREFIX) :]
        run_path = state_dir / rel
        repo_path = repo_root / rel
        run_exists = run_path.exists()
        repo_exists = repo_path.exists()
        if run_exists and repo_exists:
            if sha256_prefixed(run_path.read_bytes()) != sha256_prefixed(repo_path.read_bytes()):
                _fail("OMEGA_ROOT_PATH_COLLISION")
            return run_path
        if run_exists:
            return run_path
        if repo_exists:
            return repo_path
        return repo_path
    path = Path(path_str)
    if path.is_absolute():
        return path
    return repo_root / path


def _compute_pack_hash(pack: dict[str, Any]) -> str:
    payload = dict(pack)
    payload.pop("pack_hash", None)
    return sha256_prefixed(canon_bytes(payload))


def _compute_receipt_hash(receipt: dict[str, Any]) -> str:
    payload = dict(receipt)
    payload.pop("receipt_hash", None)
    return sha256_prefixed(canon_bytes(payload))


def _compute_json_hash(obj: dict[str, Any]) -> str:
    return sha256_prefixed(canon_bytes(obj))


def _find_omega_pack(state_dir: Path) -> tuple[Path, dict[str, Any]]:
    preferred = state_dir / "rsi_real_omega_pack_v1.json"
    if preferred.exists():
        return preferred, load_canon_json(preferred)
    for path in state_dir.glob("*.json"):
        try:
            payload = load_canon_json(path)
        except Exception:
            continue
        if payload.get("schema") == "rsi_real_omega_pack_v1":
            return path, payload
    _fail("MISSING_ARTIFACT")
    raise AssertionError


def _load_baseline(path: Path) -> dict[str, Any]:
    if not path.exists():
        _fail("MISSING_ARTIFACT")
    return load_canon_json(path)


def _load_omega_receipt(path: Path, expected_schema: str) -> dict[str, Any]:
    if not path.exists():
        _fail("MISSING_ARTIFACT")
    receipt = load_canon_json(path)
    if receipt.get("schema") != expected_schema or receipt.get("spec_version") != "v4_0":
        _fail("SCHEMA_INVALID")
    expected_hash = _compute_receipt_hash(receipt)
    if receipt.get("receipt_hash") != expected_hash:
        _fail("CANON_HASH_MISMATCH")
    return receipt


def _collect_valid_result_verify_refs(swarm_events: list[dict[str, Any]]) -> set[str]:
    refs: set[str] = set()
    for event in swarm_events:
        if event.get("event_type") != "RESULT_VERIFY":
            continue
        payload = event.get("payload") or {}
        if payload.get("verdict") != "VALID":
            continue
        ref = event.get("event_ref_hash")
        if isinstance(ref, str):
            refs.add(ref)
    return refs


def _contains_forbidden_fields(payload: Any, forbidden: set[str]) -> bool:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in forbidden:
                return True
            if _contains_forbidden_fields(value, forbidden):
                return True
        return False
    if isinstance(payload, list):
        return any(_contains_forbidden_fields(item, forbidden) for item in payload)
    return False


def _verify_meta_head(state_dir: Path, head: dict[str, Any]) -> None:
    block_id = head.get("meta_block_id")
    state_hash = head.get("meta_state_hash")
    policy_hash = head.get("meta_policy_hash")
    if not isinstance(block_id, str) or not isinstance(state_hash, str) or not isinstance(policy_hash, str):
        _fail("SCHEMA_INVALID")
    block_name = f"sha256_{block_id.split(':', 1)[1]}.meta_block_v1.json"
    block_path = state_dir / "meta_exchange" / "blocks" / block_name
    if not block_path.exists():
        _fail("MISSING_ARTIFACT")
    block = load_canon_json(block_path)
    if block.get("meta_block_id") != block_id:
        _fail("CANON_HASH_MISMATCH")
    if block.get("meta_state_hash") != state_hash:
        _fail("CANON_HASH_MISMATCH")
    if block.get("meta_policy_hash") != policy_hash:
        _fail("CANON_HASH_MISMATCH")
    state_path = _resolve_path(state_dir, block.get("meta_state_path", ""))
    policy_path = _resolve_path(state_dir, block.get("meta_policy_path", ""))
    if not state_path.exists() or not policy_path.exists():
        _fail("MISSING_ARTIFACT")
    state_payload = load_canon_json(state_path)
    policy_payload = load_canon_json(policy_path)
    if compute_meta_state_hash(state_payload) != state_hash:
        _fail("CANON_HASH_MISMATCH")
    if compute_meta_policy_hash(policy_payload) != policy_hash:
        _fail("CANON_HASH_MISMATCH")


def _verify_checkpoint_receipt(
    receipt: dict[str, Any],
    computed: dict[str, Any],
) -> None:
    for key in ["checkpoint_index", "closed_epoch_index", "cumulative", "meta_head", "rolling_windows", "acceleration"]:
        if receipt.get(key) != computed.get(key):
            _fail("CANON_HASH_MISMATCH")


def _omega_stop_index(events: list[dict[str, Any]]) -> int | None:
    for idx, event in enumerate(events):
        if event.get("event_type") == "OMEGA_STOP":
            return idx
    return None


def _verify_proposal_artifact(state_dir: Path, *, proposal_id: str, proposal_path: str) -> None:
    path = _resolve_path(state_dir, proposal_path)
    if not path.exists():
        _fail("MISSING_ARTIFACT")
    proposal = load_canon_json(path)
    if not isinstance(proposal, dict):
        _fail("SCHEMA_INVALID")
    if proposal.get("proposal_id") != proposal_id:
        _fail("CANON_HASH_MISMATCH")
    body = dict(proposal)
    body.pop("proposal_id", None)
    expected = sha256_prefixed(canon_bytes(body))
    if expected != proposal_id:
        _fail("CANON_HASH_MISMATCH")


def _verify_dev_gate_receipt(state_dir: Path, *, expected_hash: str, receipt_path: str) -> dict[str, Any]:
    path = _resolve_path(state_dir, receipt_path)
    if not path.exists():
        _fail("MISSING_ARTIFACT")
    receipt = load_canon_json(path)
    if not isinstance(receipt, dict):
        _fail("SCHEMA_INVALID")
    if receipt.get("schema") != "omega_dev_gate_receipt_v1" or receipt.get("spec_version") != "v4_0":
        _fail("SCHEMA_INVALID")
    computed = _compute_receipt_hash(receipt)
    if receipt.get("receipt_hash") != computed:
        _fail("CANON_HASH_MISMATCH")
    if computed != expected_hash:
        _fail("CANON_HASH_MISMATCH")
    return receipt


def _verify_promotion_bundle(state_dir: Path, *, promotion_bundle_id: str, promotion_bundle_path: str) -> dict[str, Any]:
    bundle_dir = _resolve_pack_path(state_dir, promotion_bundle_path)
    if not bundle_dir.exists():
        _fail("MISSING_ARTIFACT")
    policy_path = bundle_dir / "omega_solver_policy_v1.json"
    if not policy_path.exists():
        _fail("MISSING_ARTIFACT")
    policy = load_canon_json(policy_path)
    if not isinstance(policy, dict):
        _fail("SCHEMA_INVALID")
    if policy.get("schema") != "omega_solver_policy_v1" or policy.get("spec_version") != "v4_0":
        _fail("SCHEMA_INVALID")
    if _compute_json_hash(policy) != promotion_bundle_id:
        _fail("CANON_HASH_MISMATCH")
    supported_ops = policy.get("supported_ops")
    if not isinstance(supported_ops, int) or supported_ops < 0:
        _fail("SCHEMA_INVALID")
    return policy


def _verify_epochs(
    events: list[dict[str, Any]],
    tasks_per_epoch: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    closed_epochs: list[dict[str, Any]] = []
    eval_events: list[dict[str, Any]] = []
    current_epoch: int | None = None
    sampled_ids: list[str] = []
    sample_index_expected = 0
    tasks_attempted = 0
    tasks_passed = 0
    compute_used_total = 0
    attempted_ids: set[str] = set()

    for event in events:
        event_type = event.get("event_type")
        epoch_index = event.get("epoch_index")
        if event_type == "OMEGA_EPOCH_OPEN":
            if current_epoch is not None:
                _fail("SCHEMA_INVALID")
            if current_epoch is None and closed_epochs:
                if epoch_index != closed_epochs[-1]["epoch_index"] + 1:
                    _fail("SCHEMA_INVALID")
            if current_epoch is None and not closed_epochs and epoch_index != 0:
                _fail("SCHEMA_INVALID")
            current_epoch = int(epoch_index)
            sampled_ids = []
            sample_index_expected = 0
            tasks_attempted = 0
            tasks_passed = 0
            compute_used_total = 0
            attempted_ids = set()
            continue

        if current_epoch is None:
            if event_type in {
                "OMEGA_TASK_SAMPLE",
                "OMEGA_TASK_ATTEMPT_BEGIN",
                "OMEGA_TASK_EVAL_REQUEST",
                "OMEGA_TASK_EVAL_RESULT",
                "OMEGA_TASK_ATTEMPT_END",
                "OMEGA_EPOCH_CLOSE",
            }:
                _fail("SCHEMA_INVALID")
            continue

        if int(epoch_index) != current_epoch:
            _fail("SCHEMA_INVALID")

        if event_type == "OMEGA_TASK_SAMPLE":
            payload = event.get("payload") or {}
            if int(payload.get("sample_index", -1)) != sample_index_expected:
                _fail("SCHEMA_INVALID")
            task_id = payload.get("task_id")
            if not isinstance(task_id, str):
                _fail("SCHEMA_INVALID")
            sampled_ids.append(task_id)
            sample_index_expected += 1
            if len(sampled_ids) > tasks_per_epoch:
                _fail("SCHEMA_INVALID")
        elif event_type == "OMEGA_TASK_EVAL_RESULT":
            payload = event.get("payload") or {}
            task_id = payload.get("task_id")
            if task_id not in sampled_ids:
                _fail("SCHEMA_INVALID")
            if task_id in attempted_ids:
                _fail("SCHEMA_INVALID")
            attempted_ids.add(task_id)
            tasks_attempted += 1
            if payload.get("verdict") == "PASS":
                tasks_passed += 1
            compute_used_total += int(payload.get("compute_used", 0))
            eval_events.append({"epoch_index": current_epoch, "event": event})
        elif event_type == "OMEGA_EPOCH_CLOSE":
            payload = event.get("payload") or {}
            if payload.get("tasks_sampled") != len(sampled_ids):
                _fail("SCHEMA_INVALID")
            if payload.get("tasks_attempted") != tasks_attempted:
                _fail("SCHEMA_INVALID")
            if payload.get("tasks_passed") != tasks_passed:
                _fail("SCHEMA_INVALID")
            if payload.get("compute_used_total") != compute_used_total:
                _fail("SCHEMA_INVALID")
            if len(sampled_ids) != tasks_per_epoch:
                _fail("SCHEMA_INVALID")
            closed_epochs.append(
                {
                    "epoch_index": current_epoch,
                    "payload": payload,
                    "sampled_ids": list(sampled_ids),
                }
            )
            current_epoch = None
    if current_epoch is not None:
        _fail("SCHEMA_INVALID")
    return closed_epochs, eval_events


def verify(state_dir: Path) -> dict[str, Any]:
    constants = require_constants()
    lock_rel = constants.get("IMMUTABLE_CORE_LOCK_REL")
    if not isinstance(lock_rel, str):
        _fail("IMMUTABLE_CORE_ATTESTATION_INVALID")

    lock_path = _repo_root() / lock_rel
    if not lock_path.exists():
        _fail("MISSING_ARTIFACT")
    lock = load_lock(lock_path)
    try:
        validate_lock(lock)
    except Exception as exc:  # noqa: BLE001
        raise CanonError("IMMUTABLE_CORE_ATTESTATION_INVALID") from exc

    pack_path, pack = _find_omega_pack(state_dir)
    if pack.get("schema") != "rsi_real_omega_pack_v1" or pack.get("spec_version") != "v4_0":
        _fail("SCHEMA_INVALID")
    expected_pack_hash = _compute_pack_hash(pack)
    if pack.get("pack_hash") != expected_pack_hash:
        _fail("CANON_HASH_MISMATCH")

    identities = meta_identities()
    root_cfg = pack.get("root") or {}
    if root_cfg.get("required_icore_id") != lock.get("core_id"):
        _fail("ICORE_MISMATCH")
    if root_cfg.get("required_meta_hash") != identities.get("META_HASH"):
        _fail("META_HASH_MISMATCH")

    # Phase B: verify swarm/meta prefix (v3.3)
    receipt = verify_swarm(state_dir)
    if receipt.get("verdict") != "VALID":
        _fail("SWARM_INVALID")

    # Load swarm ledger for RESULT_VERIFY references + run id
    swarm_events = load_swarm_ledger(state_dir / "ledger" / "swarm_ledger_v5.jsonl")
    swarm_run_id = ""
    for event in swarm_events:
        if event.get("event_type") == "SWARM_INIT":
            swarm_run_id = str((event.get("payload") or {}).get("swarm_run_id", ""))
            break
    if not swarm_run_id:
        _fail("SCHEMA_INVALID")
    valid_result_refs = _collect_valid_result_verify_refs(swarm_events)
    if not valid_result_refs:
        _fail("SCHEMA_INVALID")

    # Omega ledger
    omega_path = state_dir / "omega" / "omega_ledger_v1.jsonl"
    omega_events = load_omega_ledger(omega_path)
    validate_omega_chain(omega_events)

    for event in omega_events:
        if event.get("root_swarm_run_id") != swarm_run_id:
            _fail("SCHEMA_INVALID")
        if event.get("icore_id") != lock.get("core_id"):
            _fail("SCHEMA_INVALID")

    stop_idx = _omega_stop_index(omega_events)
    if stop_idx is not None and stop_idx != len(omega_events) - 1:
        _fail("SCHEMA_INVALID")

    omega_cfg = pack.get("omega") or {}
    tasks_per_epoch = int(omega_cfg.get("tasks_per_epoch", 0))
    if tasks_per_epoch <= 0:
        _fail("SCHEMA_INVALID")

    closed_epochs, eval_events = _verify_epochs(omega_events, tasks_per_epoch)
    if not closed_epochs:
        _fail("SCHEMA_INVALID")

    # Validate meta heads referenced by epoch close records
    for epoch in closed_epochs:
        head = (epoch.get("payload") or {}).get("meta_head") or {}
        _verify_meta_head(state_dir, head)

    # Validate sealed eval receipts + publisher references
    forbidden = set(constants.get("OMEGA_FORBIDDEN_LEAK_FIELDS", []))
    for item in eval_events:
        event = item.get("event") or {}
        payload = event.get("payload") or {}
        receipt_path = _resolve_path(state_dir, payload.get("sealed_eval_receipt_path", ""))
        receipt = load_canon_json(receipt_path)
        if _contains_forbidden_fields(receipt, forbidden):
            _fail("SCHEMA_INVALID")
        receipt_hash = _compute_json_hash(receipt)
        if receipt_hash != payload.get("sealed_eval_receipt_hash"):
            _fail("CANON_HASH_MISMATCH")
        result_ref = payload.get("publisher_result_verify_event_ref_hash")
        if result_ref not in valid_result_refs:
            _fail("SCHEMA_INVALID")

    # Baseline
    baseline_cfg = omega_cfg.get("baseline") or {}
    baseline_path = _resolve_pack_path(state_dir, baseline_cfg.get("baseline_report_path", ""))
    baseline = _load_baseline(baseline_path)
    baseline_hash = _compute_json_hash(baseline)
    if baseline_hash != baseline_cfg.get("baseline_report_hash"):
        _fail("CANON_HASH_MISMATCH")

    baseline_solved = set(baseline.get("solved_task_ids") or [])
    baseline_passed = int(baseline.get("pass_rate_num", len(baseline_solved)))
    baseline_attempted = int(baseline.get("pass_rate_den", max(baseline.get("task_count", len(baseline_solved)), 1)))

    # Checkpoints + metrics
    checkpoint_dir = state_dir / "omega" / "checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    checkpoints_written: list[dict[str, Any]] = []

    results_by_epoch: list[tuple[int, Any]] = []
    for item in eval_events:
        event = item.get("event") or {}
        payload = event.get("payload") or {}
        results_by_epoch.append(
            (
                int(item.get("epoch_index", 0)),
                {
                    "task_id": str(payload.get("task_id", "")),
                    "verdict": str(payload.get("verdict", "")),
                    "compute_used": int(payload.get("compute_used", 0)),
                },
            )
        )
    rolling_cfg = omega_cfg.get("success_criteria", {}).get("rolling_window", {})
    window_tasks = int(rolling_cfg.get("window_tasks", 1))
    min_windows = int(rolling_cfg.get("min_windows", 1))

    accel_cfg = omega_cfg.get("success_criteria", {}).get("acceleration", {})
    accel_min_num = int(accel_cfg.get("min_accel_ratio_num", 0))
    accel_min_den = int(accel_cfg.get("min_accel_ratio_den", 1))
    accel_min_windows = int(accel_cfg.get("min_consecutive_windows", 1))

    min_new_solves = int(omega_cfg.get("success_criteria", {}).get("min_new_solves_over_baseline", 0))
    gain_num_req = int(omega_cfg.get("success_criteria", {}).get("min_passrate_gain_num", 0))
    gain_den_req = int(omega_cfg.get("success_criteria", {}).get("min_passrate_gain_den", 1))

    # Verify checkpoint receipts referenced in ledger
    for event in omega_events:
        if event.get("event_type") != "OMEGA_CHECKPOINT_WRITE":
            continue
        payload = event.get("payload") or {}
        receipt_path = _resolve_path(state_dir, payload.get("receipt_path", ""))
        receipt = _load_omega_receipt(receipt_path, "omega_checkpoint_receipt_v1")
        checkpoints_written.append(receipt)

    if not checkpoints_written:
        _fail("SCHEMA_INVALID")

    # recompute + compare
    meta_head_by_epoch = {epoch["epoch_index"]: (epoch.get("payload") or {}).get("meta_head") for epoch in closed_epochs}

    def _results_up_to_epoch(epoch_index: int) -> list[TaskResult]:
        subset: list[TaskResult] = []
        for idx, res in results_by_epoch:
            if idx <= epoch_index:
                subset.append(
                    TaskResult(
                        task_id=str(res.get("task_id", "")),
                        verdict=str(res.get("verdict", "")),
                        compute_used=int(res.get("compute_used", 0)),
                    )
                )
        return subset

    for receipt in checkpoints_written:
        closed_epoch_index = int(receipt.get("closed_epoch_index", -1))
        subset = _results_up_to_epoch(closed_epoch_index)
        cumulative = compute_cumulative(subset)
        windows = compute_rolling_windows(subset, window_tasks)
        accel = accel_index_v1(windows, accel_min_windows, accel_min_num, accel_min_den)
        meta_head = receipt.get("meta_head")
        if meta_head != meta_head_by_epoch.get(closed_epoch_index):
            _fail("CANON_HASH_MISMATCH")
        computed = {
            "checkpoint_index": receipt.get("checkpoint_index"),
            "closed_epoch_index": closed_epoch_index,
            "meta_head": meta_head,
            "cumulative": cumulative,
            "rolling_windows": windows,
            "acceleration": accel,
        }
        _verify_checkpoint_receipt(receipt, computed)

    # Improvement events (if present): verify proposal+dev-gate artifacts, promotion bundle content-addressing,
    # and ensure checkpoints reflect the active promotion bundle id.
    self_improve_cfg = omega_cfg.get("self_improvement") or {}
    self_improve_enabled = bool(self_improve_cfg.get("enabled"))
    max_promotions_per_checkpoint = int(self_improve_cfg.get("max_promotions_per_checkpoint", 0)) if self_improve_enabled else 0

    proposal_emit: dict[str, dict[str, Any]] = {}
    proposal_eval: dict[str, dict[str, Any]] = {}
    active_promotion_bundle_id = "GENESIS"
    promotions_applied = 0

    checkpoint_by_hash = {str(r.get("receipt_hash")): r for r in checkpoints_written}

    for event in omega_events:
        event_type = event.get("event_type")
        payload = event.get("payload") or {}

        if event_type == "OMEGA_PROPOSAL_EMIT":
            proposal_id = payload.get("proposal_id")
            proposal_path = payload.get("proposal_path")
            if not isinstance(proposal_id, str) or not isinstance(proposal_path, str):
                _fail("SCHEMA_INVALID")
            _verify_proposal_artifact(state_dir, proposal_id=proposal_id, proposal_path=proposal_path)
            proposal_emit[proposal_id] = payload

        elif event_type == "OMEGA_PROPOSAL_EVAL_RESULT":
            proposal_id = payload.get("proposal_id")
            receipt_hash = payload.get("dev_gate_receipt_hash")
            receipt_path = payload.get("dev_gate_receipt_path")
            decision = payload.get("decision")
            if not isinstance(proposal_id, str) or not isinstance(receipt_hash, str) or not isinstance(receipt_path, str):
                _fail("SCHEMA_INVALID")
            if decision not in {"ACCEPT", "REJECT"}:
                _fail("SCHEMA_INVALID")
            dev_receipt = _verify_dev_gate_receipt(state_dir, expected_hash=receipt_hash, receipt_path=receipt_path)
            # Ensure the event matches the receipt's verdict deterministically.
            if dev_receipt.get("proposal_id") != proposal_id:
                _fail("CANON_HASH_MISMATCH")
            if dev_receipt.get("decision") != decision:
                _fail("CANON_HASH_MISMATCH")
            if dev_receipt.get("delta_score_num") != payload.get("delta_score_num"):
                _fail("CANON_HASH_MISMATCH")
            if dev_receipt.get("delta_score_den") != payload.get("delta_score_den"):
                _fail("CANON_HASH_MISMATCH")
            proposal_eval[proposal_id] = payload

        elif event_type == "OMEGA_PROMOTION_APPLY":
            proposal_id = payload.get("proposal_id")
            if not isinstance(proposal_id, str):
                _fail("SCHEMA_INVALID")
            if (proposal_eval.get(proposal_id) or {}).get("decision") != "ACCEPT":
                _fail("SCHEMA_INVALID")
            bundle_id = payload.get("promotion_bundle_id")
            bundle_path = payload.get("promotion_bundle_path")
            if not isinstance(bundle_id, str) or not isinstance(bundle_path, str):
                _fail("SCHEMA_INVALID")
            if payload.get("meta_core_verdict") != "VALID":
                _fail("SCHEMA_INVALID")
            _verify_promotion_bundle(state_dir, promotion_bundle_id=bundle_id, promotion_bundle_path=bundle_path)
            active_promotion_bundle_id = bundle_id
            promotions_applied += 1

        elif event_type == "OMEGA_CHECKPOINT_WRITE":
            receipt_hash = payload.get("receipt_hash")
            if not isinstance(receipt_hash, str):
                _fail("SCHEMA_INVALID")
            receipt = checkpoint_by_hash.get(receipt_hash)
            if receipt is None:
                _fail("SCHEMA_INVALID")
            active_sys = receipt.get("active_system") or {}
            if (active_sys.get("active_promotion_bundle_id") or "GENESIS") != active_promotion_bundle_id:
                _fail("CANON_HASH_MISMATCH")

    if self_improve_enabled and max_promotions_per_checkpoint > 0 and promotions_applied < 1:
        _fail("SCHEMA_INVALID")

    # Ignition receipt validation (if present)
    ignition_dir = state_dir / "omega" / "ignition"
    ignition_receipts = list(ignition_dir.glob("*.json")) if ignition_dir.exists() else []
    ignition_receipt = None
    if ignition_receipts:
        ignition_receipt = _load_omega_receipt(ignition_receipts[0], "omega_ignition_receipt_v1")

    def _checkpoint_meets_criteria(receipt: dict[str, Any]) -> bool:
        closed_epoch_index = int(receipt.get("closed_epoch_index", -1))
        subset = _results_up_to_epoch(closed_epoch_index)
        omega_solved = {row.task_id for row in subset if row.verdict == "PASS"}
        new_solves = compute_new_solves_over_baseline(omega_solved, baseline_solved)
        gain_num, gain_den = passrate_gain(
            receipt.get("cumulative", {}).get("tasks_passed", 0),
            receipt.get("cumulative", {}).get("tasks_attempted", 0),
            baseline_passed,
            baseline_attempted,
        )
        if new_solves < min_new_solves:
            return False
        if not ratio_ge(gain_num, gain_den, gain_num_req, gain_den_req):
            return False
        windows = receipt.get("rolling_windows", [])
        if len(windows) < min_windows:
            return False
        accel = receipt.get("acceleration", {})
        if accel.get("metric") != "ACCEL_INDEX_V1":
            return False
        if int(accel.get("consecutive_windows", 0)) < accel_min_windows:
            return False
        return True

    if ignition_receipt:
        trigger_idx = ignition_receipt.get("trigger_checkpoint_index")
        trigger = None
        for receipt in checkpoints_written:
            if receipt.get("checkpoint_index") == trigger_idx:
                trigger = receipt
                break
        if trigger is None:
            _fail("SCHEMA_INVALID")
        if ignition_receipt.get("baseline_id") != baseline_cfg.get("baseline_id"):
            _fail("SCHEMA_INVALID")
        if ignition_receipt.get("baseline_report_hash") != baseline_cfg.get("baseline_report_hash"):
            _fail("SCHEMA_INVALID")
        if ignition_receipt.get("trigger_checkpoint_receipt_hash") != trigger.get("receipt_hash"):
            _fail("SCHEMA_INVALID")
        # Must be first checkpoint meeting criteria
        for receipt in checkpoints_written:
            if _checkpoint_meets_criteria(receipt):
                if receipt.get("checkpoint_index") != trigger_idx:
                    _fail("SCHEMA_INVALID")
                break
        # verify proof fields
        closed_epoch_index = int(trigger.get("closed_epoch_index", -1))
        subset = _results_up_to_epoch(closed_epoch_index)
        omega_solved = {row.task_id for row in subset if row.verdict == "PASS"}
        new_solves = compute_new_solves_over_baseline(omega_solved, baseline_solved)
        gain_num, gain_den = passrate_gain(
            trigger.get("cumulative", {}).get("tasks_passed", 0),
            trigger.get("cumulative", {}).get("tasks_attempted", 0),
            baseline_passed,
            baseline_attempted,
        )
        if ignition_receipt.get("proof", {}).get("new_solves_over_baseline") != new_solves:
            _fail("CANON_HASH_MISMATCH")
        if ignition_receipt.get("proof", {}).get("passrate_gain_num") != gain_num:
            _fail("CANON_HASH_MISMATCH")
        if ignition_receipt.get("proof", {}).get("passrate_gain_den") != gain_den:
            _fail("CANON_HASH_MISMATCH")
    else:
        if any(_checkpoint_meets_criteria(receipt) for receipt in checkpoints_written):
            _fail("SCHEMA_INVALID")

    # Stop condition sanity
    if stop_idx is not None:
        stop_payload = omega_events[stop_idx].get("payload") or {}
        stop_kind = str(stop_payload.get("stop_kind", ""))

        stop_cfg = (omega_cfg.get("stop_conditions") or [])
        cfg_kind = "EXTERNAL_ONLY"
        if stop_cfg:
            cfg_kind = str((stop_cfg[0] or {}).get("kind") or "EXTERNAL_ONLY")

        if cfg_kind == "EXTERNAL_ONLY":
            if stop_kind != "EXTERNAL_SIGNAL":
                _fail("SCHEMA_INVALID")
        elif cfg_kind == "MAX_CHECKPOINTS":
            if stop_kind != "MAX_CHECKPOINTS":
                _fail("SCHEMA_INVALID")
        elif cfg_kind == "MAX_TASKS":
            if stop_kind != "MAX_TASKS":
                _fail("SCHEMA_INVALID")
        elif cfg_kind == "MAX_COMPUTE":
            if stop_kind != "MAX_COMPUTE":
                _fail("SCHEMA_INVALID")
        else:
            _fail("SCHEMA_INVALID")

        final_closed = int(stop_payload.get("final_closed_epoch_index", -1))
        if final_closed != closed_epochs[-1]["epoch_index"]:
            _fail("SCHEMA_INVALID")
        final_hash = stop_payload.get("final_checkpoint_receipt_hash")
        if final_hash != checkpoints_written[-1].get("receipt_hash"):
            _fail("SCHEMA_INVALID")
        if int(checkpoints_written[-1].get("closed_epoch_index", -1)) != final_closed:
            _fail("SCHEMA_INVALID")

    return {
        "schema": "omega_run_report_v1",
        "spec_version": "v4_0",
        "root_swarm_run_id": swarm_run_id,
        "icore_id": lock.get("core_id", ""),
        "closed_epochs": len(closed_epochs),
        "checkpoints_written": len(checkpoints_written),
        "final_checkpoint_receipt_hash": checkpoints_written[-1].get("receipt_hash", ""),
        "verdict": "VALID",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state_dir", required=True)
    args = parser.parse_args()
    try:
        receipt = verify(Path(args.state_dir))
    except CanonError as exc:
        print(f"INVALID: {exc}")
        sys.exit(1)
    print("VALID")


if __name__ == "__main__":
    main()
