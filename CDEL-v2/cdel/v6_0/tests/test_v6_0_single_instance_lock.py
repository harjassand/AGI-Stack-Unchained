from __future__ import annotations

from pathlib import Path
import sys
from multiprocessing import Process, Queue

import pytest


def _attempt_lock(lock_path: Path, q: Queue) -> None:
    repo_root = Path(__file__).resolve().parents[4]
    orch_root = repo_root / "Extension-1" / "agi-orchestrator"
    sys.path.insert(0, str(orch_root))
    from orchestrator.daemon_v6_0.lockfile_v1 import LockFile

    lock = LockFile(lock_path)
    try:
        lock.acquire()
    except RuntimeError:
        q.put("locked")
        return
    q.put("acquired")
    lock.release()


def test_v6_0_single_instance_lock(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[4]
    orch_root = repo_root / "Extension-1" / "agi-orchestrator"
    sys.path.insert(0, str(orch_root))
    from orchestrator.daemon_v6_0.lockfile_v1 import LockFile

    lock_path = tmp_path / "daemon.lock"
    lock1 = LockFile(lock_path)
    lock1.acquire()
    try:
        q: Queue = Queue()
        proc = Process(target=_attempt_lock, args=(lock_path, q))
        proc.start()
        proc.join(timeout=5)
        assert q.get() == "locked"
    finally:
        lock1.release()
