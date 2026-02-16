from copy import deepcopy


def recompute_efe_report(report: dict) -> dict:
    """Recompute totals and tie-break from a provided efe_report_v1 object."""
    out = deepcopy(report)
    policies = []
    for policy in out.get("policies", []):
        total = (
            int(policy["risk_fp"])
            + int(policy["ambiguity_fp"])
            + int(policy["epistemic_fp"])
            + int(policy["complexity_fp"])
        )
        policy = dict(policy)
        policy["total_G_fp"] = total
        policies.append(policy)

    def _key(p: dict) -> tuple[int, int, str]:
        return (int(p["total_G_fp"]), int(p["risk_fp"]), str(p["policy_id"]))

    policies_sorted = sorted(policies, key=_key)
    out["policies"] = sorted(policies, key=lambda p: p["policy_id"])
    chosen = policies_sorted[0] if policies_sorted else None
    out["chosen_policy_id"] = chosen["policy_id"] if chosen else ""
    out["chosen_action_token"] = chosen["actions"][0] if chosen else ""
    compared = policies_sorted[1]["policy_id"] if len(policies_sorted) > 1 else ""
    out["tie_break_witness"] = {
        "rule": "min_total_G_then_min_risk_then_lex",
        "compared_against_policy_id": compared,
    }
    return out
