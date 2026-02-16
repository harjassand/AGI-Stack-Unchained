from __future__ import annotations

from cdel.v14_0.sas_system_build_v1 import scan_forbidden_tokens


def test_rust_forbidden_token_unsafe() -> None:
    hits = scan_forbidden_tokens("unsafe fn")
    assert "unsafe" in hits


def test_rust_forbidden_token_std_net() -> None:
    hits = scan_forbidden_tokens("use std::net::TcpStream;")
    assert "std::net" in hits
