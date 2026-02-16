"""RSI demon v4 campaign runner."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...v1_7r.canon import CanonError, canon_bytes, hash_json, load_canon_json
from ...v1_7r.demon.inbox import load_proposals_dir
from ...v1_7r.demon.trace import build_trace_event_v2
from ...v1_7r.ontology_v3.context_kernel import build_null_ctx_key, ctx_hash
from ...v1_7r.ontology_v3.dl_metric import context_hash_for_event
from ...v1_7r.ontology_v3.eval import evaluate_epoch as eval_ontology_v3
from ...v1_7r.ontology_v3.io import ensure_ontology_dirs, load_def_by_ontology_id, load_snapshot_by_id
from ...v1_7r.macros_v2.eval import evaluate_epoch as eval_macros_v2, maybe_evict as maybe_evict_macros
from ...v1_7r.macros_v2.io import ensure_macro_dirs
from ..constants import require_constants
from ..metabolism_v1.eval import evaluate_epoch as eval_metabolism_v1
from ..metabolism_v1.translation import load_translation_inputs
from .tracker import write_receipt


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
    state_head_path.write_bytes(canon_bytes(payload) + b"\n")


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


def run_campaign(*, campaign_pack: Path, out_dir: Path, mode: str, strict: bool) -> None:
    if mode != "real":
        raise CanonError("only real mode supported")
    pack = load_canon_json(campaign_pack)
    if pack.get("schema") != "rsi_real_demon_campaign_pack_v4":
        raise CanonError("campaign_pack schema mismatch")
    if int(pack.get("schema_version", 0)) != 4:
        raise CanonError("campaign_pack schema_version mismatch")
    epochs = int(pack.get("epochs", 0))
    if epochs <= 0:
        raise CanonError("campaign_pack epochs invalid")

    proposals = pack.get("proposals")
    if not isinstance(proposals, dict):
        raise CanonError("campaign_pack proposals missing")
    onto_dir = proposals.get("ontology_v3_dir")
    macro_dir = proposals.get("macros_v2_dir")
    metabolism_dir = proposals.get("metabolism_v1_dir")
    if not isinstance(onto_dir, str) or not isinstance(macro_dir, str) or not isinstance(metabolism_dir, str):
        raise CanonError("campaign_pack proposals invalid")

    translation_cfg = pack.get("translation") if isinstance(pack.get("translation"), dict) else None
    translation_path = translation_cfg.get("translation_inputs_path") if isinstance(translation_cfg, dict) else None
    if not isinstance(translation_path, str):
        raise CanonError("campaign_pack translation invalid")

    pack_root = campaign_pack.parent
    ontology_proposals = load_proposals_dir(pack_root / onto_dir)
    macro_proposals = load_proposals_dir(pack_root / macro_dir)
    metabolism_proposals = load_proposals_dir(pack_root / metabolism_dir)
    translation_inputs = load_translation_inputs(pack_root / translation_path)

    constants = require_constants()
    eval_onto_every = int(pack.get("demon", {}).get("eval_onto_every_n_epochs", 0) or 0)
    eval_macro_every = int(pack.get("demon", {}).get("eval_macro_every_n_epochs", 0) or 0)
    eval_metabolism_every = int(pack.get("demon", {}).get("eval_metabolism_every_n_epochs", 0) or 0)

    out_dir.mkdir(parents=True, exist_ok=True)
    _ensure_state_head(out_dir)
    ensure_ontology_dirs(out_dir / "current" / "ontology_v3")
    ensure_macro_dirs(out_dir / "current" / "macros_v2")

    for epoch_idx in range(1, epochs + 1):
        _emit_trace_epoch(out_dir, epoch_idx)

        if eval_onto_every and epoch_idx % eval_onto_every == 0:
            window = int(constants.get("ONTO_V3_WINDOW_EPOCHS", 0) or 0)
            start = max(1, epoch_idx - window + 1)
            window_epochs = list(range(start, epoch_idx + 1))
            eval_ontology_v3(
                state_dir=out_dir,
                epoch_id=f"epoch_{epoch_idx}",
                constants=constants,
                window_epochs=window_epochs,
                proposals=ontology_proposals,
                strict=strict,
            )

        if eval_macro_every and epoch_idx % eval_macro_every == 0:
            window = int(constants.get("MACRO_V2_WINDOW_EPOCHS", 0) or 0)
            start = max(1, epoch_idx - window + 1)
            window_epochs = list(range(start, epoch_idx + 1))
            eval_macros_v2(
                state_dir=out_dir,
                epoch_id=f"epoch_{epoch_idx}",
                constants=constants,
                window_epochs=window_epochs,
                proposals=macro_proposals,
                strict=strict,
            )
            maybe_evict_macros(state_dir=out_dir, epoch_id=f"epoch_{epoch_idx}", constants=constants)

        if eval_metabolism_every and epoch_idx % eval_metabolism_every == 0:
            eval_metabolism_v1(
                state_dir=out_dir,
                epoch_id=f"epoch_{epoch_idx}",
                constants=constants,
                proposals=metabolism_proposals,
                translation_inputs=translation_inputs,
                strict=strict,
            )

    run_id = str(pack.get("schema"))
    write_receipt(state_dir=out_dir, run_id=run_id, final_epoch=epochs)
