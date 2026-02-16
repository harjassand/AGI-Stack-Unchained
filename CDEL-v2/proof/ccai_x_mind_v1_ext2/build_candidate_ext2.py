#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import sys


def main() -> None:
    parser = argparse.ArgumentParser(prog="build-candidate-ext2")
    parser.add_argument("--out_tar", required=True)
    parser.add_argument("--template", default="wfp_500")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[3]
    agi_root = repo_root / "agi-system"
    sys.path.insert(0, str(agi_root))

    from system_runtime.tasks.ccai_x_mind_v1.proposer_ext2_v1 import propose_candidates

    out_tar = Path(args.out_tar)
    out_dir = out_tar.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    proposals = propose_candidates(out_dir, [str(args.template)])
    if not proposals:
        raise SystemExit("no proposals generated")
    proposal = proposals[0]
    if proposal.tar_path != out_tar:
        shutil.copyfile(proposal.tar_path, out_tar)
    print(proposal.candidate_id)


if __name__ == "__main__":
    main()
