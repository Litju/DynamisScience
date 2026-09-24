export type Tone = "neutral" | "good" | "warn" | "bad" | "cyan" | "purple";

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

/** Single source of truth for the scientific status vocabulary used across screens. */
export function qualityTone(state: string | null | undefined): Tone {
  switch (state) {
    case "VALID":
    case "COMPLETED":
    case "COMPLETED_MIXEDLM_RANDOM_SLOPE":
    case "ACTIVE":
      return "good";
    case "WARNING":
    case "EXPLORATORY":
    case "PROTOTYPE":
    case "DRAFT":
      return "warn";
    case "EXCLUDED":
    case "FAILED":
    case "DEPRECATED":
      return "bad";
    case "FROZEN":
      return "purple";
    case "SYNTHETIC":
      return "cyan";
    default:
      return "neutral";
  }
}

export interface Vec3 {
  x: number;
  y: number;
  z: number;
}

/**
 * Geometric angle (degrees) at `vertex` between the segments vertex→a and
 * vertex→c. Used for sagittal joint-angle approximations; it is pure geometry
 * on the supplied coordinates and makes no biomechanical assumption beyond the
 * joint definitions.
 */
export function jointAngleDegrees(a: Vec3 | undefined, vertex: Vec3 | undefined, c: Vec3 | undefined): number | null {
  if (!a || !vertex || !c) return null;
  const v1 = [a.x - vertex.x, a.y - vertex.y, a.z - vertex.z];
  const v2 = [c.x - vertex.x, c.y - vertex.y, c.z - vertex.z];
  const dot = v1[0] * v2[0] + v1[1] * v2[1] + v1[2] * v2[2];
  const mag1 = Math.hypot(v1[0], v1[1], v1[2]);
  const mag2 = Math.hypot(v2[0], v2[1], v2[2]);
  if (!mag1 || !mag2) return null;
  const cosine = Math.max(-1, Math.min(1, dot / (mag1 * mag2)));
  return (Math.acos(cosine) * 180) / Math.PI;
}

/** Interval implied by an estimate and a symmetric uncertainty half-width. */
export function uncertaintyInterval(value: number | null, halfWidth: number | null): [number, number] | null {
  if (value === null || halfWidth === null || !Number.isFinite(value) || !Number.isFinite(halfWidth)) return null;
  return [value - halfWidth, value + halfWidth];
}

/** A change is only interpretable against the typical error of a change. */
export function changeExceedsTypicalError(change: number | null, typicalError: number | null): boolean | null {
  if (change === null || typicalError === null || typicalError <= 0) return null;
  return Math.abs(change) > typicalError;
}

export function formatWithSign(value: number | null | undefined, digits = 3): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return `${value > 0 ? "+" : ""}${value.toFixed(digits)}`;
}
