from __future__ import annotations

import json
from pathlib import Path

import pytest

from cdel.v18_0.omega_common_v1 import canon_hash_obj
from tools.omega import omega_benchmark_suite_composite_v1 as composite


def _h(ch: str) -> str:
    return "sha256:" + (ch * 64)


def _write_canon(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def _with_declared_id(payload: dict[str, object], *, id_field: str) -> dict[str, object]:
    out = dict(payload)
    out[id_field] = _h("0")
    no_id = dict(out)
    no_id.pop(id_field, None)
    out[id_field] = canon_hash_obj(no_id)
    return out


def _make_manifest(*, suite_name: str, suite_runner_relpath: str = "tools/omega/omega_benchmark_suite_v1.py") -> dict[str, object]:
    payload = {
        "schema_version": "benchmark_suite_manifest_v1",
        "suite_name": str(suite_name),
        "suite_runner_relpath": str(suite_runner_relpath),
        "visibility": "PUBLIC",
        "labels": ["public", "phase1"],
        "metrics": {"q32_metric_ids": ["median_stps_non_noop_q32"]},
    }
    return _with_declared_id(payload, id_field="suite_id")


def _make_suite_set(
    *,
    suite_set_kind: str,
    anchor_ek_id: str,
    suites: list[dict[str, object]],
) -> dict[str, object]:
    payload = {
        "schema_version": "benchmark_suite_set_v1",
        "suite_set_kind": str(suite_set_kind),
        "anchor_ek_id": str(anchor_ek_id),
        "suites": list(suites),
    }
    return _with_declared_id(payload, id_field="suite_set_id")


def _make_extension_spec(*, anchor_ek_id: str, suite_set_id: str, suite_set_relpath: str) -> dict[str, object]:
    payload = {
        "schema_version": "kernel_extension_spec_v1",
        "anchor_ek_id": str(anchor_ek_id),
        "additive_only_b": True,
        "suite_set_id": str(suite_set_id),
        "suite_set_relpath": str(suite_set_relpath),
    }
    return _with_declared_id(payload, id_field="extension_spec_id")


def _make_ledger(*, anchor_ek_id: str, parent_ledger_id: str, entries: list[dict[str, object]]) -> dict[str, object]:
    payload = {
        "schema_version": "kernel_extension_ledger_v1",
        "anchor_ek_id": str(anchor_ek_id),
        "parent_ledger_id": str(parent_ledger_id),
        "entries": list(entries),
    }
    return _with_declared_id(payload, id_field="ledger_id")


def _suite_row(*, ordinal_u64: int, manifest_payload: dict[str, object], manifest_relpath: str) -> dict[str, object]:
    return {
        "ordinal_u64": int(max(0, int(ordinal_u64))),
        "suite_id": str(manifest_payload["suite_id"]),
        "suite_manifest_id": canon_hash_obj(manifest_payload),
        "suite_manifest_relpath": str(manifest_relpath),
    }


def _bootstrap_anchor_only(tmp_path: Path) -> dict[str, object]:
    repo_root = tmp_path / "repo"
    ek_id = _h("a")

    anchor_manifest_relpath = "authority/benchmark_suites/anchor_suite.json"
    anchor_manifest = _make_manifest(suite_name="anchor_suite")
    _write_canon(repo_root / anchor_manifest_relpath, anchor_manifest)

    anchor_set_relpath = "authority/benchmark_suite_sets/anchor_suite_set.json"
    anchor_set = _make_suite_set(
        suite_set_kind="ANCHOR",
        anchor_ek_id=ek_id,
        suites=[_suite_row(ordinal_u64=0, manifest_payload=anchor_manifest, manifest_relpath=anchor_manifest_relpath)],
    )
    _write_canon(repo_root / anchor_set_relpath, anchor_set)

    ledger_relpath = "authority/eval_kernel_ledgers/kernel_extension_ledger_active_v1.json"
    ledger = _make_ledger(anchor_ek_id=ek_id, parent_ledger_id="", entries=[])
    _write_canon(repo_root / ledger_relpath, ledger)

    (repo_root / "authority" / "eval_kernel_extensions").mkdir(parents=True, exist_ok=True)
    return {
        "repo_root": repo_root,
        "ek_id": ek_id,
        "anchor_suite_id": str(anchor_manifest["suite_id"]),
        "anchor_suite_set_id": str(anchor_set["suite_set_id"]),
        "ledger_id": str(ledger["ledger_id"]),
        "anchor_manifest": anchor_manifest,
    }


def _append_extension_entry(
    *,
    repo_root: Path,
    ek_id: str,
    ordinal_u64: int,
    manifest_payload: dict[str, object],
    manifest_relpath: str,
    ext_tag: str,
) -> dict[str, object]:
    _write_canon(repo_root / manifest_relpath, manifest_payload)
    ext_suite_set_relpath = f"authority/benchmark_suite_sets/extension_suite_set_{ext_tag}.json"
    ext_suite_set = _make_suite_set(
        suite_set_kind="EXTENSION",
        anchor_ek_id=ek_id,
        suites=[
            _suite_row(
                ordinal_u64=0,
                manifest_payload=manifest_payload,
                manifest_relpath=manifest_relpath,
            )
        ],
    )
    _write_canon(repo_root / ext_suite_set_relpath, ext_suite_set)

    ext_spec_relpath = f"authority/eval_kernel_extensions/extension_spec_{ext_tag}.json"
    ext_spec = _make_extension_spec(
        anchor_ek_id=ek_id,
        suite_set_id=str(ext_suite_set["suite_set_id"]),
        suite_set_relpath=ext_suite_set_relpath,
    )
    _write_canon(repo_root / ext_spec_relpath, ext_spec)
    return {
        "ordinal_u64": int(max(0, int(ordinal_u64))),
        "extension_spec_id": str(ext_spec["extension_spec_id"]),
        "extension_spec_relpath": ext_spec_relpath,
        "suite_set_id": str(ext_suite_set["suite_set_id"]),
        "suite_set_relpath": ext_suite_set_relpath,
    }


def test_anchor_only_composite_run_matches_single_suite_metrics(tmp_path: Path, monkeypatch) -> None:
    seeded = _bootstrap_anchor_only(tmp_path)
    repo_root = Path(str(seeded["repo_root"]))

    def _fake_run_legacy_suite(**_kwargs):
        return (
            "PASS",
            {
                "median_stps_non_noop_q32": {"q": 111},
                "hard_task_suite_score_q32": {"q": 222},
            },
            [{"gate_id": "ALL_SUITES_PASS", "passed_b": True}],
        )

    monkeypatch.setattr(composite, "_run_legacy_suite", _fake_run_legacy_suite)

    receipt = composite.run_composite_once(
        repo_root=repo_root,
        runs_root=tmp_path / "runs",
        series_prefix="series_anchor_only",
        ek_id=str(seeded["ek_id"]),
        anchor_suite_set_id=str(seeded["anchor_suite_set_id"]),
        extensions_ledger_id=str(seeded["ledger_id"]),
        suite_runner_id=_h("b"),
        ticks_u64=1,
        seed_u64=7,
    )

    assert receipt["schema_version"] == "benchmark_run_receipt_v2"
    assert receipt["anchor_suite_set_id"] == seeded["anchor_suite_set_id"]
    assert receipt["extensions_ledger_id"] == seeded["ledger_id"]
    assert len(receipt["executed_suites"]) == 1
    executed = receipt["executed_suites"][0]
    assert executed["suite_id"] == seeded["anchor_suite_id"]
    assert executed["suite_source"] == "ANCHOR"
    assert receipt["effective_suite_ids"] == [seeded["anchor_suite_id"]]
    assert receipt["aggregate_metrics"]["median_stps_non_noop_q32"]["q"] == 111
    assert receipt["aggregate_metrics"]["hard_task_suite_score_q32"]["q"] == 222
    assert bool(receipt["gate_results"][0]["passed_b"]) is True


def test_extension_suite_failure_marks_all_suites_gate_failed(tmp_path: Path, monkeypatch) -> None:
    seeded = _bootstrap_anchor_only(tmp_path)
    repo_root = Path(str(seeded["repo_root"]))

    ext_manifest = _make_manifest(suite_name="extension_suite")
    ext_entry = _append_extension_entry(
        repo_root=repo_root,
        ek_id=str(seeded["ek_id"]),
        ordinal_u64=0,
        manifest_payload=ext_manifest,
        manifest_relpath="authority/benchmark_suites/extension_suite.json",
        ext_tag="one",
    )
    ledger = _make_ledger(
        anchor_ek_id=str(seeded["ek_id"]),
        parent_ledger_id=str(seeded["ledger_id"]),
        entries=[ext_entry],
    )
    _write_canon(repo_root / "authority/eval_kernel_ledgers/kernel_extension_ledger_next_v1.json", ledger)

    def _fake_run_legacy_suite(**kwargs):
        suite = kwargs["suite"]
        if suite.suite_source == "EXTENSION":
            return (
                "FAIL",
                {},
                [{"gate_id": "LEGACY_RUNNER_EXIT_ZERO", "passed_b": False}],
            )
        return (
            "PASS",
            {"median_stps_non_noop_q32": {"q": 101}},
            [{"gate_id": "ALL_SUITES_PASS", "passed_b": True}],
        )

    monkeypatch.setattr(composite, "_run_legacy_suite", _fake_run_legacy_suite)

    receipt = composite.run_composite_once(
        repo_root=repo_root,
        runs_root=tmp_path / "runs",
        series_prefix="series_extension_fail",
        ek_id=str(seeded["ek_id"]),
        anchor_suite_set_id=str(seeded["anchor_suite_set_id"]),
        extensions_ledger_id=str(ledger["ledger_id"]),
        suite_runner_id=_h("c"),
        ticks_u64=1,
        seed_u64=9,
    )

    outcomes = [str(row.get("suite_outcome", "")) for row in receipt["executed_suites"]]
    assert "FAIL" in outcomes
    assert bool(receipt["gate_results"][0]["passed_b"]) is False


@pytest.mark.parametrize(
    ("tamper_kind", "expected_codes"),
    [
        ("anchor_mismatch", {"SCHEMA_FAIL"}),
        ("ordinal_gap", {"SCHEMA_FAIL"}),
        ("parent_missing", {"MISSING_STATE_INPUT"}),
    ],
)
def test_tampered_extension_ledger_is_rejected(
    tmp_path: Path,
    tamper_kind: str,
    expected_codes: set[str],
) -> None:
    seeded = _bootstrap_anchor_only(tmp_path)
    repo_root = Path(str(seeded["repo_root"]))

    if tamper_kind == "anchor_mismatch":
        ledger = _make_ledger(anchor_ek_id=_h("f"), parent_ledger_id="", entries=[])
    elif tamper_kind == "ordinal_gap":
        ext_manifest = _make_manifest(suite_name="extension_suite")
        ext_entry = _append_extension_entry(
            repo_root=repo_root,
            ek_id=str(seeded["ek_id"]),
            ordinal_u64=1,
            manifest_payload=ext_manifest,
            manifest_relpath="authority/benchmark_suites/extension_suite_ordinal_gap.json",
            ext_tag="ordinal_gap",
        )
        ledger = _make_ledger(
            anchor_ek_id=str(seeded["ek_id"]),
            parent_ledger_id="",
            entries=[ext_entry],
        )
    elif tamper_kind == "parent_missing":
        ledger = _make_ledger(anchor_ek_id=str(seeded["ek_id"]), parent_ledger_id=_h("d"), entries=[])
    else:
        raise AssertionError("unexpected tamper kind")

    _write_canon(repo_root / "authority/eval_kernel_ledgers/kernel_extension_ledger_active_v1.json", ledger)
    with pytest.raises(composite.CompositeRunnerError) as exc:
        composite.resolve_effective_suites(
            repo_root=repo_root,
            ek_id=str(seeded["ek_id"]),
            anchor_suite_set_id=str(seeded["anchor_suite_set_id"]),
            extensions_ledger_id=str(ledger["ledger_id"]),
        )
    assert exc.value.code in expected_codes


def test_duplicate_suite_ids_fail_closed(tmp_path: Path, monkeypatch) -> None:
    seeded = _bootstrap_anchor_only(tmp_path)
    repo_root = Path(str(seeded["repo_root"]))

    # Reuse the anchor manifest in an extension suite-set to force duplicate suite_id.
    ext_entry = _append_extension_entry(
        repo_root=repo_root,
        ek_id=str(seeded["ek_id"]),
        ordinal_u64=0,
        manifest_payload=dict(seeded["anchor_manifest"]),
        manifest_relpath="authority/benchmark_suites/anchor_suite.json",
        ext_tag="dup",
    )
    ledger = _make_ledger(
        anchor_ek_id=str(seeded["ek_id"]),
        parent_ledger_id=str(seeded["ledger_id"]),
        entries=[ext_entry],
    )
    _write_canon(repo_root / "authority/eval_kernel_ledgers/kernel_extension_ledger_next_v2.json", ledger)

    monkeypatch.setattr(
        composite,
        "_run_legacy_suite",
        lambda **_kwargs: (
            "PASS",
            {"median_stps_non_noop_q32": {"q": 1}},
            [{"gate_id": "ALL_SUITES_PASS", "passed_b": True}],
        ),
    )

    with pytest.raises(composite.CompositeRunnerError) as exc:
        composite.run_composite_once(
            repo_root=repo_root,
            runs_root=tmp_path / "runs",
            series_prefix="series_dup_suite",
            ek_id=str(seeded["ek_id"]),
            anchor_suite_set_id=str(seeded["anchor_suite_set_id"]),
            extensions_ledger_id=str(ledger["ledger_id"]),
            suite_runner_id=_h("e"),
            ticks_u64=1,
            seed_u64=11,
        )
    assert exc.value.code == "EK_SUITE_LIST_MISMATCH"


def test_executed_suite_order_is_deterministic_and_bound_to_effective_list(tmp_path: Path, monkeypatch) -> None:
    seeded = _bootstrap_anchor_only(tmp_path)
    repo_root = Path(str(seeded["repo_root"]))

    ext_entry_1 = _append_extension_entry(
        repo_root=repo_root,
        ek_id=str(seeded["ek_id"]),
        ordinal_u64=0,
        manifest_payload=_make_manifest(suite_name="extension_suite_one"),
        manifest_relpath="authority/benchmark_suites/extension_suite_one.json",
        ext_tag="one",
    )
    ext_entry_2 = _append_extension_entry(
        repo_root=repo_root,
        ek_id=str(seeded["ek_id"]),
        ordinal_u64=1,
        manifest_payload=_make_manifest(suite_name="extension_suite_two"),
        manifest_relpath="authority/benchmark_suites/extension_suite_two.json",
        ext_tag="two",
    )
    ledger = _make_ledger(
        anchor_ek_id=str(seeded["ek_id"]),
        parent_ledger_id=str(seeded["ledger_id"]),
        entries=[ext_entry_1, ext_entry_2],
    )
    _write_canon(repo_root / "authority/eval_kernel_ledgers/kernel_extension_ledger_next_v3.json", ledger)

    def _fake_run_legacy_suite(**kwargs):
        suite = kwargs["suite"]
        return (
            "PASS",
            {"median_stps_non_noop_q32": {"q": len(str(suite.suite_name))}},
            [{"gate_id": "ALL_SUITES_PASS", "passed_b": True}],
        )

    monkeypatch.setattr(composite, "_run_legacy_suite", _fake_run_legacy_suite)

    receipt_a = composite.run_composite_once(
        repo_root=repo_root,
        runs_root=tmp_path / "runs",
        series_prefix="series_order_a",
        ek_id=str(seeded["ek_id"]),
        anchor_suite_set_id=str(seeded["anchor_suite_set_id"]),
        extensions_ledger_id=str(ledger["ledger_id"]),
        suite_runner_id=_h("f"),
        ticks_u64=1,
        seed_u64=13,
    )
    receipt_b = composite.run_composite_once(
        repo_root=repo_root,
        runs_root=tmp_path / "runs",
        series_prefix="series_order_b",
        ek_id=str(seeded["ek_id"]),
        anchor_suite_set_id=str(seeded["anchor_suite_set_id"]),
        extensions_ledger_id=str(ledger["ledger_id"]),
        suite_runner_id=_h("f"),
        ticks_u64=1,
        seed_u64=13,
    )

    ids_a = [str(row["suite_id"]) for row in receipt_a["executed_suites"]]
    ids_b = [str(row["suite_id"]) for row in receipt_b["executed_suites"]]
    assert ids_a == ids_b
    assert ids_a == list(receipt_a["effective_suite_ids"])
    assert ids_b == list(receipt_b["effective_suite_ids"])
