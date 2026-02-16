"""CDEL client runner for CAOE v1 proposer."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

base_dir = Path(__file__).resolve().parents[1]
if str(base_dir) not in sys.path:
    sys.path.insert(0, str(base_dir))


class CDELClientError(RuntimeError):
    pass


def run_cdel_verify(
    *,
    cdel_bin: str | Path,
    candidate_tar: str | Path,
    base_ontology: str | Path,
    base_mech: str | Path,
    suitepack_dev: str | Path,
    suitepack_heldout: str | Path,
    out_dir: str | Path,
    eval_plan: str | None = None,
    screen_dev_episodes: int | None = None,
    screen_heldout_episodes: int | None = None,
    no_logs_on_fail: bool | None = None,
    progress_interval: int | None = None,
    progress_path: str | Path | None = None,
) -> None:
    candidate_tar = Path(candidate_tar)
    base_ontology = Path(base_ontology)
    base_mech = Path(base_mech)
    suitepack_dev = Path(suitepack_dev)
    suitepack_heldout = Path(suitepack_heldout)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        str(cdel_bin),
        "caoe",
        "verify",
        "--candidate",
        str(candidate_tar),
        "--base_ontology",
        str(base_ontology),
        "--base_mech",
        str(base_mech),
        "--suitepack_dev",
        str(suitepack_dev),
        "--suitepack_heldout",
        str(suitepack_heldout),
        "--out",
        str(out_dir),
    ]
    if eval_plan:
        cmd.extend(["--eval_plan", str(eval_plan)])
    if screen_dev_episodes is not None:
        cmd.extend(["--screen_dev_episodes", str(int(screen_dev_episodes))])
    if screen_heldout_episodes is not None:
        cmd.extend(["--screen_heldout_episodes", str(int(screen_heldout_episodes))])
    if no_logs_on_fail:
        cmd.append("--no_logs_on_fail")
    if progress_interval is not None:
        cmd.extend(["--progress_interval", str(int(progress_interval))])
    if progress_path is not None:
        cmd.extend(["--progress_path", str(Path(progress_path))])
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise CDELClientError(
            f"CDEL verify failed ({result.returncode}): {result.stderr.strip()}"
        )
