"""Persistent verifier worker for omega daemon v18.0.

Protocol: JSONL over stdin/stdout.
"""

from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path
from typing import Any

from .omega_common_v1 import OmegaV18Error, canon_hash_obj, fail
from . import verify_rsi_omega_daemon_v1 as verifier_module


class VerifierWorker:
    """Stateful verifier wrapper with in-memory memoized short-circuits."""

    def __init__(self) -> None:
        self._observation_cache: dict[str, str] = {}
        self._diagnose_cache: dict[str, str] = {}
        self._decide_cache: dict[str, str] = {}

        self._current_obs_payload: dict[str, Any] | None = None
        self._current_issue_payload: dict[str, Any] | None = None
        self._current_decision_payload: dict[str, Any] | None = None

    def _reset_request_payloads(self) -> None:
        self._current_obs_payload = None
        self._current_issue_payload = None
        self._current_decision_payload = None

    def _capture_payload(self, schema_name: str, payload: dict[str, Any]) -> None:
        if schema_name == "omega_observation_report_v1":
            self._current_obs_payload = payload
        elif schema_name == "omega_issue_bundle_v1":
            self._current_issue_payload = payload
        elif schema_name == "omega_decision_plan_v1":
            self._current_decision_payload = payload

    def verify(self, state_dir: Path, *, mode: str = "full") -> str:
        self._reset_request_payloads()

        original_verify_hash_binding = verifier_module._verify_hash_binding
        original_recompute_observation = verifier_module._recompute_observation_from_sources
        original_diagnose = verifier_module.diagnose
        original_decide = verifier_module.decide
        try:
            recompute_params = inspect.signature(original_recompute_observation).parameters
        except (TypeError, ValueError):
            fail("SCHEMA_FAIL")
        recompute_supports_registry = "registry" in recompute_params
        recompute_supports_exclude_run_dir = "exclude_run_dir" in recompute_params
        recompute_supports_exclude_tick = "exclude_after_or_equal_tick_u64" in recompute_params
        if "registry_hash" not in recompute_params:
            fail("SCHEMA_FAIL")

        def _verify_hash_binding_wrapper(path: Path, expected_hash: str, schema_name: str) -> dict[str, Any]:
            payload = original_verify_hash_binding(path, expected_hash, schema_name)
            self._capture_payload(schema_name, payload)
            return payload

        def _recompute_observation_wrapper(
            *,
            root: Path,
            runs_roots: list[Path] | None,
            observation_payload: dict[str, Any],
            registry: dict[str, Any] | None = None,
            policy_hash: str,
            registry_hash: str,
            objectives_hash: str,
            prev_observation: dict[str, Any] | None = None,
            exclude_run_dir: Path | None = None,
            exclude_after_or_equal_tick_u64: int | None = None,
        ) -> dict[str, Any]:
            if registry is not None and not isinstance(registry, dict):
                fail("SCHEMA_FAIL")
            if exclude_run_dir is not None and not isinstance(exclude_run_dir, Path):
                fail("SCHEMA_FAIL")
            if exclude_after_or_equal_tick_u64 is not None:
                try:
                    int(exclude_after_or_equal_tick_u64)
                except Exception:  # noqa: BLE001
                    fail("SCHEMA_FAIL")
            key = canon_hash_obj(
                {
                    "sources": observation_payload.get("sources"),
                    "policy_hash": policy_hash,
                    "registry_hash": registry_hash,
                    "objectives_hash": objectives_hash,
                    "runs_roots": [str(path) for path in (runs_roots or [])],
                    "prev_observation_hash": canon_hash_obj(prev_observation) if isinstance(prev_observation, dict) else "",
                    "exclude_run_dir": str(exclude_run_dir) if exclude_run_dir is not None else "",
                    "exclude_after_or_equal_tick_u64": (
                        int(exclude_after_or_equal_tick_u64) if exclude_after_or_equal_tick_u64 is not None else None
                    ),
                }
            )
            expected_obs_hash = canon_hash_obj(observation_payload)
            cached_obs_hash = self._observation_cache.get(key)
            if cached_obs_hash is not None and cached_obs_hash == expected_obs_hash:
                return observation_payload

            # Fail closed: cache mismatch triggers full recompute.
            recompute_kwargs: dict[str, Any] = {
                "root": root,
                "runs_roots": runs_roots,
                "observation_payload": observation_payload,
                "policy_hash": policy_hash,
                "registry_hash": registry_hash,
                "objectives_hash": objectives_hash,
                "prev_observation": prev_observation,
            }
            if recompute_supports_exclude_run_dir:
                recompute_kwargs["exclude_run_dir"] = exclude_run_dir
            if recompute_supports_exclude_tick:
                recompute_kwargs["exclude_after_or_equal_tick_u64"] = exclude_after_or_equal_tick_u64
            if recompute_supports_registry:
                if registry is None:
                    fail("SCHEMA_FAIL")
                recompute_kwargs["registry"] = registry
            recomputed = original_recompute_observation(**recompute_kwargs)
            recomputed_hash = canon_hash_obj(recomputed)
            if recomputed_hash != expected_obs_hash:
                fail("NONDETERMINISTIC")
            self._observation_cache[key] = expected_obs_hash
            return recomputed

        def _diagnose_wrapper(
            *,
            tick_u64: int,
            observation_report: dict[str, Any],
            objectives: dict[str, Any],
        ) -> tuple[dict[str, Any], str]:
            objectives_hash = canon_hash_obj(objectives)
            obs_hash = canon_hash_obj(observation_report)
            key = canon_hash_obj(
                {
                    "obs_hash": obs_hash,
                    "objectives_hash": objectives_hash,
                }
            )
            expected_issue_payload = self._current_issue_payload
            cached_issue_hash = self._diagnose_cache.get(key)
            if cached_issue_hash is not None and isinstance(expected_issue_payload, dict):
                if canon_hash_obj(expected_issue_payload) == cached_issue_hash:
                    return expected_issue_payload, cached_issue_hash

            # Fail closed: cache mismatch triggers full recompute.
            issue_payload, issue_hash = original_diagnose(
                tick_u64=tick_u64,
                observation_report=observation_report,
                objectives=objectives,
            )
            if isinstance(expected_issue_payload, dict) and canon_hash_obj(expected_issue_payload) != issue_hash:
                fail("NONDETERMINISTIC")
            self._diagnose_cache[key] = issue_hash
            return issue_payload, issue_hash

        def _decide_wrapper(*args: Any, **kwargs: Any) -> tuple[dict[str, Any], str]:
            decision_payload = self._current_decision_payload
            inputs_hash = ""
            if isinstance(decision_payload, dict):
                proof = decision_payload.get("recompute_proof")
                if isinstance(proof, dict):
                    inputs_hash = str(proof.get("inputs_hash", "")).strip()

            cached_plan_hash = self._decide_cache.get(inputs_hash) if inputs_hash else None
            if (
                cached_plan_hash is not None
                and isinstance(decision_payload, dict)
                and str(decision_payload.get("plan_id", "")).strip() == cached_plan_hash
            ):
                return decision_payload, canon_hash_obj(decision_payload)

            # Fail closed: cache mismatch triggers full recompute.
            decision_plan, decision_hash = original_decide(*args, **kwargs)
            if isinstance(decision_payload, dict):
                if canon_hash_obj(decision_plan) != canon_hash_obj(decision_payload):
                    fail("NONDETERMINISTIC")
            if inputs_hash:
                self._decide_cache[inputs_hash] = str(decision_plan.get("plan_id", ""))
            return decision_plan, decision_hash

        verifier_module._verify_hash_binding = _verify_hash_binding_wrapper
        verifier_module._recompute_observation_from_sources = _recompute_observation_wrapper
        verifier_module.diagnose = _diagnose_wrapper
        verifier_module.decide = _decide_wrapper
        try:
            return verifier_module.verify(Path(state_dir), mode=mode)
        finally:
            verifier_module._verify_hash_binding = original_verify_hash_binding
            verifier_module._recompute_observation_from_sources = original_recompute_observation
            verifier_module.diagnose = original_diagnose
            verifier_module.decide = original_decide
            self._reset_request_payloads()

    def handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        op = str(request.get("op", "")).strip().upper()
        if op != "VERIFY":
            return {
                "ok": False,
                "reason": "SCHEMA_FAIL",
                "detail": "unsupported op",
            }

        state_dir_raw = request.get("state_dir")
        if not isinstance(state_dir_raw, str) or not state_dir_raw.strip():
            return {
                "ok": False,
                "reason": "SCHEMA_FAIL",
                "detail": "missing state_dir",
            }
        mode = str(request.get("mode", "full")).strip() or "full"

        try:
            verdict = self.verify(Path(state_dir_raw), mode=mode)
            return {
                "ok": True,
                "verdict": verdict,
            }
        except OmegaV18Error as exc:
            message = str(exc)
            reason = "VERIFY_ERROR"
            if message.startswith("INVALID:"):
                tail = message.split(":", 1)[1]
                reason = tail.split(":", 1)[0] if tail else "VERIFY_ERROR"
            return {
                "ok": False,
                "reason": reason,
                "detail": message,
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "reason": "VERIFY_ERROR",
                "detail": str(exc),
            }


def _write_response(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def main() -> None:
    worker = VerifierWorker()
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except Exception as exc:  # noqa: BLE001
            _write_response(
                {
                    "ok": False,
                    "reason": "SCHEMA_FAIL",
                    "detail": f"invalid json: {exc}",
                }
            )
            continue
        if not isinstance(request, dict):
            _write_response(
                {
                    "ok": False,
                    "reason": "SCHEMA_FAIL",
                    "detail": "request must be object",
                }
            )
            continue
        _write_response(worker.handle_request(request))


if __name__ == "__main__":
    main()
