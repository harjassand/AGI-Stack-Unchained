"""Superego policy parsing + deterministic evaluation (v7.0)."""

from __future__ import annotations

import hashlib
from typing import Any, Iterable

from ..v1_7r.canon import CanonError, canon_bytes, load_canon_json, sha256_prefixed

CAPABILITIES = {
    "FS_READ_WORKSPACE",
    "FS_WRITE_RUNS_NEW",
    "FS_WRITE_DAEMON_STATE",
    "FS_WRITE_STAGE",
    "SUBPROCESS_PYTHON",
    "SUBPROCESS_TOOLCHAIN",
    "NETWORK_NONE",
    "NETWORK_LOOPBACK_ONLY",
    "NETWORK_ANY",
    "SEALEDEXEC",
    "PROMOTION_SUBMIT",
    "THERMO_IMPORT_ONLY",
    "SEALED_RUN_REQUIRED",
    "FS_WRITE_SCIENCE_ONLY",
    "SUBPROCESS_TRAINER",
}

OBJECTIVE_CLASSES = {
    "MAINTENANCE",
    "VALIDATION",
    "IMPROVEMENT_BOUNDED",
    "RESEARCH_BOUNDED",
    "BOUNDLESS_RESEARCH",
    "BOUNDLESS_SCIENCE",
    "MODEL_GENESIS",
}


class SuperegoError(CanonError):
    pass


def _fail(reason: str) -> None:
    raise SuperegoError(reason)


def load_policy(path) -> dict[str, Any]:
    policy = load_canon_json(path)
    if not isinstance(policy, dict):
        _fail("SCHEMA_INVALID")
    if policy.get("schema_version") != "superego_policy_v1":
        _fail("SCHEMA_INVALID")
    return policy


def compute_policy_hash(policy: dict[str, Any]) -> str:
    return sha256_prefixed(canon_bytes(policy))


def compute_request_id(request: dict[str, Any]) -> str:
    payload = dict(request)
    payload.pop("request_id", None)
    data = b"superego_request_v1" + canon_bytes(payload)
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _require_str(obj: dict[str, Any], key: str) -> str:
    val = obj.get(key)
    if not isinstance(val, str):
        _fail("SCHEMA_INVALID")
    return val


def _require_int(obj: dict[str, Any], key: str) -> int:
    val = obj.get(key)
    if not isinstance(val, int):
        _fail("SCHEMA_INVALID")
    return val


def _require_bool(obj: dict[str, Any], key: str) -> bool:
    val = obj.get(key)
    if not isinstance(val, bool):
        _fail("SCHEMA_INVALID")
    return val


def _require_list(obj: dict[str, Any], key: str) -> list[Any]:
    val = obj.get(key)
    if not isinstance(val, list):
        _fail("SCHEMA_INVALID")
    return val


def _validate_capabilities(caps: Iterable[Any]) -> list[str]:
    out: list[str] = []
    for cap in caps:
        if not isinstance(cap, str) or cap not in CAPABILITIES:
            _fail("SCHEMA_INVALID")
        out.append(cap)
    return out


def validate_request(request: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(request, dict):
        _fail("SCHEMA_INVALID")
    if request.get("schema_version") != "superego_action_request_v1":
        _fail("SCHEMA_INVALID")
    _require_str(request, "request_id")
    _require_str(request, "daemon_id")
    tick = _require_int(request, "tick")
    if tick < 0:
        _fail("SCHEMA_INVALID")
    objective_class = _require_str(request, "objective_class")
    if objective_class not in OBJECTIVE_CLASSES:
        _fail("SCHEMA_INVALID")
    objective_text = _require_str(request, "objective_text")
    if len(objective_text) > 512:
        _fail("SCHEMA_INVALID")
    caps = _validate_capabilities(_require_list(request, "capabilities"))
    target_paths = _require_list(request, "target_paths")
    for path in target_paths:
        if not isinstance(path, str) or not path.startswith("/"):
            _fail("SCHEMA_INVALID")
    if "inputs" in request:
        _require_list(request, "inputs")
    if "outputs_planned" in request:
        _require_list(request, "outputs_planned")
    _require_bool(request, "sealed_eval_required")
    science = request.get("science")
    if objective_class == "BOUNDLESS_SCIENCE":
        if not isinstance(science, dict):
            _fail("SCHEMA_INVALID")
        _require_str(science, "domain")
        _require_str(science, "vector")
        _require_str(science, "hazard_class")
        _require_str(science, "task_id")
    elif science is not None and not isinstance(science, dict):
        _fail("SCHEMA_INVALID")

    model_genesis = request.get("model_genesis")
    if objective_class == "MODEL_GENESIS":
        if not isinstance(model_genesis, dict):
            _fail("SCHEMA_INVALID")
        _require_str(model_genesis, "stage")
        _require_str(model_genesis, "lease_id")
        if "heldout_ids" in model_genesis and not isinstance(model_genesis.get("heldout_ids"), list):
            _fail("SCHEMA_INVALID")
    elif model_genesis is not None and not isinstance(model_genesis, dict):
        _fail("SCHEMA_INVALID")

    payload = {
        "objective_class": objective_class,
        "capabilities": caps,
        "target_paths": [str(p) for p in target_paths],
        "sealed_eval_required": bool(request.get("sealed_eval_required")),
    }
    if isinstance(science, dict):
        payload["science"] = dict(science)
    if isinstance(model_genesis, dict):
        payload["model_genesis"] = dict(model_genesis)
    return payload


def _deny_capability_present(capabilities: list[str], predicate: dict[str, Any]) -> bool:
    cap = predicate.get("cap")
    return isinstance(cap, str) and cap in capabilities


def _deny_objective_is(objective_class: str, predicate: dict[str, Any]) -> bool:
    target = predicate.get("objective")
    return isinstance(target, str) and target == objective_class


def _deny_path_prefix_not_allowed(paths: list[str], predicate: dict[str, Any]) -> bool:
    prefix = predicate.get("prefix")
    if not isinstance(prefix, str):
        return False
    return any(not path.startswith(prefix) for path in paths)


def _deny_requires_sealed_eval(request: dict[str, Any], capabilities: list[str], predicate: dict[str, Any]) -> bool:
    value = predicate.get("value")
    but_missing = predicate.get("but_missing")
    if value is True and but_missing is True:
        if bool(request.get("sealed_eval_required")) and "SEALEDEXEC" not in capabilities:
            return True
    return False


def _deny_vector_not_allowlisted(request: dict[str, Any], predicate: dict[str, Any]) -> bool:
    allowlist = predicate.get("allowlist")
    if not isinstance(allowlist, list):
        return False
    vector = None
    science = request.get("science")
    if isinstance(science, dict):
        vector = science.get("vector")
    if not isinstance(vector, str):
        return True
    return vector not in allowlist


def _deny_lease_missing(request: dict[str, Any], predicate: dict[str, Any]) -> bool:
    model = request.get("model_genesis")
    if not isinstance(model, dict):
        return False
    lease_id = model.get("lease_id")
    return not isinstance(lease_id, str) or lease_id.strip() == ""


def _deny_heldout_read_in_train(request: dict[str, Any], predicate: dict[str, Any]) -> bool:
    model = request.get("model_genesis")
    if not isinstance(model, dict):
        return False
    stage = model.get("stage")
    deny_stage = predicate.get("deny_stage") or "TRAIN"
    if stage != deny_stage:
        return False
    heldout_ids = model.get("heldout_ids") or []
    if not isinstance(heldout_ids, list):
        return True
    return len(heldout_ids) > 0


def _predicate_triggers(
    predicate: dict[str, Any], *, request: dict[str, Any], capabilities: list[str], objective_class: str, paths: list[str]
) -> bool:
    kind = predicate.get("kind")
    if kind == "capability_present":
        return _deny_capability_present(capabilities, predicate)
    if kind == "objective_is":
        return _deny_objective_is(objective_class, predicate)
    if kind == "path_prefix_not_allowed":
        return _deny_path_prefix_not_allowed(paths, predicate)
    if kind == "requires_sealed_eval":
        return _deny_requires_sealed_eval(request, capabilities, predicate)
    if kind == "vector_not_allowlisted":
        return _deny_vector_not_allowlisted(request, predicate)
    if kind == "lease_missing":
        return _deny_lease_missing(request, predicate)
    if kind == "heldout_read_in_train":
        return _deny_heldout_read_in_train(request, predicate)
    return False


def evaluate_policy(
    policy: dict[str, Any], request: dict[str, Any], *, state_snapshot: dict[str, Any] | None = None
) -> tuple[str, str]:
    """Return (decision, reason_code)."""
    _ = state_snapshot  # deterministic input reserved for future use

    validated = validate_request(request)
    objective_class = validated["objective_class"]
    capabilities = validated["capabilities"]
    target_paths = validated["target_paths"]

    if policy.get("schema_version") != "superego_policy_v1":
        _fail("SCHEMA_INVALID")

    # Global denies first.
    for predicate in policy.get("global_denies", []) or []:
        if isinstance(predicate, dict) and _predicate_triggers(
            predicate, request=request, capabilities=capabilities, objective_class=objective_class, paths=target_paths
        ):
            return "DENY", "GLOBAL_DENY"

    rules = policy.get("objective_rules") or []
    if not isinstance(rules, list):
        _fail("SCHEMA_INVALID")

    for rule in rules:
        if not isinstance(rule, dict):
            continue
        if rule.get("objective_class") != objective_class:
            continue

        allowed_caps = rule.get("allowed_capabilities") or []
        if not isinstance(allowed_caps, list):
            _fail("SCHEMA_INVALID")
        allowed_caps = _validate_capabilities(allowed_caps)

        required_caps = rule.get("required_capabilities") or []
        if required_caps:
            if not isinstance(required_caps, list):
                _fail("SCHEMA_INVALID")
            required_caps = _validate_capabilities(required_caps)
            for cap in required_caps:
                if cap not in capabilities:
                    return "DENY", "REQUIRED_CAPABILITY_MISSING"

        for cap in capabilities:
            if cap not in allowed_caps:
                return "DENY", "FORBIDDEN_CAPABILITY"

        for predicate in rule.get("deny_if", []) or []:
            if isinstance(predicate, dict) and _predicate_triggers(
                predicate, request=request, capabilities=capabilities, objective_class=objective_class, paths=target_paths
            ):
                return "DENY", "RULE_DENY"

        return "ALLOW", "ALLOW"

    default = policy.get("default_decision")
    if default == "ALLOW":
        return "ALLOW", "DEFAULT_ALLOW"
    return "DENY", "DEFAULT_DENY"


def compute_decision_hash(payload: dict[str, Any]) -> str:
    return sha256_prefixed(canon_bytes(payload))


__all__ = [
    "CAPABILITIES",
    "OBJECTIVE_CLASSES",
    "SuperegoError",
    "compute_decision_hash",
    "compute_policy_hash",
    "compute_request_id",
    "evaluate_policy",
    "load_policy",
    "validate_request",
]
