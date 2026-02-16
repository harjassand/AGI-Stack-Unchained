from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from cdel.v1_7r.canon import canon_bytes, sha256_prefixed, write_canon_json


def _salted_hash_v1(*, salt_value: str, text: str) -> str:
    data = salt_value.encode("utf-8") + b"\0" + text.encode("utf-8")
    return "sha256:" + hashlib.sha256(data).hexdigest()


def test_v4_0_sealed_worker_index_invariance(tmp_path: Path, repo_root: Path) -> None:
    # Build a one-task suitepack and sealed config.
    salt_id = "sealed_salt_test_v1"
    salt_value = "SALT::sealed_test_v1"
    task_id = "sha256:" + "1" * 64
    answer_text = "42"

    suitepack_path = tmp_path / "suitepack.suitepack"
    task = {
        "schema": "sealed_task_v2",
        "task_id": task_id,
        "domain": "io_algorithms",
        "difficulty_bucket": 0,
        "prompt": {"format": "text", "text": "OP=00 A=40 B=2"},
        "answer_commitment": {"alg": "SHA256_SALT_V1", "salt_id": salt_id, "answer_hash": _salted_hash_v1(salt_value=salt_value, text=answer_text)},
        "eval": {"type": "exact_match", "budget": {"max_compute_units": 200000, "max_wall_seconds": 60}},
    }
    suitepack_path.write_text(json.dumps(task, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    suitepack_hash = sha256_prefixed(suitepack_path.read_bytes())

    sealed_cfg_path = tmp_path / "sealed.toml"
    sealed_cfg_path.write_text(
        "\n".join(
            [
                "[sealed]",
                f'suitepack_path = "{suitepack_path}"',
                f'suitepack_hash = "{suitepack_hash}"',
                "",
                "[salts]",
                f'{salt_id} = "{salt_value}"',
                "",
            ]
        ),
        encoding="utf-8",
    )

    # Candidate output (canonical JSON).
    candidate_path = tmp_path / "candidate_output.json"
    write_canon_json(candidate_path, {"task_id": task_id, "output": answer_text})

    # Spawn the sealed worker and query it twice with different global_task_index.
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join([str(repo_root / "CDEL-v2")])
    proc = subprocess.Popen(
        [sys.executable, "-m", "cdel.v4_0.sealed_worker_v1", "--sealed_config_path", str(sealed_cfg_path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        cwd=str(repo_root),
        bufsize=1,
    )
    try:
        assert proc.stdin is not None
        assert proc.stdout is not None

        req1 = {"task_id": task_id, "candidate_output_path": str(candidate_path), "global_task_index": 1}
        req2 = {"task_id": task_id, "candidate_output_path": str(candidate_path), "global_task_index": 99999}
        proc.stdin.write(json.dumps(req1, separators=(",", ":"), ensure_ascii=False) + "\n")
        proc.stdin.write(json.dumps(req2, separators=(",", ":"), ensure_ascii=False) + "\n")
        proc.stdin.flush()

        resp1 = json.loads(proc.stdout.readline())
        resp2 = json.loads(proc.stdout.readline())
        assert canon_bytes(resp1) == canon_bytes(resp2)
    finally:
        try:
            if proc.stdin:
                proc.stdin.close()
        except Exception:
            pass
        try:
            proc.terminate()
        except Exception:
            pass
