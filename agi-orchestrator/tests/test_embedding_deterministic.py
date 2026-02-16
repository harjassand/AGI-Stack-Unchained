from __future__ import annotations

from orchestrator.embedding import dot, embed_text


def test_embedding_deterministic() -> None:
    text = "Return the absolute value of an integer"
    vec1 = embed_text(text)
    vec2 = embed_text(text)
    assert vec1 == vec2
    assert dot(vec1, vec1) > 0
