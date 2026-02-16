export type Q32 = { q: number };

const Q32_ONE = 2 ** 32;

export function q32ToFloat(input: Q32 | null | undefined): number {
  if (!input || typeof input.q !== "number") {
    return 0;
  }
  return input.q / Q32_ONE;
}

export function q32Percent(input: Q32 | null | undefined): number {
  return q32ToFloat(input) * 100;
}

export function formatPercent(value: number): string {
  return `${Math.max(0, Math.min(100, value)).toFixed(1)}%`;
}
