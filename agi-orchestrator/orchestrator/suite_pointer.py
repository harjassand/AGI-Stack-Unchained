"""Suite pointer helpers for pyut dev suite updates."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from blake3 import blake3


@dataclass(frozen=True)
class SuitePointerUpdate:
    old_hash: str | None
    new_hash: str
    suite_len: int
    updated_at: str
    source: str
    notes: str


def update_pyut_dev_suite_pointer(
    *,
    suite_hash: str,
    suites_dir: Path,
    pointer_path: Path,
    dev_config_path: Path,
    updated_at: str,
    source: str,
    notes: str,
) -> SuitePointerUpdate:
    suite_path = suites_dir / f"{suite_hash}.jsonl"
    if not suite_path.exists():
        raise ValueError(f"suite not found: {suite_path}")
    actual_hash = blake3(suite_path.read_bytes()).hexdigest()
    if actual_hash != suite_hash:
        raise ValueError("suite hash mismatch")

    suite_len = sum(1 for line in suite_path.read_text(encoding="utf-8").splitlines() if line)
    old_hash = _read_pointer_hash(pointer_path)

    pointer = {
        "domain": "python-ut-v1",
        "suite_hash": suite_hash,
        "updated_at": updated_at,
        "source": source,
        "notes": notes,
    }
    pointer_path.parent.mkdir(parents=True, exist_ok=True)
    pointer_path.write_text(json.dumps(pointer, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    _update_dev_config_hash(dev_config_path, suite_hash)
    return SuitePointerUpdate(
        old_hash=old_hash,
        new_hash=suite_hash,
        suite_len=suite_len,
        updated_at=updated_at,
        source=source,
        notes=notes,
    )


def _read_pointer_hash(pointer_path: Path) -> str | None:
    if not pointer_path.exists():
        return None
    payload = json.loads(pointer_path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        value = payload.get("suite_hash")
        if isinstance(value, str):
            return value
    return None


def _update_dev_config_hash(path: Path, suite_hash: str) -> None:
    if not path.exists():
        raise ValueError(f"dev config not found: {path}")
    lines = path.read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    updated = False
    for line in lines:
        if line.strip().startswith("eval_suite_hash"):
            out.append(f'eval_suite_hash = "{suite_hash}"')
            updated = True
        else:
            out.append(line)
    if not updated:
        raise ValueError("eval_suite_hash not found in dev config")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
