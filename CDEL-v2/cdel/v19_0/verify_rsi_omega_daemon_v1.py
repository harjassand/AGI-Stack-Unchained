"""v19 replay verifier that extends v18 replay with continuity/J recomputation."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from ..v18_0.omega_common_v1 import fail as fail_v18
from ..v18_0.verify_rsi_omega_daemon_v1 import OmegaV18Error
from ..v18_0.verify_rsi_omega_daemon_v1 import verify as verify_v18
from .omega_promoter_v1 import _verify_axis_bundle_gate


def _resolve_state_dir(path: Path) -> Path:
    root = path.resolve()
    if (root / "state").is_dir() and (root / "config").is_dir():
        return root / "state"
    if (root / "daemon" / "rsi_omega_daemon_v18_0" / "state").is_dir():
        return root / "daemon" / "rsi_omega_daemon_v18_0" / "state"
    if root.name == "state" and (root.parent / "config").is_dir():
        return root
    fail_v18("SCHEMA_FAIL")
    return root


def _latest_snapshot_or_fail(snapshot_dir: Path) -> Path:
    rows = sorted(snapshot_dir.glob("sha256_*.omega_tick_snapshot_v1.json"), key=lambda row: row.as_posix())
    if not rows:
        fail_v18("MISSING_STATE_INPUT")
    best: Path | None = None
    best_tick = -1
    for row in rows:
        payload = _load_canon_json(row)
        tick = int(payload.get("tick_u64", -1))
        if tick > best_tick:
            best_tick = tick
            best = row
    if best is None:
        fail_v18("MISSING_STATE_INPUT")
    return best


def _load_canon_json(path: Path) -> dict[str, Any]:
    import json

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        fail_v18("SCHEMA_FAIL")
    return payload


def _find_nested_hash(state_root: Path, digest: str, suffix: str) -> Path:
    hexd = str(digest).split(":", 1)[1]
    target = f"sha256_{hexd}.{suffix}"
    rows = sorted(state_root.glob(f"dispatch/*/**/{target}"), key=lambda row: row.as_posix())
    if len(rows) != 1:
        fail_v18("MISSING_STATE_INPUT")
    return rows[0]


def _load_promotion_bundle_by_hash(state_root: Path, bundle_hash: str) -> Path | None:
    if not isinstance(bundle_hash, str) or not bundle_hash.startswith("sha256:"):
        return None
    hexd = bundle_hash.split(":", 1)[1]
    if len(hexd) != 64:
        return None
    rows = sorted(state_root.glob(f"subruns/**/sha256_{hexd}.*.json"), key=lambda row: row.as_posix())
    if not rows:
        return None
    return rows[0]


def verify(state_dir: Path, *, mode: str = "full") -> str:
    verify_v18(state_dir, mode=mode)

    state_root = _resolve_state_dir(state_dir)
    snapshot_path = _latest_snapshot_or_fail(state_root / "snapshot")
    snapshot = _load_canon_json(snapshot_path)

    promo_hash = snapshot.get("promotion_receipt_hash")
    if promo_hash is None:
        return "VALID"

    promotion_path = _find_nested_hash(state_root, str(promo_hash), "omega_promotion_receipt_v1.json")
    promotion_payload = _load_canon_json(promotion_path)
    status = str((promotion_payload.get("result") or {}).get("status", ""))
    if status != "PROMOTED":
        return "VALID"

    bundle_hash = str(promotion_payload.get("promotion_bundle_hash", ""))
    bundle_path = _load_promotion_bundle_by_hash(state_root, bundle_hash)
    if bundle_path is None:
        fail_v18("MISSING_STATE_INPUT")

    bundle_obj = _load_canon_json(bundle_path)
    try:
        _verify_axis_bundle_gate(
            bundle_obj=bundle_obj,
            bundle_path=bundle_path,
            promotion_dir=promotion_path.parent,
        )
    except Exception:
        fail_v18("NONDETERMINISTIC")

    return "VALID"


def main() -> None:
    parser = argparse.ArgumentParser(prog="verify_rsi_omega_daemon_v1_v19")
    parser.add_argument("--mode", required=True)
    parser.add_argument("--state_dir", required=True)
    args = parser.parse_args()

    try:
        print(verify(Path(args.state_dir), mode=args.mode))
    except OmegaV18Error as exc:
        msg = str(exc)
        if not msg.startswith("INVALID:"):
            msg = f"INVALID:{msg}"
        print(msg)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
