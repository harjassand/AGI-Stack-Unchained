"""Main loop for RSI daemon v6.0."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
SYS_CDEL = REPO_ROOT / "CDEL-v2"
if str(SYS_CDEL) not in sys.path:
    sys.path.insert(0, str(SYS_CDEL))

from cdel.v1_7r.canon import CanonError, canon_bytes, load_canon_json, sha256_prefixed, write_canon_json  # noqa: E402
from cdel.v2_3.immutable_core import load_lock, validate_lock  # noqa: E402
from cdel.v6_0.daemon_state import compute_daemon_id, compute_snapshot_hash, load_snapshot  # noqa: E402
from cdel.v6_0.daemon_ledger import load_daemon_ledger, validate_daemon_chain  # noqa: E402
from cdel.v6_0.daemon_ledger import truncate_incomplete_tail  # noqa: E402

from .control_plane_v1 import ControlPlane
from .health_v1 import write_health_report
from .io_atomic_v1 import atomic_write_json
from .ledger_writer_v1 import LedgerWriter
from .lockfile_v1 import LockFile
from .state_store_v1 import load_latest_snapshot, write_snapshot
from .tick_engine_v1 import BudgetCounters, TickEngine


EXIT_REFUSE_ROOT = 12
EXIT_LOCK_HELD = 13
EXIT_META_DRIFT = 14
EXIT_LEDGER_CORRUPT = 15
EXIT_CHECKPOINT_MISMATCH = 16
EXIT_DISK_LOW = 17
EXIT_FATAL = 18

MIN_FREE_BYTES = 512 * 1024 * 1024
MAX_LEDGER_BYTES = 50 * 1024 * 1024
MAX_LOG_BYTES = 10 * 1024 * 1024


def _meta_core_root() -> Path:
    env_override = Path(os.environ.get("META_CORE_ROOT", "")) if os.environ.get("META_CORE_ROOT") else None
    if env_override and env_override.exists():
        return env_override
    return REPO_ROOT / "meta-core"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def _require_constants() -> dict[str, Any]:
    meta_root = _meta_core_root()
    constants_path = meta_root / "meta_constitution" / "v6_0" / "constants_v1.json"
    return load_canon_json(constants_path)


def _meta_hash() -> str:
    meta_root = _meta_core_root()
    return _read_text(meta_root / "meta_constitution" / "v6_0" / "META_HASH")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_dirs(daemon_root: Path) -> dict[str, Path]:
    config_dir = daemon_root / "config"
    state_dir = daemon_root / "state"
    dirs = {
        "config": config_dir,
        "state": state_dir,
        "lock": state_dir / "lock",
        "control": state_dir / "control",
        "ledger": state_dir / "ledger",
        "snapshots": state_dir / "snapshots",
        "checkpoints": state_dir / "checkpoints",
        "boots": state_dir / "boots",
        "shutdowns": state_dir / "shutdowns",
        "health": state_dir / "health",
        "logs": daemon_root / "logs",
    }
    for path in dirs.values():
        path.mkdir(parents=True, exist_ok=True)
    return dirs


def _load_pack(pack_path: Path, config_dir: Path) -> dict[str, Any]:
    pack = load_canon_json(pack_path)
    if not isinstance(pack, dict) or pack.get("schema_version") != "rsi_daemon_pack_v1":
        raise CanonError("SCHEMA_INVALID")

    config_pack_path = config_dir / "rsi_daemon_pack_v1.json"
    if config_pack_path.exists():
        existing = load_canon_json(config_pack_path)
        if canon_bytes(existing) != canon_bytes(pack):
            raise CanonError("CANON_HASH_MISMATCH")
    else:
        write_canon_json(config_pack_path, pack)
    return pack


def _daemon_id_ok(pack: dict[str, Any]) -> None:
    expected = compute_daemon_id(pack)
    if pack.get("daemon_id") != expected:
        raise CanonError("CANON_HASH_MISMATCH")


def _check_disk(daemon_root: Path) -> None:
    usage = shutil.disk_usage(str(daemon_root))
    if usage.free < MIN_FREE_BYTES:
        raise CanonError("DAEMON_DISK_LOW")


def _check_ledger_size(ledger_path: Path) -> None:
    if ledger_path.exists() and ledger_path.stat().st_size > MAX_LEDGER_BYTES:
        raise CanonError("DAEMON_LEDGER_CORRUPT")


def _rotate_log(path: Path) -> None:
    if not path.exists():
        return
    if path.stat().st_size <= MAX_LOG_BYTES:
        return
    rotated = path.with_suffix(path.suffix + ".1")
    try:
        os.replace(path, rotated)
    except OSError:
        pass


def _write_boot_receipt(boots_dir: Path, *, pack: dict[str, Any], tick: int, boot_count: int, ledger_head_hash: str) -> None:
    receipt = {
        "schema_version": "daemon_boot_receipt_v1",
        "kind": "BOOT",
        "daemon_id": pack["daemon_id"],
        "icore_id": pack["icore_id"],
        "meta_hash": pack["meta_hash"],
        "tick": int(tick),
        "boot_count": int(boot_count),
        "ledger_head_hash": ledger_head_hash,
        "euid": int(os.geteuid()),
        "created_utc": _now_iso(),
    }
    receipt_hash = sha256_prefixed(canon_bytes(receipt))
    name = f"sha256_{receipt_hash.split(':', 1)[1]}.daemon_boot_receipt_v1.json"
    atomic_write_json(boots_dir / name, receipt)


def _write_shutdown_receipt(shutdown_dir: Path, *, pack: dict[str, Any], tick: int, boot_count: int, ledger_head_hash: str) -> None:
    receipt = {
        "schema_version": "daemon_shutdown_receipt_v1",
        "kind": "SHUTDOWN",
        "daemon_id": pack["daemon_id"],
        "icore_id": pack["icore_id"],
        "meta_hash": pack["meta_hash"],
        "tick": int(tick),
        "boot_count": int(boot_count),
        "ledger_head_hash": ledger_head_hash,
        "created_utc": _now_iso(),
    }
    receipt_hash = sha256_prefixed(canon_bytes(receipt))
    name = f"sha256_{receipt_hash.split(':', 1)[1]}.daemon_shutdown_receipt_v1.json"
    atomic_write_json(shutdown_dir / name, receipt)


def _write_checkpoint_receipt(checkpoint_dir: Path, *, pack: dict[str, Any], tick: int, boot_count: int, ledger_head_hash: str, snapshot_hash: str) -> str:
    receipt = {
        "schema_version": "daemon_checkpoint_receipt_v1",
        "kind": "CHECKPOINT",
        "daemon_id": pack["daemon_id"],
        "icore_id": pack["icore_id"],
        "meta_hash": pack["meta_hash"],
        "tick": int(tick),
        "boot_count": int(boot_count),
        "ledger_head_hash": ledger_head_hash,
        "snapshot_hash": snapshot_hash,
        "created_utc": _now_iso(),
    }
    receipt_hash = sha256_prefixed(canon_bytes(receipt))
    name = f"sha256_{receipt_hash.split(':', 1)[1]}.daemon_checkpoint_receipt_v1.json"
    atomic_write_json(checkpoint_dir / name, receipt)
    return receipt_hash


def _write_service_manifest(config_dir: Path, *, invocation: str, plist_path: str | None) -> None:
    plist_hash = sha256_prefixed(b"")
    plist_path_resolved = plist_path
    if plist_path_resolved is None:
        default_plist = Path.home() / "Library" / "LaunchAgents" / "com.agi-stack.rsi-daemon.v6_0.plist"
        if default_plist.exists():
            plist_path_resolved = str(default_plist)
    if plist_path_resolved:
        p = Path(plist_path_resolved)
        if p.exists():
            plist_hash = sha256_prefixed(p.read_bytes())
    payload = {
        "schema_version": "daemon_service_manifest_v1",
        "plist_path": plist_path_resolved or "",
        "plist_hash": plist_hash,
        "invocation": invocation,
        "invocation_hash": sha256_prefixed(invocation.encode("utf-8")),
    }
    atomic_write_json(config_dir / "daemon_service_manifest_v1.json", payload)


def _select_activity(pack: dict[str, Any], *, tick: int) -> dict[str, Any]:
    activities = list(pack.get("activities") or [])
    if not activities:
        raise CanonError("SCHEMA_INVALID")
    idx = (tick - 1) % len(activities)
    return dict(activities[idx])


def _run_activity(*, daemon_id: str, tick: int, activity: dict[str, Any], runs_root: Path) -> tuple[str, str]:
    kind = str(activity.get("activity_kind"))
    activity_id = str(activity.get("activity_id") or kind)
    receipt = {
        "schema_version": "daemon_activity_receipt_v1",
        "activity_kind": kind,
        "activity_id": activity_id,
        "daemon_id": daemon_id,
        "tick": int(tick),
    }
    receipt_hash = sha256_prefixed(canon_bytes(receipt))
    run_dir = runs_root / f"rsi_daemon_v6_0_tick_{tick}"
    run_dir.mkdir(parents=True, exist_ok=True)
    name = f"sha256_{receipt_hash.split(':', 1)[1]}.daemon_activity_receipt_v1.json"
    path = run_dir / name
    atomic_write_json(path, receipt)
    return receipt_hash, str(path)


def _prune_checkpoints(checkpoint_dir: Path, snapshot_dir: Path, retain_last_n: int) -> None:
    receipts = []
    for path in checkpoint_dir.glob("sha256_*.daemon_checkpoint_receipt_v1.json"):
        try:
            receipt = load_canon_json(path)
        except Exception:
            continue
        tick = int(receipt.get("tick", 0))
        receipts.append((tick, path, receipt))
    receipts.sort(key=lambda item: item[0])
    if len(receipts) <= retain_last_n:
        return
    to_delete = receipts[: len(receipts) - retain_last_n]
    keep = receipts[len(receipts) - retain_last_n :]
    keep_snapshots = {r[2].get("snapshot_hash") for r in keep}
    for _tick, path, receipt in to_delete:
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass
        snap_hash = receipt.get("snapshot_hash")
        if snap_hash and snap_hash not in keep_snapshots:
            name = f"sha256_{str(snap_hash).split(':', 1)[1]}.daemon_state_snapshot_v1.json"
            (snapshot_dir / name).unlink(missing_ok=True)


def _load_checkpoint_receipts(checkpoint_dir: Path) -> list[dict[str, Any]]:
    receipts: list[dict[str, Any]] = []
    if not checkpoint_dir.exists():
        return receipts
    for path in checkpoint_dir.glob("sha256_*.daemon_checkpoint_receipt_v1.json"):
        receipt = load_canon_json(path)
        if not isinstance(receipt, dict):
            raise CanonError("SCHEMA_INVALID")
        if receipt.get("schema_version") != "daemon_checkpoint_receipt_v1" or receipt.get("kind") != "CHECKPOINT":
            raise CanonError("SCHEMA_INVALID")
        receipt_hash = sha256_prefixed(canon_bytes(receipt))
        expected_name = f"sha256_{receipt_hash.split(':', 1)[1]}.daemon_checkpoint_receipt_v1.json"
        if path.name != expected_name:
            raise CanonError("CANON_HASH_MISMATCH")
        receipts.append(receipt)
    return receipts


def run_daemon(pack_path: Path, daemon_root: Path, *, foreground: bool, service_plist: str | None) -> int:
    if os.geteuid() == 0:
        print("DAEMON_REFUSE_ROOT", file=sys.stderr)
        return EXIT_REFUSE_ROOT

    dirs = _ensure_dirs(daemon_root)
    lock = LockFile(dirs["lock"] / "daemon.lock")
    try:
        lock.acquire()
    except RuntimeError:
        print("DAEMON_LOCK_HELD", file=sys.stderr)
        return EXIT_LOCK_HELD

    writer: LedgerWriter | None = None
    tick_engine: TickEngine | None = None
    current_tick = 0
    boot_count = 0

    try:
        pack = _load_pack(pack_path, dirs["config"])
        _daemon_id_ok(pack)
        pack_state_dir = Path(str(pack.get("state_dir", ""))).resolve()
        if pack_state_dir != dirs["state"].resolve():
            raise CanonError("SCHEMA_INVALID")

        invocation = " ".join(sys.argv)
        _write_service_manifest(dirs["config"], invocation=invocation, plist_path=service_plist)

        constants = _require_constants()
        lock_rel = constants.get("IMMUTABLE_CORE_LOCK_REL")
        if not isinstance(lock_rel, str):
            raise CanonError("IMMUTABLE_CORE_ATTESTATION_INVALID")
        lock_path = REPO_ROOT / lock_rel
        if not lock_path.exists():
            raise CanonError("MISSING_ARTIFACT")
        lock_payload = load_lock(lock_path)
        validate_lock(lock_payload)
        expected_icore = str(lock_payload.get("core_id"))
        expected_meta = _meta_hash()

        ledger_path = dirs["ledger"] / "daemon_ledger_v1.jsonl"
        tail_truncated = truncate_incomplete_tail(ledger_path)

        entries: list[dict[str, Any]] = []
        if ledger_path.exists() and ledger_path.read_text(encoding="utf-8").strip():
            entries = load_daemon_ledger(ledger_path)
            head_hash, current_tick, last_seq = validate_daemon_chain(entries)
        else:
            head_hash, current_tick, last_seq = "GENESIS", 0, 0

        entry_by_hash = {ev.get("entry_hash"): ev for ev in entries if isinstance(ev.get("entry_hash"), str)}

        # Validate latest checkpoint snapshot/receipt (fail-closed on mismatch).
        receipts = _load_checkpoint_receipts(dirs["checkpoints"])
        latest_snapshot: dict[str, Any] | None = None
        receipt_meta_drift = False
        if receipts:
            snapshots_present = False
            valid_pairs: list[tuple[int, dict[str, Any], dict[str, Any]]] = []
            for receipt in receipts:
                if receipt.get("daemon_id") != pack.get("daemon_id"):
                    raise CanonError("SCHEMA_INVALID")
                if receipt.get("icore_id") != pack.get("icore_id") or receipt.get("meta_hash") != pack.get("meta_hash"):
                    receipt_meta_drift = True

                snapshot_hash = str(receipt.get("snapshot_hash", ""))
                if not snapshot_hash.startswith("sha256:"):
                    raise CanonError("DAEMON_CHECKPOINT_MISMATCH")
                snap_name = f"sha256_{snapshot_hash.split(':', 1)[1]}.daemon_state_snapshot_v1.json"
                snap_path = dirs["snapshots"] / snap_name
                if not snap_path.exists():
                    raise CanonError("DAEMON_CHECKPOINT_MISMATCH")
                snapshots_present = True
                snapshot = load_snapshot(snap_path)
                expected_snap_hash = compute_snapshot_hash(snapshot)
                if expected_snap_hash != snapshot_hash:
                    raise CanonError("DAEMON_CHECKPOINT_MISMATCH")
                if snapshot.get("daemon_id") != receipt.get("daemon_id"):
                    raise CanonError("DAEMON_CHECKPOINT_MISMATCH")
                if snapshot.get("icore_id") != receipt.get("icore_id") or snapshot.get("meta_hash") != receipt.get("meta_hash"):
                    raise CanonError("DAEMON_CHECKPOINT_MISMATCH")
                if snapshot.get("ledger_head_hash") != receipt.get("ledger_head_hash"):
                    raise CanonError("DAEMON_CHECKPOINT_MISMATCH")
                if snapshot.get("tick") != receipt.get("tick"):
                    raise CanonError("DAEMON_CHECKPOINT_MISMATCH")
                if snapshot.get("boot_count") != receipt.get("boot_count"):
                    raise CanonError("DAEMON_CHECKPOINT_MISMATCH")
                ledger_head_hash = str(receipt.get("ledger_head_hash", ""))
                ledger_entry = entry_by_hash.get(ledger_head_hash)
                if ledger_entry is None or ledger_entry.get("event_type") != "CHECKPOINT":
                    raise CanonError("DAEMON_CHECKPOINT_MISMATCH")
                valid_pairs.append((int(receipt.get("tick", 0)), receipt, snapshot))

            if not snapshots_present:
                raise CanonError("DAEMON_CHECKPOINT_MISMATCH")

            valid_pairs.sort(key=lambda item: item[0])
            latest_snapshot = valid_pairs[-1][2]
        else:
            if entries:
                raise CanonError("DAEMON_CHECKPOINT_MISMATCH")
            if dirs["snapshots"].exists() and any(dirs["snapshots"].glob("sha256_*.daemon_state_snapshot_v1.json")):
                raise CanonError("DAEMON_CHECKPOINT_MISMATCH")

        meta_drift = False
        pinned_icore = str(pack.get("icore_id", ""))
        pinned_meta = str(pack.get("meta_hash", ""))
        if latest_snapshot is not None:
            if latest_snapshot.get("daemon_id") != pack.get("daemon_id"):
                raise CanonError("SCHEMA_INVALID")
            pinned_icore = str(latest_snapshot.get("icore_id", ""))
            pinned_meta = str(latest_snapshot.get("meta_hash", ""))
            if pinned_icore != pack.get("icore_id") or pinned_meta != pack.get("meta_hash"):
                meta_drift = True

        if receipt_meta_drift:
            meta_drift = True

        if pinned_icore != expected_icore or pinned_meta != expected_meta:
            meta_drift = True

        if meta_drift:
            writer = LedgerWriter(ledger_path, prev_hash=head_hash, seq=last_seq)
            writer.append(event_type="META_DRIFT_DETECTED", event_payload={}, tick=current_tick)
            writer.append(event_type="PAUSED", event_payload={"reason": "META_DRIFT_DETECTED"}, tick=current_tick)
            write_health_report(
                dirs["health"] / "daemon_health_report_v1.json",
                daemon_id=pack["daemon_id"],
                icore_id=pack["icore_id"],
                meta_hash=pack["meta_hash"],
                tick=current_tick,
                boot_count=int(0),
                ledger_head_hash=writer.prev_hash,
                status="PAUSED",
                paused_reason="META_DRIFT_DETECTED",
            )
            print("DAEMON_META_DRIFT", file=sys.stderr)
            return EXIT_META_DRIFT

        snapshot = latest_snapshot
        if snapshot is None:
            snapshot, _snap_hash = load_latest_snapshot(dirs["snapshots"])
        boot_count = int(snapshot.get("boot_count", 0)) if snapshot else 0
        budget_counters = BudgetCounters.from_dict(snapshot.get("budget_counters") if snapshot else None)
        budget_counters.ticks_this_boot = 0
        budget_counters.work_units_today = 0

        if snapshot is not None:
            snap_tick = int(snapshot.get("tick", 0))
            if current_tick < snap_tick:
                raise CanonError("DAEMON_LEDGER_CORRUPT")

        writer = LedgerWriter(ledger_path, prev_hash=head_hash, seq=last_seq)
        if tail_truncated:
            writer.append(event_type="RECOVERY_TAIL_TRUNCATED", event_payload={}, tick=current_tick)

        boot_count += 1
        boot_entry = writer.append(event_type="BOOT", event_payload={"boot_count": boot_count}, tick=current_tick)
        _write_boot_receipt(dirs["boots"], pack=pack, tick=current_tick, boot_count=boot_count, ledger_head_hash=boot_entry["entry_hash"])

        tick_engine = TickEngine(current_tick=current_tick, budgets=dict(pack.get("budgets") or {}), counters=budget_counters)
        control = ControlPlane(dirs["control"])
        control.install_signal_handlers()

        stop_logged = False
        paused = False
        last_checkpoint_hash: str | None = None

        while True:
            _check_disk(daemon_root)
            _check_ledger_size(ledger_path)
            _rotate_log(dirs["logs"] / "daemon_stdout.log")
            _rotate_log(dirs["logs"] / "daemon_stderr.log")

            control.refresh()
            if control.stop_requested:
                if not stop_logged:
                    writer.append(event_type="STOP_REQUESTED", event_payload={}, tick=tick_engine.current_tick)
                    stop_logged = True
                break

            if control.pause_requested:
                if not paused:
                    writer.append(event_type="PAUSED", event_payload={"reason": "OPERATOR_PAUSE"}, tick=tick_engine.current_tick)
                    paused = True
                write_health_report(
                    dirs["health"] / "daemon_health_report_v1.json",
                    daemon_id=pack["daemon_id"],
                    icore_id=pack["icore_id"],
                    meta_hash=pack["meta_hash"],
                    tick=tick_engine.current_tick,
                    boot_count=boot_count,
                    ledger_head_hash=writer.prev_hash,
                    status="PAUSED",
                    paused_reason="OPERATOR_PAUSE",
                )
                time.sleep(0.1)
                continue

            if paused:
                writer.append(event_type="RESUMED", event_payload={}, tick=tick_engine.current_tick)
                paused = False

            if not tick_engine.can_advance():
                writer.append(event_type="PAUSED", event_payload={"reason": "BUDGET_EXCEEDED"}, tick=tick_engine.current_tick)
                paused = True
                write_health_report(
                    dirs["health"] / "daemon_health_report_v1.json",
                    daemon_id=pack["daemon_id"],
                    icore_id=pack["icore_id"],
                    meta_hash=pack["meta_hash"],
                    tick=tick_engine.current_tick,
                    boot_count=boot_count,
                    ledger_head_hash=writer.prev_hash,
                    status="PAUSED",
                    paused_reason="BUDGET_EXCEEDED",
                )
                time.sleep(0.1)
                continue

            tick = tick_engine.next_tick()
            current_tick = tick_engine.current_tick
            writer.append(event_type="TICK_BEGIN", event_payload={"tick": tick}, tick=tick)

            activity = _select_activity(pack, tick=tick)
            receipt_hash, receipt_path = _run_activity(
                daemon_id=pack["daemon_id"],
                tick=tick,
                activity=activity,
                runs_root=REPO_ROOT / "runs",
            )
            writer.append(
                event_type="ACTIVITY_DONE",
                event_payload={
                    "activity_kind": activity.get("activity_kind"),
                    "activity_id": activity.get("activity_id"),
                    "activity_receipt_hash": receipt_hash,
                    "activity_receipt_path": receipt_path,
                },
                tick=tick,
            )
            tick_engine.record_work_units(1)

            checkpoint_every = int((pack.get("checkpoint_policy") or {}).get("every_ticks", 1))
            if checkpoint_every > 0 and tick % checkpoint_every == 0:
                checkpoint_entry = writer.append(event_type="CHECKPOINT", event_payload={}, tick=tick)
                snapshot_payload = {
                    "schema_version": "daemon_state_snapshot_v1",
                    "daemon_id": pack["daemon_id"],
                    "icore_id": pack["icore_id"],
                    "meta_hash": pack["meta_hash"],
                    "tick": tick,
                    "ledger_head_hash": checkpoint_entry["entry_hash"],
                    "last_checkpoint_hash": last_checkpoint_hash,
                    "boot_count": boot_count,
                    "paused_reason": None,
                    "budget_counters": tick_engine.counters.to_dict(),
                }
                snapshot_hash, _ = write_snapshot(dirs["snapshots"], snapshot_payload)
                last_checkpoint_hash = _write_checkpoint_receipt(
                    dirs["checkpoints"],
                    pack=pack,
                    tick=tick,
                    boot_count=boot_count,
                    ledger_head_hash=checkpoint_entry["entry_hash"],
                    snapshot_hash=snapshot_hash,
                )
                retain_n = int((pack.get("checkpoint_policy") or {}).get("retain_last_n", 1))
                if retain_n > 0:
                    _prune_checkpoints(dirs["checkpoints"], dirs["snapshots"], retain_n)

            write_health_report(
                dirs["health"] / "daemon_health_report_v1.json",
                daemon_id=pack["daemon_id"],
                icore_id=pack["icore_id"],
                meta_hash=pack["meta_hash"],
                tick=tick_engine.current_tick,
                boot_count=boot_count,
                ledger_head_hash=writer.prev_hash,
                status="RUNNING",
                paused_reason=None,
            )

            if foreground:
                time.sleep(0.01)

        shutdown_entry = writer.append(event_type="SHUTDOWN", event_payload={}, tick=tick_engine.current_tick)
        _write_shutdown_receipt(
            dirs["shutdowns"],
            pack=pack,
            tick=tick_engine.current_tick,
            boot_count=boot_count,
            ledger_head_hash=shutdown_entry["entry_hash"],
        )
        write_health_report(
            dirs["health"] / "daemon_health_report_v1.json",
            daemon_id=pack["daemon_id"],
            icore_id=pack["icore_id"],
            meta_hash=pack["meta_hash"],
            tick=tick_engine.current_tick,
            boot_count=boot_count,
            ledger_head_hash=shutdown_entry["entry_hash"],
            status="STOPPED",
            paused_reason=None,
        )
        return 0
    except CanonError as exc:
        reason = str(exc)
        exit_code = {
            "DAEMON_DISK_LOW": EXIT_DISK_LOW,
            "DAEMON_LEDGER_CORRUPT": EXIT_LEDGER_CORRUPT,
            "DAEMON_CHECKPOINT_MISMATCH": EXIT_CHECKPOINT_MISMATCH,
        }.get(reason, EXIT_FATAL)
        if writer is not None:
            try:
                writer.append(event_type="FATAL", event_payload={"reason": reason}, tick=current_tick)
            except Exception:  # noqa: BLE001
                pass
        if exit_code == EXIT_FATAL:
            print(f"DAEMON_FATAL_UNHANDLED: {reason}", file=sys.stderr)
        else:
            print(reason, file=sys.stderr)
        return exit_code
    finally:
        lock.release()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--daemon_pack", required=True)
    parser.add_argument("--daemon_root", required=True)
    parser.add_argument("--foreground", action="store_true")
    parser.add_argument("--service_plist")
    args = parser.parse_args(argv)
    return run_daemon(Path(args.daemon_pack), Path(args.daemon_root), foreground=bool(args.foreground), service_plist=args.service_plist)


__all__ = ["main", "run_daemon"]
