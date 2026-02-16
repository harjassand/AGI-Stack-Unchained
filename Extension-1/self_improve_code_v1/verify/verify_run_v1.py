"""Verify run artifacts without re-exec (v1)."""

from __future__ import annotations

import io
import json
import os
import tarfile
import argparse
from typing import Dict, List, Tuple

from ..canon.json_canon_v1 import canon_bytes
from ..canon.hash_v1 import sha256_hex
from ..canon.jsonl_v1 import verify_jsonl_rolling_hash, iter_jsonl
from ..package.candidate_hash_v1 import compute_candidate_id, set_candidate_id_backend
from ..run_manifest_v1 import build_run_manifest
from ..state.state_io_v1 import load_state
from ..state.state_update_v1 import apply_attempts


def _tar_bytes(entries: Dict[str, bytes]) -> bytes:
    bio = io.BytesIO()
    with tarfile.open(fileobj=bio, mode="w", format=tarfile.USTAR_FORMAT) as tf:
        for name in sorted(entries.keys()):
            data = entries[name]
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            info.mtime = 0
            info.uid = 0
            info.gid = 0
            info.uname = "root"
            info.gname = "root"
            tf.addfile(info, io.BytesIO(data))
    return bio.getvalue()


def _read_json(path: str) -> Dict:
    with open(path, "rb") as f:
        return json.loads(f.read().decode("utf-8"))


def _verify_candidate_bundle(manifest: Dict, patch_bytes: bytes, tar_bytes: bytes, label: str) -> List[str]:
    errors: List[str] = []
    candidate_id, _, _, _ = compute_candidate_id(manifest, patch_bytes)
    if candidate_id != manifest.get("candidate_id"):
        errors.append(f"candidate_id mismatch for {label}")
    recomputed = _tar_bytes({"manifest.json": canon_bytes(manifest), "patch.diff": patch_bytes})
    if sha256_hex(recomputed) != sha256_hex(tar_bytes):
        errors.append(f"candidate.tar not deterministic for {label}")
    return errors


def _extract_from_tar(tar_bytes: bytes) -> Tuple[Dict, bytes]:
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:*") as tf:
        manifest_member = tf.getmember("manifest.json")
        patch_member = tf.getmember("patch.diff")
        manifest_data = tf.extractfile(manifest_member).read()
        patch_data = tf.extractfile(patch_member).read()
    manifest = json.loads(manifest_data.decode("utf-8"))
    return manifest, patch_data


def verify_run(run_dir: str) -> Tuple[bool, List[str]]:
    errors: List[str] = []
    run_config = _read_json(os.path.join(run_dir, "run_config.json"))
    if "candidate_id" in run_config:
        set_candidate_id_backend(run_config.get("candidate_id", {}), base_dir=run_dir)
    attempts_path = os.path.join(run_dir, "attempts.jsonl")
    ok, _ = verify_jsonl_rolling_hash(attempts_path)
    if not ok:
        errors.append("attempts.jsonl rolling hash invalid")

    # Verify topk candidates using stored manifest/patch/tar
    topk_dir = os.path.join(run_dir, "topk")
    if os.path.isdir(topk_dir):
        for name in sorted(os.listdir(topk_dir)):
            if not name.endswith("_manifest.json"):
                continue
            prefix = name.replace("_manifest.json", "")
            manifest_path = os.path.join(topk_dir, f"{prefix}_manifest.json")
            patch_path = os.path.join(topk_dir, f"{prefix}_patch.diff")
            tar_path = os.path.join(topk_dir, f"{prefix}_candidate.tar")
            if not (os.path.exists(manifest_path) and os.path.exists(patch_path) and os.path.exists(tar_path)):
                errors.append(f"missing topk files for {prefix}")
                continue
            manifest = _read_json(manifest_path)
            with open(patch_path, "rb") as f:
                patch_bytes = f.read()
            with open(tar_path, "rb") as f:
                tar_bytes = f.read()
            errors.extend(_verify_candidate_bundle(manifest, patch_bytes, tar_bytes, f"topk/{prefix}"))

    selected_dir = os.path.join(run_dir, "selected")
    tar_path = os.path.join(selected_dir, "selected_candidate.tar")
    if os.path.exists(tar_path):
        with open(tar_path, "rb") as f:
            tar_bytes = f.read()
        try:
            manifest, patch_bytes = _extract_from_tar(tar_bytes)
            errors.extend(_verify_candidate_bundle(manifest, patch_bytes, tar_bytes, "selected"))
        except Exception:
            errors.append("failed to read selected_candidate.tar")

    # Replay checks
    state_before = load_state(os.path.join(run_dir, "state_before.json"))
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

    recomputed_manifest = build_run_manifest(
        run_config,
        attempts,
        state_before_sha,
        state_after_sha,
        artifacts,
        run_config.get("selected_candidate_id"),
    )
    stored_manifest = _read_json(os.path.join(run_dir, "run_manifest.json"))
    if sha256_hex(canon_bytes(recomputed_manifest)) != sha256_hex(canon_bytes(stored_manifest)):
        errors.append("run_manifest.json mismatch on replay")

    stored_state_after = _read_json(os.path.join(run_dir, "state_after.json"))
    if sha256_hex(canon_bytes(state_after)) != sha256_hex(canon_bytes(stored_state_after)):
        errors.append("state_after.json mismatch on replay")

    return len(errors) == 0, errors


__all__ = ["verify_run"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args()
    ok, errors = verify_run(args.run_dir)
    print("OK" if ok else "FAIL")
    if errors:
        for e in errors:
            print(e)
