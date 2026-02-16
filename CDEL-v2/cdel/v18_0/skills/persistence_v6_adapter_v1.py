"""Legacy persistence adapter (v6 lineage) for Omega v18."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..omega_common_v1 import Q32_ONE, validate_schema
from ..omega_common_v1 import load_canon_dict


_SHA256_ZERO = "sha256:" + ("0" * 64)


def _snapshot_rows(state_root: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for path in sorted((state_root / "snapshot").glob("sha256_*.omega_tick_snapshot_v1.json"), key=lambda row: row.as_posix()):
        payload = load_canon_dict(path)
        validate_schema(payload, "omega_tick_snapshot_v1")
        out.append(payload)
    out.sort(key=lambda row: (int(row.get("tick_u64", 0)), str(row.get("snapshot_id", ""))))
    return out


def _has_hashed_file(path: Path, *, digest: str, suffix: str) -> bool:
    if not isinstance(digest, str) or not digest.startswith("sha256:"):
        return False
    hex_part = digest.split(":", 1)[1]
    if len(hex_part) != 64:
        return False
    return (path / f"sha256_{hex_part}.{suffix}").exists()


def compute_skill_report(*, tick_u64: int, state_root: Path, config_dir: Path) -> dict[str, Any]:
    _ = config_dir

    flags: list[str] = []
    snapshots = _snapshot_rows(state_root)
    if not snapshots:
        flags.append("SNAPSHOT_MISSING")
    else:
        prev_tick = None
        for row in snapshots[-32:]:
            tick_value = int(row.get("tick_u64", 0))
            if prev_tick is not None and tick_value != prev_tick + 1:
                flags.append("SNAPSHOT_GAP")
                break
            prev_tick = tick_value

        latest = snapshots[-1]
        trace_hash = str(latest.get("trace_hash_chain_hash", _SHA256_ZERO))
        if not _has_hashed_file(
            state_root / "ledger",
            digest=trace_hash,
            suffix="omega_trace_hash_chain_v1.json",
        ):
            flags.append("TRACE_CHAIN_MISSING")

        state_hash = str(latest.get("state_hash", _SHA256_ZERO))
        if not _has_hashed_file(
            state_root / "state",
            digest=state_hash,
            suffix="omega_state_v1.json",
        ):
            flags.append("STATE_HASH_MISSING")

    healthy_b = len(flags) == 0
    persistence_health_q32 = int(Q32_ONE if healthy_b else 0)

    return {
        "schema_version": "omega_skill_report_v1",
        "skill_id": "PERSIST_V6",
        "tick_u64": int(tick_u64),
        "metrics": {
            "persistence_health_q32": {"q": persistence_health_q32},
            "persistence_flags_q32": {"q": int(len(flags))},
        },
        "flags": flags,
        "recommendations": [
            {
                "kind": "PERSISTENCE_AUDIT",
                "detail": "Repair snapshot or trace continuity before enabling risky promotions.",
            }
        ],
    }
