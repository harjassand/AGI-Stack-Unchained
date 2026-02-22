from __future__ import annotations

import json
from pathlib import Path

from cdel.v19_0.nontriviality_cert_v1 import (
    FORCED_HEAVY_ARCHETYPE_CALL_EDGE,
    FORCED_HEAVY_ARCHETYPE_CONTROL_FLOW,
    FORCED_HEAVY_ARCHETYPE_HELPER_REPLACE,
    build_nontriviality_cert_v1,
)
from cdel.v18_0.hard_task_suite_v1 import evaluate_hard_task_patch_delta_v1

from tools.genesis_engine import ge_symbiotic_optimizer_v0_3 as ge_v0_3


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def test_json_tweak_cooldown_minus_1_template(tmp_path: Path) -> None:
    rel = "campaigns/rsi_omega_daemon_v18_0/omega_capability_registry_v2.json"
    target = tmp_path / rel
    _write_json(
        target,
        {
            "schema_version": "omega_capability_registry_v2",
            "capabilities": [
                {"campaign_id": "rsi_a", "cooldown_ticks_u64": 5},
                {"campaign_id": "rsi_b", "cooldown_ticks_u64": 9},
            ],
        },
    )
    patch = ge_v0_3._build_json_tweak_patch(  # noqa: SLF001
        target_relpath=rel,
        marker="m",
        template_id="JSON_TWEAK_COOLDOWN_MINUS_1",
        repo_root=tmp_path,
    )
    patch_text = patch.decode("utf-8")
    assert '"cooldown_ticks_u64":5' in patch_text
    assert '"cooldown_ticks_u64":4' in patch_text


def test_json_tweak_budget_minus_1step_template(tmp_path: Path) -> None:
    rel = "campaigns/rsi_omega_daemon_v18_0/omega_capability_registry_v2.json"
    target = tmp_path / rel
    _write_json(
        target,
        {
            "schema_version": "omega_capability_registry_v2",
            "capabilities": [
                {"campaign_id": "rsi_a", "budget_cost_hint_q32": {"q": (1 << 31)}},
            ],
        },
    )
    patch = ge_v0_3._build_json_tweak_patch(  # noqa: SLF001
        target_relpath=rel,
        marker="m",
        template_id="JSON_TWEAK_BUDGET_HINT_MINUS_1STEP",
        repo_root=tmp_path,
    )
    patch_text = patch.decode("utf-8")
    assert f'"q":{1 << 31}' in patch_text
    assert f'"q":{1 << 30}' in patch_text


def test_code_fastpath_guard_template(tmp_path: Path) -> None:
    rel = "orchestrator/common/run_invoker_v1.py"
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "\n".join(
            [
                "def run(proc, output_dir, stdout_path, stderr_path):",
                "    output_dir.mkdir(parents=True, exist_ok=True)",
                "    stdout_path.write_text(proc.stdout, encoding=\"utf-8\")",
                "    output_dir.mkdir(parents=True, exist_ok=True)",
                "    stderr_path.write_text(proc.stderr, encoding=\"utf-8\")",
                "    return 0",
                "",
            ]
        ),
        encoding="utf-8",
    )

    patch = ge_v0_3._build_code_fastpath_guard_patch(  # noqa: SLF001
        target_relpath=rel,
        repo_root=tmp_path,
    )
    patch_text = patch.decode("utf-8")
    assert "-    output_dir.mkdir(parents=True, exist_ok=True)" in patch_text
    assert "stdout_path.write_text(proc.stdout, encoding=\"utf-8\")" in patch_text
    assert "stderr_path.write_text(proc.stderr, encoding=\"utf-8\")" in patch_text


def test_code_rewrite_ast_template_unified_diff_first(tmp_path: Path) -> None:
    rel = "orchestrator/omega_v18_0/decider_v1.py"
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "\n".join(
            [
                "def decide(x: int) -> int:",
                "    return x + 1",
                "",
            ]
        ),
        encoding="utf-8",
    )
    patch = ge_v0_3._build_code_rewrite_ast_patch(  # noqa: SLF001
        target_relpath=rel,
        marker="marker_1",
        repo_root=tmp_path,
    )
    patch_text = patch.decode("utf-8")
    assert "+# ge_code_rewrite_ast:marker_1" in patch_text
    assert "+def _ge_wire_helper_marker_1(value):" in patch_text


def test_code_rewrite_ast_template_supports_two_files_deterministically(tmp_path: Path) -> None:
    rel_a = "orchestrator/omega_v18_0/decider_v1.py"
    rel_b = "orchestrator/omega_v18_0/goal_synthesizer_v1.py"
    for rel, fn_name in ((rel_a, "decide"), (rel_b, "synthesize")):
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            "\n".join(
                [
                    f"def {fn_name}(x: int) -> int:",
                    "    return x + 1",
                    "",
                ]
            ),
            encoding="utf-8",
        )
    patch = ge_v0_3._build_code_rewrite_ast_patch(  # noqa: SLF001
        target_relpaths=[rel_b, rel_a],
        marker="marker_two",
        repo_root=tmp_path,
    )
    patch_text = patch.decode("utf-8")
    assert patch_text.count("--- a/orchestrator/omega_v18_0/decider_v1.py") == 1
    assert patch_text.count("--- a/orchestrator/omega_v18_0/goal_synthesizer_v1.py") == 1
    assert patch_text.find("--- a/orchestrator/omega_v18_0/decider_v1.py") < patch_text.find(
        "--- a/orchestrator/omega_v18_0/goal_synthesizer_v1.py"
    )


def test_code_rewrite_ast_archetype_call_edge_cert(tmp_path: Path) -> None:
    rel = "orchestrator/omega_v18_0/decider_v1.py"
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "\n".join(
            [
                "def decide(x: int) -> int:",
                "    return x + 1",
                "",
            ]
        ),
        encoding="utf-8",
    )
    patch = ge_v0_3._build_code_rewrite_ast_patch(  # noqa: SLF001
        target_relpath=rel,
        marker="marker_call",
        repo_root=tmp_path,
        archetype_id=FORCED_HEAVY_ARCHETYPE_CALL_EDGE,
    )
    cert = build_nontriviality_cert_v1(
        repo_root=tmp_path,
        patch_bytes=patch,
        archetype_id=FORCED_HEAVY_ARCHETYPE_CALL_EDGE,
    )
    assert cert["call_edges_changed_b"] is True
    assert cert["wiring_class_ok_b"] is True
    assert cert["archetype_pass_b"] is True
    assert cert["failed_threshold_code"] is None


def test_code_rewrite_ast_archetype_control_flow_cert(tmp_path: Path) -> None:
    rel = "orchestrator/omega_v18_0/decider_v1.py"
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "\n".join(
            [
                "def decide(x: int) -> int:",
                "    return x + 1",
                "",
            ]
        ),
        encoding="utf-8",
    )
    patch = ge_v0_3._build_code_rewrite_ast_patch(  # noqa: SLF001
        target_relpath=rel,
        marker="marker_cf",
        repo_root=tmp_path,
        archetype_id=FORCED_HEAVY_ARCHETYPE_CONTROL_FLOW,
    )
    cert = build_nontriviality_cert_v1(
        repo_root=tmp_path,
        patch_bytes=patch,
        archetype_id=FORCED_HEAVY_ARCHETYPE_CONTROL_FLOW,
    )
    assert cert["control_flow_changed_b"] is True
    assert cert["wiring_class_ok_b"] is True
    assert cert["archetype_pass_b"] is True
    assert cert["failed_threshold_code"] is None


def test_code_rewrite_ast_archetype_helper_replace_cert(tmp_path: Path) -> None:
    rel = "orchestrator/omega_v18_0/decider_v1.py"
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "\n".join(
            [
                "def decide(x: int) -> int:",
                "    return x + 1",
                "",
            ]
        ),
        encoding="utf-8",
    )
    patch = ge_v0_3._build_code_rewrite_ast_patch(  # noqa: SLF001
        target_relpath=rel,
        marker="marker_helper",
        repo_root=tmp_path,
        archetype_id=FORCED_HEAVY_ARCHETYPE_HELPER_REPLACE,
    )
    cert = build_nontriviality_cert_v1(
        repo_root=tmp_path,
        patch_bytes=patch,
        archetype_id=FORCED_HEAVY_ARCHETYPE_HELPER_REPLACE,
    )
    assert cert["data_flow_changed_b"] is True
    assert int(cert["ast_nodes_changed_u32"]) >= int(cert["thresholds_v1"]["wiring_ast_nodes_min_u32"])
    assert cert["wiring_class_ok_b"] is True
    assert cert["archetype_pass_b"] is True
    assert cert["failed_threshold_code"] is None


def test_code_rewrite_ast_target_patchable_requires_return_site(tmp_path: Path) -> None:
    rel_adapter = "orchestrator/omega_v18_0/decider_v1.py"
    adapter = tmp_path / rel_adapter
    adapter.parent.mkdir(parents=True, exist_ok=True)
    adapter.write_text(
        "\n".join(
            [
                '"""Adapter."""',
                "from cdel.v18_0.omega_decider_v1 import decide",
                "",
            ]
        ),
        encoding="utf-8",
    )
    rel_impl = "orchestrator/omega_v18_0/goal_synthesizer_v1.py"
    impl = tmp_path / rel_impl
    impl.parent.mkdir(parents=True, exist_ok=True)
    impl.write_text(
        "\n".join(
            [
                "def synthesize(x: int) -> int:",
                "    return x",
                "",
            ]
        ),
        encoding="utf-8",
    )
    assert ge_v0_3._code_rewrite_ast_target_patchable(repo_root=tmp_path, target_relpath=rel_adapter) is False  # noqa: SLF001
    assert ge_v0_3._code_rewrite_ast_target_patchable(repo_root=tmp_path, target_relpath=rel_impl) is True  # noqa: SLF001


def test_forced_heavy_template_pool_wiring_contract_v1(tmp_path: Path) -> None:
    rel = "orchestrator/omega_v18_0/decider_v1.py"
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "\n".join(
            [
                "def decide(x: int) -> int:",
                "    return x + 1",
                "",
            ]
        ),
        encoding="utf-8",
    )
    for template_id in ge_v0_3.FORCED_HEAVY_TEMPLATE_POOL_V1:
        for archetype_id in (
            FORCED_HEAVY_ARCHETYPE_CALL_EDGE,
            FORCED_HEAVY_ARCHETYPE_CONTROL_FLOW,
            FORCED_HEAVY_ARCHETYPE_HELPER_REPLACE,
        ):
            patch = ge_v0_3._build_patch_bytes_for_template(  # noqa: SLF001
                template_id=template_id,
                target_relpath=rel,
                target_relpaths=[rel],
                marker=f"marker_{template_id}_{archetype_id}",
                repo_root=tmp_path,
                archetype_id=archetype_id,
            )
            cert = build_nontriviality_cert_v1(
                repo_root=tmp_path,
                patch_bytes=patch,
                archetype_id=archetype_id,
            )
            assert cert["wiring_class_ok_b"] is True
            assert any(
                bool(cert.get(flag, False))
                for flag in ("call_edges_changed_b", "control_flow_changed_b", "data_flow_changed_b")
            )


def test_forced_heavy_smoke_eval_predicts_hard_task_gain_v1(tmp_path: Path) -> None:
    rel = "orchestrator/omega_v18_0/goal_synthesizer_v1.py"
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "\n".join(
            [
                "import re",
                "",
                "_GOAL_ID_TOKEN_RE = re.compile(r\"[^a-z0-9_]+\")",
                "",
                "def _slug(value: str) -> str:",
                "    out = _GOAL_ID_TOKEN_RE.sub(\"_\", str(value).strip().lower()).strip(\"_\")",
                "    return out or \"x\"",
                "",
                "def _goal_id_for(priority_prefix: str, reason_slug: str, capability_id: str, tick_u64: int, suffix_u64: int = 0) -> str:",
                "    cap_slug = _slug(capability_id)",
                "    if priority_prefix == \"CORE\":",
                "        base = f\"goal_self_optimize_core_00_{_slug(reason_slug)}_{int(tick_u64):06d}\"",
                "    elif priority_prefix == \"00\":",
                "        base = f\"goal_auto_00_issue_{_slug(reason_slug)}_{cap_slug}_{int(tick_u64):06d}\"",
                "    elif priority_prefix == \"10\":",
                "        base = f\"goal_auto_10_runaway_blocked_{cap_slug}_{int(tick_u64):06d}\"",
                "    elif priority_prefix == \"20\":",
                "        base = f\"goal_explore_20_family_{_slug(reason_slug)}_{cap_slug}_{int(tick_u64):06d}\"",
                "    else:",
                "        base = f\"goal_auto_90_queue_floor_{cap_slug}_{int(tick_u64):06d}\"",
                "    if suffix_u64 <= 0:",
                "        return base",
                "    return f\"{base}_{int(suffix_u64):02d}\"",
                "",
            ]
        ),
        encoding="utf-8",
    )

    patch_call_edge = ge_v0_3._build_code_rewrite_ast_patch(  # noqa: SLF001
        target_relpath=rel,
        marker="marker_call",
        repo_root=tmp_path,
        archetype_id=FORCED_HEAVY_ARCHETYPE_CALL_EDGE,
    )
    call_edge_delta = evaluate_hard_task_patch_delta_v1(repo_root=tmp_path, patch_bytes=patch_call_edge)
    assert int(call_edge_delta["predicted_delta_total_q32"]) > 0

    patch_control_flow = ge_v0_3._build_code_rewrite_ast_patch(  # noqa: SLF001
        target_relpath=rel,
        marker="marker_cf",
        repo_root=tmp_path,
        archetype_id=FORCED_HEAVY_ARCHETYPE_CONTROL_FLOW,
    )
    control_flow_delta = evaluate_hard_task_patch_delta_v1(repo_root=tmp_path, patch_bytes=patch_control_flow)
    assert int(control_flow_delta["predicted_delta_total_q32"]) <= 0
