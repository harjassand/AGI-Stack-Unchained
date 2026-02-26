from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cdel.v1_7r.canon import canon_bytes
from cdel.v18_0.eudrs_u.dmpl_config_load_v1 import load_runtime_from_droot_v1
from cdel.v18_0.eudrs_u import dmpl_planner_dcbts_l_v1 as dmpl_planner_dcbts_l_v1_mod
from cdel.v18_0.eudrs_u.dmpl_train_sgd_v1 import encode_tensor_q32_v1
from cdel.v18_0.omega_common_v1 import validate_schema as validate_schema_v18

from tools.ttc_grpo.candidate_store_v1 import CandidateStore


class DmplEvalHarnessError(RuntimeError):
    pass


def _fail(reason: str) -> None:
    raise DmplEvalHarnessError(str(reason).strip() or "DMPL_EVAL_FAIL")


def _sha256_prefixed(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _derive_sha(*parts: str) -> str:
    payload = {"schema_id": "ttc_grpo_hash_material_v1", "parts": [str(p) for p in parts]}
    return _sha256_prefixed(canon_bytes(payload))


def _synthetic_action_receipt(*, candidate_ir_hash: str, reward_q32: int, budget: dict[str, int]) -> dict[str, Any]:
    node_id = _derive_sha("node", candidate_ir_hash)
    receipt = {
        "schema_id": "dmpl_action_receipt_v1",
        "dc1_id": "dc1:q32_v1",
        "opset_id": "opset:eudrs_u_v1:" + _derive_sha("opset", candidate_ir_hash),
        "plan_query_id": _derive_sha("plan_query", candidate_ir_hash),
        "rollout_trace_id": _derive_sha("rollout", candidate_ir_hash),
        "chosen_action_record_id": _derive_sha("action_record", candidate_ir_hash),
        "chosen_action_hash": _derive_sha("action_hash", candidate_ir_hash),
        "chosen_node_id": node_id,
        "tie_break_proof": {
            "ordering_policy": {
                "primary_key_id": "upper_bound_primary_score_desc",
                "secondary_key_id": "depth_asc",
                "tertiary_key_id": "node_id_asc",
            },
            "ordering_keys": [
                {
                    "candidate_rank_u32": 0,
                    "node_id": node_id,
                    "bound_score_q32": {"q": int(reward_q32)},
                    "depth_u32": 0,
                }
            ],
            "proof_digest": _derive_sha("proof", candidate_ir_hash),
        },
        "ufc_decomposition": {
            "schema_id": "dmpl_ufc_decomposition_v1",
            "terms": {},
        },
        "gating_summary": {
            "caps_digest": _derive_sha("caps", candidate_ir_hash),
            "K_ctx_u32": int(max(1, min(int(budget.get("beam_width_u64", 1)), (1 << 32) - 1))),
            "K_g_u32": int(max(1, min(int(budget.get("beam_width_u64", 1)), (1 << 32) - 1))),
            "inverse_head_enabled_b": False,
            "rev_err_max_q32": {"q": 0},
            "planner_budget_summary": {
                "nodes_u32": int(max(1, min(int(budget.get("max_nodes_u64", 1)), (1 << 32) - 1))),
                "ops_u64": int(max(1, int(budget.get("max_nodes_u64", 1)))),
                "bytes_u64": int(max(1, int(budget.get("beam_width_u64", 1)) * 1024)),
            },
            "status": {"ok_b": True, "reason_code": "DMPL_OK"},
        },
    }
    validate_schema_v18(receipt, "dmpl_action_receipt_v1")
    return receipt


class _PlannerArtifactWriter:
    def __init__(self, out_root: Path) -> None:
        self.out_root = Path(out_root).resolve()
        self._cache: dict[tuple[str, str, str], bytes] = {}

    def _write(self, *, artifact_type: str, ext: str, raw: bytes) -> str:
        digest = _sha256_prefixed(bytes(raw))
        out_dir = self.out_root / str(artifact_type)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"sha256_{digest.split(':', 1)[1]}.{artifact_type}.{ext}"
        if out_path.exists():
            existing = out_path.read_bytes()
            if existing != bytes(raw):
                _fail("NONDETERMINISTIC")
        else:
            out_path.write_bytes(bytes(raw))
        self._cache[(digest, str(artifact_type), str(ext))] = bytes(raw)
        return digest

    def write_json_artifact(self, artifact_type: str, obj: Any) -> str:
        if not isinstance(obj, dict):
            _fail("SCHEMA_FAIL")
        return self._write(artifact_type=str(artifact_type), ext="json", raw=canon_bytes(obj))

    def write_bin_artifact(self, artifact_type: str, raw: bytes) -> str:
        return self._write(artifact_type=str(artifact_type), ext="bin", raw=bytes(raw))


class _PlannerResolver:
    def __init__(self, *, roots: list[Path], writer: _PlannerArtifactWriter) -> None:
        self._roots = [Path(row).resolve() for row in roots]
        self._writer = writer

    def load_artifact_bytes(self, *, artifact_id: str, artifact_type: str, ext: str) -> bytes:
        key = (str(artifact_id), str(artifact_type), str(ext))
        cached = self._writer._cache.get(key)
        if cached is not None:
            return bytes(cached)

        expected_name = f"sha256_{str(artifact_id).split(':', 1)[1]}.{artifact_type}.{ext}"
        matches: list[Path] = []
        for root in self._roots:
            if not root.exists() or not root.is_dir():
                continue
            matches.extend([p for p in root.rglob(expected_name) if p.is_file()])
        if len(matches) != 1:
            _fail("MISSING_STATE_INPUT")
        return matches[0].read_bytes()


@dataclass(slots=True)
class DmplEvalHarnessV1:
    store: CandidateStore
    dmpl_campaign_id: str
    reward_from_cac_field: str
    budget: dict[str, int]
    require_real_dmpl_b: bool = False
    droot_id: str | None = None
    artifact_roots: tuple[Path, ...] = ()
    _runtime: Any | None = field(init=False, default=None)
    _planner_writer: _PlannerArtifactWriter = field(init=False)
    _planner_resolver: _PlannerResolver = field(init=False)

    def __post_init__(self) -> None:
        env_droot = str(os.environ.get("TTC_GRPO_DMPL_DROOT_ID", "")).strip()
        if not self.droot_id and env_droot:
            self.droot_id = env_droot

        if not self.artifact_roots:
            env_roots = [row.strip() for row in str(os.environ.get("TTC_GRPO_DMPL_ARTIFACT_ROOTS", "")).split(":") if row.strip()]
            rows = [Path(row).resolve() for row in env_roots]
            default_stage = (Path(__file__).resolve().parents[2] / "runs" / "eudrs_u_bootstrap_dmpl_plan" / "daemon" / "rsi_eudrs_u_dmpl_plan_v1" / "state").resolve()
            if default_stage.exists() and default_stage.is_dir():
                rows.append(default_stage)
            self.artifact_roots = tuple(rows)

        self._planner_writer = _PlannerArtifactWriter(self.store.plan_dir)
        self._planner_resolver = _PlannerResolver(roots=list(self.artifact_roots) + [self.store.plan_dir], writer=self._planner_writer)

    def _discover_droot_id(self) -> str | None:
        if self.droot_id:
            return str(self.droot_id)
        matches: list[Path] = []
        for root in self.artifact_roots:
            if not root.exists() or not root.is_dir():
                continue
            matches.extend(sorted(root.rglob("sha256_*.dmpl_droot_v1.json"), key=lambda p: p.as_posix()))
        if not matches:
            return None
        return "sha256:" + matches[-1].name.split(".", 1)[0].split("_", 1)[1]

    def _load_runtime_if_available(self) -> Any | None:
        if self._runtime is not None:
            return self._runtime
        droot_id = self._discover_droot_id()
        if not droot_id:
            return None
        try:
            self._runtime = load_runtime_from_droot_v1(droot_id=droot_id, resolver=self._planner_resolver)
        except Exception:
            return None
        return self._runtime

    def _reward_from_receipt(self, action_receipt_obj: dict[str, Any]) -> int:
        try:
            return int(
                (((action_receipt_obj.get("tie_break_proof") or {}).get("ordering_keys") or [])[0].get("bound_score_q32") or {}).get("q", 0)
            )
        except Exception:
            return 0

    def _synthetic_reward_q32(self, *, candidate_ir_hash: str, tick_u64: int, candidate_index_u64: int, seed_u64: int) -> int:
        material = {
            "schema_id": "ttc_grpo_synth_reward_v1",
            "candidate_ir_hash": str(candidate_ir_hash),
            "tick_u64": int(tick_u64),
            "candidate_index_u64": int(candidate_index_u64),
            "seed_u64": int(seed_u64),
        }
        digest = hashlib.sha256(canon_bytes(material)).digest()
        raw = int.from_bytes(digest[:8], "big", signed=False)
        return int((raw & 0x7FFFFFFF) << 1)

    def _write_cac(self, *, candidate_ir_hash: str, plan_hash: str, reward_q32: int, mode: str) -> tuple[str, int]:
        reward_field = str(self.reward_from_cac_field).strip()
        if not reward_field:
            _fail("SCHEMA_FAIL:reward_from_cac_field")
        cac_obj = {
            "schema_id": "cac_v1",
            "campaign_id": str(self.dmpl_campaign_id),
            "planner_mode": str(mode),
            "candidate_ir_hash": str(candidate_ir_hash),
            "dmpl_plan_result_hash": str(plan_hash),
            "total_advantage_q32": int(reward_q32),
            "reward_source_field": str(reward_field),
            "status": "OK",
            "reason_code": "DMPL_OK",
        }
        if reward_field not in cac_obj:
            _fail("SCHEMA_FAIL:reward_from_cac_field")
        try:
            reward_value = int(cac_obj.get(reward_field))
        except Exception as exc:  # noqa: BLE001
            raise DmplEvalHarnessError("SCHEMA_FAIL:reward_from_cac_field") from exc
        cac_hash = self.store.write_cac(cac_obj)
        return cac_hash, reward_value

    def _evaluate_synthetic(
        self,
        *,
        candidate_ir_hash: str,
        tick_u64: int,
        candidate_index_u64: int,
        seed_u64: int,
    ) -> tuple[str, str, int]:
        reward_q32 = self._synthetic_reward_q32(
            candidate_ir_hash=str(candidate_ir_hash),
            tick_u64=int(tick_u64),
            candidate_index_u64=int(candidate_index_u64),
            seed_u64=int(seed_u64),
        )
        receipt_obj = _synthetic_action_receipt(candidate_ir_hash=str(candidate_ir_hash), reward_q32=int(reward_q32), budget=dict(self.budget))
        plan_hash = self._planner_writer.write_json_artifact("dmpl_action_receipt_v1", receipt_obj)
        cac_hash, reward_value = self._write_cac(candidate_ir_hash=str(candidate_ir_hash), plan_hash=str(plan_hash), reward_q32=int(reward_q32), mode="SYNTHETIC")
        return plan_hash, cac_hash, int(reward_value)

    def _evaluate_real(
        self,
        *,
        candidate_ir_hash: str,
        tick_u64: int,
        candidate_index_u64: int,
        seed_u64: int,
    ) -> tuple[str, str, int] | None:
        runtime = self._load_runtime_if_available()
        if runtime is None:
            return None

        z0 = encode_tensor_q32_v1(dims_u32=[int(runtime.dims.d_u32)], values_i64=[0 for _ in range(int(runtime.dims.d_u32))])
        z0_tensor_id = self._planner_writer.write_bin_artifact("dmpl_tensor_q32_v1", z0)

        start_state_id = _derive_sha("start_state", candidate_ir_hash, str(tick_u64), str(candidate_index_u64))
        plan_query_obj = {
            "schema_id": "dmpl_plan_query_v1",
            "dc1_id": "dc1:q32_v1",
            "opset_id": str(runtime.opset_id),
            "dmpl_droot_id": str(runtime.droot_id),
            "start_state_id": str(start_state_id),
            "z0_tensor_bin_id": str(z0_tensor_id),
            "call_context": {
                "vm_step_u64": int(max(0, int(candidate_index_u64))),
                "scenario_id": f"ttc_grpo_tick_{int(tick_u64)}",
            },
        }
        plan_query_id = self._planner_writer.write_json_artifact("dmpl_plan_query_v1", plan_query_obj)

        try:
            planner_fn = getattr(dmpl_planner_dcbts_l_v1_mod, "dmpl_planner_dcbts_l_v1", None)
            if callable(planner_fn):
                plan_result = planner_fn(
                    runtime=runtime,
                    plan_query_obj=dict(plan_query_obj),
                    resolver=self._planner_resolver,
                    artifact_writer=self._planner_writer,
                )
            else:
                plan_result = dmpl_planner_dcbts_l_v1_mod.plan_call_v1(
                    runtime=runtime,
                    plan_query_obj=dict(plan_query_obj),
                    resolver=self._planner_resolver,
                    artifact_writer=self._planner_writer,
                )
        except Exception:
            return None

        action_receipt_id = str(plan_result.action_receipt_id)
        action_receipt_raw = self._planner_resolver.load_artifact_bytes(
            artifact_id=action_receipt_id,
            artifact_type="dmpl_action_receipt_v1",
            ext="json",
        )
        try:
            import json

            parsed = json.loads(action_receipt_raw.decode("utf-8"))
            if not isinstance(parsed, dict):
                return None
            action_receipt_obj = parsed
        except Exception:
            return None

        reward_q32 = self._reward_from_receipt(action_receipt_obj)
        if str(action_receipt_obj.get("plan_query_id", "")) != str(plan_query_id):
            return None

        cac_hash, reward_value = self._write_cac(
            candidate_ir_hash=str(candidate_ir_hash),
            plan_hash=action_receipt_id,
            reward_q32=int(reward_q32),
            mode="REAL_DMPL",
        )
        return action_receipt_id, cac_hash, int(reward_value)

    def dmpl_eval_candidate_v1(
        self,
        *,
        candidate_ir_hash: str,
        tick_u64: int,
        candidate_index_u64: int,
        seed_u64: int,
    ) -> tuple[str, str, int]:
        real = self._evaluate_real(
            candidate_ir_hash=str(candidate_ir_hash),
            tick_u64=int(tick_u64),
            candidate_index_u64=int(candidate_index_u64),
            seed_u64=int(seed_u64),
        )
        if real is not None:
            return real
        if bool(self.require_real_dmpl_b):
            _fail("DMPL_RUNTIME_UNAVAILABLE")
        return self._evaluate_synthetic(
            candidate_ir_hash=str(candidate_ir_hash),
            tick_u64=int(tick_u64),
            candidate_index_u64=int(candidate_index_u64),
            seed_u64=int(seed_u64),
        )


__all__ = ["DmplEvalHarnessError", "DmplEvalHarnessV1"]
