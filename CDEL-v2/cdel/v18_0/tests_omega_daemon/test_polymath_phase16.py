from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from cdel.v1_7r.canon import load_canon_json, write_canon_json
from cdel.v18_0 import campaign_polymath_bootstrap_domain_v1 as bootstrap_campaign
from cdel.v18_0 import campaign_polymath_conquer_domain_v1 as conquer_campaign
from cdel.v18_0.omega_common_v1 import Q32_ONE, OmegaV18Error, canon_hash_obj, load_canon_dict, validate_schema
from cdel.v18_0.polymath_verifier_kernel_v1 import verify_domain
from orchestrator.omega_v18_0.goal_synthesizer_v1 import synthesize_goal_queue
from tools.polymath import polymath_dataset_fetch_v1 as fetch_mod
from tools.polymath import polymath_scout_v1 as scout_mod
from tools.polymath.polymath_domain_bootstrap_v1 import bootstrap_domain
from tools.polymath.polymath_equivalence_suite_v1 import run_equivalence


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _sha(ch: str) -> str:
    return f"sha256:{ch * 64}"


def _q32_accuracy(preds: list[int], targets: list[int]) -> int:
    if len(preds) != len(targets) or not targets:
        raise RuntimeError("invalid metric inputs")
    correct = sum(1 for pred, target in zip(preds, targets) if int(pred) == int(target))
    return (correct * Q32_ONE) // len(targets)


def _write_fetch_receipt(path: Path, *, sha256: str, url: str) -> dict[str, Any]:
    payload = {
        "schema_version": "polymath_fetch_receipt_v1",
        "receipt_id": _sha("0"),
        "url": str(url),
        "request": {"headers": {}, "params": {}},
        "fetched_at_utc": "2026-02-09T00:00:00+00:00",
        "http_status": 200,
        "content_type": "application/json",
        "content_length_u64": 1,
        "etag": None,
        "last_modified": None,
        "sha256": str(sha256),
    }
    no_id = dict(payload)
    no_id.pop("receipt_id", None)
    payload["receipt_id"] = canon_hash_obj(no_id)
    write_canon_json(path, payload)
    return payload


def _write_void_row(path: Path, *, domain_id: str, topic_id: str, topic_name: str, void_q: int) -> None:
    row = {
        "schema_version": "polymath_void_report_v1",
        "row_id": _sha("f"),
        "scanned_at_utc": "2026-02-09T00:00:00+00:00",
        "topic_id": str(topic_id),
        "topic_name": str(topic_name),
        "candidate_domain_id": str(domain_id),
        "trend_score_q32": {"q": max(void_q, 1)},
        "coverage_score_q32": {"q": 0},
        "void_score_q32": {"q": int(void_q)},
        "source_evidence": [
            {
                "url": "https://example.org/topic",
                "sha256": _sha("1"),
                "receipt_sha256": _sha("2"),
            }
        ],
    }
    validate_schema(row, "polymath_void_report_v1")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def test_polymath_schemas_validate_and_hashes_are_stable() -> None:
    root = _repo_root()
    schema_paths = [
        root / "Genesis" / "schema" / "v18_0" / "polymath_domain_pack_v1.jsonschema",
        root / "Genesis" / "schema" / "v18_0" / "polymath_domain_registry_v1.jsonschema",
        root / "Genesis" / "schema" / "v18_0" / "polymath_fetch_receipt_v1.jsonschema",
        root / "Genesis" / "schema" / "v18_0" / "polymath_void_report_v1.jsonschema",
        root / "Genesis" / "schema" / "v18_0" / "polymath_domain_corpus_v1.jsonschema",
        root / "Genesis" / "schema" / "v18_0" / "polymath_equivalence_report_v1.jsonschema",
        root / "Genesis" / "schema" / "v18_0" / "domain_policy_v1.jsonschema",
    ]
    for path in schema_paths:
        first = canon_hash_obj(load_canon_dict(path))
        second = canon_hash_obj(load_canon_dict(path))
        assert first == second
        assert first.startswith("sha256:")

    validate_schema(load_canon_dict(root / "polymath" / "domain_policy_v1.json"), "domain_policy_v1")
    validate_schema(
        {
            "schema_version": "polymath_fetch_receipt_v1",
            "receipt_id": _sha("1"),
            "url": "https://example.org/data.json",
            "request": {"headers": {}, "params": {}},
            "fetched_at_utc": "2026-02-09T00:00:00+00:00",
            "http_status": 200,
            "content_type": "application/json",
            "content_length_u64": 10,
            "etag": None,
            "last_modified": None,
            "sha256": _sha("2"),
        },
        "polymath_fetch_receipt_v1",
    )
    validate_schema(
        {
            "schema_version": "polymath_void_report_v1",
            "row_id": _sha("3"),
            "scanned_at_utc": "2026-02-09T00:00:00+00:00",
            "topic_id": "topic:genomics",
            "topic_name": "Genomics",
            "candidate_domain_id": "genomics",
            "trend_score_q32": {"q": 1},
            "coverage_score_q32": {"q": 0},
            "void_score_q32": {"q": 1},
            "source_evidence": [{"url": "https://example.org", "sha256": _sha("4"), "receipt_sha256": _sha("5")}],
        },
        "polymath_void_report_v1",
    )
    validate_schema(
        {
            "schema_version": "polymath_domain_corpus_v1",
            "corpus_id": _sha("6"),
            "dataset_sha256": _sha("7"),
            "domain_id": "genomics",
            "examples": [{"example_id": "ex-1", "input": {"x": 1}, "target": 1}],
        },
        "polymath_domain_corpus_v1",
    )
    validate_schema(
        {
            "schema_version": "polymath_domain_pack_v1",
            "domain_id": "genomics",
            "domain_name": "Genomics",
            "topic_ids": ["topic:genomics"],
            "dataset_artifacts": [
                {
                    "sha256": _sha("8"),
                    "kind": "starter_dataset",
                    "license": "CC0-1.0",
                    "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
                    "provenance": [{"url": "https://example.org/dataset", "receipt_sha256": _sha("9")}],
                }
            ],
            "tasks": [
                {
                    "task_id": "task_classify_v1",
                    "task_type": "classification",
                    "input_schema_ref": "schemas/input_v1.jsonschema",
                    "target_schema_ref": "schemas/target_v1.jsonschema",
                    "metric": "accuracy",
                    "split": {"train_sha256": _sha("a"), "test_sha256": _sha("b")},
                }
            ],
            "metamorphic_tests": [{"test_id": "round_trip_v1", "task_id": "task_classify_v1", "template": "schema_round_trip"}],
            "oracles": [{"oracle_name": "huggingface_load_dataset", "adapter_version": "polymath_sources_v1", "response_sha256": [_sha("c")]}],
        },
        "polymath_domain_pack_v1",
    )
    validate_schema(
        {
            "schema_version": "polymath_domain_registry_v1",
            "domains": [
                {
                    "domain_id": "genomics",
                    "domain_name": "Genomics",
                    "status": "ACTIVE",
                    "created_at_utc": "2026-02-09T00:00:00+00:00",
                    "topic_ids": ["topic:genomics"],
                    "domain_pack_rel": "domains/genomics/domain_pack_v1.json",
                }
            ],
        },
        "polymath_domain_registry_v1",
    )
    validate_schema(
        {
            "schema_version": "polymath_equivalence_report_v1",
            "report_id": _sha("d"),
            "domain_id": "genomics",
            "kernel_version": "polymath_verifier_kernel_v1",
            "reference_hash": _sha("e"),
            "candidate_hash": _sha("f"),
            "cases_u64": 1,
            "mismatches_u64": 0,
            "pass_b": True,
            "details": [],
        },
        "polymath_equivalence_report_v1",
    )


def test_fetch_url_sealed_cache_returns_same_sha_and_preserves_receipts(monkeypatch, tmp_path: Path) -> None:
    store = tmp_path / "store"
    calls = {"count": 0}
    monkeypatch.setenv("OMEGA_NET_LIVE_OK", "1")
    times = iter(
        [
            "2026-02-09T00:00:00+00:00",
            "2026-02-09T00:00:01+00:00",
            "2026-02-09T00:00:02+00:00",
            "2026-02-09T00:00:03+00:00",
        ]
    )

    class _FakeResponse:
        def __init__(self, data: bytes) -> None:
            self._data = data
            self.status = 200
            self.headers = {
                "Content-Type": "application/json",
                "ETag": 'W/"abc"',
                "Last-Modified": "Mon, 09 Feb 2026 00:00:00 GMT",
            }

        def read(self) -> bytes:
            return self._data

        def __enter__(self) -> "_FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:  # noqa: ANN001
            _ = (exc_type, exc, tb)
            return False

    def _urlopen(_request, timeout=0):  # noqa: ANN001
        _ = timeout
        calls["count"] += 1
        return _FakeResponse(b'{"ok":1}')

    monkeypatch.setattr(fetch_mod, "_utc_now_iso", lambda: next(times))
    monkeypatch.setattr(fetch_mod.urllib.request, "urlopen", _urlopen)

    first = fetch_mod.fetch_url_sealed("https://example.org/data.json", params={"q": "1"}, store_root=store)
    second = fetch_mod.fetch_url_sealed("https://example.org/data.json", params={"q": "1"}, store_root=store)
    third = fetch_mod.fetch_url_sealed(
        "https://example.org/data.json",
        params={"q": "1"},
        store_root=store,
        force_refetch=True,
    )

    assert str(first["sha256"]) == str(second["sha256"]) == str(third["sha256"])
    assert bool(second["cached_b"]) is True
    assert int(calls["count"]) == 2

    digest = str(first["sha256"]).split(":", 1)[1]
    receipt_paths = sorted((store / "receipts").glob(f"{digest}*.json"), key=lambda path: path.name)
    assert len(receipt_paths) == 2

    primary_receipt = load_canon_dict(receipt_paths[0])
    assert str(primary_receipt["fetched_at_utc"]) == "2026-02-09T00:00:00+00:00"
    assert fetch_mod.load_blob_bytes(sha256=str(first["sha256"]), store_root=store) == b'{"ok":1}'


def test_scout_void_is_deterministic_from_pinned_source_responses(monkeypatch, tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.json"
    void_a = tmp_path / "void_a.jsonl"
    void_b = tmp_path / "void_b.jsonl"
    receipts_dir = tmp_path / "receipts"
    receipts_dir.mkdir(parents=True, exist_ok=True)

    write_canon_json(registry_path, {"schema_version": "polymath_domain_registry_v1", "domains": []})

    def _sealed(name: str, ch: str, url: str) -> dict[str, str]:
        receipt_path = receipts_dir / f"{name}.json"
        _write_fetch_receipt(receipt_path, sha256=_sha(ch), url=url)
        return {
            "sha256": _sha(ch),
            "receipt_path": receipt_path.as_posix(),
            "url": url,
        }

    sealed_map = {
        "openalex": _sealed("openalex", "1", "https://api.openalex.org/topics"),
        "arxiv": _sealed("arxiv", "2", "http://export.arxiv.org/api/query"),
        "crossref": _sealed("crossref", "3", "https://api.crossref.org/works"),
        "s2": _sealed("s2", "4", "https://api.semanticscholar.org/graph/v1/paper/search"),
    }

    class _FakeSourceClient:
        def openalex_topics(self, **_kwargs):  # noqa: ANN003
            return {
                "api": "openalex_topics",
                "url": sealed_map["openalex"]["url"],
                "sealed": dict(sealed_map["openalex"]),
                "payload": {
                    "results": [
                        {"id": "topic:1", "display_name": "Genomics Lite", "cited_by_count": 1000},
                        {"id": "topic:2", "display_name": "Classical Mechanics", "cited_by_count": 200},
                    ]
                },
            }

        def arxiv_query(self, *, search_query: str, **_kwargs):  # noqa: ANN003
            total = 40 if "Genomics" in search_query else 5
            xml = (
                '<feed xmlns="http://www.w3.org/2005/Atom" '
                'xmlns:open="http://a9.com/-/spec/opensearch/1.1/">'
                f"<open:totalResults>{total}</open:totalResults></feed>"
            )
            return {"api": "arxiv_query", "url": sealed_map["arxiv"]["url"], "sealed": dict(sealed_map["arxiv"]), "payload": {"xml": xml}}

        def crossref_works(self, *, query: str, **_kwargs):  # noqa: ANN003
            total = 500 if "Genomics" in query else 12
            return {
                "api": "crossref_works",
                "url": sealed_map["crossref"]["url"],
                "sealed": dict(sealed_map["crossref"]),
                "payload": {"message": {"total-results": total}},
            }

        def semantic_scholar_paper_search(self, *, query: str, **_kwargs):  # noqa: ANN003
            total = 250 if "Genomics" in query else 7
            return {"api": "s2", "url": sealed_map["s2"]["url"], "sealed": dict(sealed_map["s2"]), "payload": {"total": total}}

    monkeypatch.setattr(scout_mod, "_utc_now_iso", lambda: "2026-02-09T00:00:00+00:00")

    result_a = scout_mod.scout_void(
        registry_path=registry_path,
        void_report_path=void_a,
        source_client=_FakeSourceClient(),
        max_topics=2,
        delay_seconds=0.0,
    )
    result_b = scout_mod.scout_void(
        registry_path=registry_path,
        void_report_path=void_b,
        source_client=_FakeSourceClient(),
        max_topics=2,
        delay_seconds=0.0,
    )

    rows_a = [json.loads(line) for line in void_a.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows_b = [json.loads(line) for line in void_b.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert rows_a == rows_b
    assert int(result_a["rows_written_u64"]) == 2
    assert int(result_b["rows_written_u64"]) == 2
    assert str(result_a["top_rows"][0]["candidate_domain_id"]) == "genomics_lite"


def test_bootstrap_campaign_bootstraps_and_registers_domain(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    out_dir = tmp_path / "out"
    pack_path = tmp_path / "bootstrap_pack.json"

    write_canon_json(
        repo / "polymath" / "registry" / "polymath_domain_registry_v1.json",
        {"schema_version": "polymath_domain_registry_v1", "domains": []},
    )
    write_canon_json(
        repo / "polymath" / "domain_policy_v1.json",
        {
            "schema_version": "domain_policy_v1",
            "denylist_keywords": ["malware"],
            "allowlist_keywords": ["genomics", "physics", "chemistry"],
        },
    )
    _write_void_row(
        repo / "polymath" / "registry" / "polymath_void_report_v1.jsonl",
        domain_id="genomics_lite",
        topic_id="topic:genomics_lite",
        topic_name="Genomics Lite",
        void_q=Q32_ONE,
    )
    write_canon_json(
        pack_path,
        {
            "schema_version": "rsi_polymath_bootstrap_domain_pack_v1",
            "domain_registry_path_rel": "polymath/registry/polymath_domain_registry_v1.json",
            "void_report_path_rel": "polymath/registry/polymath_void_report_v1.jsonl",
            "domain_policy_path_rel": "polymath/domain_policy_v1.json",
            "max_new_domains_u64": 1,
        },
    )

    monkeypatch.setattr(bootstrap_campaign, "repo_root", lambda: repo)
    monkeypatch.setattr(bootstrap_campaign, "emit_test_plan_receipt", lambda **_kwargs: ({}, {}))
    monkeypatch.setenv("OMEGA_POLYMATH_STORE_ROOT", str((repo / ".omega_cache" / "polymath" / "store").resolve()))
    bootstrap_campaign.run(campaign_pack=pack_path, out_dir=out_dir)

    report = load_canon_dict(out_dir / "daemon" / "rsi_polymath_bootstrap_domain_v1" / "state" / "reports" / "polymath_bootstrap_report_v1.json")
    assert str(report["status"]) == "BOOTSTRAPPED"
    domain_pack_path = out_dir / str(report["domain_pack_rel"])
    domain_pack = load_canon_dict(domain_pack_path)
    validate_schema(domain_pack, "polymath_domain_pack_v1")

    registry = load_canon_dict(out_dir / "polymath" / "registry" / "polymath_domain_registry_v1.json")
    domains = registry.get("domains")
    assert isinstance(domains, list) and len(domains) == 1
    assert str(domains[0]["status"]) == "ACTIVE"
    assert str(domains[0]["capability_id"]).startswith("RSI_DOMAIN_")


def test_bootstrap_campaign_blocks_policy_violations(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    out_dir = tmp_path / "out"
    pack_path = tmp_path / "bootstrap_pack.json"

    write_canon_json(
        repo / "polymath" / "registry" / "polymath_domain_registry_v1.json",
        {"schema_version": "polymath_domain_registry_v1", "domains": []},
    )
    write_canon_json(
        repo / "polymath" / "domain_policy_v1.json",
        {
            "schema_version": "domain_policy_v1",
            "denylist_keywords": ["malware"],
            "allowlist_keywords": ["genomics", "physics", "chemistry"],
        },
    )
    _write_void_row(
        repo / "polymath" / "registry" / "polymath_void_report_v1.jsonl",
        domain_id="malware_research",
        topic_id="topic:malware_research",
        topic_name="Malware Research",
        void_q=Q32_ONE,
    )
    write_canon_json(
        pack_path,
        {
            "schema_version": "rsi_polymath_bootstrap_domain_pack_v1",
            "domain_registry_path_rel": "polymath/registry/polymath_domain_registry_v1.json",
            "void_report_path_rel": "polymath/registry/polymath_void_report_v1.jsonl",
            "domain_policy_path_rel": "polymath/domain_policy_v1.json",
            "max_new_domains_u64": 1,
        },
    )

    monkeypatch.setattr(bootstrap_campaign, "repo_root", lambda: repo)
    monkeypatch.setattr(bootstrap_campaign, "emit_test_plan_receipt", lambda **_kwargs: ({}, {}))
    monkeypatch.setenv("OMEGA_POLYMATH_STORE_ROOT", str((repo / ".omega_cache" / "polymath" / "store").resolve()))
    bootstrap_campaign.run(campaign_pack=pack_path, out_dir=out_dir)

    report = load_canon_dict(out_dir / "daemon" / "rsi_polymath_bootstrap_domain_v1" / "state" / "reports" / "polymath_bootstrap_report_v1.json")
    assert str(report["status"]) == "BLOCKED_POLICY"
    registry = load_canon_dict(out_dir / "polymath" / "registry" / "polymath_domain_registry_v1.json")
    domains = registry.get("domains")
    assert isinstance(domains, list) and len(domains) == 1
    assert str(domains[0]["status"]) == "BLOCKED_POLICY"


def test_polymath_verifier_and_equivalence_suite_end_to_end(tmp_path: Path) -> None:
    store_root = tmp_path / "polymath" / "store"
    domains_root = tmp_path / "domains"
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)

    bootstrap = bootstrap_domain(
        domain_id="genomics_lite",
        domain_name="Genomics Lite",
        topic_ids=["topic:genomics_lite"],
        domains_root=domains_root,
        store_root=store_root,
        starter_size=18,
    )
    domain_pack = load_canon_dict(Path(str(bootstrap["domain_pack_path"])))
    task = domain_pack["tasks"][0]
    task_id = str(task["task_id"])
    test_sha = str(task["split"]["test_sha256"])
    test_rows = json.loads(fetch_mod.load_blob_bytes(sha256=test_sha, store_root=store_root).decode("utf-8"))
    targets = [int(row["target"]) for row in test_rows if isinstance(row, dict)]

    perfect_preds = list(targets)
    perfect_outputs = {
        "schema_version": "polymath_candidate_outputs_v1",
        "domain_id": str(bootstrap["domain_id"]),
        "task_outputs": [
            {
                "task_id": task_id,
                "predictions": perfect_preds,
                "reported_metric": {"q": _q32_accuracy(perfect_preds, targets)},
            }
        ],
    }
    perfect_path = tmp_path / "perfect_outputs.json"
    write_canon_json(perfect_path, perfect_outputs)

    assert (
        verify_domain(
            state_dir=state_dir,
            domain_pack_path=Path(str(bootstrap["domain_pack_path"])),
            candidate_outputs_path=perfect_path,
        )
        == "VALID"
    )

    bad_outputs = dict(perfect_outputs)
    bad_outputs["task_outputs"] = [dict(perfect_outputs["task_outputs"][0])]
    bad_outputs["task_outputs"][0]["reported_metric"] = {"q": int(perfect_outputs["task_outputs"][0]["reported_metric"]["q"]) - 1}
    bad_path = tmp_path / "bad_outputs.json"
    write_canon_json(bad_path, bad_outputs)
    with pytest.raises(OmegaV18Error):
        verify_domain(
            state_dir=state_dir,
            domain_pack_path=Path(str(bootstrap["domain_pack_path"])),
            candidate_outputs_path=bad_path,
        )

    mismatch_preds = [1 - int(value) for value in targets]
    mismatch_outputs = {
        "schema_version": "polymath_candidate_outputs_v1",
        "domain_id": str(bootstrap["domain_id"]),
        "task_outputs": [
            {
                "task_id": task_id,
                "predictions": mismatch_preds,
                "reported_metric": {"q": _q32_accuracy(mismatch_preds, targets)},
            }
        ],
    }
    mismatch_path = tmp_path / "mismatch_outputs.json"
    write_canon_json(mismatch_path, mismatch_outputs)

    eq_pass = run_equivalence(
        state_dir=state_dir,
        domain_pack_path=Path(str(bootstrap["domain_pack_path"])),
        reference_outputs_path=perfect_path,
        candidate_outputs_path=perfect_path,
        out_path=tmp_path / "eq_pass.json",
    )
    assert bool(eq_pass["pass_b"]) is True
    assert int(eq_pass["mismatches_u64"]) == 0

    eq_fail = run_equivalence(
        state_dir=state_dir,
        domain_pack_path=Path(str(bootstrap["domain_pack_path"])),
        reference_outputs_path=perfect_path,
        candidate_outputs_path=mismatch_path,
        out_path=tmp_path / "eq_fail.json",
    )
    assert bool(eq_fail["pass_b"]) is False
    assert int(eq_fail["mismatches_u64"]) > 0


def _bootstrap_repo_domain(repo_root: Path, *, domain_id: str = "genomics_lite") -> dict[str, Any]:
    store_root = repo_root / "polymath" / "store"
    domains_root = repo_root / "domains"
    bootstrap = bootstrap_domain(
        domain_id=domain_id,
        domain_name="Genomics Lite",
        topic_ids=["topic:genomics_lite"],
        domains_root=domains_root,
        store_root=store_root,
        starter_size=18,
    )
    registry = {
        "schema_version": "polymath_domain_registry_v1",
        "domains": [
            {
                "domain_id": str(bootstrap["domain_id"]),
                "domain_name": "Genomics Lite",
                "status": "ACTIVE",
                "created_at_utc": "2026-02-09T00:00:00+00:00",
                "topic_ids": ["topic:genomics_lite"],
                "domain_pack_rel": f"domains/{bootstrap['domain_id']}/domain_pack_v1.json",
                "capability_id": f"RSI_DOMAIN_{str(bootstrap['domain_id']).upper()}",
                "dataset_artifact_sha256s": [],
            }
        ],
    }
    write_canon_json(repo_root / "polymath" / "registry" / "polymath_domain_registry_v1.json", registry)
    return bootstrap


def test_conquer_campaign_accepts_improving_solver(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    out_dir = tmp_path / "out"
    pack_path = tmp_path / "conquer_pack.json"
    _bootstrap_repo_domain(repo)
    write_canon_json(
        pack_path,
        {
            "schema_version": "rsi_polymath_conquer_domain_pack_v1",
            "domain_registry_path_rel": "polymath/registry/polymath_domain_registry_v1.json",
            "require_improvement_b": True,
            "target_domain_id": "",
        },
    )

    monkeypatch.setattr(conquer_campaign, "repo_root", lambda: repo)
    monkeypatch.setattr(conquer_campaign, "emit_test_plan_receipt", lambda **_kwargs: ({}, {}))
    conquer_campaign.run(campaign_pack=pack_path, out_dir=out_dir)

    report = load_canon_dict(out_dir / "daemon" / "rsi_polymath_conquer_domain_v1" / "state" / "reports" / "polymath_conquer_report_v1.json")
    assert str(report["status"]) == "IMPROVED"
    bundle_rows = sorted(
        (out_dir / "daemon" / "rsi_polymath_conquer_domain_v1" / "state" / "promotion").glob("sha256_*.polymath_conquer_promotion_bundle_v1.json")
    )
    assert bundle_rows


def test_conquer_campaign_rejects_when_no_improvement(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    out_dir = tmp_path / "out"
    pack_path = tmp_path / "conquer_pack.json"
    _bootstrap_repo_domain(repo)
    write_canon_json(
        pack_path,
        {
            "schema_version": "rsi_polymath_conquer_domain_pack_v1",
            "domain_registry_path_rel": "polymath/registry/polymath_domain_registry_v1.json",
            "require_improvement_b": True,
            "target_domain_id": "",
        },
    )

    monkeypatch.setattr(conquer_campaign, "repo_root", lambda: repo)
    monkeypatch.setattr(conquer_campaign, "_metric_improved", lambda metric, baseline_q32, improved_q32: False)
    monkeypatch.setattr(conquer_campaign, "emit_test_plan_receipt", lambda **_kwargs: ({}, {}))
    conquer_campaign.run(campaign_pack=pack_path, out_dir=out_dir)

    report = load_canon_dict(out_dir / "daemon" / "rsi_polymath_conquer_domain_v1" / "state" / "reports" / "polymath_conquer_report_v1.json")
    assert str(report["status"]) == "NO_IMPROVEMENT"
    bundle_rows = sorted(
        (out_dir / "daemon" / "rsi_polymath_conquer_domain_v1" / "state" / "promotion").glob("sha256_*.polymath_conquer_promotion_bundle_v1.json")
    )
    assert not bundle_rows


def test_goal_synthesizer_emits_polymath_bootstrap_and_conquer_goals(monkeypatch) -> None:
    monkeypatch.setattr("orchestrator.omega_v18_0.goal_synthesizer_v1._top_void_candidate_domain_id", lambda: "genomics_lite")
    monkeypatch.setattr("orchestrator.omega_v18_0.goal_synthesizer_v1._latest_ready_domain_id", lambda: "genomics_lite")

    out = synthesize_goal_queue(
        tick_u64=100,
        goal_queue_base={"schema_version": "omega_goal_queue_v1", "goals": []},
        state={
            "budget_remaining": {
                "cpu_cost_q32": {"q": 1 << 40},
                "build_cost_q32": {"q": 1 << 40},
                "verifier_cost_q32": {"q": 1 << 40},
                "disk_bytes_u64": 1 << 40,
            },
            "cooldowns": {},
            "last_actions": [],
            "goals": {},
        },
        issue_bundle={"issues": []},
        observation_report={
            "metrics": {
                "top_void_score_q32": {"q": int(0.50 * Q32_ONE)},
                "polymath_scout_age_ticks_u64": 5,
                "domains_ready_for_conquer_u64": 1,
                "runaway_blocked_noop_rate_rat": {"num_u64": 0, "den_u64": 1},
                "runaway_blocked_recent3_u64": 0,
            }
        },
        registry={
            "capabilities": [
                {
                    "campaign_id": "rsi_polymath_scout_v1",
                    "capability_id": "RSI_POLYMATH_SCOUT",
                    "enabled": True,
                    "budget_cost_hint_q32": {"q": 1},
                },
                {
                    "campaign_id": "rsi_polymath_bootstrap_domain_v1",
                    "capability_id": "RSI_POLYMATH_BOOTSTRAP_DOMAIN",
                    "enabled": True,
                    "budget_cost_hint_q32": {"q": 1},
                },
                {
                    "campaign_id": "rsi_polymath_conquer_domain_v1",
                    "capability_id": "RSI_POLYMATH_CONQUER_DOMAIN",
                    "enabled": True,
                    "budget_cost_hint_q32": {"q": 1},
                },
            ]
        },
        runaway_cfg={"schema_version": "omega_runaway_config_v1", "enabled": True},
    )

    goals = [str(row.get("goal_id", "")) for row in out.get("goals", []) if isinstance(row, dict)]
    assert any(goal.startswith("goal_polymath_bootstrap_genomics_lite_") for goal in goals)
    assert any(goal.startswith("goal_polymath_conquer_genomics_lite_") for goal in goals)
