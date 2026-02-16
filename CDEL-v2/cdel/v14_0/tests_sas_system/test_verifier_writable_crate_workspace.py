from __future__ import annotations

from pathlib import Path

from cdel.v14_0 import verify_rsi_sas_system_v1 as v14_verify


def test_prepare_writable_crate_dir_uses_state_workspace(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    src_crate = repo_root / "CDEL-v2" / "cdel" / "v14_0" / "rust" / "cdel_workmeter_rs_v1"
    src_src = src_crate / "src"
    src_src.mkdir(parents=True, exist_ok=True)
    (src_crate / "Cargo.toml").write_text("[package]\nname='x'\nversion='0.1.0'\n", encoding="utf-8")
    (src_src / "lib.rs").write_text("pub fn x() -> i32 { 1 }\n", encoding="utf-8")
    (src_src / "lib.rs").chmod(0o444)

    monkeypatch.setattr(v14_verify, "_repo_root", lambda: repo_root)

    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    writable = v14_verify._prepare_writable_crate_dir(state_dir)

    assert writable != src_crate
    assert str(writable).startswith(str(state_dir))
    copied = writable / "src" / "lib.rs"
    copied.write_text("pub fn x() -> i32 { 2 }\n", encoding="utf-8")
    assert copied.read_text(encoding="utf-8").strip().endswith("{ 2 }")
