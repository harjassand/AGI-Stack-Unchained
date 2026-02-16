"""Verifier for RSI Architecture Synthesis v11.0."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ..v1_7r.canon import CanonError, canon_bytes, load_canon_json, sha256_prefixed
from .arch_bundle import (
    compute_architecture_bundle_id,
    compute_promotion_bundle_id,
    compute_weights_bundle_id,
)
from .arch_synthesis_ledger import SYNTH_EVENT_TYPES, TRAIN_EVENT_TYPES, load_ledger, validate_chain
from .architecture_builder_v1 import build_manifest, compute_arch_id, enforce_allowlist
from .fixed_q32_v1 import Q, Q32Error, parse_q32, q32_from_ratio, q32_obj, iroot2_floor, iroot4_floor
from .novelty_v1 import recompute_novelty_score
from .path_canon_v1 import canon_root_v1
from .topology_fingerprint_v1 import compute_fingerprint


class SASError(CanonError):
    pass


def _fail(reason: str) -> None:
    raise SASError(reason)


def _hash_file(path: Path) -> str:
    return sha256_prefixed(path.read_bytes())


def _load_json(path: Path) -> Any:
    try:
        return load_canon_json(path)
    except CanonError as exc:
        msg = str(exc)
        if "floats are not allowed" in msg:
            _fail("NON_Q32_VALUE")
        raise


def _require_schema(obj: Any, schema_version: str) -> dict[str, Any]:
    if not isinstance(obj, dict) or obj.get("schema_version") != schema_version:
        _fail("SCHEMA_INVALID")
    return obj


def _check_path_value(path_value: str) -> None:
    if path_value == "":
        _fail("PATH_TRAVERSAL_FORBIDDEN")
    if path_value.startswith("/"):
        _fail("ABSOLUTE_PATH_FORBIDDEN")
    if ".." in path_value:
        _fail("PATH_TRAVERSAL_FORBIDDEN")
    if "\\" in path_value:
        _fail("PATH_TRAVERSAL_FORBIDDEN")
    if any(ch.isspace() for ch in path_value):
        _fail("PATH_HAS_WHITESPACE")


def _validate_paths(obj: Any, key_hint: str = "") -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            _validate_paths(value, key)
    elif isinstance(obj, list):
        for item in obj:
            _validate_paths(item, key_hint)
    else:
        if isinstance(obj, str) and "path" in key_hint.lower():
            _check_path_value(obj)


def _parse_q32(obj: Any) -> int:
    try:
        return parse_q32(obj)
    except Q32Error:
        _fail("NON_Q32_VALUE")
    return 0


def _utility_q(metric_q: int, direction: str) -> int:
    if direction == "higher_is_better":
        return int(metric_q)
    if direction == "lower_is_better":
        if metric_q <= 0:
            _fail("METRIC_NONPOSITIVE_FOR_INVERT")
        return (Q * Q) // int(metric_q)
    _fail("SCHEMA_INVALID")
    return 0


def _param_penalty_q(param_count: int, exponent: dict[str, Any]) -> int:
    num = int(exponent.get("num", 0))
    den = int(exponent.get("den", 0))
    if (num, den) == (1, 1):
        return int(param_count) << 32
    if (num, den) == (1, 2):
        return iroot2_floor(int(param_count) << 64)
    if (num, den) == (1, 4):
        return iroot4_floor(int(param_count) << 128)
    _fail("SCHEMA_INVALID")
    return 0


def _capacity_efficiency_q(utility_q: int, penalty_q: int) -> int:
    if penalty_q <= 0:
        _fail("Q32_DIV_BY_ZERO")
    return (int(utility_q) << 32) // int(penalty_q)


def _load_single(dir_path: Path, pattern: str) -> Path:
    items = list(dir_path.glob(pattern))
    if not items:
        _fail("MISSING_ARTIFACT")
    return items[0]


def _verify_root_manifest(state_dir: Path) -> dict[str, Any]:
    health_dir = state_dir / "health"
    manifests = list(health_dir.glob("sha256_*.sas_root_manifest_v1.json"))
    if not manifests:
        _fail("ROOT_CANON_MISMATCH")
    manifest_path = manifests[0]
    manifest = _load_json(manifest_path)
    _require_schema(manifest, "sas_root_manifest_v1")
    expected = canon_root_v1(str(manifest.get("agi_root_raw", "")))
    # Verify fields
    for key in ["agi_root_raw", "agi_root_stripped", "agi_root_canon", "was_trimmed", "sas_root_canon", "canon_method"]:
        if manifest.get(key) != expected.get(key):
            _fail("ROOT_CANON_MISMATCH")
    agi_root_canon = str(expected.get("agi_root_canon"))
    sas_root_canon = str(expected.get("sas_root_canon"))
    if str(state_dir.parent.resolve()) != sas_root_canon:
        _fail("ROOT_CANON_MISMATCH")
    if manifest.get("agi_root_canon_hash") != sha256_prefixed(agi_root_canon.encode("utf-8")):
        _fail("ROOT_CANON_MISMATCH")
    if manifest.get("sas_root_canon_hash") != sha256_prefixed(sas_root_canon.encode("utf-8")):
        _fail("ROOT_CANON_MISMATCH")
    # content-addressed filename
    manifest_hash = sha256_prefixed(canon_bytes(manifest))
    if not manifest_path.name.startswith(f"sha256_{manifest_hash.split(':',1)[1]}"):
        _fail("ROOT_CANON_MISMATCH")
    return manifest


def _require_enable_files(state_dir: Path) -> None:
    control = state_dir / "control"
    if not (control / "ENABLE_RESEARCH").exists():
        _fail("MISSING_ENABLE_RESEARCH")
    if not (control / "ENABLE_ARCH_SYNTHESIS").exists():
        _fail("MISSING_ENABLE_ARCH_SYNTHESIS")
    if not (control / "ENABLE_TRAINING").exists():
        _fail("MISSING_ENABLE_TRAINING")
    if not (control / "ENABLE_MODEL_GENESIS").exists():
        _fail("MISSING_ENABLE_MODEL_GENESIS")
    if not (control / "ARCH_SYNTHESIS_LEASE.json").exists():
        _fail("MISSING_ARTIFACT")


def _load_constants(repo_root: Path) -> dict[str, Any]:
    path = repo_root / "meta-core" / "meta_constitution" / "v11_0" / "constants_v1.json"
    if not path.exists():
        _fail("MISSING_ARTIFACT")
    constants = _load_json(path)
    _require_schema(constants, "constants_v1")
    return constants


def _load_eval_dataset(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        _fail("SCHEMA_INVALID")
    return payload


def _check_training_corpus_no_heldout(dataset_path: Path) -> None:
    for line in dataset_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        if not isinstance(obj, dict):
            continue
        source = obj.get("source") or {}
        split = source.get("split")
        if split not in {"TRAIN", "DEV"}:
            _fail("HELDOUT_LEAK")


def verify(state_dir: Path, *, mode: str) -> dict[str, Any]:
    sas_root = state_dir.parent
    config_dir = sas_root / "config"

    _verify_root_manifest(state_dir)
    _require_enable_files(state_dir)

    # Ledger
    ledger_path = state_dir / "ledger" / "sas_synthesis_ledger_v1.jsonl"
    entries = load_ledger(ledger_path)
    head_hash, _last_seq, _min_tick, _max_tick = validate_chain(entries, allowed_events=SYNTH_EVENT_TYPES)

    if mode == "full":
        ignition_path = state_dir / "ledger" / "sas_ignition_receipt_v1.json"
        if not ignition_path.exists():
            _fail("MISSING_ARTIFACT")

    # Load config artifacts
    pack = _require_schema(_load_json(config_dir / "rsi_arch_synthesis_pack_v1.json"), "rsi_arch_synthesis_pack_v1")
    allowlist = _require_schema(_load_json(config_dir / "arch_allowlist_v1.json"), "arch_allowlist_v1")
    _require_schema(_load_json(config_dir / "arch_search_config_v1.json"), "arch_search_config_v1")
    training_cfg = _require_schema(_load_json(config_dir / "arch_training_config_v1.json"), "arch_training_config_v1")
    eval_cfg_dev = _require_schema(_load_json(config_dir / "arch_eval_config_dev_v1.json"), "arch_eval_config_dev_v1")
    eval_cfg_held = _require_schema(_load_json(config_dir / "arch_eval_config_heldout_v1.json"), "arch_eval_config_heldout_v1")
    toolchain = _require_schema(_load_json(config_dir / "arch_synthesis_toolchain_manifest_v1.json"), "arch_synthesis_toolchain_manifest_v1")
    registry = _require_schema(_load_json(config_dir / "sas_family_registry_v1.json"), "sas_family_registry_v1")
    opset = _require_schema(_load_json(config_dir / "sas_opset_manifest_v1.json"), "sas_opset_manifest_v1")

    # Validate pinned constants
    repo_root = Path(__file__).resolve().parents[3]
    constants = _load_constants(repo_root)
    registry_hash = sha256_prefixed(canon_bytes(registry))
    opset_hash = sha256_prefixed(canon_bytes(opset))
    if registry_hash != constants.get("SAS_FAMILY_REGISTRY_HASH"):
        _fail("FAMILY_REGISTRY_HASH_MISMATCH")
    if opset_hash != constants.get("SAS_OPSET_HASH"):
        _fail("OPSET_HASH_MISMATCH")

    family_builder: dict[str, str] = {}
    for entry in registry.get("families", []) or []:
        if entry.get("opset_hash") != opset_hash:
            _fail("OPSET_HASH_MISMATCH")
        name = entry.get("family_name")
        if isinstance(name, str):
            family_builder[name] = str(entry.get("builder_version", ""))

    # Allowlist budgets
    max_total_params = int(allowlist.get("max_total_params", 0))
    max_candidates = int(allowlist.get("max_candidates_per_run", 0))
    max_steps = int(allowlist.get("max_train_steps_per_candidate", 0))
    max_heldout = int(allowlist.get("max_heldout_evals_per_run", 0))

    # Validate training config steps
    steps = int(training_cfg.get("steps", 0))
    min_steps = int(training_cfg.get("min_steps", 0))
    min_time_ms = int(training_cfg.get("min_time_ms", 0))
    if max_steps and steps > max_steps:
        _fail("PARAM_BUDGET_EXCEEDED")
    if min_steps and steps < min_steps:
        _fail("MIN_WORK_NOT_MET")

    # Training corpus no heldout
    dataset_rel = str(training_cfg.get("dataset_path"))
    dataset_path = state_dir / dataset_rel
    if not dataset_path.exists():
        _fail("MISSING_ARTIFACT")
    _check_training_corpus_no_heldout(dataset_path)

    # Dev eval dataset split must not be HELDOUT
    dev_dataset_path = state_dir / str(eval_cfg_dev.get("dataset_path"))
    dev_ds = _load_eval_dataset(dev_dataset_path)
    if dev_ds.get("split") == "HELDOUT":
        _fail("HELDOUT_LEAK")

    # Heldout dataset must be heldout
    held_dataset_path = state_dir / str(eval_cfg_held.get("dataset_path"))
    held_ds = _load_eval_dataset(held_dataset_path)
    if held_ds.get("split") != "HELDOUT":
        _fail("HELDOUT_LEAK")

    # Load arch IRs
    arch_ir_paths = list((state_dir / "arch" / "candidates").glob("sha256_*.sas_arch_ir_v1.json"))
    if not arch_ir_paths:
        _fail("MISSING_ARTIFACT")
    arch_irs: dict[str, dict[str, Any]] = {}
    for path in arch_ir_paths:
        arch_ir = _require_schema(_load_json(path), "sas_arch_ir_v1")
        enforce_allowlist(arch_ir, allowlist)
        arch_id = compute_arch_id(arch_ir)
        if not path.name.startswith(f"sha256_{arch_id.split(':',1)[1]}"):
            _fail("SCHEMA_INVALID")
        if arch_id in arch_irs:
            _fail("SCHEMA_INVALID")
        arch_irs[arch_id] = arch_ir

    toolchain_hash = sha256_prefixed(canon_bytes(toolchain))

    # Manifests
    manifest_paths = list((state_dir / "arch" / "manifests").glob("sha256_*.sas_arch_manifest_v1.json"))
    if not manifest_paths:
        _fail("MISSING_ARTIFACT")
    manifests: dict[str, dict[str, Any]] = {}
    total_params = 0
    for path in manifest_paths:
        manifest = _require_schema(_load_json(path), "sas_arch_manifest_v1")
        manifest_hash = sha256_prefixed(canon_bytes(manifest))
        if not path.name.startswith(f"sha256_{manifest_hash.split(':',1)[1]}"):
            _fail("SCHEMA_INVALID")
        arch_id = manifest.get("arch_id")
        if arch_id not in arch_irs:
            _fail("SCHEMA_INVALID")
        arch_ir = arch_irs[arch_id]
        family = str(arch_ir.get("arch_family"))
        builder_version = family_builder.get(family)
        if not builder_version:
            _fail("FAMILY_NOT_IN_REGISTRY")
        recomputed = build_manifest(arch_ir=arch_ir, builder_version=str(builder_version), toolchain_hash=toolchain_hash)
        if manifest.get("arch_graph_hash") != recomputed.get("arch_graph_hash"):
            _fail("SCHEMA_INVALID")
        if manifest.get("init_weights_hash") != recomputed.get("init_weights_hash"):
            _fail("SCHEMA_INVALID")
        param_count = int(manifest.get("param_count", 0))
        total_params += param_count
        manifests[arch_id] = manifest

    if max_total_params and total_params > max_total_params:
        _fail("PARAM_BUDGET_EXCEEDED")

    # Fingerprints
    fingerprint_paths = list((state_dir / "arch" / "fingerprints").glob("sha256_*.sas_topology_fingerprint_v1.json"))
    if not fingerprint_paths:
        _fail("MISSING_ARTIFACT")
    fingerprints: dict[str, dict[str, Any]] = {}
    for path in fingerprint_paths:
        fingerprint = _require_schema(_load_json(path), "sas_topology_fingerprint_v1")
        fingerprint_hash = sha256_prefixed(canon_bytes(fingerprint))
        if not path.name.startswith(f"sha256_{fingerprint_hash.split(':',1)[1]}"):
            _fail("SCHEMA_INVALID")
        arch_id = fingerprint.get("arch_id")
        if arch_id not in manifests:
            _fail("SCHEMA_INVALID")
        expected_fp = compute_fingerprint(manifests[arch_id])
        if fingerprint.get("signature_hash") != expected_fp.get("signature_hash"):
            _fail("FINGERPRINT_HASH_MISMATCH")
        fingerprints[arch_id] = fingerprint

    # Build receipts
    build_receipt_paths = list((state_dir / "arch" / "build_receipts").glob("sha256_*.sas_arch_build_receipt_v1.json"))
    if not build_receipt_paths:
        _fail("MISSING_ARTIFACT")
    build_receipts: dict[str, dict[str, Any]] = {}
    for path in build_receipt_paths:
        build_receipt = _require_schema(_load_json(path), "sas_arch_build_receipt_v1")
        build_receipt_hash = sha256_prefixed(canon_bytes(build_receipt))
        if not path.name.startswith(f"sha256_{build_receipt_hash.split(':',1)[1]}"):
            _fail("SCHEMA_INVALID")
        arch_id = build_receipt.get("arch_id")
        if arch_id not in manifests:
            _fail("SCHEMA_INVALID")
        if build_receipt.get("network_used") is not False:
            _fail("NETWORK_USED")
        if build_receipt.get("toolchain_hash") != toolchain_hash:
            _fail("SCHEMA_INVALID")
        if build_receipt.get("allowlist_hash") != sha256_prefixed(canon_bytes(allowlist)):
            _fail("SCHEMA_INVALID")
        if build_receipt.get("family_registry_hash") != registry_hash:
            _fail("FAMILY_REGISTRY_HASH_MISMATCH")
        if build_receipt.get("opset_hash") != opset_hash:
            _fail("OPSET_HASH_MISMATCH")
        if build_receipt.get("arch_manifest_hash") != sha256_prefixed(canon_bytes(manifests[arch_id])):
            _fail("SCHEMA_INVALID")
        if build_receipt.get("fingerprint_hash") != sha256_prefixed(canon_bytes(fingerprints[arch_id])):
            _fail("FINGERPRINT_HASH_MISMATCH")
        build_receipts[arch_id] = build_receipt

    # Architecture bundles
    arch_bundle_paths = list((state_dir / "arch" / "bundles").glob("sha256_*.sas_architecture_bundle_v1.json"))
    if not arch_bundle_paths:
        _fail("MISSING_ARTIFACT")
    arch_bundles_by_arch: dict[str, dict[str, Any]] = {}
    arch_bundles_by_id: dict[str, dict[str, Any]] = {}
    for path in arch_bundle_paths:
        arch_bundle = _require_schema(_load_json(path), "sas_architecture_bundle_v1")
        arch_id = arch_bundle.get("arch_id")
        if arch_id not in arch_irs:
            _fail("SCHEMA_INVALID")
        arch_bundle_id = compute_architecture_bundle_id(arch_bundle)
        if arch_bundle.get("bundle_id") != arch_bundle_id:
            _fail("SCHEMA_INVALID")
        if not path.name.startswith(f"sha256_{arch_bundle_id.split(':',1)[1]}"):
            _fail("SCHEMA_INVALID")
        arch_bundles_by_arch[arch_id] = arch_bundle
        arch_bundles_by_id[arch_bundle_id] = arch_bundle

    # Training receipt + weights
    training_receipt_paths = list((state_dir / "training" / "sealed_receipts").glob("sha256_*.sas_sealed_training_receipt_v1.json"))
    if not training_receipt_paths:
        _fail("MISSING_ARTIFACT")
    training_receipts: dict[str, dict[str, Any]] = {}
    weights_hash_by_arch: dict[str, str] = {}
    for path in training_receipt_paths:
        training_receipt = _require_schema(_load_json(path), "sas_sealed_training_receipt_v1")
        training_receipt_hash = sha256_prefixed(canon_bytes(training_receipt))
        if not path.name.startswith(f"sha256_{training_receipt_hash.split(':',1)[1]}"):
            _fail("SCHEMA_INVALID")
        arch_id = training_receipt.get("arch_id")
        if arch_id not in manifests:
            _fail("SCHEMA_INVALID")
        if training_receipt.get("network_used") is not False:
            _fail("TRAINING_NETWORK_USED")
        if training_receipt.get("training_config_hash") != sha256_prefixed(canon_bytes(training_cfg)):
            _fail("TRAINING_CONFIG_HASH_MISMATCH")
        if training_receipt.get("toolchain_hash") != toolchain_hash:
            _fail("SCHEMA_INVALID")
        if min_time_ms and int(training_receipt.get("time_ms", 0)) < min_time_ms:
            _fail("MIN_WORK_NOT_MET")
        weights_hash = str(training_receipt.get("weights_sha256"))
        if not weights_hash.startswith("sha256:"):
            _fail("SCHEMA_INVALID")
        weights_path = state_dir / "training" / "outputs" / "weights" / f"sha256_{weights_hash.split(':',1)[1]}.weights.bin"
        if not weights_path.exists():
            _fail("MISSING_ARTIFACT")
        if weights_hash != _hash_file(weights_path):
            _fail("MODEL_WEIGHTS_HASH_MISMATCH")
        training_receipts[arch_id] = training_receipt
        weights_hash_by_arch[arch_id] = weights_hash

    # Training ledger
    train_ledger_path = state_dir / "training" / "ledgers" / "sas_training_ledger_v1.jsonl"
    train_entries = load_ledger(train_ledger_path)
    _train_head_hash, _seq, _min_tick, _max_tick = validate_chain(train_entries, allowed_events=TRAIN_EVENT_TYPES)
    train_entry_hashes = {entry.get("entry_hash") for entry in train_entries if isinstance(entry.get("entry_hash"), str)}

    # Weights bundle
    weights_bundle_paths = list((state_dir / "training" / "outputs" / "bundles").glob("sha256_*.sas_weights_bundle_v1.json"))
    if not weights_bundle_paths:
        _fail("MISSING_ARTIFACT")
    weights_bundles_by_arch: dict[str, dict[str, Any]] = {}
    weights_bundles_by_id: dict[str, dict[str, Any]] = {}
    for path in weights_bundle_paths:
        weights_bundle = _require_schema(_load_json(path), "sas_weights_bundle_v1")
        if "training_ledger_head_hash" not in weights_bundle:
            _fail("WEIGHTS_BUNDLE_MISSING_TRAINING_LEDGER_HEAD")
        if weights_bundle.get("training_ledger_head_hash") not in train_entry_hashes:
            _fail("SCHEMA_INVALID")
        arch_id = weights_bundle.get("arch_id")
        if arch_id not in manifests:
            _fail("SCHEMA_INVALID")
        if weights_bundle.get("weights_sha256") != weights_hash_by_arch.get(arch_id):
            _fail("MODEL_WEIGHTS_HASH_MISMATCH")
        if weights_bundle.get("training_config_hash") != sha256_prefixed(canon_bytes(training_cfg)):
            _fail("TRAINING_CONFIG_HASH_MISMATCH")
        if weights_bundle.get("toolchain_hash") != toolchain_hash:
            _fail("SCHEMA_INVALID")
        weights_bundle_id = compute_weights_bundle_id(weights_bundle)
        if weights_bundle.get("bundle_id") != weights_bundle_id:
            _fail("SCHEMA_INVALID")
        if not path.name.startswith(f"sha256_{weights_bundle_id.split(':',1)[1]}"):
            _fail("SCHEMA_INVALID")
        weights_bundles_by_arch[arch_id] = weights_bundle
        weights_bundles_by_id[weights_bundle_id] = weights_bundle

    # Eval receipts
    dev_receipts_by_arch: dict[str, dict[str, Any]] = {}
    held_receipts_by_arch: dict[str, dict[str, Any]] = {}
    receipts_by_hash: dict[str, dict[str, Any]] = {}
    receipt_metrics: dict[str, dict[str, Any]] = {}

    def _validate_receipt(receipt: dict[str, Any], schema: str, config: dict[str, Any], store: dict[str, dict[str, Any]]) -> None:
        receipt_hash = sha256_prefixed(canon_bytes(receipt))
        receipts_by_hash[receipt_hash] = receipt
        arch_id = receipt.get("arch_id")
        if arch_id not in manifests:
            _fail("SCHEMA_INVALID")
        manifest = manifests[arch_id]
        if receipt.get("param_count") != manifest.get("param_count"):
            _fail("SCHEMA_INVALID")
        if receipt.get("weights_sha256") != weights_hash_by_arch.get(arch_id):
            _fail("MODEL_WEIGHTS_HASH_MISMATCH")
        _validate_paths(receipt)
        if receipt.get("network_used") is not False:
            _fail("SCHEMA_INVALID")
        if receipt.get("eval_config_hash") != sha256_prefixed(canon_bytes(config)):
            _fail("SCHEMA_INVALID")
        metric_q = _parse_q32(receipt.get("primary_metric_q32"))
        direction = str(receipt.get("primary_metric_direction"))
        utility_q = _utility_q(metric_q, direction)
        exponent = receipt.get("param_penalty_exponent") or {}
        penalty_q = _param_penalty_q(int(manifest.get("param_count", 0)), exponent)
        if _parse_q32(receipt.get("utility_q32")) != utility_q:
            _fail("CAPACITY_EFFICIENCY_MISMATCH")
        if _parse_q32(receipt.get("param_penalty_q32")) != penalty_q:
            _fail("CAPACITY_EFFICIENCY_MISMATCH")
        capacity_q = _capacity_efficiency_q(utility_q, penalty_q)
        if _parse_q32(receipt.get("capacity_efficiency_q32")) != capacity_q:
            _fail("CAPACITY_EFFICIENCY_MISMATCH")
        store[arch_id] = receipt
        receipt_metrics[receipt_hash] = {
            "utility_q": utility_q,
            "eff_q": capacity_q,
            "arch_id": arch_id,
            "schema_version": receipt.get("schema_version"),
        }

    for path in (state_dir / "eval" / "dev_receipts").glob("sha256_*.sas_model_eval_receipt_v1.json"):
        dev_receipt = _require_schema(_load_json(path), "sas_model_eval_receipt_v1")
        dev_receipt_hash = sha256_prefixed(canon_bytes(dev_receipt))
        if not path.name.startswith(f"sha256_{dev_receipt_hash.split(':',1)[1]}"):
            _fail("SCHEMA_INVALID")
        _validate_receipt(dev_receipt, "sas_model_eval_receipt_v1", eval_cfg_dev, dev_receipts_by_arch)

    for path in (state_dir / "eval" / "heldout_receipts").glob("sha256_*.sas_model_eval_receipt_heldout_v1.json"):
        held_receipt = _require_schema(_load_json(path), "sas_model_eval_receipt_heldout_v1")
        held_receipt_hash = sha256_prefixed(canon_bytes(held_receipt))
        if not path.name.startswith(f"sha256_{held_receipt_hash.split(':',1)[1]}"):
            _fail("SCHEMA_INVALID")
        _validate_receipt(held_receipt, "sas_model_eval_receipt_heldout_v1", eval_cfg_held, held_receipts_by_arch)

    # Promotion bundle
    promo_path = _load_single(state_dir / "promotion", "sha256_*.sas_promotion_bundle_v1.json")
    promo = _require_schema(_load_json(promo_path), "sas_promotion_bundle_v1")
    _validate_paths(promo)

    candidate_arch_bundle_id = promo.get("candidate_architecture_bundle_id")
    candidate_weights_bundle_id = promo.get("candidate_weights_bundle_id")
    baseline_weights_bundle_id = promo.get("baseline_model_id")
    baseline_arch_id = promo.get("baseline_arch_id")

    candidate_arch_bundle = arch_bundles_by_id.get(candidate_arch_bundle_id)
    if not candidate_arch_bundle:
        _fail("DOMINANCE_RECOMPUTE_MISMATCH")
    candidate_arch_id = candidate_arch_bundle.get("arch_id")

    candidate_weights_bundle = weights_bundles_by_id.get(candidate_weights_bundle_id)
    if not candidate_weights_bundle:
        _fail("DOMINANCE_RECOMPUTE_MISMATCH")
    if candidate_weights_bundle.get("arch_id") != candidate_arch_id:
        _fail("DOMINANCE_RECOMPUTE_MISMATCH")

    baseline_weights_bundle = weights_bundles_by_id.get(baseline_weights_bundle_id)
    if not baseline_weights_bundle:
        _fail("DOMINANCE_RECOMPUTE_MISMATCH")
    if baseline_weights_bundle.get("arch_id") != baseline_arch_id:
        _fail("DOMINANCE_RECOMPUTE_MISMATCH")

    baseline_fp = fingerprints.get(baseline_arch_id)
    candidate_fp = fingerprints.get(candidate_arch_id)
    if not baseline_fp or not candidate_fp:
        _fail("DOMINANCE_RECOMPUTE_MISMATCH")
    if promo.get("baseline_fingerprint_hash") != baseline_fp.get("signature_hash"):
        _fail("DOMINANCE_RECOMPUTE_MISMATCH")
    if promo.get("candidate_fingerprint_hash") != candidate_fp.get("signature_hash"):
        _fail("DOMINANCE_RECOMPUTE_MISMATCH")

    baseline_receipt_hash = promo.get("dev_eval_receipt_sha256")
    candidate_receipt_hash = promo.get("heldout_eval_receipt_sha256")
    baseline_receipt = receipts_by_hash.get(baseline_receipt_hash)
    candidate_receipt = receipts_by_hash.get(candidate_receipt_hash)
    if not baseline_receipt or not candidate_receipt:
        _fail("DOMINANCE_RECOMPUTE_MISMATCH")
    if baseline_receipt.get("arch_id") != baseline_arch_id:
        _fail("DOMINANCE_RECOMPUTE_MISMATCH")
    if candidate_receipt.get("arch_id") != candidate_arch_id:
        _fail("DOMINANCE_RECOMPUTE_MISMATCH")

    # Heldout threshold applies to candidate receipt
    held_threshold_q = _parse_q32(eval_cfg_held.get("min_primary_metric_q32"))
    held_metric_q = _parse_q32(candidate_receipt.get("primary_metric_q32"))
    if held_metric_q < held_threshold_q:
        _fail("HELDOUT_THRESHOLD_NOT_MET")

    # Novelty report
    novelty_hash = promo.get("novelty_report_sha256")
    if not isinstance(novelty_hash, str) or not novelty_hash.startswith("sha256:"):
        _fail("SCHEMA_INVALID")
    novelty_path = state_dir / "novelty" / "reports" / f"sha256_{novelty_hash.split(':',1)[1]}.sas_novelty_report_v1.json"
    if not novelty_path.exists():
        _fail("MISSING_ARTIFACT")
    novelty = _require_schema(_load_json(novelty_path), "sas_novelty_report_v1")
    novelty_hash_check = sha256_prefixed(canon_bytes(novelty))
    if not novelty_path.name.startswith(f"sha256_{novelty_hash_check.split(':',1)[1]}"):
        _fail("SCHEMA_INVALID")
    if novelty.get("baseline_fingerprint_hash") != baseline_fp.get("signature_hash"):
        _fail("NOVELTY_SCORE_MISMATCH")
    if novelty.get("candidate_fingerprint_hash") != candidate_fp.get("signature_hash"):
        _fail("NOVELTY_SCORE_MISMATCH")
    novelty_q = recompute_novelty_score(novelty, baseline_fp, candidate_fp)
    if _parse_q32(novelty.get("novelty_score_q32")) != novelty_q:
        _fail("NOVELTY_SCORE_MISMATCH")

    # Q32 policy fields
    min_util_delta = _parse_q32(promo.get("min_utility_delta_q32"))
    min_eff_delta = _parse_q32(promo.get("min_efficiency_delta_q32"))
    max_regress = _parse_q32(promo.get("max_utility_regression_q32"))
    min_novelty = _parse_q32(promo.get("min_novelty_q32"))
    require_novelty = bool(promo.get("require_novelty", False))

    # Computed fields
    base_util = _parse_q32(promo.get("baseline_utility_q32"))
    cand_util = _parse_q32(promo.get("candidate_utility_q32"))
    base_eff = _parse_q32(promo.get("baseline_capacity_efficiency_q32"))
    cand_eff = _parse_q32(promo.get("candidate_capacity_efficiency_q32"))
    nov_score = _parse_q32(promo.get("novelty_score_q32"))

    baseline_metrics = receipt_metrics.get(baseline_receipt_hash)
    candidate_metrics = receipt_metrics.get(candidate_receipt_hash)
    if not baseline_metrics or not candidate_metrics:
        _fail("DOMINANCE_RECOMPUTE_MISMATCH")
    if base_util != baseline_metrics["utility_q"] or cand_util != candidate_metrics["utility_q"]:
        _fail("DOMINANCE_RECOMPUTE_MISMATCH")
    if base_eff != baseline_metrics["eff_q"] or cand_eff != candidate_metrics["eff_q"]:
        _fail("DOMINANCE_RECOMPUTE_MISMATCH")
    if nov_score != novelty_q:
        _fail("DOMINANCE_RECOMPUTE_MISMATCH")

    delta_u = cand_util - base_util
    delta_e = cand_eff - base_eff
    if delta_u < -max_regress:
        _fail("DOMINANCE_RECOMPUTE_MISMATCH")
    if not (delta_u >= min_util_delta or delta_e >= min_eff_delta):
        _fail("DOMINANCE_RECOMPUTE_MISMATCH")
    if require_novelty and nov_score < min_novelty:
        _fail("NOVELTY_REQUIRED_NOT_MET")

    # Path policy checks
    for obj in [
        *training_receipts.values(),
        *build_receipts.values(),
        *weights_bundles_by_arch.values(),
        *arch_bundles_by_arch.values(),
        novelty,
    ]:
        _validate_paths(obj)

    # Heldout eval count
    heldout_evals = len(list((state_dir / "eval" / "heldout_receipts").glob("sha256_*.sas_model_eval_receipt_heldout_v1.json")))
    if max_heldout and heldout_evals > max_heldout:
        _fail("PARAM_BUDGET_EXCEEDED")

    # Candidate count
    if max_candidates and len(arch_irs) > max_candidates:
        _fail("PARAM_BUDGET_EXCEEDED")

    # Content-addressed promotion bundle
    promo_id = promo.get("bundle_id")
    if not isinstance(promo_id, str) or not promo_path.name.startswith(f"sha256_{promo_id.split(':',1)[1]}"):
        _fail("SCHEMA_INVALID")

    return {
        "status": "VALID",
        "ledger_head_hash": head_hash,
        "arch_id": candidate_arch_id,
        "weights_bundle_id": candidate_weights_bundle_id,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sas_state_dir", required=True)
    parser.add_argument("--mode", choices=["prefix", "full"], default="prefix")
    args = parser.parse_args()
    try:
        result = verify(Path(args.sas_state_dir), mode=args.mode)
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
