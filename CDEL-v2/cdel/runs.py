"""Run directory lifecycle utilities."""

from __future__ import annotations

import shutil
import time
from datetime import datetime
from pathlib import Path
import json


def _classify_run(run_dir: Path) -> str:
    status_path = run_dir / "STATUS.json"
    if not status_path.exists():
        return "legacy"
    try:
        status = json.loads(status_path.read_text(encoding="utf-8"))
    except Exception:
        return "legacy"
    if (run_dir / "DONE").exists() and status.get("status") == "complete":
        return "complete"
    if (run_dir / "FAILED.json").exists() or status.get("status") == "failed":
        return "failed"
    return "incomplete"


def gc_runs(root: Path, policy: str = "keep", days: int = 7) -> dict:
    root = root.resolve()
    if not root.exists():
        raise SystemExit(f"runs root does not exist: {root}")

    summary = {"root": str(root), "policy": policy, "archived": [], "deleted": [], "kept": []}
    cutoff = time.time() - (days * 86400)
    archive_dir = None
    if policy == "archive":
        stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        archive_dir = root / "_archive" / stamp
        archive_dir.mkdir(parents=True, exist_ok=True)

    for run_dir in sorted(p for p in root.iterdir() if p.is_dir() and p.name != "_archive"):
        status = _classify_run(run_dir)
        if policy == "keep":
            summary["kept"].append({"run_id": run_dir.name, "status": status})
            continue
        if status == "complete":
            summary["kept"].append({"run_id": run_dir.name, "status": status})
            continue
        if policy == "archive":
            dest = archive_dir / run_dir.name
            if dest.exists():
                shutil.rmtree(dest)
            shutil.move(str(run_dir), str(dest))
            summary["archived"].append({"run_id": run_dir.name, "status": status})
            continue
        if policy == "delete":
            mtime = run_dir.stat().st_mtime
            if mtime < cutoff:
                shutil.rmtree(run_dir)
                summary["deleted"].append({"run_id": run_dir.name, "status": status})
            else:
                summary["kept"].append({"run_id": run_dir.name, "status": status})
            continue
    return summary
