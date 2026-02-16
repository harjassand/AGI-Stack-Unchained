from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from cdel.v1_7r.canon import canon_bytes, load_canon_json, write_canon_json, write_jsonl_line
from cdel.v6_0.daemon_checkpoint import compute_receipt_hash
from cdel.v7_0.alignment_eval import compute_alignment_report_hash
from cdel.v7_0.superego_ledger import compute_entry_hash as compute_superego_entry_hash
from cdel.v7_0.superego_policy import compute_decision_hash, compute_policy_hash, compute_request_id
from cdel.v8_0.daemon_ledger import compute_entry_hash as compute_daemon_entry_hash
from cdel.v8_0.daemon_state import compute_daemon_id, compute_snapshot_hash
from cdel.v8_0.math_attempts import compute_attempt_id, compute_attempt_receipt_hash
from cdel.v8_0.math_ledger import compute_entry_hash as compute_math_entry_hash
from cdel.v8_0.math_problem import compute_problem_id
from cdel.v8_0.math_toolchain import compute_manifest_hash, compute_toolchain_id
from cdel.v8_0.sealed_proofcheck import compute_sealed_receipt_hash


def repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def identities() -> tuple[str, str]:
    root = repo_root()
    lock = load_canon_json(root / "meta-core" / "meta_constitution" / "v8_0" / "immutable_core_lock_v1.json")
    icore_id = str(lock.get("core_id"))
    meta_hash = (root / "meta-core" / "meta_constitution" / "v8_0" / "META_HASH").read_text(encoding="utf-8").strip()
    return icore_id, meta_hash


def policy_hash() -> str:
    root = repo_root()
    policy = load_canon_json(root / "meta-core" / "meta_constitution" / "v8_0" / "superego_policy_v2.json")
    return compute_policy_hash(policy)


def copy_policy(alignment_dir: Path) -> tuple[Path, Path]:
    root = repo_root()
    policy_src = root / "meta-core" / "meta_constitution" / "v8_0" / "superego_policy_v2.json"
    lock_src = root / "meta-core" / "meta_constitution" / "v8_0" / "superego_policy_lock_v1.json"
    policy_dst = alignment_dir / "policy" / "superego_policy_v1.json"
    lock_dst = alignment_dir / "policy" / "superego_policy_lock_v1.json"
    policy_dst.parent.mkdir(parents=True, exist_ok=True)
    policy_dst.write_text(policy_src.read_text(encoding="utf-8"), encoding="utf-8")
    lock_dst.write_text(lock_src.read_text(encoding="utf-8"), encoding="utf-8")
    return policy_dst, lock_dst


def write_alignment_artifacts(alignment_dir: Path, *, clearance_level: str = "BOUNDLESS") -> dict[str, str]:
    alignment_dir.mkdir(parents=True, exist_ok=True)
    copy_policy(alignment_dir)

    ledger_path = alignment_dir / "ledger" / "superego_ledger_v1.jsonl"
    entry = build_superego_entry(1, 0, "CLEARANCE_EMITTED", "GENESIS", {"note": "fixture"})
    write_ledger(ledger_path, [entry])

    report = build_alignment_report()
    report_path = alignment_dir / "reports" / "alignment_report_v1.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    write_canon_json(report_path, report)

    receipt = build_clearance_receipt(report, ledger_head_hash=entry["entry_hash"], clearance_level=clearance_level)
    receipt_path = alignment_dir / "clearance" / "alignment_clearance_receipt_v1.json"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    write_canon_json(receipt_path, receipt)

    return {
        "ledger": str(ledger_path),
        "report": str(report_path),
        "clearance": str(receipt_path),
    }


def write_alignment_pack(config_dir: Path, *, sealed_path: str, thresholds: dict[str, Any]) -> dict[str, Any]:
    icore_id, meta_hash = identities()
    pack: dict[str, Any] = {
        "schema_version": "rsi_alignment_pack_v1",
        "icore_id": icore_id,
        "meta_hash": meta_hash,
        "policy_hash": policy_hash(),
        "sealed_alignment_config": sealed_path,
        "clearance_thresholds": thresholds,
    }
    write_canon_json(config_dir / "rsi_alignment_pack_v1.json", pack)
    return pack


def write_math_toolchain(config_dir: Path) -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "schema_version": "math_toolchain_manifest_v1",
        "toolchain_id": "",
        "checker_name": "toy_kernel",
        "checker_version": "v1-fixture",
        "checker_executable_hash": "sha256:" + ("0" * 64),
        "library_name": "toy_library",
        "library_commit": "v1",
        "os": "macos",
        "arch": "arm64",
        "invocation_template": ["/usr/bin/python3", "checker.py", "{entrypoint}"],
        "determinism_notes": "fixture",
    }
    manifest["toolchain_id"] = compute_toolchain_id(manifest)
    write_canon_json(config_dir / "math_toolchain_manifest_v1.json", manifest)
    return manifest


def write_math_pack(config_dir: Path, *, problems_dir: Path, selection_policy: str, limits: dict[str, int]) -> dict[str, Any]:
    icore_id, meta_hash = identities()
    manifest = load_canon_json(config_dir / "math_toolchain_manifest_v1.json")
    manifest_hash = compute_manifest_hash(manifest)
    pack: dict[str, Any] = {
        "schema_version": "rsi_boundless_math_pack_v1",
        "icore_id": icore_id,
        "meta_hash": meta_hash,
        "superego_policy_hash": policy_hash(),
        "toolchain_manifest_hash": manifest_hash,
        "problem_set_id": "fixture_set",
        "problems_dir": str(problems_dir),
        "selection_policy": selection_policy,
        "limits": {
            "attempts_per_tick_max": int(limits.get("attempts_per_tick_max", 1)),
            "proof_check_per_tick_max": int(limits.get("proof_check_per_tick_max", 1)),
            "daily_attempt_budget": int(limits.get("daily_attempt_budget", 2)),
            "per_attempt_time_limit_ms": int(limits.get("per_attempt_time_limit_ms", 1000)),
            "per_attempt_memory_limit_mb": int(limits.get("per_attempt_memory_limit_mb", 256)),
        },
        "acceptance": {"accept_only_on_pass": True, "require_sealed_receipt": True},
    }
    write_canon_json(config_dir / "rsi_boundless_math_pack_v1.json", pack)
    return pack


def write_problem_spec(problems_dir: Path, *, statement: str = "example : 1 = 1 :=") -> dict[str, Any]:
    problems_dir.mkdir(parents=True, exist_ok=True)
    statement_hash = "sha256:" + hashlib.sha256(statement.encode("utf-8")).hexdigest()
    statement_path = problems_dir / f"sha256_{statement_hash.split(':',1)[1]}.statement.txt"
    statement_path.write_text(statement, encoding="utf-8")
    spec: dict[str, Any] = {
        "schema_version": "math_problem_spec_v1",
        "problem_id": "",
        "domain": "FORMAL_MATH",
        "difficulty_tier": "TRIVIAL",
        "statement_artifact_hash": statement_hash,
        "checker_entrypoint": "proof.lean",
        "time_limit_ms": 1000,
        "memory_limit_mb": 256,
        "requires_library": True,
        "tags": ["fixture"],
    }
    spec["problem_id"] = compute_problem_id(spec)
    path = problems_dir / f"{spec['problem_id'].split(':',1)[1]}.math_problem_spec_v1.json"
    write_canon_json(path, spec)
    return spec


def write_daemon_pack(config_dir: Path, *, state_dir: Path, alignment_pack_path: str, math_pack_path: str, toolchain_path: str) -> dict[str, Any]:
    icore_id, meta_hash = identities()
    pack: dict[str, Any] = {
        "schema_version": "rsi_daemon_pack_v8",
        "icore_id": icore_id,
        "meta_hash": meta_hash,
        "daemon_id": "",
        "state_dir": str(state_dir),
        "control": {
            "stop": "control/STOP",
            "pause": "control/PAUSE",
            "enable_research": "control/ENABLE_RESEARCH",
            "enable_boundless_math": "control/ENABLE_BOUNDLESS_MATH",
        },
        "checkpoint_policy": {"every_ticks": 1, "retain_last_n": 2},
        "budgets": {"max_ticks_per_boot": 4, "max_work_units_per_day": 1000},
        "activities": [
            {
                "activity_kind": "MATH_BOUNDLESS_V1",
                "activity_id": "boundless_math",
                "objective_class": "BOUNDLESS_RESEARCH",
                "capabilities": [
                    "FS_READ_WORKSPACE",
                    "FS_WRITE_DAEMON_STATE",
                    "SUBPROCESS_TOOLCHAIN",
                    "SEALEDEXEC",
                    "NETWORK_NONE",
                ],
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
        "math_boundless": {
            "enabled": True,
            "boundless_pack_path": math_pack_path,
            "toolchain_manifest_path": toolchain_path,
            "require_enable_research_file": True,
            "require_enable_boundless_math_file": True,
            "attempts_per_tick_max": 1,
            "proof_check_per_tick_max": 1,
            "daily_attempt_budget": 2,
            "problem_selection_policy": "first",
        },
    }
    pack["daemon_id"] = compute_daemon_id(pack)
    write_canon_json(config_dir / "rsi_daemon_pack_v8.json", pack)
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


def build_math_entry(seq: int, tick: int, event_type: str, prev_hash: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    entry = {
        "seq": seq,
        "tick": tick,
        "event_type": event_type,
        "event_payload": payload or {},
        "prev_entry_hash": prev_hash,
        "entry_hash": "",
    }
    entry["entry_hash"] = compute_math_entry_hash(entry)
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


def build_alignment_report(**kwargs: Any) -> dict[str, Any]:
    icore_id, meta_hash = identities()
    report = {
        "schema_version": "alignment_report_v1",
        "policy_hash": policy_hash(),
        "icore_id": icore_id,
        "meta_hash": meta_hash,
        "suite_id": "fixture",
        "hard_fail_count": 0,
        "hard_total": 4,
        "soft_pass_count": 2,
        "soft_total": 3,
        "align_score_num": 8,
        "align_score_den": 10,
        "meets_clearance": True,
        "evidence_hashes": [],
    }
    report.update(kwargs)
    return report


def build_clearance_receipt(report: dict[str, Any], *, ledger_head_hash: str, clearance_level: str = "BOUNDLESS") -> dict[str, Any]:
    icore_id, meta_hash = identities()
    return {
        "schema_version": "alignment_clearance_receipt_v1",
        "policy_hash": policy_hash(),
        "icore_id": icore_id,
        "meta_hash": meta_hash,
        "clearance_level": clearance_level,
        "issued_at_tick": 1,
        "alignment_report_hash": compute_alignment_report_hash(report),
        "ledger_head_hash": ledger_head_hash,
    }


def build_valid_state(
    tmp_path: Path,
    *,
    attempts_per_tick: int = 1,
    enable_boundless: bool = True,
    capabilities: list[str] | None = None,
    attempt_result: str = "PASS",
    sealed_receipt_present: bool = True,
    override_meta_hash: str | None = None,
    force_accept_event: bool = False,
) -> dict[str, Any]:
    daemon_root = tmp_path / "daemon" / "rsi_daemon_v8_0_math"
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
        state_dir / "math" / "ledger",
        state_dir / "math" / "attempts" / "receipts",
        state_dir / "math" / "attempts" / "records",
        state_dir / "math" / "attempts" / "sealed",
        state_dir / "math" / "attempts" / "proofs",
        state_dir / "math" / "solved" / "receipts",
    ]:
        sub.mkdir(parents=True, exist_ok=True)

    sealed_config = tmp_path / "sealed_alignment_fixture_v1.toml"
    sealed_config.write_text("suite_id = 'fixture'\n", encoding="utf-8")

    write_alignment_pack(config_dir, sealed_path=str(sealed_config), thresholds={"min_align_score_num": 1, "min_align_score_den": 2, "hard_fail_max": 0})

    toolchain = write_math_toolchain(config_dir)
    problems_dir = tmp_path / "problems"
    problem_spec = write_problem_spec(problems_dir)
    limits = {"attempts_per_tick_max": 1, "proof_check_per_tick_max": 1, "daily_attempt_budget": 2}
    math_pack = write_math_pack(config_dir, problems_dir=problems_dir, selection_policy="first", limits=limits)

    pack = write_daemon_pack(
        config_dir,
        state_dir=state_dir,
        alignment_pack_path=str(config_dir / "rsi_alignment_pack_v1.json"),
        math_pack_path=str(config_dir / "rsi_boundless_math_pack_v1.json"),
        toolchain_path=str(config_dir / "math_toolchain_manifest_v1.json"),
    )

    if override_meta_hash:
        pack["meta_hash"] = override_meta_hash
        pack["daemon_id"] = compute_daemon_id(pack)
        write_canon_json(config_dir / "rsi_daemon_pack_v8.json", pack)

    write_alignment_artifacts(state_dir / "alignment")

    if capabilities is None:
        capabilities = [
            "FS_READ_WORKSPACE",
            "FS_WRITE_DAEMON_STATE",
            "SUBPROCESS_TOOLCHAIN",
            "SEALEDEXEC",
            "NETWORK_NONE",
        ]

    request = {
        "schema_version": "superego_action_request_v1",
        "request_id": "",
        "daemon_id": pack["daemon_id"],
        "tick": 1,
        "objective_class": "BOUNDLESS_RESEARCH",
        "objective_text": "boundless math attempt",
        "capabilities": capabilities,
        "target_paths": [str(state_dir)],
        "sealed_eval_required": True,
    }
    request["request_id"] = compute_request_id(request)

    decision_payload = {
        "schema_version": "superego_decision_receipt_v1",
        "request_id": request["request_id"],
        "decision": "ALLOW",
        "policy_hash": policy_hash(),
        "decision_reason_code": "ALLOW",
        "tick": 1,
        "daemon_id": pack["daemon_id"],
        "icore_id": pack["icore_id"],
        "meta_hash": pack["meta_hash"],
    }
    decision_payload["decision_hash"] = compute_decision_hash({k: v for k, v in decision_payload.items() if k != "decision_hash"})

    attempt_ids: list[str] = []
    sealed_receipts: dict[str, dict[str, Any]] = {}
    attempt_receipts: dict[str, dict[str, Any]] = {}

    for idx in range(attempts_per_tick):
        attempt_record = {
            "schema_version": "math_attempt_record_v1",
            "attempt_id": "",
            "problem_id": problem_spec["problem_id"],
            "tick": 1,
            "daemon_id": pack["daemon_id"],
            "superego_request_id": request["request_id"],
            "objective_class": "BOUNDLESS_RESEARCH",
            "capabilities": capabilities,
        }
        attempt_record["attempt_id"] = compute_attempt_id(attempt_record)
        attempt_id = attempt_record["attempt_id"]
        attempt_ids.append(attempt_id)

        record_hash = hashlib.sha256(canon_bytes(attempt_record)).hexdigest()
        record_path = state_dir / "math" / "attempts" / "records" / f"sha256_{record_hash}.math_attempt_record_v1.json"
        write_canon_json(record_path, attempt_record)

        proof_content = f"example : {idx} = {idx} := by rfl\n".encode("utf-8")
        proof_hash = "sha256:" + hashlib.sha256(proof_content).hexdigest()
        proof_path = state_dir / "math" / "attempts" / "proofs" / f"sha256_{proof_hash.split(':',1)[1]}.proof.lean"
        proof_path.write_bytes(proof_content)

        logs_dir = state_dir / "math" / "attempts" / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        stdout_bytes = b""
        stderr_bytes = b""
        stdout_hash = "sha256:" + hashlib.sha256(stdout_bytes).hexdigest()
        stderr_hash = "sha256:" + hashlib.sha256(stderr_bytes).hexdigest()
        (logs_dir / f"sha256_{stdout_hash.split(':',1)[1]}.stdout.log").write_bytes(stdout_bytes)
        (logs_dir / f"sha256_{stderr_hash.split(':',1)[1]}.stderr.log").write_bytes(stderr_bytes)

        sealed = {
            "schema_version": "sealed_proof_check_receipt_v1",
            "toolchain_id": toolchain["toolchain_id"],
            "problem_id": problem_spec["problem_id"],
            "attempt_id": attempt_id,
            "invocation_argv": toolchain["invocation_template"],
            "exit_code": 0,
            "stdout_hash": stdout_hash,
            "stderr_hash": stderr_hash,
            "result": attempt_result,
            "time_ms": 10,
            "sandbox_manifest_hash": "sha256:" + ("0" * 64),
        }
        sealed_hash = compute_sealed_receipt_hash(sealed)
        sealed_path = state_dir / "math" / "attempts" / "sealed" / f"sha256_{sealed_hash.split(':',1)[1]}.sealed_proof_check_receipt_v1.json"
        if sealed_receipt_present:
            write_canon_json(sealed_path, sealed)
        sealed_receipts[attempt_id] = sealed

        receipt = {
            "schema_version": "math_attempt_receipt_v1",
            "attempt_id": attempt_id,
            "problem_id": problem_spec["problem_id"],
            "tick": 1,
            "daemon_id": pack["daemon_id"],
            "toolchain_id": toolchain["toolchain_id"],
            "toolchain_manifest_hash": compute_manifest_hash(toolchain),
            "sealed_proof_check_receipt_hash": sealed_hash,
            "result": attempt_result,
            "proof_artifact_hash": proof_hash,
            "stdout_hash": sealed["stdout_hash"],
            "stderr_hash": sealed["stderr_hash"],
            "wall_ms": 10,
        }
        receipt_hash = compute_attempt_receipt_hash(receipt)
        receipt_path = state_dir / "math" / "attempts" / "receipts" / f"sha256_{receipt_hash.split(':',1)[1]}.math_attempt_receipt_v1.json"
        write_canon_json(receipt_path, receipt)
        attempt_receipts[attempt_id] = receipt

    # Math ledger.
    math_entries: list[dict[str, Any]] = []
    prev = "GENESIS"
    seq = 1
    math_entries.append(build_math_entry(seq, 0, "MATH_BOOTSTRAP", prev, {"note": "fixture"}))
    prev = math_entries[-1]["entry_hash"]
    seq += 1
    math_entries.append(build_math_entry(seq, 1, "PROBLEM_SELECTED", prev, {"problem_id": problem_spec["problem_id"]}))
    prev = math_entries[-1]["entry_hash"]
    seq += 1
    for attempt_id in attempt_ids:
        math_entries.append(build_math_entry(seq, 1, "ATTEMPT_STARTED", prev, {"attempt_id": attempt_id}))
        prev = math_entries[-1]["entry_hash"]
        seq += 1
        math_entries.append(build_math_entry(seq, 1, "SEALED_PROOF_CHECK_STARTED", prev, {"attempt_id": attempt_id}))
        prev = math_entries[-1]["entry_hash"]
        seq += 1
        math_entries.append(
            build_math_entry(seq, 1, "SEALED_PROOF_CHECK_RESULT", prev, {"attempt_id": attempt_id, "result": attempt_result})
        )
        prev = math_entries[-1]["entry_hash"]
        seq += 1
        math_entries.append(build_math_entry(seq, 1, "ATTEMPT_RESULT_RECORDED", prev, {"attempt_id": attempt_id}))
        prev = math_entries[-1]["entry_hash"]
        seq += 1
        if attempt_result == "PASS" or force_accept_event:
            math_entries.append(build_math_entry(seq, 1, "PROOF_ACCEPTED", prev, {"attempt_id": attempt_id}))
            prev = math_entries[-1]["entry_hash"]
            seq += 1
        else:
            math_entries.append(build_math_entry(seq, 1, "PROOF_REJECTED", prev, {"attempt_id": attempt_id}))
            prev = math_entries[-1]["entry_hash"]
            seq += 1
    math_entries.append(build_math_entry(seq, 1, "SOLVED_INDEX_UPDATED", prev, {"count": len(attempt_ids)}))

    write_ledger(state_dir / "math" / "ledger" / "math_research_ledger_v1.jsonl", math_entries)

    # Daemon ledger.
    entries: list[dict[str, Any]] = []
    prev_hash = "GENESIS"
    seq = 1
    entries.append(build_daemon_entry(seq, 0, "BOOT", prev_hash, {}))
    prev_hash = entries[-1]["entry_hash"]
    seq += 1
    entries.append(build_daemon_entry(seq, 1, "TICK_BEGIN", prev_hash, {}))
    prev_hash = entries[-1]["entry_hash"]
    seq += 1
    entries.append(build_daemon_entry(seq, 1, "ENABLE_RESEARCH_PRESENT", prev_hash, {}))
    prev_hash = entries[-1]["entry_hash"]
    seq += 1
    if enable_boundless:
        entries.append(build_daemon_entry(seq, 1, "ENABLE_BOUNDLESS_MATH_PRESENT", prev_hash, {}))
        prev_hash = entries[-1]["entry_hash"]
        seq += 1

    for attempt_id in attempt_ids:
        entries.append(
            build_daemon_entry(
                seq,
                1,
                "SUPEREGO_REQUEST",
                prev_hash,
                {
                    "request_id": request["request_id"],
                    "objective_class": request["objective_class"],
                    "capabilities": request["capabilities"],
                },
            )
        )
        prev_hash = entries[-1]["entry_hash"]
        seq += 1
        entries.append(
            build_daemon_entry(
                seq,
                1,
                "SUPEREGO_DECISION",
                prev_hash,
                {
                    "request_id": request["request_id"],
                    "decision": "ALLOW",
                    "policy_hash": decision_payload["policy_hash"],
                    "decision_hash": decision_payload["decision_hash"],
                },
            )
        )
        prev_hash = entries[-1]["entry_hash"]
        seq += 1
        entries.append(
            build_daemon_entry(
                seq,
                1,
                "MATH_ATTEMPT_STARTED",
                prev_hash,
                {"attempt_id": attempt_id, "request_id": request["request_id"], "problem_id": problem_spec["problem_id"]},
            )
        )
        prev_hash = entries[-1]["entry_hash"]
        seq += 1
        entries.append(build_daemon_entry(seq, 1, "SEALED_PROOF_CHECK", prev_hash, {"attempt_id": attempt_id}))
        prev_hash = entries[-1]["entry_hash"]
        seq += 1
        entries.append(
            build_daemon_entry(
                seq,
                1,
                "MATH_ATTEMPT_RESULT",
                prev_hash,
                {"attempt_id": attempt_id, "result": attempt_result},
            )
        )
        prev_hash = entries[-1]["entry_hash"]
        seq += 1
        entries.append(
            build_daemon_entry(
                seq,
                1,
                "ACTION_EXECUTED",
                prev_hash,
                {"request_id": request["request_id"], "objective_class": "BOUNDLESS_RESEARCH"},
            )
        )
        prev_hash = entries[-1]["entry_hash"]
        seq += 1

    entries.append(build_daemon_entry(seq, 1, "CHECKPOINT", prev_hash, {}))
    prev_hash = entries[-1]["entry_hash"]

    write_ledger(state_dir / "ledger" / "daemon_ledger_v1.jsonl", entries)

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
        "budget_counters": {"math_attempts_today": attempts_per_tick},
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
        "created_utc": "2026-02-04T00:00:00Z",
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
        "created_utc": "2026-02-04T00:00:01Z",
    }
    write_checkpoint_receipt(state_dir / "checkpoints", checkpoint_receipt)

    return {
        "daemon_root": daemon_root,
        "state_dir": state_dir,
        "pack": pack,
        "attempt_ids": attempt_ids,
        "attempt_receipts": attempt_receipts,
        "sealed_receipts": sealed_receipts,
        "toolchain": toolchain,
    }


__all__ = [
    "build_valid_state",
    "copy_policy",
    "identities",
    "policy_hash",
    "repo_root",
    "write_alignment_artifacts",
    "write_alignment_pack",
]
