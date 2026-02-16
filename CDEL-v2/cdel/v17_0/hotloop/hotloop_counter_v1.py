"""Deterministic workload generators and counters for kernel hotloops."""

from __future__ import annotations

import base64
import random
import subprocess
from typing import Any, Callable

from ...v1_7r.canon import canon_bytes, sha256_prefixed
from ..val.val_cost_model_v1 import estimate_val_cycles


class HotloopCounterError(ValueError):
    pass


def generate_workload_messages(workload: dict[str, Any]) -> list[bytes]:
    if workload.get("schema_version") != "kernel_workload_suitepack_v1":
        raise HotloopCounterError("INVALID:SCHEMA_FAIL")
    rng = random.Random(int(workload["seed_u64"]))
    n_messages = int(workload["n_messages"])
    min_len = int(workload["min_len"])
    max_len = int(workload["max_len"])

    if n_messages <= 0 or min_len < 0 or max_len < min_len:
        raise HotloopCounterError("INVALID:SCHEMA_FAIL")

    out: list[bytes] = []
    for _ in range(n_messages):
        length = rng.randint(min_len, max_len)
        out.append(bytes(rng.getrandbits(8) for _ in range(length)))
    return out


def load_fixture_messages(fixture_obj: dict[str, Any]) -> list[bytes]:
    if fixture_obj.get("schema_version") != "brain_suitepack_dev_v15_1":
        raise HotloopCounterError("INVALID:SCHEMA_FAIL")
    rows = fixture_obj.get("messages_b64")
    if not isinstance(rows, list) or not rows:
        raise HotloopCounterError("INVALID:SCHEMA_FAIL")
    return [base64.b64decode(str(item), validate=True) for item in rows]


def sha256_subprocess_hex(message: bytes) -> str:
    cmd = ["/usr/bin/shasum", "-a", "256"]
    proc = subprocess.run(cmd, input=message, capture_output=True, check=False)
    if proc.returncode != 0:
        raise HotloopCounterError("INVALID:EXEC_CRASH")
    token = proc.stdout.decode("utf-8", errors="strict").strip().split()[0]
    if len(token) != 64:
        raise HotloopCounterError("INVALID:EXEC_CRASH")
    return token.lower()


def _tree_hash_from_digests(digests_hex: list[str]) -> str:
    payload = {
        "schema_version": "sha256_digest_tree_v1",
        "digests_hex": list(digests_hex),
    }
    return sha256_prefixed(canon_bytes(payload))


def run_baseline_workload(*, messages: list[bytes], decoded_trace: dict[str, Any]) -> dict[str, Any]:
    digests: list[str] = []
    total_bytes = 0
    total_cycles = 0
    spawn_count = 0

    for msg in messages:
        digest = sha256_subprocess_hex(msg)
        digests.append(digest)
        total_bytes += len(msg)
        blocks_len = (len(msg) + 63) // 64
        total_cycles += estimate_val_cycles(decoded_trace, blocks_len=blocks_len, baseline_mode=True)
        spawn_count += 1

    return {
        "schema_version": "kernel_hash_workload_report_v1",
        "mode": "baseline",
        "tree_hash": _tree_hash_from_digests(digests),
        "spawn_count": int(spawn_count),
        "bytes_hashed": int(total_bytes),
        "val_cycles_total": int(total_cycles),
    }


def run_candidate_workload(
    *,
    messages: list[bytes],
    decoded_trace: dict[str, Any],
    candidate_hash_hex: Callable[[bytes], str],
) -> dict[str, Any]:
    digests: list[str] = []
    total_bytes = 0
    total_cycles = 0

    for msg in messages:
        digest = str(candidate_hash_hex(msg))
        digests.append(digest)
        total_bytes += len(msg)
        blocks_len = (len(msg) + 63) // 64
        total_cycles += estimate_val_cycles(decoded_trace, blocks_len=blocks_len, baseline_mode=False)

    return {
        "schema_version": "kernel_hash_workload_report_v1",
        "mode": "candidate",
        "tree_hash": _tree_hash_from_digests(digests),
        "spawn_count": 0,
        "bytes_hashed": int(total_bytes),
        "val_cycles_total": int(total_cycles),
    }


__all__ = [
    "HotloopCounterError",
    "generate_workload_messages",
    "load_fixture_messages",
    "run_baseline_workload",
    "run_candidate_workload",
    "sha256_subprocess_hex",
]
