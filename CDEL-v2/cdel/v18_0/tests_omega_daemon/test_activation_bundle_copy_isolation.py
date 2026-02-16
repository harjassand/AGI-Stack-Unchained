from __future__ import annotations

from pathlib import Path

from cdel.v18_0.omega_promoter_v1 import _build_meta_core_activation_bundle
from cdel.v1_7r.canon import write_canon_json


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def _prepare_fake_meta_core_root(root: Path) -> tuple[Path, Path]:
    active_hex = "a" * 64
    active_bundle_dir = root / "store" / "bundles" / active_hex

    write_canon_json(
        active_bundle_dir / "constitution.manifest.json",
        {"schema_version": "constitution_manifest_v1", "proofs": {}, "blobs": []},
    )
    write_canon_json(active_bundle_dir / "ruleset" / "accept.ir.json", {"Safe": None})
    write_canon_json(active_bundle_dir / "ruleset" / "costvec.ir.json", {"Const": 1})
    write_canon_json(active_bundle_dir / "ruleset" / "migrate.ir.json", {"Migrate": []})
    write_canon_json(active_bundle_dir / "proofs" / "dominance_witness.json", {})
    write_canon_json(active_bundle_dir / "proofs" / "proof_bundle.manifest.json", {})

    _write_text(root / "active" / "ACTIVE_BUNDLE", f"{active_hex}\n")
    _write_text(root / "meta_constitution" / "v1" / "META_HASH", "b" * 64 + "\n")
    _write_text(root / "kernel" / "verifier" / "KERNEL_HASH", "c" * 64 + "\n")
    _write_text(root / "meta_constitution" / "v1" / "build_meta_hash.sh", "#!/bin/sh\n")
    _write_text(root / "scripts" / "build.sh", "#!/bin/sh\n")
    _write_text(root / "kernel" / "verifier" / "toolchain.lock", "toolchain\n")
    _write_text(root / "kernel" / "verifier" / "Cargo.lock", "cargo-lock\n")
    _write_text(root / "kernel" / "verifier" / "build.sh", "#!/bin/sh\n")
    _write_text(root / "meta_constitution" / "v1" / "schemas" / "migration.schema.json", "{}\n")
    _write_text(
        root / "engine" / "hashing.py",
        "\n".join(
            [
                "def ruleset_hash(bundle_dir):",
                "    return '1' * 64",
                "def proof_bundle_hash(bundle_dir):",
                "    return '2' * 64",
                "def migration_hash(bundle_dir):",
                "    return '3' * 64",
                "def state_schema_hash(meta_core_root):",
                "    return '4' * 64",
                "def toolchain_merkle_root(meta_core_root):",
                "    return '5' * 64",
                "def manifest_hash(manifest):",
                "    return '6' * 64",
                "def bundle_hash(manifest_hash_hex, ruleset_hash_hex, proof_bundle_hash_hex, migration_hash_hex, state_schema_hash_hex, toolchain_merkle_root_hex):",
                "    return '7' * 64",
                "",
            ]
        ),
    )

    return active_bundle_dir, root


def test_activation_bundle_copy_isolation(tmp_path, monkeypatch) -> None:
    fake_meta_core_root = tmp_path / "meta-core"
    active_bundle_dir, _ = _prepare_fake_meta_core_root(fake_meta_core_root)
    out_dir = tmp_path / "out"
    binding_payload = {
        "schema_version": "omega_activation_binding_v1",
        "binding_id": "sha256:" + ("d" * 64),
        "campaign_id": "rsi_sas_code_v12_0",
    }

    source_accept_path = active_bundle_dir / "ruleset" / "accept.ir.json"
    source_accept_before = source_accept_path.read_bytes()

    monkeypatch.setattr("cdel.v18_0.omega_promoter_v1._meta_core_root", lambda: fake_meta_core_root)

    activation_bundle_dir, activation_manifest_hash = _build_meta_core_activation_bundle(
        out_dir=out_dir,
        binding_payload=binding_payload,
        binding_hash_hex8="deadbeef",
    )

    assert activation_manifest_hash.startswith("sha256:")
    destination_accept_path = activation_bundle_dir / "ruleset" / "accept.ir.json"
    destination_accept_path.write_text('{"tampered":true}\n', encoding="utf-8")

    assert source_accept_path.read_bytes() == source_accept_before
