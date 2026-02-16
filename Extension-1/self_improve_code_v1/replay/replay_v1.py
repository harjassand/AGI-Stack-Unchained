"""Replay run from logs only (v1)."""

from __future__ import annotations

import json
import os
import argparse
from typing import Dict

from ..canon.jsonl_v1 import iter_jsonl, verify_jsonl_rolling_hash
from ..canon.hash_v1 import sha256_hex
from ..canon.json_canon_v1 import canon_bytes
from ..package.candidate_hash_v1 import set_candidate_id_backend
from ..state.state_io_v1 import load_state
from ..state.state_update_v1 import apply_attempts
from ..run_manifest_v1 import build_run_manifest


def replay_run(run_dir: str) -> Dict:
    run_config_path = os.path.join(run_dir, "run_config.json")
    state_before_path = os.path.join(run_dir, "state_before.json")
    attempts_path = os.path.join(run_dir, "attempts.jsonl")

    with open(run_config_path, "rb") as f:
        run_config = json.loads(f.read().decode("utf-8"))
    if "candidate_id" in run_config:
        set_candidate_id_backend(run_config.get("candidate_id", {}), base_dir=run_dir)
    state_before = load_state(state_before_path)
    ok, _ = verify_jsonl_rolling_hash(attempts_path)
    if not ok:
        raise ValueError("attempts.jsonl rolling hash verification failed")

    attempts = list(iter_jsonl(attempts_path))
    eta = int(run_config.get("search", {}).get("eta", 1))
    state_before_sha = sha256_hex(canon_bytes(state_before))
    state_after = apply_attempts(json.loads(canon_bytes(state_before).decode("utf-8")), attempts, eta)
    state_after_sha = sha256_hex(canon_bytes(state_after))

    artifacts = {}
    for attempt in attempts:
        cand_id = attempt.get("candidate_id")
        if not cand_id:
            continue
        artifacts[cand_id] = {
            "patch_sha256": attempt.get("patch_sha256", ""),
            "tar_sha256": attempt.get("tar_sha256", ""),
        }

    manifest = build_run_manifest(
        run_config,
        attempts,
        state_before_sha,
        state_after_sha,
        artifacts,
        run_config.get("selected_candidate_id"),
    )
    return {"state_after": state_after, "run_manifest": manifest}


__all__ = ["replay_run"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args()
    out = replay_run(args.run_dir)
    print("OK")
    print(json.dumps(out["run_manifest"], sort_keys=True))
