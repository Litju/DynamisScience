export function fmt(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toLocaleString("en-GB", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function fmtInt(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return Math.round(value).toLocaleString("en-GB");
}

export function fmtSigned(value: number | null | undefined, digits = 1, unit = "%"): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${value > 0 ? "+" : value < 0 ? "−" : ""}${fmt(Math.abs(value), digits)}${unit}`;
}

export function pct(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${fmt(value, digits)}%`;
}

export function shortDate(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
}

export function shortDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function todayLabel(): string {
  return new Date()
    .toLocaleDateString("en-GB", {
      weekday: "long",
      day: "2-digit",
      month: "long",
      year: "numeric",
    })
    .replace(",", "");
}

export function round(value: number | null | undefined, digits = 2): number | null {
  if (value === null || value === undefined || Number.isNaN(value)) return null;
  return Number(value.toFixed(digits));
}

/** Canonical display for legacy stored units that lost their separator glyphs. */
export function displayUnit(unit: string | null | undefined): string {
  if (!unit) return "";
  const text = String(unit);
  if (text.includes("N") && text.includes("s") && text.includes("kg")) return "N·s·kg⁻¹";
  if (text.includes("kg") && text.includes("W")) return "W·kg⁻¹";
  if (text.includes("m") && text.includes("s") && text.includes("−1")) return "m·s⁻¹";
  return text;
}

export const POSITIONS = ["GK", "RB", "CB", "LB", "DM", "CM", "AM", "RW", "LW", "ST"] as const;

export const PHASE_TONE: Record<string, string> = {
  BUILD: "info",
  MATCH: "warn",
  TAPER: "ok",
  RECOVERY: "neutral",
  STRENGTH_BLOCK: "info",
};

export function severityTone(severity: string): "bad" | "warn" | "ok" | "info" | "neutral" {
  if (severity === "action" || severity === "high" || severity === "bad") return "bad";
  if (severity === "attention" || severity === "medium" || severity === "warn") return "warn";
  if (severity === "ok" || severity === "valid") return "ok";
  if (severity === "info") return "info";
  return "neutral";
}
