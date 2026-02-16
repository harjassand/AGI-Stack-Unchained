from __future__ import annotations

from pathlib import Path
from typing import Any

from cdel.v1_7r.canon import canon_bytes, load_canon_json, sha256_prefixed, write_canon_json, write_jsonl_line
from cdel.v10_0.corpus_manifest import compute_corpus_id
from cdel.v10_0.model_bundle import compute_bundle_id
from cdel.v10_0.model_genesis_ledger import compute_entry_hash
from cdel.v10_0.training_toolchain import compute_toolchain_id
from cdel.v7_0.superego_policy import compute_policy_hash


def repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def identities() -> tuple[str, str, str]:
    root = repo_root()
    lock_path = root / "meta-core" / "meta_constitution" / "v10_0" / "immutable_core_lock_v1.json"
    meta_path = root / "meta-core" / "meta_constitution" / "v10_0" / "META_HASH"
    policy_path = root / "meta-core" / "meta_constitution" / "v10_0" / "superego_policy_v4.json"
    if lock_path.exists():
        lock = load_canon_json(lock_path)
        icore_id = str(lock.get("core_id"))
    else:
        icore_id = "sha256:" + "0" * 64
    meta_hash = meta_path.read_text(encoding="utf-8").strip() if meta_path.exists() else "0" * 64
    policy_hash = compute_policy_hash(load_canon_json(policy_path)) if policy_path.exists() else "sha256:" + "1" * 64
    return icore_id, meta_hash, policy_hash


def build_valid_state(tmp_path: Path) -> dict[str, Any]:
    smg_root = tmp_path / "smg"
    config_dir = smg_root / "config"
    state_dir = smg_root / "state"
    control_dir = state_dir / "control"
    ledger_dir = state_dir / "ledger"
    (config_dir).mkdir(parents=True, exist_ok=True)
    (control_dir).mkdir(parents=True, exist_ok=True)
    (ledger_dir).mkdir(parents=True, exist_ok=True)

    icore_id, meta_hash, policy_hash = identities()

    # Enable files + lease
    (control_dir / "ENABLE_RESEARCH").write_text("enable", encoding="utf-8")
    (control_dir / "ENABLE_MODEL_GENESIS").write_text("enable", encoding="utf-8")
    (control_dir / "ENABLE_TRAINING").write_text("enable", encoding="utf-8")
    lease = {
        "schema_version": "model_genesis_lease_token_v1",
        "lease_id": "sha256:" + "2" * 64,
        "issued_by": "fixture",
        "valid_from_tick": 0,
        "valid_until_tick": 10,
        "allowed_ops": ["MODEL_GENESIS_TRAIN", "MODEL_GENESIS_EVAL"],
        "max_runs": 2,
    }
    write_canon_json(control_dir / "MODEL_GENESIS_LEASE.json", lease)

    # Toolchain manifest
    toolchain = {
        "schema_version": "training_toolchain_manifest_v1",
        "toolchain_id": "",
        "python_exe_hash": "sha256:" + "3" * 64,
        "pip_freeze_hash": "sha256:" + "4" * 64,
        "trainer_backend": "toy_cpu_v1",
        "trainer_code_hash": "sha256:" + "5" * 64,
        "env_vars": {"PYTHONHASHSEED": "0"},
        "offline_required": True,
    }
    toolchain["toolchain_id"] = compute_toolchain_id(toolchain)
    toolchain_path = config_dir / "training_toolchain_manifest_v1.json"
    write_canon_json(toolchain_path, toolchain)

    # Training config + base manifest
    base_manifest = {
        "schema_version": "model_base_manifest_v1",
        "base_model_id": "sha256:" + "6" * 64,
        "description": "fixture",
    }
    base_manifest_path = config_dir / "model_base_manifest_v1.json"
    write_canon_json(base_manifest_path, base_manifest)

    training_config = {
        "schema_version": "training_config_v1",
        "base_model_id": base_manifest["base_model_id"],
        "architecture": "toy_transformer_bytelevel_v1",
        "seed": 0,
        "device": "cpu",
        "steps": 1,
        "batch_size": 1,
        "lr_num": 1,
        "lr_den": 1000,
        "max_seq_len": 8,
        "determinism": {"single_thread": True, "torch_deterministic": True},
        "output_format": "weights_bin_v1",
    }
    training_config_path = config_dir / "training_config_v1.json"
    write_canon_json(training_config_path, training_config)

    # Eval config + fixture datasets
    fixtures_dir = tmp_path / "fixtures"
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    math_dataset = fixtures_dir / "math_eval_fixture.json"
    science_dataset = fixtures_dir / "science_eval_fixture.json"
    safety_dataset = fixtures_dir / "safety_eval_fixture.json"
    math_dataset.write_text('{"features":[-1,0,1,2],"labels":[0,0,1,1]}', encoding="utf-8")
    science_dataset.write_text('{"features":[-2,1,2,3],"labels":[0,1,1,1]}', encoding="utf-8")
    safety_dataset.write_text('{"features":[0],"labels":[1]}', encoding="utf-8")

    eval_config = {
        "schema_version": "eval_config_v1",
        "math_eval_mode": "FIXTURE_EXACT_MATCH_V1",
        "science_eval_mode": "FIXTURE_ACCURACY_V1",
        "safety_eval_mode": "SUPEREGO_DENYRATE_V1",
        "suites": [
            {"suite_id": "math_heldout_fixture_v1", "kind": "MATH_HELDOUT_V1", "dataset_path": str(math_dataset)},
            {"suite_id": "science_heldout_fixture_v1", "kind": "SCI_HELDOUT_V1", "dataset_path": str(science_dataset)},
            {"suite_id": "safety_probe_fixture_v1", "kind": "SAFETY_PROBE_V1", "dataset_path": str(safety_dataset)},
        ],
    }
    eval_config_path = config_dir / "eval_config_v1.json"
    write_canon_json(eval_config_path, eval_config)

    pack = {
        "schema_version": "rsi_model_genesis_pack_v1",
        "icore_id": icore_id,
        "meta_hash": meta_hash,
        "superego_policy_hash": policy_hash,
        "smg_root": str(smg_root),
        "sources": {"v8_math_runs": [], "v9_science_runs": []},
        "split_policy": {"math_train_allowlist_path": str(fixtures_dir / "allowlist.json"), "science_use_dev_only": True},
        "toolchain_manifest_path": str(toolchain_path),
        "training_config_path": str(training_config_path),
        "eval_config_path": str(eval_config_path),
        "model_base_manifest_path": str(base_manifest_path),
        "thresholds": {
            "math_pass_min_num": 0,
            "math_pass_min_den": 1,
            "science_metric_min_num": 0,
            "science_metric_min_den": 1,
            "safety_regression_max_num": 1,
            "safety_regression_max_den": 1,
        },
    }
    write_canon_json(config_dir / "rsi_model_genesis_pack_v1.json", pack)

    # Corpus
    corpus_dir = state_dir / "corpus"
    shard_dir = corpus_dir / "shards"
    manifest_dir = corpus_dir / "manifest"
    index_dir = corpus_dir / "indexes"
    shard_dir.mkdir(parents=True, exist_ok=True)
    manifest_dir.mkdir(parents=True, exist_ok=True)
    index_dir.mkdir(parents=True, exist_ok=True)

    example = {
        "schema_version": "training_example_v1",
        "example_id": "",
        "example_type": "MATH_PROOF",
        "prompt": "example : 1 = 1 :=",
        "completion": "by rfl",
        "source": {
            "source_kind": "V8_MATH",
            "source_run_id": "fixture",
            "source_receipt_hash": "sha256:" + "7" * 64,
            "source_artifact_hashes": ["sha256:" + "8" * 64],
            "split": "TRAIN",
        },
    }
    example["example_id"] = sha256_prefixed(canon_bytes({k: v for k, v in example.items() if k != "example_id"}))

    shard_path = shard_dir / "training_examples_v1.jsonl"
    shard_path.write_text("", encoding="utf-8")
    write_jsonl_line(shard_path, example)
    shard_hash = sha256_prefixed(shard_path.read_bytes())

    manifest = {
        "schema_version": "training_corpus_manifest_v1",
        "corpus_id": "",
        "shards": [
            {"path": str(shard_path), "sha256": shard_hash, "num_examples": 1},
        ],
        "counts_by_type": {"MATH_PROOF": 1},
        "source_run_receipts": [example["source"]["source_receipt_hash"]],
        "split_policy": {"math_train_allowlist_path": "", "science_use_dev_only": True},
    }
    manifest["corpus_id"] = compute_corpus_id(manifest)
    manifest_hash = sha256_prefixed(canon_bytes(manifest))
    manifest_path = manifest_dir / f"sha256_{manifest_hash.split(':',1)[1]}.training_corpus_manifest_v1.json"
    write_canon_json(manifest_path, manifest)

    index = {
        "schema_version": "training_corpus_index_v1",
        "corpus_id": manifest["corpus_id"],
        "example_ids": [example["example_id"]],
    }
    index_hash = sha256_prefixed(canon_bytes(index))
    index_path = index_dir / f"sha256_{index_hash.split(':',1)[1]}.training_corpus_index_v1.json"
    write_canon_json(index_path, index)

    # Training receipt + weights
    weights_dir = state_dir / "training" / "outputs" / "weights"
    weights_dir.mkdir(parents=True, exist_ok=True)
    weights_bytes = b"weights"
    weights_hash = sha256_prefixed(weights_bytes)
    weights_path = weights_dir / f"sha256_{weights_hash.split(':',1)[1]}.weights.bin"
    weights_path.write_bytes(weights_bytes)

    toolchain_hash = sha256_prefixed(canon_bytes(toolchain))
    training_config_hash = sha256_prefixed(canon_bytes(training_config))
    receipt = {
        "schema_version": "sealed_training_receipt_v1",
        "toolchain_id": toolchain["toolchain_id"],
        "toolchain_manifest_hash": toolchain_hash,
        "training_config_hash": training_config_hash,
        "corpus_id": manifest["corpus_id"],
        "corpus_manifest_hash": manifest_hash,
        "result": "OK",
        "weights_hash": weights_hash,
        "stdout_hash": sha256_prefixed(b""),
        "stderr_hash": sha256_prefixed(b""),
        "time_ms": 1,
        "network_used": False,
    }
    receipt_hash = sha256_prefixed(canon_bytes(receipt))
    receipt_dir = state_dir / "training" / "sealed_receipts"
    receipt_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = receipt_dir / f"sha256_{receipt_hash.split(':',1)[1]}.sealed_training_receipt_v1.json"
    write_canon_json(receipt_path, receipt)

    # Ledger entries (boot + training)
    entry_boot = {
        "seq": 1,
        "tick": 0,
        "event_type": "SMG_BOOT",
        "event_payload": {},
        "prev_entry_hash": "GENESIS",
        "entry_hash": "",
    }
    entry_boot["entry_hash"] = compute_entry_hash(entry_boot)
    entry_train = {
        "seq": 2,
        "tick": 1,
        "event_type": "SMG_TRAINING_DONE",
        "event_payload": {"training_receipt_hash": receipt_hash},
        "prev_entry_hash": entry_boot["entry_hash"],
        "entry_hash": "",
    }
    entry_train["entry_hash"] = compute_entry_hash(entry_train)

    # Bundle
    bundle = {
        "schema_version": "model_weights_bundle_v1",
        "bundle_id": "",
        "base_model_id": base_manifest["base_model_id"],
        "weights_hash": weights_hash,
        "weights_path": str(weights_path),
        "training_receipt_hash": receipt_hash,
        "training_ledger_head_hash": entry_train["entry_hash"],
        "corpus_manifest_hash": manifest_hash,
        "toolchain_manifest_hash": toolchain_hash,
        "training_config_hash": training_config_hash,
        "created_utc": "2026-02-04T00:00:00Z",
    }
    bundle["bundle_id"] = compute_bundle_id(bundle)
    bundle_dir = state_dir / "training" / "outputs" / "bundles"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    bundle_path = bundle_dir / f"sha256_{bundle['bundle_id'].split(':',1)[1]}.model_weights_bundle_v1.json"
    write_canon_json(bundle_path, bundle)

    # Eval receipts
    eval_receipts_dir = state_dir / "eval" / "sealed_receipts"
    eval_receipts_dir.mkdir(parents=True, exist_ok=True)
    sealed_receipts = []
    for suite in eval_config["suites"]:
        rec = {
            "schema_version": "sealed_model_eval_receipt_v1",
            "eval_suite_id": suite["suite_id"],
            "bundle_id": bundle["bundle_id"],
            "weights_hash": weights_hash,
            "result": "OK",
            "metric_num": 1,
            "metric_den": 1,
            "stdout_hash": sha256_prefixed(b""),
            "stderr_hash": sha256_prefixed(b""),
            "time_ms": 1,
            "network_used": False,
        }
        rec_hash = sha256_prefixed(canon_bytes(rec))
        rec_path = eval_receipts_dir / f"sha256_{rec_hash.split(':',1)[1]}.sealed_model_eval_receipt_v1.json"
        write_canon_json(rec_path, rec)
        sealed_receipts.append(rec)

    # Model eval receipt
    eval_receipt = {
        "schema_version": "model_eval_receipt_v1",
        "bundle_id": bundle["bundle_id"],
        "math_metric": {"num": 1, "den": 1},
        "science_metric": {"num": 1, "den": 1},
        "safety_metric": {"num": 1, "den": 1},
        "meets_thresholds": True,
        "sealed_eval_receipt_hashes": [sha256_prefixed(canon_bytes(rec)) for rec in sealed_receipts],
    }
    eval_receipt_hash = sha256_prefixed(canon_bytes(eval_receipt))
    eval_out_dir = state_dir / "eval" / "model_eval_receipts"
    eval_out_dir.mkdir(parents=True, exist_ok=True)
    eval_out_path = eval_out_dir / f"sha256_{eval_receipt_hash.split(':',1)[1]}.model_eval_receipt_v1.json"
    write_canon_json(eval_out_path, eval_receipt)

    # Promotion bundle
    promo_dir = state_dir / "promotion"
    promo_dir.mkdir(parents=True, exist_ok=True)
    promo = {
        "schema_version": "model_promotion_bundle_v1",
        "bundle_id": bundle["bundle_id"],
        "icore_id": icore_id,
        "meta_hash": meta_hash,
        "superego_policy_hash": policy_hash,
        "training_receipt_hash": receipt_hash,
        "eval_receipt_hash": eval_receipt_hash,
        "activation_target": str(config_dir / "model_base_manifest_v1.json"),
        "two_phase": {
            "stage_hash": "sha256:" + "9" * 64,
            "activate_hash": "sha256:" + "a" * 64,
            "rollback_hash": "sha256:" + "b" * 64,
        },
    }
    promo_hash = sha256_prefixed(canon_bytes(promo))
    promo_path = promo_dir / f"sha256_{promo_hash.split(':',1)[1]}.model_promotion_bundle_v1.json"
    write_canon_json(promo_path, promo)

    # Ledger
    ledger_path = ledger_dir / "model_genesis_ledger_v1.jsonl"
    ledger_path.write_text("", encoding="utf-8")
    write_jsonl_line(ledger_path, entry_boot)
    write_jsonl_line(ledger_path, entry_train)

    ignition = {
        "schema_version": "model_genesis_ignition_receipt_v1",
        "icore_id": icore_id,
        "meta_hash": meta_hash,
        "superego_policy_hash": policy_hash,
        "ledger_head_hash": entry_train["entry_hash"],
        "created_utc": "2026-02-04T00:00:00Z",
    }
    write_canon_json(ledger_dir / "model_genesis_ignition_receipt_v1.json", ignition)

    return {
        "smg_root": smg_root,
        "state_dir": state_dir,
        "pack_path": config_dir / "rsi_model_genesis_pack_v1.json",
        "training_config_path": training_config_path,
        "corpus_shard_path": shard_path,
        "training_receipt_path": receipt_path,
    }
