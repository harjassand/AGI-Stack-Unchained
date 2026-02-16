#!/usr/bin/env python3
import math


def alpha_schedule(i: int, alpha_total: float) -> float:
    return alpha_total * (6.0 / (math.pi ** 2)) * (1.0 / (i ** 2))


def simulate_deployment(alpha_total: float, attempts: int = 100) -> None:
    alpha_spent = 0.0
    attempt_counter = 0

    for i in range(1, attempts + 1):
        attempt_counter += 1
        alpha_i = alpha_schedule(i, alpha_total)
        if alpha_spent + alpha_i > alpha_total:
            # Refusal condition: no further spend.
            break
        # Simulate a PASS every 10 attempts.
        passed = (i % 10 == 0)
        alpha_spent += alpha_i if passed else alpha_i

        if alpha_spent > alpha_total + 1e-12:
            raise AssertionError("alpha_spent exceeds alpha_total")

    if attempt_counter < 1:
        raise AssertionError("attempt_counter not incremented")


def simulate_research(fdr_target: float, attempts: int = 50) -> None:
    w0 = fdr_target / 2.0
    reward = fdr_target / 2.0
    wealth = w0

    def gamma(j: int) -> float:
        return (6.0 / (math.pi ** 2)) * (1.0 / (j ** 2))

    rejections = []

    for j in range(1, attempts + 1):
        alpha_raw = gamma(j) * w0
        for k, r_k in enumerate(rejections, start=1):
            alpha_raw += gamma(j - k) * r_k * reward
        alpha_j = min(alpha_raw, wealth)
        # Simulate a rejection every 7 attempts.
        r_j = 1 if (j % 7 == 0) else 0
        wealth = wealth - alpha_j + r_j * reward
        rejections.append(r_j)

        if wealth < -1e-12:
            raise AssertionError("fdr_wealth went negative")


def main() -> int:
    simulate_deployment(alpha_total=0.05)
    simulate_research(fdr_target=0.1)
    print("alpha ledger sim OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
