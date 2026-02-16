from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from cdel.v1_7r.canon import canon_bytes, load_canon_json, write_canon_json, write_jsonl_line
from cdel.v6_0.daemon_checkpoint import compute_receipt_hash
from cdel.v7_0.superego_ledger import compute_entry_hash as compute_superego_entry_hash
from cdel.v7_0.superego_policy import compute_decision_hash, compute_policy_hash, compute_request_id
from cdel.v9_0.daemon_ledger import compute_entry_hash as compute_daemon_entry_hash
from cdel.v9_0.daemon_state import compute_daemon_id, compute_snapshot_hash
from cdel.v9_0.science_attempts import compute_acceptance_hash, compute_attempt_id
from cdel.v9_0.science_ledger import compute_entry_hash as compute_science_entry_hash
from cdel.v9_0.science_suitepack import compute_suitepack_hash, compute_task_id
from cdel.v9_0.science_toolchain import compute_manifest_hash as compute_toolchain_hash, compute_toolchain_id
from cdel.v9_0.science_dataset import compute_manifest_hash as compute_dataset_manifest_hash


def repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def identities() -> tuple[str, str]:
    root = repo_root()
    lock = load_canon_json(root / "meta-core" / "meta_constitution" / "v9_0" / "immutable_core_lock_v1.json")
    icore_id = str(lock.get("core_id"))
    meta_hash = (root / "meta-core" / "meta_constitution" / "v9_0" / "META_HASH").read_text(encoding="utf-8").strip()
    return icore_id, meta_hash


def policy_hash() -> str:
    root = repo_root()
    policy = load_canon_json(root / "meta-core" / "meta_constitution" / "v9_0" / "superego_policy_v3.json")
    return compute_policy_hash(policy)


def copy_policy(alignment_dir: Path) -> tuple[Path, Path]:
    root = repo_root()
    policy_src = root / "meta-core" / "meta_constitution" / "v9_0" / "superego_policy_v3.json"
    lock_src = root / "meta-core" / "meta_constitution" / "v9_0" / "superego_policy_lock_v1.json"
    policy_dst = alignment_dir / "policy" / "superego_policy_v1.json"
    lock_dst = alignment_dir / "policy" / "superego_policy_lock_v1.json"
    policy_dst.parent.mkdir(parents=True, exist_ok=True)
    policy_dst.write_text(policy_src.read_text(encoding="utf-8"), encoding="utf-8")
    lock_dst.write_text(lock_src.read_text(encoding="utf-8"), encoding="utf-8")
    return policy_dst, lock_dst


def write_alignment_artifacts(alignment_dir: Path, *, clearance_level: str = "BOUNDLESS") -> None:
    alignment_dir.mkdir(parents=True, exist_ok=True)
    copy_policy(alignment_dir)

    ledger_path = alignment_dir / "ledger" / "superego_ledger_v1.jsonl"
    entry = build_superego_entry(1, 0, "CLEARANCE_EMITTED", "GENESIS", {"note": "fixture"})
    write_ledger(ledger_path, [entry])

    report = {
        "schema_version": "alignment_report_v1",
        "policy_hash": policy_hash(),
        "icore_id": identities()[0],
        "meta_hash": identities()[1],
        "suite_id": "fixture",
        "hard_fail_count": 0,
        "hard_total": 1,
        "soft_pass_count": 1,
        "soft_total": 1,
        "align_score_num": 1,
        "align_score_den": 1,
        "meets_clearance": True,
        "evidence_hashes": [],
    }
    report_path = alignment_dir / "reports" / "alignment_report_v1.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    write_canon_json(report_path, report)

    clearance = {
        "schema_version": "alignment_clearance_receipt_v1",
        "policy_hash": policy_hash(),
        "icore_id": identities()[0],
        "meta_hash": identities()[1],
        "clearance_level": clearance_level,
        "issued_at_tick": 1,
        "alignment_report_hash": "sha256:" + hashlib.sha256(canon_bytes(report)).hexdigest(),
        "ledger_head_hash": entry["entry_hash"],
    }
    clearance_path = alignment_dir / "clearance" / "alignment_clearance_receipt_v1.json"
    clearance_path.parent.mkdir(parents=True, exist_ok=True)
    write_canon_json(clearance_path, clearance)

    checkpoint = {
        "schema_version": "alignment_checkpoint_receipt_v1",
        "policy_hash": policy_hash(),
        "icore_id": identities()[0],
        "meta_hash": identities()[1],
        "tick": 1,
        "alignment_report_hash": clearance["alignment_report_hash"],
        "ledger_head_hash": entry["entry_hash"],
        "created_utc": "",
    }
    checkpoint_path = alignment_dir / "checkpoints" / "alignment_checkpoint_receipt_v1.json"
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    write_canon_json(checkpoint_path, checkpoint)


def write_toolchain(env_dir: Path) -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "schema_version": "science_toolchain_manifest_v1",
        "toolchain_id": "",
        "checker_name": "science_eval_worker",
        "checker_version": "v1-fixture",
        "checker_executable_hash": "sha256:" + ("0" * 64),
        "library_name": "fixture",
        "library_commit": "v1",
        "os": "macos",
        "arch": "arm64",
        "invocation_template": ["/usr/bin/python3", "-m", "cdel.v9_0.sealed_science_worker_v1"],
        "determinism_notes": "fixture",
    }
    manifest["toolchain_id"] = compute_toolchain_id(manifest)
    write_canon_json(env_dir / "science_toolchain_manifest_v1.json", manifest)
    return manifest


def write_dataset(env_dir: Path) -> dict[str, Any]:
    datasets_dir = env_dir / "datasets"
    datasets_dir.mkdir(parents=True, exist_ok=True)
    payload = {"features": [1, -1, 2, -2], "labels": [1, 0, 1, 0]}
    data_path = datasets_dir / "physics_fixture.json"
    data_path.write_text(json.dumps(payload), encoding="utf-8")
    sha = "sha256:" + hashlib.sha256(data_path.read_bytes()).hexdigest()
    dataset_id = "sha256:" + hashlib.sha256((sha + "physics").encode("utf-8")).hexdigest()
    manifest = {
        "schema_version": "dataset_manifest_v1",
        "datasets": [
            {"dataset_id": dataset_id, "path": str(data_path), "sha256": sha, "domain": "PHYSICS"}
        ],
    }
    write_canon_json(env_dir / "dataset_manifest_v1.json", manifest)
    return manifest


def write_analysis_bundle(env_dir: Path) -> dict[str, Any]:
    bundle_dir = env_dir / "bundle"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    script_path = bundle_dir / "analysis.py"
    script_path.write_text("# fixture\n", encoding="utf-8")
    sha = "sha256:" + hashlib.sha256(script_path.read_bytes()).hexdigest()
    manifest = {
        "schema_version": "analysis_code_bundle_manifest_v1",
        "bundle_id": "",
        "files": [{"path": str(script_path), "sha256": sha, "bytes": script_path.stat().st_size}],
        "entrypoint": str(script_path),
    }
    manifest["bundle_id"] = "sha256:" + hashlib.sha256(canon_bytes(manifest)).hexdigest()
    write_canon_json(env_dir / "analysis_code_bundle_manifest_v1.json", manifest)
    return manifest


def write_suitepack(env_dir: Path, *, dataset_id: str, suite_id: str) -> dict[str, Any]:
    task = {
        "schema_version": "science_task_spec_v1",
        "task_id": "",
        "domain": "PHYSICS",
        "vector": "PHYS_PDE_BENCH_V1",
        "hazard_class": "H1_LOW_RISK",
        "dataset_id": dataset_id,
        "metric": {"kind": "accuracy", "direction": "MAX", "quantization": "ratio"},
        "baseline_metric": {"num": 1, "den": 4},
        "acceptance_threshold": {"num": 3, "den": 4},
        "limits": {"time_limit_ms": 1000, "memory_limit_mb": 128, "cpu_limit_ms": 1000},
        "output_constraints": {"allow_kinds": ["model_weights"], "max_bytes": 1024, "allow_free_text": False},
        "stochastic": False,
    }
    task["task_id"] = compute_task_id(task)
    suitepack = {"schema_version": "science_suitepack_v1", "suite_id": suite_id, "tasks": [task]}
    path = env_dir / f"science_suitepack_{suite_id}.json"
    write_canon_json(path, suitepack)
    return suitepack


def write_env_lock(env_dir: Path, *, toolchain: dict[str, Any], dataset: dict[str, Any], bundle: dict[str, Any], dev: dict[str, Any], heldout: dict[str, Any]) -> dict[str, str]:
    payload = {
        "toolchain_manifest_hash": compute_toolchain_hash(toolchain),
        "dataset_manifest_hash": compute_dataset_manifest_hash(dataset),
        "analysis_code_bundle_hash": "sha256:" + hashlib.sha256(canon_bytes(bundle)).hexdigest(),
        "dev_suitepack_hash": compute_suitepack_hash(dev),
        "heldout_suitepack_hash": compute_suitepack_hash(heldout),
    }
    write_canon_json(env_dir / "SCIENCE_ENV_LOCK_HASHES.json", payload)
    return payload


def write_lease(leases_dir: Path, *, daemon_id: str) -> dict[str, Any]:
    leases_dir.mkdir(parents=True, exist_ok=True)
    lease = {
        "schema_version": "science_lease_token_v1",
        "lease_id": "fixture",
        "daemon_id": daemon_id,
        "icore_id": identities()[0],
        "meta_hash": identities()[1],
        "superego_policy_hash": policy_hash(),
        "domains_allowed": ["PHYSICS"],
        "max_hazard_class": "H1_LOW_RISK",
        "budgets": {"max_ticks": 10, "max_work_units": 10, "max_artifact_bytes": 4096, "max_wall_ms": 1000},
        "not_before_utc": "2026-01-01T00:00:00Z",
        "not_after_utc": "2027-01-01T00:00:00Z",
        "operator_signatures": ["fixture"],
    }
    write_canon_json(leases_dir / "lease_fixture.science_lease_token_v1.json", lease)
    (leases_dir / "ACTIVE_SCIENCE_LEASE_ID").write_text("fixture", encoding="utf-8")
    return lease


def write_daemon_pack(config_dir: Path, *, state_dir: Path, alignment_pack_path: str, boundless_pack_path: str, toolchain_path: str) -> dict[str, Any]:
    icore_id, meta_hash = identities()
    pack: dict[str, Any] = {
        "schema_version": "rsi_daemon_pack_v9",
        "icore_id": icore_id,
        "meta_hash": meta_hash,
        "daemon_id": "",
        "state_dir": str(state_dir),
        "control": {
            "stop": "control/STOP",
            "pause": "control/PAUSE",
            "enable_research": "control/ENABLE_RESEARCH",
            "enable_boundless_science": "control/ENABLE_BOUNDLESS_SCIENCE",
            "enable_science_physics": "control/ENABLE_SCIENCE_PHYSICS",
            "enable_science_chemistry": "control/ENABLE_SCIENCE_CHEMISTRY",
            "enable_science_biology": "control/ENABLE_SCIENCE_BIOLOGY",
        },
        "checkpoint_policy": {"every_ticks": 1, "retain_last_n": 2},
        "budgets": {"max_ticks_per_boot": 4, "max_work_units_per_day": 1000},
        "activities": [
            {
                "activity_kind": "SCIENCE_BOUNDLESS_V1",
                "activity_id": "boundless_science",
                "objective_class": "BOUNDLESS_SCIENCE",
                "capabilities": ["FS_WRITE_SCIENCE_ONLY", "SEALED_RUN_REQUIRED", "NETWORK_NONE"],
            }
        ],
        "alignment": {
            "alignment_pack_path": alignment_pack_path,
            "policy_lock_path": "policy/superego_policy_lock_v1.json",
            "clearance_required_for_research_bounded": True,
            "clearance_required_for_boundless": True,
            "require_enable_research_file_for_boundless": True,
            "clearance_refresh_ticks": 2,
        },
        "science_boundless": {
            "enabled": True,
            "boundless_pack_path": boundless_pack_path,
            "toolchain_manifest_path": toolchain_path,
            "require_enable_research_file": True,
            "require_enable_boundless_science_file": True,
            "require_domain_enable_file": True,
            "attempts_per_tick_max": 1,
            "daily_attempt_budget": 4,
            "heldout_eval_every_k_attempts": 1,
            "problem_selection_policy": "first",
        },
    }
    pack["daemon_id"] = compute_daemon_id(pack)
    write_canon_json(config_dir / "rsi_daemon_pack_v9.json", pack)
    return pack


def build_superego_entry(seq: int, tick: int, event_type: str, prev_hash: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    entry = {
        "seq": seq,
        "tick": tick,
        "event_type": event_type,
        "event_payload": payload or {},
        "prev_entry_hash": prev_hash,
        "entry_hash": "",
    }
    entry["entry_hash"] = compute_superego_entry_hash(entry)
    return entry


def build_daemon_entry(seq: int, tick: int, event_type: str, prev_hash: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    entry = {
        "seq": seq,
        "tick": tick,
        "event_type": event_type,
        "event_payload": payload or {},
        "prev_entry_hash": prev_hash,
        "entry_hash": "",
    }
    entry["entry_hash"] = compute_daemon_entry_hash(entry)
    return entry


def build_science_entry(seq: int, tick: int, event_type: str, prev_hash: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    entry = {
        "seq": seq,
        "tick": tick,
        "event_type": event_type,
        "event_payload": payload or {},
        "prev_entry_hash": prev_hash,
        "entry_hash": "",
    }
    entry["entry_hash"] = compute_science_entry_hash(entry)
    return entry


def write_ledger(path: Path, entries: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")
    for entry in entries:
        write_jsonl_line(path, entry)


def write_snapshot(snapshot_dir: Path, snapshot: dict[str, Any]) -> str:
    snap_hash = compute_snapshot_hash(snapshot)
    name = f"sha256_{snap_hash.split(':', 1)[1]}.daemon_state_snapshot_v1.json"
    write_canon_json(snapshot_dir / name, snapshot)
    return snap_hash


def write_boot_receipt(boot_dir: Path, receipt: dict[str, Any]) -> str:
    receipt_hash = compute_receipt_hash(receipt)
    name = f"sha256_{receipt_hash.split(':', 1)[1]}.daemon_boot_receipt_v1.json"
    write_canon_json(boot_dir / name, receipt)
    return receipt_hash


def write_checkpoint_receipt(checkpoint_dir: Path, receipt: dict[str, Any]) -> str:
    receipt_hash = compute_receipt_hash(receipt)
    name = f"sha256_{receipt_hash.split(':', 1)[1]}.daemon_checkpoint_receipt_v1.json"
    write_canon_json(checkpoint_dir / name, receipt)
    return receipt_hash


def build_valid_state(tmp_path: Path, *, enable_boundless: bool = True, include_acceptance: bool = False) -> dict[str, Any]:
    daemon_root = tmp_path / "daemon" / "rsi_daemon_v9_0_science"
    state_dir = daemon_root / "state"
    config_dir = daemon_root / "config"

    for sub in [
        state_dir / "ledger",
        state_dir / "snapshots",
        state_dir / "checkpoints",
        state_dir / "boots",
        state_dir / "shutdowns",
        state_dir / "alignment",
        state_dir / "control",
        state_dir / "science" / "env",
        state_dir / "science" / "leases",
        state_dir / "science" / "ledger",
        state_dir / "science" / "attempts",
        state_dir / "science" / "accepted" / "receipts",
    ]:
        sub.mkdir(parents=True, exist_ok=True)

    sealed_config = tmp_path / "sealed_alignment_fixture_v1.toml"
    sealed_config.write_text("suite_id = 'fixture'\n", encoding="utf-8")

    alignment_pack = {
        "schema_version": "rsi_alignment_pack_v1",
        "icore_id": identities()[0],
        "meta_hash": identities()[1],
        "policy_hash": policy_hash(),
        "sealed_alignment_config": str(sealed_config),
        "clearance_thresholds": {"min_align_score_num": 1, "min_align_score_den": 1, "hard_fail_max": 0},
    }
    write_canon_json(config_dir / "rsi_alignment_pack_v1.json", alignment_pack)

    write_alignment_artifacts(state_dir / "alignment")

    toolchain = write_toolchain(state_dir / "science" / "env")
    dataset = write_dataset(state_dir / "science" / "env")
    bundle = write_analysis_bundle(state_dir / "science" / "env")
    dev_suitepack = write_suitepack(state_dir / "science" / "env", dataset_id=dataset["datasets"][0]["dataset_id"], suite_id="dev_v1")
    heldout_suitepack = write_suitepack(state_dir / "science" / "env", dataset_id=dataset["datasets"][0]["dataset_id"], suite_id="heldout_v1")

    write_env_lock(state_dir / "science" / "env", toolchain=toolchain, dataset=dataset, bundle=bundle, dev=dev_suitepack, heldout=heldout_suitepack)

    boundless_pack = {
        "schema_version": "rsi_boundless_science_pack_v1",
        "icore_id": identities()[0],
        "meta_hash": identities()[1],
        "superego_policy_hash": policy_hash(),
        "toolchain_manifest_hash": compute_toolchain_hash(toolchain),
        "dataset_manifest_hash": compute_dataset_manifest_hash(dataset),
        "analysis_code_bundle_hash": "sha256:" + hashlib.sha256(canon_bytes(bundle)).hexdigest(),
        "dev_suitepack_hash": compute_suitepack_hash(dev_suitepack),
        "heldout_suitepack_hash": compute_suitepack_hash(heldout_suitepack),
        "toolchain_manifest_path": str(state_dir / "science" / "env" / "science_toolchain_manifest_v1.json"),
        "dataset_manifest_path": str(state_dir / "science" / "env" / "dataset_manifest_v1.json"),
        "analysis_code_bundle_path": str(state_dir / "science" / "env" / "analysis_code_bundle_manifest_v1.json"),
        "dev_suitepack_path": str(state_dir / "science" / "env" / "science_suitepack_dev_v1.json"),
        "heldout_suitepack_path": str(state_dir / "science" / "env" / "science_suitepack_heldout_v1.json"),
        "limits": {"attempts_per_tick_max": 1, "daily_attempt_budget": 4, "per_attempt_time_limit_ms": 1000, "per_attempt_memory_limit_mb": 128},
        "heldout_eval_every_k_attempts": 1,
        "selection_policy": "first",
    }
    write_canon_json(config_dir / "rsi_boundless_science_pack_v1.json", boundless_pack)

    pack = write_daemon_pack(
        config_dir,
        state_dir=state_dir,
        alignment_pack_path=str(config_dir / "rsi_alignment_pack_v1.json"),
        boundless_pack_path=str(config_dir / "rsi_boundless_science_pack_v1.json"),
        toolchain_path=str(state_dir / "science" / "env" / "science_toolchain_manifest_v1.json"),
    )

    write_lease(state_dir / "science" / "leases", daemon_id=pack["daemon_id"])

    task = dev_suitepack["tasks"][0]
    attempt_record = {
        "schema_version": "science_attempt_record_v1",
        "attempt_id": "",
        "task_id": task["task_id"],
        "tick": 1,
        "daemon_id": pack["daemon_id"],
        "superego_request_id": "",
        "objective_class": "BOUNDLESS_SCIENCE",
        "capabilities": ["NETWORK_NONE", "SEALED_RUN_REQUIRED", "FS_WRITE_SCIENCE_ONLY"],
        "lease_id": "fixture",
        "suite_id": dev_suitepack["suite_id"],
        "domain": task["domain"],
        "vector": task["vector"],
        "hazard_class": task["hazard_class"],
        "target_paths": [str(state_dir / "science" / "attempts")],
    }

    request = {
        "schema_version": "superego_action_request_v1",
        "request_id": "",
        "daemon_id": pack["daemon_id"],
        "tick": 1,
        "objective_class": "BOUNDLESS_SCIENCE",
        "objective_text": "science attempt",
        "capabilities": attempt_record["capabilities"],
        "target_paths": [str(state_dir / "science" / "attempts")],
        "sealed_eval_required": True,
        "science": {
            "domain": task["domain"],
            "vector": task["vector"],
            "hazard_class": task["hazard_class"],
            "task_id": task["task_id"],
            "lease_id": "fixture",
        },
    }
    request["request_id"] = compute_request_id(request)
    attempt_record["superego_request_id"] = request["request_id"]
    attempt_record["attempt_id"] = compute_attempt_id(attempt_record)

    attempt_dir = state_dir / "science" / "attempts" / task["task_id"] / attempt_record["attempt_id"]
    attempt_dir.mkdir(parents=True, exist_ok=True)
    write_canon_json(attempt_dir / "attempt_record_v1.json", attempt_record)

    artifact = {"bias": 0}
    artifact_bytes = json.dumps(artifact, sort_keys=True, separators=(",", ":")).encode("utf-8")
    art_hash = "sha256:" + hashlib.sha256(artifact_bytes).hexdigest()
    artifacts_dir = attempt_dir / "outputs" / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifacts_dir / f"{art_hash.split(':',1)[1]}.json"
    artifact_path.write_bytes(artifact_bytes)

    output_manifest = {
        "schema_version": "output_manifest_v1",
        "artifacts": [
            {"path": str(artifact_path), "sha256": art_hash, "bytes": len(artifact_bytes), "kind": "model_weights"}
        ],
    }
    (attempt_dir / "outputs").mkdir(parents=True, exist_ok=True)
    write_canon_json(attempt_dir / "outputs" / "output_manifest_v1.json", output_manifest)

    dev_suite_hash = compute_suitepack_hash(dev_suitepack)
    heldout_suite_hash = compute_suitepack_hash(heldout_suitepack)
    sealed_receipt = {
        "schema_version": "sealed_science_eval_receipt_v1",
        "task_id": task["task_id"],
        "attempt_id": attempt_record["attempt_id"],
        "toolchain_id": toolchain["toolchain_id"],
        "toolchain_manifest_hash": compute_toolchain_hash(toolchain),
        "dataset_manifest_hash": compute_dataset_manifest_hash(dataset),
        "suitepack_hash": dev_suite_hash,
        "metric_num": 4,
        "metric_den": 4,
        "stdout_hash": "sha256:" + ("0" * 64),
        "stderr_hash": "sha256:" + ("0" * 64),
        "network_used": False,
        "time_ms": 1,
        "memory_mb": 1,
    }
    sealed_hash = "sha256:" + hashlib.sha256(canon_bytes(sealed_receipt)).hexdigest()
    sealed_dir = attempt_dir / "sealed"
    sealed_dir.mkdir(parents=True, exist_ok=True)
    write_canon_json(sealed_dir / f"sha256_{sealed_hash.split(':',1)[1]}.sealed_science_eval_receipt_v1.json", sealed_receipt)

    if include_acceptance:
        heldout_receipt = dict(sealed_receipt)
        heldout_receipt["suitepack_hash"] = heldout_suite_hash
        heldout_hash = "sha256:" + hashlib.sha256(canon_bytes(heldout_receipt)).hexdigest()
        write_canon_json(
            sealed_dir / f"sha256_{heldout_hash.split(':',1)[1]}.sealed_science_eval_receipt_v1.json",
            heldout_receipt,
        )
        acceptance = {
            "schema_version": "acceptance_receipt_v1",
            "task_id": task["task_id"],
            "decision": "ACCEPTED",
            "metric_num": 4,
            "metric_den": 4,
            "threshold_num": 3,
            "threshold_den": 4,
            "replication_count": 1,
            "heldout_receipt_hashes": [heldout_hash],
            "created_utc": "",
        }
        acc_hash = compute_acceptance_hash(acceptance)
        write_canon_json(state_dir / "science" / "accepted" / "receipts" / f"sha256_{acc_hash.split(':',1)[1]}.acceptance_receipt_v1.json", acceptance)

    # Daemon ledger
    prev = "GENESIS"
    entries = []
    seq = 0
    seq += 1
    entry = build_daemon_entry(seq, 0, "BOOT", prev, {})
    entries.append(entry)
    prev = entry["entry_hash"]
    seq += 1
    entry = build_daemon_entry(seq, 1, "TICK_BEGIN", prev, {"tick": 1})
    entries.append(entry)
    prev = entry["entry_hash"]
    seq += 1
    entry = build_daemon_entry(seq, 1, "ENABLE_RESEARCH_PRESENT", prev, {})
    entries.append(entry)
    prev = entry["entry_hash"]
    if enable_boundless:
        seq += 1
        entry = build_daemon_entry(seq, 1, "ENABLE_BOUNDLESS_SCIENCE_PRESENT", prev, {})
        entries.append(entry)
        prev = entry["entry_hash"]
    seq += 1
    entry = build_daemon_entry(seq, 1, "ENABLE_SCIENCE_PHYSICS_PRESENT", prev, {})
    entries.append(entry)
    prev = entry["entry_hash"]
    seq += 1
    entry = build_daemon_entry(
        seq,
        1,
        "SUPEREGO_REQUEST",
        prev,
        {"request_id": request["request_id"], "objective_class": "BOUNDLESS_SCIENCE", "capabilities": request["capabilities"]},
    )
    entries.append(entry)
    prev = entry["entry_hash"]
    decision_payload = {
        "schema_version": "superego_decision_receipt_v1",
        "request_id": request["request_id"],
        "decision": "ALLOW",
        "policy_hash": policy_hash(),
        "decision_reason_code": "ALLOW",
        "decision_hash": "",
        "tick": 1,
        "daemon_id": pack["daemon_id"],
        "icore_id": identities()[0],
        "meta_hash": identities()[1],
    }
    decision_payload["decision_hash"] = compute_decision_hash(decision_payload)
    seq += 1
    entry = build_daemon_entry(
        seq,
        1,
        "SUPEREGO_DECISION",
        prev,
        {
            "request_id": request["request_id"],
            "decision": "ALLOW",
            "policy_hash": decision_payload["policy_hash"],
            "decision_hash": decision_payload["decision_hash"],
            "decision_reason_code": "ALLOW",
        },
    )
    entries.append(entry)
    prev = entry["entry_hash"]
    seq += 1
    entry = build_daemon_entry(seq, 1, "SCI_ATTEMPT_STARTED", prev, {"attempt_id": attempt_record["attempt_id"], "request_id": request["request_id"]})
    entries.append(entry)
    prev = entry["entry_hash"]
    seq += 1
    entry = build_daemon_entry(seq, 1, "ACTION_EXECUTED", prev, {"request_id": request["request_id"]})
    entries.append(entry)
    prev = entry["entry_hash"]
    seq += 1
    entry = build_daemon_entry(seq, 1, "CHECKPOINT", prev, {})
    entries.append(entry)

    ledger_path = state_dir / "ledger" / "daemon_ledger_v1.jsonl"
    write_ledger(ledger_path, entries)

    snapshot = {
        "schema_version": "daemon_state_snapshot_v1",
        "daemon_id": pack["daemon_id"],
        "icore_id": pack["icore_id"],
        "meta_hash": pack["meta_hash"],
        "tick": 1,
        "ledger_head_hash": entries[-1]["entry_hash"],
        "last_checkpoint_hash": None,
        "boot_count": 1,
        "paused_reason": None,
        "budget_counters": {"ticks_today": 1, "science_attempts_today": 1},
    }
    snap_hash = write_snapshot(state_dir / "snapshots", snapshot)

    boot_receipt = {
        "schema_version": "daemon_boot_receipt_v1",
        "kind": "BOOT",
        "daemon_id": pack["daemon_id"],
        "icore_id": pack["icore_id"],
        "meta_hash": pack["meta_hash"],
        "tick": 0,
        "boot_count": 1,
        "ledger_head_hash": entries[0]["entry_hash"],
        "euid": 501,
        "created_utc": "",
    }
    write_boot_receipt(state_dir / "boots", boot_receipt)

    checkpoint_receipt = {
        "schema_version": "daemon_checkpoint_receipt_v1",
        "kind": "CHECKPOINT",
        "daemon_id": pack["daemon_id"],
        "icore_id": pack["icore_id"],
        "meta_hash": pack["meta_hash"],
        "tick": 1,
        "boot_count": 1,
        "ledger_head_hash": entries[-1]["entry_hash"],
        "snapshot_hash": snap_hash,
        "created_utc": "",
    }
    write_checkpoint_receipt(state_dir / "checkpoints", checkpoint_receipt)

    sci_entries = []
    prev = "GENESIS"
    sci_entries.append(build_science_entry(1, 0, "SCI_BOOT", prev, {}))
    prev = sci_entries[-1]["entry_hash"]
    sci_entries.append(build_science_entry(2, 1, "SCI_TASK_SELECTED", prev, {"task_id": task["task_id"]}))
    prev = sci_entries[-1]["entry_hash"]
    sci_entries.append(build_science_entry(3, 1, "SCI_ATTEMPT_STARTED", prev, {"attempt_id": attempt_record["attempt_id"], "task_id": task["task_id"]}))
    prev = sci_entries[-1]["entry_hash"]
    sci_entries.append(build_science_entry(4, 1, "SCI_SEALED_RECEIPT_RECORDED", prev, {"attempt_id": attempt_record["attempt_id"], "receipt_hash": sealed_hash}))
    if include_acceptance:
        prev = sci_entries[-1]["entry_hash"]
        sci_entries.append(build_science_entry(5, 1, "SCI_ACCEPTED", prev, {"task_id": task["task_id"]}))
    write_ledger(state_dir / "science" / "ledger" / "science_ledger_v1.jsonl", sci_entries)

    return {"state_dir": state_dir, "daemon_pack": pack, "attempt_dir": attempt_dir}
