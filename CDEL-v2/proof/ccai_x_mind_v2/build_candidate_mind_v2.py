from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(prog="build-candidate-mind-v2")
    parser.add_argument("--out_tar", required=True)
    parser.add_argument("--template", required=True)
    args = parser.parse_args()

    from system_runtime.tasks.ccai_x_mind_v1.proposer_mind_v2 import propose_candidates

    out_path = Path(args.out_tar).resolve()
    out_dir = out_path.parent
    proposals = propose_candidates(out_dir, [str(args.template)])
    if not proposals:
        raise SystemExit("no proposals returned")
    proposal = proposals[0]
    if proposal.tar_path != out_path:
        out_path.write_bytes(proposal.tar_path.read_bytes())
    print(proposal.candidate_id)


if __name__ == "__main__":
    main()
