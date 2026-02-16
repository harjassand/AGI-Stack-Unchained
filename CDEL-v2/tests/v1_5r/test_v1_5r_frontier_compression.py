from cdel.v1_5r.family_dsl.runtime import compute_signature
from cdel.v1_5r.sr_cegar.frontier import compress_frontier


def _family(fid_suffix: str) -> dict:
    family_hash = "sha256:" + fid_suffix * 64
    signature = compute_signature({"family_hash": family_hash})
    return {"family_id": family_hash, "signature": signature}


def test_frontier_compression_deterministic() -> None:
    families = [_family("a"), _family("b"), _family("c")]
    witnesses = [
        {"family_id": families[0]["family_id"], "family_signature": families[0]["signature"]},
        {"family_id": families[1]["family_id"], "family_signature": families[1]["signature"]},
    ]
    selected_a, report_a = compress_frontier(families, witnesses, m_frontier=2)
    selected_b, report_b = compress_frontier(families, witnesses, m_frontier=2)
    assert [f["family_id"] for f in selected_a] == [f["family_id"] for f in selected_b]
    assert report_a == report_b
