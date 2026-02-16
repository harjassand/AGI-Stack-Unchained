#!/usr/bin/env python3
"""Deterministic replay manifest writer and verifier for Omega overnight runs."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MANIFEST_NAME = "OMEGA_REPLAY_MANIFEST_v1.json"
_EMPTY_SHA = "sha256:"
_REPLAY_FILENAMES = (
    "OMEGA_OVERNIGHT_REPORT_v1.json",
    "OMEGA_BENCHMARK_GATES_v1.json",
    "OMEGA_GATE_PROOF_v1.json",
    "OMEGA_DIAGNOSTIC_PACKET_v1.json",
    "OMEGA_PROMOTION_SUMMARY_v1.json",
    "OMEGA_RUN_SCORECARD_v1.json",
    "OMEGA_TIMINGS_AGG_v1.json",
    "OMEGA_VOID_TO_GOALS_REPORT_v1.json",
    "OMEGA_BENCHMARK_SUMMARY_v1.md",
    "OMEGA_LLM_ROUTER_PLAN_v1.json",
    "OMEGA_LLM_TOOL_TRACE_v1.jsonl",
)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _git_rev_parse(path: Path) -> str:
    run = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=path,
        check=False,
        capture_output=True,
        text=True,
    )
    if int(run.returncode) != 0:
        return ""
    return str(run.stdout).strip()


def _sha_or_empty(path: Path | None) -> str:
    if path is None:
        return _EMPTY_SHA
    abs_path = path.expanduser().resolve()
    if not abs_path.exists() or not abs_path.is_file():
        return _EMPTY_SHA
    return hash_file_sha256_prefixed(abs_path)


def hash_file_sha256_prefixed(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def collect_replay_artifacts(run_dir: Path) -> list[Path]:
    run_root = run_dir.expanduser().resolve()
    out: list[Path] = []
    seen: set[str] = set()

    def _append(path: Path) -> None:
        resolved = path.resolve()
        key = resolved.as_posix()
        if key in seen:
            return
        seen.add(key)
        out.append(resolved)

    for name in _REPLAY_FILENAMES:
        candidate = run_root / name
        if candidate.exists() and candidate.is_file():
            _append(candidate)
    replay_jsonl = run_root / "_overnight_pack" / "replay" / "orch_llm_replay.jsonl"
    if replay_jsonl.exists() and replay_jsonl.is_file():
        _append(replay_jsonl)
    polymath_store = run_root / "polymath" / "store"
    if polymath_store.exists() and polymath_store.is_dir():
        for path in sorted(polymath_store.rglob("*"), key=lambda row: row.as_posix()):
            if path.is_file():
                _append(path)
    out.sort(key=lambda row: row.as_posix())
    return out


def collect_state_roots(run_dir: Path) -> list[Path]:
    run_root = run_dir.expanduser().resolve()
    daemon_root = run_root / "daemon"
    if not daemon_root.exists() or not daemon_root.is_dir():
        return []
    seen: set[str] = set()
    rows: list[Path] = []
    for pattern in ("**/state", "**/subruns"):
        for path in sorted(daemon_root.glob(pattern), key=lambda row: row.as_posix()):
            if not path.exists() or not path.is_dir():
                continue
            resolved = path.resolve()
            key = resolved.as_posix()
            if key in seen:
                continue
            seen.add(key)
            rows.append(resolved)
    rows.sort(key=lambda row: row.as_posix())
    return rows


def write_replay_manifest(
    run_dir: Path,
    *,
    series_prefix: str,
    profile: str,
    meta_core_mode: str,
    campaign_pack_path: Path,
    capability_registry_path: Path | None,
    goal_queue_effective_path: Path | None,
) -> Path:
    run_root = run_dir.expanduser().resolve()
    run_root.mkdir(parents=True, exist_ok=True)

    campaign_pack_abs = campaign_pack_path.expanduser().resolve()
    capability_registry_abs = capability_registry_path.expanduser().resolve() if capability_registry_path is not None else None
    goal_queue_abs = goal_queue_effective_path.expanduser().resolve() if goal_queue_effective_path is not None else None

    artifacts = [
        {"path": artifact.as_posix(), "sha256": hash_file_sha256_prefixed(artifact)}
        for artifact in collect_replay_artifacts(run_root)
    ]
    state_roots = [path.as_posix() for path in collect_state_roots(run_root)]

    manifest = {
        "schema_version": "OMEGA_REPLAY_MANIFEST_v1",
        "run_dir": run_root.as_posix(),
        "series_prefix": str(series_prefix),
        "profile": str(profile),
        "meta_core_mode": str(meta_core_mode),
        "git": {
            "agi_stack_head_sha": _git_rev_parse(_REPO_ROOT),
            "cdel_submodule_sha": _git_rev_parse(_REPO_ROOT / "CDEL-v2") if (_REPO_ROOT / "CDEL-v2").exists() else "",
        },
        "inputs": {
            "campaign_pack_path": campaign_pack_abs.as_posix(),
            "campaign_pack_sha256": _sha_or_empty(campaign_pack_abs),
            "capability_registry_path": capability_registry_abs.as_posix() if capability_registry_abs is not None else "",
            "capability_registry_sha256": _sha_or_empty(capability_registry_abs),
            "goal_queue_effective_path": goal_queue_abs.as_posix() if goal_queue_abs is not None else "",
            "goal_queue_effective_sha256": _sha_or_empty(goal_queue_abs),
        },
        "artifacts": artifacts,
        "state_roots": state_roots,
    }
    out_path = run_root / _MANIFEST_NAME
    _write_json(out_path, manifest)
    return out_path


def verify_existing_manifest(run_dir: Path) -> tuple[bool, str, list[dict[str, str]]]:
    run_root = run_dir.expanduser().resolve()
    manifest_path = run_root / _MANIFEST_NAME
    if not manifest_path.exists() or not manifest_path.is_file():
        return False, "REPLAY_VERIFY_MANIFEST_MISSING", []
    try:
        manifest = _load_json(manifest_path)
    except Exception:  # noqa: BLE001
        return False, "REPLAY_VERIFY_MANIFEST_INVALID", []
    if not isinstance(manifest, dict):
        return False, "REPLAY_VERIFY_MANIFEST_INVALID", []

    details: list[dict[str, str]] = []

    inputs = manifest.get("inputs")
    if isinstance(inputs, dict):
        for path_key, sha_key in (
            ("campaign_pack_path", "campaign_pack_sha256"),
            ("capability_registry_path", "capability_registry_sha256"),
            ("goal_queue_effective_path", "goal_queue_effective_sha256"),
        ):
            path_value = str(inputs.get(path_key, "")).strip()
            expected_sha = str(inputs.get(sha_key, _EMPTY_SHA)).strip()
            if not path_value:
                continue
            abs_path = Path(path_value)
            if not abs_path.exists() or not abs_path.is_file():
                details.append({"reason_code": "MISSING_FILE", "path": abs_path.as_posix()})
                continue
            observed_sha = hash_file_sha256_prefixed(abs_path)
            if expected_sha != observed_sha:
                details.append(
                    {
                        "reason_code": "SHA_MISMATCH",
                        "path": abs_path.as_posix(),
                    }
                )

    artifacts = manifest.get("artifacts")
    if isinstance(artifacts, list):
        for row in artifacts:
            if not isinstance(row, dict):
                continue
            path_value = str(row.get("path", "")).strip()
            expected_sha = str(row.get("sha256", _EMPTY_SHA)).strip()
            if not path_value:
                continue
            abs_path = Path(path_value)
            if not abs_path.exists() or not abs_path.is_file():
                details.append({"reason_code": "MISSING_FILE", "path": abs_path.as_posix()})
                continue
            observed_sha = hash_file_sha256_prefixed(abs_path)
            if expected_sha != observed_sha:
                details.append({"reason_code": "SHA_MISMATCH", "path": abs_path.as_posix()})

    state_roots = manifest.get("state_roots")
    if isinstance(state_roots, list):
        for row in state_roots:
            path_value = str(row).strip()
            if not path_value:
                continue
            abs_path = Path(path_value)
            if not abs_path.exists() or not abs_path.is_dir():
                details.append({"reason_code": "MISSING_STATE_ROOT", "path": abs_path.as_posix()})

    details.sort(key=lambda row: (str(row.get("path", "")), str(row.get("reason_code", ""))))
    if not details:
        return True, "OK", []

    reason_codes = {str(row.get("reason_code", "")) for row in details}
    if "SHA_MISMATCH" in reason_codes:
        return False, "REPLAY_VERIFY_SHA_MISMATCH", details
    return False, "REPLAY_VERIFY_PATH_MISSING", details


def main() -> None:
    parser = argparse.ArgumentParser(prog="omega_replay_bundle_v1")
    parser.add_argument("--run_dir", required=True)
    parser.add_argument("--series_prefix", default="")
    parser.add_argument("--profile", default="")
    parser.add_argument("--meta_core_mode", default="")
    parser.add_argument("--campaign_pack", default="")
    parser.add_argument("--capability_registry", default="")
    parser.add_argument("--goal_queue_effective", default="")
    parser.add_argument("--verify_existing", type=int, default=0)
    args = parser.parse_args()

    run_dir = Path(args.run_dir).expanduser().resolve()
    verify_existing_b = bool(int(args.verify_existing))
    manifest_path = run_dir / _MANIFEST_NAME

    if not str(args.campaign_pack).strip():
        if not verify_existing_b:
            raise SystemExit("--campaign_pack is required unless --verify_existing 1 is set")
    else:
        capability_registry_path = Path(args.capability_registry).expanduser().resolve() if str(args.capability_registry).strip() else None
        goal_queue_path = Path(args.goal_queue_effective).expanduser().resolve() if str(args.goal_queue_effective).strip() else None
        manifest_path = write_replay_manifest(
            run_dir=run_dir,
            series_prefix=str(args.series_prefix),
            profile=str(args.profile),
            meta_core_mode=str(args.meta_core_mode),
            campaign_pack_path=Path(args.campaign_pack),
            capability_registry_path=capability_registry_path,
            goal_queue_effective_path=goal_queue_path,
        )

    if verify_existing_b:
        ok_b, reason_code, details = verify_existing_manifest(run_dir)
        if not ok_b:
            sys.stderr.write(json.dumps({"reason_code": reason_code, "details": details}, sort_keys=True, separators=(",", ":")) + "\n")
            raise SystemExit(1)
    print(manifest_path.as_posix())


if __name__ == "__main__":
    main()
