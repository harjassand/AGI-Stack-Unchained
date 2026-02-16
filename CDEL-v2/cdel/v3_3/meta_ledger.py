"""Meta-ledger helpers for v3.3."""

from __future__ import annotations

from typing import Any, Callable

from ..v1_7r.canon import CanonError, canon_bytes, sha256_prefixed


def _strip(payload: dict[str, Any], keys: set[str]) -> dict[str, Any]:
    out = dict(payload)
    for key in keys:
        out.pop(key, None)
    return out


def compute_update_id(update: dict[str, Any]) -> str:
    body = _strip(update, {"update_id", "update_hash"})
    return sha256_prefixed(canon_bytes(body))


def compute_assertion_id(assertion: dict[str, Any]) -> str:
    body = _strip(assertion, {"assertion_id"})
    return sha256_prefixed(canon_bytes(body))


def compute_meta_block_id(block: dict[str, Any]) -> str:
    body = _strip(block, {"meta_block_id", "meta_block_hash"})
    return sha256_prefixed(canon_bytes(body))


def compute_meta_state_hash(state: dict[str, Any]) -> str:
    body = _strip(state, {"state_hash"})
    return sha256_prefixed(canon_bytes(body))


def compute_meta_policy_hash(policy: dict[str, Any]) -> str:
    body = _strip(policy, {"policy_hash"})
    return sha256_prefixed(canon_bytes(body))


def build_meta_state(
    *,
    root_swarm_run_id: str,
    icore_id: str,
    meta_epoch_index: int,
    prev_meta_state_hash: str,
    assertions: list[dict[str, Any]],
) -> dict[str, Any]:
    sorted_assertions = sorted(assertions, key=lambda row: row.get("assertion_id", ""))
    state = {
        "schema": "meta_state_v1",
        "spec_version": "v3_3",
        "root_swarm_run_id": root_swarm_run_id,
        "icore_id": icore_id,
        "meta_epoch_index": int(meta_epoch_index),
        "prev_meta_state_hash": prev_meta_state_hash,
        "knowledge_graph": {"assertions": sorted_assertions},
        "state_hash": "__SELF__",
    }
    state["state_hash"] = compute_meta_state_hash(state)
    return state


def build_meta_policy(
    *,
    root_swarm_run_id: str,
    icore_id: str,
    meta_epoch_index: int,
    prev_meta_policy_hash: str,
    subscriptions_add: list[str],
    priorities: list[dict[str, Any]],
) -> dict[str, Any]:
    subs_sorted = sorted(set(subscriptions_add))
    priorities_sorted = sorted(priorities, key=lambda row: row.get("topic", ""))
    policy = {
        "schema": "meta_policy_v1",
        "spec_version": "v3_3",
        "root_swarm_run_id": root_swarm_run_id,
        "icore_id": icore_id,
        "meta_epoch_index": int(meta_epoch_index),
        "prev_meta_policy_hash": prev_meta_policy_hash,
        "policy": {
            "bridge": {"subscriptions_add": subs_sorted},
            "task": {"priority": priorities_sorted},
        },
        "policy_hash": "__SELF__",
    }
    policy["policy_hash"] = compute_meta_policy_hash(policy)
    return policy


def build_meta_block(
    *,
    root_swarm_run_id: str,
    icore_id: str,
    meta_epoch_index: int,
    prev_meta_block_id: str,
    accepted_update_ids: list[str],
    rejected_updates: list[dict[str, Any]],
    meta_state_hash: str,
    meta_state_path: str,
    meta_policy_hash: str,
    meta_policy_path: str,
    stats: dict[str, Any],
) -> dict[str, Any]:
    block = {
        "schema": "meta_block_v1",
        "spec_version": "v3_3",
        "meta_block_id": "__SELF__",
        "meta_block_hash": "__SELF__",
        "root_swarm_run_id": root_swarm_run_id,
        "icore_id": icore_id,
        "meta_epoch_index": int(meta_epoch_index),
        "prev_meta_block_id": prev_meta_block_id,
        "accepted_update_ids": accepted_update_ids,
        "rejected_updates": rejected_updates,
        "meta_state_hash": meta_state_hash,
        "meta_state_path": meta_state_path,
        "meta_policy_hash": meta_policy_hash,
        "meta_policy_path": meta_policy_path,
        "stats": stats,
    }
    block_id = compute_meta_block_id(block)
    block["meta_block_id"] = block_id
    block["meta_block_hash"] = block_id
    return block


def apply_meta_updates(
    *,
    root_swarm_run_id: str,
    icore_id: str,
    meta_epoch_index: int,
    prev_state: dict[str, Any],
    prev_policy: dict[str, Any],
    updates: list[dict[str, Any]],
    knowledge_limits: dict[str, Any],
    policy_limits: dict[str, Any],
    allowed_update_kinds: set[str],
    max_updates_apply: int,
    evidence_validator: Callable[[dict[str, Any]], bool] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], list[str], list[dict[str, Any]], dict[str, Any]]:
    """Apply updates (sorted by update_id) and return new state/policy + stats."""
    assertions = list(prev_state.get("knowledge_graph", {}).get("assertions", []) or [])
    subs_add = list(prev_policy.get("policy", {}).get("bridge", {}).get("subscriptions_add", []) or [])
    priorities = list(prev_policy.get("policy", {}).get("task", {}).get("priority", []) or [])
    priorities_by_topic = {row.get("topic"): row.get("priority") for row in priorities if isinstance(row, dict)}

    max_assertions_per_update = int(knowledge_limits.get("max_assertions_per_update", 0))
    max_total_assertions = int(knowledge_limits.get("max_total_assertions", 0))
    max_evidence_refs = int(knowledge_limits.get("max_evidence_refs_per_assertion", 0))

    allowed_policy_keys = set(policy_limits.get("allowed_keys") or [])
    max_subs_total = int(policy_limits.get("max_subscriptions_add_total", 0))
    max_priority_topics = int(policy_limits.get("max_priority_topics", 0))
    priority_min = int(policy_limits.get("priority_min", 0))
    priority_max = int(policy_limits.get("priority_max", 0))

    accepted: list[str] = []
    rejected: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    updates_sorted = sorted(updates, key=lambda row: row.get("update_id", ""))
    for update in updates_sorted:
        update_id = update.get("update_id")
        if not isinstance(update_id, str):
            rejected.append({"update_id": "", "reason": "SCHEMA_INVALID"})
            continue
        if update_id in seen_ids:
            rejected.append({"update_id": update_id, "reason": "DUPLICATE"})
            continue
        seen_ids.add(update_id)

        if max_updates_apply and len(accepted) >= max_updates_apply:
            rejected.append({"update_id": update_id, "reason": "CAPACITY_EXCEEDED"})
            continue

        update_kind = update.get("update_kind")
        if update_kind not in allowed_update_kinds:
            rejected.append({"update_id": update_id, "reason": "KIND_NOT_ALLOWED"})
            continue

        payload = update.get("payload") if isinstance(update.get("payload"), dict) else None
        if payload is None:
            rejected.append({"update_id": update_id, "reason": "SCHEMA_INVALID"})
            continue

        if update_kind == "KNOWLEDGE_ASSERTION_ADD_V1":
            assertions_in = payload.get("assertions") if isinstance(payload.get("assertions"), list) else None
            if assertions_in is None:
                rejected.append({"update_id": update_id, "reason": "SCHEMA_INVALID"})
                continue
            if max_assertions_per_update and len(assertions_in) > max_assertions_per_update:
                rejected.append({"update_id": update_id, "reason": "CAPACITY_EXCEEDED"})
                continue

            valid = True
            evidence_missing = False
            new_assertions: list[dict[str, Any]] = []
            for assertion in assertions_in:
                if not isinstance(assertion, dict):
                    valid = False
                    break
                assertion_id = assertion.get("assertion_id")
                if not isinstance(assertion_id, str) or not assertion_id.startswith("sha256:"):
                    valid = False
                    break
                expected_id = compute_assertion_id(assertion)
                if expected_id != assertion_id:
                    valid = False
                    break
                conf_num = assertion.get("confidence_num")
                conf_den = assertion.get("confidence_den")
                if not isinstance(conf_num, int) or not isinstance(conf_den, int):
                    valid = False
                    break
                if conf_num < 0 or conf_den < 1 or conf_den > 100 or conf_num > conf_den:
                    valid = False
                    break
                evidence_refs = assertion.get("evidence_refs") if isinstance(assertion.get("evidence_refs"), list) else None
                if evidence_refs is None:
                    valid = False
                    break
                if max_evidence_refs and len(evidence_refs) > max_evidence_refs:
                    valid = False
                    break
                if evidence_validator is not None:
                    for ref in evidence_refs:
                        if not isinstance(ref, dict) or not evidence_validator(ref):
                            valid = False
                            evidence_missing = True
                            break
                if not valid:
                    break
                new_assertions.append(assertion)

            if not valid:
                rejected.append({
                    "update_id": update_id,
                    "reason": "EVIDENCE_MISSING" if evidence_missing else "SCHEMA_INVALID",
                })
                continue

            if max_total_assertions and (len(assertions) + len(new_assertions)) > max_total_assertions:
                rejected.append({"update_id": update_id, "reason": "CAPACITY_EXCEEDED"})
                continue

            existing_ids = {row.get("assertion_id") for row in assertions if isinstance(row, dict)}
            for assertion in new_assertions:
                if assertion.get("assertion_id") in existing_ids:
                    continue
                assertions.append(assertion)
                existing_ids.add(assertion.get("assertion_id"))

            accepted.append(update_id)
            continue

        if update_kind == "POLICY_PATCH_V1":
            policy_delta = payload.get("policy_delta") if isinstance(payload.get("policy_delta"), dict) else None
            if policy_delta is None:
                rejected.append({"update_id": update_id, "reason": "SCHEMA_INVALID"})
                continue
            for key in policy_delta.keys():
                if key not in allowed_policy_keys:
                    raise CanonError("META_POLICY_OUT_OF_BOUNDS")

            subs_delta = policy_delta.get("bridge.subscriptions_add")
            if subs_delta is not None and not isinstance(subs_delta, list):
                raise CanonError("META_POLICY_OUT_OF_BOUNDS")
            if subs_delta is not None:
                subs_add.extend([s for s in subs_delta if isinstance(s, str)])

            priority_delta = policy_delta.get("task.priority_boost")
            if priority_delta is not None and not isinstance(priority_delta, list):
                raise CanonError("META_POLICY_OUT_OF_BOUNDS")
            if priority_delta is not None:
                for item in priority_delta:
                    if not isinstance(item, dict):
                        raise CanonError("META_POLICY_OUT_OF_BOUNDS")
                    topic = item.get("topic")
                    priority = item.get("priority")
                    if not isinstance(topic, str) or not isinstance(priority, int):
                        raise CanonError("META_POLICY_OUT_OF_BOUNDS")
                    if priority < priority_min or priority > priority_max:
                        raise CanonError("META_POLICY_OUT_OF_BOUNDS")
                    prev_val = priorities_by_topic.get(topic)
                    if prev_val is None or priority > prev_val:
                        priorities_by_topic[topic] = priority

            subs_add = sorted(set(subs_add))
            if max_subs_total and len(subs_add) > max_subs_total:
                rejected.append({"update_id": update_id, "reason": "CAPACITY_EXCEEDED"})
                continue

            if max_priority_topics and len(priorities_by_topic) > max_priority_topics:
                rejected.append({"update_id": update_id, "reason": "CAPACITY_EXCEEDED"})
                continue

            accepted.append(update_id)
            continue

        rejected.append({"update_id": update_id, "reason": "SCHEMA_INVALID"})

    priorities_out = [
        {"topic": topic, "priority": priorities_by_topic[topic]}
        for topic in sorted(priorities_by_topic.keys())
    ]

    new_state = build_meta_state(
        root_swarm_run_id=root_swarm_run_id,
        icore_id=icore_id,
        meta_epoch_index=meta_epoch_index,
        prev_meta_state_hash=prev_state.get("state_hash", "GENESIS"),
        assertions=assertions,
    )
    new_policy = build_meta_policy(
        root_swarm_run_id=root_swarm_run_id,
        icore_id=icore_id,
        meta_epoch_index=meta_epoch_index,
        prev_meta_policy_hash=prev_policy.get("policy_hash", "GENESIS"),
        subscriptions_add=subs_add,
        priorities=priorities_out,
    )

    stats = {
        "candidate_updates": len(updates_sorted),
        "accepted_updates": len(accepted),
        "rejected_updates": len(rejected),
        "total_assertions": len(new_state.get("knowledge_graph", {}).get("assertions", []) or []),
        "total_subscriptions_add": len(new_policy.get("policy", {}).get("bridge", {}).get("subscriptions_add", []) or []),
    }

    rejected_sorted = sorted(rejected, key=lambda row: (row.get("update_id", ""), row.get("reason", "")))
    accepted_sorted = sorted(accepted)
    return new_state, new_policy, accepted_sorted, rejected_sorted, stats


__all__ = [
    "build_meta_block",
    "build_meta_policy",
    "build_meta_state",
    "apply_meta_updates",
    "compute_assertion_id",
    "compute_meta_block_id",
    "compute_meta_policy_hash",
    "compute_meta_state_hash",
    "compute_update_id",
]
