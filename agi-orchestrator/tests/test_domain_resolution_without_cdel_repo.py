from __future__ import annotations

from orchestrator.run import _resolve_domain


def test_resolve_domain_without_repo_io() -> None:
    domain = _resolve_domain("io-algorithms-v1", require_repo=False)
    assert domain.dev_config is None
    assert domain.heldout_config is None


def test_resolve_domain_without_repo_env() -> None:
    domain = _resolve_domain("env-gridworld-v1", require_repo=False)
    assert domain.dev_config is None
    assert domain.heldout_config is None
