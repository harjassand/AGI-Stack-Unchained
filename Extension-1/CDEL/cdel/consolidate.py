"""Concept consolidation report generator (read-only)."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path

from blake3 import blake3

from cdel.config import Config
from cdel.adoption.storage import read_head as read_adoption_head
from cdel.ledger import index as idx
from cdel.ledger.closure import compute_closure_with_stats, load_module_payload
from cdel.sealed.canon import canon_bytes
from cdel.sealed.evalue import (
    encoded_evalue_to_decimal,
    format_decimal,
    parse_decimal,
    parse_evalue,
)


@dataclass(frozen=True)
class CandidateEvidence:
    symbol: str
    module_hash: str | None
    active: bool
    closure_symbols: int | None
    alpha_i: str | None
    threshold: str | None
    evalue: dict | None
    margin: str | None
    score: Decimal


def consolidate_concept(
    cfg: Config,
    concept: str,
    *,
    policy: str = "best_cert",
    topk: int = 5,
    out_dir: Path | None = None,
    write_proposal: bool = False,
) -> dict:
    conn = idx.connect(str(cfg.sqlite_path))
    idx.init_schema(conn)

    symbols = idx.list_symbols_for_concept(conn, concept, 10_000)
    adoption = idx.latest_adoption_for_concept(conn, concept)
    active_symbol = adoption["chosen_symbol"] if adoption else None

    candidates: list[CandidateEvidence] = []
    for symbol in symbols:
        module_hash = idx.get_symbol_module(conn, symbol)
        closure_symbols = None
        try:
            closure, _ = compute_closure_with_stats(conn, [symbol])
            closure_symbols = len(closure)
        except Exception:
            closure_symbols = None
        cert = _stat_cert_from_symbol(cfg, module_hash, symbol)
        evidence = _candidate_evidence(
            symbol=symbol,
            module_hash=module_hash,
            active=(symbol == active_symbol),
            closure_symbols=closure_symbols,
            cert=cert,
        )
        candidates.append(evidence)

    ranked_all = _rank_candidates(candidates, policy)
    ranked = ranked_all[:topk] if topk > 0 else ranked_all

    report = _report_payload(cfg, concept, policy, topk, active_symbol, ranked_all, ranked)
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "consolidation_report.json").write_text(
            json.dumps(report, sort_keys=True, indent=2),
            encoding="utf-8",
        )
        _write_markdown(out_dir / "consolidation_report.md", report)
        if write_proposal:
            proposal = _proposal_payload(cfg, concept, active_symbol, ranked)
            if proposal:
                (out_dir / "adoption_proposal.json").write_text(
                    json.dumps(proposal, sort_keys=True, indent=2),
                    encoding="utf-8",
                )
    return report


def _stat_cert_from_symbol(cfg: Config, module_hash: str | None, symbol: str) -> dict | None:
    if not module_hash:
        return None
    try:
        payload = load_module_payload(cfg, module_hash)
    except Exception:
        return None
    for spec in payload.get("specs", []):
        if not isinstance(spec, dict):
            continue
        if spec.get("kind") != "stat_cert":
            continue
        if spec.get("candidate_symbol") != symbol:
            continue
        return spec
    return None


def _candidate_evidence(
    *,
    symbol: str,
    module_hash: str | None,
    active: bool,
    closure_symbols: int | None,
    cert: dict | None,
) -> CandidateEvidence:
    alpha_i = None
    threshold = None
    evalue = None
    margin = None
    score = Decimal("-1")
    if cert:
        risk = cert.get("risk") or {}
        certificate = cert.get("certificate") or {}
        alpha_i = risk.get("alpha_i")
        evalue = certificate.get("evalue")
        try:
            if isinstance(alpha_i, str) and isinstance(evalue, dict):
                alpha_dec = parse_decimal(alpha_i)
                parsed_evalue = parse_evalue(evalue, "consolidate evalue")
                evalue_dec = encoded_evalue_to_decimal(parsed_evalue)
                with localcontext() as ctx:
                    ctx.prec = 50
                    threshold = format_decimal(parse_decimal("1") / alpha_dec)
                    margin = format_decimal(evalue_dec * alpha_dec)
                score = evalue_dec * alpha_dec
        except (ValueError, InvalidOperation):
            score = Decimal("-1")
    return CandidateEvidence(
        symbol=symbol,
        module_hash=module_hash,
        active=active,
        closure_symbols=closure_symbols,
        alpha_i=alpha_i,
        threshold=threshold,
        evalue=evalue,
        margin=margin,
        score=score,
    )


def _rank_candidates(candidates: list[CandidateEvidence], policy: str) -> list[CandidateEvidence]:
    if policy != "best_cert":
        raise ValueError("policy must be best_cert")

    def sort_key(item: CandidateEvidence) -> tuple[int, Decimal, int]:
        active_key = 0 if item.active else 1
        closure = item.closure_symbols if item.closure_symbols is not None else 10**9
        return (active_key, -item.score, closure)

    return sorted(candidates, key=sort_key)


def _proposal_payload(
    cfg: Config,
    concept: str,
    active_symbol: str | None,
    ranked: list[CandidateEvidence],
) -> dict | None:
    if not ranked:
        return None
    best = ranked[0]
    if best.symbol == active_symbol:
        return None
    cert = _stat_cert_from_symbol(cfg, best.module_hash, best.symbol) if best.module_hash else None
    if not cert:
        return None
    return {
        "schema_version": 1,
        "parent": read_adoption_head(cfg),
        "payload": {
            "concept": concept,
            "chosen_symbol": best.symbol,
            "baseline_symbol": active_symbol,
            "certificate": cert,
            "constraints": {},
        },
    }


def _report_payload(
    cfg: Config,
    concept: str,
    policy: str,
    topk: int,
    active_symbol: str | None,
    ranked_all: list[CandidateEvidence],
    ranked: list[CandidateEvidence],
) -> dict:
    entries = []
    for cand in ranked:
        entries.append(
            {
                "symbol": cand.symbol,
                "module_hash": cand.module_hash,
                "active": cand.active,
                "closure_symbols": cand.closure_symbols,
                "alpha_i": cand.alpha_i,
                "threshold": cand.threshold,
                "evalue": cand.evalue,
                "margin": cand.margin,
            }
        )
    total = len(ranked_all)
    active_count = 1 if active_symbol else 0
    inactive_count = max(total - active_count, 0)
    return {
        "schema_version": 1,
        "meta": _meta_info(cfg),
        "concept": concept,
        "policy": policy,
        "topk": topk,
        "active_symbol": active_symbol,
        "summary": {
            "candidates": total,
            "active": active_count,
            "inactive": inactive_count,
        },
        "ranked": entries,
    }


def _write_markdown(path: Path, report: dict) -> None:
    summary = report.get("summary") or {}
    lines = [
        "# Consolidation Report",
        "",
        f"- concept: {report.get('concept')}",
        f"- policy: {report.get('policy')}",
        f"- topk: {report.get('topk')}",
        f"- active_symbol: {report.get('active_symbol')}",
        f"- candidates: {summary.get('candidates')}",
        f"- active: {summary.get('active')}",
        f"- inactive: {summary.get('inactive')}",
        "",
        "Ranked candidates:",
        "",
    ]
    for row in report.get("ranked", []):
        lines.append(
            f"- {row.get('symbol')} active={row.get('active')} "
            f"closure={row.get('closure_symbols')} "
            f"alpha_i={row.get('alpha_i')} threshold={row.get('threshold')} "
            f"margin={row.get('margin')}"
        )
    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def _meta_info(cfg: Config) -> dict:
    sealed = cfg.data.get("sealed") or {}
    return {
        "git_commit": _git_commit(_repo_root()),
        "config_hash": _config_hash(cfg.data),
        "eval_harness_id": sealed.get("eval_harness_id"),
        "eval_harness_hash": sealed.get("eval_harness_hash"),
        "eval_suite_hash": sealed.get("eval_suite_hash"),
    }


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _git_commit(root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()
    except Exception:
        return None


def _config_hash(data: dict) -> str:
    payload = json.loads(json.dumps(data))
    sealed = payload.get("sealed")
    if isinstance(sealed, dict):
        sealed.pop("private_key", None)
    return blake3(canon_bytes(payload)).hexdigest()
