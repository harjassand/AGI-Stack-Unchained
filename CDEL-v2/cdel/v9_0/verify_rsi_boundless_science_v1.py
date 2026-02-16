"""Verifier for RSI boundless science runs (v9.0)."""

from __future__ import annotations

import argparse
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from ..v1_7r.canon import CanonError, canon_bytes, load_canon_json, sha256_prefixed
from ..v2_3.immutable_core import load_lock, validate_lock
from ..v6_0.daemon_checkpoint import compute_receipt_hash, load_receipt
from ..v7_0.superego_policy import compute_policy_hash, load_policy
from .daemon_ledger import load_daemon_ledger, validate_daemon_chain
from .daemon_state import compute_daemon_id, compute_snapshot_hash, load_snapshot
from .science_attempts import load_acceptance_receipt, load_attempt_record, load_output_manifest
from .science_dataset import compute_manifest_hash as compute_dataset_manifest_hash, load_dataset_manifest
from .science_ledger import load_science_ledger, validate_science_chain
from .science_suitepack import compute_suitepack_hash, load_suitepack
from .science_toolchain import compute_manifest_hash as compute_toolchain_hash, load_toolchain_manifest


NETWORK_CAPS = {"NETWORK_NONE", "NETWORK_LOOPBACK_ONLY", "NETWORK_ANY"}


def _fail(reason: str) -> None:
    raise CanonError(reason)


def _meta_core_root() -> Path:
    env_override = Path(os.environ.get("META_CORE_ROOT", "")) if os.environ.get("META_CORE_ROOT") else None
    if env_override and env_override.exists():
        return env_override
    return Path(__file__).resolve().parents[3] / "meta-core"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def _normalize_path_for_known_repo_space_bug(raw_path: str) -> str:
    """Normalize legacy absolute paths that accidentally include '<repo_root> '."""
    candidate = str(raw_path).strip()
    repo = str(Path(__file__).resolve().parents[3])
    buggy_prefix = f"{repo} "
    if candidate.startswith(buggy_prefix):
        return f"{repo}{candidate[len(buggy_prefix):]}"
    # Historical fixtures may embed a stale absolute root before '/daemon/...'.
    marker = " /daemon/"
    marker_idx = candidate.find(marker)
    if marker_idx >= 0:
        suffix = candidate[marker_idx + len(marker) :]
        return str(Path(repo) / "daemon" / suffix)
    return candidate


def _require_constants() -> dict[str, Any]:
    meta_root = _meta_core_root()
    constants_path = meta_root / "meta_constitution" / "v9_0" / "constants_v1.json"
    return load_canon_json(constants_path)


def _meta_identities() -> dict[str, str]:
    meta_root = _meta_core_root()
    meta_hash = _read_text(meta_root / "meta_constitution" / "v9_0" / "META_HASH")
    kernel_hash = _read_text(meta_root / "kernel" / "verifier" / "KERNEL_HASH")
    constants_hash = sha256_prefixed(canon_bytes(_require_constants()))
    return {
        "META_HASH": meta_hash,
        "KERNEL_HASH": kernel_hash,
        "constants_hash": constants_hash,
    }


def _load_pack(config_dir: Path) -> dict[str, Any]:
    pack_path = config_dir / "rsi_daemon_pack_v9.json"
    if not pack_path.exists():
        _fail("MISSING_ARTIFACT")
    pack = load_canon_json(pack_path)
    if not isinstance(pack, dict) or pack.get("schema_version") != "rsi_daemon_pack_v9":
        _fail("SCHEMA_INVALID")
    for key in [
        "icore_id",
        "meta_hash",
        "daemon_id",
        "state_dir",
        "control",
        "checkpoint_policy",
        "budgets",
        "activities",
        "alignment",
        "science_boundless",
    ]:
        if key not in pack:
            _fail("SCHEMA_INVALID")
    return pack


def _require_str(obj: dict[str, Any], key: str) -> str:
    val = obj.get(key)
    if not isinstance(val, str):
        _fail("SCHEMA_INVALID")
    return val


def _validate_receipt_name(path: Path, receipt: dict[str, Any]) -> None:
    receipt_hash = compute_receipt_hash(receipt)
    name = f"sha256_{receipt_hash.split(':', 1)[1]}.{receipt.get('schema_version')}.json"
    if path.name != name:
        _fail("CANON_HASH_MISMATCH")


def _collect_snapshots(snapshot_dir: Path) -> dict[str, dict[str, Any]]:
    snapshots: dict[str, dict[str, Any]] = {}
    if not snapshot_dir.exists():
        _fail("MISSING_ARTIFACT")
    for path in snapshot_dir.glob("sha256_*.daemon_state_snapshot_v1.json"):
        snapshot = load_snapshot(path)
        snap_hash = compute_snapshot_hash(snapshot)
        expected = f"sha256_{snap_hash.split(':', 1)[1]}.daemon_state_snapshot_v1.json"
        if path.name != expected:
            _fail("CANON_HASH_MISMATCH")
        snapshots[snap_hash] = snapshot
    if not snapshots:
        _fail("MISSING_ARTIFACT")
    return snapshots


def _load_policy_from_alignment(alignment_dir: Path, *, expected_icore: str, expected_meta: str) -> tuple[dict[str, Any], str]:
    policy_path = alignment_dir / "policy" / "superego_policy_v1.json"
    policy_lock_path = alignment_dir / "policy" / "superego_policy_lock_v1.json"
    policy = load_policy(policy_path)
    policy_hash = compute_policy_hash(policy)
    if not policy_lock_path.exists():
        _fail("MISSING_ARTIFACT")
    lock = load_canon_json(policy_lock_path)
    if not isinstance(lock, dict) or lock.get("schema_version") != "superego_policy_lock_v1":
        _fail("SCHEMA_INVALID")
    if lock.get("superego_policy_hash") != policy_hash:
        _fail("POLICY_HASH_MISMATCH")
    if lock.get("icore_id") != expected_icore or lock.get("meta_hash") != expected_meta:
        _fail("META_DRIFT")
    return policy, policy_hash


def _load_env_lock(env_dir: Path) -> dict[str, str]:
    lock_path = env_dir / "SCIENCE_ENV_LOCK_HASHES.json"
    if not lock_path.exists():
        _fail("MISSING_ARTIFACT")
    payload = load_canon_json(lock_path)
    if not isinstance(payload, dict):
        _fail("SCHEMA_INVALID")
    out: dict[str, str] = {}
    for key in [
        "toolchain_manifest_hash",
        "dataset_manifest_hash",
        "analysis_code_bundle_hash",
        "dev_suitepack_hash",
        "heldout_suitepack_hash",
    ]:
        val = payload.get(key)
        if not isinstance(val, str):
            _fail("SCHEMA_INVALID")
        out[key] = val
    return out


def _check_env_drift(env_dir: Path, lock_hashes: dict[str, str]) -> dict[str, Any]:
    toolchain = load_toolchain_manifest(env_dir / "science_toolchain_manifest_v1.json")
    dataset = load_dataset_manifest(env_dir / "dataset_manifest_v1.json")
    bundle = load_canon_json(env_dir / "analysis_code_bundle_manifest_v1.json")
    dev_suitepack = load_suitepack(env_dir / "science_suitepack_dev_v1.json")
    heldout_suitepack = load_suitepack(env_dir / "science_suitepack_heldout_v1.json")

    toolchain_hash = compute_toolchain_hash(toolchain)
    dataset_hash = compute_dataset_manifest_hash(dataset)
    bundle_hash = sha256_prefixed(canon_bytes(bundle))
    dev_hash = compute_suitepack_hash(dev_suitepack)
    heldout_hash = compute_suitepack_hash(heldout_suitepack)

    if lock_hashes.get("toolchain_manifest_hash") != toolchain_hash:
        _fail("SCIENCE_ENV_DRIFT")
    if lock_hashes.get("dataset_manifest_hash") != dataset_hash:
        _fail("SCIENCE_ENV_DRIFT")
    if lock_hashes.get("analysis_code_bundle_hash") != bundle_hash:
        _fail("SCIENCE_ENV_DRIFT")
    if lock_hashes.get("dev_suitepack_hash") != dev_hash:
        _fail("SCIENCE_ENV_DRIFT")
    if lock_hashes.get("heldout_suitepack_hash") != heldout_hash:
        _fail("SCIENCE_ENV_DRIFT")

    return {
        "toolchain": toolchain,
        "dataset": dataset,
        "bundle": bundle,
        "dev_suitepack": dev_suitepack,
        "heldout_suitepack": heldout_suitepack,
        "toolchain_hash": toolchain_hash,
        "dataset_hash": dataset_hash,
        "bundle_hash": bundle_hash,
        "dev_hash": dev_hash,
        "heldout_hash": heldout_hash,
    }


def _load_active_lease(leases_dir: Path) -> dict[str, Any]:
    pointer = leases_dir / "ACTIVE_SCIENCE_LEASE_ID"
    if not pointer.exists():
        _fail("SCIENCE_LEASE_INVALID")
    lease_id = pointer.read_text(encoding="utf-8").strip()
    if not lease_id:
        _fail("SCIENCE_LEASE_INVALID")
    lease_path = leases_dir / f"lease_{lease_id}.science_lease_token_v1.json"
    if not lease_path.exists():
        _fail("SCIENCE_LEASE_INVALID")
    lease = load_canon_json(lease_path)
    if not isinstance(lease, dict) or lease.get("schema_version") != "science_lease_token_v1":
        _fail("SCIENCE_LEASE_INVALID")
    _validate_lease(lease)
    return lease


def _parse_utc(ts: str) -> datetime:
    text = ts.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)


def _validate_lease(lease: dict[str, Any]) -> None:
    for key in ["daemon_id", "icore_id", "meta_hash", "superego_policy_hash", "domains_allowed", "max_hazard_class"]:
        if key not in lease:
            _fail("SCIENCE_LEASE_INVALID")
    signatures = lease.get("operator_signatures")
    if not isinstance(signatures, list) or not signatures:
        _fail("SCIENCE_LEASE_INVALID")
    budgets = lease.get("budgets")
    if not isinstance(budgets, dict):
        _fail("SCIENCE_LEASE_INVALID")
    for key in ["max_ticks", "max_work_units", "max_artifact_bytes", "max_wall_ms"]:
        value = budgets.get(key)
        if not isinstance(value, int) or value < 1:
            _fail("SCIENCE_LEASE_INVALID")
    not_before = lease.get("not_before_utc")
    not_after = lease.get("not_after_utc")
    if not isinstance(not_before, str) or not isinstance(not_after, str):
        _fail("SCIENCE_LEASE_INVALID")
    try:
        start = _parse_utc(not_before)
        end = _parse_utc(not_after)
    except Exception:
        _fail("SCIENCE_LEASE_INVALID")
        return
    if start > end:
        _fail("SCIENCE_LEASE_INVALID")


def _has_h2_override(leases_dir: Path, *, domain: str) -> bool:
    overrides_dir = leases_dir / "overrides"
    if not overrides_dir.exists():
        return False
    for path in overrides_dir.glob("override_*.dual_key_override_v1.json"):
        override = load_canon_json(path)
        if not isinstance(override, dict):
            continue
        if override.get("schema_version") != "dual_key_override_v1":
            continue
        if override.get("hazard_class") != "H2_RESTRICTED_DUAL_USE":
            continue
        domains = override.get("domains_allowed") or []
        if domain in domains:
            return True
    return False


def _check_network_caps(capabilities: list[str]) -> None:
    net_caps = [cap for cap in capabilities if cap in NETWORK_CAPS]
    if "NETWORK_NONE" not in net_caps:
        _fail("SCIENCE_NETWORK_USED")
    if any(cap for cap in net_caps if cap != "NETWORK_NONE"):
        _fail("SCIENCE_NETWORK_USED")


def _allowed_write_prefixes(state_dir: Path) -> list[str]:
    base = state_dir / "science"
    return [
        str(base / "attempts"),
        str(base / "accepted"),
        str(base / "reports"),
        str(base / "ledger"),
    ]


def _check_write_fences(target_paths: list[str], state_dir: Path) -> None:
    allowed = _allowed_write_prefixes(state_dir)
    disallowed = [
        str(state_dir / "control"),
        str(state_dir / "science" / "env"),
        str(state_dir / "science" / "leases"),
    ]
    for raw_path in target_paths:
        path = _normalize_path_for_known_repo_space_bug(str(raw_path))
        if any(path.startswith(prefix) for prefix in disallowed):
            _fail("SCIENCE_WRITE_FENCE_VIOLATION")
        if not any(path.startswith(prefix) for prefix in allowed):
            _fail("SCIENCE_WRITE_FENCE_VIOLATION")


def _gather_task_map(suitepack: dict[str, Any]) -> dict[str, dict[str, Any]]:
    tasks: dict[str, dict[str, Any]] = {}
    for task in suitepack.get("tasks", []) or []:
        if isinstance(task, dict) and isinstance(task.get("task_id"), str):
            tasks[task["task_id"]] = task
    return tasks


def verify(state_dir: Path, *, mode: str) -> dict[str, Any]:
    state_dir = state_dir.resolve()

    constants = _require_constants()
    lock_rel = constants.get("IMMUTABLE_CORE_LOCK_REL")
    if not isinstance(lock_rel, str):
        _fail("IMMUTABLE_CORE_ATTESTATION_INVALID")

    repo_root = Path(__file__).resolve().parents[3]
    lock_path = repo_root / lock_rel
    if not lock_path.exists():
        _fail("MISSING_ARTIFACT")
    lock = load_lock(lock_path)
    try:
        validate_lock(lock)
    except Exception as exc:  # noqa: BLE001
        raise CanonError("IMMUTABLE_CORE_ATTESTATION_INVALID") from exc

    identities = _meta_identities()
    expected_icore = str(lock.get("core_id"))
    expected_meta = identities.get("META_HASH")

    daemon_root = state_dir.parent
    config_dir = daemon_root / "config"
    pack = _load_pack(config_dir)

    computed_daemon_id = compute_daemon_id(pack)
    if pack.get("daemon_id") != computed_daemon_id:
        _fail("CANON_HASH_MISMATCH")
    expected_daemon_id = pack.get("daemon_id")

    pack_state_dir = Path(_normalize_path_for_known_repo_space_bug(_require_str(pack, "state_dir"))).resolve()
    if pack_state_dir != state_dir.resolve():
        _fail("SCHEMA_INVALID")

    if pack.get("icore_id") != expected_icore or pack.get("meta_hash") != expected_meta:
        _fail("META_DRIFT")

    ledger_path = state_dir / "ledger" / "daemon_ledger_v1.jsonl"
    events = load_daemon_ledger(ledger_path)
    head_hash, _last_tick, _last_seq = validate_daemon_chain(events)
    if not events:
        _fail("MISSING_ARTIFACT")

    snapshots = _collect_snapshots(state_dir / "snapshots")

    checkpoint_dir = state_dir / "checkpoints"
    if not checkpoint_dir.exists():
        _fail("MISSING_ARTIFACT")
    for path in checkpoint_dir.glob("sha256_*.daemon_checkpoint_receipt_v1.json"):
        receipt = load_receipt(path, schema_version="daemon_checkpoint_receipt_v1", kind="CHECKPOINT")
        _validate_receipt_name(path, receipt)
        snap_hash = receipt.get("snapshot_hash")
        if snap_hash not in snapshots:
            _fail("DAEMON_CHECKPOINT_MISMATCH")

    if mode == "full":
        shutdowns = list((state_dir / "shutdowns").glob("sha256_*.daemon_shutdown_receipt_v1.json"))
        if not shutdowns:
            _fail("MISSING_ARTIFACT")

    alignment_dir = state_dir / "alignment"
    _policy, policy_hash = _load_policy_from_alignment(alignment_dir, expected_icore=expected_icore, expected_meta=expected_meta)

    # Env lock + manifests
    env_dir = state_dir / "science" / "env"
    lock_hashes = _load_env_lock(env_dir)
    env = _check_env_drift(env_dir, lock_hashes)

    # Lease
    lease = _load_active_lease(state_dir / "science" / "leases")
    if lease.get("daemon_id") != expected_daemon_id:
        _fail("SCIENCE_LEASE_INVALID")
    if lease.get("icore_id") != expected_icore or lease.get("meta_hash") != expected_meta:
        _fail("SCIENCE_LEASE_INVALID")
    if lease.get("superego_policy_hash") != policy_hash:
        _fail("SCIENCE_LEASE_INVALID")

    lease_budgets = lease.get("budgets") or {}
    allowed_domains = set(lease.get("domains_allowed") or [])
    max_hazard = str(lease.get("max_hazard_class"))

    allow_vectors = set(constants.get("SCIENCE_VECTOR_ALLOWLIST") or [])

    # Build task maps
    dev_tasks = _gather_task_map(env["dev_suitepack"])
    heldout_tasks = _gather_task_map(env["heldout_suitepack"])

    # Track enable flags per tick
    enable_by_tick: dict[int, dict[str, bool]] = {}
    decisions_by_tick: dict[int, dict[str, tuple[str, str]]] = {}

    for ev in events:
        tick = int(ev.get("tick", 0))
        enable = enable_by_tick.setdefault(tick, {})
        if ev.get("event_type") == "ENABLE_RESEARCH_PRESENT":
            enable["research"] = True
        if ev.get("event_type") == "ENABLE_BOUNDLESS_SCIENCE_PRESENT":
            enable["boundless"] = True
        if ev.get("event_type") == "ENABLE_SCIENCE_PHYSICS_PRESENT":
            enable["physics"] = True
        if ev.get("event_type") == "ENABLE_SCIENCE_CHEMISTRY_PRESENT":
            enable["chemistry"] = True
        if ev.get("event_type") == "ENABLE_SCIENCE_BIOLOGY_PRESENT":
            enable["biology"] = True
        if ev.get("event_type") == "SUPEREGO_DECISION":
            payload = ev.get("event_payload") or {}
            req_id = payload.get("request_id")
            decision = payload.get("decision")
            policy_hash = payload.get("policy_hash")
            if isinstance(req_id, str) and isinstance(decision, str) and isinstance(policy_hash, str):
                decisions_by_tick.setdefault(tick, {})[req_id] = (decision, policy_hash)

    # Science ledger chain
    sci_ledger_path = state_dir / "science" / "ledger" / "science_ledger_v1.jsonl"
    sci_events = load_science_ledger(sci_ledger_path)
    validate_science_chain(sci_events)

    # Attempt validation
    attempts_root = state_dir / "science" / "attempts"
    acceptance_root = state_dir / "science" / "accepted" / "receipts"
    acceptance_root.mkdir(parents=True, exist_ok=True)

    sealed_receipts: dict[str, dict[str, Any]] = {}
    attempt_count = 0
    attempts_by_tick: dict[int, int] = {}
    for task_id, task in dev_tasks.items():
        task_dir = attempts_root / task_id
        if not task_dir.exists():
            continue
        for attempt_dir in task_dir.iterdir():
            if not attempt_dir.is_dir():
                continue
            record_path = attempt_dir / "attempt_record_v1.json"
            if not record_path.exists():
                continue
            record = load_attempt_record(record_path)
            attempt_count += 1
            tick = int(record.get("tick", 0))
            max_ticks = int(lease_budgets.get("max_ticks", 0))
            if max_ticks and tick > max_ticks:
                _fail("SCIENCE_LEASE_INVALID")
            attempts_by_tick[tick] = attempts_by_tick.get(tick, 0) + 1
            req_id = str(record.get("superego_request_id"))
            decision_entry = decisions_by_tick.get(tick, {}).get(req_id)
            if not decision_entry:
                _fail("SCIENCE_SUPEREGO_DECISION_MISSING")
            decision, decision_policy_hash = decision_entry
            if decision != "ALLOW":
                _fail("SCIENCE_SUPEREGO_DECISION_MISSING")
            if decision_policy_hash != policy_hash:
                _fail("SCIENCE_SUPEREGO_DECISION_MISSING")

            enable = enable_by_tick.get(tick, {})
            if not enable.get("research") or not enable.get("boundless"):
                _fail("SCIENCE_ENABLE_MISSING")

            domain = str(record.get("domain"))
            if domain == "PHYSICS" and not enable.get("physics"):
                _fail("SCIENCE_ENABLE_MISSING")
            if domain == "CHEMISTRY" and not enable.get("chemistry"):
                _fail("SCIENCE_ENABLE_MISSING")
            if domain == "BIOLOGY" and not enable.get("biology"):
                _fail("SCIENCE_ENABLE_MISSING")

            if domain not in allowed_domains:
                _fail("SCIENCE_LEASE_INVALID")

            hazard = str(record.get("hazard_class"))
            if hazard == "H3_PROHIBITED":
                _fail("SCIENCE_HAZARD_VIOLATION")
            if hazard == "H2_RESTRICTED_DUAL_USE":
                if not _has_h2_override(state_dir / "science" / "leases", domain=domain):
                    _fail("SCIENCE_HAZARD_VIOLATION")
            if max_hazard == "H0_BENIGN" and hazard != "H0_BENIGN":
                _fail("SCIENCE_HAZARD_VIOLATION")
            if max_hazard == "H1_LOW_RISK" and hazard not in {"H0_BENIGN", "H1_LOW_RISK"}:
                _fail("SCIENCE_HAZARD_VIOLATION")

            vector = str(record.get("vector"))
            if vector not in allow_vectors:
                _fail("SCIENCE_VECTOR_VIOLATION")

            _check_network_caps(list(record.get("capabilities") or []))
            _check_write_fences(list(record.get("target_paths") or []), state_dir)

            # Sealed receipts (dev + optional heldout)
            sealed_dir = attempt_dir / "sealed"
            sealed_files = list(sealed_dir.glob("sha256_*.sealed_science_eval_receipt_v1.json"))
            if not sealed_files:
                _fail("UNKNOWN_FATAL")

            dev_receipt: dict[str, Any] | None = None
            for sealed_path in sealed_files:
                sealed = load_canon_json(sealed_path)
                if not isinstance(sealed, dict) or sealed.get("schema_version") != "sealed_science_eval_receipt_v1":
                    _fail("SCHEMA_INVALID")
                sealed_hash = sha256_prefixed(canon_bytes(sealed))
                expected_name = f"sha256_{sealed_hash.split(':',1)[1]}.sealed_science_eval_receipt_v1.json"
                if sealed_path.name != expected_name:
                    _fail("CANON_HASH_MISMATCH")
                sealed_receipts[sealed_hash] = sealed
                max_wall_ms = int(lease_budgets.get("max_wall_ms", 0))
                if max_wall_ms and int(sealed.get("time_ms", 0)) > max_wall_ms:
                    _fail("SCIENCE_LEASE_INVALID")
                suitepack_hash = sealed.get("suitepack_hash")
                if suitepack_hash not in {env["dev_hash"], env["heldout_hash"]}:
                    _fail("SCIENCE_ENV_DRIFT")
                if suitepack_hash == env["dev_hash"]:
                    dev_receipt = sealed

            if dev_receipt is None:
                _fail("SCIENCE_ENV_DRIFT")
            if dev_receipt.get("network_used") is not False:
                _fail("SCIENCE_NETWORK_USED")
            if dev_receipt.get("toolchain_manifest_hash") != env["toolchain_hash"]:
                _fail("SCIENCE_ENV_DRIFT")
            if dev_receipt.get("dataset_manifest_hash") != env["dataset_hash"]:
                _fail("SCIENCE_ENV_DRIFT")
            if dev_receipt.get("attempt_id") != record.get("attempt_id"):
                _fail("UNKNOWN_FATAL")
            if dev_receipt.get("task_id") != record.get("task_id"):
                _fail("UNKNOWN_FATAL")

            # Output manifest
            output_manifest = load_output_manifest(attempt_dir / "outputs" / "output_manifest_v1.json")
            artifacts = output_manifest.get("artifacts") or []
            max_bytes = int(task.get("output_constraints", {}).get("max_bytes", 0))
            allow_kinds = set(task.get("output_constraints", {}).get("allow_kinds", []))
            for artifact in artifacts:
                if not isinstance(artifact, dict):
                    _fail("SCHEMA_INVALID")
                kind = artifact.get("kind")
                if kind not in allow_kinds:
                    _fail("SCIENCE_WRITE_FENCE_VIOLATION")
                size = int(artifact.get("bytes", 0))
                if max_bytes and size > max_bytes:
                    _fail("SCIENCE_WRITE_FENCE_VIOLATION")
            lease_max_bytes = int(lease_budgets.get("max_artifact_bytes", 0))
            if lease_max_bytes:
                total_bytes = sum(int(a.get("bytes", 0)) for a in artifacts)
                if total_bytes > lease_max_bytes:
                    _fail("SCIENCE_LEASE_INVALID")

    max_per_tick = int((pack.get("science_boundless") or {}).get("attempts_per_tick_max", 1))
    for _tick, count in attempts_by_tick.items():
        if count > max_per_tick:
            _fail("SCIENCE_LEASE_INVALID")
    daily_budget = int((pack.get("science_boundless") or {}).get("daily_attempt_budget", 0))
    if daily_budget:
        for snapshot in snapshots.values():
            counters = snapshot.get("budget_counters") or {}
            attempts_today = int(counters.get("science_attempts_today", 0))
            if attempts_today > daily_budget:
                _fail("SCIENCE_LEASE_INVALID")

    # Acceptance receipts
    for path in acceptance_root.glob("sha256_*.acceptance_receipt_v1.json"):
        receipt = load_acceptance_receipt(path)
        rec_hash = sha256_prefixed(canon_bytes(receipt))
        expected = f"sha256_{rec_hash.split(':',1)[1]}.acceptance_receipt_v1.json"
        if path.name != expected:
            _fail("CANON_HASH_MISMATCH")
        task_id = str(receipt.get("task_id"))
        if task_id not in heldout_tasks:
            _fail("SCIENCE_ACCEPTANCE_WITHOUT_HELDOUT")
        task = heldout_tasks[task_id]
        threshold = task.get("acceptance_threshold") or {}
        threshold_num = int(threshold.get("num", 0))
        threshold_den = int(threshold.get("den", 1))
        metric_num = int(receipt.get("metric_num", 0))
        metric_den = int(receipt.get("metric_den", 1))
        if metric_num * threshold_den < threshold_num * metric_den:
            _fail("SCIENCE_ACCEPTANCE_WITHOUT_HELDOUT")
        replicas = list(receipt.get("heldout_receipt_hashes") or [])
        required = 5 if task.get("stochastic") else 2
        if len(replicas) < required:
            _fail("SCIENCE_ACCEPTANCE_WITHOUT_REPLICATION")
        if int(receipt.get("replication_count", len(replicas))) != len(replicas):
            _fail("SCIENCE_ACCEPTANCE_WITHOUT_REPLICATION")
        for rep_hash in replicas:
            sealed = sealed_receipts.get(rep_hash)
            if sealed is None:
                _fail("SCIENCE_ACCEPTANCE_WITHOUT_HELDOUT")
            if sealed.get("suitepack_hash") != env["heldout_hash"]:
                _fail("SCIENCE_ACCEPTANCE_WITHOUT_HELDOUT")
            if int(sealed.get("metric_num", 0)) != metric_num or int(sealed.get("metric_den", 1)) != metric_den:
                _fail("SCIENCE_ACCEPTANCE_WITHOUT_HELDOUT")

    if attempt_count == 0:
        # zero-attempt runs are valid if ledger is intact
        return {"status": "VALID", "attempts": 0}

    return {"status": "VALID", "attempts": attempt_count, "ledger_head": head_hash}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--daemon_state_dir", required=True)
    parser.add_argument("--mode", choices=["prefix", "full"], default="prefix")
    args = parser.parse_args()
    try:
        result = verify(Path(args.daemon_state_dir), mode=args.mode)
    except CanonError as exc:
        print(f"INVALID: {exc}")
        raise SystemExit(2) from exc
    print("VALID")
    if result:
        for key, value in result.items():
            if key == "status":
                continue
            print(f"{key}: {value}")


if __name__ == "__main__":
    main()
