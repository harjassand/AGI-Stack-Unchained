from __future__ import annotations

from cdel.v18_0.campaign_ge_symbiotic_optimizer_sh1_v0_1 import _patch_touches_capability_registry


def test_patch_touches_capability_registry_detects_v18_path() -> None:
    patch = (
        "--- a/campaigns/rsi_omega_daemon_v18_0/omega_capability_registry_v2.json\n"
        "+++ b/campaigns/rsi_omega_daemon_v18_0/omega_capability_registry_v2.json\n"
        "@@ -1 +1 @@\n"
    ).encode("utf-8")
    assert _patch_touches_capability_registry(patch_bytes=patch) is True


def test_patch_touches_capability_registry_detects_v18_prod_path() -> None:
    patch = (
        "--- a/campaigns/rsi_omega_daemon_v18_0_prod/omega_capability_registry_v2.json\n"
        "+++ b/campaigns/rsi_omega_daemon_v18_0_prod/omega_capability_registry_v2.json\n"
        "@@ -1 +1 @@\n"
    ).encode("utf-8")
    assert _patch_touches_capability_registry(patch_bytes=patch) is True


def test_patch_touches_capability_registry_ignores_other_paths() -> None:
    patch = (
        "--- a/campaigns/rsi_omega_daemon_v18_0/goals/omega_goal_queue_v1.json\n"
        "+++ b/campaigns/rsi_omega_daemon_v18_0/goals/omega_goal_queue_v1.json\n"
        "@@ -1 +1 @@\n"
    ).encode("utf-8")
    assert _patch_touches_capability_registry(patch_bytes=patch) is False
