import { describe, expect, it } from "vitest";
import { formatScientificValue, isExcluded, provenanceLabel } from "./scientific";

describe("scientific display contracts", () => {
  it("formats missing and finite measurements without inventing values", () => {
    expect(formatScientificValue(1.23456)).toBe("1.235");
    expect(formatScientificValue(null)).toBe("—");
    expect(formatScientificValue(Number.NaN)).toBe("—");
  });

  it("keeps explicit quality states and provenance visible", () => {
    expect(isExcluded("EXCLUDED")).toBe(true);
    expect(isExcluded("VALID")).toBe(false);
    expect(provenanceLabel("DS-SYNTH-001", 20260924)).toBe("DS-SYNTH-001 · seed 20260924");
  });
});
