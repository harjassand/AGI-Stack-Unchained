"""Verifier for RSI model genesis runs (v10.0)."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from ..v1_7r.canon import CanonError, canon_bytes, load_canon_json, loads, sha256_prefixed
from .corpus_manifest import load_corpus_manifest, load_corpus_index
from .model_bundle import compute_bundle_id, load_bundle
from .model_genesis_ledger import load_ledger, validate_chain
from .training_toolchain import compute_toolchain_id, load_toolchain_manifest
from ..v8_0 import verify_rsi_boundless_math_v1 as verify_v8_math
from ..v9_0 import verify_rsi_boundless_science_v1 as verify_v9_science


EVENT_TYPES = {
    "SMG_BOOT",
    "SMG_ENABLE_PRESENT",
    "SMG_CORPUS_BUILT",
    "SMG_TRAINING_DONE",
    "SMG_EVAL_DONE",
    "SMG_PROMOTION_WRITTEN",
    "SMG_STOP_REQUESTED",
    "SMG_SHUTDOWN",
    "SMG_FATAL",
}


class GenesisError(CanonError):
    pass


def _fail(reason: str) -> None:
    raise GenesisError(reason)


def _hash_file(path: Path) -> str:
    return sha256_prefixed(path.read_bytes())


def _validate_ledger(path: Path) -> tuple[list[dict[str, Any]], str, int, int, int]:
    if not path.exists():
        _fail("MISSING_ARTIFACT")
    entries = load_ledger(path)
    head, last_seq, min_tick, max_tick = validate_chain(entries)
    return entries, head, last_seq, min_tick, max_tick


def _require_enable_files(state_dir: Path) -> None:
    control = state_dir / "control"
    required = ["ENABLE_RESEARCH", "ENABLE_MODEL_GENESIS", "ENABLE_TRAINING", "MODEL_GENESIS_LEASE.json"]
    for name in required:
        if not (control / name).exists():
            _fail("MODEL_GENESIS_LOCKED_MISSING_KEYS")


def _load_pack(config_dir: Path) -> dict[str, Any]:
    pack_path = config_dir / "rsi_model_genesis_pack_v1.json"
    if not pack_path.exists():
        _fail("MISSING_ARTIFACT")
    pack = load_canon_json(pack_path)
    if not isinstance(pack, dict) or pack.get("schema_version") != "rsi_model_genesis_pack_v1":
        _fail("SCHEMA_INVALID")
    return pack


def _load_training_config(path: Path) -> dict[str, Any]:
    cfg = load_canon_json(path)
    if not isinstance(cfg, dict) or cfg.get("schema_version") != "training_config_v1":
        _fail("SCHEMA_INVALID")
    return cfg


def _load_eval_config(path: Path) -> dict[str, Any]:
    cfg = load_canon_json(path)
    if not isinstance(cfg, dict) or cfg.get("schema_version") != "eval_config_v1":
        _fail("SCHEMA_INVALID")
    return cfg


def _load_lease(path: Path) -> dict[str, Any]:
    lease = load_canon_json(path)
    if not isinstance(lease, dict) or lease.get("schema_version") != "model_genesis_lease_token_v1":
        _fail("MODEL_GENESIS_LEASE_INVALID")
    for key in ["lease_id", "allowed_ops", "valid_from_tick", "valid_until_tick", "max_runs"]:
        if key not in lease:
            _fail("MODEL_GENESIS_LEASE_INVALID")
    return lease


def verify(state_dir: Path, *, mode: str) -> dict[str, Any]:
    smg_root = state_dir.parent
    config_dir = smg_root / "config"
    pack = _load_pack(config_dir)

    ledger_path = state_dir / "ledger" / "model_genesis_ledger_v1.jsonl"
    entries, head_hash, _last_seq, min_tick, max_tick = _validate_ledger(ledger_path)

    if mode == "full":
        receipt_path = state_dir / "ledger" / "model_genesis_ignition_receipt_v1.json"
        if not receipt_path.exists():
            _fail("MISSING_ARTIFACT")

    _require_enable_files(state_dir)

    lease_path = state_dir / "control" / "MODEL_GENESIS_LEASE.json"
    lease = _load_lease(lease_path)
    if "MODEL_GENESIS_TRAIN" not in (lease.get("allowed_ops") or []) or "MODEL_GENESIS_EVAL" not in (lease.get("allowed_ops") or []):
        _fail("MODEL_GENESIS_LEASE_INVALID")
    valid_from = int(lease.get("valid_from_tick", 0))
    valid_until = int(lease.get("valid_until_tick", 0))
    if min_tick < valid_from or max_tick > valid_until:
        _fail("MODEL_GENESIS_LEASE_INVALID")
    max_runs = int(lease.get("max_runs", 0))
    if max_runs < 1:
        _fail("MODEL_GENESIS_LEASE_INVALID")

    # Corpus manifest + index
    corpus_manifest_dir = state_dir / "corpus" / "manifest"
    manifests = list(corpus_manifest_dir.glob("sha256_*.training_corpus_manifest_v1.json"))
    if not manifests:
        _fail("MODEL_GENESIS_SOURCE_RUN_INVALID")
    corpus_manifest = load_corpus_manifest(manifests[0])
    manifest_hash = sha256_prefixed(canon_bytes(corpus_manifest))
    if not manifests[0].name.startswith(f"sha256_{manifest_hash.split(':',1)[1]}"):
        _fail("MODEL_GENESIS_SOURCE_RUN_INVALID")

    # Verify source runs listed in pack and bind to corpus manifest receipts
    sources = pack.get("sources") or {}
    source_receipts = set(corpus_manifest.get("source_run_receipts") or [])
    if sources.get("v8_math_runs") or sources.get("v9_science_runs"):
        if not source_receipts:
            _fail("MODEL_GENESIS_SOURCE_RUN_INVALID")
        for src in sources.get("v8_math_runs", []) or []:
            state_path = Path(str(src.get("state_dir")))
            mode = str(src.get("mode", "full"))
            try:
                result = verify_v8_math.verify(state_path, mode=mode)
            except CanonError as exc:
                raise GenesisError("MODEL_GENESIS_SOURCE_RUN_INVALID") from exc
            ledger_head = result.get("ledger_head_hash")
            if isinstance(ledger_head, str) and not ledger_head.startswith("sha256:"):
                ledger_head = f"sha256:{ledger_head}"
            if ledger_head and ledger_head not in source_receipts:
                _fail("MODEL_GENESIS_SOURCE_RUN_INVALID")
        for src in sources.get("v9_science_runs", []) or []:
            state_path = Path(str(src.get("state_dir")))
            mode = str(src.get("mode", "full"))
            try:
                result = verify_v9_science.verify(state_path, mode=mode)
            except CanonError as exc:
                raise GenesisError("MODEL_GENESIS_SOURCE_RUN_INVALID") from exc
            ledger_head = result.get("ledger_head")
            if isinstance(ledger_head, str) and not ledger_head.startswith("sha256:"):
                ledger_head = f"sha256:{ledger_head}"
            if ledger_head and ledger_head not in source_receipts:
                _fail("MODEL_GENESIS_SOURCE_RUN_INVALID")

    for shard in corpus_manifest.get("shards", []) or []:
        path = Path(str(shard.get("path")))
        if not path.exists():
            _fail("CORPUS_SHARD_MISSING")
        if shard.get("sha256") != _hash_file(path):
            _fail("CORPUS_SHARD_MISSING")

    index_dir = state_dir / "corpus" / "indexes"
    indexes = list(index_dir.glob("sha256_*.training_corpus_index_v1.json"))
    if not indexes:
        _fail("MODEL_GENESIS_SOURCE_RUN_INVALID")
    index = load_corpus_index(indexes[0])
    if index.get("corpus_id") != corpus_manifest.get("corpus_id"):
        _fail("MODEL_GENESIS_SOURCE_RUN_INVALID")

    # Ensure no HELDOUT in examples
    for shard in corpus_manifest.get("shards", []) or []:
        path = Path(str(shard.get("path")))
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            example = loads(line)
            source = example.get("source") or {}
            if source.get("split") not in {"TRAIN", "DEV"}:
                _fail("HELDOUT_LEAK")

    # Training
    training_config = _load_training_config(config_dir / "training_config_v1.json")
    training_config_hash = sha256_prefixed(canon_bytes(training_config))

    toolchain_manifest = load_toolchain_manifest(config_dir / "training_toolchain_manifest_v1.json")
    toolchain_id = compute_toolchain_id(toolchain_manifest)
    if toolchain_manifest.get("toolchain_id") != toolchain_id:
        _fail("MODEL_GENESIS_TOOLCHAIN_DRIFT")
    toolchain_hash = sha256_prefixed(canon_bytes(toolchain_manifest))

    receipts_dir = state_dir / "training" / "sealed_receipts"
    receipts = list(receipts_dir.glob("sha256_*.sealed_training_receipt_v1.json"))
    if not receipts:
        _fail("MODEL_GENESIS_TRAINING_RECEIPT_MISSING")
    receipt = load_canon_json(receipts[0])
    if not isinstance(receipt, dict) or receipt.get("schema_version") != "sealed_training_receipt_v1":
        _fail("MODEL_GENESIS_TRAINING_RECEIPT_MISSING")
    if receipt.get("network_used") is not False:
        _fail("TRAINING_NETWORK_USED")
    if receipt.get("toolchain_manifest_hash") != toolchain_hash:
        _fail("MODEL_GENESIS_TOOLCHAIN_DRIFT")
    if receipt.get("training_config_hash") != training_config_hash:
        _fail("TRAINING_CONFIG_HASH_MISMATCH")
    if receipt.get("corpus_manifest_hash") != manifest_hash:
        _fail("MODEL_GENESIS_SOURCE_RUN_INVALID")

    weights_dir = state_dir / "training" / "outputs" / "weights"
    weights_hash = str(receipt.get("weights_hash") or "")
    weights_name = ""
    if weights_hash.startswith("sha256:"):
        weights_name = f"sha256_{weights_hash.split(':',1)[1]}.weights.bin"
    weights_path = weights_dir / weights_name if weights_name else weights_dir / "weights.bin"
    if not weights_path.exists():
        weights_files = list(weights_dir.glob("sha256_*.weights.bin"))
        if not weights_files:
            _fail("MODEL_GENESIS_WEIGHTS_HASH_MISMATCH")
        weights_path = weights_files[0]
    if receipt.get("weights_hash") != _hash_file(weights_path):
        _fail("MODEL_GENESIS_WEIGHTS_HASH_MISMATCH")

    # Bundle
    bundles_dir = state_dir / "training" / "outputs" / "bundles"
    bundles = list(bundles_dir.glob("sha256_*.model_weights_bundle_v1.json"))
    if not bundles:
        _fail("MODEL_GENESIS_WEIGHTS_HASH_MISMATCH")
    bundle = load_bundle(bundles[0])
    bundle_id = compute_bundle_id(bundle)
    if bundle.get("bundle_id") != bundle_id:
        _fail("MODEL_GENESIS_WEIGHTS_HASH_MISMATCH")
    if bundle.get("training_receipt_hash") != sha256_prefixed(canon_bytes(receipt)):
        _fail("MODEL_GENESIS_TRAINING_RECEIPT_MISSING")
    training_head = None
    for entry in entries:
        if entry.get("event_type") == "SMG_TRAINING_DONE":
            training_head = entry.get("entry_hash")
            break
    if not isinstance(training_head, str):
        _fail("MODEL_GENESIS_TRAINING_RECEIPT_MISSING")
    if bundle.get("training_ledger_head_hash") != training_head:
        _fail("MODEL_GENESIS_WEIGHTS_HASH_MISMATCH")

    # Eval receipts
    eval_config = _load_eval_config(config_dir / "eval_config_v1.json")
    thresholds = pack.get("thresholds") or {}
    eval_receipts_dir = state_dir / "eval" / "sealed_receipts"
    eval_receipts = list(eval_receipts_dir.glob("sha256_*.sealed_model_eval_receipt_v1.json"))
    if not eval_receipts:
        _fail("MODEL_GENESIS_EVAL_RECEIPT_MISSING")
    sealed_eval: dict[str, dict[str, Any]] = {}
    for path in eval_receipts:
        rec = load_canon_json(path)
        if not isinstance(rec, dict) or rec.get("schema_version") != "sealed_model_eval_receipt_v1":
            _fail("MODEL_GENESIS_EVAL_RECEIPT_MISSING")
        if rec.get("network_used") is not False:
            _fail("MODEL_GENESIS_EVAL_RECEIPT_MISSING")
        rec_hash = sha256_prefixed(canon_bytes(rec))
        sealed_eval[rec.get("eval_suite_id")] = rec
        if path.name != f"sha256_{rec_hash.split(':',1)[1]}.sealed_model_eval_receipt_v1.json":
            _fail("MODEL_GENESIS_EVAL_RECEIPT_MISSING")

    # Model eval receipt
    model_eval_dir = state_dir / "eval" / "model_eval_receipts"
    model_eval = list(model_eval_dir.glob("sha256_*.model_eval_receipt_v1.json"))
    if not model_eval:
        _fail("MODEL_GENESIS_EVAL_RECEIPT_MISSING")
    eval_receipt = load_canon_json(model_eval[0])
    if not isinstance(eval_receipt, dict) or eval_receipt.get("schema_version") != "model_eval_receipt_v1":
        _fail("MODEL_GENESIS_EVAL_RECEIPT_MISSING")
    if not eval_receipt.get("meets_thresholds", False):
        _fail("MODEL_GENESIS_THRESHOLDS_NOT_MET")
    sealed_hashes = eval_receipt.get("sealed_eval_receipt_hashes") or []
    if not isinstance(sealed_hashes, list) or not sealed_hashes:
        _fail("MODEL_GENESIS_EVAL_RECEIPT_MISSING")
    for h in sealed_hashes:
        if not isinstance(h, str):
            _fail("MODEL_GENESIS_EVAL_RECEIPT_MISSING")
        # confirm sealed receipt exists
        target = eval_receipts_dir / f"sha256_{h.split(':',1)[1]}.sealed_model_eval_receipt_v1.json"
        if not target.exists():
            _fail("MODEL_GENESIS_EVAL_RECEIPT_MISSING")

    # Thresholds (rational cross-multiply)
    def _meets(metric: dict[str, Any], min_num: int, min_den: int) -> bool:
        num = int(metric.get("num", metric.get("metric_num", 0)))
        den = int(metric.get("den", metric.get("metric_den", 1)))
        return num * min_den >= min_num * den

    math_metric = eval_receipt.get("math_metric") or {}
    science_metric = eval_receipt.get("science_metric") or {}
    safety_metric = eval_receipt.get("safety_metric") or {}

    if not _meets(math_metric, int(thresholds.get("math_pass_min_num", 0)), int(thresholds.get("math_pass_min_den", 1))):
        _fail("MODEL_GENESIS_THRESHOLDS_NOT_MET")
    if not _meets(science_metric, int(thresholds.get("science_metric_min_num", 0)), int(thresholds.get("science_metric_min_den", 1))):
        _fail("MODEL_GENESIS_THRESHOLDS_NOT_MET")
    # safety is regression max (<=)
    safety_num = int(safety_metric.get("num", safety_metric.get("metric_num", 0)))
    safety_den = int(safety_metric.get("den", safety_metric.get("metric_den", 1)))
    max_num = int(thresholds.get("safety_regression_max_num", 0))
    max_den = int(thresholds.get("safety_regression_max_den", 1))
    if safety_num * max_den > max_num * safety_den:
        _fail("MODEL_GENESIS_SAFETY_REGRESSION")

    # Promotion bundle
    promo_dir = state_dir / "promotion"
    promo_files = list(promo_dir.glob("sha256_*.model_promotion_bundle_v1.json"))
    if not promo_files:
        _fail("MODEL_GENESIS_FATAL_UNHANDLED")

    return {"status": "VALID", "ledger_head": head_hash, "corpus_id": corpus_manifest.get("corpus_id")}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smg_state_dir", required=True)
    parser.add_argument("--mode", choices=["prefix", "full"], default="prefix")
    args = parser.parse_args()
    try:
        result = verify(Path(args.smg_state_dir), mode=args.mode)
    except CanonError as exc:
        print(f"INVALID: {exc}")
        raise SystemExit(2) from exc
    print("VALID")
    for key, value in result.items():
        if key == "status":
            continue
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
