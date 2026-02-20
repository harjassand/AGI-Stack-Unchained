from __future__ import annotations

from orchestrator.native import native_router_v1


def test_shadow_mode_never_returns_native_authoritative(monkeypatch) -> None:
    native_router_v1.drain_runtime_stats()
    native_router_v1._py_impl_cache.clear()  # type: ignore[attr-defined]

    op_id = "omega_kernel_eval_v1"
    binary_sha = "sha256:" + ("1" * 64)

    monkeypatch.setattr(
        native_router_v1,
        "_policy_for_op",
        lambda query: {
            "op_id": query,
            "py_impl_import": "fake.module:fake_fn",
            "verification_mode": "SHADOW",
            "shadow_calls_u32": 1,
        }
        if query == op_id
        else None,
    )
    monkeypatch.setattr(native_router_v1, "_import_callable", lambda _spec: (lambda *_args: b"py_out"))
    monkeypatch.setattr(native_router_v1, "_active_binary_for_op", lambda _op: binary_sha)
    monkeypatch.setattr(native_router_v1, "_is_disabled", lambda _op, _bin: False)
    monkeypatch.setattr(native_router_v1, "_is_shadow_route_disabled", lambda _op, _bin: False)
    monkeypatch.setattr(native_router_v1, "_shadow_should_dual_run", lambda _op, _bin, _limit: True)
    monkeypatch.setattr(native_router_v1, "_ctypes_load_module", lambda _op, _bin: object())
    monkeypatch.setattr(native_router_v1, "_invoke_bloblist", lambda _handle, _blob: b"py_out")

    out = native_router_v1.route(op_id, b"abc")
    assert out == b"py_out"

    rows = native_router_v1.drain_runtime_stats()
    row = next(r for r in rows if r.get("op_id") == op_id)
    assert int(row.get("py_returned_u64", 0)) == 1
    assert int(row.get("native_returned_u64", 0)) == 0
