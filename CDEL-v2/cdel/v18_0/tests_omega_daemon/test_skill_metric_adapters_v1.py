from __future__ import annotations

from pathlib import Path

from cdel.v1_7r.canon import write_canon_json
from cdel.v18_0 import omega_observer_v1 as observer
from cdel.v18_0 import verify_rsi_omega_daemon_v1 as verifier


def _sha(char: str) -> str:
    return f"sha256:{char * 64}"


def _write_code_perf_report(path: Path, *, passed: bool) -> None:
    payload = {
        "schema_version": "sas_code_perf_report_v1",
        "eval_kind": "DEV",
        "suite_id": "suite_a",
        "suitepack_hash": _sha("1"),
        "baseline_algo_id": _sha("2"),
        "candidate_algo_id": _sha("3"),
        "baseline_work_cost_total": 100,
        "candidate_work_cost_total": 90 if passed else 110,
        "speedup_q32": {
            "schema_version": "q32_v1",
            "shift": 32,
            "q": "4294967296",
        },
        "gate": {
            "min_improvement_percent": 1,
            "passed": bool(passed),
            "reasons": [],
        },
    }
    write_canon_json(path, payload)


def test_observer_load_code_metrics_from_reports(tmp_path: Path) -> None:
    perf_dir = tmp_path / "runs" / "rsi_sas_code_v12_0_tick_0001" / "daemon" / "rsi_sas_code_v12_0" / "state" / "eval" / "perf"
    perf_dir.mkdir(parents=True, exist_ok=True)
    _write_code_perf_report(perf_dir / "a.sas_code_perf_report_v1.json", passed=True)

    metrics, sources = observer._load_code_metrics(root=tmp_path, index={})
    rate = metrics.get("code_success_rate_rat")
    assert isinstance(rate, dict)
    assert int(rate.get("num_u64", 0)) == 1
    assert int(rate.get("den_u64", 0)) == 1
    assert len(sources) == 1
    assert all(str(row.get("schema_id", "")) == "sas_code_perf_report_v1" for row in sources)


def test_verifier_recompute_emits_metric_aliases_and_code_rate(monkeypatch) -> None:
    source_payloads = {
        "metasearch_compute_report_v1": {
            "schema_version": "metasearch_compute_report_v1",
            "c_base_work_cost_total": 2,
            "c_cand_work_cost_total": 1,
        },
        "kernel_hotloop_report_v1": {
            "schema_version": "kernel_hotloop_report_v1",
            "top_loops": [{"bytes": 10}, {"bytes": 5}],
        },
        "sas_system_perf_report_v1": {
            "schema_version": "sas_system_perf_report_v1",
            "cand_cost_total": 1,
            "ref_cost_total": 2,
        },
        "sas_science_promotion_bundle_v1": {
            "schema_version": "sas_science_promotion_bundle_v1",
            "discovery_bundle": {
                "heldout_metrics": {
                    "rmse_pos1_q32": {"q": 123},
                }
            },
        },
        "sas_code_perf_report_v1": {
            "schema_version": "sas_code_perf_report_v1",
            "eval_kind": "DEV",
            "suite_id": "suite_a",
            "suitepack_hash": _sha("1"),
            "baseline_algo_id": _sha("2"),
            "candidate_algo_id": _sha("3"),
            "baseline_work_cost_total": 100,
            "candidate_work_cost_total": 90,
            "speedup_q32": {
                "schema_version": "q32_v1",
                "shift": 32,
                "q": "4294967296",
            },
            "gate": {
                "min_improvement_percent": 1,
                "passed": True,
                "reasons": [],
            },
        },
        "omega_skill_transfer_report_v1": {
            "schema_version": "omega_skill_report_v1",
            "skill_id": "TRANSFER_V1_6R",
            "tick_u64": 1,
            "inputs_hash": _sha("a"),
            "metrics": {"transfer_gain_q32": {"q": 77}},
            "flags": [],
            "recommendations": [{"kind": "TRANSFER_REVIEW", "detail": "ok"}],
        },
        "omega_skill_ontology_report_v1": {
            "schema_version": "omega_skill_report_v1",
            "skill_id": "ONTOLOGY_V2_V1_6R",
            "tick_u64": 1,
            "inputs_hash": _sha("b"),
            "metrics": {"ontology_consistency_q32": {"q": 88}},
            "flags": [],
            "recommendations": [{"kind": "ONTOLOGY_SYNC", "detail": "ok"}],
        },
        "omega_skill_eff_flywheel_report_v1": {
            "schema_version": "omega_skill_report_v1",
            "skill_id": "EFF_FLYWHEEL_V2_0",
            "tick_u64": 1,
            "inputs_hash": _sha("c"),
            "metrics": {"flywheel_yield_q32": {"q": 99}},
            "flags": [],
            "recommendations": [{"kind": "FLYWHEEL_TUNE", "detail": "ok"}],
        },
        "omega_skill_thermo_report_v1": {
            "schema_version": "omega_skill_report_v1",
            "skill_id": "THERMO_V5",
            "tick_u64": 1,
            "inputs_hash": _sha("d"),
            "metrics": {"thermo_efficiency_q32": {"q": 111}},
            "flags": [],
            "recommendations": [{"kind": "THERMO_REVIEW", "detail": "ok"}],
        },
        "omega_skill_persistence_report_v1": {
            "schema_version": "omega_skill_report_v1",
            "skill_id": "PERSIST_V6",
            "tick_u64": 1,
            "inputs_hash": _sha("e"),
            "metrics": {"persistence_health_q32": {"q": 1 << 32}},
            "flags": ["SNAPSHOT_OK", "TRACE_OK"],
            "recommendations": [{"kind": "PERSISTENCE_AUDIT", "detail": "ok"}],
        },
    }

    def _fake_read_observer_source_artifact(*, root: Path, source: dict, runs_roots=None):  # noqa: ARG001
        schema_id = str(source.get("schema_id", ""))
        payload = source_payloads[schema_id]
        return schema_id, payload

    monkeypatch.setattr(verifier, "_read_observer_source_artifact", _fake_read_observer_source_artifact)

    sources = []
    for idx, schema_id in enumerate(
        [
            "metasearch_compute_report_v1",
            "kernel_hotloop_report_v1",
            "sas_system_perf_report_v1",
            "sas_science_promotion_bundle_v1",
            "sas_code_perf_report_v1",
            "omega_skill_transfer_report_v1",
            "omega_skill_ontology_report_v1",
            "omega_skill_eff_flywheel_report_v1",
            "omega_skill_thermo_report_v1",
            "omega_skill_persistence_report_v1",
        ]
    ):
        sources.append(
            {
                "schema_id": schema_id,
                "artifact_hash": _sha(hex(idx + 1)[2]),
                "producer_campaign_id": verifier._OBS_SOURCE_CAMPAIGN[schema_id],
                "producer_run_id": f"run_{idx}",
            }
        )

    observation_payload = {
        "schema_version": "omega_observation_report_v1",
        "report_id": _sha("a"),
        "tick_u64": 1,
        "active_manifest_hash": _sha("b"),
        "metrics": {},
        "sources": sources,
        "inputs_hashes": {
            "policy_hash": _sha("c"),
            "registry_hash": _sha("d"),
            "objectives_hash": _sha("e"),
        },
    }

    recomputed = verifier._recompute_observation_from_sources(
        root=Path("."),
        runs_roots=[],
        observation_payload=observation_payload,
        policy_hash=_sha("c"),
        registry_hash=_sha("d"),
        objectives_hash=_sha("e"),
        prev_observation=None,
    )
    metrics = recomputed.get("metrics")
    assert isinstance(metrics, dict)
    assert metrics.get("hotloop_top_share_q32") == metrics.get("val_hotloop_top_share_q32")
    assert metrics.get("build_link_fraction_q32") == metrics.get("system_build_link_fraction_q32")
    code_rate = metrics.get("code_success_rate_rat")
    assert isinstance(code_rate, dict)
    assert int(code_rate.get("num_u64", 0)) == 1
    assert int(code_rate.get("den_u64", 0)) == 1
    assert metrics.get("transfer_gain_q32") == {"q": 77}
    assert metrics.get("ontology_consistency_q32") == {"q": 88}
    assert metrics.get("flywheel_yield_q32") == {"q": 99}
    assert metrics.get("thermo_efficiency_q32") == {"q": 111}
    assert metrics.get("persistence_health_q32") == {"q": 1 << 32}
    assert int(metrics.get("persistence_flags_u64", 0)) == 2
