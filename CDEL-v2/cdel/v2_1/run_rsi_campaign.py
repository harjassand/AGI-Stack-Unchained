"""Entry point for RSI demon v7 recursive ontology campaigns."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from ..v1_7r.canon import CanonError, canon_bytes, hash_json, load_canon_json, write_canon_json
from ..v1_7r.constants import require_constants as require_constants_v1_7r
from ..v1_7r.demon.inbox import load_proposals_dir
from ..v1_7r.demon.trace import build_trace_event_v2
from ..v1_7r.ontology_v3.context_kernel import build_null_ctx_key, ctx_hash
from ..v1_7r.ontology_v3.dl_metric import context_hash_for_event
from ..v1_7r.ontology_v3.eval import evaluate_epoch as eval_ontology_v3
from ..v1_7r.ontology_v3.io import ensure_ontology_dirs, load_def_by_ontology_id, load_snapshot_by_id
from ..v1_7r.macros_v2.eval import evaluate_epoch as eval_macros_v2, maybe_evict as maybe_evict_macros
from ..v1_7r.macros_v2.io import ensure_macro_dirs
from ..v1_8r.metabolism_v1.io import compute_patch_id, ensure_metabolism_dirs, patch_def_hash, write_patch_def_if_missing
from ..v1_8r.metabolism_v1.ledger import append_ledger_entry, build_ledger_entry, load_ledger_entries as load_metabolism_ledger
from ..v1_8r.metabolism_v1.translation import evaluate_translation, load_translation_inputs, validate_translation_inputs
from ..v1_8r.metabolism_v1.workvec import WorkVec
from .constants import meta_identities, require_constants
from .efficiency import efficiency_gate


FAMILY_COUNT = 3
STEPS_PER_FAMILY = 16384


def _ensure_state_head(state_dir: Path) -> None:
    state_head_path = state_dir / "current" / "state_ledger_head_v1.json"
    if state_head_path.exists():
        return
    payload = {
        "schema": "state_ledger_head_v1",
        "schema_version": 1,
        "ledger_head_hash": "sha256:" + "0" * 64,
        "line_count": 0,
    }
    state_head_path.parent.mkdir(parents=True, exist_ok=True)
    write_canon_json(state_head_path, payload)


def _family_id(idx: int) -> str:
    return hash_json({"family_index": idx})


def _inst_hash(family_id: str) -> str:
    return hash_json({"family_id": family_id})


def _obs_hash(epoch_idx: int, family_id: str, t_step: int) -> str:
    return hash_json({"epoch": epoch_idx, "family_id": family_id, "t_step": t_step})


def _post_obs_hash(obs_hash: str, action_name: str, t_step: int) -> str:
    return hash_json({"obs_hash": obs_hash, "action": action_name, "t_step": t_step})


def _receipt_hash(post_obs_hash: str) -> str:
    return hash_json({"post_obs_hash": post_obs_hash})


def _load_active_ontology(state_dir: Path) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    ontology_root = state_dir / "current" / "ontology_v3"
    active_path = ontology_root / "active" / "ontology_active_set_v3.json"
    if not active_path.exists():
        return None, None
    active_set = load_canon_json(active_path)
    ontology_id = active_set.get("active_ontology_id")
    snapshot_id = active_set.get("active_snapshot_id")
    if not isinstance(ontology_id, str) or not isinstance(snapshot_id, str):
        return None, None
    dirs = ensure_ontology_dirs(ontology_root)
    ontology_def = load_def_by_ontology_id(ontology_id, defs_root=dirs["defs"])
    snapshot = load_snapshot_by_id(snapshot_id, snapshots_root=dirs["snapshots"])
    return ontology_def, snapshot


def _emit_trace_epoch(state_dir: Path, epoch_idx: int) -> None:
    trace_dir = state_dir / "epochs" / f"epoch_{epoch_idx}" / "traces"
    trace_dir.mkdir(parents=True, exist_ok=True)
    trace_path = trace_dir / "trace_v2.jsonl"

    ontology_def, snapshot = _load_active_ontology(state_dir)
    null_ctx_hash = ctx_hash(build_null_ctx_key())

    with trace_path.open("wb") as handle:
        for fam_idx in range(FAMILY_COUNT):
            family_id = _family_id(fam_idx)
            inst_hash = _inst_hash(family_id)
            for step in range(STEPS_PER_FAMILY):
                t_step = int(step)
                mod = t_step % 4
                action_name = f"act_{mod}"
                action_args: dict[str, Any] = {}
                obs_hash = _obs_hash(epoch_idx, family_id, t_step)
                post_obs_hash = _post_obs_hash(obs_hash, action_name, t_step)
                receipt_hash = _receipt_hash(post_obs_hash)

                event = {
                    "schema": "trace_event_v2",
                    "schema_version": 2,
                    "t_step": t_step,
                    "family_id": family_id,
                    "inst_hash": inst_hash,
                    "action": {"name": action_name, "args": action_args},
                    "obs_hash": obs_hash,
                    "post_obs_hash": post_obs_hash,
                    "receipt_hash": receipt_hash,
                    "macro_id": None,
                    "onto_ctx_hash": null_ctx_hash,
                    "active_ontology_id": None,
                    "active_snapshot_id": None,
                }
                if ontology_def is not None and snapshot is not None:
                    event["onto_ctx_hash"] = context_hash_for_event(event, ontology_def, snapshot)
                    event["active_ontology_id"] = ontology_def.get("ontology_id")
                    event["active_snapshot_id"] = snapshot.get("snapshot_id")
                payload = build_trace_event_v2(
                    t_step=event["t_step"],
                    family_id=event["family_id"],
                    inst_hash=event["inst_hash"],
                    action_name=event["action"]["name"],
                    action_args=event["action"]["args"],
                    obs_hash=event["obs_hash"],
                    post_obs_hash=event["post_obs_hash"],
                    receipt_hash=event["receipt_hash"],
                    macro_id=event["macro_id"],
                    onto_ctx_hash=event["onto_ctx_hash"],
                    active_ontology_id=event["active_ontology_id"],
                    active_snapshot_id=event["active_snapshot_id"],
                )
                handle.write(canon_bytes(payload) + b"\n")


def _validate_out_dir(out_dir: Path) -> None:
    if not out_dir.exists():
        return
    entries = [path.name for path in out_dir.iterdir()]
    if not entries:
        return
    allowed = {"autonomy", "pinned"}
    if set(entries).issubset(allowed):
        return
    raise CanonError("OUT_DIR_NOT_EMPTY")


def _pin_campaign_pack(campaign_pack: Path, out_dir: Path) -> None:
    payload = load_canon_json(campaign_pack)
    dest = out_dir / "current" / "campaign_pack" / "campaign_pack_used.json"
    write_canon_json(dest, payload)


def _epoch_index(epoch_id: str) -> int | None:
    tail = str(epoch_id).split("_")[-1]
    return int(tail) if tail.isdigit() else None


def _meta_check(payload: dict[str, Any], meta: dict[str, str]) -> None:
    xmeta = payload.get("x-meta")
    if not isinstance(xmeta, dict):
        raise CanonError("x-meta missing")
    for key in ("META_HASH", "KERNEL_HASH", "constants_hash"):
        if xmeta.get(key) != meta.get(key):
            raise CanonError("x-meta mismatch")


def _validate_patch_def(patch_def: dict[str, Any], constants: dict[str, Any], meta: dict[str, str]) -> dict[str, Any]:
    if patch_def.get("schema") != "meta_patch_def_v1":
        raise CanonError("meta patch def schema mismatch")
    if int(patch_def.get("schema_version", 0)) != 1:
        raise CanonError("meta patch def schema_version mismatch")
    _meta_check(patch_def, meta)
    patch_id = patch_def.get("patch_id")
    if not isinstance(patch_id, str):
        raise CanonError("patch_id missing")
    expected = compute_patch_id(patch_def)
    if patch_id != expected:
        raise CanonError("patch_id mismatch")
    patch_kind = patch_def.get("patch_kind")
    if patch_kind != "ctx_hash_cache_v1":
        raise CanonError("patch_kind not allowlisted")
    params = patch_def.get("params") if isinstance(patch_def.get("params"), dict) else {}
    capacity = int(params.get("capacity", 0))
    max_capacity = int(constants.get("CTX_HASH_CACHE_V1_MAX_CAPACITY", 0) or 0)
    if capacity < 1 or capacity > max_capacity:
        raise CanonError("capacity out of range")
    return patch_def


def _write_active_set(path: Path, patch_id: str, epoch_idx: int, meta: dict[str, str]) -> dict[str, Any]:
    payload = {
        "schema": "meta_patch_active_set_v1",
        "schema_version": 1,
        "active_patch_ids": [patch_id],
        "activation_epoch": int(epoch_idx),
        "x-meta": meta,
    }
    write_canon_json(path, payload)
    return payload


def _evaluate_metabolism_v3(
    *,
    state_dir: Path,
    epoch_id: str,
    constants: dict[str, Any],
    proposals: list[dict[str, Any]],
    translation_inputs: dict[str, Any],
    strict: bool = True,
    rho_min: dict[str, Any] | None = None,
) -> dict[str, Any]:
    meta = meta_identities()
    metabolism_root = state_dir / "current" / "metabolism_v1"
    dirs = ensure_metabolism_dirs(metabolism_root)
    ledger_path = dirs["ledger"] / "meta_patch_ledger_v1.jsonl"
    active_path = dirs["active"] / "meta_patch_active_set_v1.json"

    epoch_idx = _epoch_index(epoch_id)
    if epoch_idx is None:
        raise CanonError("invalid epoch_id")

    translation_inputs = validate_translation_inputs(translation_inputs)

    weights = constants.get("WORK_COST_WEIGHTS_V1", {}) if isinstance(constants.get("WORK_COST_WEIGHTS_V1"), dict) else {}
    rho_min_num = int(rho_min.get("num", 0) or 0) if isinstance(rho_min, dict) else 0
    rho_min_den = int(rho_min.get("den", 1) or 1) if isinstance(rho_min, dict) else 1

    best: dict[str, Any] | None = None
    for proposal in proposals:
        if not isinstance(proposal, dict):
            continue
        try:
            patch_def = _validate_patch_def(proposal, constants, meta)
            patch_id = patch_def.get("patch_id")
            patch_hash = patch_def_hash(patch_def)
            capacity = int(patch_def.get("params", {}).get("capacity", 0))
            eval_result = evaluate_translation(
                translation_inputs=translation_inputs,
                cache_capacity=capacity,
                min_sha256_delta=0,
            )
            workvec_base: WorkVec = eval_result.get("workvec_base")
            workvec_patch: WorkVec = eval_result.get("workvec_patch")
            gate_info = efficiency_gate(
                workvec_base,
                workvec_patch,
                weights=weights,
                rho_min_num=rho_min_num,
                rho_min_den=rho_min_den,
            )

            candidate = {
                "patch_def": patch_def,
                "patch_id": patch_id,
                "patch_def_hash": patch_hash,
                "workvec_base": workvec_base,
                "workvec_patch": workvec_patch,
                "gate": gate_info,
            }
            if best is None:
                best = candidate
            else:
                best_cost = int(best["gate"]["work_cost_patch"])
                cand_cost = int(candidate["gate"]["work_cost_patch"])
                if cand_cost < best_cost:
                    best = candidate
                elif cand_cost == best_cost:
                    if str(candidate.get("patch_id")) < str(best.get("patch_id")):
                        best = candidate
        except Exception:
            if strict:
                continue
            continue

    if best is None:
        raise CanonError("no valid metabolism proposals")

    report = {
        "schema": "meta_patch_eval_report_v2",
        "schema_version": 2,
        "epoch": int(epoch_idx),
        "workvec_base": best["workvec_base"].to_dict(),
        "workvec_patch": best["workvec_patch"].to_dict(),
        "work_cost_base": int(best["gate"]["work_cost_base"]),
        "work_cost_patch": int(best["gate"]["work_cost_patch"]),
        "rho_met": best["gate"]["rho_met"],
        "rho_met_min": {"num": int(rho_min_num), "den": int(rho_min_den)},
        "efficiency_vector_dominance": bool(best["gate"]["efficiency_vector_dominance"]),
        "efficiency_scalar_gate": bool(best["gate"]["efficiency_scalar_gate"]),
        "efficiency_gate_passed": bool(best["gate"]["efficiency_gate_passed"]),
    }
    report_path = dirs["reports"] / f"meta_patch_eval_report_v2_epoch_{epoch_idx}.json"
    write_canon_json(report_path, report)

    activated = False
    patch_id = best.get("patch_id")
    patch_def = best.get("patch_def")
    patch_hash = best.get("patch_def_hash")
    if bool(best["gate"]["efficiency_gate_passed"]):
        write_patch_def_if_missing(patch_def, dirs["defs"])
        report_hash = hash_json(report)
        admit_receipt = {
            "schema": "meta_patch_admit_receipt_v1",
            "schema_version": 1,
            "epoch_id": epoch_id,
            "patch_id": patch_id,
            "patch_def_hash": patch_hash,
            "meta_patch_eval_report_hash": report_hash,
            "verdict": "VALID",
            "x-meta": meta,
        }
        receipt_path = dirs["receipts"] / f"meta_patch_admit_receipt_v1_epoch_{epoch_idx}.json"
        write_canon_json(receipt_path, admit_receipt)
        receipt_hash = hash_json(admit_receipt)

        ledger_entries = load_metabolism_ledger(ledger_path)
        prev_hash = ledger_entries[-1].get("line_hash") if ledger_entries else None

        admit_entry = build_ledger_entry(
            event="ADMIT",
            epoch_id=epoch_id,
            patch_id=patch_id,
            patch_def_hash=patch_hash,
            meta_patch_admit_receipt_hash=receipt_hash,
            prev_line_hash=prev_hash,
            meta=meta,
        )
        append_ledger_entry(ledger_path, admit_entry)

        activate_entry = build_ledger_entry(
            event="ACTIVATE",
            epoch_id=epoch_id,
            patch_id=patch_id,
            patch_def_hash=None,
            meta_patch_admit_receipt_hash=None,
            prev_line_hash=admit_entry.get("line_hash"),
            meta=meta,
        )
        append_ledger_entry(ledger_path, activate_entry)
        _write_active_set(active_path, patch_id, epoch_idx, meta)
        activated = True

    return {
        "report": report,
        "activated": activated,
        "patch_id": patch_id,
    }


def _write_receipt_v7(*, state_dir: Path, final_epoch: int, last_eval: dict[str, Any]) -> Path:
    metabolism_root = state_dir / "current" / "metabolism_v1"
    ledger_path = metabolism_root / "ledger" / "meta_patch_ledger_v1.jsonl"
    ledger = load_metabolism_ledger(ledger_path)

    admitted = sum(1 for entry in ledger if entry.get("event") == "ADMIT")
    activated = sum(1 for entry in ledger if entry.get("event") == "ACTIVATE")

    active_patch_id = ""
    if activated >= 1:
        active_set_path = metabolism_root / "active" / "meta_patch_active_set_v1.json"
        if active_set_path.exists():
            active_set = load_canon_json(active_set_path)
            active_ids = active_set.get("active_patch_ids") if isinstance(active_set.get("active_patch_ids"), list) else []
            if active_ids:
                active_patch_id = str(active_ids[0])
        if not active_patch_id:
            active_patch_id = str(last_eval.get("patch_id", ""))

    report = last_eval.get("report", {}) if isinstance(last_eval.get("report"), dict) else {}

    verdict = "VALID" if bool(report.get("efficiency_gate_passed")) and activated >= 1 else "INVALID"

    latest_eval_epoch = int(report.get("epoch", final_epoch))
    payload = {
        "schema": "rsi_demon_receipt_v7",
        "schema_version": 7,
        "verdict": verdict,
        "metabolism_v1": {
            "admitted": int(admitted),
            "activated": int(activated),
            "active_patch_id": active_patch_id,
            "latest_eval_epoch": latest_eval_epoch,
            "work_cost_base": int(report.get("work_cost_base", 0)),
            "work_cost_patch": int(report.get("work_cost_patch", 0)),
            "rho_met": report.get("rho_met", {"num": 0, "den": 1}),
            "rho_coupled": report.get("rho_met", {"num": 0, "den": 1}),
            "efficiency_gate_passed": bool(report.get("efficiency_gate_passed")),
        },
    }

    out_path = state_dir / "epochs" / f"epoch_{final_epoch}" / "diagnostics" / "rsi_demon_receipt_v7.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_canon_json(out_path, payload)
    return out_path


def run_campaign(*, campaign_pack: Path, out_dir: Path, mode: str, strict: bool) -> None:
    if mode != "real":
        raise CanonError("only real mode supported")
    _validate_out_dir(out_dir)
    pack = load_canon_json(campaign_pack)
    if pack.get("schema") != "rsi_real_demon_campaign_pack_v7":
        raise CanonError("campaign_pack schema mismatch")
    if "schema_version" in pack and int(pack.get("schema_version", 0)) != 7:
        raise CanonError("campaign_pack schema_version mismatch")
    epochs = int(pack.get("epochs", 0))
    if epochs <= 0:
        raise CanonError("campaign_pack epochs invalid")

    proposals = pack.get("proposals")
    if not isinstance(proposals, dict):
        raise CanonError("campaign_pack proposals missing")
    onto_dir = proposals.get("ontology_v3_dir")
    macro_dir = proposals.get("macros_v2_dir")
    metabolism_dir = proposals.get("metabolism_dir")
    opt_concepts_dir = proposals.get("opt_concepts_dir")
    if not isinstance(metabolism_dir, str) or not isinstance(opt_concepts_dir, str):
        raise CanonError("campaign_pack proposals invalid")

    translation_path = pack.get("translation_inputs_path")
    if not isinstance(translation_path, str):
        raise CanonError("campaign_pack translation invalid")

    autonomy_cfg = pack.get("autonomy") if isinstance(pack.get("autonomy"), dict) else None
    if not isinstance(autonomy_cfg, dict):
        raise CanonError("campaign_pack autonomy missing")
    metabolism_cfg = autonomy_cfg.get("metabolism") if isinstance(autonomy_cfg.get("metabolism"), dict) else None
    if not isinstance(metabolism_cfg, dict):
        raise CanonError("campaign_pack autonomy metabolism missing")

    efficiency_cfg = pack.get("efficiency") if isinstance(pack.get("efficiency"), dict) else None
    if not isinstance(efficiency_cfg, dict) or not efficiency_cfg.get("enabled"):
        raise CanonError("campaign_pack efficiency invalid")
    rho_min = efficiency_cfg.get("rho_min") if isinstance(efficiency_cfg.get("rho_min"), dict) else None
    if not isinstance(rho_min, dict):
        raise CanonError("campaign_pack efficiency invalid")

    pack_root = campaign_pack.parent
    ontology_proposals: list[dict[str, Any]] = []
    if isinstance(onto_dir, str):
        ontology_proposals = load_proposals_dir(pack_root / onto_dir)
    macro_proposals: list[dict[str, Any]] = []
    if isinstance(macro_dir, str):
        macro_proposals = load_proposals_dir(pack_root / macro_dir)

    metabolism_proposals_dir = out_dir / "autonomy" / "metabolism_v1" / "proposals"
    if metabolism_dir != "__AUTONOMY_RUNDIR_V2__":
        metabolism_proposals_dir = pack_root / metabolism_dir
    metabolism_proposals = load_proposals_dir(metabolism_proposals_dir)
    translation_inputs = load_translation_inputs(pack_root / translation_path)

    constants_onto = require_constants_v1_7r()
    constants_meta = require_constants()
    eval_onto_every = int(pack.get("demon", {}).get("eval_onto_every_n_epochs", 0) or 0)
    eval_macro_every = int(pack.get("demon", {}).get("eval_macro_every_n_epochs", 0) or 0)
    eval_metabolism_every = int(pack.get("demon", {}).get("eval_metabolism_every_n_epochs", 0) or 0)

    out_dir.mkdir(parents=True, exist_ok=True)
    _pin_campaign_pack(campaign_pack, out_dir)
    _ensure_state_head(out_dir)
    ensure_ontology_dirs(out_dir / "current" / "ontology_v3")
    ensure_macro_dirs(out_dir / "current" / "macros_v2")

    last_eval: dict[str, Any] | None = None

    for epoch_idx in range(1, epochs + 1):
        _emit_trace_epoch(out_dir, epoch_idx)

        if eval_onto_every and epoch_idx % eval_onto_every == 0:
            window = int(constants_onto.get("ONTO_V3_WINDOW_EPOCHS", 0) or 0)
            start = max(1, epoch_idx - window + 1)
            window_epochs = list(range(start, epoch_idx + 1))
            eval_ontology_v3(
                state_dir=out_dir,
                epoch_id=f"epoch_{epoch_idx}",
                constants=constants_onto,
                window_epochs=window_epochs,
                proposals=ontology_proposals,
                strict=strict,
            )

        if eval_macro_every and epoch_idx % eval_macro_every == 0:
            window = int(constants_onto.get("MACRO_V2_WINDOW_EPOCHS", 0) or 0)
            start = max(1, epoch_idx - window + 1)
            window_epochs = list(range(start, epoch_idx + 1))
            eval_macros_v2(
                state_dir=out_dir,
                epoch_id=f"epoch_{epoch_idx}",
                constants=constants_onto,
                window_epochs=window_epochs,
                proposals=macro_proposals,
                strict=strict,
            )
            maybe_evict_macros(state_dir=out_dir, epoch_id=f"epoch_{epoch_idx}", constants=constants_onto)

        if eval_metabolism_every and epoch_idx % eval_metabolism_every == 0:
            last_eval = _evaluate_metabolism_v3(
                state_dir=out_dir,
                epoch_id=f"epoch_{epoch_idx}",
                constants=constants_meta,
                proposals=metabolism_proposals,
                translation_inputs=translation_inputs,
                strict=strict,
                rho_min=rho_min,
            )

    if last_eval is None:
        raise CanonError("missing metabolism evaluation")

    _write_receipt_v7(state_dir=out_dir, final_epoch=epochs, last_eval=last_eval)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run RSI demon v7 recursive ontology campaign")
    parser.add_argument("--mode", default="real")
    parser.add_argument("--strict-rsi", action="store_true", dest="strict")
    parser.add_argument("--campaign_pack", required=True)
    parser.add_argument("--out_dir", required=True)
    args = parser.parse_args()

    run_campaign(
        campaign_pack=Path(args.campaign_pack),
        out_dir=Path(args.out_dir),
        mode=str(args.mode),
        strict=bool(args.strict),
    )


if __name__ == "__main__":
    main()
