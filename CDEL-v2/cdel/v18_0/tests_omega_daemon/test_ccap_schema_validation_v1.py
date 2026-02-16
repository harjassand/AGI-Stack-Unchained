from __future__ import annotations

from cdel.v18_0.omega_common_v1 import validate_schema


def _h(ch: str) -> str:
    return "sha256:" + (ch * 64)


def test_ccap_related_schemas_validate_minimal_payloads() -> None:
    actionseq = {
        "schema_version": "actionseq_v1",
        "seq_id": _h("1"),
        "steps": [
            {
                "op_id": "OP_RENAME_LOCAL",
                "site": "tools/omega/sample.py::fn",
                "args": {"from_name": "a", "to_name": "b"},
            }
        ],
    }
    validate_schema(actionseq, "actionseq_v1")

    operator_pool = {
        "schema_version": "operator_pool_v1",
        "op_pool_id": _h("2"),
        "pool_version_u32": 1,
        "operators": [
            {
                "op_id": "OP_RENAME_LOCAL",
                "kind": "ACTIONSEQ",
                "enabled": True,
                "pattern": {"site": "<module>::<fn>"},
                "rewrite": {"kind": "python_ast_rename_local"},
                "type_rules": {"site_scope": "function_local"},
                "obligation_bundle": {
                    "requires": [],
                    "generates": [],
                    "discharges": [],
                },
            }
        ],
    }
    validate_schema(operator_pool, "operator_pool_v1")

    evaluation_kernel = {
        "schema_version": "evaluation_kernel_v1",
        "ek_version": 1,
        "obs_schema_ids": ["https://genesis.engine/specs/v18_0/omega_observation_report_v1"],
        "obs_canon_id": _h("3"),
        "boundary_event_set_id": _h("4"),
        "stages": [
            {"stage_name": "REALIZE"},
            {"stage_name": "SCORE"},
            {"stage_name": "FINAL_AUDIT"},
        ],
        "scoring_impl": {
            "kind": "OMEGA_BENCHMARK_SUITE",
            "code_ref": {
                "commit_hash": "abcdef0",
                "path": "tools/omega/omega_benchmark_suite_v1.py",
            },
            "applicability_preds_id": _h("5"),
            "ek_meta_tests_id": _h("6"),
        },
    }
    validate_schema(evaluation_kernel, "evaluation_kernel_v1")

    ccap = {
        "meta": {
            "ccap_version": 1,
            "base_tree_id": _h("7"),
            "auth_hash": _h("8"),
            "dsbx_profile_id": _h("9"),
            "env_contract_id": _h("a"),
            "toolchain_root_id": _h("b"),
            "ek_id": _h("c"),
            "op_pool_id": _h("d"),
            "canon_version_ids": {
                "ccap_can_v": _h("e"),
                "ir_can_v": _h("f"),
                "op_can_v": _h("0"),
                "obs_can_v": _h("1"),
            },
        },
        "payload": {
            "kind": "ACTIONSEQ",
            "action_seq": actionseq,
        },
        "build": {
            "build_recipe_id": _h("2"),
            "build_targets": [],
            "artifact_bindings": {},
        },
        "eval": {
            "stages": [
                {"stage_name": "REALIZE"},
                {"stage_name": "SCORE"},
                {"stage_name": "FINAL_AUDIT"},
            ],
            "final_suite_id": _h("3"),
        },
        "budgets": {
            "cpu_ms_max": 1,
            "wall_ms_max": 1,
            "mem_mb_max": 1,
            "disk_mb_max": 1,
            "fds_max": 1,
            "procs_max": 1,
            "threads_max": 1,
            "net": "forbidden",
        },
    }
    validate_schema(ccap, "ccap_v1")

    ccap_receipt = {
        "schema_version": "ccap_receipt_v1",
        "ccap_id": _h("4"),
        "base_tree_id": _h("5"),
        "applied_tree_id": _h("6"),
        "realized_out_id": _h("7"),
        "ek_id": _h("8"),
        "op_pool_id": _h("9"),
        "auth_hash": _h("a"),
        "determinism_check": "PASS",
        "eval_status": "PASS",
        "decision": "PROMOTE",
        "cost_vector": {
            "cpu_ms": 1,
            "wall_ms": 1,
            "mem_mb": 1,
            "disk_mb": 1,
            "fds": 1,
            "procs": 1,
            "threads": 1,
        },
        "logs_hash": _h("b"),
    }
    validate_schema(ccap_receipt, "ccap_receipt_v1")

    realized_receipt = {
        "schema_version": "realized_capsule_receipt_v1",
        "realized_receipt_id": _h("c"),
        "ccap_id": _h("4"),
        "base_tree_id": _h("5"),
        "applied_tree_id": _h("6"),
        "realized_out_id": _h("7"),
        "ek_id": _h("8"),
        "op_pool_id": _h("9"),
        "auth_hash": _h("a"),
        "determinism_check": "PASS",
        "eval_status": "PASS",
        "cost_vector": {
            "cpu_ms": 1,
            "wall_ms": 1,
            "mem_mb": 1,
            "disk_mb": 1,
            "fds": 1,
            "procs": 1,
            "threads": 1,
        },
        "logs_hash": _h("d"),
    }
    validate_schema(realized_receipt, "realized_capsule_receipt_v1")

    refutation = {
        "schema_version": "ccap_refutation_cert_v1",
        "ccap_id": _h("e"),
        "refutation_code": "NONDETERMINISM_DETECTED",
        "detail": "double run diverged",
        "evidence_hashes": [_h("f")],
    }
    validate_schema(refutation, "ccap_refutation_cert_v1")

    authority_state = {
        "schema_version": "authority_state_v1",
        "authority_state_id": _h("0"),
        "auth_hash": _h("1"),
        "re1_constitution_state_id": _h("2"),
        "re2_verifier_state_id": _h("3"),
        "active_ek_id": _h("4"),
        "active_op_pool_ids": [_h("5")],
        "active_dsbx_profile_ids": [_h("6")],
        "env_contract_id": _h("7"),
        "toolchain_root_id": _h("8"),
        "ccap_patch_allowlists_id": _h("e"),
        "canon_version_ids": {
            "ccap_can_v": _h("9"),
            "ir_can_v": _h("a"),
            "op_can_v": _h("b"),
            "obs_can_v": _h("c"),
        },
    }
    validate_schema(authority_state, "authority_state_v1")

    promotion_bundle = {
        "schema_version": "omega_promotion_bundle_ccap_v1",
        "ccap_id": _h("d"),
        "ccap_relpath": "ccap/sha256_" + ("d" * 64) + ".ccap_v1.json",
        "patch_relpath": "ccap/blobs/sha256_" + ("e" * 64) + ".patch",
        "touched_paths": [
            "ccap/sha256_" + ("d" * 64) + ".ccap_v1.json",
            "ccap/blobs/sha256_" + ("e" * 64) + ".patch",
        ],
        "activation_key": "ccap_activation_key_v1",
    }
    validate_schema(promotion_bundle, "omega_promotion_bundle_ccap_v1")
