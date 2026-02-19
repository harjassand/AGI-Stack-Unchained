from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from cdel.v1_7r.canon import write_canon_json
from cdel.v18_0 import campaign_polymath_bootstrap_domain_v1 as bootstrap_campaign
from cdel.v18_0 import campaign_polymath_sip_ingestion_l0_v1 as sip_campaign
from cdel.v18_0 import verify_rsi_polymath_domain_v1 as domain_verifier
from cdel.v18_0 import verify_rsi_polymath_sip_ingestion_l0_v1 as sip_verifier
from cdel.v18_0.omega_common_v1 import canon_hash_obj, repo_root
from cdel.v18_0.polymath_sip_ingestion_l0_v1 import canonicalize_jsonl_bytes_from_inputs
from orchestrator.omega_v19_0 import coordinator_v1 as coordinator_v19


def _sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _sid(label: str) -> str:
    return _sha(label.encode("utf-8"))


def _sip_pack(*, dataset_name: str, input_relpath: str, input_content_id: str, max_entropy_q16: int = 524288) -> dict[str, Any]:
    return {
        "schema_version": "rsi_polymath_sip_ingestion_l0_pack_v1",
        "dataset_name": dataset_name,
        "inputs_relpaths": [input_relpath],
        "input_content_ids": {input_relpath: input_content_id},
        "sip_profile": {
            "sip_profile_id": _sid(f"sip-profile::{dataset_name}"),
            "canonicalization_profile_ids": [_sid("canon-jsonl-v1")],
            "leakage_policy": {
                "forbidden_patterns": [],
                "max_entropy_q16": int(max_entropy_q16),
                "on_detect": "REJECT",
            },
        },
        "sip_budget_spec": {
            "schema_name": "budget_spec_v1",
            "schema_version": "v19_0",
            "max_steps": 200_000,
            "max_bytes_read": 2_000_000,
            "max_bytes_write": 2_000_000,
            "max_items": 200_000,
            "seed": 19,
            "policy": "SAFE_HALT",
        },
        "canonical_jsonl_policy": "CANON_JSONL_DETERMINISTIC_V1",
    }


def _write_sip_input(*, repo: Path, relpath: str, blob: bytes) -> str:
    path = repo / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(blob)
    return _sha(blob)


def _run_sip_campaign(
    *,
    monkeypatch,
    tmp_path: Path,
    dataset_blob: bytes,
    input_content_id_override: str | None = None,
    tick_u64: int = 7,
    max_entropy_q16: int = 524288,
) -> tuple[Path, Path, dict[str, Any]]:
    repo = tmp_path / "repo"
    out_dir = tmp_path / "out"
    pack_path = tmp_path / "sip_pack.json"

    input_rel = "datasets/physics_l0/fixture.jsonl"
    input_content_id = _write_sip_input(repo=repo, relpath=input_rel, blob=dataset_blob)
    pinned_id = input_content_id_override or input_content_id
    pack = _sip_pack(
        dataset_name="physics_fixture_v1",
        input_relpath=input_rel,
        input_content_id=pinned_id,
        max_entropy_q16=max_entropy_q16,
    )
    write_canon_json(pack_path, pack)

    monkeypatch.setenv("OMEGA_TICK_U64", str(int(tick_u64)))
    monkeypatch.setattr(sip_campaign, "repo_root", lambda: repo)
    sip_campaign.run(campaign_pack=pack_path, out_dir=out_dir)

    state_root = out_dir / "daemon" / "rsi_polymath_sip_ingestion_l0_v1" / "state"
    ingestion_root = state_root / "polymath" / "ingestion"
    return state_root, ingestion_root, pack


def _glob_one(base: Path, pattern: str) -> Path:
    rows = sorted(base.glob(pattern), key=lambda p: p.as_posix())
    assert len(rows) == 1
    return rows[0]


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_canonical_jsonl_is_deterministic_across_file_and_line_order() -> None:
    inputs_a = {
        "a.jsonl": b'{"b":2,"a":1}\n\n{"z":0}\n',
        "b.jsonl": b'{"k":[2,1]}\n',
    }
    inputs_b = {
        "b.jsonl": b'{"k":[2,1]}\r\n',
        "a.jsonl": b'{"z":0}\r\n{"a":1,"b":2}\r\n',
    }

    canon_a, count_a = canonicalize_jsonl_bytes_from_inputs(input_bytes_by_relpath=inputs_a)
    canon_b, count_b = canonicalize_jsonl_bytes_from_inputs(input_bytes_by_relpath=inputs_b)

    assert canon_a == canon_b
    assert count_a == count_b == 3
    assert _sha(canon_a) == _sha(canon_b)


def test_sip_campaign_success_and_verifier_valid(monkeypatch, tmp_path: Path) -> None:
    state_root, ingestion_root, _ = _run_sip_campaign(
        monkeypatch=monkeypatch,
        tmp_path=tmp_path,
        dataset_blob=b'{"topic":"physics","value":1}\n{"topic":"math","value":2}\n',
    )

    knowledge_path = _glob_one(ingestion_root / "knowledge", "sha256_*.sip_knowledge_artifact_v1.json")
    manifest_path = _glob_one(ingestion_root / "manifests", "sha256_*.world_snapshot_manifest_v1.json")
    receipt_path = _glob_one(ingestion_root / "receipts", "sha256_*.sealed_ingestion_receipt_v1.json")

    knowledge = _json(knowledge_path)
    receipt = _json(receipt_path)

    assert knowledge["schema_version"] == "sip_knowledge_artifact_v1"
    assert receipt["outcome"] == "ACCEPT"
    assert receipt["reason_code"] == "GATES_PASS"
    assert sip_verifier.verify(state_root, mode="full") == "VALID"

    manifest_id = _sha((manifest_path.read_text(encoding="utf-8").rstrip("\n")).encode("utf-8"))
    assert manifest_id.startswith("sha256:")


def test_sip_campaign_replay_deterministic_ids(monkeypatch, tmp_path: Path) -> None:
    blob = b'{"x":1}\n{"y":2}\n'
    state_root_a, ingestion_root_a, _ = _run_sip_campaign(
        monkeypatch=monkeypatch,
        tmp_path=tmp_path / "run_a",
        dataset_blob=blob,
        tick_u64=9,
    )
    state_root_b, ingestion_root_b, _ = _run_sip_campaign(
        monkeypatch=monkeypatch,
        tmp_path=tmp_path / "run_b",
        dataset_blob=blob,
        tick_u64=9,
    )

    knowledge_path_a = _glob_one(ingestion_root_a / "knowledge", "sha256_*.sip_knowledge_artifact_v1.json")
    knowledge_path_b = _glob_one(ingestion_root_b / "knowledge", "sha256_*.sip_knowledge_artifact_v1.json")
    knowledge_a = _json(knowledge_path_a)
    knowledge_b = _json(knowledge_path_b)

    assert knowledge_a["canonical_jsonl_content_id"] == knowledge_b["canonical_jsonl_content_id"]
    assert knowledge_a["producer_run_id"] == knowledge_b["producer_run_id"]
    assert canon_hash_obj(knowledge_a) == canon_hash_obj(knowledge_b)
    assert sip_verifier.verify(state_root_a, mode="full") == "VALID"
    assert sip_verifier.verify(state_root_b, mode="full") == "VALID"


def test_sip_campaign_pin_mismatch_refutation(monkeypatch, tmp_path: Path) -> None:
    state_root, ingestion_root, _ = _run_sip_campaign(
        monkeypatch=monkeypatch,
        tmp_path=tmp_path,
        dataset_blob=b'{"ok":1}\n',
        input_content_id_override=_sid("wrong-pin"),
    )

    ref_path = _glob_one(ingestion_root / "refutations", "sha256_*.sip_knowledge_refutation_v1.json")
    ref = _json(ref_path)
    assert ref["reason_code"] == "INPUT_HASH_MISMATCH"
    assert ref["sip_manifest_id"] is None
    assert ref["sip_seal_receipt_id"] is None
    assert not list((ingestion_root / "receipts").glob("sha256_*.sealed_ingestion_receipt_v1.json"))
    assert sip_verifier.verify(state_root, mode="full") == "VALID"


def test_sip_campaign_parse_fail_refutation(monkeypatch, tmp_path: Path) -> None:
    bad_utf8 = b"\xff\xfe\n"
    state_root, ingestion_root, _ = _run_sip_campaign(
        monkeypatch=monkeypatch,
        tmp_path=tmp_path,
        dataset_blob=bad_utf8,
    )

    ref_path = _glob_one(ingestion_root / "refutations", "sha256_*.sip_knowledge_refutation_v1.json")
    ref = _json(ref_path)
    assert ref["reason_code"] == "CANON_JSONL_PARSE_FAIL"
    assert ref["sip_manifest_id"] is None
    assert ref["sip_seal_receipt_id"] is None
    assert not list((ingestion_root / "receipts").glob("sha256_*.sealed_ingestion_receipt_v1.json"))
    assert sip_verifier.verify(state_root, mode="full") == "VALID"


def test_sip_campaign_entropy_rejection_refutation(monkeypatch, tmp_path: Path) -> None:
    noise = "".join(chr(i) for i in range(32, 127))
    blob = (json.dumps({"payload": noise * 8}, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    state_root, ingestion_root, _ = _run_sip_campaign(
        monkeypatch=monkeypatch,
        tmp_path=tmp_path,
        dataset_blob=blob,
        max_entropy_q16=1024,
    )

    ref_path = _glob_one(ingestion_root / "refutations", "sha256_*.sip_knowledge_refutation_v1.json")
    receipt_path = _glob_one(ingestion_root / "receipts", "sha256_*.sealed_ingestion_receipt_v1.json")
    ref = _json(ref_path)
    receipt = _json(receipt_path)

    assert ref["reason_code"] == "SIP_REJECTED"
    assert receipt["outcome"] == "REJECT"
    assert receipt["reason_code"] == "LEAKAGE_DETECTED"
    assert sip_verifier.verify(state_root, mode="full") == "VALID"


def test_bootstrap_optional_sip_refutation_blocks_cleanly(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    out_dir = tmp_path / "out"
    pack_path = tmp_path / "bootstrap_pack.json"

    input_rel = "datasets/bootstrap_sip/fixture.jsonl"
    _ = _write_sip_input(repo=repo, relpath=input_rel, blob=b'{"ok":1}\n')
    sip_cfg = _sip_pack(
        dataset_name="bootstrap_sip_fixture_v1",
        input_relpath=input_rel,
        input_content_id=_sid("intentionally-wrong"),
    )

    write_canon_json(
        pack_path,
        {
            "schema_version": "rsi_polymath_bootstrap_domain_pack_v1",
            "sip_ingestion_l0": sip_cfg,
        },
    )

    monkeypatch.setenv("OMEGA_TICK_U64", "11")
    monkeypatch.setattr(bootstrap_campaign, "repo_root", lambda: repo)
    bootstrap_campaign.run(campaign_pack=pack_path, out_dir=out_dir)

    state_root = out_dir / "daemon" / "rsi_polymath_bootstrap_domain_v1" / "state"
    report = _json(state_root / "reports" / "polymath_bootstrap_report_v1.json")
    assert report["status"] == "BLOCKED_SIP_INGESTION"
    assert isinstance(report.get("sip_knowledge_refutation_rel"), str)
    assert domain_verifier.verify(state_root, mode="full") == "VALID"


def test_v19_tick_binds_sip_ingestion_to_ledger_and_trace(monkeypatch, tmp_path: Path) -> None:
    pack_path = repo_root() / "campaigns" / "rsi_omega_daemon_v19_0_phase4a_sip_ingestion" / "rsi_omega_daemon_pack_v1.json"
    out_dir = tmp_path / "phase4a_tick"

    monkeypatch.setenv("OMEGA_META_CORE_ACTIVATION_MODE", "simulate")
    monkeypatch.setenv("OMEGA_ALLOW_SIMULATE_ACTIVATION", "1")
    monkeypatch.setenv("OMEGA_DISABLE_FORCED_RUNAWAY", "1")

    _ = coordinator_v19.run_tick(
        campaign_pack=pack_path,
        out_dir=out_dir,
        tick_u64=1,
        prev_state_dir=None,
    )

    state_root = out_dir / "daemon" / "rsi_omega_daemon_v19_0" / "state"
    ledger_path = state_root / "ledger" / "omega_ledger_v1.jsonl"
    ledger_rows = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    sip_rows = [row for row in ledger_rows if str(row.get("event_type", "")) == "SIP_INGESTION_L0"]
    assert len(sip_rows) == 1
    artifact_hash = str(sip_rows[0]["artifact_hash"])

    trace_path = _glob_one(state_root / "ledger", "sha256_*.omega_trace_hash_chain_v1.json")
    trace = _json(trace_path)
    assert artifact_hash in [str(row) for row in trace.get("artifact_hashes", [])]

    digest = artifact_hash.split(":", 1)[1]
    imported_path = state_root / "polymath" / "ingestion" / "knowledge" / f"sha256_{digest}.sip_knowledge_artifact_v1.json"
    assert imported_path.exists() and imported_path.is_file()
