#!/usr/bin/env python3
"""Seed flagship polymath domain blobs into canonical store (v1)."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _entry in (_REPO_ROOT, _REPO_ROOT / "CDEL-v2"):
    _value = str(_entry)
    if _value not in sys.path:
        sys.path.insert(0, _value)

from cdel.v18_0.omega_common_v1 import load_canon_dict
from tools.polymath.polymath_dataset_fetch_v1 import polymath_store_root

_DEFAULT_DOMAIN_ID = "pubchem_weight300"
_DEFAULT_DOMAIN_PACK_REL = "domains/pubchem_weight300/domain_pack_l0_v1.json"
_DEFAULT_SUMMARY_BASENAME = "OMEGA_POLYMATH_SEED_FLAGSHIPS_SUMMARY_v1.json"


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _default_summary_path() -> Path:
    return (Path.cwd() / _DEFAULT_SUMMARY_BASENAME).resolve()


def _blob_path(store_root: Path, sha256: str) -> Path:
    if not isinstance(sha256, str) or not sha256.startswith("sha256:"):
        raise RuntimeError("invalid sha256")
    digest = sha256.split(":", 1)[1].strip().lower()
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise RuntimeError("invalid sha256")
    return store_root / "blobs" / "sha256" / digest


def _required_sha256s_from_domain_pack(path: Path) -> list[str]:
    payload = load_canon_dict(path)
    if str(payload.get("schema_version", "")).strip() != "polymath_domain_pack_v1":
        raise RuntimeError("domain pack schema_version mismatch")

    tasks = payload.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise RuntimeError("domain pack tasks missing")
    task = tasks[0]
    if not isinstance(task, dict):
        raise RuntimeError("domain pack tasks[0] invalid")
    split = task.get("split")
    if not isinstance(split, dict):
        raise RuntimeError("domain pack split missing")
    train_sha256 = str(split.get("train_sha256", "")).strip()
    test_sha256 = str(split.get("test_sha256", "")).strip()
    if not train_sha256:
        raise RuntimeError("domain pack train_sha256 missing")
    if not test_sha256:
        raise RuntimeError("domain pack test_sha256 missing")

    dataset_artifacts = payload.get("dataset_artifacts")
    if not isinstance(dataset_artifacts, list):
        raise RuntimeError("domain pack dataset_artifacts missing")

    out = {train_sha256, test_sha256}
    for row in dataset_artifacts:
        if not isinstance(row, dict):
            raise RuntimeError("domain pack dataset_artifacts item invalid")
        sha256 = str(row.get("sha256", "")).strip()
        if not sha256:
            raise RuntimeError("domain pack dataset artifact sha256 missing")
        out.add(sha256)

    return sorted(out)


def _missing_sha256s(*, store_root: Path, required_sha256s: list[str]) -> list[str]:
    missing: list[str] = []
    for sha256 in required_sha256s:
        blob = _blob_path(store_root, sha256)
        if not blob.exists() or not blob.is_file():
            missing.append(sha256)
    return sorted(missing)


def _write_summary(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, separators=(",", ":")) + "\n", encoding="utf-8")


def run(
    *,
    store_root_arg: str,
    domain_id: str,
    domain_pack_rel: str,
    summary_path: Path,
    seed_tmp_root_arg: str,
) -> tuple[dict[str, Any], int]:
    resolved_store_root = polymath_store_root(Path(store_root_arg).expanduser().resolve() if store_root_arg else None)
    resolved_domain_pack_path = (_REPO_ROOT / domain_pack_rel).resolve()
    resolved_seed_tmp_root = (
        Path(seed_tmp_root_arg).expanduser().resolve()
        if seed_tmp_root_arg
        else (resolved_store_root / "refinery" / "seed_tmp").resolve()
    )

    required_sha256s: list[str] = []
    missing_before_sha256s: list[str] = []
    missing_after_sha256s: list[str] = []
    builder_ran_b = False
    status = "OK"
    exit_code = 0

    try:
        required_sha256s = _required_sha256s_from_domain_pack(resolved_domain_pack_path)
        missing_before_sha256s = _missing_sha256s(store_root=resolved_store_root, required_sha256s=required_sha256s)
        if missing_before_sha256s:
            builder_ran_b = True
            builder_cmd = [
                sys.executable,
                str(_REPO_ROOT / "tools" / "polymath" / "polymath_build_flagship_pubchem_weight300_v1.py"),
                "--fixture_path",
                str(_REPO_ROOT / "tools" / "polymath" / "fixtures" / "pubchem_weight300_snapshot_v1.json"),
                "--domain_root",
                str((resolved_seed_tmp_root / _DEFAULT_DOMAIN_ID).resolve()),
                "--store_root",
                str(resolved_store_root),
            ]
            run = subprocess.run(builder_cmd, cwd=_REPO_ROOT, capture_output=True, text=True, check=False)
            missing_after_sha256s = _missing_sha256s(store_root=resolved_store_root, required_sha256s=required_sha256s)
            if int(run.returncode) != 0 or missing_after_sha256s:
                status = "FAIL"
                exit_code = 2
        else:
            missing_after_sha256s = []
    except Exception:  # noqa: BLE001
        status = "FAIL"
        exit_code = 2
        missing_after_sha256s = list(missing_before_sha256s)

    summary = {
        "schema_version": "OMEGA_POLYMATH_SEED_FLAGSHIPS_SUMMARY_v1",
        "created_at_utc": _utc_now_iso(),
        "store_root": resolved_store_root.as_posix(),
        "domain_id": str(domain_id),
        "domain_pack_path": resolved_domain_pack_path.as_posix(),
        "required_sha256s": [str(row) for row in required_sha256s],
        "missing_before_sha256s": [str(row) for row in missing_before_sha256s],
        "builder_ran_b": bool(builder_ran_b),
        "missing_after_sha256s": [str(row) for row in missing_after_sha256s],
        "status": status,
    }
    _write_summary(summary_path, summary)
    return summary, int(exit_code)


def main() -> None:
    parser = argparse.ArgumentParser(prog="polymath_seed_flagships_v1")
    parser.add_argument("--store_root", default="")
    parser.add_argument("--domain_id", default=_DEFAULT_DOMAIN_ID)
    parser.add_argument("--domain_pack_rel", default=_DEFAULT_DOMAIN_PACK_REL)
    parser.add_argument("--summary_path", default="")
    parser.add_argument("--seed_tmp_root", default="")
    args = parser.parse_args()

    summary_path = (
        Path(str(args.summary_path)).expanduser().resolve()
        if str(args.summary_path).strip()
        else _default_summary_path()
    )
    _, exit_code = run(
        store_root_arg=str(args.store_root).strip(),
        domain_id=str(args.domain_id).strip() or _DEFAULT_DOMAIN_ID,
        domain_pack_rel=str(args.domain_pack_rel).strip() or _DEFAULT_DOMAIN_PACK_REL,
        summary_path=summary_path,
        seed_tmp_root_arg=str(args.seed_tmp_root).strip(),
    )
    print(summary_path.as_posix())
    if int(exit_code) != 0:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
