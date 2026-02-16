"""Deterministic SH1 capability scaffold materializer."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from cdel.v1_7r.canon import write_canon_json


_TOKEN_RE = re.compile(r"[^a-z0-9]+")


def _slug_token(value: str) -> str:
    out = _TOKEN_RE.sub("_", str(value).strip().lower()).strip("_")
    return out or "x"


def _wrapper_source(domain_slug: str) -> str:
    return (
        f"\"\"\"Generated SH1 skill campaign wrapper for `{domain_slug}`.\"\"\"\n\n"
        "from __future__ import annotations\n\n"
        "from orchestrator.omega_skill_generated_sh1_v1 import main\n\n\n"
        "if __name__ == \"__main__\":\n"
        "    raise SystemExit(main())\n"
    )


def materialize_sh1_scaffold(*, repo_root: Path, domain_slug: str) -> dict[str, Any]:
    root = repo_root.resolve()
    slug = _slug_token(domain_slug)
    campaign_id = f"rsi_domain_skill_{slug}_v1"
    capability_id = f"RSI_DOMAIN_SKILL_{slug.upper()}_V1"
    module_rel = Path("orchestrator") / f"omega_skill_{slug}_v1.py"
    module_path = (root / module_rel).resolve()
    pack_rel = Path("campaigns") / campaign_id / f"rsi_domain_skill_{slug}_pack_v1.json"
    pack_path = (root / pack_rel).resolve()

    module_path.parent.mkdir(parents=True, exist_ok=True)
    src = _wrapper_source(slug)
    if not module_path.exists() or module_path.read_text(encoding="utf-8") != src:
        module_path.write_text(src, encoding="utf-8")

    pack_payload = {
        "schema_version": f"rsi_domain_skill_{slug}_pack_v1",
        "campaign_id": campaign_id,
        "domain_slug": slug,
        "skill_prompt": f"synthesize capability scaffold for domain:{slug}",
    }
    pack_path.parent.mkdir(parents=True, exist_ok=True)
    write_canon_json(pack_path, pack_payload)

    registry_row = {
        "campaign_id": campaign_id,
        "capability_id": capability_id,
        "orchestrator_module": f"orchestrator.omega_skill_{slug}_v1",
        "verifier_module": "cdel.v18_0.verify_rsi_omega_skill_report_v1",
        "campaign_pack_rel": pack_rel.as_posix(),
        "state_dir_rel": f"daemon/{campaign_id}/state",
        "promotion_bundle_rel": f"daemon/{campaign_id}/state/promotion/*.omega_skill_generated_sh1_promotion_bundle_v1.json",
        "risk_class": "LOW",
        "cooldown_ticks_u64": 8,
        "budget_cost_hint_q32": {"q": 1073741824},
        "enabled": True,
    }
    return {
        "domain_slug": slug,
        "campaign_id": campaign_id,
        "capability_id": capability_id,
        "module_rel": module_rel.as_posix(),
        "pack_rel": pack_rel.as_posix(),
        "registry_row": registry_row,
    }


def main() -> None:
    parser = argparse.ArgumentParser(prog="omega_skill_scaffold_generator_v1")
    parser.add_argument("--repo_root", default=".")
    parser.add_argument("--domain_slug", required=True)
    args = parser.parse_args()

    payload = materialize_sh1_scaffold(
        repo_root=Path(args.repo_root).expanduser().resolve(),
        domain_slug=str(args.domain_slug),
    )
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
