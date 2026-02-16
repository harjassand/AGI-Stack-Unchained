#!/usr/bin/env python3
"""Collect completion bundle artifacts without copying heldout bytes."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Iterable


def _safe_copy(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)


def _copy_tree(src: Path, dest: Path, *, suffixes: Iterable[str]) -> None:
    for path in sorted(src.glob("*")):
        if not path.is_file():
            continue
        if path.suffix not in suffixes:
            continue
        _safe_copy(path, dest / path.name)


def _git_rev(repo_root: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repo_root, text=True
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def _cdel_pin(repo_root: Path) -> str:
    pyproject = repo_root / "pyproject.toml"
    if not pyproject.exists():
        return ""
    text = pyproject.read_text(encoding="utf-8")
    marker = "cdel[sealed] @ "
    for line in text.splitlines():
        if "cdel[sealed]" in line and "@ git+" in line:
            return line.strip().strip('"').strip("'")
    for line in text.splitlines():
        if marker in line:
            return line.strip()
    return ""


def _write_manifest(bundle_dir: Path, summary_path: Path, run_dir: Path, repo_root: Path) -> None:
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    certs = sorted(run_dir.glob("*_heldout_cert.json"))
    requests = sorted(run_dir.glob("*_heldout_request.json"))
    manifest = {
        "run_id": summary.get("run_id"),
        "git_rev": _git_rev(repo_root),
        "cdel_pin": _cdel_pin(repo_root),
        "summary_path": str(summary_path),
        "certs": [p.name for p in certs],
        "requests": [p.name for p in requests],
    }
    (bundle_dir / "manifest.json").write_text(
        json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8"
    )


def _assert_no_jsonl(bundle_dir: Path) -> None:
    for path in bundle_dir.rglob("*.jsonl"):
        raise RuntimeError(f"bundle contains jsonl: {path}")


def collect_bundle(
    *, repo_root: Path, bundle_dir: Path, capstone_dir: Path
) -> None:
    if bundle_dir.exists():
        shutil.rmtree(bundle_dir)
    bundle_dir.mkdir(parents=True, exist_ok=True)

    summary_path = capstone_dir / "capstone_ae_summary.json"
    if not summary_path.exists():
        raise FileNotFoundError(f"capstone summary missing: {summary_path}")

    _safe_copy(summary_path, bundle_dir / "capstone_ae_summary.json")

    run_artifacts = bundle_dir / "run_artifacts"
    for path in sorted(capstone_dir.glob("*_heldout_cert.json")):
        _safe_copy(path, run_artifacts / path.name)
    for path in sorted(capstone_dir.glob("*_heldout_request.json")):
        _safe_copy(path, run_artifacts / path.name)

    _write_manifest(bundle_dir, summary_path, capstone_dir, repo_root)

    _copy_tree(repo_root / "suites", bundle_dir / "suite_pointers_snapshot", suffixes=(".json",))
    _copy_tree(repo_root / "configs", bundle_dir / "configs_snapshot", suffixes=(".toml",))

    _assert_no_jsonl(bundle_dir)


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect completion bundle artifacts.")
    parser.add_argument("--bundle-dir", default="completion_bundle")
    parser.add_argument("--capstone-dir", default="runs/capstone_ae")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    collect_bundle(
        repo_root=repo_root,
        bundle_dir=repo_root / args.bundle_dir,
        capstone_dir=repo_root / args.capstone_dir,
    )
    print(str((repo_root / args.bundle_dir).resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
