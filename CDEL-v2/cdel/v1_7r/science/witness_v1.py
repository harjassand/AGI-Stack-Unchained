"""SCI-RSI v1.7r: science witness emission (per-failure witnesses become curriculum).

Strict guarantees:
- canonical JSON only (GCJ-1)
- deterministic witness hashing and file naming
- bounded witness size (trace excerpt only)
- idempotent writes (existing file must match exactly)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cdel.v1_7r.canon import hash_json, load_canon_json, write_canon_json


SCI_WITNESS_FAILURE_MODES_V1 = [
    "INVALID_SUITE_ROW",
    "TIMEOUT_MAX_STEPS",
    "INVALID_ACTION",
    "EVAL_BEFORE_VALID_STATE",
    "SINGULAR_MATRIX",
    "ESTIMATOR_INVALID",
    "NONTRIVIALITY_FAIL",
    "UNKNOWN",
]

SCI_WITNESS_ENV_KINDS_V1 = ("wmworld-v1", "causalworld-v1")
SCI_WITNESS_INSTANCE_KINDS_V1 = ("anchor", "pressure", "gate")


def _require_str(x: Any, name: str) -> str:
    if not isinstance(x, str):
        raise TypeError(f"{name} must be str")
    return x


def _require_dict(x: Any, name: str) -> dict:
    if not isinstance(x, dict):
        raise TypeError(f"{name} must be dict")
    return x


def _require_list(x: Any, name: str) -> list:
    if not isinstance(x, list):
        raise TypeError(f"{name} must be list")
    return x


def _require_u64(x: Any, name: str) -> int:
    if isinstance(x, bool) or not isinstance(x, int):
        raise TypeError(f"{name} must be int")
    if x < 0:
        raise ValueError(f"{name} must be >= 0")
    return x


def _sha256_digest_prefixed(digest32: Any, name: str) -> str:
    if not isinstance(digest32, (bytes, bytearray)):
        raise TypeError(f"{name} must be bytes")
    b = bytes(digest32)
    if len(b) != 32:
        raise ValueError(f"{name} must be 32 bytes (sha256 digest)")
    return "sha256:" + b.hex()


def _canon_action(action: Any) -> dict:
    """Strictly canonicalize a trace action: {"name": str, "args": {}}."""
    if not isinstance(action, dict):
        raise TypeError("trace action must be dict")
    if set(action.keys()) != {"name", "args"}:
        raise ValueError("trace action keys must be exactly {'name','args'}")
    name = action.get("name")
    args = action.get("args")
    if not isinstance(name, str):
        raise TypeError("trace action name must be str")
    if not isinstance(args, dict):
        raise TypeError("trace action args must be dict")
    if args:
        raise ValueError("trace action args must be empty dict")
    return {"name": name, "args": {}}


def _trace_excerpt(trace: list[dict]) -> list[dict]:
    if len(trace) <= 32:
        return list(trace)
    return list(trace[:16]) + list(trace[-16:])


def emit_science_witness_on_fail(
    *,
    diagnostics_dir: str | Path,
    epoch_id: str,
    env_kind: str,
    instance_kind: str,
    suite_row: dict,
    inst_hash: bytes,
    failure_mode: str,
    trace: list[dict],
    final_last_eval: dict,
    workvec: dict,
    x_meta: dict | None = None,
) -> str:
    """Write a per-failure science witness file and return witness_hash (sha256:...)."""
    diag = Path(diagnostics_dir)
    epoch_id_s = _require_str(epoch_id, "epoch_id")
    env_kind_s = _require_str(env_kind, "env_kind")
    instance_kind_s = _require_str(instance_kind, "instance_kind")
    suite_row_d = _require_dict(suite_row, "suite_row")
    final_last_eval_d = _require_dict(final_last_eval, "final_last_eval")
    workvec_d = _require_dict(workvec, "workvec")
    x_meta_d = {} if x_meta is None else _require_dict(x_meta, "x_meta")

    if env_kind_s not in SCI_WITNESS_ENV_KINDS_V1:
        raise ValueError("env_kind invalid")
    if instance_kind_s not in SCI_WITNESS_INSTANCE_KINDS_V1:
        raise ValueError("instance_kind invalid")
    if failure_mode not in SCI_WITNESS_FAILURE_MODES_V1:
        failure_mode = "UNKNOWN"

    inst_hash_s = _sha256_digest_prefixed(inst_hash, "inst_hash")

    # Canonicalize the full trace (for hashing) and build a bounded excerpt.
    trace_list = _require_list(trace, "trace")
    trace_canon = [_canon_action(a) for a in trace_list]
    trace_hash_s = hash_json(trace_canon)

    excerpt = _trace_excerpt(trace_canon)

    # Required workvec fields.
    env_steps_total = _require_u64(workvec_d.get("env_steps_total"), "workvec.env_steps_total")
    bytes_hashed_total = _require_u64(workvec_d.get("bytes_hashed_total"), "workvec.bytes_hashed_total")
    verifier_gas_total = _require_u64(workvec_d.get("verifier_gas_total"), "workvec.verifier_gas_total")

    # Hash the suite_row deterministically.
    suite_row_hash_s = hash_json(suite_row_d)

    witness = {
        "schema": "science_instance_witness_v1",
        "schema_version": 1,
        "epoch_id": epoch_id_s,
        "env_kind": env_kind_s,
        "instance_kind": instance_kind_s,
        "suite_row": suite_row_d,
        "suite_row_hash": suite_row_hash_s,
        "inst_hash": inst_hash_s,
        "failure_mode": failure_mode,
        "trace_hash": trace_hash_s,
        "trace_excerpt": excerpt,
        "final_last_eval": final_last_eval_d,
        "workvec": {
            "env_steps_total": env_steps_total,
            "bytes_hashed_total": bytes_hashed_total,
            "verifier_gas_total": verifier_gas_total,
        },
        "x-meta": x_meta_d,
    }

    witness_hash = hash_json(witness)

    witness_dir = diag / "science_instance_witnesses_v1"
    witness_path = witness_dir / f"{witness_hash.split(':', 1)[1]}.json"

    # Idempotent write: if the file exists, it must match exactly.
    if witness_path.exists():
        existing = load_canon_json(witness_path)
        if existing != witness:
            raise ValueError("existing witness file does not match expected content")
    else:
        write_canon_json(witness_path, witness)

    return witness_hash


def emit_science_witness_index(*, diagnostics_dir: str | Path, epoch_id: str) -> None:
    """Scan witness directory and emit grouped witness index deterministically."""
    diag = Path(diagnostics_dir)
    epoch_id_s = _require_str(epoch_id, "epoch_id")

    witness_dir = diag / "science_instance_witnesses_v1"
    by_env_kind: dict[str, dict[str, list[str]]] = {
        "wmworld-v1": {"anchor": [], "pressure": [], "gate": []},
        "causalworld-v1": {"anchor": [], "pressure": [], "gate": []},
    }

    if witness_dir.exists():
        for p in sorted(witness_dir.glob("*.json"), key=lambda x: x.name):
            w = load_canon_json(p)
            if not isinstance(w, dict):
                raise ValueError("witness must be a dict")
            if w.get("schema") != "science_instance_witness_v1":
                raise ValueError("invalid witness schema")
            if str(w.get("epoch_id")) != epoch_id_s:
                raise ValueError("witness epoch_id mismatch")

            wh = hash_json(w)
            # Ensure filename matches hash hex.
            if p.stem != wh.split(":", 1)[1]:
                raise ValueError("witness filename does not match witness hash")

            env_kind = str(w.get("env_kind"))
            instance_kind = str(w.get("instance_kind"))
            if env_kind not in by_env_kind:
                raise ValueError("invalid env_kind in witness")
            if instance_kind not in by_env_kind[env_kind]:
                raise ValueError("invalid instance_kind in witness")

            by_env_kind[env_kind][instance_kind].append(wh)

    # Deterministic: sort within each bucket lexicographically by witness_hash string.
    for env_kind in by_env_kind:
        for inst_kind in by_env_kind[env_kind]:
            by_env_kind[env_kind][inst_kind] = sorted(by_env_kind[env_kind][inst_kind])

    index = {
        "schema": "science_instance_witness_index_v1",
        "schema_version": 1,
        "epoch_id": epoch_id_s,
        "by_env_kind": by_env_kind,
    }

    write_canon_json(diag / "science_instance_witness_index_v1.json", index)
