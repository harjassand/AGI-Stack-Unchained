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


def _make_manifest(
    *,
    suite_name: str,
    suite_runner_relpath: str = "tools/omega/omega_benchmark_suite_v1.py",
    visibility: str = "PUBLIC",
    inputs_pack_id: str | None = None,
    labels_pack_id: str | None = None,
    hidden_tests_pack_id: str | None = None,
    io_contract: dict[str, object] | None = None,
) -> dict[str, object]:
    payload = {
        "schema_version": "benchmark_suite_manifest_v1",
        "suite_name": str(suite_name),
        "suite_runner_relpath": str(suite_runner_relpath),
        "visibility": str(visibility),
        "labels": ["public", "phase1"],
        "metrics": {"q32_metric_ids": ["median_stps_non_noop_q32"]},
    }
    if isinstance(inputs_pack_id, str) and inputs_pack_id:
        payload["inputs_pack_id"] = str(inputs_pack_id)
    if isinstance(labels_pack_id, str) and labels_pack_id:
        payload["labels_pack_id"] = str(labels_pack_id)
    if isinstance(hidden_tests_pack_id, str) and hidden_tests_pack_id:
        payload["hidden_tests_pack_id"] = str(hidden_tests_pack_id)
    if isinstance(io_contract, dict):
        payload["io_contract"] = dict(io_contract)
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


def _write_holdout_policy(repo_root: Path, *, require_sandbox_for_live_autonomy: bool = False) -> str:
    payload = {
        "schema_version": "holdout_policy_v1",
        "candidate_visible_prefixes": [
            "tools/",
            "authority/benchmark_suites/",
            "authority/benchmark_suite_sets/",
            "authority/eval_kernel_ledgers/",
            "authority/eval_kernel_extensions/",
        ],
        "harness_only_prefixes": [
            "authority/holdouts/",
        ],
        "candidate_output_policy": {
            "forbidden_output_prefixes": [
                "authority/",
                "meta-core/",
            ],
            "max_output_files_u64": 8,
            "max_output_bytes_u64": 65536,
            "max_single_output_bytes_u64": 32768,
        },
        "candidate_execution_policy": {
            "network": "forbidden",
            "filesystem": "workspace_only",
            "process_spawn": "restricted",
            "require_sandbox_for_live_autonomy_b": bool(require_sandbox_for_live_autonomy),
        },
    }
    with_id = _with_declared_id(payload, id_field="holdout_policy_id")
    path = repo_root / "authority" / "holdout_policies" / "holdout_policy_core_v1.json"
    _write_canon(path, with_id)
    return str(with_id["holdout_policy_id"])


def _write_holdout_pack(
    *,
    repo_root: Path,
    schema_version: str,
    rows: list[dict[str, object]],
) -> str:
    payload = {
        "schema_version": str(schema_version),
        "rows": list(rows),
    }
    with_id = _with_declared_id(payload, id_field="pack_id")
    pack_id = str(with_id["pack_id"])
    pack_path = repo_root / "authority" / "holdouts" / "packs" / f"sha256_{pack_id.split(':', 1)[1]}.json"
    _write_canon(pack_path, with_id)
    return pack_id


def _write_holdout_candidate_runner(repo_root: Path, *, include_forbidden_write: bool = False) -> str:
    rel = "tools/omega/holdout_candidate_runner_test.py"
    path = repo_root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    body = [
        "#!/usr/bin/env python3",
        "from __future__ import annotations",
        "import argparse",
        "import json",
        "from pathlib import Path",
        "",
        "def main() -> int:",
        "    p = argparse.ArgumentParser()",
        "    p.add_argument('--mode', required=True)",
        "    p.add_argument('--inputs_pack_path', required=False)",
        "    p.add_argument('--out_dir', required=False)",
        "    p.add_argument('--suite_id', required=False)",
        "    p.add_argument('--ticks', required=False)",
        "    p.add_argument('--seed_u64', required=False)",
        "    args = p.parse_args()",
        "    if args.mode != 'holdout_candidate':",
        "        return 1",
        "    out_dir = Path(str(args.out_dir or '')).resolve()",
        "    out_dir.mkdir(parents=True, exist_ok=True)",
        "    payload = json.loads(Path(str(args.inputs_pack_path)).read_text(encoding='utf-8'))",
        "    rows = payload.get('rows', []) if isinstance(payload, dict) else []",
        "    lines = []",
        "    for row in rows:",
        "        if not isinstance(row, dict):",
        "            continue",
        "        row_id = str(row.get('id', '')).strip()",
        "        guess = str(row.get('guess', '')).strip()",
        "        if row_id:",
        "            lines.append(json.dumps({'id': row_id, 'prediction': guess}, sort_keys=True, separators=(',', ':')))",
        "    (out_dir / 'predictions.jsonl').write_text('\\n'.join(lines) + ('\\n' if lines else ''), encoding='utf-8')",
    ]
    if include_forbidden_write:
        body.append("    Path('authority/holdouts/leak.txt').parent.mkdir(parents=True, exist_ok=True)")
        body.append("    Path('authority/holdouts/leak.txt').write_text('leak\\n', encoding='utf-8')")
    body.append("    return 0")
    body.append("")
    body.append("if __name__ == '__main__':")
    body.append("    raise SystemExit(main())")
    path.write_text("\n".join(body) + "\n", encoding="utf-8")
    return rel


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


def test_holdout_workspace_excludes_harness_packs_and_binds_receipt_ids(tmp_path: Path, monkeypatch) -> None:
    seeded = _bootstrap_anchor_only(tmp_path)
    repo_root = Path(str(seeded["repo_root"]))
    holdout_policy_id = _write_holdout_policy(repo_root)
    runner_relpath = _write_holdout_candidate_runner(repo_root)

    inputs_pack_id = _write_holdout_pack(
        repo_root=repo_root,
        schema_version="holdout_inputs_pack_v1",
        rows=[
            {"id": "ex1", "guess": "A"},
            {"id": "ex2", "guess": "B"},
        ],
    )
    labels_pack_id = _write_holdout_pack(
        repo_root=repo_root,
        schema_version="holdout_labels_pack_v1",
        rows=[
            {"id": "ex1", "label": "A"},
            {"id": "ex2", "label": "B"},
        ],
    )

    holdout_manifest_rel = "authority/benchmark_suites/holdout_suite.json"
    holdout_manifest = _make_manifest(
        suite_name="holdout_suite",
        suite_runner_relpath=runner_relpath,
        visibility="HOLDOUT",
        inputs_pack_id=inputs_pack_id,
        labels_pack_id=labels_pack_id,
        io_contract={
            "predictions_relpath": "predictions.jsonl",
            "allowed_output_files": ["predictions.jsonl"],
            "max_output_files_u64": 4,
            "max_output_bytes_u64": 65536,
            "max_single_output_bytes_u64": 65536,
        },
    )
    _write_canon(repo_root / holdout_manifest_rel, holdout_manifest)
    holdout_set = _make_suite_set(
        suite_set_kind="ANCHOR",
        anchor_ek_id=str(seeded["ek_id"]),
        suites=[_suite_row(ordinal_u64=0, manifest_payload=holdout_manifest, manifest_relpath=holdout_manifest_rel)],
    )
    _write_canon(repo_root / "authority/benchmark_suite_sets/holdout_anchor_set.json", holdout_set)

    monkeypatch.setattr(
        composite,
        "tracked_files",
        lambda root: sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()),
    )

    receipt = composite.run_composite_once(
        repo_root=repo_root,
        runs_root=tmp_path / "runs",
        series_prefix="series_holdout_isolation",
        ek_id=str(seeded["ek_id"]),
        anchor_suite_set_id=str(holdout_set["suite_set_id"]),
        extensions_ledger_id=str(seeded["ledger_id"]),
        suite_runner_id=_h("9"),
        holdout_policy_id=holdout_policy_id,
        ticks_u64=1,
        seed_u64=17,
    )

    executed = receipt["executed_suites"][0]
    assert executed["suite_visibility"] == "HOLDOUT"
    assert executed["suite_outcome"] == "PASS"
    holdout_execution = dict(executed["holdout_execution"])
    assert holdout_execution["holdout_policy_id"] == holdout_policy_id
    assert holdout_execution["inputs_pack_id"] == inputs_pack_id
    assert holdout_execution["labels_pack_id"] == labels_pack_id
    assert str(holdout_execution["candidate_outputs_hash"]).startswith("sha256:")
    assert int(holdout_execution["candidate_outputs_bytes_u64"]) > 0
    assert receipt["holdout_policy_id"] == holdout_policy_id

    workspace_root = tmp_path / "runs" / "series_holdout_isolation" / "suite_runs" / "suite_000" / "candidate_workspace"
    assert not (workspace_root / "authority" / "holdouts").exists()
    assert not (workspace_root / "authority" / "holdouts" / "packs").exists()


def test_holdout_candidate_write_outside_output_root_fails_io_contract(tmp_path: Path, monkeypatch) -> None:
    seeded = _bootstrap_anchor_only(tmp_path)
    repo_root = Path(str(seeded["repo_root"]))
    holdout_policy_id = _write_holdout_policy(repo_root)
    runner_relpath = _write_holdout_candidate_runner(repo_root, include_forbidden_write=True)

    inputs_pack_id = _write_holdout_pack(
        repo_root=repo_root,
        schema_version="holdout_inputs_pack_v1",
        rows=[{"id": "ex1", "guess": "A"}],
    )
    labels_pack_id = _write_holdout_pack(
        repo_root=repo_root,
        schema_version="holdout_labels_pack_v1",
        rows=[{"id": "ex1", "label": "A"}],
    )

    holdout_manifest_rel = "authority/benchmark_suites/holdout_suite_write_fail.json"
    holdout_manifest = _make_manifest(
        suite_name="holdout_suite_write_fail",
        suite_runner_relpath=runner_relpath,
        visibility="HOLDOUT",
        inputs_pack_id=inputs_pack_id,
        labels_pack_id=labels_pack_id,
        io_contract={
            "predictions_relpath": "predictions.jsonl",
            "allowed_output_files": ["predictions.jsonl"],
            "max_output_files_u64": 4,
            "max_output_bytes_u64": 65536,
            "max_single_output_bytes_u64": 65536,
        },
    )
    _write_canon(repo_root / holdout_manifest_rel, holdout_manifest)
    holdout_set = _make_suite_set(
        suite_set_kind="ANCHOR",
        anchor_ek_id=str(seeded["ek_id"]),
        suites=[_suite_row(ordinal_u64=0, manifest_payload=holdout_manifest, manifest_relpath=holdout_manifest_rel)],
    )
    _write_canon(repo_root / "authority/benchmark_suite_sets/holdout_anchor_set_write_fail.json", holdout_set)

    monkeypatch.setattr(
        composite,
        "tracked_files",
        lambda root: sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()),
    )

    receipt = composite.run_composite_once(
        repo_root=repo_root,
        runs_root=tmp_path / "runs",
        series_prefix="series_holdout_write_fail",
        ek_id=str(seeded["ek_id"]),
        anchor_suite_set_id=str(holdout_set["suite_set_id"]),
        extensions_ledger_id=str(seeded["ledger_id"]),
        suite_runner_id=_h("8"),
        holdout_policy_id=holdout_policy_id,
        ticks_u64=1,
        seed_u64=19,
    )

    executed = receipt["executed_suites"][0]
    assert executed["suite_outcome"] == "FAIL"
    gate_rows = list(executed["gate_results"])
    assert gate_rows
    assert "SUITE_IO_CONTRACT_VIOLATION" in str(gate_rows[0].get("detail", ""))
    holdout_execution = dict(executed["holdout_execution"])
    assert holdout_execution["candidate_stage_status"] == "FAIL"
    assert holdout_execution["harness_stage_status"] == "SKIPPED"


def test_holdout_requires_sandbox_in_live_autonomy_when_unavailable(tmp_path: Path, monkeypatch) -> None:
    seeded = _bootstrap_anchor_only(tmp_path)
    repo_root = Path(str(seeded["repo_root"]))
    holdout_policy_id = _write_holdout_policy(repo_root, require_sandbox_for_live_autonomy=True)
    runner_relpath = _write_holdout_candidate_runner(repo_root)

    inputs_pack_id = _write_holdout_pack(
        repo_root=repo_root,
        schema_version="holdout_inputs_pack_v1",
        rows=[{"id": "ex1", "guess": "A"}],
    )
    labels_pack_id = _write_holdout_pack(
        repo_root=repo_root,
        schema_version="holdout_labels_pack_v1",
        rows=[{"id": "ex1", "label": "A"}],
    )

    holdout_manifest_rel = "authority/benchmark_suites/holdout_suite_live_autonomy.json"
    holdout_manifest = _make_manifest(
        suite_name="holdout_suite_live_autonomy",
        suite_runner_relpath=runner_relpath,
        visibility="HOLDOUT",
        inputs_pack_id=inputs_pack_id,
        labels_pack_id=labels_pack_id,
        io_contract={
            "predictions_relpath": "predictions.jsonl",
            "allowed_output_files": ["predictions.jsonl"],
            "max_output_files_u64": 4,
            "max_output_bytes_u64": 65536,
            "max_single_output_bytes_u64": 65536,
        },
    )
    _write_canon(repo_root / holdout_manifest_rel, holdout_manifest)
    holdout_set = _make_suite_set(
        suite_set_kind="ANCHOR",
        anchor_ek_id=str(seeded["ek_id"]),
        suites=[_suite_row(ordinal_u64=0, manifest_payload=holdout_manifest, manifest_relpath=holdout_manifest_rel)],
    )
    _write_canon(repo_root / "authority/benchmark_suite_sets/holdout_anchor_set_live_autonomy.json", holdout_set)

    monkeypatch.setattr(
        composite,
        "tracked_files",
        lambda root: sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()),
    )
    monkeypatch.setenv("OMEGA_LIVE_AUTONOMY_B", "1")

    receipt = composite.run_composite_once(
        repo_root=repo_root,
        runs_root=tmp_path / "runs",
        series_prefix="series_holdout_live_autonomy",
        ek_id=str(seeded["ek_id"]),
        anchor_suite_set_id=str(holdout_set["suite_set_id"]),
        extensions_ledger_id=str(seeded["ledger_id"]),
        suite_runner_id=_h("6"),
        holdout_policy_id=holdout_policy_id,
        ticks_u64=1,
        seed_u64=29,
    )

    executed = receipt["executed_suites"][0]
    assert executed["suite_outcome"] == "FAIL"
    assert "HOLDOUT_ACCESS_VIOLATION" in str(executed["gate_results"][0]["detail"])


def test_holdout_harness_score_changes_when_labels_change(tmp_path: Path, monkeypatch) -> None:
    seeded = _bootstrap_anchor_only(tmp_path)
    repo_root = Path(str(seeded["repo_root"]))
    holdout_policy_id = _write_holdout_policy(repo_root)
    runner_relpath = _write_holdout_candidate_runner(repo_root)

    inputs_pack_id = _write_holdout_pack(
        repo_root=repo_root,
        schema_version="holdout_inputs_pack_v1",
        rows=[
            {"id": "ex1", "guess": "A"},
            {"id": "ex2", "guess": "B"},
        ],
    )
    labels_pack_match = _write_holdout_pack(
        repo_root=repo_root,
        schema_version="holdout_labels_pack_v1",
        rows=[
            {"id": "ex1", "label": "A"},
            {"id": "ex2", "label": "B"},
        ],
    )
    labels_pack_mismatch = _write_holdout_pack(
        repo_root=repo_root,
        schema_version="holdout_labels_pack_v1",
        rows=[
            {"id": "ex1", "label": "A"},
            {"id": "ex2", "label": "C"},
        ],
    )

    monkeypatch.setattr(
        composite,
        "tracked_files",
        lambda root: sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()),
    )

    def _run_with_labels(*, series: str, labels_pack_id: str) -> dict[str, object]:
        holdout_manifest_rel = f"authority/benchmark_suites/holdout_suite_{series}.json"
        holdout_manifest = _make_manifest(
            suite_name=f"holdout_suite_{series}",
            suite_runner_relpath=runner_relpath,
            visibility="HOLDOUT",
            inputs_pack_id=inputs_pack_id,
            labels_pack_id=labels_pack_id,
            io_contract={
                "predictions_relpath": "predictions.jsonl",
                "allowed_output_files": ["predictions.jsonl"],
                "max_output_files_u64": 4,
                "max_output_bytes_u64": 65536,
                "max_single_output_bytes_u64": 65536,
            },
        )
        _write_canon(repo_root / holdout_manifest_rel, holdout_manifest)
        holdout_set = _make_suite_set(
            suite_set_kind="ANCHOR",
            anchor_ek_id=str(seeded["ek_id"]),
            suites=[_suite_row(ordinal_u64=0, manifest_payload=holdout_manifest, manifest_relpath=holdout_manifest_rel)],
        )
        _write_canon(repo_root / f"authority/benchmark_suite_sets/holdout_anchor_set_{series}.json", holdout_set)
        return composite.run_composite_once(
            repo_root=repo_root,
            runs_root=tmp_path / "runs",
            series_prefix=f"series_holdout_{series}",
            ek_id=str(seeded["ek_id"]),
            anchor_suite_set_id=str(holdout_set["suite_set_id"]),
            extensions_ledger_id=str(seeded["ledger_id"]),
            suite_runner_id=_h("7"),
            holdout_policy_id=holdout_policy_id,
            ticks_u64=1,
            seed_u64=23,
        )

    receipt_match = _run_with_labels(series="match", labels_pack_id=labels_pack_match)
    receipt_mismatch = _run_with_labels(series="mismatch", labels_pack_id=labels_pack_mismatch)

    acc_match = int(receipt_match["aggregate_metrics"]["holdout_accuracy_q32"]["q"])
    acc_mismatch = int(receipt_mismatch["aggregate_metrics"]["holdout_accuracy_q32"]["q"])
    assert acc_match > acc_mismatch
