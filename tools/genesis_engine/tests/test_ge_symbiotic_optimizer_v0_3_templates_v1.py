from __future__ import annotations

import json
from pathlib import Path

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
