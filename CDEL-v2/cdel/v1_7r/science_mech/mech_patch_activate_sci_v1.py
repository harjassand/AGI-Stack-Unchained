"""SCI-RSI v1.7r: mechanism patch activation (SCI_MECH_PATCH_ACTIVATE_V1).

Writes:
- current/science_mech_patch_active_set_v1.json
- current/ledger_events_v1/<event_hash>.json
- appends canonical line to current/ledger_events_v1.jsonl

This is a minimal implementation; verifier/tracker can bind hashes later.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cdel.v1_7r.canon import hash_json, write_canon_json, write_jsonl_line


def _require_str(x: Any, name: str) -> str:
    if not isinstance(x, str):
        raise TypeError(f"{name} must be str")
    return x


def activate_patch_sci(
    *,
    state_dir: str | Path,
    patch_id: str,
    patch_hash: str,
    benchmark_pack_hash: str,
    eval_cert_hash: str,
    base_state_hash: str,
) -> None:
    sd = Path(state_dir)
    cur = sd / "current"
    cur.mkdir(parents=True, exist_ok=True)

    patch_id_s = _require_str(patch_id, "patch_id")
    patch_hash_s = _require_str(patch_hash, "patch_hash")
    bench_hash_s = _require_str(benchmark_pack_hash, "benchmark_pack_hash")
    cert_hash_s = _require_str(eval_cert_hash, "eval_cert_hash")
    base_state_hash_s = _require_str(base_state_hash, "base_state_hash")

    event = {
        "schema": "ledger_event_v1",
        "schema_version": 1,
        "event_type": "SCI_MECH_PATCH_ACTIVATE_V1",
        "patch_id": patch_id_s,
        "patch_hash": patch_hash_s,
        "benchmark_pack_hash": bench_hash_s,
        "eval_cert_hash": cert_hash_s,
        "base_state_hash": base_state_hash_s,
        "x-meta": {},
    }
    event_hash = hash_json(event)

    # Write event file
    ev_dir = cur / "ledger_events_v1"
    ev_path = ev_dir / f"{event_hash.split(':', 1)[1]}.json"
    write_canon_json(ev_path, event)

    # Append to jsonl for convenience
    write_jsonl_line(cur / "ledger_events_v1.jsonl", event)

    # Update active set
    active_set = {
        "schema": "science_mech_patch_active_set_v1",
        "schema_version": 1,
        "active_patches": [{"patch_id": patch_id_s, "patch_hash": patch_hash_s}],
        "x-meta": {"activation_event_hash": event_hash},
    }
    write_canon_json(cur / "science_mech_patch_active_set_v1.json", active_set)
