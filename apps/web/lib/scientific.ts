export function formatScientificValue(value: number | null | undefined, digits = 3): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return value.toFixed(digits);
}

export function isExcluded(state: string): boolean {
  return state === "EXCLUDED";
}

export function provenanceLabel(snapshotId: string, seed: number): string {
  return `${snapshotId} · seed ${seed}`;
}
