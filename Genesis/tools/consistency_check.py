#!/usr/bin/env python3
import json
import re
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
ROOT = TOOLS_DIR.parents[0]

sys.path.insert(0, str(TOOLS_DIR))
import canonicalize as canon  # noqa: E402

SCHEMA_PATH = ROOT / "schema" / "capsule.schema.json"
ENUMS_DOC = ROOT / "docs" / "enums.md"
CONTRACT_DOC = ROOT / "docs" / "contract_taxonomy.md"
README_PATH = ROOT / "README.md"
SPEC_VERSION_PATH = ROOT / "SPEC_VERSION"
EXAMPLES_DIR = ROOT / "examples"


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as fp:
        return json.load(fp)


def extract_json_block(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    match = re.search(r"```json\n(.*?)\n```", text, re.DOTALL)
    if not match:
        raise ValueError(f"no JSON block found in {path}")
    return json.loads(match.group(1))


def check_enums(schema: dict, enums: dict) -> None:
    schema_artifacts = schema["properties"]["artifact_type"]["enum"]
    if schema_artifacts != enums["artifact_types"]:
        raise ValueError("artifact_types enum mismatch between schema and docs")

    schema_grades = schema["$defs"]["budget_bid"]["properties"]["grade"]["enum"]
    if schema_grades != enums["grades"]:
        raise ValueError("grades enum mismatch between schema and docs")

    schema_effects = schema["$defs"]["effect"]["enum"]
    if schema_effects != enums["effect_permissions"]:
        raise ValueError("effect_permissions enum mismatch between schema and docs")

    schema_clause_types = schema["$defs"]["spec_clause"]["properties"]["clause_type"]["enum"]
    if schema_clause_types != enums["clause_types"]:
        raise ValueError("clause_types enum mismatch between schema and docs")


def check_spec_version(schema: dict) -> None:
    spec_version = SPEC_VERSION_PATH.read_text(encoding="utf-8").strip()
    pattern = schema["properties"]["schema_version"]["pattern"]
    if not re.fullmatch(pattern, spec_version):
        raise ValueError("SPEC_VERSION does not match capsule.schema.json schema_version pattern")

    readme = README_PATH.read_text(encoding="utf-8")
    if spec_version not in readme:
        raise ValueError("SPEC_VERSION value not referenced in README.md")


def check_canonicalization_id(enums: dict) -> None:
    canon_id_doc = enums.get("canonicalization_id")
    if canon_id_doc != canon.CANON_ID:
        raise ValueError("canonicalization id mismatch between docs and tool")

    canonicalization_doc = (ROOT / "docs" / "canonicalization.md").read_text(encoding="utf-8")
    match = re.search(r"Canonicalization ID: `([^`]+)`", canonicalization_doc)
    if not match:
        raise ValueError("Canonicalization ID not found in docs/canonicalization.md")
    if match.group(1) != canon.CANON_ID:
        raise ValueError("canonicalization id mismatch between canonicalization.md and tool")


def check_examples(requirements: dict) -> None:
    required_blocks = requirements["required_blocks"]
    artifact_requirements = requirements["artifact_requirements"]

    for path in sorted(EXAMPLES_DIR.glob("*.capsule.json")):
        capsule = load_json(path)
        artifact_type = capsule["artifact_type"]
        contract = capsule["contract"]

        for block in required_blocks:
            if block not in contract:
                raise ValueError(f"{path} missing contract block {block}")

        func_count = len(contract["functional_spec"]["clauses"])
        safety_count = len(contract["safety_spec"]["invariants"]) + len(contract["safety_spec"]["forbidden_behaviors"])
        req = artifact_requirements.get(artifact_type)
        if not req:
            raise ValueError(f"no requirements defined for {artifact_type}")

        if func_count < req["min_functional_clauses"]:
            raise ValueError(f"{path} has insufficient functional clauses")
        if safety_count < req["min_safety_clauses"]:
            raise ValueError(f"{path} has insufficient safety clauses")

        if req.get("requires_identifiability_witness"):
            certs = capsule["evidence"]["certificates"]
            if not any(c.get("cert_type") == "identifiability_witness" for c in certs):
                raise ValueError(f"{path} missing identifiability_witness certificate")


def main() -> int:
    schema = load_json(SCHEMA_PATH)
    enums = extract_json_block(ENUMS_DOC)
    requirements = extract_json_block(CONTRACT_DOC)

    check_enums(schema, enums)
    check_spec_version(schema)
    check_canonicalization_id(enums)
    check_examples(requirements)

    print("consistency check OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
