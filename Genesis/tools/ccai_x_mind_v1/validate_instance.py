import json
import sys
from pathlib import Path

try:
    from jsonschema import Draft202012Validator
except Exception as exc:
    print(f"jsonschema not available: {exc}")
    sys.exit(2)

from .canonical_json import assert_no_floats, to_gcj1_bytes

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = ROOT / "schema" / "ccai_x_mind_v1"

SCHEMAS = {
    "markov_blanket_spec_v1": SCHEMA_DIR / "markov_blanket_spec_v1.schema.json",
    "do_map_v1": SCHEMA_DIR / "do_map_v1.schema.json",
    "intervention_log_entry_v1": SCHEMA_DIR / "intervention_log_entry_v1.schema.json",
    "causal_mechanism_registry_v1": SCHEMA_DIR / "causal_mechanism_registry_v1.schema.json",
    "inference_kernel_isa_v1": SCHEMA_DIR / "inference_kernel_isa_v1.schema.json",
    "inference_kernel_program_v1": SCHEMA_DIR / "inference_kernel_program_v1.schema.json",
    "workspace_state_v1": SCHEMA_DIR / "workspace_state_v1.schema.json",
    "efe_report_v1": SCHEMA_DIR / "efe_report_v1.schema.json",
    "policy_prior_v1": SCHEMA_DIR / "policy_prior_v1.schema.json",
    "preference_capsule_v1": SCHEMA_DIR / "preference_capsule_v1.schema.json",
    "coherence_operator_v1": SCHEMA_DIR / "coherence_operator_v1.schema.json",
    "affordance_latent_v1": SCHEMA_DIR / "affordance_latent_v1.schema.json",
    "ccai_x_mind_patch_candidate_mind_v1": SCHEMA_DIR
    / "ccai_x_mind_patch_candidate_manifest_v1.schema.json",
}


class FloatNotAllowed(ValueError):
    pass


class CcaiXValidationError(Exception):
    def __init__(self, code: str, details: str = "") -> None:
        self.code = code
        self.details = details
        super().__init__(code)


ERR_WORKSPACE_MARGINAL_LENGTH_MISMATCH = "CCAI_X_ERR_WORKSPACE_MARGINAL_LENGTH_MISMATCH"


def _reject_float(value: str):
    raise FloatNotAllowed(f"float token not allowed: {value}")


def load_json_strict(text: str):
    try:
        return json.loads(text, parse_float=_reject_float)
    except FloatNotAllowed:
        raise
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {exc}")


def _load_schema(schema_path: Path) -> dict:
    return json.loads(schema_path.read_text(encoding="utf-8"))


def _validate_schema(obj: dict) -> None:
    fmt = obj.get("format")
    if not fmt or fmt not in SCHEMAS:
        raise ValueError(f"unknown or missing format: {fmt}")
    schema = _load_schema(SCHEMAS[fmt])
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(obj), key=lambda e: e.path)
    if errors:
        err = errors[0]
        loc = "/".join(str(p) for p in err.path)
        raise ValueError(f"schema error at {loc or '<root>'}: {err.message}")


def _assert_sorted(values, name: str) -> None:
    if values != sorted(values):
        raise ValueError(f"{name} must be sorted")


def _assert_strictly_increasing(values, name: str) -> None:
    if values != sorted(values):
        raise ValueError(f"{name} must be sorted")
    for idx in range(len(values) - 1):
        if values[idx] >= values[idx + 1]:
            raise ValueError(f"{name} must be strictly increasing")


def _check_markov_blanket(obj: dict) -> None:
    policy = obj["side_channel_policy"]
    _assert_sorted(policy["env_var_allowlist"], "env_var_allowlist")
    _assert_sorted(policy["fs_read_allowlist_prefixes"], "fs_read_allowlist_prefixes")
    _assert_sorted(policy["fs_write_allowlist_prefixes"], "fs_write_allowlist_prefixes")


def _check_do_map(obj: dict) -> None:
    entries = obj["entries"]
    keys = [(e["action_token"], e["target_mechanism_id"]) for e in entries]
    if keys != sorted(keys):
        raise ValueError("do_map.entries must be sorted by action_token, target_mechanism_id")


def _check_registry(obj: dict) -> None:
    variables = obj["variables"]
    _assert_sorted([v["var_id"] for v in variables], "variables.var_id")
    for var in variables:
        domain = var["domain"]
        if domain["kind"] == "int_enum":
            _assert_sorted(domain["values"], "domain.values")

    mechanisms = obj["mechanisms"]
    _assert_sorted([m["mechanism_id"] for m in mechanisms], "mechanisms.mechanism_id")
    for mech in mechanisms:
        _assert_sorted(mech["parents"], f"mechanism.{mech['mechanism_id']}.parents")
        _assert_sorted(
            [c["claim_id"] for c in mech["invariance_claims"]],
            f"mechanism.{mech['mechanism_id']}.invariance_claims",
        )
        _assert_sorted(
            mech["identifiability"]["identified_by_interventions"],
            f"mechanism.{mech['mechanism_id']}.identified_by_interventions",
        )


def _check_isa(obj: dict) -> None:
    _assert_sorted(obj["primitives"], "primitives")


def _check_program(obj: dict) -> None:
    stages = obj["schedule"]["stages"]
    _assert_sorted([s["stage_id"] for s in stages], "schedule.stages.stage_id")


def _check_workspace_state(obj: dict) -> None:
    beliefs = obj["beliefs"]
    _assert_sorted([m["var_id"] for m in beliefs["variable_marginals"]], "variable_marginals")
    for marginal in beliefs["variable_marginals"]:
        _assert_strictly_increasing(marginal["support"], f"support.{marginal['var_id']}")
    _assert_sorted([p["param_id"] for p in beliefs["parameter_estimates"]], "parameter_estimates")


def _check_efe_report(obj: dict) -> None:
    _assert_sorted([p["policy_id"] for p in obj["policies"]], "policies")


def _check_policy_prior(obj: dict) -> None:
    _assert_sorted([p["policy_id"] for p in obj["policy_logprior"]], "policy_logprior")


def _check_preference_capsule(obj: dict) -> None:
    _assert_sorted([m["metric_id"] for m in obj["metrics"]], "metrics")
    _assert_sorted(obj["admissibility"]["forbidden_action_tokens"], "forbidden_action_tokens")


def _check_candidate_manifest(obj: dict) -> None:
    _assert_sorted([a["path"] for a in obj["artifacts"]], "artifacts")


def _check_workspace_invariants(obj: dict) -> None:
    beliefs = obj["beliefs"]
    for marginal in beliefs["variable_marginals"]:
        support = marginal["support"]
        prob_fp = marginal["prob_fp"]
        if len(support) != len(prob_fp):
            raise CcaiXValidationError(ERR_WORKSPACE_MARGINAL_LENGTH_MISMATCH, "")
        for value in prob_fp:
            if value < 0:
                raise ValueError("prob_fp must be non-negative")


def _check_invariants(obj: dict) -> None:
    fmt = obj.get("format")
    if fmt == "workspace_state_v1":
        _check_workspace_invariants(obj)


def _check_sorted(obj: dict) -> None:
    fmt = obj.get("format")
    if fmt == "markov_blanket_spec_v1":
        _check_markov_blanket(obj)
    elif fmt == "do_map_v1":
        _check_do_map(obj)
    elif fmt == "causal_mechanism_registry_v1":
        _check_registry(obj)
    elif fmt == "inference_kernel_isa_v1":
        _check_isa(obj)
    elif fmt == "inference_kernel_program_v1":
        _check_program(obj)
    elif fmt == "workspace_state_v1":
        _check_workspace_state(obj)
    elif fmt == "efe_report_v1":
        _check_efe_report(obj)
    elif fmt == "policy_prior_v1":
        _check_policy_prior(obj)
    elif fmt == "preference_capsule_v1":
        _check_preference_capsule(obj)
    elif fmt == "ccai_x_mind_patch_candidate_mind_v1":
        _check_candidate_manifest(obj)
    elif fmt == "coherence_operator_v1":
        _assert_sorted(obj["merge_policy"], "merge_policy")


def _assert_canonical(raw_bytes: bytes, obj) -> None:
    canonical = to_gcj1_bytes(obj)
    if raw_bytes != canonical:
        raise ValueError("non-canonical JSON (GCJ-1) detected")


def validate_json_bytes(raw_bytes: bytes, source: str = "<memory>") -> dict:
    text = raw_bytes.decode("utf-8")
    obj = load_json_strict(text)
    assert_no_floats(obj)
    _assert_canonical(raw_bytes, obj)
    _validate_schema(obj)
    _check_invariants(obj)
    _check_sorted(obj)
    return obj


def validate_json_file(path: Path) -> dict:
    raw_bytes = path.read_bytes()
    return validate_json_bytes(raw_bytes, str(path))


def validate_jsonl_file(path: Path) -> None:
    raw_bytes = path.read_bytes()
    if not raw_bytes.endswith(b"\n"):
        raise ValueError("JSONL file must end with LF")
    lines = raw_bytes.split(b"\n")
    for idx, line in enumerate(lines[:-1]):
        if not line:
            raise ValueError(f"empty JSONL line at {idx}")
        obj = validate_json_bytes(line, f"{path}:{idx}")
        fmt = obj.get("format")
        if fmt not in ("intervention_log_entry_v1", "workspace_state_v1", "efe_report_v1"):
            raise ValueError(f"unexpected format in JSONL line {idx}")


def validate_path(path: Path) -> None:
    if path.suffix == ".jsonl":
        validate_jsonl_file(path)
    else:
        validate_json_file(path)
