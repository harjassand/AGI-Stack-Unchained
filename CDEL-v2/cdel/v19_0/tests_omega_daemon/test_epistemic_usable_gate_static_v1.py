from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

from cdel.v19_0.epistemic.usable_index_v1 import (
    append_usable_index_row,
    iter_usable_graphs,
    load_usable_capsule_ids,
    load_usable_graph_ids,
    load_rows,
)
from orchestrator.omega_v19_0.microkernel_v1 import _collect_epistemic_metrics_from_prev_state


Q32_ONE = 1 << 32
_DENY_SEGMENTS: tuple[tuple[str, str], ...] = (("epistemic", "capsules"), ("epistemic", "graphs"))
_DENY_GLOB_SUFFIXES: tuple[str, ...] = ("epistemic_capsule_v1.json", "qxwmr_graph_v1.json")


def _canon(obj: dict) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _h(obj: dict) -> str:
    return "sha256:" + hashlib.sha256(_canon(obj)).hexdigest()


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canon(payload) + b"\n")


def _split_path_tokens(text: str) -> list[str]:
    return [part for part in str(text).replace("\\", "/").split("/") if part]


def _contains_segment(tokens: list[str], segment: tuple[str, str]) -> bool:
    if len(tokens) < len(segment):
        return False
    for idx in range(0, len(tokens) - len(segment) + 1):
        if tuple(tokens[idx : idx + len(segment)]) == segment:
            return True
    return False


def _iter_literal_strings(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.JoinedStr):
        out: list[str] = []
        for value in node.values:
            out.extend(_iter_literal_strings(value))
        return out
    if isinstance(node, ast.FormattedValue):
        return _iter_literal_strings(node.value)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _iter_literal_strings(node.left) + _iter_literal_strings(node.right)
    if isinstance(node, ast.Tuple | ast.List | ast.Set):
        out: list[str] = []
        for value in node.elts:
            out.extend(_iter_literal_strings(value))
        return out
    if isinstance(node, ast.Dict):
        out: list[str] = []
        for value in [*node.keys, *node.values]:
            if value is not None:
                out.extend(_iter_literal_strings(value))
        return out
    return []


def _path_tokens_from_expr(node: ast.AST | None) -> list[str]:
    if node is None:
        return []
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return _split_path_tokens(node.value)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return _path_tokens_from_expr(node.left) + _path_tokens_from_expr(node.right)
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id == "Path" and node.args:
            return _path_tokens_from_expr(node.args[0])
        if isinstance(node.func, ast.Attribute) and node.func.attr == "joinpath":
            out = _path_tokens_from_expr(node.func.value)
            for arg in node.args:
                out.extend(_path_tokens_from_expr(arg))
            return out
    if isinstance(node, ast.Attribute):
        return _path_tokens_from_expr(node.value)
    return []


def _has_direct_epistemic_read(text: str) -> bool:
    tree = ast.parse(text)
    read_methods = {"glob", "rglob", "read_text", "read_bytes", "open"}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        method = None
        func_value = None
        if isinstance(node.func, ast.Attribute):
            method = node.func.attr
            func_value = node.func.value
        elif isinstance(node.func, ast.Name):
            method = node.func.id
        if method not in read_methods:
            continue
        literal_strings = _iter_literal_strings(node)
        tokens = _path_tokens_from_expr(func_value)
        for literal in literal_strings:
            tokens.extend(_split_path_tokens(literal))
        has_dir = any(_contains_segment(tokens, segment) for segment in _DENY_SEGMENTS)
        has_glob = any(
            any(suffix in literal for suffix in _DENY_GLOB_SUFFIXES)
            for literal in literal_strings
        )
        if has_dir or has_glob:
            return True
    return False


def _graph_payload(*, episode_id: str, confidence_q32: int) -> dict:
    payload = {
        "schema_version": "qxwmr_graph_v1",
        "graph_id": "sha256:" + ("0" * 64),
        "episode_id": episode_id,
        "reduce_contract_id": _h({"k": "reduce"}),
        "confidence_calibration_id": _h({"k": "cal"}),
        "nodes": [
            {
                "node_id": "node-1",
                "type_id": "CLAIM",
                "value_kind": "STRING",
                "text_value": "alpha",
                "confidence_q32": int(confidence_q32),
                "provenance_raw_blob_ids": [],
            }
        ],
        "edges": [],
    }
    payload["graph_id"] = _h({k: v for k, v in payload.items() if k != "graph_id"})
    return payload


def _capsule_payload(*, episode_id: str, graph_id: str, usable_b: bool, cert_gate_status: str) -> dict:
    payload = {
        "schema_version": "epistemic_capsule_v1",
        "capsule_id": "sha256:" + ("0" * 64),
        "episode_id": episode_id,
        "tick_u64": 1,
        "pinset_id": _h({"k": "pinset", "episode": episode_id}),
        "mob_ids": [_h({"k": "mob", "episode": episode_id})],
        "distillate_graph_id": graph_id,
        "reduce_contract_id": _h({"k": "reduce"}),
        "confidence_calibration_id": _h({"k": "cal"}),
        "sip_manifest_id": _h({"k": "manifest", "episode": episode_id}),
        "sip_receipt_id": _h({"k": "receipt", "episode": episode_id}),
        "world_snapshot_id": _h({"k": "snapshot", "episode": episode_id}),
        "world_root": _h({"k": "root", "episode": episode_id}),
        "usable_b": bool(usable_b),
        "cert_gate_status": str(cert_gate_status),
        "cert_profile_id": "sha256:" + ("0" * 64),
    }
    payload["capsule_id"] = _h({k: v for k, v in payload.items() if k != "capsule_id"})
    return payload


def test_static_guard_rejects_direct_capsule_graph_reads_outside_allowlist() -> None:
    repo_root = Path(__file__).resolve().parents[4]
    py_files = sorted(
        [
            *repo_root.glob("orchestrator/omega_v19_0/*.py"),
            *repo_root.glob("CDEL-v2/cdel/v19_0/**/*.py"),
        ],
        key=lambda p: p.as_posix(),
    )

    allowlist = {
        (repo_root / "orchestrator/omega_v19_0/microkernel_v1.py").resolve(),
        (repo_root / "CDEL-v2/cdel/v19_0/verify_rsi_omega_daemon_v1.py").resolve(),
        (repo_root / "CDEL-v2/cdel/v19_0/verify_rsi_epistemic_reduce_v1.py").resolve(),
        (repo_root / "CDEL-v2/cdel/v19_0/verify_rsi_epistemic_retention_harden_v1.py").resolve(),
        (repo_root / "CDEL-v2/cdel/v19_0/campaign_epistemic_retention_harden_v1.py").resolve(),
        (repo_root / "CDEL-v2/cdel/v19_0/shadow_corpus_v1.py").resolve(),
        (repo_root / "CDEL-v2/cdel/v19_0/epistemic/capsule_v1.py").resolve(),
        (repo_root / "CDEL-v2/cdel/v19_0/epistemic/usable_index_v1.py").resolve(),
        (repo_root / "CDEL-v2/cdel/v19_0/epistemic/verify_epistemic_capsule_v1.py").resolve(),
        (repo_root / "CDEL-v2/cdel/v19_0/epistemic/verify_epistemic_certs_v1.py").resolve(),
        (repo_root / "CDEL-v2/cdel/v19_0/epistemic/verify_epistemic_reduce_v1.py").resolve(),
        (repo_root / "CDEL-v2/cdel/v19_0/epistemic/verify_epistemic_type_governance_v1.py").resolve(),
    }

    offenders: list[str] = []
    for path in py_files:
        if "/tests_omega_daemon/" in path.as_posix():
            continue
        if path.resolve() in allowlist:
            continue
        text = path.read_text(encoding="utf-8")
        if _has_direct_epistemic_read(text):
            offenders.append(path.relative_to(repo_root).as_posix())

    assert not offenders, f"Direct epistemic capsule/graph reads detected outside allowlist: {offenders}"


def test_runtime_metrics_ignore_unusable_capsules_and_graphs(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    epi_root = state_root / "epistemic"
    (epi_root / "capsules").mkdir(parents=True, exist_ok=True)
    (epi_root / "graphs").mkdir(parents=True, exist_ok=True)
    (epi_root / "refutations").mkdir(parents=True, exist_ok=True)

    episode_a = _h({"episode": "A"})
    episode_b = _h({"episode": "B"})
    graph_a = _graph_payload(episode_id=episode_a, confidence_q32=Q32_ONE)
    graph_b = _graph_payload(episode_id=episode_b, confidence_q32=0)
    capsule_a = _capsule_payload(
        episode_id=episode_a,
        graph_id=str(graph_a["graph_id"]),
        usable_b=True,
        cert_gate_status="PASS",
    )
    capsule_b = _capsule_payload(
        episode_id=episode_b,
        graph_id=str(graph_b["graph_id"]),
        usable_b=False,
        cert_gate_status="BLOCKED",
    )

    _write(epi_root / "graphs" / f"sha256_{_h(graph_a).split(':', 1)[1]}.qxwmr_graph_v1.json", graph_a)
    _write(epi_root / "graphs" / f"sha256_{_h(graph_b).split(':', 1)[1]}.qxwmr_graph_v1.json", graph_b)
    _write(epi_root / "capsules" / f"sha256_{_h(capsule_a).split(':', 1)[1]}.epistemic_capsule_v1.json", capsule_a)
    _write(epi_root / "capsules" / f"sha256_{_h(capsule_b).split(':', 1)[1]}.epistemic_capsule_v1.json", capsule_b)

    append_usable_index_row(
        state_root=state_root,
        capsule_id=str(capsule_a["capsule_id"]),
        distillate_graph_id=str(graph_a["graph_id"]),
        usable_b=True,
        cert_gate_status="PASS",
        cert_profile_id="sha256:" + ("0" * 64),
        reason_code="CERT_OK",
    )

    rows = load_rows(state_root)
    assert rows
    assert all(bool(row.get("usable_b", False)) for row in rows)

    usable_capsules = load_usable_capsule_ids(state_root)
    usable_graphs = load_usable_graph_ids(state_root)
    assert str(capsule_a["capsule_id"]) in usable_capsules
    assert str(capsule_b["capsule_id"]) not in usable_capsules
    assert str(graph_a["graph_id"]) in usable_graphs
    assert str(graph_b["graph_id"]) not in usable_graphs

    iterable_graph_paths = iter_usable_graphs(state_root)
    assert len(iterable_graph_paths) == 1
    loaded_graph = json.loads(iterable_graph_paths[0].read_text(encoding="utf-8"))
    assert str(loaded_graph.get("graph_id", "")) == str(graph_a["graph_id"])

    metrics = _collect_epistemic_metrics_from_prev_state(state_root)
    assert int(metrics["epistemic_capsule_count_u64"]) == 1
    assert int(metrics["epistemic_refutation_count_u64"]) == 0
    # Only usable graph A is counted; it has full confidence.
    assert int((metrics["epistemic_low_confidence_ratio_q32"] or {}).get("q", 0)) == 0
