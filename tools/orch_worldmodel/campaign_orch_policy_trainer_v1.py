#!/usr/bin/env python3
"""Campaign wrapper for Step-5A orchestration world-model policy training (v1)."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _entry in (_REPO_ROOT, _REPO_ROOT / "CDEL-v2"):
    if str(_entry) not in sys.path:
        sys.path.insert(0, str(_entry))

from cdel.v1_7r.canon import write_canon_json

from tools.orch_worldmodel.orch_transition_dataset_builder_v1 import build_transition_dataset
from tools.orch_worldmodel.orch_worldmodel_trainer_v1 import train_worldmodel_policy
from tools.orch_worldmodel.pack_orch_policy_bundle_v1 import pack_orch_policy_bundle


_DEFAULT_MAX_WALLCLOCK_S = 600
_DEFAULT_MAX_BYTES_WRITTEN_U64 = 200 * 1024 * 1024


class CampaignError(RuntimeError):
    pass


def _fail(reason: str) -> None:
    raise CampaignError(str(reason))


def _is_sha256(value: Any) -> bool:
    raw = str(value).strip()
    return raw.startswith("sha256:") and len(raw) == 71 and all(ch in "0123456789abcdef" for ch in raw.split(":", 1)[1])


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise CampaignError("SCHEMA_FAIL") from exc
    if not isinstance(payload, dict):
        _fail("SCHEMA_FAIL")
    return payload


def _resolve_repo_rel(path_value: str) -> Path:
    raw = str(path_value).strip()
    if not raw:
        _fail("SCHEMA_FAIL")
    rel = Path(raw)
    if rel.is_absolute() or ".." in rel.parts:
        _fail("SCHEMA_FAIL")
    out = (_REPO_ROOT / rel).resolve()
    if not out.exists() or not out.is_file():
        _fail("MISSING_STATE_INPUT")
    return out


def _resolve_out_rel(base_out_dir: Path, rel_value: str) -> Path:
    rel = Path(str(rel_value).strip())
    if rel.is_absolute() or ".." in rel.parts:
        _fail("SCHEMA_FAIL")
    out = (base_out_dir / rel).resolve()
    try:
        out.relative_to(base_out_dir.resolve())
    except Exception as exc:
        raise CampaignError("SCHEMA_FAIL") from exc
    return out


def _dir_size_bytes(path: Path) -> int:
    total = 0
    if not path.exists() or not path.is_dir():
        return 0
    for row in path.rglob("*"):
        if row.exists() and row.is_file():
            total += int(row.stat().st_size)
    return int(total)


def _enforce_wallclock(start_monotonic: float, max_wallclock_s: int) -> None:
    elapsed = time.monotonic() - float(start_monotonic)
    if elapsed > float(max_wallclock_s):
        _fail("BUDGET_EXHAUSTED:MAX_WALLCLOCK")


def run_campaign(*, campaign_pack: Path, out_dir: Path, ek_id: str | None, kernel_ledger_id: str | None) -> dict[str, Any]:
    pack = _load_json(campaign_pack.resolve())
    if str(pack.get("schema_version", "")).strip() != "rsi_orch_policy_trainer_pack_v1":
        _fail("SCHEMA_FAIL")

    train_config_rel = str(pack.get("train_config_rel", "")).strip()
    output_dir_rel = str(pack.get("output_dir_rel", "")).strip()
    if not train_config_rel or not output_dir_rel:
        _fail("SCHEMA_FAIL")

    max_wallclock_s = int(max(1, int(pack.get("max_wallclock_s", _DEFAULT_MAX_WALLCLOCK_S))))
    max_bytes_written_u64 = int(max(1, int(pack.get("max_bytes_written_u64", _DEFAULT_MAX_BYTES_WRITTEN_U64))))

    output_root = _resolve_out_rel(out_dir.resolve(), output_dir_rel)
    output_root.mkdir(parents=True, exist_ok=True)

    start_monotonic = time.monotonic()
    out_root = (_REPO_ROOT / "daemon" / "orch_policy").resolve()

    train_config_path = _resolve_repo_rel(train_config_rel)
    _enforce_wallclock(start_monotonic, max_wallclock_s)

    transition_manifest_rel = str(pack.get("transition_dataset_manifest_rel", "")).strip()
    runs_root_rel = str(pack.get("runs_root_rel", "")).strip()
    has_manifest_rel = bool(transition_manifest_rel)
    has_runs_rel = bool(runs_root_rel)
    if has_manifest_rel == has_runs_rel:
        _fail("SCHEMA_FAIL")

    if has_manifest_rel:
        transition_manifest_path = _resolve_repo_rel(transition_dataset_manifest_rel := transition_manifest_rel)
        dataset_summary = {
            "dataset_manifest_path": transition_manifest_path.as_posix(),
            "dataset_manifest_id": str(_load_json(transition_manifest_path).get("dataset_manifest_id", "")),
            "events_included_u64": int(_load_json(transition_manifest_path).get("counts", {}).get("events_included_u64", 0)),
        }
    else:
        runs_root = Path(str(runs_root_rel)).expanduser()
        if runs_root.is_absolute() or ".." in runs_root.parts:
            _fail("SCHEMA_FAIL")
        runs_root_path = (_REPO_ROOT / runs_root).resolve()
        if not runs_root_path.exists() or not runs_root_path.is_dir():
            _fail("MISSING_RUNS_ROOT")

        resolved_ek_id = str(ek_id or pack.get("ek_id", "")).strip()
        resolved_kernel_ledger_id = str(kernel_ledger_id or pack.get("kernel_ledger_id", "")).strip()
        if not _is_sha256(resolved_ek_id) or not _is_sha256(resolved_kernel_ledger_id):
            _fail("SCHEMA_FAIL")

        dataset_summary = build_transition_dataset(
            runs_root=runs_root_path,
            out_root=out_root,
            ek_id=resolved_ek_id,
            kernel_ledger_id=resolved_kernel_ledger_id,
            max_runs_u64=int(max(0, int(pack.get("max_runs_u64", 5000)))),
            max_events_u64=int(max(1, int(pack.get("max_events_u64", 200000)))),
            cost_scale_ms_u64=int(max(1, int(pack.get("cost_scale_ms_u64", 60000)))),
        )
        transition_manifest_path = Path(str(dataset_summary["dataset_manifest_path"]))

    _enforce_wallclock(start_monotonic, max_wallclock_s)

    trainer_summary = train_worldmodel_policy(
        dataset_manifest_path=transition_manifest_path.resolve(),
        train_config_path=train_config_path.resolve(),
        out_dir=output_root,
    )
    _enforce_wallclock(start_monotonic, max_wallclock_s)

    pack_summary = pack_orch_policy_bundle(
        policy_table_path=Path(str(trainer_summary["policy_table_path"])).resolve(),
        train_config_path=train_config_path.resolve(),
        transition_dataset_manifest_path=transition_manifest_path.resolve(),
        out_root=out_root,
        notes=str(pack.get("notes", "")),
    )
    _enforce_wallclock(start_monotonic, max_wallclock_s)

    final_policy_table = output_root / "orch_policy_table_v1.json"
    final_bundle = output_root / "orch_policy_bundle_v1.json"

    if Path(str(pack_summary["plain_policy_table_path"])).resolve() != final_policy_table.resolve():
        shutil.copyfile(Path(str(pack_summary["plain_policy_table_path"])).resolve(), final_policy_table)
    if Path(str(pack_summary["plain_bundle_path"])).resolve() != final_bundle.resolve():
        shutil.copyfile(Path(str(pack_summary["plain_bundle_path"])).resolve(), final_bundle)

    written_bytes = _dir_size_bytes(output_root)
    if int(written_bytes) > int(max_bytes_written_u64):
        _fail("BUDGET_EXHAUSTED:MAX_BYTES_WRITTEN")

    summary = {
        "schema_version": "orch_policy_trainer_campaign_summary_v1",
        "status": "OK",
        "reason_code": "OK",
        "dataset_manifest_id": str(dataset_summary.get("dataset_manifest_id", "")),
        "dataset_manifest_path": transition_manifest_path.as_posix(),
        "policy_table_id": str(trainer_summary.get("policy_table_id", "")),
        "policy_table_path": final_policy_table.as_posix(),
        "bundle_id": str(pack_summary.get("bundle_id", "")),
        "bundle_path": final_bundle.as_posix(),
        "max_wallclock_s": int(max_wallclock_s),
        "max_bytes_written_u64": int(max_bytes_written_u64),
        "bytes_written_u64": int(written_bytes),
    }
    write_canon_json(output_root / "orch_policy_trainer_campaign_summary_v1.json", summary)
    return summary


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="campaign_orch_policy_trainer_v1")
    parser.add_argument("--campaign_pack", required=True)
    parser.add_argument("--out_dir", required=True)
    parser.add_argument("--ek_id", required=False)
    parser.add_argument("--kernel_ledger_id", required=False)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    summary = run_campaign(
        campaign_pack=Path(str(args.campaign_pack)).resolve(),
        out_dir=Path(str(args.out_dir)).resolve(),
        ek_id=(str(args.ek_id).strip() if args.ek_id else None),
        kernel_ledger_id=(str(args.kernel_ledger_id).strip() if args.kernel_ledger_id else None),
    )
    print(json.dumps(summary, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
