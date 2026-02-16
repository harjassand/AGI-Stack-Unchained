"""Deterministic stub CDEL runner (v1)."""

from __future__ import annotations

import argparse
import io
import json
import os
import tarfile

from ..canon.hash_v1 import sha256_hex


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--out_dir", required=True)
    args, _ = parser.parse_known_args()

    os.makedirs(args.out_dir, exist_ok=True)
    with open(args.candidate, "rb") as f:
        cand_bytes = f.read()
    cand_sha = sha256_hex(cand_bytes)

    result = {"status": "PASS", "candidate_tar_sha256": cand_sha}
    receipt = {"receipt": "stub", "candidate_tar_sha256": cand_sha}

    with open(os.path.join(args.out_dir, "result_report.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, sort_keys=True)
    with open(os.path.join(args.out_dir, "receipt.json"), "w", encoding="utf-8") as f:
        json.dump(receipt, f, sort_keys=True)

    evidence_path = os.path.join(args.out_dir, "evidence_bundle_v1.tar")
    payload = b"stub_evidence_v1"
    bio = io.BytesIO()
    with tarfile.open(fileobj=bio, mode="w", format=tarfile.USTAR_FORMAT) as tf:
        info = tarfile.TarInfo(name="evidence.txt")
        info.size = len(payload)
        info.mtime = 0
        info.uid = 0
        info.gid = 0
        info.uname = "root"
        info.gname = "root"
        tf.addfile(info, io.BytesIO(payload))
    with open(evidence_path, "wb") as f:
        f.write(bio.getvalue())


if __name__ == "__main__":
    main()
