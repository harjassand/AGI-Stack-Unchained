#!/usr/bin/env python3

def simulate_compute(compute_total: int, wall_total_ms: int) -> None:
    compute_spent = 0
    wall_spent = 0
    entries = [(200, 1000), (300, 2000), (400, 3000), (200, 1000)]

    for units, wall_ms in entries:
        if compute_spent + units > compute_total or wall_spent + wall_ms > wall_total_ms:
            # Refusal condition.
            continue
        compute_spent += units
        wall_spent += wall_ms
        if compute_spent > compute_total:
            raise AssertionError("compute_spent exceeds compute_total")
        if wall_spent > wall_total_ms:
            raise AssertionError("wall_spent exceeds wall_total_ms")


def main() -> int:
    simulate_compute(compute_total=1000, wall_total_ms=5000)
    print("compute ledger sim OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
