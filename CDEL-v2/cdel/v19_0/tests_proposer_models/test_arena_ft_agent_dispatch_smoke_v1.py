from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import tools.arena.proposer_arena_v1 as apa
import tools.proposer_models.pointers_v1 as pointers_v1
import tools.proposer_models.runtime_v1 as runtime_v1


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)


def test_arena_ft_agent_dispatch_smoke_v1(monkeypatch, tmp_path: Path) -> None:
    repo = (tmp_path / "repo").resolve()
    repo.mkdir(parents=True, exist_ok=True)

    _git(repo, "init")
    _git(repo, "config", "user.email", "dev@example.com")
    _git(repo, "config", "user.name", "Dev User")

    target_rel = "campaigns/rsi_proposer_arena_v1/proposer_arena_spec_v1.json"
    target_path = (repo / target_rel).resolve()
    target_path.parent.mkdir(parents=True, exist_ok=True)

    before_line = "{\"schema_version\":\"proposer_arena_spec_v1\"}"
    after_line = "{\"schema_version\":\"proposer_arena_spec_v1\",\"arena_touch_tick_u64\":1}"
    target_path.write_text(before_line + "\n", encoding="utf-8")

    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "init")

    patch_text = (
        f"diff --git a/{target_rel} b/{target_rel}\n"
        f"--- a/{target_rel}\n"
        f"+++ b/{target_rel}\n"
        "@@ -1 +1 @@\n"
        f"-{before_line}\n"
        f"+{after_line}\n"
    )

    def _fake_load_active_pointer(*, active_root: Path, role: str) -> dict[str, Any]:
        return {
            "schema_version": "proposer_model_pointer_v1",
            "role": role,
            "active_bundle_id": "sha256:" + ("4" * 64),
            "updated_tick_u64": 1,
        }

    def _fake_generate_patch_deterministic(
        role: str,
        prompt_text: str,
        model_bundle_id: str,
        seed_u64: int,
        max_new_tokens_u32: int,
    ) -> str:
        assert role == "PATCH_DRAFTER_V1"
        assert model_bundle_id == "sha256:" + ("4" * 64)
        assert max_new_tokens_u32 > 0
        assert "target_file" in prompt_text
        return patch_text

    monkeypatch.setattr(pointers_v1, "load_active_pointer", _fake_load_active_pointer)
    monkeypatch.setattr(runtime_v1, "generate_patch_deterministic", _fake_generate_patch_deterministic)

    task_distribution = {
        "schema_version": "proposer_arena_task_distribution_v1",
        "weights": {"ft_patch_drafter_v1": 1},
        "patch_targets": [target_rel],
    }
    candidate = apa._generate_candidate_for_agent(
        root=repo,
        tick_u64=11,
        ordinal_u32=0,
        agent_id="ft_patch_drafter_v1",
        task_distribution=task_distribution,
        pins={"active_ek_id": "sha256:" + ("5" * 64)},
        agent_def={
            "agent_id": "ft_patch_drafter_v1",
            "agent_kind": "PATCH_PROPOSER",
            "entry_module": "tools.arena.proposer_arena_v1",
            "agent_method": "ft_patch_drafter_v1",
            "model_role": "PATCH_DRAFTER_V1",
        },
    )

    assert str(candidate.get("candidate_kind", "")) == "PATCH"
    assert target_rel in list(candidate.get("declared_touched_paths") or [])

    admitted_b, decision_code, derived_touched, _payload_hashes = apa._admission_allowlist_and_preflight(
        root=repo,
        candidate=candidate,
        allowlists={
            "allow_prefixes": ["campaigns/rsi_proposer_arena_v1/"],
            "forbid_prefixes": [],
            "forbid_exact_paths": [],
        },
        arena_spec={"forbid_lock_prefixes": []},
        lane_requires_wiring_b=False,
        max_patch_bytes_u32=10_000,
    )

    assert admitted_b is True
    assert decision_code == "PASS"
    assert target_rel in derived_touched
