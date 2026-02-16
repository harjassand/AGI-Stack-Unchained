"""FFT helpers over Goldilocks field (v1).

This implements radix-2 Cooley-Tukey FFT/IFFT for power-of-two sizes.

All arithmetic is done with Python integers mod p, deterministic and float-free.
"""

from __future__ import annotations

from .gld_field_v1 import P_GOLDILOCKS, inv, mul, sub


def fft_inplace(a: list[int], omega: int) -> None:
    """In-place FFT.

    Interprets `a` as coefficients; outputs evaluations at powers of omega.
    """

    n = len(a)
    if n <= 0 or (n & (n - 1)) != 0:
        raise ValueError("len(a) must be power of two")
    w = int(omega) % P_GOLDILOCKS

    # Bit-reversal permutation.
    j = 0
    for i in range(1, n):
        bit = n >> 1
        while j & bit:
            j ^= bit
            bit >>= 1
        j ^= bit
        if i < j:
            a[i], a[j] = a[j], a[i]

    length = 2
    while length <= n:
        wlen = pow(w, n // length, P_GOLDILOCKS)
        for i in range(0, n, length):
            ww = 1
            half = length // 2
            for j in range(half):
                u = int(a[i + j]) % P_GOLDILOCKS
                v = (int(a[i + j + half]) % P_GOLDILOCKS) * ww % P_GOLDILOCKS
                a[i + j] = (u + v) % P_GOLDILOCKS
                a[i + j + half] = (u - v) % P_GOLDILOCKS
                ww = (ww * wlen) % P_GOLDILOCKS
        length <<= 1


def ifft_inplace(a: list[int], omega: int) -> None:
    """In-place inverse FFT.

    Interprets `a` as evaluations at powers of omega; outputs coefficients.
    """

    n = len(a)
    inv_omega = inv(int(omega) % P_GOLDILOCKS)
    fft_inplace(a, inv_omega)
    inv_n = inv(n % P_GOLDILOCKS)
    for i in range(n):
        a[i] = mul(int(a[i]), inv_n)


def interpolate_poly_from_evals(values_n: list[int], omega_n: int) -> list[int]:
    """Return monomial coefficients for degree < n polynomial from n evaluations."""

    coeffs = [int(v) % P_GOLDILOCKS for v in list(values_n)]
    ifft_inplace(coeffs, omega_n)
    return coeffs


def eval_poly_on_coset(
    *,
    coeffs: list[int],
    omega_m: int,
    shift: int,
    m: int,
) -> list[int]:
    """Evaluate polynomial (given monomial coeffs) on coset shift*<omega_m>.

    `m` must be a power of two, and len(coeffs) <= m.
    """

    mm = int(m)
    if mm <= 0 or (mm & (mm - 1)) != 0:
        raise ValueError("m must be pow2")
    if len(coeffs) > mm:
        raise ValueError("coeffs too long")

    out = [0] * mm
    s = int(shift) % P_GOLDILOCKS
    # Twiddle coefficients: c_k' = c_k * shift^k, so FFT yields p(shift*omega^i).
    pow_s = 1
    for k in range(mm):
        if k < len(coeffs):
            out[k] = (int(coeffs[k]) % P_GOLDILOCKS) * pow_s % P_GOLDILOCKS
        else:
            out[k] = 0
        pow_s = (pow_s * s) % P_GOLDILOCKS

    fft_inplace(out, omega_m)
    return out


def fold_fri_layer(
    *,
    evals: list[int],
    domain_x: list[int],
    alpha: int,
) -> list[int]:
    """Compute next FRI layer evaluations by folding pairs (x, -x).

    `evals` length must be even. `domain_x` length must match and contain x points.
    Returns evals_next length = len(evals)//2.
    """

    n = len(evals)
    if n <= 0 or (n & 1) != 0:
        raise ValueError("evals length must be even")
    if len(domain_x) != n:
        raise ValueError("domain_x length mismatch")

    half = n // 2
    a = int(alpha) % P_GOLDILOCKS
    inv2 = (P_GOLDILOCKS + 1) // 2  # since p is odd
    out = [0] * half

    for i in range(half):
        f_x = int(evals[i]) % P_GOLDILOCKS
        f_mx = int(evals[i + half]) % P_GOLDILOCKS
        x = int(domain_x[i]) % P_GOLDILOCKS
        if x == 0:
            raise ValueError("domain contains 0; invalid for FRI fold")

        even = (f_x + f_mx) * inv2 % P_GOLDILOCKS
        odd = (f_x - f_mx) * inv2 % P_GOLDILOCKS
        odd = odd * inv(x) % P_GOLDILOCKS
        out[i] = (even + a * odd) % P_GOLDILOCKS

    return out


def poly_degree_from_evals(
    *,
    evals: list[int],
    omega: int,
    max_degree_inclusive: int,
) -> bool:
    """Return True iff interpolated polynomial degree <= max_degree_inclusive."""

    coeffs = [int(v) % P_GOLDILOCKS for v in list(evals)]
    ifft_inplace(coeffs, omega)
    md = int(max_degree_inclusive)
    if md < 0:
        return False
    # Degree <= md means coefficients above md are 0.
    for i in range(md + 1, len(coeffs)):
        if int(coeffs[i]) % P_GOLDILOCKS != 0:
            return False
    return True


__all__ = [
    "eval_poly_on_coset",
    "fft_inplace",
    "fold_fri_layer",
    "ifft_inplace",
    "interpolate_poly_from_evals",
    "poly_degree_from_evals",
]
