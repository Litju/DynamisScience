import { describe, expect, it } from "vitest";
import { fmt, fmtInt, fmtSigned, severityTone, shortDate } from "./format";

describe("performance formatting", () => {
  it("always renders a visible placeholder instead of zero for missing values", () => {
    expect(fmt(null, 1)).toBe("—");
    expect(fmt(undefined, 2)).toBe("—");
    expect(fmtInt(null)).toBe("—");
  });

  it("formats canonical display precision without changing stored values", () => {
    expect(fmt(42.343, 2)).toBe("42.34");
    expect(fmt(7.091, 1)).toBe("7.1");
    expect(fmtInt(1567.9)).toBe("1,568");
  });

  it("uses a true minus sign for negative changes", () => {
    expect(fmtSigned(-4.888, 1)).toBe("−4.9%");
    expect(fmtSigned(0.79, 1)).toBe("+0.8%");
    expect(fmtSigned(null, 1)).toBe("—");
  });

  it("maps action severity to the review tone rather than colour alone", () => {
    expect(severityTone("action")).toBe("bad");
    expect(severityTone("attention")).toBe("warn");
    expect(severityTone("ok")).toBe("ok");
    expect(severityTone("unknown")).toBe("neutral");
  });

  it("renders an unavailable date as a placeholder", () => {
    expect(shortDate(null)).toBe("—");
  });
});
