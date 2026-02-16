from orchestrator.pyut_utils import extract_python_source, python_source_payload


def test_pyut_source_roundtrip() -> None:
    source = "def abs_int(x: int) -> int:\n    return x\n"
    payload = python_source_payload(name="abs_int_code", source=source, concept="py.abs_int")
    assert extract_python_source(payload) == source
