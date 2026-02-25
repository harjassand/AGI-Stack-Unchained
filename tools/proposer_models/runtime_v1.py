#!/usr/bin/env python3
"""Runtime inference for proposer fine-tuned model bundles (v1)."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any

from tools.proposer_models import store_v1


class ProposerRuntimeError(RuntimeError):
    """Fail-closed runtime error carrying a compact reason code."""


def _fail(reason: str) -> None:
    raise ProposerRuntimeError(str(reason).strip() or "MODEL_RUNTIME_FAILED")


def _normalize_role(role: Any) -> str:
    role_text = str(role).strip()
    if role_text not in {"PATCH_DRAFTER_V1", "PATCH_CRITIC_V1"}:
        _fail("SCHEMA_FAIL")
    return role_text


def _default_store_root() -> Path:
    return store_v1.default_model_store_root()


def _import_runtime_deps() -> tuple[Any, Any, Any, Any, Any]:
    try:
        import numpy as np
        import torch
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except Exception:
        _fail("MODEL_RUNTIME_DEPS_MISSING")
    return np, torch, PeftModel, AutoModelForCausalLM, AutoTokenizer


def _set_deterministic_seeds(*, np: Any, torch: Any, seed_u64: int) -> None:
    seed = int(seed_u64) & ((1 << 63) - 1)
    np.random.seed(int(seed % (1 << 32)))
    torch.manual_seed(seed)
    if bool(torch.cuda.is_available()):
        torch.cuda.manual_seed_all(seed)
    try:
        torch.use_deterministic_algorithms(True)
    except Exception:
        pass


def _resolve_adapter_blob_path(*, store_root: Path, row: dict[str, Any]) -> Path:
    digest = store_v1.ensure_sha256_id(row.get("sha256"), reason="SCHEMA_FAIL")
    relpath = str(row.get("relpath", "")).strip()
    if not relpath:
        _fail("SCHEMA_FAIL")
    ext = Path(relpath).suffix.lstrip(".").lower() or "bin"
    blobs_root = (store_root.resolve() / "blobs" / "sha256").resolve()

    candidate = blobs_root / store_v1.blob_filename(digest, kind="adapter", ext=ext)
    if candidate.exists() and candidate.is_file():
        return candidate

    rows = sorted(blobs_root.glob(f"sha256_{digest.split(':', 1)[1]}.adapter.*"), key=lambda p: p.as_posix())
    if not rows:
        _fail("BUNDLE_ADAPTER_MISSING")
    return rows[0]


def _adapter_dir_from_bundle(*, bundle: dict[str, Any], store_root: Path) -> str:
    adapter_files = bundle.get("adapter_files")
    if not isinstance(adapter_files, list):
        _fail("SCHEMA_FAIL")

    materialized_root = Path(tempfile.mkdtemp(prefix="proposer_adapter_runtime_v1_")).resolve()
    for row in adapter_files:
        if not isinstance(row, dict):
            _fail("SCHEMA_FAIL")
        relpath = str(row.get("relpath", "")).strip()
        if not relpath:
            _fail("SCHEMA_FAIL")
        src = _resolve_adapter_blob_path(store_root=store_root, row=row)
        dst = (materialized_root / Path(relpath)).resolve()
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(src.read_bytes())
    return str(materialized_root)


def generate_patch_deterministic(
    role: str,
    prompt_text: str,
    model_bundle_id: str,
    seed_u64: int,
    max_new_tokens_u32: int,
) -> str:
    """Returns unified diff as text. Fail-closed on any mismatch."""

    role_norm = _normalize_role(role)
    bundle_id = store_v1.ensure_sha256_id(model_bundle_id, reason="SCHEMA_FAIL")
    max_new_tokens = int(max(1, int(max_new_tokens_u32)))
    prompt = str(prompt_text)

    store_root = _default_store_root()
    store_v1.ensure_model_store_layout(store_root)

    try:
        bundle = store_v1.load_bundle_manifest(store_root=store_root, bundle_id=bundle_id)
    except RuntimeError as exc:
        _fail(str(exc) or "MODEL_BUNDLE_MISSING")

    if str(bundle.get("role", "")).strip() != role_norm:
        _fail("MODEL_ROLE_MISMATCH")

    # Integrity verification runs before dependency imports.
    try:
        store_v1.verify_bundle_adapter_hashes(store_root=store_root, bundle=bundle)
    except RuntimeError as exc:
        _fail(str(exc) or "BUNDLE_HASH_MISMATCH")

    np, torch, PeftModel, AutoModelForCausalLM, AutoTokenizer = _import_runtime_deps()
    _set_deterministic_seeds(np=np, torch=torch, seed_u64=int(seed_u64))

    base_model_ref = str(bundle.get("base_model_ref", "")).strip()
    tokenizer_ref = str(bundle.get("tokenizer_ref", "")).strip()
    if not base_model_ref or not tokenizer_ref:
        _fail("SCHEMA_FAIL")

    adapter_dir = ""
    try:
        adapter_dir = _adapter_dir_from_bundle(bundle=bundle, store_root=store_root)
        tokenizer = AutoTokenizer.from_pretrained(tokenizer_ref)
        if tokenizer.pad_token_id is None and tokenizer.eos_token_id is not None:
            tokenizer.pad_token = tokenizer.eos_token

        model = AutoModelForCausalLM.from_pretrained(base_model_ref)
        model = PeftModel.from_pretrained(model, adapter_dir)
        model.eval()

        encoded = tokenizer(prompt, return_tensors="pt")
        device = next(model.parameters()).device
        encoded = {k: v.to(device) for k, v in encoded.items()}

        with torch.no_grad():
            generated = model.generate(
                **encoded,
                max_new_tokens=max_new_tokens,
                do_sample=False,
                temperature=0.0,
                top_p=1.0,
                num_beams=1,
                pad_token_id=tokenizer.pad_token_id,
                eos_token_id=tokenizer.eos_token_id,
            )

        input_len = int(encoded["input_ids"].shape[-1])
        tail = generated[0][input_len:]
        text = tokenizer.decode(tail, skip_special_tokens=True)
        if not text.strip():
            text = tokenizer.decode(generated[0], skip_special_tokens=True)
        return str(text)
    except ProposerRuntimeError:
        raise
    except Exception:
        _fail("MODEL_RUNTIME_FAILED")
    finally:
        if adapter_dir:
            try:
                shutil.rmtree(Path(adapter_dir), ignore_errors=True)
            except Exception:
                pass


__all__ = ["ProposerRuntimeError", "generate_patch_deterministic"]
