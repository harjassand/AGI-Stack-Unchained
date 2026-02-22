from __future__ import annotations

from copy import deepcopy

from cdel.v18_0 import verify_rsi_omega_daemon_v1 as verifier
from cdel.v18_0.omega_common_v1 import canon_hash_obj

from .utils import latest_file, load_json, run_tick_once


def test_verifier_recompute_detects_hard_task_suite_hash_mismatch_v1(tmp_path) -> None:
    _, state_dir = run_tick_once(tmp_path, tick_u64=1)

    daemon_root = state_dir.parent
    config_dir = daemon_root / "config"
    _, policy_hash = verifier.load_policy(config_dir / "omega_policy_ir_v1.json")
    registry, registry_hash = verifier.load_registry(config_dir / "omega_capability_registry_v2.json")
    _, objectives_hash = verifier.load_objectives(config_dir / "omega_objectives_v1.json")

    snapshot = load_json(latest_file(state_dir / "snapshot", "sha256_*.omega_tick_snapshot_v1.json"))
    obs_hash_hex = str(snapshot["observation_report_hash"]).split(":", 1)[1]
    obs_payload = load_json(state_dir / "observations" / f"sha256_{obs_hash_hex}.omega_observation_report_v1.json")

    tampered_obs = deepcopy(obs_payload)
    hard_task_suite = tampered_obs.get("hard_task_suite_v1")
    assert isinstance(hard_task_suite, dict)
    hard_task_suite["suite_hash"] = "sha256:" + ("0" * 64)

    prev_observation = verifier._find_prev_observation_report(  # noqa: SLF001
        state_root=state_dir,
        current_tick_u64=int(tampered_obs.get("tick_u64", 0)),
    )
    if prev_observation is None:
        prev_observation = verifier._derive_prev_observation_from_payload(tampered_obs)  # noqa: SLF001

    exclude_run_dir = daemon_root.parent.parent if daemon_root.parent.name == "daemon" else None
    recomputed = verifier._recompute_observation_from_sources(  # noqa: SLF001
        root=verifier._repo_root(),  # noqa: SLF001
        runs_roots=verifier._observer_runs_roots(  # noqa: SLF001
            root=verifier._repo_root(),  # noqa: SLF001
            daemon_root=daemon_root,
        ),
        observation_payload=tampered_obs,
        registry=registry,
        policy_hash=policy_hash,
        registry_hash=registry_hash,
        objectives_hash=objectives_hash,
        prev_observation=prev_observation,
        exclude_run_dir=exclude_run_dir,
        exclude_after_or_equal_tick_u64=int(tampered_obs.get("tick_u64", 0)),
    )

    assert canon_hash_obj(recomputed) != canon_hash_obj(tampered_obs)
