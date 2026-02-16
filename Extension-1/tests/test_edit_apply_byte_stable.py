from pathlib import Path

from self_improve_code_v1.ops.token_edit_v1 import apply_edit_to_text, read_text_normalized, write_text_lf


def test_apply_edit_to_text():
    text = "abc123def"
    out = apply_edit_to_text(text, (3, 6), "XYZ")
    assert out == "abcXYZdef"


def test_read_write_lf(tmp_path: Path):
    p = tmp_path / "file.txt"
    p.write_bytes(b"a\r\n")
    text = read_text_normalized(str(p))
    assert text == "a\n"
    write_text_lf(str(p), text)
    assert p.read_bytes() == b"a\n"
