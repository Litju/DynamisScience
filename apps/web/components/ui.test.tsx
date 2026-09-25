import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { EvidencePassport, Forest, KV, State, toneFor } from "@/components/ui";

const passport = {
  metricLabel: "Concentric impulse",
  value: 1.62981,
  unit: "N·s·kg⁻¹",
  metricId: "MET-CMJ-IMPULSE",
  canonicalId: "cmj.concentric_impulse",
  method: "trapezoidal integration of net vertical GRF over the propulsion phase",
  algorithm: "cmj-metrics@1.0.0",
  protocolId: "PROT-CMJ",
  sourceId: "CMJ-001-01-1",
  snapshotId: "DS-SYNTH-001",
  quality: "VALID",
  checksum: "15f3a660d08e73cbb2216b821c25081bb825e16a8d391953ca33c586b108d765",
  reproducible: true,
};

describe("EvidencePassport", () => {
  it("renders the value, unit and the full provenance contract of a derived measurement", () => {
    render(<EvidencePassport {...passport} />);
    expect(screen.getByText("1.630")).toBeInTheDocument();
    expect(screen.getByText("N·s·kg⁻¹")).toBeInTheDocument();
    expect(screen.getByText("MET-CMJ-IMPULSE")).toBeInTheDocument();
    expect(screen.getByText("cmj.concentric_impulse")).toBeInTheDocument();
    expect(screen.getByText("PROT-CMJ")).toBeInTheDocument();
    expect(screen.getByText("CMJ-001-01-1")).toBeInTheDocument();
    expect(screen.getByText("DS-SYNTH-001")).toBeInTheDocument();
    expect(screen.getByText("15f3a660d08e73cb")).toBeInTheDocument();
    expect(screen.getByText("VALID")).toBeInTheDocument();
  });

  it("never fabricates a value and disables actions that have no target", () => {
    render(<EvidencePassport {...passport} value={null} quality="WARNING" />);
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.getByText("WARNING")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Methodology/ })).toBeDisabled();
  });

  it("routes source, methodology and lineage to the supplied handlers", () => {
    const onInspectSource = vi.fn();
    const onInspectMethod = vi.fn();
    const onInspectLineage = vi.fn();
    render(<EvidencePassport {...passport} onInspectSource={onInspectSource} onInspectMethod={onInspectMethod} onInspectLineage={onInspectLineage} />);
    fireEvent.click(screen.getByRole("button", { name: /Source/ }));
    fireEvent.click(screen.getByRole("button", { name: /Methodology/ }));
    fireEvent.click(screen.getByRole("button", { name: /Lineage/ }));
    expect(onInspectSource).toHaveBeenCalledOnce();
    expect(onInspectMethod).toHaveBeenCalledOnce();
    expect(onInspectLineage).toHaveBeenCalledOnce();
  });
});

describe("State", () => {
  it("always renders the state as text, never colour alone", () => {
    render(<State>EXCLUDED</State>);
    expect(screen.getByText("EXCLUDED")).toBeInTheDocument();
  });

  it("maps the status vocabulary to consistent tones", () => {
    expect(toneFor("VALID")).toBe("tone-valid");
    expect(toneFor("EXCLUDED")).toBe("tone-excluded");
    expect(toneFor("EXPLORATORY")).toBe("tone-exploratory");
    expect(toneFor("FROZEN")).toBe("tone-frozen");
    expect(toneFor("CONFIRMATORY")).toBe("tone-frozen");
    expect(toneFor("SUPERSEDED")).toBe("tone-superseded");
    expect(toneFor("SYNTHETIC")).toBe("tone-synthetic");
    expect(toneFor(undefined)).toBe("tone-neutral");
  });
});

describe("Forest", () => {
  it("describes the estimate and interval textually", () => {
    render(<Forest estimate={0.0933} low={0.0665} high={0.12} unit="N·s·kg⁻¹" />);
    expect(screen.getByRole("img", { name: "Estimate 0.0933 N·s·kg⁻¹, 95% interval 0.0665 to 0.120" })).toBeInTheDocument();
  });
});

describe("KV", () => {
  it("shows an explicit dash for missing values", () => {
    render(<KV rows={[["Seed", "20260924", "mono"], ["Cohort", undefined]]} />);
    expect(screen.getByText("20260924")).toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();
  });
});
