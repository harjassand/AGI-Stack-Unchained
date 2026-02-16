from __future__ import annotations

from pathlib import Path

from cdel.v18_0 import omega_observer_v1 as observer
from cdel.v1_7r.canon import write_canon_json


def _write_bundle(path: Path, *, theory_id: str, rmse_q: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_canon_json(
        path,
        {
            "schema_version": "sas_science_promotion_bundle_v1",
            "discovery_bundle": {
                "theory_id": theory_id,
                "heldout_metrics": {
                    "rmse_pos1_q32": {
                        "schema_version": "q32_v1",
                        "shift": 32,
                        "q": str(rmse_q),
                    }
                },
            },
        },
    )


def test_science_metric_from_promotion_bundle(tmp_path, monkeypatch) -> None:
    run_a = (
        tmp_path
        / "runs"
        / "rsi_sas_science_v13_0_demo_001"
        / "daemon"
        / "rsi_sas_science_v13_0"
        / "state"
        / "promotion"
        / "sha256_1111.sas_science_promotion_bundle_v1.json"
    )
    run_b = (
        tmp_path
        / "runs"
        / "rsi_sas_science_v13_0_demo_002"
        / "daemon"
        / "rsi_sas_science_v13_0"
        / "state"
        / "promotion"
        / "sha256_2222.sas_science_promotion_bundle_v1.json"
    )

    _write_bundle(run_a, theory_id="sha256:" + ("1" * 64), rmse_q=700)
    _write_bundle(run_b, theory_id="sha256:" + ("2" * 64), rmse_q=321)

    monkeypatch.setattr(observer, "repo_root", lambda: tmp_path)

    science_q, source = observer._load_science_metric_global()  # noqa: SLF001
    assert science_q == 321
    assert source["schema_id"] == "sas_science_promotion_bundle_v1"
    assert source["producer_campaign_id"] == "rsi_sas_science_v13_0"
