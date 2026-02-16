from __future__ import annotations

from pathlib import Path

from orchestrator.common.run_invoker_v1 import _build_env, _env_fingerprint, run_module


def test_run_invoker_propagates_polymath_store_root_env(monkeypatch, tmp_path: Path) -> None:
    store_root = (tmp_path / "polymath_store").resolve()
    store_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("OMEGA_POLYMATH_STORE_ROOT", store_root.as_posix())

    module_path = tmp_path / "env_probe_v1.py"
    module_path.write_text(
        "import os\n"
        "print(os.environ.get('OMEGA_POLYMATH_STORE_ROOT', ''))\n",
        encoding="utf-8",
    )

    output_dir = tmp_path / "out"
    receipt = run_module(
        py_module="env_probe_v1",
        argv=[],
        cwd=tmp_path,
        output_dir=output_dir,
    )
    assert int(receipt["return_code"]) == 0
    stdout_text = Path(receipt["stdout_path"]).read_text(encoding="utf-8").strip()
    assert stdout_text == store_root.as_posix()

    expected_env = _build_env()
    assert expected_env["OMEGA_POLYMATH_STORE_ROOT"] == store_root.as_posix()
    assert str(receipt["env_fingerprint_hash"]) == _env_fingerprint(expected_env)
