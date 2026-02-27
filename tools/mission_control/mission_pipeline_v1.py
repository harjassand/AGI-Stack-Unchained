from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
_CDEL_ROOT = REPO_ROOT / "CDEL-v2"
for _entry in (REPO_ROOT, _CDEL_ROOT):
    _value = str(_entry)
    if _value not in os.sys.path:
        os.sys.path.insert(0, _value)

from cdel.v1_7r.canon import canon_bytes, load_canon_json, sha256_prefixed, write_canon_json, write_jsonl_line
from cdel.v19_0.common_v1 import validate_schema as validate_schema_v19

_BLOB_ROOT_REL = Path("polymath/store/blobs/sha256")
_MC_CACHE_REL = Path(".omega_cache/mission_control")
_MISSIONS_REL = _MC_CACHE_REL / "missions"
_EVENTS_REL = _MC_CACHE_REL / "mission_events.jsonl"
_CURRENT_MISSION_ID_REL = _MC_CACHE_REL / "current_mission_id.txt"

_BUDGET_KEYS = (
    "max_wall_ms_u64",
    "max_cpu_ms_u64",
    "max_steps_u64",
    "max_disk_bytes_u64",
    "max_net_bytes_u64",
)
_DEFAULT_MISSION_BUDGETS = {
    "max_wall_ms_u64": 120_000,
    "max_cpu_ms_u64": 60_000,
    "max_steps_u64": 128,
    "max_disk_bytes_u64": 64 * 1024 * 1024,
    "max_net_bytes_u64": 8 * 1024 * 1024,
}
_DEFAULT_NODE_BUDGETS = {
    "max_wall_ms_u64": 20_000,
    "max_cpu_ms_u64": 10_000,
    "max_steps_u64": 8,
    "max_disk_bytes_u64": 16 * 1024 * 1024,
    "max_net_bytes_u64": 2 * 1024 * 1024,
}


def _repo_root(repo_root: str | Path | None = None) -> Path:
    return Path(repo_root).resolve() if repo_root is not None else REPO_ROOT


def _blob_root(repo_root: str | Path | None = None) -> Path:
    root = _repo_root(repo_root) / _BLOB_ROOT_REL
    root.mkdir(parents=True, exist_ok=True)
    return root


def _mission_cache_root(repo_root: str | Path | None = None) -> Path:
    root = _repo_root(repo_root) / _MC_CACHE_REL
    root.mkdir(parents=True, exist_ok=True)
    return root


def _missions_root(repo_root: str | Path | None = None) -> Path:
    root = _repo_root(repo_root) / _MISSIONS_REL
    root.mkdir(parents=True, exist_ok=True)
    return root


def _events_path(repo_root: str | Path | None = None) -> Path:
    path = _repo_root(repo_root) / _EVENTS_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("", encoding="utf-8")
    return path


def _current_mission_path(repo_root: str | Path | None = None) -> Path:
    path = _repo_root(repo_root) / _CURRENT_MISSION_ID_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _mission_dir(mission_id: str, *, repo_root: str | Path | None = None) -> Path:
    rel = mission_id.split(":", 1)[1]
    path = _missions_root(repo_root) / rel
    path.mkdir(parents=True, exist_ok=True)
    return path


def _mission_index_path(mission_id: str, *, repo_root: str | Path | None = None) -> Path:
    return _mission_dir(mission_id, repo_root=repo_root) / "index.json"


def _mission_state_path(mission_id: str, *, repo_root: str | Path | None = None) -> Path:
    return _mission_dir(mission_id, repo_root=repo_root) / "mission_state_latest.json"


def _hash_bytes(data: bytes) -> str:
    return sha256_prefixed(data)


def canon_content_id(obj: dict[str, Any]) -> str:
    return _hash_bytes(canon_bytes(obj))


def _ensure_sha256_id(value: Any, *, field: str = "id") -> str:
    text = str(value or "")
    if len(text) != 71 or not text.startswith("sha256:"):
        raise RuntimeError(f"INVALID_SHA256:{field}")
    suffix = text.split(":", 1)[1]
    if len(suffix) != 64 or any(ch not in "0123456789abcdef" for ch in suffix):
        raise RuntimeError(f"INVALID_SHA256:{field}")
    return text


def _write_blob_if_missing(path: Path, data: bytes) -> None:
    if path.exists():
        existing = path.read_bytes()
        if hashlib.sha256(existing).hexdigest() != hashlib.sha256(data).hexdigest():
            raise RuntimeError("NONDETERMINISTIC_BLOB_COLLISION")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def store_blob_bytes(data: bytes, *, repo_root: str | Path | None = None) -> str:
    digest = _hash_bytes(data)
    path = _blob_root(repo_root) / digest.split(":", 1)[1]
    _write_blob_if_missing(path, data)
    return digest


def store_json_artifact(obj: dict[str, Any], *, repo_root: str | Path | None = None) -> str:
    data = canon_bytes(obj)
    digest = _hash_bytes(data)
    path = _blob_root(repo_root) / digest.split(":", 1)[1]
    _write_blob_if_missing(path, data)
    return digest


def store_json_artifact_with_forced_id(
    obj: dict[str, Any],
    *,
    forced_content_id: str,
    repo_root: str | Path | None = None,
) -> str:
    digest = _ensure_sha256_id(forced_content_id, field="forced_content_id")
    data = canon_bytes(obj)
    path = _blob_root(repo_root) / digest.split(":", 1)[1]
    _write_blob_if_missing(path, data)
    return digest


def load_artifact(content_id: str, *, repo_root: str | Path | None = None) -> dict[str, Any]:
    digest = _ensure_sha256_id(content_id, field="content_id")
    path = _blob_root(repo_root) / digest.split(":", 1)[1]
    if not path.exists() or not path.is_file():
        raise RuntimeError("MISSING_ARTIFACT")
    payload = load_canon_json(path)
    if not isinstance(payload, dict):
        raise RuntimeError("INVALID_ARTIFACT_PAYLOAD")
    return payload


def artifact_exists(content_id: str, *, repo_root: str | Path | None = None) -> bool:
    try:
        digest = _ensure_sha256_id(content_id, field="content_id")
    except RuntimeError:
        return False
    path = _blob_root(repo_root) / digest.split(":", 1)[1]
    return path.exists() and path.is_file()


@contextmanager
def _schema_env(repo_root: Path):
    prev = os.environ.get("OMEGA_REPO_ROOT")
    os.environ["OMEGA_REPO_ROOT"] = str(repo_root)
    try:
        yield
    finally:
        if prev is None:
            os.environ.pop("OMEGA_REPO_ROOT", None)
        else:
            os.environ["OMEGA_REPO_ROOT"] = prev


def validate_schema(schema_name: str, obj: dict[str, Any], *, repo_root: str | Path | None = None) -> None:
    root = _repo_root(repo_root)
    with _schema_env(root):
        validate_schema_v19(obj, schema_name)


def _normalize_mission_request(mission_request: dict[str, Any]) -> dict[str, Any]:
    payload = dict(mission_request)
    payload.setdefault("schema_name", "mission_request_v1")
    payload.setdefault("schema_version", "v19_0")
    if not isinstance(payload.get("user_prompt"), str) or not str(payload.get("user_prompt", "")).strip():
        prompt = str(payload.get("human_intent_str", "")).strip()
        if not prompt:
            prompt = str(payload.get("notes", "")).strip() or "Mission request"
        payload["user_prompt"] = prompt

    attachments = payload.get("attachments")
    if not isinstance(attachments, list):
        payload["attachments"] = []

    budgets = _normalize_budgets(payload.get("budgets"), fallback=payload.get("budget_caps"))
    payload["budgets"] = budgets
    payload["constraints"] = _normalize_constraints(payload.get("constraints"))
    if isinstance(payload.get("success_spec"), dict):
        payload["success_spec"] = _normalize_success_spec(payload.get("success_spec"))
    else:
        payload.pop("success_spec", None)
    return payload


def _normalize_budgets(raw: Any, *, fallback: Any = None) -> dict[str, int]:
    out: dict[str, int] = dict(_DEFAULT_MISSION_BUDGETS)
    if isinstance(raw, dict):
        for key in _BUDGET_KEYS:
            value = raw.get(key)
            if isinstance(value, int) and value >= 0:
                out[key] = int(value)
    if isinstance(fallback, dict):
        if isinstance(fallback.get("max_disk_bytes_u64"), int):
            out["max_disk_bytes_u64"] = max(0, int(fallback["max_disk_bytes_u64"]))
    return out


def _normalize_constraints(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raw = {}
    out: dict[str, Any] = {
        "allowed_capabilities": [],
        "forbidden_actions": [],
        "forbidden_paths": [],
        "network_mode": "OFF",
    }
    for key in ("allowed_capabilities", "forbidden_actions", "forbidden_paths"):
        value = raw.get(key)
        if isinstance(value, list):
            out[key] = sorted({str(row).strip() for row in value if str(row).strip()})
    mode = str(raw.get("network_mode", out["network_mode"])).strip().upper()
    if mode in {"OFF", "ALLOWLIST_ONLY", "ON"}:
        out["network_mode"] = mode
    return out


def _normalize_success_spec(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raw = {}
    pinned = raw.get("pinned_eval_refs")
    refs: list[dict[str, Any]] = []
    if isinstance(pinned, list):
        for row in pinned:
            if not isinstance(row, dict):
                continue
            suitepack_id = str(row.get("suitepack_id", "")).strip()
            gate_raw = row.get("gate")
            if not suitepack_id or not isinstance(gate_raw, dict):
                continue
            op = str(gate_raw.get("op", "")).strip()
            if op not in {">=", "<=", "=="}:
                continue
            metric = str(gate_raw.get("metric", "")).strip()
            threshold = gate_raw.get("threshold_q32")
            if not metric or not isinstance(threshold, int) or threshold < 0:
                continue
            refs.append(
                {
                    "suitepack_id": suitepack_id,
                    "heldout_b": bool(row.get("heldout_b", True)),
                    "gate": {
                        "metric": metric,
                        "op": op,
                        "threshold_q32": int(threshold),
                    },
                }
            )
    deliverables_raw = raw.get("deliverables")
    deliverables = sorted({str(item).strip() for item in deliverables_raw}) if isinstance(deliverables_raw, list) else []
    deliverables = [item for item in deliverables if item]
    return {
        "definition_of_done": str(raw.get("definition_of_done", "")).strip(),
        "pinned_eval_refs": refs,
        "deliverables": deliverables,
    }


def _next_tick() -> int:
    return int(time.time() * 1000)


def _append_event(
    *,
    event_type: str,
    mission_id: str,
    payload: dict[str, Any] | None = None,
    tick_u64: int | None = None,
    repo_root: str | Path | None = None,
) -> None:
    body = {
        "event_type": str(event_type),
        "tick_u64": int(tick_u64 if tick_u64 is not None else _next_tick()),
        "mission_id": mission_id,
        "payload": dict(payload or {}),
    }
    write_jsonl_line(_events_path(repo_root), body)


def _mission_index(mission_id: str, *, repo_root: str | Path | None = None) -> dict[str, Any]:
    path = _mission_index_path(mission_id, repo_root=repo_root)
    if not path.exists():
        return {}
    payload = load_canon_json(path)
    if not isinstance(payload, dict):
        return {}
    return payload


def _write_mission_index(mission_id: str, payload: dict[str, Any], *, repo_root: str | Path | None = None) -> None:
    path = _mission_index_path(mission_id, repo_root=repo_root)
    write_canon_json(path, payload)


def _set_current_mission_id(mission_id: str, *, repo_root: str | Path | None = None) -> None:
    path = _current_mission_path(repo_root)
    path.write_text(mission_id + "\n", encoding="utf-8")


def _load_current_mission_id(*, repo_root: str | Path | None = None) -> str | None:
    path = _current_mission_path(repo_root)
    if not path.exists() or not path.is_file():
        return None
    mission_id = path.read_text(encoding="utf-8").strip()
    if not mission_id:
        return None
    try:
        return _ensure_sha256_id(mission_id, field="mission_id")
    except RuntimeError:
        return None


def capture_manifest(
    mission_request: dict[str, Any],
    *,
    attachment_files: list[dict[str, Any]] | None = None,
    repo_root: str | Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    root = _repo_root(repo_root)
    req = _normalize_mission_request(mission_request)
    files = list(attachment_files or [])

    existing_attachments = req.get("attachments")
    normalized_attachments: list[dict[str, Any]] = []
    if isinstance(existing_attachments, list):
        for row in existing_attachments:
            if not isinstance(row, dict):
                continue
            normalized_attachments.append(
                {
                    "content_id": str(row.get("content_id", "")).strip() or None,
                    "filename": str(row.get("filename", "attachment.bin")),
                    "mime": str(row.get("mime", "application/octet-stream")),
                    "size_bytes_u64": int(row.get("size_bytes_u64", 0)) if isinstance(row.get("size_bytes_u64"), int) else 0,
                }
            )

    for idx, file_row in enumerate(files):
        data = file_row.get("data")
        if not isinstance(data, (bytes, bytearray)):
            continue
        content_id = store_blob_bytes(bytes(data), repo_root=root)
        filename = str(file_row.get("filename", f"attachment_{idx}.bin"))
        mime = str(file_row.get("mime", "application/octet-stream"))
        normalized_attachments.append(
            {
                "content_id": content_id,
                "filename": filename,
                "mime": mime,
                "size_bytes_u64": len(data),
            }
        )

    req["attachments"] = normalized_attachments

    validate_schema("mission_request_v1", req, repo_root=root)
    mission_request_content_id = store_json_artifact(req, repo_root=root)

    prompt_bytes = str(req.get("user_prompt", "")).encode("utf-8")
    prompt_content_id = store_blob_bytes(prompt_bytes, repo_root=root)

    inputs: list[dict[str, Any]] = [
        {
            "role": "USER_PROMPT",
            "content_id": prompt_content_id,
            "size_bytes_u64": len(prompt_bytes),
        }
    ]

    for row in normalized_attachments:
        content_id = row.get("content_id")
        if not isinstance(content_id, str) or not content_id:
            continue
        _ensure_sha256_id(content_id, field="attachment.content_id")
        inputs.append(
            {
                "role": "ATTACHMENT",
                "content_id": content_id,
                "filename": str(row.get("filename", "")),
                "mime": str(row.get("mime", "")),
                "size_bytes_u64": int(row.get("size_bytes_u64", 0)),
            }
        )

    manifest_no_id = {
        "schema_version": "mission_input_manifest_v1",
        "mission_request_content_id": mission_request_content_id,
        "inputs": inputs,
        "notes": {"ingestion_policy_id": "mission_control_default_v1"},
    }
    manifest = dict(manifest_no_id)
    manifest["manifest_id"] = canon_content_id(manifest_no_id)
    validate_schema("mission_input_manifest_v1", manifest, repo_root=root)
    store_json_artifact(manifest, repo_root=root)
    store_json_artifact_with_forced_id(
        manifest,
        forced_content_id=manifest["manifest_id"],
        repo_root=root,
    )
    return req, manifest


def _stable_text_hash(prefix: str, text: str) -> str:
    return sha256_prefixed(canon_bytes({"prefix": prefix, "text": text}))


def build_intent_graph(
    mission_request: dict[str, Any],
    manifest: dict[str, Any],
    *,
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    root = _repo_root(repo_root)
    mission_request_content_id = _ensure_sha256_id(store_json_artifact(mission_request, repo_root=root), field="mission_request_content_id")
    manifest_id = _ensure_sha256_id(manifest.get("manifest_id"), field="manifest_id")

    prompt = str(mission_request.get("user_prompt", "")).strip()
    success_spec = mission_request.get("success_spec")
    constraints = mission_request.get("constraints")

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    clarifications: list[dict[str, Any]] = []

    intent_id = _stable_text_hash("intent", prompt)
    nodes.append(
        {
            "intent_node_id": intent_id,
            "kind": "INTENT",
            "text": prompt,
            "confidence_q32": 4294967295,
            "canonical_fields": {"user_prompt": prompt},
        }
    )

    if isinstance(constraints, dict):
        for key in ("forbidden_actions", "forbidden_paths", "allowed_capabilities"):
            values = constraints.get(key)
            if isinstance(values, list) and values:
                node_id = _stable_text_hash("constraint", key + ":" + "|".join(sorted(str(v) for v in values)))
                nodes.append(
                    {
                        "intent_node_id": node_id,
                        "kind": "CONSTRAINT",
                        "text": key,
                        "confidence_q32": 3800000000,
                        "canonical_fields": {key: sorted(str(v) for v in values)},
                    }
                )
                edges.append(
                    {
                        "src": intent_id,
                        "dst": node_id,
                        "rel": "REFINES",
                        "confidence_q32": 3800000000,
                    }
                )

    pinned_eval_refs: list[dict[str, Any]] = []
    if isinstance(success_spec, dict):
        eval_refs = success_spec.get("pinned_eval_refs")
        if isinstance(eval_refs, list):
            for row in eval_refs:
                if not isinstance(row, dict):
                    continue
                suitepack_id = str(row.get("suitepack_id", "")).strip()
                if not suitepack_id:
                    continue
                pinned_eval_refs.append(row)
                node_id = _stable_text_hash("eval_ref", suitepack_id)
                nodes.append(
                    {
                        "intent_node_id": node_id,
                        "kind": "EVAL_REF",
                        "text": suitepack_id,
                        "confidence_q32": 4200000000,
                        "canonical_fields": row,
                    }
                )
                edges.append(
                    {
                        "src": intent_id,
                        "dst": node_id,
                        "rel": "DEPENDS_ON",
                        "confidence_q32": 4200000000,
                    }
                )

        definition_of_done = str(success_spec.get("definition_of_done", "")).strip()
        if not definition_of_done:
            clarifications.append(
                {
                    "clarification_id": _stable_text_hash("clarification", "definition_of_done"),
                    "path": "/success_spec/definition_of_done",
                    "question": "Define completion criteria for this mission.",
                    "expected_type": "string",
                    "blocking_b": True,
                }
            )
    else:
        clarifications.append(
            {
                "clarification_id": _stable_text_hash("clarification", "success_spec"),
                "path": "/success_spec",
                "question": "Provide success_spec with pinned evaluation references.",
                "expected_type": "object",
                "blocking_b": True,
            }
        )

    if not pinned_eval_refs:
        clarifications.append(
            {
                "clarification_id": _stable_text_hash("clarification", "pinned_eval_refs"),
                "path": "/success_spec/pinned_eval_refs",
                "question": "Add at least one pinned eval reference for mission gates.",
                "expected_type": "array",
                "blocking_b": True,
            }
        )

    primary_branch_no_id = {
        "title": "Primary interpretation",
        "summary": "Direct execution path from prompt, constraints, and pinned eval refs.",
        "selected_node_ids": sorted(node["intent_node_id"] for node in nodes),
        "assumptions": ["Use deterministic default execution template."],
        "confidence_q32": 4000000000,
    }
    primary_branch_id = canon_content_id(primary_branch_no_id)
    primary_branch = dict(primary_branch_no_id)
    primary_branch["branch_id"] = primary_branch_id

    conservative_branch_no_id = {
        "title": "Conservative interpretation",
        "summary": "Bias toward minimal-risk synthesis before patch/eval gates.",
        "selected_node_ids": [intent_id],
        "assumptions": ["Prefer read-mostly execution if ambiguity remains."],
        "confidence_q32": 3200000000,
    }
    conservative_branch_id = canon_content_id(conservative_branch_no_id)
    conservative_branch = dict(conservative_branch_no_id)
    conservative_branch["branch_id"] = conservative_branch_id

    branches = [primary_branch, conservative_branch]
    branches.sort(key=lambda row: (-int(row["confidence_q32"]), str(row["branch_id"])))

    intent_no_id = {
        "schema_version": "mission_intent_graph_v1",
        "mission_request_content_id": mission_request_content_id,
        "manifest_id": manifest_id,
        "nodes": nodes,
        "edges": edges,
        "branches": branches,
        "required_clarifications": clarifications,
    }
    intent = dict(intent_no_id)
    intent["intent_graph_id"] = canon_content_id(intent_no_id)
    validate_schema("mission_intent_graph_v1", intent, repo_root=root)
    store_json_artifact(intent, repo_root=root)
    store_json_artifact_with_forced_id(
        intent,
        forced_content_id=intent["intent_graph_id"],
        repo_root=root,
    )
    return intent


def _select_branch(intent_graph: dict[str, Any], selected_branch_id: str | None = None) -> tuple[str, str]:
    branches = intent_graph.get("branches")
    if not isinstance(branches, list) or not branches:
        raise RuntimeError("MISSION_BRANCHES_EMPTY")
    valid_ids = [str(row.get("branch_id", "")) for row in branches if isinstance(row, dict)]
    if selected_branch_id:
        if selected_branch_id not in valid_ids:
            raise RuntimeError("MISSION_BRANCH_NOT_FOUND")
        return selected_branch_id, "EXPLICIT"
    best = sorted(
        (row for row in branches if isinstance(row, dict)),
        key=lambda row: (-int(row.get("confidence_q32", 0)), str(row.get("branch_id", ""))),
    )[0]
    return str(best["branch_id"]), "AUTO_HIGHEST_CONFIDENCE_LEX"


def _node_id_from_spec(node_spec: dict[str, Any]) -> str:
    no_id = dict(node_spec)
    no_id.pop("node_id", None)
    return canon_content_id(no_id)


def _new_gate(gate_id: str, gate_type: str, params: dict[str, Any]) -> dict[str, Any]:
    return {
        "gate_id": gate_id,
        "gate_type": gate_type,
        "params": params,
        "fail_closed_b": True,
    }


def _template_nodes(
    *,
    mission_request_content_id: str,
    manifest_id: str,
    intent_graph_id: str,
    prompt: str,
    success_spec: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    eval_refs = success_spec.get("pinned_eval_refs") if isinstance(success_spec, dict) else []
    eval_refs = eval_refs if isinstance(eval_refs, list) else []

    base_nodes: list[dict[str, Any]] = [
        {
            "node_type": "INGEST",
            "name": "Capture mission inputs",
            "inputs": [
                {"role": "mission_request", "content_id": mission_request_content_id},
                {"role": "manifest", "content_id": manifest_id},
            ],
            "outputs_expected": [
                {"role": "ingest_receipt", "schema_version": "mission_ingest_artifact_v1", "required_b": True}
            ],
            "gates": [_new_gate("gate_ingest_schema", "SCHEMA", {"schema": "mission_input_manifest_v1"})],
            "budgets": dict(_DEFAULT_NODE_BUDGETS),
            "executor": {"executor_kind": "SCRIPT", "ref": {"node_handler": "INGEST"}},
        },
        {
            "node_type": "SYNTHESIZE",
            "name": "Synthesize mission strategy",
            "inputs": [
                {"role": "mission_request", "content_id": mission_request_content_id},
                {"role": "intent_graph", "content_id": intent_graph_id},
            ],
            "outputs_expected": [
                {"role": "solution_bundle", "schema_version": "mission_solution_bundle_v1", "required_b": True}
            ],
            "gates": [
                _new_gate("gate_synth_budget", "BUDGET", {"policy": "HARD_FAIL"}),
                _new_gate("gate_synth_policy", "POLICY", {"network_mode": "OFF"}),
            ],
            "budgets": dict(_DEFAULT_NODE_BUDGETS),
            "executor": {"executor_kind": "SCRIPT", "ref": {"node_handler": "SYNTHESIZE"}},
        },
    ]

    if any(token in prompt.lower() for token in ("patch", "fix", "refactor", "edit", "code")):
        base_nodes.append(
            {
                "node_type": "PATCH",
                "name": "Generate candidate patch plan",
                "inputs": [{"role": "solution_bundle", "content_id": mission_request_content_id}],
                "outputs_expected": [
                    {"role": "patch_plan", "schema_version": "mission_patch_plan_v1", "required_b": True}
                ],
                "gates": [
                    _new_gate("gate_patch_policy", "POLICY", {"require_ccap_receipt": True}),
                    _new_gate("gate_patch_regression", "NO_REGRESSION", {"policy": "strict"}),
                ],
                "budgets": dict(_DEFAULT_NODE_BUDGETS),
                "executor": {"executor_kind": "SCRIPT", "ref": {"node_handler": "PATCH"}},
            }
        )

    base_nodes.extend(
        [
            {
                "node_type": "EVAL",
                "name": "Run pinned mission gates",
                "inputs": [{"role": "intent_graph", "content_id": intent_graph_id}],
                "outputs_expected": [{"role": "eval_report", "schema_version": "eval_report_v1", "required_b": True}],
                "gates": [_new_gate("gate_eval", "EVAL", {"pinned_eval_refs": eval_refs})],
                "budgets": dict(_DEFAULT_NODE_BUDGETS),
                "executor": {"executor_kind": "SCRIPT", "ref": {"node_handler": "EVAL"}},
            },
            {
                "node_type": "WRITEUP",
                "name": "Produce evidence-linked mission writeup",
                "inputs": [{"role": "eval_report", "content_id": intent_graph_id}],
                "outputs_expected": [{"role": "writeup", "schema_version": "mission_writeup_v1", "required_b": True}],
                "gates": [_new_gate("gate_writeup_schema", "SCHEMA", {"schema": "mission_node_result_v1"})],
                "budgets": dict(_DEFAULT_NODE_BUDGETS),
                "executor": {"executor_kind": "SCRIPT", "ref": {"node_handler": "WRITEUP"}},
            },
        ]
    )

    nodes: list[dict[str, Any]] = []
    for row in base_nodes:
        node = dict(row)
        node["node_id"] = _node_id_from_spec(node)
        nodes.append(node)

    edges: list[dict[str, Any]] = []
    for idx in range(len(nodes) - 1):
        edges.append({"src": nodes[idx]["node_id"], "dst": nodes[idx + 1]["node_id"], "kind": "CONTROL"})
    return nodes, edges


def _topological_depths(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, int]:
    ids = [str(row["node_id"]) for row in nodes]
    preds: dict[str, set[str]] = {node_id: set() for node_id in ids}
    succs: dict[str, set[str]] = {node_id: set() for node_id in ids}
    for edge in edges:
        src = str(edge["src"])
        dst = str(edge["dst"])
        if src not in preds or dst not in preds:
            raise RuntimeError("MISSION_GRAPH_EDGE_UNKNOWN_NODE")
        preds[dst].add(src)
        succs[src].add(dst)

    queue = sorted([node_id for node_id, row in preds.items() if not row])
    depth: dict[str, int] = {node_id: 0 for node_id in queue}
    visited: list[str] = []
    while queue:
        current = queue.pop(0)
        visited.append(current)
        current_depth = depth.get(current, 0)
        for nxt in sorted(succs[current]):
            preds[nxt].remove(current)
            depth[nxt] = max(depth.get(nxt, 0), current_depth + 1)
            if not preds[nxt]:
                queue.append(nxt)
                queue.sort()
    if len(visited) != len(ids):
        raise RuntimeError("MISSION_GRAPH_CYCLE")
    for node_id in ids:
        depth.setdefault(node_id, 0)
    return depth


def _enforce_budget_bounds(mission_budgets: dict[str, int], nodes: list[dict[str, Any]]) -> None:
    for node in nodes:
        budgets = node.get("budgets")
        if not isinstance(budgets, dict):
            raise RuntimeError("MISSION_NODE_BUDGETS_INVALID")
        for key in _BUDGET_KEYS:
            node_value = budgets.get(key)
            mission_value = mission_budgets.get(key)
            if not isinstance(node_value, int) or node_value < 0:
                raise RuntimeError("MISSION_NODE_BUDGETS_INVALID")
            if not isinstance(mission_value, int) or mission_value < 0:
                raise RuntimeError("MISSION_BUDGETS_INVALID")
            if node_value > mission_value:
                raise RuntimeError("MISSION_NODE_BUDGETS_EXCEED_MISSION")


def build_mission_graph(
    mission_request: dict[str, Any],
    manifest: dict[str, Any],
    intent_graph: dict[str, Any],
    *,
    selected_branch_id: str,
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    root = _repo_root(repo_root)
    mission_request_content_id = store_json_artifact(mission_request, repo_root=root)
    manifest_id = _ensure_sha256_id(manifest.get("manifest_id"), field="manifest_id")
    intent_graph_id = _ensure_sha256_id(intent_graph.get("intent_graph_id"), field="intent_graph_id")

    inputs = {
        "mission_request_content_id": mission_request_content_id,
        "manifest_id": manifest_id,
        "intent_graph_id": intent_graph_id,
        "selected_branch_id": selected_branch_id,
    }
    mission_id = _hash_bytes(canon_bytes(inputs))

    prompt = str(mission_request.get("user_prompt", ""))
    success_spec = mission_request.get("success_spec") if isinstance(mission_request.get("success_spec"), dict) else {}
    nodes, edges = _template_nodes(
        mission_request_content_id=mission_request_content_id,
        manifest_id=manifest_id,
        intent_graph_id=intent_graph_id,
        prompt=prompt,
        success_spec=success_spec,
    )
    _topological_depths(nodes, edges)

    budgets = _normalize_budgets(mission_request.get("budgets"))
    constraints = _normalize_constraints(mission_request.get("constraints"))
    _enforce_budget_bounds(budgets, nodes)

    graph = {
        "schema_version": "mission_graph_v1",
        "mission_id": mission_id,
        "inputs": inputs,
        "budgets": budgets,
        "constraints": constraints,
        "nodes": nodes,
        "edges": edges,
    }
    validate_schema("mission_graph_v1", graph, repo_root=root)
    store_json_artifact(graph, repo_root=root)
    return graph


def compile_mission(
    mission_request: dict[str, Any],
    *,
    attachment_files: list[dict[str, Any]] | None = None,
    selected_branch_id: str | None = None,
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    root = _repo_root(repo_root)
    req, manifest = capture_manifest(mission_request, attachment_files=attachment_files, repo_root=root)
    intent_graph = build_intent_graph(req, manifest, repo_root=root)

    mission_request_content_id = store_json_artifact(req, repo_root=root)
    manifest_id = _ensure_sha256_id(manifest.get("manifest_id"), field="manifest_id")
    intent_graph_id = _ensure_sha256_id(intent_graph.get("intent_graph_id"), field="intent_graph_id")

    required_clarifications = intent_graph.get("required_clarifications")
    if not isinstance(required_clarifications, list):
        required_clarifications = []

    receipt: dict[str, Any] = {
        "schema_version": "mission_compile_receipt_v1",
        "ok_b": False,
        "reason_code": "NEEDS_CLARIFICATION",
        "mission_request_content_id": mission_request_content_id,
        "manifest_id": manifest_id,
        "intent_graph_id": intent_graph_id,
        "required_clarifications": required_clarifications,
    }
    mission_graph: dict[str, Any] | None = None
    selection_rule = ""
    selected_id = ""
    if not required_clarifications:
        selected_id, selection_rule = _select_branch(intent_graph, selected_branch_id=selected_branch_id)
        mission_graph = build_mission_graph(req, manifest, intent_graph, selected_branch_id=selected_id, repo_root=root)
        mission_graph_id = store_json_artifact(mission_graph, repo_root=root)
        receipt.update(
            {
                "ok_b": True,
                "reason_code": "OK",
                "selected_branch_id": selected_id,
                "mission_graph_id": mission_graph_id,
                "selection_rule": selection_rule,
            }
        )

    validate_schema("mission_compile_receipt_v1", receipt, repo_root=root)
    compile_receipt_id = store_json_artifact(receipt, repo_root=root)
    out: dict[str, Any] = {
        "mission_request": req,
        "mission_request_content_id": mission_request_content_id,
        "manifest": manifest,
        "manifest_id": manifest_id,
        "intent_graph": intent_graph,
        "intent_graph_id": intent_graph_id,
        "compile_receipt": receipt,
        "compile_receipt_id": compile_receipt_id,
    }

    if mission_graph is not None:
        mission_id = _ensure_sha256_id(mission_graph.get("mission_id"), field="mission_id")
        mission_graph_id = _ensure_sha256_id(receipt.get("mission_graph_id"), field="mission_graph_id")
        out["mission_graph"] = mission_graph
        out["mission_id"] = mission_id
        out["mission_graph_id"] = mission_graph_id
        out["selected_branch_id"] = selected_id
        _persist_compilation(out, repo_root=root)
        _append_event(
            event_type="MISSION_COMPILED",
            mission_id=mission_id,
            payload={
                "mission_graph_id": mission_graph_id,
                "manifest_id": manifest_id,
                "intent_graph_id": intent_graph_id,
                "selection_rule": selection_rule,
            },
            repo_root=root,
        )
    else:
        temporary_id = _hash_bytes(canon_bytes({"mission_request_content_id": mission_request_content_id}))
        _append_event(
            event_type="MISSION_CLARIFICATION_REQUIRED",
            mission_id=temporary_id,
            payload={"required_clarifications": required_clarifications},
            repo_root=root,
        )

    return out


def _persist_compilation(compiled: dict[str, Any], *, repo_root: str | Path | None = None) -> None:
    mission_id = _ensure_sha256_id(compiled.get("mission_id"), field="mission_id")
    index = {
        "schema_version": "mission_index_v1",
        "mission_id": mission_id,
        "mission_request_content_id": compiled.get("mission_request_content_id"),
        "manifest_id": compiled.get("manifest_id"),
        "intent_graph_id": compiled.get("intent_graph_id"),
        "mission_graph_id": compiled.get("mission_graph_id"),
        "compile_receipt_id": compiled.get("compile_receipt_id"),
        "selected_branch_id": compiled.get("selected_branch_id"),
        "updated_unix_ms": int(time.time() * 1000),
    }
    _write_mission_index(mission_id, index, repo_root=repo_root)
    _set_current_mission_id(mission_id, repo_root=repo_root)


def initialize_mission_state(
    mission_graph: dict[str, Any],
    *,
    repo_root: str | Path | None = None,
) -> tuple[dict[str, Any], str]:
    root = _repo_root(repo_root)
    mission_id = _ensure_sha256_id(mission_graph.get("mission_id"), field="mission_id")
    mission_graph_id = store_json_artifact(mission_graph, repo_root=root)
    budgets = _normalize_budgets(mission_graph.get("budgets"))
    state = {
        "schema_version": "mission_state_v1",
        "mission_id": mission_id,
        "mission_graph_id": mission_graph_id,
        "status": "PENDING",
        "completed_node_ids": [],
        "active_node_id": None,
        "node_results": [],
        "budgets_remaining": budgets,
        "last_tick_u64": 0,
    }
    validate_schema("mission_state_v1", state, repo_root=root)
    state_id = store_json_artifact(state, repo_root=root)
    write_canon_json(_mission_state_path(mission_id, repo_root=root), state)

    index = _mission_index(mission_id, repo_root=root)
    index["mission_state_id"] = state_id
    index["status"] = state["status"]
    index["updated_unix_ms"] = int(time.time() * 1000)
    _write_mission_index(mission_id, index, repo_root=root)
    return state, state_id


def _load_mission_graph_from_index(mission_id: str, *, repo_root: str | Path | None = None) -> dict[str, Any]:
    index = _mission_index(mission_id, repo_root=repo_root)
    graph_id = _ensure_sha256_id(index.get("mission_graph_id"), field="mission_graph_id")
    graph = load_artifact(graph_id, repo_root=repo_root)
    validate_schema("mission_graph_v1", graph, repo_root=repo_root)
    return graph


def load_mission_state(mission_id: str, *, repo_root: str | Path | None = None) -> dict[str, Any]:
    path = _mission_state_path(mission_id, repo_root=repo_root)
    if not path.exists() or not path.is_file():
        raise RuntimeError("MISSION_STATE_MISSING")
    payload = load_canon_json(path)
    if not isinstance(payload, dict):
        raise RuntimeError("MISSION_STATE_INVALID")
    validate_schema("mission_state_v1", payload, repo_root=repo_root)
    return payload


def _save_mission_state(mission_id: str, state: dict[str, Any], *, repo_root: str | Path | None = None) -> str:
    root = _repo_root(repo_root)
    validate_schema("mission_state_v1", state, repo_root=root)
    state_id = store_json_artifact(state, repo_root=root)
    write_canon_json(_mission_state_path(mission_id, repo_root=root), state)

    index = _mission_index(mission_id, repo_root=root)
    index["mission_state_id"] = state_id
    index["status"] = state.get("status")
    index["updated_unix_ms"] = int(time.time() * 1000)
    _write_mission_index(mission_id, index, repo_root=root)
    return state_id


def _graph_pred_map(graph: dict[str, Any]) -> dict[str, set[str]]:
    nodes = graph.get("nodes")
    edges = graph.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise RuntimeError("MISSION_GRAPH_INVALID")
    pred: dict[str, set[str]] = {}
    for node in nodes:
        if not isinstance(node, dict):
            raise RuntimeError("MISSION_GRAPH_INVALID")
        node_id = _ensure_sha256_id(node.get("node_id"), field="node_id")
        pred[node_id] = set()
    for edge in edges:
        if not isinstance(edge, dict):
            raise RuntimeError("MISSION_GRAPH_INVALID")
        src = _ensure_sha256_id(edge.get("src"), field="edge.src")
        dst = _ensure_sha256_id(edge.get("dst"), field="edge.dst")
        if src not in pred or dst not in pred:
            raise RuntimeError("MISSION_GRAPH_EDGE_UNKNOWN_NODE")
        pred[dst].add(src)
    return pred


def select_next_node(graph: dict[str, Any], state: dict[str, Any]) -> dict[str, Any] | None:
    nodes = graph.get("nodes")
    if not isinstance(nodes, list):
        raise RuntimeError("MISSION_GRAPH_INVALID")
    completed = {str(value) for value in state.get("completed_node_ids", []) if isinstance(value, str)}
    pred = _graph_pred_map(graph)
    depths = _topological_depths(
        [node for node in nodes if isinstance(node, dict)],
        [edge for edge in graph.get("edges", []) if isinstance(edge, dict)],
    )

    ready: list[dict[str, Any]] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_id = _ensure_sha256_id(node.get("node_id"), field="node_id")
        if node_id in completed:
            continue
        if all(dep in completed for dep in pred.get(node_id, set())):
            ready.append(node)
    if not ready:
        return None
    ready.sort(key=lambda node: (depths.get(str(node["node_id"]), 0), str(node["node_id"])))
    return ready[0]


def _default_node_budgets(node: dict[str, Any]) -> dict[str, int]:
    raw = node.get("budgets")
    out = dict(_DEFAULT_NODE_BUDGETS)
    if isinstance(raw, dict):
        for key in _BUDGET_KEYS:
            value = raw.get(key)
            if isinstance(value, int) and value >= 0:
                out[key] = value
    return out


def _consume_budget(remaining: dict[str, int], used: dict[str, int]) -> dict[str, int]:
    out = dict(remaining)
    for key in _BUDGET_KEYS:
        if out.get(key, 0) < used.get(key, 0):
            raise RuntimeError("BUDGET_EXCEEDED")
        out[key] = int(out.get(key, 0)) - int(used.get(key, 0))
    return out


def _build_eval_report_stub(*, mission_id: str, node_id: str, tick_u64: int) -> dict[str, Any]:
    report = {
        "schema_name": "eval_report_v1",
        "schema_version": "v19_0",
        "report_id": "sha256:" + ("0" * 64),
        "tick_u64": int(tick_u64),
        "mode": "CLASSIFY_ONLY",
        "ek_hash": canon_content_id({"mission_id": mission_id, "kind": "ek"}),
        "suite_hash": canon_content_id({"mission_id": mission_id, "kind": "suite"}),
        "delta_j_q32": 0,
        "classification": "INSUFFICIENT_DATA",
        "metrics": {
            "cap_frontier_u64": 0,
            "cap_frontier_delta_s64": 0,
            "promotion_success_rate_q32": 0,
            "invalid_rate_q32": 0,
            "hard_task_score_q32": 0,
            "hard_task_delta_q32": 0,
        },
        "heavy_ok_count_by_capability": {},
        "heavy_no_utility_count_by_capability": {},
        "maintenance_count": 0,
        "dependency_debt_snapshot_hash": None,
        "frontier_attempts_u64": 0,
    }
    no_id = dict(report)
    no_id.pop("report_id", None)
    report["report_id"] = canon_content_id(no_id)
    return report


def _execute_node(
    *,
    mission_id: str,
    node: dict[str, Any],
    tick_u64: int,
    repo_root: str | Path | None = None,
    dev_mode: bool = True,
) -> dict[str, Any]:
    _ = dev_mode  # v1 executes deterministic stubs regardless of runtime provider.
    node_id = _ensure_sha256_id(node.get("node_id"), field="node_id")
    node_type = str(node.get("node_type", ""))
    expected = node.get("outputs_expected")
    if not isinstance(expected, list):
        expected = []

    budgets_used = {
        "wall_ms_u64": 5 + len(expected),
        "cpu_ms_u64": 3 + len(expected),
        "disk_bytes_u64": 256 * max(1, len(expected)),
        "net_bytes_u64": 0,
        "steps_u64": 1,
    }
    output_rows: list[dict[str, str]] = []
    verifier_receipts: list[dict[str, str]] = []
    for idx, row in enumerate(expected):
        if not isinstance(row, dict):
            continue
        role = str(row.get("role", f"output_{idx}"))
        schema_version = str(row.get("schema_version", "mission_output_v1"))
        if schema_version == "eval_report_v1":
            payload = _build_eval_report_stub(mission_id=mission_id, node_id=node_id, tick_u64=tick_u64)
            validate_schema("eval_report_v1", payload, repo_root=repo_root)
        else:
            payload = {
                "schema_version": schema_version,
                "mission_id": mission_id,
                "node_id": node_id,
                "node_type": node_type,
                "role": role,
                "tick_u64": int(tick_u64),
                "summary": f"deterministic_{node_type.lower()}_{role}",
            }
        content_id = store_json_artifact(payload, repo_root=repo_root)
        output_rows.append({"role": role, "content_id": content_id})

    verifier_payload = {
        "schema_version": "mission_executor_verifier_receipt_v1",
        "mission_id": mission_id,
        "node_id": node_id,
        "tick_u64": int(tick_u64),
        "status": "PASS",
    }
    verifier_receipt_id = store_json_artifact(verifier_payload, repo_root=repo_root)
    verifier_receipts.append(
        {
            "verifier_id": "mission_executor_stub_v1",
            "receipt_content_id": verifier_receipt_id,
        }
    )
    status = "SUCCEEDED"
    reason_code = "OK"
    return {
        "status": status,
        "reason_code": reason_code,
        "outputs": output_rows,
        "verifier_receipts": verifier_receipts,
        "budgets_used": budgets_used,
    }


def run_mission_step(
    mission_id: str,
    *,
    tick_u64: int,
    repo_root: str | Path | None = None,
    dev_mode: bool = True,
) -> dict[str, Any]:
    root = _repo_root(repo_root)
    mission_id = _ensure_sha256_id(mission_id, field="mission_id")
    graph = _load_mission_graph_from_index(mission_id, repo_root=root)
    state = load_mission_state(mission_id, repo_root=root)

    if str(state.get("status")) in {"FAILED", "SUCCEEDED", "WAITING_CLARIFICATION"}:
        return {"mission_id": mission_id, "state": state, "node_result": None}

    node = select_next_node(graph, state)
    if node is None:
        state["status"] = "SUCCEEDED"
        state["active_node_id"] = None
        state["last_tick_u64"] = int(tick_u64)
        _save_mission_state(mission_id, state, repo_root=root)
        return {"mission_id": mission_id, "state": state, "node_result": None}

    node_id = _ensure_sha256_id(node.get("node_id"), field="node_id")
    state["status"] = "RUNNING"
    state["active_node_id"] = node_id
    state["last_tick_u64"] = int(tick_u64)
    _save_mission_state(mission_id, state, repo_root=root)
    _append_event(
        event_type="MISSION_NODE_START",
        mission_id=mission_id,
        tick_u64=int(tick_u64),
        payload={"node_id": node_id, "node_type": node.get("node_type", "")},
        repo_root=root,
    )

    execution = _execute_node(
        mission_id=mission_id,
        node=node,
        tick_u64=int(tick_u64),
        repo_root=root,
        dev_mode=dev_mode,
    )

    used = execution["budgets_used"]
    state_budgets = state.get("budgets_remaining")
    if not isinstance(state_budgets, dict):
        raise RuntimeError("MISSION_STATE_BUDGETS_INVALID")
    mission_used = {
        "max_wall_ms_u64": int(used["wall_ms_u64"]),
        "max_cpu_ms_u64": int(used["cpu_ms_u64"]),
        "max_steps_u64": int(used["steps_u64"]),
        "max_disk_bytes_u64": int(used["disk_bytes_u64"]),
        "max_net_bytes_u64": int(used["net_bytes_u64"]),
    }

    try:
        remaining = _consume_budget({k: int(state_budgets.get(k, 0)) for k in _BUDGET_KEYS}, mission_used)
    except RuntimeError:
        execution = {
            "status": "FAILED",
            "reason_code": "BUDGET_EXCEEDED",
            "outputs": [],
            "verifier_receipts": execution["verifier_receipts"],
            "budgets_used": execution["budgets_used"],
        }
        remaining = {k: int(state_budgets.get(k, 0)) for k in _BUDGET_KEYS}

    node_result = {
        "schema_version": "mission_node_result_v1",
        "mission_id": mission_id,
        "node_id": node_id,
        "status": execution["status"],
        "reason_code": execution["reason_code"],
        "start_tick_u64": int(tick_u64),
        "end_tick_u64": int(tick_u64),
        "inputs": list(node.get("inputs", [])),
        "outputs": execution["outputs"],
        "verifier_receipts": execution["verifier_receipts"],
        "budgets_used": execution["budgets_used"],
    }
    validate_schema("mission_node_result_v1", node_result, repo_root=root)
    node_result_id = store_json_artifact(node_result, repo_root=root)

    completed = list(state.get("completed_node_ids", []))
    if execution["status"] == "SUCCEEDED":
        completed.append(node_id)
    state["completed_node_ids"] = sorted(set(completed))
    state["active_node_id"] = None
    state["last_tick_u64"] = int(tick_u64)
    state["node_results"] = list(state.get("node_results", [])) + [{"node_id": node_id, "node_result_id": node_result_id}]
    state["budgets_remaining"] = remaining

    if execution["status"] != "SUCCEEDED":
        state["status"] = "FAILED"
    else:
        next_candidate = select_next_node(graph, state)
        state["status"] = "SUCCEEDED" if next_candidate is None else "RUNNING"

    _save_mission_state(mission_id, state, repo_root=root)
    _append_event(
        event_type="MISSION_NODE_END",
        mission_id=mission_id,
        tick_u64=int(tick_u64),
        payload={
            "node_id": node_id,
            "node_result_id": node_result_id,
            "status": node_result["status"],
            "reason_code": node_result["reason_code"],
        },
        repo_root=root,
    )
    if execution["status"] == "SUCCEEDED" and any(
        row.get("role") == "eval_report" for row in node_result.get("outputs", []) if isinstance(row, dict)
    ):
        eval_ids = [row.get("content_id") for row in node_result["outputs"] if row.get("role") == "eval_report"]
        _append_event(
            event_type="MISSION_EVAL_UPDATE",
            mission_id=mission_id,
            tick_u64=int(tick_u64),
            payload={"eval_report_ids": eval_ids},
            repo_root=root,
        )
    return {"mission_id": mission_id, "state": state, "node_result": node_result, "node_result_id": node_result_id}


def run_mission_until_complete(
    mission_id: str,
    *,
    max_ticks_u64: int = 128,
    repo_root: str | Path | None = None,
    dev_mode: bool = True,
) -> dict[str, Any]:
    root = _repo_root(repo_root)
    mission_id = _ensure_sha256_id(mission_id, field="mission_id")
    steps = max(1, int(max_ticks_u64))
    result: dict[str, Any] = {"mission_id": mission_id, "steps": 0}
    for idx in range(steps):
        tick = int(idx + 1)
        result = run_mission_step(mission_id, tick_u64=tick, repo_root=root, dev_mode=dev_mode)
        state = result.get("state")
        if isinstance(state, dict) and str(state.get("status")) in {"FAILED", "SUCCEEDED", "WAITING_CLARIFICATION"}:
            break
    return result


def build_evidence_pack(
    mission_id: str,
    *,
    repo_root: str | Path | None = None,
) -> tuple[dict[str, Any], str]:
    root = _repo_root(repo_root)
    mission_id = _ensure_sha256_id(mission_id, field="mission_id")
    index = _mission_index(mission_id, repo_root=root)
    if not index:
        raise RuntimeError("MISSION_INDEX_MISSING")

    state = load_mission_state(mission_id, repo_root=root)
    state_id = store_json_artifact(state, repo_root=root)

    node_rows: list[dict[str, str]] = []
    eval_reports: list[dict[str, str]] = []
    promotion_receipts: list[dict[str, str]] = []
    for row in state.get("node_results", []):
        if not isinstance(row, dict):
            continue
        node_id = _ensure_sha256_id(row.get("node_id"), field="node_id")
        node_result_id = _ensure_sha256_id(row.get("node_result_id"), field="node_result_id")
        node_rows.append({"node_id": node_id, "node_result_id": node_result_id})
        node_result = load_artifact(node_result_id, repo_root=root)
        for output in node_result.get("outputs", []):
            if not isinstance(output, dict):
                continue
            if str(output.get("role")) != "eval_report":
                continue
            eval_id = _ensure_sha256_id(output.get("content_id"), field="eval_report_id")
            eval_payload = load_artifact(eval_id, repo_root=root)
            suitepack_id = "pinned_default"
            if isinstance(eval_payload, dict):
                suitepack_id = str(eval_payload.get("suite_hash", suitepack_id))
            eval_reports.append({"eval_report_id": eval_id, "suitepack_id": suitepack_id})
        for receipt in node_result.get("verifier_receipts", []):
            if not isinstance(receipt, dict):
                continue
            rid = _ensure_sha256_id(receipt.get("receipt_content_id"), field="receipt_content_id")
            promotion_receipts.append({"kind": "MISSION_PROMOTION", "content_id": rid})

    node_rows.sort(key=lambda row: row["node_id"])
    eval_reports = sorted(eval_reports, key=lambda row: (row["eval_report_id"], row["suitepack_id"]))
    promotion_receipts = sorted(promotion_receipts, key=lambda row: (row["kind"], row["content_id"]))

    pack_no_id = {
        "schema_version": "mission_evidence_pack_v1",
        "mission_id": mission_id,
        "bindings": {
            "mission_request_content_id": _ensure_sha256_id(index.get("mission_request_content_id"), field="mission_request_content_id"),
            "manifest_id": _ensure_sha256_id(index.get("manifest_id"), field="manifest_id"),
            "intent_graph_id": _ensure_sha256_id(index.get("intent_graph_id"), field="intent_graph_id"),
            "mission_graph_id": _ensure_sha256_id(index.get("mission_graph_id"), field="mission_graph_id"),
            "mission_state_id": state_id,
        },
        "node_results": node_rows,
        "eval_reports": eval_reports,
        "promotion_activation_receipts": promotion_receipts,
        "trace": {
            "tick_snapshots": [],
            "ledger_entries": [],
        },
        "replay": {
            "verify_tool": "tools/mission_control/replay_verify_v1.py",
            "verify_args": ["--evidence_pack_id", "__EVIDENCE_PACK_ID__"],
        },
    }
    evidence_pack_id = canon_content_id(pack_no_id)
    pack = dict(pack_no_id)
    pack["evidence_pack_id"] = evidence_pack_id
    validate_schema("mission_evidence_pack_v1", pack, repo_root=root)
    store_json_artifact(pack, repo_root=root)
    store_json_artifact_with_forced_id(pack, forced_content_id=evidence_pack_id, repo_root=root)

    index["evidence_pack_id"] = evidence_pack_id
    _write_mission_index(mission_id, index, repo_root=root)
    _append_event(
        event_type="MISSION_EVIDENCE_PACK_READY",
        mission_id=mission_id,
        payload={"evidence_pack_id": evidence_pack_id},
        repo_root=root,
    )
    return pack, evidence_pack_id


def replay_verify_evidence_pack(
    evidence_pack_id: str,
    *,
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    root = _repo_root(repo_root)
    evidence_pack_id = _ensure_sha256_id(evidence_pack_id, field="evidence_pack_id")
    pack = load_artifact(evidence_pack_id, repo_root=root)
    validate_schema("mission_evidence_pack_v1", pack, repo_root=root)

    no_id = dict(pack)
    no_id.pop("evidence_pack_id", None)
    recomputed = canon_content_id(no_id)
    if recomputed != evidence_pack_id:
        return {"ok_b": False, "reason_code": "EVIDENCE_PACK_ID_MISMATCH", "evidence_pack_id": evidence_pack_id}

    bindings = pack.get("bindings")
    if not isinstance(bindings, dict):
        return {"ok_b": False, "reason_code": "BINDINGS_INVALID", "evidence_pack_id": evidence_pack_id}

    required_refs = [
        "mission_request_content_id",
        "manifest_id",
        "intent_graph_id",
        "mission_graph_id",
        "mission_state_id",
    ]
    for key in required_refs:
        content_id = bindings.get(key)
        try:
            content_id = _ensure_sha256_id(content_id, field=key)
        except RuntimeError:
            return {"ok_b": False, "reason_code": f"BINDING_INVALID:{key}", "evidence_pack_id": evidence_pack_id}
        if not artifact_exists(content_id, repo_root=root):
            return {"ok_b": False, "reason_code": f"BINDING_MISSING:{key}", "evidence_pack_id": evidence_pack_id}

    for row in pack.get("node_results", []):
        if not isinstance(row, dict):
            return {"ok_b": False, "reason_code": "NODE_RESULT_ROW_INVALID", "evidence_pack_id": evidence_pack_id}
        node_result_id = row.get("node_result_id")
        try:
            node_result_id = _ensure_sha256_id(node_result_id, field="node_result_id")
        except RuntimeError:
            return {"ok_b": False, "reason_code": "NODE_RESULT_ID_INVALID", "evidence_pack_id": evidence_pack_id}
        if not artifact_exists(node_result_id, repo_root=root):
            return {"ok_b": False, "reason_code": "NODE_RESULT_MISSING", "evidence_pack_id": evidence_pack_id}
        node_result = load_artifact(node_result_id, repo_root=root)
        validate_schema("mission_node_result_v1", node_result, repo_root=root)

    return {
        "ok_b": True,
        "reason_code": "PASS",
        "evidence_pack_id": evidence_pack_id,
    }


def current_mission_summary(*, repo_root: str | Path | None = None) -> dict[str, Any]:
    root = _repo_root(repo_root)
    mission_id = _load_current_mission_id(repo_root=root)
    if mission_id is None:
        return {"found_b": False}
    index = _mission_index(mission_id, repo_root=root)
    if not index:
        return {"found_b": False}
    out: dict[str, Any] = {
        "found_b": True,
        "mission_id": mission_id,
        "mission_graph_id": index.get("mission_graph_id"),
        "manifest_id": index.get("manifest_id"),
        "intent_graph_id": index.get("intent_graph_id"),
        "compile_receipt_id": index.get("compile_receipt_id"),
        "evidence_pack_id": index.get("evidence_pack_id"),
        "status": index.get("status"),
        "selected_branch_id": index.get("selected_branch_id"),
        "updated_unix_ms": index.get("updated_unix_ms"),
        "replay_verify": index.get("replay_verify"),
    }
    intent_graph_id = index.get("intent_graph_id")
    if isinstance(intent_graph_id, str):
        try:
            intent_graph = load_artifact(intent_graph_id, repo_root=root)
        except Exception:
            intent_graph = None
        if isinstance(intent_graph, dict):
            branches_raw = intent_graph.get("branches")
            branches: list[dict[str, Any]] = []
            if isinstance(branches_raw, list):
                for row in branches_raw:
                    if not isinstance(row, dict):
                        continue
                    branches.append(
                        {
                            "branch_id": row.get("branch_id"),
                            "title": row.get("title"),
                            "confidence_q32": row.get("confidence_q32"),
                        }
                    )
            out["intent_branches"] = branches
    try:
        state = load_mission_state(mission_id, repo_root=root)
    except Exception:
        state = None
    if isinstance(state, dict):
        out["state"] = {
            "status": state.get("status"),
            "active_node_id": state.get("active_node_id"),
            "completed_count_u64": len(state.get("completed_node_ids", []))
            if isinstance(state.get("completed_node_ids"), list)
            else 0,
            "total_node_results_u64": len(state.get("node_results", []))
            if isinstance(state.get("node_results"), list)
            else 0,
            "last_tick_u64": state.get("last_tick_u64"),
            "completed_node_ids": state.get("completed_node_ids"),
        }
    return out


def recent_mission_events(
    *,
    mission_id: str | None = None,
    limit: int = 40,
    repo_root: str | Path | None = None,
) -> list[dict[str, Any]]:
    path = _events_path(repo_root)
    rows: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        text = raw.strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        if mission_id is not None and str(payload.get("mission_id")) != mission_id:
            continue
        rows.append(payload)
    if limit <= 0:
        return rows
    return rows[-limit:]


def run_compile_execute_and_pack(
    mission_request: dict[str, Any],
    *,
    attachment_files: list[dict[str, Any]] | None = None,
    repo_root: str | Path | None = None,
    max_ticks_u64: int = 128,
    dev_mode: bool = True,
) -> dict[str, Any]:
    compiled = compile_mission(mission_request, attachment_files=attachment_files, repo_root=repo_root)
    receipt = compiled["compile_receipt"]
    if not bool(receipt.get("ok_b", False)):
        return {
            "ok_b": False,
            "reason_code": str(receipt.get("reason_code", "NEEDS_CLARIFICATION")),
            "compile_receipt": receipt,
            "mission_id": compiled.get("mission_id"),
        }

    mission_id = _ensure_sha256_id(compiled.get("mission_id"), field="mission_id")
    graph = compiled.get("mission_graph")
    if not isinstance(graph, dict):
        raise RuntimeError("MISSION_GRAPH_MISSING")
    initialize_mission_state(graph, repo_root=repo_root)
    _append_event(event_type="MISSION_ADMITTED", mission_id=mission_id, payload={"admission": "local_mission_runner_v1"}, repo_root=repo_root)

    run_result = run_mission_until_complete(
        mission_id,
        max_ticks_u64=max_ticks_u64,
        repo_root=repo_root,
        dev_mode=dev_mode,
    )
    state = run_result.get("state") if isinstance(run_result, dict) else None
    evidence_pack_id: str | None = None
    replay: dict[str, Any] | None = None
    if isinstance(state, dict) and str(state.get("status")) in {"SUCCEEDED", "FAILED"}:
        _, evidence_pack_id = build_evidence_pack(mission_id, repo_root=repo_root)
        replay = replay_verify_evidence_pack(evidence_pack_id, repo_root=repo_root)
        index = _mission_index(mission_id, repo_root=repo_root)
        index["replay_verify"] = replay
        _write_mission_index(mission_id, index, repo_root=repo_root)

    return {
        "ok_b": True,
        "reason_code": "OK",
        "mission_id": mission_id,
        "compile_receipt": receipt,
        "mission_graph_id": compiled.get("mission_graph_id"),
        "state": state,
        "evidence_pack_id": evidence_pack_id,
        "replay_verify": replay,
    }


def _parse_attachments_arg(paths: Iterable[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for value in paths:
        path = Path(value).expanduser().resolve()
        if not path.exists() or not path.is_file():
            raise RuntimeError(f"MISSING_ATTACHMENT:{path}")
        out.append(
            {
                "filename": path.name,
                "mime": "application/octet-stream",
                "data": path.read_bytes(),
            }
        )
    return out


def _load_request_arg(raw: str) -> dict[str, Any]:
    path = Path(raw)
    try:
        is_file = path.exists() and path.is_file()
    except OSError:
        is_file = False
    if is_file:
        payload = json.loads(path.read_text(encoding="utf-8"))
    else:
        payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise RuntimeError("MISSION_REQUEST_INVALID")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Mission pipeline v1 helper")
    parser.add_argument("--mission_request", required=True, help="JSON string or path to mission request JSON file")
    parser.add_argument("--attachment", action="append", default=[], help="Attachment file path (repeatable)")
    parser.add_argument("--max_ticks_u64", type=int, default=128)
    parser.add_argument("--dev_mode", type=int, default=1)
    args = parser.parse_args()

    request_payload = _load_request_arg(args.mission_request)
    attachments = _parse_attachments_arg(args.attachment)
    out = run_compile_execute_and_pack(
        request_payload,
        attachment_files=attachments,
        max_ticks_u64=max(1, int(args.max_ticks_u64)),
        dev_mode=bool(int(args.dev_mode)),
    )
    print(json.dumps(out, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
