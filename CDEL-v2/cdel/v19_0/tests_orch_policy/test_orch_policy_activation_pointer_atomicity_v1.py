from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "CDEL-v2") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "CDEL-v2"))

from cdel.v1_7r.canon import canon_bytes, load_canon_json, sha256_prefixed, write_canon_json
from cdel.v18_0.omega_activator_v1 import run_activation


def _sha_obj(payload: dict) -> str:
    return sha256_prefixed(canon_bytes(payload))


def _build_policy_bundle(context_key: str, capability_id: str, score_q32: int) -> tuple[dict, str, str]:
    table_payload = {
        "schema_version": "orch_policy_table_v1",
        "policy_table_id": "sha256:" + ("0" * 64),
        "rows": [
            {
                "context_key": str(context_key),
                "ranked_capabilities": [{"capability_id": str(capability_id), "score_q32": int(score_q32)}],
            }
        ],
    }
    table_payload["policy_table_id"] = _sha_obj(
        {
            "schema_version": str(table_payload["schema_version"]),
            "rows": list(table_payload["rows"]),
        }
    )
    table_id = str(table_payload["policy_table_id"])

    bundle_payload = {
        "schema_version": "orch_policy_bundle_v1",
        "policy_bundle_id": "sha256:" + ("0" * 64),
        "policy_table_id": table_id,
        "policy_table": dict(table_payload),
    }
    bundle_payload["policy_bundle_id"] = _sha_obj(
        {
            "schema_version": str(bundle_payload["schema_version"]),
            "policy_table_id": str(bundle_payload["policy_table_id"]),
            "policy_table": dict(bundle_payload["policy_table"]),
        }
    )
    bundle_id = str(bundle_payload["policy_bundle_id"])
    return bundle_payload, bundle_id, table_id


def _write_bundle_artifact(dispatch_dir: Path, *, context_key: str, capability_id: str, score_q32: int) -> tuple[str, str]:
    bundle_payload, bundle_id, table_id = _build_policy_bundle(
        context_key=context_key,
        capability_id=capability_id,
        score_q32=score_q32,
    )
    promotion_dir = dispatch_dir / "promotion"
    promotion_dir.mkdir(parents=True, exist_ok=True)
    bundle_path = promotion_dir / f"sha256_{bundle_id.split(':', 1)[1]}.orch_policy_bundle_v1.json"
    write_canon_json(bundle_path, bundle_payload)
    return bundle_id, table_id


def _promotion_receipt(policy_bundle_id: str) -> dict:
    return {
        "result": {"status": "PROMOTED"},
        "result_kind": "PROMOTED_POLICY_UPDATE",
        "promotion_bundle_hash": str(policy_bundle_id),
        "activation_binding_kind": "ACTIVATION_KIND_ORCH_POLICY_UPDATE",
    }


def test_orch_policy_activation_pointer_atomicity_v1(tmp_path: Path) -> None:
    state_root = tmp_path / "daemon" / "rsi_omega_daemon_v19_0" / "state"
    state_root.mkdir(parents=True, exist_ok=True)

    dispatch_dir_1 = state_root / "dispatch" / "tick_0001"
    dispatch_dir_1.mkdir(parents=True, exist_ok=True)
    bundle_id_1, table_id_1 = _write_bundle_artifact(
        dispatch_dir_1,
        context_key="sha256:" + ("1" * 64),
        capability_id="cap_a",
        score_q32=1,
    )

    activation_receipt_1, _activation_hash_1, _rollback_1, _rollback_hash_1, _before_hash_1 = run_activation(
        tick_u64=1,
        dispatch_ctx={"dispatch_dir": str(dispatch_dir_1)},
        promotion_receipt=_promotion_receipt(bundle_id_1),
        healthcheck_suitepack={"checks": []},
        healthcheck_suite_hash="sha256:" + ("a" * 64),
        active_manifest_hash_before="sha256:" + ("b" * 64),
    )
    assert isinstance(activation_receipt_1, dict)
    assert bool(activation_receipt_1.get("activation_success", False))

    orch_root = state_root.parents[1] / "orch_policy"
    pointer_path = orch_root / "active" / "ORCH_POLICY_V1.json"
    pointer_payload_1 = load_canon_json(pointer_path)
    assert str(pointer_payload_1.get("active_policy_bundle_id", "")) == bundle_id_1
    assert int(pointer_payload_1.get("updated_tick_u64", -1)) == 1

    dispatch_dir_2 = state_root / "dispatch" / "tick_0002"
    dispatch_dir_2.mkdir(parents=True, exist_ok=True)
    bundle_id_2, table_id_2 = _write_bundle_artifact(
        dispatch_dir_2,
        context_key="sha256:" + ("2" * 64),
        capability_id="cap_b",
        score_q32=2,
    )

    activation_receipt_2, _activation_hash_2, _rollback_2, _rollback_hash_2, _before_hash_2 = run_activation(
        tick_u64=2,
        dispatch_ctx={"dispatch_dir": str(dispatch_dir_2)},
        promotion_receipt=_promotion_receipt(bundle_id_2),
        healthcheck_suitepack={"checks": []},
        healthcheck_suite_hash="sha256:" + ("a" * 64),
        active_manifest_hash_before="sha256:" + ("c" * 64),
    )
    assert isinstance(activation_receipt_2, dict)
    assert bool(activation_receipt_2.get("activation_success", False))

    pointer_payload_2 = load_canon_json(pointer_path)
    assert str(pointer_payload_2.get("active_policy_bundle_id", "")) == bundle_id_2
    assert int(pointer_payload_2.get("updated_tick_u64", -1)) == 2

    store_dir = orch_root / "store"
    assert (store_dir / f"sha256_{bundle_id_1.split(':', 1)[1]}.orch_policy_bundle_v1.json").exists()
    assert (store_dir / f"sha256_{bundle_id_2.split(':', 1)[1]}.orch_policy_bundle_v1.json").exists()
    assert (store_dir / f"sha256_{table_id_1.split(':', 1)[1]}.orch_policy_table_v1.json").exists()
    assert (store_dir / f"sha256_{table_id_2.split(':', 1)[1]}.orch_policy_table_v1.json").exists()

    tmp_files = list(orch_root.rglob("*.tmp"))
    assert not tmp_files
