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

/**
 * Significant-figure display for estimates. Fixed decimals hide precision on
 * small quantities (a 0.011 s braking change) and overstate it on large ones.
 */
export function formatSig(value: number | null | undefined, significant = 3): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  if (value === 0) return "0";
  if (Math.abs(value) < 1e-4) return value.toExponential(Math.max(0, significant - 1));
  const magnitude = Math.floor(Math.log10(Math.abs(value)));
  const decimals = Math.max(0, Math.min(8, significant - 1 - magnitude));
  return value.toFixed(decimals);
}

export function formatSignedSig(value: number | null | undefined, significant = 3): string {
  const text = formatSig(value, significant);
  return value !== null && value !== undefined && Number.isFinite(value) && value > 0 ? `+${text}` : text;
}

/** "0.0933 [0.0665, 0.120]" — the interval is only shown when it was computed. */
export function formatEstimateWithInterval(estimate: number | null | undefined, low: number | null | undefined, high: number | null | undefined, significant = 3): string {
  const point = formatSig(estimate, significant);
  if (low === null || low === undefined || high === null || high === undefined || !Number.isFinite(low) || !Number.isFinite(high)) return point;
  return `${point} [${formatSig(low, significant)}, ${formatSig(high, significant)}]`;
}

/** Whether a two-sided interval excludes the null value. */
export function intervalExcludes(low: number | null | undefined, high: number | null | undefined, value = 0): boolean | null {
  if (low === null || low === undefined || high === null || high === undefined) return null;
  return low > value || high < value;
}

export const ARM_LABEL = { INTERVENTION: "Intervention", COMPARISON: "Comparison" } as const;

export interface MetricOption {
  id: string;
  label: string;
  short: string;
  unit: string;
  column: string;
  role: "PRIMARY" | "SECONDARY" | "CONTEXT";
}

/** Outcome metrics the workbench can explore and analyse; IDs resolve to Library MetricDefinitions. */
export const METRIC_OPTIONS: MetricOption[] = [
  { id: "MET-CMJ-IMPULSE", label: "Concentric impulse", short: "Conc. impulse", unit: "N·s·kg⁻¹", column: "concentric_impulse_n_s_kg", role: "PRIMARY" },
  { id: "MET-CMJ-BRAKING-DURATION", label: "Eccentric braking duration", short: "Braking dur.", unit: "s", column: "eccentric_braking_duration_s", role: "PRIMARY" },
  { id: "MET-CMJ-HEIGHT", label: "Jump height (flight time)", short: "Jump height", unit: "cm", column: "jump_height_cm", role: "SECONDARY" },
  { id: "MET-CMJ-POWER", label: "Peak power", short: "Peak power", unit: "W·kg⁻¹", column: "peak_power_w_kg", role: "SECONDARY" },
  { id: "MET-CMJ-DEPTH", label: "Countermovement depth", short: "CM depth", unit: "cm", column: "countermovement_depth_cm", role: "SECONDARY" },
  { id: "MET-CMJ-BRAKING-IMPULSE", label: "Eccentric braking impulse", short: "Braking imp.", unit: "N·s·kg⁻¹", column: "eccentric_braking_impulse_n_s_kg", role: "CONTEXT" },
  { id: "MET-CMJ-RSI-MOD", label: "RSI-mod", short: "RSI-mod", unit: "cm·s⁻¹", column: "rsi_mod", role: "CONTEXT" },
];

export function metricOption(id: string | undefined | null): MetricOption {
  return METRIC_OPTIONS.find((metric) => metric.id === id) ?? METRIC_OPTIONS[0];
}

export const METHOD_LABEL: Record<string, string> = {
  "METH-LONG": "Group × time longitudinal model",
  "METH-REL": "Repeated-trial reliability",
  "METH-IND": "Individual change context",
};

/** Seeded longitudinal runs nest the primary model under ``primary``; executed runs do not. */
export function primaryResult<T = Record<string, unknown>>(result: Record<string, unknown> | undefined): T | undefined {
  if (!result) return undefined;
  const nested = result.primary;
  return (nested && typeof nested === "object" ? nested : result) as T;
}

export function shortChecksum(value: unknown, length = 12): string {
  return typeof value === "string" && value.length > 0 ? value.slice(0, length) : "—";
}

/** Two-letter display for athlete IDs ("ATH-008" → "008"). */
export function athleteNumber(displayId: string): string {
  return displayId.replace(/^ATH-/, "");
}

export function describeReproduction(reproduces: string[] | undefined): string | null {
  if (!reproduces || reproduces.length === 0) return null;
  return `reproduces ${reproduces.join(", ")} (identical result digest)`;
}
