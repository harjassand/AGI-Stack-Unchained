from __future__ import annotations

from pathlib import Path
from typing import Any

import tools.arena.proposer_arena_v1 as apa


def _patch_candidate(agent_id: str) -> dict[str, Any]:
    return {
        "agent_id": agent_id,
        "candidate_kind": "PATCH",
        "declared_touched_paths": ["campaigns/rsi_proposer_arena_v1/proposer_arena_spec_v1.json"],
        "patch_bytes": b"diff --git a/campaigns/rsi_proposer_arena_v1/proposer_arena_spec_v1.json b/campaigns/rsi_proposer_arena_v1/proposer_arena_spec_v1.json\n--- a/campaigns/rsi_proposer_arena_v1/proposer_arena_spec_v1.json\n+++ b/campaigns/rsi_proposer_arena_v1/proposer_arena_spec_v1.json\n@@ -1,1 +1,1 @@\n-{}\n+{\"schema_version\":\"proposer_arena_spec_v1\"}\n",
        "nontriviality_cert_id": None,
        "oracle_trace_id": None,
        "base_tree_id": "sha256:" + ("0" * 64),
    }


def test_proposer_arena_agent_dispatch_v1(monkeypatch) -> None:
    called: list[str] = []

    def _fake_sh1(*, root: Path, tick_u64: int, ordinal_u32: int, agent_id: str, task_distribution: dict[str, Any]) -> dict[str, Any]:
        called.append("sh1")
        return _patch_candidate(agent_id)

    def _fake_coord(*, root: Path, tick_u64: int, ordinal_u32: int, agent_id: str) -> dict[str, Any]:
        called.append("coord")
        return _patch_candidate(agent_id)

    def _fake_market(*, root: Path, tick_u64: int, ordinal_u32: int, agent_id: str) -> dict[str, Any]:
        called.append("market")
        return _patch_candidate(agent_id)

    def _fake_ext(*, tick_u64: int, ordinal_u32: int, agent_id: str, pins: dict[str, Any]) -> dict[str, Any]:
        called.append("ext")
        return {
            "agent_id": agent_id,
            "candidate_kind": "KERNEL_EXT_PROPOSAL",
            "declared_touched_paths": [],
            "extension_spec": {"schema_version": "kernel_extension_spec_v1", "extension_spec_id": "sha256:" + ("1" * 64), "anchor_ek_id": "sha256:" + ("2" * 64), "extension_name": "x", "suite_set_id": "sha256:" + ("3" * 64), "suite_set_relpath": "benchmark_suite_set_v1.json", "additive_only_b": True},
            "benchmark_suite_manifest": {"schema_version": "benchmark_suite_manifest_v1", "suite_id": "sha256:" + ("4" * 64), "suite_name": "s", "suite_runner_relpath": "tools/omega/omega_benchmark_suite_composite_v1.py", "visibility": "PUBLIC", "labels": ["apa"], "metrics": {"q32_metric_ids": ["accuracy_q32"], "public_only_b": True}},
            "benchmark_suite_set": {"schema_version": "benchmark_suite_set_v1", "suite_set_id": "sha256:" + ("3" * 64), "suite_set_kind": "EXTENSION", "anchor_ek_id": "sha256:" + ("2" * 64), "suites": [{"suite_id": "sha256:" + ("4" * 64), "suite_manifest_id": "sha256:" + ("4" * 64), "suite_manifest_relpath": "benchmark_suite_manifest_v1.json", "ordinal_u64": 0}]},
            "nontriviality_cert_id": None,
            "oracle_trace_id": None,
            "base_tree_id": "sha256:" + ("0" * 64),
        }

    monkeypatch.setattr(apa, "_build_patch_candidate_via_sh1", _fake_sh1)
    monkeypatch.setattr(apa, "_build_patch_candidate_via_coordinator_mutator", _fake_coord)
    monkeypatch.setattr(apa, "_build_patch_candidate_via_market_mutator", _fake_market)
    monkeypatch.setattr(apa, "_build_extension_candidate", _fake_ext)

    root = Path(__file__).resolve().parents[4]
    task_distribution = {"schema_version": "proposer_arena_task_distribution_v1", "weights": {"sh1_v0_3": 1}}
    pins = {"active_ek_id": "sha256:" + ("a" * 64)}

    sh1 = apa._generate_candidate_for_agent(
        root=root,
        tick_u64=7,
        ordinal_u32=0,
        agent_id="sh1_v0_3",
        task_distribution=task_distribution,
        pins=pins,
        agent_def={"agent_id": "sh1_v0_3", "agent_kind": "PATCH_PROPOSER", "entry_module": "tools.genesis_engine.ge_symbiotic_optimizer_v0_3"},
    )
    assert sh1["candidate_kind"] == "PATCH"

    coord = apa._generate_candidate_for_agent(
        root=root,
        tick_u64=7,
        ordinal_u32=0,
        agent_id="coordinator_mutator_v1",
        task_distribution=task_distribution,
        pins=pins,
        agent_def={"agent_id": "coordinator_mutator_v1", "agent_kind": "PATCH_PROPOSER", "entry_module": "orchestrator.rsi_coordinator_mutator_v1"},
    )
    assert coord["candidate_kind"] == "PATCH"

    market = apa._generate_candidate_for_agent(
        root=root,
        tick_u64=7,
        ordinal_u32=0,
        agent_id="market_rules_mutator_v1",
        task_distribution=task_distribution,
        pins=pins,
        agent_def={"agent_id": "market_rules_mutator_v1", "agent_kind": "PATCH_PROPOSER", "entry_module": "orchestrator.rsi_market_rules_mutator_v1"},
    )
    assert market["candidate_kind"] == "PATCH"

    ext = apa._generate_candidate_for_agent(
        root=root,
        tick_u64=7,
        ordinal_u32=0,
        agent_id="kernel_ext_mutator_v1",
        task_distribution=task_distribution,
        pins=pins,
        agent_def={"agent_id": "kernel_ext_mutator_v1", "agent_kind": "KERNEL_EXT_PROPOSER", "entry_module": "tools.arena.proposer_arena_v1"},
    )
    assert ext["candidate_kind"] == "KERNEL_EXT_PROPOSAL"
    assert called == ["sh1", "coord", "market", "ext"]
