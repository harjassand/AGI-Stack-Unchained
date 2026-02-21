"""Generate deterministic epistemic canary evidence from a state root."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from cdel.v1_7r.canon import write_canon_json
from cdel.v18_0.omega_common_v1 import canon_hash_obj, load_canon_dict


def _failure_counts(refutation_paths: list[Path]) -> dict[str, int]:
    out: dict[str, int] = {}
    for path in refutation_paths:
        payload = load_canon_dict(path)
        reason = str(payload.get("reason_code", "")).strip().lower() or "unknown"
        key = "failure_" + "".join(ch if ch.isalnum() else "_" for ch in reason).strip("_")
        out[key] = int(out.get(key, 0)) + 1
    return {key: out[key] for key in sorted(out.keys())}


def build_canary_bundle(state_root: Path) -> dict[str, Any]:
    epi_root = state_root.resolve() / "epistemic"
    capsule_paths = sorted((epi_root / "capsules").glob("sha256_*.epistemic_capsule_v1.json"), key=lambda p: p.as_posix())
    refutation_paths = sorted((epi_root / "refutations").glob("sha256_*.epistemic_capsule_refutation_v1.json"), key=lambda p: p.as_posix())
    graph_paths = sorted((epi_root / "graphs").glob("sha256_*.qxwmr_graph_v1.json"), key=lambda p: p.as_posix())
    manifest_paths = sorted((epi_root / "world" / "manifests").glob("sha256_*.world_snapshot_manifest_v1.json"), key=lambda p: p.as_posix())
    receipt_paths = sorted((epi_root / "world" / "receipts").glob("sha256_*.sealed_ingestion_receipt_v1.json"), key=lambda p: p.as_posix())
    snapshot_paths = sorted((epi_root / "world" / "snapshots").glob("sha256_*.world_snapshot_v1.json"), key=lambda p: p.as_posix())

    payload = {
        "schema_version": "epistemic_canary_bundle_v1",
        "bundle_id": "sha256:" + ("0" * 64),
        "capsule_ids": [f"sha256:{path.name.split('.', 1)[0].split('_', 1)[1]}" for path in capsule_paths],
        "refutation_ids": [f"sha256:{path.name.split('.', 1)[0].split('_', 1)[1]}" for path in refutation_paths],
        "graph_ids": [f"sha256:{path.name.split('.', 1)[0].split('_', 1)[1]}" for path in graph_paths],
        "world_manifest_ids": [f"sha256:{path.name.split('.', 1)[0].split('_', 1)[1]}" for path in manifest_paths],
        "sip_receipt_ids": [f"sha256:{path.name.split('.', 1)[0].split('_', 1)[1]}" for path in receipt_paths],
        "world_snapshot_ids": [f"sha256:{path.name.split('.', 1)[0].split('_', 1)[1]}" for path in snapshot_paths],
        "counts": {
            "capsule_count_u64": int(len(capsule_paths)),
            "refutation_count_u64": int(len(refutation_paths)),
            "graph_count_u64": int(len(graph_paths)),
        },
        "failure_taxonomy": _failure_counts(refutation_paths),
    }
    payload["bundle_id"] = canon_hash_obj({k: v for k, v in payload.items() if k != "bundle_id"})
    return payload


def main() -> None:
    ap = argparse.ArgumentParser(prog="generate_epistemic_canary_bundle_v1")
    ap.add_argument("--state_root", required=True)
    ap.add_argument("--out_path", required=True)
    args = ap.parse_args()
    payload = build_canary_bundle(Path(args.state_root))
    write_canon_json(Path(args.out_path), payload)


if __name__ == "__main__":
    main()
