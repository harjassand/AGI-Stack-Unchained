import pytest

from self_improve_code_v1.ops.token_locator_v1 import locate_token_span, TokenLocationError


def test_anchor_single_match():
    content = "X=1\nY=2\n"
    selector = {"anchor_before": "X=", "anchor_after": "\n"}
    start, end = locate_token_span(content, selector)
    assert content[start:end] == "1"


def test_anchor_multiple_matches_error():
    content = "X=1\nX=2\n"
    selector = {"anchor_before": "X=", "anchor_after": "\n"}
    with pytest.raises(TokenLocationError):
        locate_token_span(content, selector)


def test_regex_single_match():
    content = "val=123\n"
    selector = {"regex_single_match": r"\d+"}
    start, end = locate_token_span(content, selector)
    assert content[start:end] == "123"
