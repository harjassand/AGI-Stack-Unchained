"""Sealed Rust runner invocation helpers for VAL v17.0."""

from __future__ import annotations

import json
import struct
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from ...v1_7r.canon import canon_bytes, sha256_prefixed


class SealedRunnerError(ValueError):
    pass


def _normalize_trace_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except Exception as exc:  # noqa: BLE001
            raise SealedRunnerError("INVALID:EXEC_TRACE_INCOMPLETE") from exc
        if not isinstance(obj, dict):
            raise SealedRunnerError("INVALID:EXEC_TRACE_INCOMPLETE")
        rows.append(obj)
    return rows


def _rewrite_trace_rows(
    *,
    trace_path: Path,
    rows: list[dict[str, Any]],
    input_hash: str,
    output_hash: str,
    val_cycles_total: int,
) -> None:
    prev = "GENESIS"
    out_rows: list[dict[str, Any]] = []
    for row in rows:
        event_type = str(row.get("event_type", ""))
        enriched = {
            "schema_version": "val_exec_trace_v1",
            "seq_u64": int(row.get("seq_u64", 0)),
            "event_type": event_type,
            "status": str(row.get("status", "")),
            "mode": str(row.get("mode", "")),
            "exec_backend": str(row.get("exec_backend", "")),
            "input_hash": input_hash,
            "output_hash": output_hash,
            "val_cycles": int(val_cycles_total if event_type == "VAL_EXEC_END" else 0),
            "prev_hash": prev,
        }
        row_hash = sha256_prefixed(canon_bytes(enriched))
        enriched["hash"] = row_hash
        out_rows.append(enriched)
        prev = row_hash
    trace_path.write_text(
        "".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in out_rows),
        encoding="utf-8",
    )


def trace_head_hash(path: Path) -> str:
    rows = _normalize_trace_rows(path)
    if not rows:
        raise SealedRunnerError("INVALID:EXEC_TRACE_INCOMPLETE")
    head = str(rows[-1].get("hash", ""))
    if not head:
        raise SealedRunnerError("INVALID:EXEC_TRACE_INCOMPLETE")
    return head


def message_pack_bytes(messages: list[bytes]) -> bytes:
    out = bytearray()
    for msg in messages:
        if len(msg) > 0xFFFFFFFF:
            raise SealedRunnerError("INVALID:SCHEMA_FAIL")
        out += struct.pack("<I", len(msg))
        out += msg
    return bytes(out)


def parse_message_pack(raw: bytes) -> list[bytes]:
    out: list[bytes] = []
    idx = 0
    while idx < len(raw):
        if idx + 4 > len(raw):
            raise SealedRunnerError("INVALID:EXEC_TRACE_INCOMPLETE")
        (n,) = struct.unpack_from("<I", raw, idx)
        idx += 4
        if idx + n > len(raw):
            raise SealedRunnerError("INVALID:EXEC_TRACE_INCOMPLETE")
        out.append(raw[idx : idx + n])
        idx += n
    return out


def _load_json_unchecked(path: Path) -> dict[str, Any]:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise SealedRunnerError("INVALID:SEALED_RUN_RECEIPT_MISSING") from exc
    if not isinstance(obj, dict):
        raise SealedRunnerError("INVALID:SEALED_RUN_RECEIPT_MISSING")
    return obj


def run_runner_batch(
    *,
    runner_bin: Path,
    mode: str,
    messages: list[bytes],
    patch_bytes: bytes,
    trace_path: Path,
    receipt_path: Path,
    max_len_bytes: int,
    step_bytes: int,
    safety_status: str,
    runner_bin_hash: str,
    code_bytes_hash: str,
) -> dict[str, Any]:
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        messages_path = tmpdir / "messages.pack"
        outputs_path = tmpdir / "outputs.pack"
        patch_path = tmpdir / "patch.bin"
        messages_path.write_bytes(message_pack_bytes(messages))
        patch_path.write_bytes(patch_bytes)

        cmd = [
            str(runner_bin),
            "--mode",
            mode,
            "--messages",
            str(messages_path),
            "--outputs",
            str(outputs_path),
            "--trace",
            str(trace_path),
            "--receipt",
            str(receipt_path),
            "--patch",
            str(patch_path),
            "--max-len-bytes",
            str(max_len_bytes),
            "--step-bytes",
            str(step_bytes),
            "--safety-status",
            str(safety_status),
            "--runner-bin-hash",
            str(runner_bin_hash),
            "--code-bytes-hash",
            str(code_bytes_hash),
        ]

        rc = subprocess.run(cmd, capture_output=True, text=True, check=False)

        receipt = _load_json_unchecked(receipt_path) if receipt_path.exists() else {}
        outputs = parse_message_pack(outputs_path.read_bytes()) if outputs_path.exists() else []

        input_hash, output_hash = aggregate_io_hash(messages=messages, outputs=outputs)
        rows = _normalize_trace_rows(trace_path)
        if rows:
            _rewrite_trace_rows(
                trace_path=trace_path,
                rows=rows,
                input_hash=input_hash,
                output_hash=output_hash,
                val_cycles_total=int(receipt.get("val_cycles_total", 0)),
            )

        return {
            "returncode": int(rc.returncode),
            "stdout": rc.stdout,
            "stderr": rc.stderr,
            "receipt": receipt,
            "outputs": outputs,
        }


def run_runner_benchmark(
    *,
    runner_bin: Path,
    messages: list[bytes],
    patch_bytes: bytes,
    report_path: Path,
    warmup: int,
    reps: int,
    max_len_bytes: int,
    step_bytes: int,
    safety_status: str,
) -> dict[str, Any]:
    report_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        messages_path = tmpdir / "messages.pack"
        patch_path = tmpdir / "patch.bin"
        messages_path.write_bytes(message_pack_bytes(messages))
        patch_path.write_bytes(patch_bytes)

        cmd = [
            str(runner_bin),
            "--mode",
            "benchmark",
            "--messages",
            str(messages_path),
            "--patch",
            str(patch_path),
            "--benchmark-report",
            str(report_path),
            "--warmup",
            str(warmup),
            "--reps",
            str(reps),
            "--max-len-bytes",
            str(max_len_bytes),
            "--step-bytes",
            str(step_bytes),
            "--safety-status",
            str(safety_status),
        ]
        rc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if rc.returncode != 0:
            raise SealedRunnerError("INVALID:PERF_WALLCLOCK_GATE_FAIL")

    return _load_json_unchecked(report_path)


def ensure_trace_complete(path: Path) -> None:
    rows = _normalize_trace_rows(path)

    starts = [row for row in rows if row.get("event_type") == "VAL_EXEC_START"]
    ends = [row for row in rows if row.get("event_type") == "VAL_EXEC_END"]
    if not starts or not ends:
        raise SealedRunnerError("INVALID:EXEC_TRACE_INCOMPLETE")
    if len(ends) > len(starts):
        raise SealedRunnerError("INVALID:EXEC_TRACE_INCOMPLETE")
    prev = "GENESIS"
    for row in rows:
        for key in ["input_hash", "output_hash", "val_cycles", "prev_hash", "hash"]:
            if key not in row:
                raise SealedRunnerError("INVALID:EXEC_TRACE_INCOMPLETE")
        if str(row.get("prev_hash", "")) != prev:
            raise SealedRunnerError("INVALID:EXEC_TRACE_INCOMPLETE")
        expected = dict(row)
        expected_hash = str(expected.pop("hash", ""))
        if not expected_hash:
            raise SealedRunnerError("INVALID:EXEC_TRACE_INCOMPLETE")
        got_hash = sha256_prefixed(canon_bytes(expected))
        if got_hash != expected_hash:
            raise SealedRunnerError("INVALID:EXEC_TRACE_INCOMPLETE")
        prev = expected_hash


def has_exec_end(path: Path) -> bool:
    if not path.exists():
        return False
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except Exception:
            continue
        if isinstance(obj, dict) and obj.get("event_type") == "VAL_EXEC_END":
            return True
    return False


def output_hashes(outputs: list[bytes]) -> list[str]:
    return [sha256_prefixed(out) for out in outputs]


def aggregate_io_hash(*, messages: list[bytes], outputs: list[bytes]) -> tuple[str, str]:
    in_hash = sha256_prefixed(canon_bytes({"messages": [sha256_prefixed(m) for m in messages]}))
    out_hash = sha256_prefixed(canon_bytes({"outputs": output_hashes(outputs)}))
    return in_hash, out_hash


__all__ = [
    "SealedRunnerError",
    "aggregate_io_hash",
    "ensure_trace_complete",
    "has_exec_end",
    "message_pack_bytes",
    "output_hashes",
    "parse_message_pack",
    "run_runner_batch",
    "run_runner_benchmark",
    "trace_head_hash",
]
