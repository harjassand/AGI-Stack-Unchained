from __future__ import annotations

from pathlib import Path
from typing import Any

from cdel.v1_7r.canon import canon_bytes, load_canon_json, sha256_prefixed, write_canon_json, write_jsonl_line
from cdel.v11_0.arch_bundle import compute_architecture_bundle_id, compute_weights_bundle_id, compute_promotion_bundle_id
from cdel.v11_0.arch_synthesis_ledger import compute_entry_hash
from cdel.v11_0.architecture_builder_v1 import build_manifest, compute_arch_id
from cdel.v11_0.fixed_q32_v1 import Q, q32_from_ratio, q32_obj, parse_q32, iroot2_floor, iroot4_floor
from cdel.v11_0.novelty_v1 import compute_novelty
from cdel.v11_0.path_canon_v1 import canon_root_v1
from cdel.v11_0.topology_fingerprint_v1 import compute_fingerprint


def repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _relpath(path: Path, state_dir: Path) -> str:
    return path.resolve().relative_to(state_dir.resolve()).as_posix()


def _write_root_manifest(state_dir: Path, agi_root_raw: str) -> Path:
    canon = canon_root_v1(agi_root_raw)
    manifest = dict(canon)
    manifest.update(
        {
            "schema_version": "sas_root_manifest_v1",
            "canon_time_utc": "2026-02-04T00:00:00Z",
            "agi_root_canon_hash": sha256_prefixed(str(canon["agi_root_canon"]).encode("utf-8")),
            "sas_root_canon_hash": sha256_prefixed(str(canon["sas_root_canon"]).encode("utf-8")),
        }
    )
    manifest_hash = sha256_prefixed(canon_bytes(manifest))
    out_path = state_dir / "health" / f"sha256_{manifest_hash.split(':',1)[1]}.sas_root_manifest_v1.json"
    write_canon_json(out_path, manifest)
    return out_path


def build_valid_state(tmp_path: Path) -> dict[str, Any]:
    # Establish agi_root and sas_root
    agi_root = tmp_path / "agi_root"
    sas_root = agi_root / "daemon" / "rsi_arch_synthesis_v11_0"
    config_dir = sas_root / "config"
    state_dir = sas_root / "state"
    control_dir = state_dir / "control"
    ledger_dir = state_dir / "ledger"
    (config_dir).mkdir(parents=True, exist_ok=True)
    (control_dir).mkdir(parents=True, exist_ok=True)
    (ledger_dir).mkdir(parents=True, exist_ok=True)

    # Enable files + lease
    (control_dir / "ENABLE_RESEARCH").write_text("enable", encoding="utf-8")
    (control_dir / "ENABLE_ARCH_SYNTHESIS").write_text("enable", encoding="utf-8")
    (control_dir / "ENABLE_TRAINING").write_text("enable", encoding="utf-8")
    (control_dir / "ENABLE_MODEL_GENESIS").write_text("enable", encoding="utf-8")

    lease = load_canon_json(repo_root() / "campaigns" / "rsi_arch_synthesis_v11_0" / "arch_synthesis_lease_token_v1.json")
    write_canon_json(control_dir / "ARCH_SYNTHESIS_LEASE.json", lease)

    # Copy config from campaigns
    camp = repo_root() / "campaigns" / "rsi_arch_synthesis_v11_0"
    allowlist = load_canon_json(camp / "arch_allowlist_v1.json")
    search_cfg = load_canon_json(camp / "arch_search_config_v1.json")
    training_cfg = load_canon_json(camp / "arch_training_config_v1.json")
    eval_cfg_dev = load_canon_json(camp / "arch_eval_config_dev_v1.json")
    eval_cfg_held = load_canon_json(camp / "arch_eval_config_heldout_v1.json")
    toolchain = load_canon_json(camp / "arch_synthesis_toolchain_manifest_v1.json")

    # Registry/opset files are content-addressed; copy them
    registry_path = next(camp.glob("sha256_*.sas_family_registry_v1.json"))
    opset_path = next(camp.glob("sha256_*.sas_opset_manifest_v1.json"))
    registry = load_canon_json(registry_path)
    opset = load_canon_json(opset_path)

    write_canon_json(config_dir / "arch_allowlist_v1.json", allowlist)
    write_canon_json(config_dir / "arch_search_config_v1.json", search_cfg)
    write_canon_json(config_dir / "arch_training_config_v1.json", training_cfg)
    write_canon_json(config_dir / "arch_eval_config_dev_v1.json", eval_cfg_dev)
    write_canon_json(config_dir / "arch_eval_config_heldout_v1.json", eval_cfg_held)
    write_canon_json(config_dir / "arch_synthesis_toolchain_manifest_v1.json", toolchain)
    write_canon_json(config_dir / "sas_family_registry_v1.json", registry)
    write_canon_json(config_dir / "sas_opset_manifest_v1.json", opset)

    # Pack (for completeness)
    pack = load_canon_json(camp / "rsi_arch_synthesis_pack_v1.json")
    write_canon_json(config_dir / "rsi_arch_synthesis_pack_v1.json", pack)

    # State layout
    (state_dir / "arch" / "candidates").mkdir(parents=True, exist_ok=True)
    (state_dir / "arch" / "manifests").mkdir(parents=True, exist_ok=True)
    (state_dir / "arch" / "fingerprints").mkdir(parents=True, exist_ok=True)
    (state_dir / "arch" / "build_receipts").mkdir(parents=True, exist_ok=True)
    (state_dir / "arch" / "bundles").mkdir(parents=True, exist_ok=True)
    (state_dir / "training" / "ledgers").mkdir(parents=True, exist_ok=True)
    (state_dir / "training" / "sealed_receipts").mkdir(parents=True, exist_ok=True)
    (state_dir / "training" / "outputs" / "weights").mkdir(parents=True, exist_ok=True)
    (state_dir / "training" / "outputs" / "bundles").mkdir(parents=True, exist_ok=True)
    (state_dir / "eval" / "dev_receipts").mkdir(parents=True, exist_ok=True)
    (state_dir / "eval" / "heldout_receipts").mkdir(parents=True, exist_ok=True)
    (state_dir / "eval" / "fixtures").mkdir(parents=True, exist_ok=True)
    (state_dir / "novelty" / "reports").mkdir(parents=True, exist_ok=True)
    (state_dir / "promotion").mkdir(parents=True, exist_ok=True)
    (state_dir / "health").mkdir(parents=True, exist_ok=True)

    # Root manifest
    _write_root_manifest(state_dir, str(agi_root))

    # Training dataset
    train_src = camp / "fixtures" / "train_examples_v1.jsonl"
    train_dst = state_dir / str(training_cfg.get("dataset_path"))
    train_dst.parent.mkdir(parents=True, exist_ok=True)
    train_dst.write_bytes(train_src.read_bytes())

    # Eval fixtures
    dev_src = camp / "fixtures" / "dev_eval_fixture_v1.json"
    held_src = camp / "fixtures" / "heldout_eval_fixture_v1.json"
    dev_dst = state_dir / str(eval_cfg_dev.get("dataset_path"))
    held_dst = state_dir / str(eval_cfg_held.get("dataset_path"))
    dev_dst.parent.mkdir(parents=True, exist_ok=True)
    held_dst.parent.mkdir(parents=True, exist_ok=True)
    dev_dst.write_bytes(dev_src.read_bytes())
    held_dst.write_bytes(held_src.read_bytes())

    # Arch IR (single candidate)
    arch_ir = {
        "schema_version": "sas_arch_ir_v1",
        "arch_family": "toy_transformer_v1",
        "arch_seed": 0,
        "model_io": {"vocab_size": 32, "seq_len": 8, "task_head": "lm_head_v1"},
        "hyperparams": {
            "depth": 2,
            "width": 8,
            "attn_layers": 2,
            "ssm_layers": 0,
            "conv_layers": 0,
            "rnn_layers": 0,
            "memory_tokens": 0,
        },
        "constraints": {"max_params": 200000, "max_activation_mb": 64},
    }
    arch_id = compute_arch_id(arch_ir)
    arch_ir_path = state_dir / "arch" / "candidates" / f"sha256_{arch_id.split(':',1)[1]}.sas_arch_ir_v1.json"
    write_canon_json(arch_ir_path, arch_ir)

    # Manifest + fingerprint
    toolchain_hash = sha256_prefixed(canon_bytes(toolchain))
    builder_version = registry["families"][0]["builder_version"]
    manifest = build_manifest(arch_ir=arch_ir, builder_version=builder_version, toolchain_hash=toolchain_hash)
    manifest_hash = sha256_prefixed(canon_bytes(manifest))
    manifest_path = state_dir / "arch" / "manifests" / f"sha256_{manifest_hash.split(':',1)[1]}.sas_arch_manifest_v1.json"
    write_canon_json(manifest_path, manifest)

    fingerprint = compute_fingerprint(manifest)
    fingerprint_hash = sha256_prefixed(canon_bytes(fingerprint))
    fingerprint_path = state_dir / "arch" / "fingerprints" / f"sha256_{fingerprint_hash.split(':',1)[1]}.sas_topology_fingerprint_v1.json"
    write_canon_json(fingerprint_path, fingerprint)

    # Build receipt
    build_receipt = {
        "schema_version": "sas_arch_build_receipt_v1",
        "arch_id": arch_id,
        "arch_graph_hash": manifest.get("arch_graph_hash"),
        "init_weights_hash": manifest.get("init_weights_hash"),
        "arch_manifest_hash": manifest_hash,
        "fingerprint_hash": fingerprint_hash,
        "toolchain_hash": toolchain_hash,
        "allowlist_hash": sha256_prefixed(canon_bytes(allowlist)),
        "family_registry_hash": sha256_prefixed(canon_bytes(registry)),
        "opset_hash": sha256_prefixed(canon_bytes(opset)),
        "builder_version": builder_version,
        "arch_ir_path": _relpath(arch_ir_path, state_dir),
        "arch_manifest_path": _relpath(manifest_path, state_dir),
        "fingerprint_path": _relpath(fingerprint_path, state_dir),
        "network_used": False,
        "time_ms": 1,
    }
    build_receipt_hash = sha256_prefixed(canon_bytes(build_receipt))
    build_receipt_path = state_dir / "arch" / "build_receipts" / f"sha256_{build_receipt_hash.split(':',1)[1]}.sas_arch_build_receipt_v1.json"
    write_canon_json(build_receipt_path, build_receipt)

    # Architecture bundle
    arch_bundle = {
        "schema_version": "sas_architecture_bundle_v1",
        "bundle_id": "",
        "arch_id": arch_id,
        "arch_ir_hash": sha256_prefixed(canon_bytes(arch_ir)),
        "arch_manifest_hash": manifest_hash,
        "fingerprint_hash": fingerprint_hash,
        "build_receipt_hash": build_receipt_hash,
        "arch_graph_hash": manifest.get("arch_graph_hash"),
        "toolchain_hash": toolchain_hash,
        "allowlist_hash": sha256_prefixed(canon_bytes(allowlist)),
        "family_registry_hash": sha256_prefixed(canon_bytes(registry)),
        "opset_hash": sha256_prefixed(canon_bytes(opset)),
        "builder_version": builder_version,
    }
    arch_bundle["bundle_id"] = compute_architecture_bundle_id(arch_bundle)
    arch_bundle_path = state_dir / "arch" / "bundles" / f"sha256_{arch_bundle['bundle_id'].split(':',1)[1]}.sas_architecture_bundle_v1.json"
    write_canon_json(arch_bundle_path, arch_bundle)

    # Training receipt + weights
    weights_dir = state_dir / "training" / "outputs" / "weights"
    weights_dir.mkdir(parents=True, exist_ok=True)
    weights_bytes = b"weights" + b"\x00" * 8
    weights_hash = sha256_prefixed(weights_bytes)
    weights_path = weights_dir / f"sha256_{weights_hash.split(':',1)[1]}.weights.bin"
    weights_path.write_bytes(weights_bytes)

    corpus_id = sha256_prefixed(train_dst.read_bytes())
    min_time_ms = int(training_cfg.get("min_time_ms", 0))
    training_receipt = {
        "schema_version": "sas_sealed_training_receipt_v1",
        "arch_id": arch_id,
        "arch_graph_hash": manifest.get("arch_graph_hash"),
        "toolchain_hash": toolchain_hash,
        "training_config_hash": sha256_prefixed(canon_bytes(training_cfg)),
        "corpus_id": corpus_id,
        "weights_sha256": weights_hash,
        "dataset_path": _relpath(train_dst, state_dir),
        "weights_path": _relpath(weights_path, state_dir),
        "stdout_hash": sha256_prefixed(b""),
        "stderr_hash": sha256_prefixed(b""),
        "time_ms": max(1, min_time_ms),
        "network_used": False,
    }
    training_receipt_hash = sha256_prefixed(canon_bytes(training_receipt))
    training_receipt_path = state_dir / "training" / "sealed_receipts" / f"sha256_{training_receipt_hash.split(':',1)[1]}.sas_sealed_training_receipt_v1.json"
    write_canon_json(training_receipt_path, training_receipt)

    # Training ledger
    train_ledger_path = state_dir / "training" / "ledgers" / "sas_training_ledger_v1.jsonl"
    entry_train = {
        "seq": 1,
        "tick": 1,
        "event_type": "SAS_TRAINING_DONE",
        "event_payload": {"weights_sha256": weights_hash},
        "prev_entry_hash": "GENESIS",
        "entry_hash": "",
    }
    entry_train["entry_hash"] = compute_entry_hash(entry_train)
    write_jsonl_line(train_ledger_path, entry_train)

    # Weights bundle
    weights_bundle = {
        "schema_version": "sas_weights_bundle_v1",
        "bundle_id": "",
        "arch_id": arch_id,
        "arch_graph_hash": manifest.get("arch_graph_hash"),
        "weights_sha256": weights_hash,
        "training_ledger_head_hash": entry_train["entry_hash"],
        "training_config_hash": sha256_prefixed(canon_bytes(training_cfg)),
        "corpus_id": corpus_id,
        "toolchain_hash": toolchain_hash,
    }
    weights_bundle["bundle_id"] = compute_weights_bundle_id(weights_bundle)
    weights_bundle_path = state_dir / "training" / "outputs" / "bundles" / f"sha256_{weights_bundle['bundle_id'].split(':',1)[1]}.sas_weights_bundle_v1.json"
    write_canon_json(weights_bundle_path, weights_bundle)

    # Eval receipts
    def _eval_receipt(schema_version: str, dataset_path: Path) -> dict[str, Any]:
        import json
        data = json.loads(dataset_path.read_text(encoding="utf-8"))
        features = data.get("features") or []
        labels = data.get("labels") or []
        # simple metric: accuracy with zero bias
        correct = 0
        total = min(len(features), len(labels))
        for i in range(total):
            pred = 1 if int(features[i]) >= 0 else 0
            if pred == int(labels[i]):
                correct += 1
        metric_q = q32_from_ratio(correct, total if total > 0 else 1)
        utility_q = parse_q32(metric_q)
        exponent = {"num": 1, "den": 4}
        penalty_q = iroot4_floor(int(manifest.get("param_count", 0)) << 128)
        capacity_q = (utility_q << 32) // penalty_q
        return {
            "schema_version": schema_version,
            "arch_id": arch_id,
            "arch_graph_hash": manifest.get("arch_graph_hash"),
            "weights_sha256": weights_hash,
            "param_count": int(manifest.get("param_count", 0)),
            "primary_metric_name": "accuracy",
            "primary_metric_direction": "higher_is_better",
            "primary_metric_q32": metric_q,
            "utility_q32": q32_obj(utility_q),
            "param_penalty_exponent": exponent,
            "param_penalty_q32": q32_obj(penalty_q),
            "capacity_efficiency_q32": q32_obj(capacity_q),
            "eval_config_hash": sha256_prefixed(canon_bytes(eval_cfg_dev if schema_version=="sas_model_eval_receipt_v1" else eval_cfg_held)),
            "dataset_path": _relpath(dataset_path, state_dir),
            "toolchain_hash": toolchain_hash,
            "stdout_hash": sha256_prefixed(b""),
            "stderr_hash": sha256_prefixed(b""),
            "time_ms": 1,
            "network_used": False,
        }

    dev_receipt = _eval_receipt("sas_model_eval_receipt_v1", dev_dst)
    dev_receipt_hash = sha256_prefixed(canon_bytes(dev_receipt))
    dev_receipt_path = state_dir / "eval" / "dev_receipts" / f"sha256_{dev_receipt_hash.split(':',1)[1]}.sas_model_eval_receipt_v1.json"
    write_canon_json(dev_receipt_path, dev_receipt)

    held_receipt = _eval_receipt("sas_model_eval_receipt_heldout_v1", held_dst)
    held_receipt_hash = sha256_prefixed(canon_bytes(held_receipt))
    held_receipt_path = state_dir / "eval" / "heldout_receipts" / f"sha256_{held_receipt_hash.split(':',1)[1]}.sas_model_eval_receipt_heldout_v1.json"
    write_canon_json(held_receipt_path, held_receipt)

    # Novelty report
    novelty_report = compute_novelty(fingerprint, fingerprint)
    novelty_hash = sha256_prefixed(canon_bytes(novelty_report))
    novelty_path = state_dir / "novelty" / "reports" / f"sha256_{novelty_hash.split(':',1)[1]}.sas_novelty_report_v1.json"
    write_canon_json(novelty_path, novelty_report)

    # Promotion bundle
    promo = {
        "schema_version": "sas_promotion_bundle_v1",
        "bundle_id": "",
        "baseline_model_id": weights_bundle["bundle_id"],
        "baseline_arch_id": arch_id,
        "candidate_architecture_bundle_id": arch_bundle["bundle_id"],
        "candidate_weights_bundle_id": weights_bundle["bundle_id"],
        "dev_eval_receipt_sha256": dev_receipt_hash,
        "heldout_eval_receipt_sha256": held_receipt_hash,
        "baseline_fingerprint_hash": fingerprint.get("signature_hash"),
        "candidate_fingerprint_hash": fingerprint.get("signature_hash"),
        "novelty_report_sha256": novelty_hash,
        "min_utility_delta_q32": {"schema_version": "q32_v1", "shift": 32, "q": "0"},
        "min_efficiency_delta_q32": {"schema_version": "q32_v1", "shift": 32, "q": "0"},
        "max_utility_regression_q32": {"schema_version": "q32_v1", "shift": 32, "q": "0"},
        "require_novelty": False,
        "min_novelty_q32": {"schema_version": "q32_v1", "shift": 32, "q": "0"},
        "param_penalty_exponent": {"num": 1, "den": 4},
        "baseline_utility_q32": dev_receipt["utility_q32"],
        "candidate_utility_q32": held_receipt["utility_q32"],
        "baseline_capacity_efficiency_q32": dev_receipt["capacity_efficiency_q32"],
        "candidate_capacity_efficiency_q32": held_receipt["capacity_efficiency_q32"],
        "novelty_score_q32": novelty_report["novelty_score_q32"],
        "acceptance_decision": {"pass": True, "reasons": []},
        "created_utc": "2026-02-04T00:00:00Z",
    }
    promo["bundle_id"] = compute_promotion_bundle_id(promo)
    promo_path = state_dir / "promotion" / f"sha256_{promo['bundle_id'].split(':',1)[1]}.sas_promotion_bundle_v1.json"
    write_canon_json(promo_path, promo)

    # Ledger (minimal)
    ledger_path = ledger_dir / "sas_synthesis_ledger_v1.jsonl"
    entry_boot = {
        "seq": 1,
        "tick": 0,
        "event_type": "SAS_BOOT",
        "event_payload": {},
        "prev_entry_hash": "GENESIS",
        "entry_hash": "",
    }
    entry_boot["entry_hash"] = compute_entry_hash(entry_boot)
    entry_shutdown = {
        "seq": 2,
        "tick": 1,
        "event_type": "SAS_SHUTDOWN",
        "event_payload": {},
        "prev_entry_hash": entry_boot["entry_hash"],
        "entry_hash": "",
    }
    entry_shutdown["entry_hash"] = compute_entry_hash(entry_shutdown)
    write_jsonl_line(ledger_path, entry_boot)
    write_jsonl_line(ledger_path, entry_shutdown)

    ignition = {
        "schema_version": "sas_ignition_receipt_v1",
        "icore_id": "sha256:" + "a" * 64,
        "meta_hash": (repo_root() / "meta-core" / "meta_constitution" / "v11_0" / "META_HASH").read_text(encoding="utf-8").strip(),
        "ledger_head_hash": entry_shutdown["entry_hash"],
        "created_utc": "2026-02-04T00:00:00Z",
    }
    write_canon_json(ledger_dir / "sas_ignition_receipt_v1.json", ignition)

    write_canon_json(state_dir / "health" / "sas_health_report_v1.json", {"last_run": ignition["created_utc"], "status": "OK"})

    return {
        "sas_root": sas_root,
        "state_dir": state_dir,
        "arch_ir_path": arch_ir_path,
        "training_receipt_path": training_receipt_path,
        "weights_bundle_path": weights_bundle_path,
        "novelty_path": novelty_path,
    }
