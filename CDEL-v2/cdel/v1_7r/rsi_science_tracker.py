from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from cdel.v1_6r.constants import meta_identities, require_constants
from cdel.v1_6r.family_dsl.runtime import instantiate_family
from cdel.v1_7r.canon import canon_bytes, hash_json, load_canon_json, sha256_prefixed, write_canon_json


R_DEFAULT_INSERTIONS = 5


def _parse_prefixed_hash(h: str) -> bytes:
    if not isinstance(h, str) or ":" not in h:
        raise ValueError(f"bad hash string: {h!r}")
    alg, hexpart = h.split(":", 1)
    if alg != "sha256":
        raise ValueError(f"unsupported hash alg: {alg!r}")
    if len(hexpart) != 64:
        raise ValueError(f"bad sha256 hex length: {len(hexpart)}")
    return bytes.fromhex(hexpart)


def _read_jsonl(path: Path) -> List[dict]:
    if not path.exists():
        raise FileNotFoundError(str(path))
    out: List[dict] = []
    for ln, line in enumerate(path.read_text().splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError as e:
            raise ValueError(f"{path} line {ln}: invalid json: {e}") from e
    return out


def _alpha_streak(values: List[int], *, alpha_num: int, alpha_den: int, k_accel: int) -> bool:
    """
    Returns True iff there exists i such that for k_accel consecutive steps:
        values[j] * alpha_den <= values[j-1] * alpha_num
    for j in i+1..i+k_accel.
    Uses only integer arithmetic.
    """
    if k_accel <= 0:
        return True
    if len(values) < k_accel + 1:
        return False
    for i in range(len(values) - k_accel):
        ok = True
        for j in range(i + 1, i + 1 + k_accel):
            if values[j] * alpha_den > values[j - 1] * alpha_num:
                ok = False
                break
        if ok:
            return True
    return False


def _all_ok(checks: Dict[str, dict]) -> bool:
    return all(bool(v.get("ok")) for v in checks.values())


def _family_paths(state_dir: Path) -> Path:
    return state_dir / "current" / "families"


def _load_family_by_hash(state_dir: Path, family_hash: str) -> dict:
    fam_path = _family_paths(state_dir) / (family_hash.split(":", 1)[1] + ".json")
    return load_canon_json(fam_path)


def _suite_row_hash(suite_row: dict) -> str:
    return sha256_prefixed(canon_bytes(suite_row))


def _instantiate_suite_row(family: dict, *, epoch_key: bytes) -> dict:
    dummy_commit = {"commitment": "sci-replay"}
    inst = instantiate_family(
        family,
        theta={},
        epoch_commit=dummy_commit,
        epoch_key=epoch_key,
        skip_validation=True,
    )
    if not isinstance(inst, dict):
        raise ValueError("instantiate_family did not return dict")

    payload = inst.get("payload")
    if isinstance(payload, dict):
        sr = payload.get("suite_row")
        if isinstance(sr, dict):
            return sr

    sr2 = inst.get("suite_row")
    if isinstance(sr2, dict):
        return sr2

    raise ValueError("instantiate_family did not return suite_row (expected payload.suite_row)")

def _load_witness(state_dir: Path, witness_hash: str) -> dict:
    """
    Witnesses are stored in epochs/<epoch_id>/diagnostics/science_instance_witnesses_v1/<witness_hash_hex>.json.
    We search all epochs and fail-closed if not found or ambiguous.
    """
    epochs_dir = state_dir / "epochs"
    if not epochs_dir.exists():
        raise FileNotFoundError(str(epochs_dir))
    witness_stem = witness_hash.split(":", 1)[1] if witness_hash.startswith("sha256:") else witness_hash
    matches: List[Path] = []
    for ep in epochs_dir.iterdir():
        if not ep.is_dir() or not ep.name.startswith("epoch_"):
            continue
        p = ep / "diagnostics" / "science_instance_witnesses_v1" / f"{witness_stem}.json"
        if p.exists():
            matches.append(p)
    if len(matches) != 1:
        raise FileNotFoundError(f"witness {witness_hash} not found uniquely; matches={len(matches)}")
    return load_canon_json(matches[0])


@dataclass(frozen=True)
class InsertionRecord:
    insertion_id: str
    epoch_id: str
    admitted_family_id: str
    admitted_family_hash: str
    barrier_entry_hash: str
    env_steps_total: int
    bytes_hashed_total: int
    env_steps_by_env_kind: Dict[str, int]
    bytes_hashed_by_env_kind: Dict[str, int]


def _load_insertions_window(state_dir: Path, *, R: int) -> List[InsertionRecord]:
    barrier_path = state_dir / "current" / "barrier_ledger_v1.jsonl"
    entries = _read_jsonl(barrier_path)
    if len(entries) < R:
        raise ValueError(f"need >= {R} barrier entries, got {len(entries)}")
    window = entries[-R:]

    out: List[InsertionRecord] = []
    for e in window:
        ins_id = e.get("insertion_id")
        epoch_id = e.get("start_epoch_id") or e.get("epoch_id") or e.get("start_epoch") or e.get("epoch")
        fam_id = e.get("admitted_family_id")
        fam_hash = e.get("admitted_family_hash")
        work = e.get("barrier_workvec_sum") or {}
        env_steps_total = int(work.get("env_steps_total", 0))
        bytes_hashed_total = int(work.get("bytes_hashed_total", 0))
        env_steps_by_env = e.get("x-env_steps_by_env_kind") or {}
        bytes_by_env = e.get("x-bytes_hashed_by_env_kind") or {}
        if not isinstance(env_steps_by_env, dict) or not isinstance(bytes_by_env, dict):
            raise ValueError("barrier entry missing env-kind splits")
        barrier_hash = sha256_prefixed(canon_bytes(e))
        out.append(
            InsertionRecord(
                insertion_id=str(ins_id),
                epoch_id=str(epoch_id),
                admitted_family_id=str(fam_id),
                admitted_family_hash=str(fam_hash),
                barrier_entry_hash=barrier_hash,
                env_steps_total=env_steps_total,
                bytes_hashed_total=bytes_hashed_total,
                env_steps_by_env_kind={str(k): int(v) for k, v in env_steps_by_env.items()},
                bytes_hashed_by_env_kind={str(k): int(v) for k, v in bytes_by_env.items()},
            )
        )
    return out


def build_rsi_science_window_report(*, state_dir: Path, epoch_id: str, R: int = R_DEFAULT_INSERTIONS) -> dict:
    """
    Recomputes the SCI window checks strictly from state_dir evidence.
    Writes nothing; pure function.
    """
    state_dir = state_dir.resolve()
    meta = meta_identities()
    const = require_constants()
    alpha_num = int(const["rsi"]["alpha_num"])
    alpha_den = int(const["rsi"]["alpha_den"])
    k_accel = int(const["rsi"]["K_accel"])

    insertions = _load_insertions_window(state_dir, R=R)

    # 1) portfolio_env_count: heldout instance specs in the final epoch must contain >=2 env kinds
    heldout_specs_path = state_dir / "epochs" / epoch_id / "diagnostics" / "instance_specs_v1.json"
    heldout_envs: List[str] = []
    if heldout_specs_path.exists():
        inst_specs_doc = load_canon_json(heldout_specs_path)
        instances = inst_specs_doc.get("instances") if isinstance(inst_specs_doc, dict) else None
        if isinstance(instances, dict):
            for inst in instances.values():
                try:
                    env = inst["payload"]["suite_row"]["env"]
                except Exception:
                    continue
                heldout_envs.append(str(env))
    heldout_env_kinds = sorted(set(heldout_envs))
    chk_portfolio_env_count = {
        "ok": len(heldout_env_kinds) >= 2,
        "reason_codes": [] if len(heldout_env_kinds) >= 2 else ["INSUFFICIENT_HELDOUT_ENV_KINDS"],
        "details": {"heldout_env_kinds": heldout_env_kinds},
    }

    # 2) insertion novelty + key sensitivity: require family_semantics_report_v1.json for each insertion epoch
    novelty_ok = True
    key_sensitive_ok = True
    novelty_rc: List[str] = []
    key_rc: List[str] = []
    insertion_env_kinds: List[str] = []
    witness_parent_hashes: List[str] = []
    witness_replay_ok = True

    for ins in insertions:
        sem_path = state_dir / "epochs" / ins.epoch_id / "diagnostics" / "family_semantics_report_v1.json"
        if not sem_path.exists():
            novelty_ok = False
            key_sensitive_ok = False
            novelty_rc.append("MISSING_FAMILY_SEMANTICS_REPORT")
            key_rc.append("MISSING_FAMILY_SEMANTICS_REPORT")
            continue
        sem = load_canon_json(sem_path)
        checks = sem.get("checks", {}) if isinstance(sem, dict) else {}
        nov = bool(checks.get("fingerprint_unique_vs_prev_frontier", {}).get("ok"))
        ks = bool(checks.get("key_sensitive", {}).get("ok"))
        if not nov:
            novelty_ok = False
            novelty_rc.append("NOVELTY_FAIL")
        if not ks:
            key_sensitive_ok = False
            key_rc.append("KEY_SENSITIVITY_FAIL")

        # infer env kind from probe instantiation (probe_key_a)
        family = _load_family_by_hash(state_dir, ins.admitted_family_hash)
        probe_key_a = _parse_prefixed_hash(const["family_semantics"]["probe_key_a"])
        sr_a = _instantiate_suite_row(family, epoch_key=probe_key_a)
        insertion_env_kinds.append(str(sr_a.get("env", "unknown")))

        parent_wit = family.get("x-parent_witness_hash")
        if isinstance(parent_wit, str) and parent_wit:
            witness_parent_hashes.append(parent_wit)
            replay_key = None
            instantiator = family.get("instantiator", {})
            if isinstance(instantiator, dict):
                replay_key = instantiator.get("replay_key") or instantiator.get("x-replay_key")
            if isinstance(replay_key, str) and replay_key.startswith("sha256:"):
                w = _load_witness(state_dir, parent_wit)
                parent_sr_hash = str(w.get("suite_row_hash"))
                sr_replay = _instantiate_suite_row(family, epoch_key=_parse_prefixed_hash(replay_key))
                if _suite_row_hash(sr_replay) != parent_sr_hash:
                    witness_replay_ok = False
            else:
                witness_replay_ok = False

    chk_insertions_true_novelty = {
        "ok": novelty_ok,
        "reason_codes": [] if novelty_ok else sorted(set(novelty_rc)),
    }
    chk_insertions_key_sensitive = {
        "ok": key_sensitive_ok,
        "reason_codes": [] if key_sensitive_ok else sorted(set(key_rc)),
    }

    # 3) witness-conditioned insertion present
    chk_witness_conditioned_present = {
        "ok": len(witness_parent_hashes) >= 1,
        "reason_codes": [] if len(witness_parent_hashes) >= 1 else ["NO_SCI_WITNESS_CONDITIONED_INSERTION"],
    }

    # 4) witness replay ok
    chk_witness_replay_ok = {
        "ok": witness_replay_ok and len(witness_parent_hashes) >= 1,
        "reason_codes": [] if (witness_replay_ok and len(witness_parent_hashes) >= 1) else ["SCI_WITNESS_REPLAY_FAIL"],
    }

    # 5) macro transfer present
    macro_report_path = state_dir / "epochs" / epoch_id / "diagnostics" / "macro_cross_env_support_report_v2.json"
    macro_ok = False
    macro_rc: List[str] = []
    macro_support_details: dict = {}
    if macro_report_path.exists():
        mr = load_canon_json(macro_report_path)
        macro_support_details = {"macro_count": len(mr.get("macros", [])) if isinstance(mr, dict) else 0}
        if isinstance(mr, dict):
            for m in mr.get("macros", []):
                if not isinstance(m, dict):
                    continue
                if int(m.get("support_envs_hold", 0)) >= 2 and m.get("status") == "ADMIT":
                    macro_ok = True
                    break
        if not macro_ok:
            macro_rc.append("NO_ADMITTED_CROSS_ENV_MACRO")
    else:
        macro_rc.append("MISSING_MACRO_SUPPORT_REPORT")
    chk_macro_transfer_present = {"ok": macro_ok, "reason_codes": [] if macro_ok else macro_rc, "details": macro_support_details}

    # 6) mech patch promoted + eval pass
    mech_cert_path = state_dir / "epochs" / epoch_id / "diagnostics" / "mech_patch_eval_cert_sci_v1.json"
    mech_active_path = state_dir / "current" / "science_mech_patch_active_set_v1.json"
    mech_eval_ok = False
    mech_prom_ok = False
    mech_rc: List[str] = []
    if mech_cert_path.exists():
        cert = load_canon_json(mech_cert_path)
        summary = cert.get("summary", {}) if isinstance(cert, dict) else {}
        mech_eval_ok = bool(summary.get("nonregressing_all")) and bool(summary.get("strict_improvement_any"))
        if not mech_eval_ok:
            mech_rc.append("MECH_EVAL_FAIL")
    else:
        mech_rc.append("MISSING_MECH_EVAL_CERT")

    if mech_active_path.exists():
        active = load_canon_json(mech_active_path)
        active_ids = active.get("active_patch_ids") if isinstance(active, dict) else None
        mech_prom_ok = isinstance(active_ids, list) and len(active_ids) >= 1
        if not mech_prom_ok:
            mech_rc.append("EMPTY_MECH_ACTIVE_SET")
    else:
        mech_rc.append("MISSING_MECH_ACTIVE_SET")

    chk_mech_patch_promoted = {"ok": mech_prom_ok, "reason_codes": [] if mech_prom_ok else ["MECH_PATCH_NOT_PROMOTED"]}
    chk_mech_patch_eval_pass = {"ok": mech_eval_ok, "reason_codes": [] if mech_eval_ok else mech_rc}

    # 7) barrier accel checks
    pooled_env_steps = [ins.env_steps_total for ins in insertions]
    pooled_bytes = [ins.bytes_hashed_total for ins in insertions]

    pooled_env_ok = _alpha_streak(pooled_env_steps, alpha_num=alpha_num, alpha_den=alpha_den, k_accel=k_accel)
    pooled_bytes_ok = _alpha_streak(pooled_bytes, alpha_num=alpha_num, alpha_den=alpha_den, k_accel=k_accel)

    chk_barrier_env_steps = {
        "ok": pooled_env_ok,
        "reason_codes": [] if pooled_env_ok else ["BARRIER_ACCEL_FAIL_POOLED_ENV_STEPS"],
        "details": {"series": pooled_env_steps, "alpha_num": alpha_num, "alpha_den": alpha_den, "k_accel": k_accel},
    }
    chk_barrier_bytes = {
        "ok": pooled_bytes_ok,
        "reason_codes": [] if pooled_bytes_ok else ["BARRIER_ACCEL_FAIL_POOLED_BYTES_HASHED"],
        "details": {"series": pooled_bytes, "alpha_num": alpha_num, "alpha_den": alpha_den, "k_accel": k_accel},
    }

    env_kinds_in_window = sorted(set(insertion_env_kinds))
    by_env_env_steps_ok = True
    by_env_bytes_ok = True
    by_env_details: Dict[str, Any] = {}
    for ek in env_kinds_in_window:
        series_steps = [int(ins.env_steps_by_env_kind.get(ek, 0)) for ins in insertions]
        series_bytes = [int(ins.bytes_hashed_by_env_kind.get(ek, 0)) for ins in insertions]
        ok_steps = _alpha_streak(series_steps, alpha_num=alpha_num, alpha_den=alpha_den, k_accel=k_accel)
        ok_bytes = _alpha_streak(series_bytes, alpha_num=alpha_num, alpha_den=alpha_den, k_accel=k_accel)
        by_env_details[ek] = {"env_steps": series_steps, "bytes_hashed": series_bytes, "ok_env_steps": ok_steps, "ok_bytes": ok_bytes}
        if not ok_steps:
            by_env_env_steps_ok = False
        if not ok_bytes:
            by_env_bytes_ok = False

    chk_barrier_env_steps_by_env = {
        "ok": by_env_env_steps_ok,
        "reason_codes": [] if by_env_env_steps_ok else ["BARRIER_ACCEL_FAIL_ENV_STEPS_BY_ENV"],
        "details": by_env_details,
    }
    chk_barrier_bytes_by_env = {
        "ok": by_env_bytes_ok,
        "reason_codes": [] if by_env_bytes_ok else ["BARRIER_ACCEL_FAIL_BYTES_HASHED_BY_ENV"],
        "details": by_env_details,
    }

    checks: Dict[str, dict] = {
        "portfolio_env_count": chk_portfolio_env_count,
        "insertions_true_novelty": chk_insertions_true_novelty,
        "insertions_key_sensitive": chk_insertions_key_sensitive,
        "science_witness_conditioned_insertion_present": chk_witness_conditioned_present,
        "science_witness_replay_ok": chk_witness_replay_ok,
        "macro_transfer_present_science": chk_macro_transfer_present,
        "mech_patch_promoted_science": chk_mech_patch_promoted,
        "mech_patch_eval_pass_science": chk_mech_patch_eval_pass,
        "barrier_accel_env_steps": chk_barrier_env_steps,
        "barrier_accel_bytes_hashed": chk_barrier_bytes,
        "barrier_accel_env_steps_by_env": chk_barrier_env_steps_by_env,
        "barrier_accel_bytes_hashed_by_env": chk_barrier_bytes_by_env,
    }

    report = {
        "schema": "rsi_science_window_report_v1",
        "schema_version": 1,
        "epoch_id": epoch_id,
        "R_insertions": R,
        "insertions_used": [ins.insertion_id for ins in insertions],
        "insertion_epochs": [ins.epoch_id for ins in insertions],
        "x-meta": meta,
        "checks": checks,
    }
    return report


def maybe_emit_rsi_science_receipt(
    *,
    state_dir: Path,
    epoch_id: str,
    window_report: dict,
    out_path: Path,
    macro_report_paths: List[Path],
    mech_cert_paths: List[Path],
    witness_hashes_used: List[str],
    barrier_entry_hashes: List[str],
) -> Optional[dict]:
    """
    Emit receipt only if all window checks pass.
    Returns receipt dict if emitted, else None.
    """
    if not _all_ok(window_report.get("checks", {})):
        return None

    meta = meta_identities()
    const = require_constants()
    const_hash = hash_json(const)

    macro_hashes = [hash_json(load_canon_json(p)) for p in macro_report_paths]
    mech_hashes = [hash_json(load_canon_json(p)) for p in mech_cert_paths]
    window_hash = hash_json(window_report)

    receipt = {
        "schema": "rsi_science_receipt_v1",
        "schema_version": 1,
        "epoch_id": epoch_id,
        "KERNEL_HASH": meta["KERNEL_HASH"],
        "META_HASH": meta["META_HASH"],
        "constants_hash": const_hash,
        "toolchain_root": meta["toolchain_root"],
        "insertions_used": list(window_report.get("insertions_used", [])),
        "witness_hashes_used": sorted(set(witness_hashes_used)),
        "macro_cross_env_support_report_hashes": macro_hashes,
        "mech_patch_eval_cert_hashes": mech_hashes,
        "rsi_science_window_report_hash": window_hash,
        "barrier_ledger_entry_hashes": barrier_entry_hashes,
        "x-meta": meta,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_canon_json(out_path, receipt)
    return receipt
