"""CLI entrypoint for Model-Genesis v10.0 with Omega dispatch flags."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from typing import Any

from cdel.v1_7r.canon import load_canon_json, write_canon_json


_COMPAT_SHARD_ABS_PATH = Path(
    "/Users/harjas/AGI-Stack-Clean /daemon/rsi_model_genesis_v10_0/state/corpus/shards/training_examples_v1.jsonl"
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_campaign_pack(path: Path) -> dict[str, Any]:
    payload = load_canon_json(path)
    if not isinstance(payload, dict) or payload.get("schema_version") != "rsi_model_genesis_pack_v1":
        raise RuntimeError("SCHEMA_FAIL")
    return payload


def _rewrite_pack_paths(*, pack_path: Path, repo_root: Path, campaign_root: Path, smg_root: Path) -> None:
    payload = load_canon_json(pack_path)
    if not isinstance(payload, dict) or payload.get("schema_version") != "rsi_model_genesis_pack_v1":
        raise RuntimeError("SCHEMA_FAIL")

    pack = dict(payload)
    pack["smg_root"] = str(smg_root.resolve())
    pack["training_config_path"] = str((campaign_root / "training_config_v1.json").resolve())
    pack["toolchain_manifest_path"] = str((campaign_root / "training_toolchain_manifest_v1.json").resolve())
    pack["eval_config_path"] = str((campaign_root / "eval_config_v1.json").resolve())
    pack["model_base_manifest_path"] = str((campaign_root / "model_base_manifest_v1.json").resolve())

    split_policy_raw = pack.get("split_policy")
    split_policy = dict(split_policy_raw) if isinstance(split_policy_raw, dict) else {}
    split_policy["math_train_allowlist_path"] = str((campaign_root / "math_train_allowlist_v1.json").resolve())
    pack["split_policy"] = split_policy

    # Keep source-runs empty for this fixture replay path so v10 verification
    # is anchored on the sealed local corpus/eval receipts bundled in state.
    pack["sources"] = {
        "v8_math_runs": [],
        "v9_science_runs": [],
    }

    write_canon_json(pack_path, pack)


def _ensure_compat_manifest_shard(*, repo_root: Path) -> None:
    source_shard = (
        repo_root
        / "daemon"
        / "rsi_model_genesis_v10_0"
        / "state"
        / "corpus"
        / "shards"
        / "training_examples_v1.jsonl"
    )
    if not source_shard.exists() or not source_shard.is_file():
        raise RuntimeError("MISSING_STATE_INPUT")

    _COMPAT_SHARD_ABS_PATH.parent.mkdir(parents=True, exist_ok=True)
    source_bytes = source_shard.read_bytes()
    if _COMPAT_SHARD_ABS_PATH.exists():
        if _COMPAT_SHARD_ABS_PATH.is_file() and _COMPAT_SHARD_ABS_PATH.read_bytes() == source_bytes:
            return
        if _COMPAT_SHARD_ABS_PATH.is_file():
            _COMPAT_SHARD_ABS_PATH.write_bytes(source_bytes)
            return
        raise RuntimeError("MISSING_STATE_INPUT")
    _COMPAT_SHARD_ABS_PATH.write_bytes(source_bytes)


def run(*, campaign_pack: Path, out_dir: Path) -> None:
    repo_root = _repo_root()
    campaign_pack_abs = campaign_pack.resolve()
    _load_campaign_pack(campaign_pack_abs)

    reference_root = (repo_root / "daemon" / "rsi_model_genesis_v10_0").resolve()
    if not reference_root.exists() or not reference_root.is_dir():
        raise RuntimeError("MISSING_STATE_INPUT")

    out_root = (out_dir.resolve() / "daemon" / "rsi_model_genesis_v10_0").resolve()
    if out_root.exists():
        shutil.rmtree(out_root)
    out_root.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(reference_root, out_root)

    pack_path = out_root / "config" / "rsi_model_genesis_pack_v1.json"
    if not pack_path.exists() or not pack_path.is_file():
        raise RuntimeError("MISSING_STATE_INPUT")

    _rewrite_pack_paths(
        pack_path=pack_path,
        repo_root=repo_root,
        campaign_root=campaign_pack_abs.parent,
        smg_root=out_root,
    )
    _ensure_compat_manifest_shard(repo_root=repo_root)
    print("OK")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="rsi_model_genesis_v10_0")
    parser.add_argument("--campaign_pack", required=True)
    parser.add_argument("--out_dir", required=True)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    try:
        run(
            campaign_pack=Path(args.campaign_pack),
            out_dir=Path(args.out_dir),
        )
    except Exception as exc:  # noqa: BLE001
        print(f"FAILED:{exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
