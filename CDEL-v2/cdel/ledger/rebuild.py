"""Rebuild SQLite index from ledger order.log."""

from __future__ import annotations

import json
import time
from decimal import Decimal

from cdel.config import Config
from cdel.kernel import canon
from cdel.kernel.cost import count_term_nodes
from cdel.kernel.deps import collect_sym_refs
from cdel.kernel.parse import parse_definition
from cdel.kernel.types import FunType, Type
from cdel.ledger import index as idx
from cdel.ledger.alias import alias_target
from cdel.ledger.storage import GENESIS_HASH, iter_order_log, read_object, write_head
from cdel.sealed.config import load_sealed_config
from cdel.sealed.evalue import alpha_for_round, format_decimal


def rebuild_index(cfg: Config) -> None:
    conn = idx.connect(str(cfg.sqlite_path))
    idx.init_schema(conn)
    with conn:
        conn.execute("DELETE FROM modules")
        conn.execute("DELETE FROM symbols")
        conn.execute("DELETE FROM def_hashes")
        conn.execute("DELETE FROM deps")
        conn.execute("DELETE FROM sym_deps")
        conn.execute("DELETE FROM type_index")
        conn.execute("DELETE FROM aliases")
        conn.execute("DELETE FROM concepts")
        conn.execute("DELETE FROM index_impact")
        conn.execute("DELETE FROM budget")
        conn.execute("DELETE FROM rejections")
        conn.execute("DELETE FROM stat_cert_state")
    remaining = int(cfg.data["ledger"]["budget"])
    idx.set_budget(conn, remaining)
    head = GENESIS_HASH
    stat_round = 1
    alpha_spent = Decimal("0")
    sealed_cfg = None

    for module_hash in iter_order_log(cfg):
        payload_bytes = read_object(cfg, module_hash)
        payload = json.loads(payload_bytes.decode("utf-8"))
        canon_payload = canon.canonicalize_payload(payload)
        canon_bytes = canon.canonical_json_bytes(canon_payload)
        if canon_bytes != payload_bytes:
            raise ValueError(f"non-canonical payload bytes for {module_hash}")
        if canon.payload_hash_hex(canon_payload) != module_hash:
            raise ValueError(f"hash mismatch for module {module_hash}")
        definitions = canon_payload.get("definitions") or []
        new_defs = [parse_definition(defn) for defn in definitions]
        symbol_types: dict[str, Type] = {d.name: FunType(tuple(p.typ for p in d.params), d.ret_type) for d in new_defs}
        def_hashes = {defn.get("name"): canon.definition_hash(defn) for defn in definitions}
        alias_map = {}
        for defn in new_defs:
            target = alias_target(defn)
            if target:
                alias_map[defn.name] = target
        module_deps = set(canon_payload.get("declared_deps") or [])
        per_symbol_deps = {}
        sym_deps_count = 0
        for defn in definitions:
            refs = collect_sym_refs(defn.get("body"))
            per_symbol_deps[defn.get("name")] = {s for s in refs if s != defn.get("name")}
            sym_deps_count += len(per_symbol_deps[defn.get("name")])
        cost = _recompute_cost(canon_payload, new_defs, module_deps, cfg)
        remaining -= cost
        with conn:
            idx.insert_module(conn, module_hash, head, payload_bytes, cost, int(time.time()))
            idx.insert_symbols(conn, symbol_types, def_hashes, module_hash)
            idx.insert_def_hashes(conn, def_hashes, module_hash)
            idx.insert_deps(conn, module_hash, module_deps)
            for name, deps in per_symbol_deps.items():
                idx.insert_sym_deps(conn, name, deps)
            idx.insert_type_index(conn, symbol_types)
            idx.insert_aliases(conn, alias_map)
            idx.insert_concepts(conn, canon_payload.get("concepts") or [], module_hash)
            idx.insert_index_impact(
                conn,
                module_hash,
                len(symbol_types),
                len(module_deps),
                sym_deps_count,
                len(symbol_types),
                len(def_hashes),
            )
            idx.update_budget(conn, remaining)
            for spec in canon_payload.get("specs") or []:
                if spec.get("kind") == "stat_cert":
                    if sealed_cfg is None:
                        sealed_cfg = load_sealed_config(cfg.data, require_keys=False)
                    alpha_spent += alpha_for_round(sealed_cfg.alpha_total, stat_round, sealed_cfg.alpha_schedule)
                    stat_round += 1
        head = module_hash
    write_head(cfg, head)
    if stat_round > 1:
        idx.set_stat_cert_state(conn, stat_round, format_decimal(alpha_spent))


def _recompute_cost(payload: dict, defs: list, module_deps: set[str], cfg: Config) -> int:
    claim = payload.get("capacity_claim")
    if claim:
        ast_nodes = int(claim.get("ast_nodes"))
        spec_work = int(claim.get("spec_work"))
        index_impact = int(claim.get("index_impact"))
    else:
        ast_nodes = sum(count_term_nodes(defn.body) for defn in defs)
        spec_work = 0
        index_impact = len(payload.get("new_symbols") or []) + len(module_deps) + len(payload.get("new_symbols") or [])
    cost_cfg = cfg.data["cost"]
    return (
        int(cost_cfg["alpha"]) * ast_nodes
        + int(cost_cfg["beta"]) * spec_work
        + int(cost_cfg["gamma"]) * index_impact
    )
