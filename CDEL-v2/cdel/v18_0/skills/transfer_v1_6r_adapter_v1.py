"""Legacy transfer adapter (v1.6r lineage) for Omega v18."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..omega_common_v1 import rat_q32, validate_schema
from ..omega_common_v1 import load_canon_dict


def compute_skill_report(*, tick_u64: int, state_root: Path, config_dir: Path) -> dict[str, Any]:
    _ = config_dir
    promoted_u64 = 0
    promoted_capabilities: set[str] = set()

    dispatch_root = state_root / "dispatch"
    if dispatch_root.exists() and dispatch_root.is_dir():
        for dispatch_dir in sorted(dispatch_root.iterdir(), key=lambda row: row.as_posix()):
            if not dispatch_dir.is_dir():
                continue
            dispatch_rows = sorted(dispatch_dir.glob("*.omega_dispatch_receipt_v1.json"), key=lambda row: row.as_posix())
            capability_id = ""
            if dispatch_rows:
                dispatch_payload = load_canon_dict(dispatch_rows[-1])
                validate_schema(dispatch_payload, "omega_dispatch_receipt_v1")
                capability_id = str(dispatch_payload.get("capability_id", "")).strip()

            for promo_path in sorted(
                dispatch_dir.glob("promotion/sha256_*.omega_promotion_receipt_v1.json"),
                key=lambda row: row.as_posix(),
            ):
                promo_payload = load_canon_dict(promo_path)
                validate_schema(promo_payload, "omega_promotion_receipt_v1")
                status = str((promo_payload.get("result") or {}).get("status", "")).strip()
                if status != "PROMOTED":
                    continue
                promoted_u64 += 1
                if capability_id:
                    promoted_capabilities.add(capability_id)

    transfer_gain_q32 = rat_q32(len(promoted_capabilities), max(1, promoted_u64)) if promoted_u64 > 0 else 0
    flags: list[str] = []
    if promoted_u64 == 0:
        flags.append("NO_PROMOTIONS")

    recommendations = [
        {
            "kind": "TRANSFER_REVIEW",
            "detail": "Increase legal promotion opportunities across capability families.",
        }
    ]

    return {
        "schema_version": "omega_skill_report_v1",
        "skill_id": "TRANSFER_V1_6R",
        "tick_u64": int(tick_u64),
        "metrics": {
            "transfer_gain_q32": {"q": int(transfer_gain_q32)},
            "transfer_promotions_q32": {"q": int(promoted_u64)},
        },
        "flags": flags,
        "recommendations": recommendations,
    }
