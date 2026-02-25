from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "CDEL-v2") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "CDEL-v2"))

import cdel.v19_0.verify_orch_policy_bundle_v1 as eval_module

from cdel.v1_7r.canon import canon_bytes, sha256_prefixed, write_canon_json

Q32_ONE = 1 << 32


def _sha_obj(payload: dict) -> str:
    return sha256_prefixed(canon_bytes(payload))


def _build_policy_bundle(rows_by_context: dict[str, list[tuple[str, int]]]) -> tuple[dict, str]:
    table_rows = []
    for context_key, ranked in sorted(rows_by_context.items(), key=lambda row: row[0]):
        table_rows.append(
            {
                "context_key": str(context_key),
                "ranked_capabilities": [
                    {"capability_id": str(capability_id), "score_q32": int(score_q32)}
                    for capability_id, score_q32 in ranked
                ],
            }
        )
    table_payload = {
        "schema_version": "orch_policy_table_v1",
        "policy_table_id": "sha256:" + ("0" * 64),
        "rows": table_rows,
    }
    table_payload["policy_table_id"] = _sha_obj(
        {
            "schema_version": str(table_payload["schema_version"]),
            "rows": list(table_payload["rows"]),
        }
    )
    bundle_payload = {
        "schema_version": "orch_policy_bundle_v1",
        "policy_bundle_id": "sha256:" + ("0" * 64),
        "policy_table_id": str(table_payload["policy_table_id"]),
        "policy_table": dict(table_payload),
    }
    bundle_payload["policy_bundle_id"] = _sha_obj(
        {
            "schema_version": str(bundle_payload["schema_version"]),
            "policy_table_id": str(bundle_payload["policy_table_id"]),
            "policy_table": dict(bundle_payload["policy_table"]),
        }
    )
    return bundle_payload, str(bundle_payload["policy_bundle_id"])


def _holdout_row(
    *,
    context_key: str,
    action_capability_id: str,
    reward_q32: int,
    toxic_fail_b: bool,
) -> dict:
    return {
        "context_key": str(context_key),
        "action_capability_id": str(action_capability_id),
        "reward_q32": int(reward_q32),
        "toxic_fail_b": bool(toxic_fail_b),
        "eligible_capability_ids": ["cap_a", "cap_b"],
    }


def _baseline_lookup_from_rows(rows: dict[str, str]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for context_key, capability_id in sorted(rows.items(), key=lambda row: row[0]):
        out[context_key] = [{"capability_id": str(capability_id), "score_q32": 0}]
    return out


def _state_and_dispatch(tmp_path: Path) -> tuple[Path, Path]:
    state_root = tmp_path / "daemon" / "rsi_omega_daemon_v19_0" / "state"
    config_dir = state_root.parent / "config"
    dispatch_dir = state_root / "dispatch" / "tick_0001"
    config_dir.mkdir(parents=True, exist_ok=True)
    dispatch_dir.mkdir(parents=True, exist_ok=True)
    return state_root, dispatch_dir


def _run_eval(
    *,
    tmp_path: Path,
    monkeypatch,
    candidate_rows: dict[str, list[tuple[str, int]]],
    baseline_rows: dict[str, str],
    holdout_rows: list[dict],
    eval_cfg: dict,
) -> dict:
    state_root, dispatch_dir = _state_and_dispatch(tmp_path)
    bundle_payload, _bundle_id = _build_policy_bundle(candidate_rows)
    candidate_path = dispatch_dir / "candidate.orch_policy_bundle_v1.json"
    write_canon_json(candidate_path, bundle_payload)

    def _fake_load_and_pin_eval_config(*, config_dir: Path, state_root: Path) -> tuple[dict, list[dict]]:
        del config_dir
        del state_root
        return dict(eval_cfg), [dict(row) for row in holdout_rows]

    def _fake_load_active_policy_lookup(*, state_root: Path) -> tuple[str, dict[str, list[dict]]]:
        del state_root
        return "sha256:" + ("f" * 64), _baseline_lookup_from_rows(baseline_rows)

    monkeypatch.setattr(eval_module, "_load_and_pin_eval_config", _fake_load_and_pin_eval_config)
    monkeypatch.setattr(eval_module, "_load_active_policy_lookup", _fake_load_active_policy_lookup)

    receipt, _receipt_id = eval_module.verify_orch_policy_bundle_v1(
        tick_u64=1,
        dispatch_ctx={
            "state_root": str(state_root),
            "dispatch_dir": str(dispatch_dir),
        },
        candidate_bundle_path=candidate_path,
    )
    return dict(receipt)


def test_orch_policy_eval_gate_low_coverage_v1(tmp_path: Path, monkeypatch) -> None:
    context_1 = "sha256:" + ("1" * 64)
    context_2 = "sha256:" + ("2" * 64)
    holdout_rows = [
        _holdout_row(context_key=context_1, action_capability_id="cap_a", reward_q32=Q32_ONE, toxic_fail_b=False),
        _holdout_row(context_key=context_2, action_capability_id="cap_b", reward_q32=Q32_ONE, toxic_fail_b=False),
    ]
    receipt = _run_eval(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        candidate_rows={context_1: [("cap_a", 1)]},
        baseline_rows={context_1: "cap_a", context_2: "cap_b"},
        holdout_rows=holdout_rows,
        eval_cfg={
            "schema_version": "orch_policy_eval_config_v1",
            "holdout_dataset_id": "sha256:" + ("a" * 64),
            "min_delta_q32": -Q32_ONE,
            "min_coverage_q32": (Q32_ONE * 3) // 4,
            "max_toxic_increase_q32": Q32_ONE,
            "baseline_kind": "ACTIVE_POLICY",
        },
    )
    assert str(receipt["status"]) == "FAIL"
    assert str(receipt["reason_code"]) == "EVAL_FAIL:LOW_COVERAGE"
    assert int(((receipt.get("metrics") or {}).get("coverage_q32", -1))) == (Q32_ONE // 2)


def test_orch_policy_eval_gate_no_improvement_v1(tmp_path: Path, monkeypatch) -> None:
    context_1 = "sha256:" + ("1" * 64)
    context_2 = "sha256:" + ("2" * 64)
    holdout_rows = [
        _holdout_row(context_key=context_1, action_capability_id="cap_a", reward_q32=Q32_ONE, toxic_fail_b=False),
        _holdout_row(context_key=context_2, action_capability_id="cap_b", reward_q32=Q32_ONE, toxic_fail_b=False),
    ]
    candidate_rows = {
        context_1: [("cap_a", 1)],
        context_2: [("cap_b", 1)],
    }
    receipt = _run_eval(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        candidate_rows=candidate_rows,
        baseline_rows={context_1: "cap_a", context_2: "cap_b"},
        holdout_rows=holdout_rows,
        eval_cfg={
            "schema_version": "orch_policy_eval_config_v1",
            "holdout_dataset_id": "sha256:" + ("a" * 64),
            "min_delta_q32": 1,
            "min_coverage_q32": Q32_ONE,
            "max_toxic_increase_q32": Q32_ONE,
            "baseline_kind": "ACTIVE_POLICY",
        },
    )
    assert str(receipt["status"]) == "FAIL"
    assert str(receipt["reason_code"]) == "EVAL_FAIL:NO_IMPROVEMENT"


def test_orch_policy_eval_gate_toxic_increase_v1(tmp_path: Path, monkeypatch) -> None:
    context_1 = "sha256:" + ("1" * 64)
    context_2 = "sha256:" + ("2" * 64)
    holdout_rows = [
        _holdout_row(context_key=context_1, action_capability_id="cap_a", reward_q32=Q32_ONE, toxic_fail_b=True),
        _holdout_row(context_key=context_2, action_capability_id="cap_b", reward_q32=Q32_ONE, toxic_fail_b=False),
    ]
    candidate_rows = {
        context_1: [("cap_a", 1)],
        context_2: [("cap_b", 1)],
    }
    receipt = _run_eval(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        candidate_rows=candidate_rows,
        baseline_rows={context_1: "cap_b", context_2: "cap_b"},
        holdout_rows=holdout_rows,
        eval_cfg={
            "schema_version": "orch_policy_eval_config_v1",
            "holdout_dataset_id": "sha256:" + ("a" * 64),
            "min_delta_q32": 1,
            "min_coverage_q32": Q32_ONE,
            "max_toxic_increase_q32": 0,
            "baseline_kind": "ACTIVE_POLICY",
        },
    )
    assert str(receipt["status"]) == "FAIL"
    assert str(receipt["reason_code"]) == "EVAL_FAIL:TOXIC_INCREASE"


def test_orch_policy_eval_gate_pass_v1(tmp_path: Path, monkeypatch) -> None:
    context_1 = "sha256:" + ("1" * 64)
    context_2 = "sha256:" + ("2" * 64)
    holdout_rows = [
        _holdout_row(context_key=context_1, action_capability_id="cap_a", reward_q32=Q32_ONE, toxic_fail_b=False),
        _holdout_row(context_key=context_2, action_capability_id="cap_b", reward_q32=Q32_ONE, toxic_fail_b=False),
    ]
    candidate_rows = {
        context_1: [("cap_a", 1)],
        context_2: [("cap_b", 1)],
    }
    receipt = _run_eval(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        candidate_rows=candidate_rows,
        baseline_rows={context_1: "cap_b", context_2: "cap_a"},
        holdout_rows=holdout_rows,
        eval_cfg={
            "schema_version": "orch_policy_eval_config_v1",
            "holdout_dataset_id": "sha256:" + ("a" * 64),
            "min_delta_q32": 1,
            "min_coverage_q32": Q32_ONE,
            "max_toxic_increase_q32": 0,
            "baseline_kind": "ACTIVE_POLICY",
        },
    )
    assert str(receipt["status"]) == "PASS"
    assert str(receipt["reason_code"]) == "OK"
