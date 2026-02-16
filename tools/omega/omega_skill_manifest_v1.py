#!/usr/bin/env python3
"""Generate a unified Omega skill manifest from campaign registries and CDEL verifiers."""

from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_VERSION_RE = re.compile(r"(v[0-9]+_[0-9]+[a-z]*)")


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"invalid json object: {path}")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def _registry_paths(repo_root: Path) -> list[Path]:
    rows: list[Path] = []
    rows.extend(sorted((repo_root / "campaigns").glob("**/omega_capability_registry_v2.json"), key=lambda p: p.as_posix()))
    rows.extend(sorted((repo_root / "daemon").glob("**/config/omega_capability_registry_v2.json"), key=lambda p: p.as_posix()))
    uniq: list[Path] = []
    seen: set[str] = set()
    for path in rows:
        key = path.resolve().as_posix()
        if key in seen:
            continue
        seen.add(key)
        uniq.append(path)
    return uniq


def _discover_verifier_modules(repo_root: Path) -> set[str]:
    root = (repo_root / "CDEL-v2" / "cdel").resolve()
    if not root.exists() or not root.is_dir():
        return set()
    out: set[str] = set()
    for path in sorted(root.glob("v*/**/verify*.py"), key=lambda p: p.as_posix()):
        if not path.is_file():
            continue
        try:
            rel = path.relative_to((repo_root / "CDEL-v2").resolve())
        except ValueError:
            continue
        module = rel.as_posix().replace("/", ".")
        if module.endswith(".py"):
            module = module[:-3]
        out.add(module)
    return out


def _extract_version(*, campaign_id: str, orchestrator_module: str, verifier_module: str) -> str:
    for candidate in (verifier_module, orchestrator_module, campaign_id):
        match = _VERSION_RE.search(str(candidate))
        if match:
            return str(match.group(1))
    return ""


def _family_from_capability(capability_id: str) -> str:
    value = str(capability_id).strip().upper()
    if value.startswith("RSI_SAS_"):
        return value.split("RSI_SAS_", 1)[1].split("_", 1)[0]
    if value.startswith("RSI_POLYMATH_"):
        return "POLYMATH"
    if value.startswith("RSI_GE_"):
        return "GE"
    if value.startswith("RSI_OMEGA_"):
        return "OMEGA"
    if value.startswith("RSI_"):
        tail = value.split("RSI_", 1)[1]
        return tail.split("_", 1)[0]
    return "UNKNOWN"


def _skill_id(*, capability_id: str, cdel_version: str) -> str:
    cap = str(capability_id).strip().upper()
    if cap.startswith("RSI_"):
        cap = cap.split("RSI_", 1)[1]
    if cdel_version:
        return f"{cap}_{str(cdel_version).upper()}"
    return cap


def generate_skill_manifest(*, repo_root: Path) -> dict[str, Any]:
    verifier_modules = _discover_verifier_modules(repo_root)
    skills: list[dict[str, Any]] = []

    for registry_path in _registry_paths(repo_root):
        try:
            registry_payload = _load_json(registry_path)
        except Exception:  # noqa: BLE001
            continue
        capabilities = registry_payload.get("capabilities")
        if not isinstance(capabilities, list):
            continue
        for row in capabilities:
            if not isinstance(row, dict):
                continue
            campaign_id = str(row.get("campaign_id", "")).strip()
            capability_id = str(row.get("capability_id", "")).strip()
            orchestrator_module = str(row.get("orchestrator_module", "")).strip()
            verifier_module = str(row.get("verifier_module", "")).strip()
            if not campaign_id or not capability_id or not verifier_module:
                continue
            if verifier_module not in verifier_modules:
                continue
            cdel_version = _extract_version(
                campaign_id=campaign_id,
                orchestrator_module=orchestrator_module,
                verifier_module=verifier_module,
            )
            skills.append(
                {
                    "skill_id": _skill_id(capability_id=capability_id, cdel_version=cdel_version),
                    "cdel_version": cdel_version,
                    "capability_id": capability_id,
                    "campaign_id": campaign_id,
                    "orchestrator_module": orchestrator_module,
                    "verifier_module": verifier_module,
                    "family": _family_from_capability(capability_id),
                    "enabled_by_default_b": bool(row.get("enabled", False)),
                }
            )

    deduped: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for row in skills:
        key = (
            str(row.get("capability_id", "")),
            str(row.get("campaign_id", "")),
            str(row.get("verifier_module", "")),
            str(row.get("orchestrator_module", "")),
        )
        prev = deduped.get(key)
        if prev is None:
            deduped[key] = row
            continue
        if bool(row.get("enabled_by_default_b", False)):
            prev["enabled_by_default_b"] = True

    sorted_rows = sorted(
        deduped.values(),
        key=lambda row: (
            str(row.get("family", "")),
            str(row.get("capability_id", "")),
            str(row.get("campaign_id", "")),
            str(row.get("cdel_version", "")),
        ),
    )
    return {
        "schema_version": "OMEGA_SKILL_MANIFEST_v1",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "skills": sorted_rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(prog="omega_skill_manifest_v1")
    parser.add_argument("--repo_root", default="")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    if str(args.repo_root).strip():
        repo_root = Path(str(args.repo_root)).expanduser().resolve()
    else:
        repo_root = Path(__file__).resolve().parents[2]
    out_path = Path(str(args.out)).expanduser().resolve()

    payload = generate_skill_manifest(repo_root=repo_root)
    _write_json(out_path, payload)
    print(out_path.as_posix())


if __name__ == "__main__":
    main()
