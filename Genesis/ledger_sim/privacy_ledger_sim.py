#!/usr/bin/env python3

def simulate_privacy(epsilon_total: float, delta_total: float) -> None:
    epsilon_spent = 0.0
    delta_spent = 0.0
    query_counter = 0

    spends = [(0.1, 1e-5), (0.2, 2e-5), (0.3, 3e-5), (0.4, 4e-5)]
    for eps_i, del_i in spends:
        query_counter += 1
        if epsilon_spent + eps_i > epsilon_total or delta_spent + del_i > delta_total:
            # Refusal condition.
            continue
        epsilon_spent += eps_i
        delta_spent += del_i
        if epsilon_spent > epsilon_total + 1e-12:
            raise AssertionError("epsilon_spent exceeds epsilon_total")
        if delta_spent > delta_total + 1e-12:
            raise AssertionError("delta_spent exceeds delta_total")

    if query_counter < 1:
        raise AssertionError("query_counter not incremented")


def main() -> int:
    simulate_privacy(epsilon_total=0.5, delta_total=1e-3)
    print("privacy ledger sim OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
