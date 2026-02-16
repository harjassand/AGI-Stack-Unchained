from __future__ import annotations

from pathlib import Path

from cdel.v1_5r.canon import sha256_prefixed
from cdel.v1_5r.portfolio.generator import build_from_generator, load_generator


def _hash_tree(root: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            rel = path.relative_to(root).as_posix()
            hashes[rel] = sha256_prefixed(path.read_bytes())
    return hashes


def test_portfolio_generator_determinism(tmp_path: Path) -> None:
    generator = {
        "schema": "portfolio_generator_v1",
        "schema_version": 1,
        "generator_id": "test_gen",
        "motif_action_names": ["A", "B", "C", "D", "E", "F"],
        "portfolios": [
            {"portfolio_id": "p1", "seed_label": "seed_a", "families": 3, "repeats_per_family": 4},
            {"portfolio_id": "p2", "seed_label": "seed_b", "families": 3, "repeats_per_family": 4},
        ],
    }
    out_a = tmp_path / "out_a"
    out_b = tmp_path / "out_b"
    build_from_generator(generator, out_a)
    build_from_generator(generator, out_b)
    assert _hash_tree(out_a) == _hash_tree(out_b)
