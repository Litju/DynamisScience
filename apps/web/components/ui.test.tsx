import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { EvidencePassport, StatusBadge } from "@/components/ui";
import type { Evidence } from "@/lib/types";

const effectEvidence: Evidence = {
  id: "EVID-0001",
  title: "Intervention × Time effect on concentric impulse",
  kind: "EFFECT",
  metric_id: "MET-CMJ-IMPULSE",
  value: 0.0933,
  unit: "N·s·kg⁻¹",
  estimate: 0.0933,
  uncertainty: 0.0137,
  uncertainty_label: "SE",
  effect_size: 0.536,
  population: "Synthetic elite football cohort, weeks 1–16",
  sample_size: 448,
  protocol_id: "PROT-CMJ",
  dataset_snapshot_id: "DS-SYNTH-001",
  analysis_run_id: "RUN-0001",
  diagnostics: {},
  quality: "VALID",
  provenance: {
    method: "statsmodels MixedLM with athlete random intercept and random week slope",
    algorithm: "statsmodels MixedLM with athlete random intercept and random week slope",
    algorithm_version: "1.2.0",
    snapshot_checksum: "15f3a660d08e73cbb2216b821c25081bb825e16a8d391953ca33c586b108d765",
  },
  interpretation: "Computed from DS-SYNTH-001.",
};

const missingEvidence: Evidence = {
  ...effectEvidence,
  id: "EVID-9999",
  value: null,
  estimate: null,
  uncertainty: null,
  uncertainty_label: null,
  quality: "WARNING",
};

describe("EvidencePassport", () => {
  it("renders the estimate, unit, uncertainty and provenance contract", () => {
    render(<EvidencePassport evidence={effectEvidence} onNavigate={vi.fn()} />);
    expect(screen.getByText("0.093")).toBeInTheDocument();
    expect(screen.getByText("N·s·kg⁻¹")).toBeInTheDocument();
    expect(screen.getByText(/SE · ±0.014 N·s·kg⁻¹/)).toBeInTheDocument();
    expect(screen.getByText("PROT-CMJ")).toBeInTheDocument();
    expect(screen.getByText("MET-CMJ-IMPULSE")).toBeInTheDocument();
    expect(screen.getByText("448")).toBeInTheDocument();
    expect(screen.getByText("DS-SYNTH-001")).toBeInTheDocument();
    expect(screen.getByText("1.2.0")).toBeInTheDocument();
    expect(screen.getByText(/15f3a660d08e73cbb2/)).toBeInTheDocument();
  });

  it("never fabricates a value when the estimate is missing", () => {
    render(<EvidencePassport evidence={missingEvidence} onNavigate={vi.fn()} />);
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.queryByText("0.000")).not.toBeInTheDocument();
    expect(screen.getByText("WARNING")).toBeInTheDocument();
  });

  it("links lineage to the supplied artifact rather than a hard-coded id", () => {
    const onNavigate = vi.fn();
    render(<EvidencePassport evidence={effectEvidence} onNavigate={onNavigate} lineageId="CMJ-001-10-1" />);
    screen.getByRole("button", { name: /View lineage/ }).click();
    expect(onNavigate).toHaveBeenCalledWith("lineage", "CMJ-001-10-1");
    screen.getByRole("button", { name: /Open source run/ }).click();
    expect(onNavigate).toHaveBeenCalledWith("runs", "RUN-0001");
  });
});

describe("StatusBadge", () => {
  it("always renders the state as text, never colour alone", () => {
    render(<StatusBadge tone="warn">EXCLUDED</StatusBadge>);
    expect(screen.getByText("EXCLUDED")).toBeInTheDocument();
  });
});
