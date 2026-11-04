import { describe, expect, it } from "vitest";
import {
  changeExceedsTypicalError,
  formatScientificValue,
  formatWithSign,
  isExcluded,
  jointAngleDegrees,
  metricOptionsFor,
  provenanceLabel,
  REAL_METHODS,
  qualityTone,
  uncertaintyInterval,
} from "./scientific";

describe("scientific display contracts", () => {
  it("formats missing and finite measurements without inventing values", () => {
    expect(formatScientificValue(1.23456)).toBe("1.235");
    expect(formatScientificValue(null)).toBe("—");
    expect(formatScientificValue(undefined)).toBe("—");
    expect(formatScientificValue(Number.NaN)).toBe("—");
    expect(formatScientificValue(Number.POSITIVE_INFINITY)).toBe("—");
    expect(formatWithSign(0.1234)).toBe("+0.123");
    expect(formatWithSign(-0.1234)).toBe("-0.123");
    expect(formatWithSign(null)).toBe("—");
  });

  it("keeps explicit quality states and provenance visible", () => {
    expect(isExcluded("EXCLUDED")).toBe(true);
    expect(isExcluded("VALID")).toBe(false);
    expect(provenanceLabel("DS-SYNTH-001", 20260924)).toBe("DS-SYNTH-001 · seed 20260924");
  });

  it("maps the scientific status vocabulary to a tone consistently", () => {
    expect(qualityTone("VALID")).toBe("good");
    expect(qualityTone("EXCLUDED")).toBe("bad");
    expect(qualityTone("WARNING")).toBe("warn");
    expect(qualityTone("FROZEN")).toBe("purple");
    expect(qualityTone("SYNTHETIC")).toBe("cyan");
    expect(qualityTone("EXPLORATORY")).toBe("warn");
    expect(qualityTone(undefined)).toBe("neutral");
  });

  it("computes joint angles from real geometry", () => {
    const vertex = { x: 0, y: 0, z: 0 };
    expect(jointAngleDegrees({ x: 1, y: 0, z: 0 }, vertex, { x: 1, y: 0, z: 0 })).toBeCloseTo(0, 6);
    expect(jointAngleDegrees({ x: 1, y: 0, z: 0 }, vertex, { x: -1, y: 0, z: 0 })).toBeCloseTo(180, 6);
    expect(jointAngleDegrees({ x: 1, y: 0, z: 0 }, vertex, { x: 0, y: 0, z: 1 })).toBeCloseTo(90, 6);
    expect(jointAngleDegrees({ x: 0, y: 0, z: 1 }, { x: 0, y: 0, z: 0 }, { x: 0, y: 1, z: 1 })).toBeCloseTo(45, 6);
    expect(jointAngleDegrees(undefined, vertex, { x: 1, y: 0, z: 0 })).toBeNull();
    expect(jointAngleDegrees({ x: 0, y: 0, z: 0 }, vertex, { x: 1, y: 0, z: 0 })).toBeNull();
  });

  it("derives uncertainty intervals only from real uncertainty", () => {
    expect(uncertaintyInterval(0.5, 0.1)).toEqual([0.4, 0.6]);
    expect(uncertaintyInterval(null, 0.1)).toBeNull();
    expect(uncertaintyInterval(0.5, null)).toBeNull();
  });

  it("keeps real-study metrics and methods scoped to their dataset", () => {
    expect(metricOptionsFor(true, "STUDY-REAL-001").map((metric) => metric.id)).toEqual([
      "MET-REAL-CMJ-HEIGHT",
      "MET-REAL-ISO-REL-PEAK",
      "MET-REAL-BS-REL",
      "MET-REAL-SPRINT-20M",
    ]);
    expect(metricOptionsFor(true, "STUDY-REAL-002").map((metric) => metric.id)).toEqual([
      "MET-REAL-FZ-PEAK",
      "MET-REAL-FZ-IMPULSE",
    ]);
    expect(metricOptionsFor(false, "STUDY-REAL-001").some((metric) => metric.id === "MET-CMJ-IMPULSE")).toBe(true);
    expect(REAL_METHODS["STUDY-REAL-001"]).toContain("METH-REAL-TREND");
    expect(REAL_METHODS["STUDY-REAL-002"]).toContain("METH-REAL-RELIABILITY");
  });

  it("only flags a change as interpretable when it exceeds the typical error", () => {
    expect(changeExceedsTypicalError(0.2, 0.05)).toBe(true);
    expect(changeExceedsTypicalError(-0.2, 0.05)).toBe(true);
    expect(changeExceedsTypicalError(0.02, 0.05)).toBe(false);
    expect(changeExceedsTypicalError(null, 0.05)).toBeNull();
    expect(changeExceedsTypicalError(0.2, 0)).toBeNull();
  });
});
