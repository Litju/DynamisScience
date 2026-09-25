import { describe, expect, it } from "vitest";
import type { Evidence, MatchFrame, Run, WorkbenchBlock } from "@/lib/types";
import { formatEstimateWithInterval, formatSig, formatSignedSig, intervalExcludes, primaryResult } from "@/lib/scientific";
import { groupReproductions } from "@/components/report/ReportDocument";
import { frameMeasures } from "@/components/viewers/MatchViewer";
import { scenarioLoads } from "./blocks/ExtraBlocks";
import { runMatchesConfig } from "./blocks/AnalysisBlocks";

describe("numeric display", () => {
  it("uses significant figures so small and large quantities keep their precision", () => {
    expect(formatSig(0.0109488)).toBe("0.0109");
    expect(formatSig(1.62981, 4)).toBe("1.630");
    expect(formatSig(397150, 3)).toBe("397150");
    expect(formatSig(null)).toBe("—");
    expect(formatSignedSig(0.0933)).toBe("+0.0933");
    expect(formatSignedSig(-0.0109)).toBe("-0.0109");
  });

  it("only prints an interval that was computed", () => {
    expect(formatEstimateWithInterval(0.0933, 0.0665, 0.12)).toBe("0.0933 [0.0665, 0.120]");
    expect(formatEstimateWithInterval(0.0933, null, 0.12)).toBe("0.0933");
    expect(intervalExcludes(0.0665, 0.12)).toBe(true);
    expect(intervalExcludes(-0.01, 0.12)).toBe(false);
    expect(intervalExcludes(null, 0.12)).toBeNull();
  });

  it("unwraps the nested primary model of seeded longitudinal runs", () => {
    expect(primaryResult({ primary: { estimator: "MIXEDLM_RANDOM_SLOPE" }, secondary: {} })).toEqual({ estimator: "MIXEDLM_RANDOM_SLOPE" });
    expect(primaryResult({ estimator: "GEE" })).toEqual({ estimator: "GEE" });
  });
});

const evidence = (id: string, reproduces: string[] = []): Evidence => ({
  id, title: id, kind: "EFFECT", metric_id: "MET-CMJ-IMPULSE", value: 0.09, unit: "N·s·kg⁻¹", estimate: 0.09, uncertainty: 0.01, uncertainty_label: "SE",
  effect_size: null, population: "", sample_size: 440, protocol_id: "PROT-CMJ", dataset_snapshot_id: "DS-SYNTH-001", analysis_run_id: `RUN-${id}`, diagnostics: {}, quality: "VALID", provenance: {}, interpretation: "", reproduces,
});

describe("report composition", () => {
  it("reports an independently reproduced result once, citing its reproductions", () => {
    const groups = groupReproductions([evidence("EVID-0001"), evidence("EVID-0004", ["EVID-0001"]), evidence("EVID-0005")]);
    expect(groups.map((group) => group.primary.id)).toEqual(["EVID-0001", "EVID-0005"]);
    expect(groups[0].reproductions.map((item) => item.id)).toEqual(["EVID-0004"]);
  });

  it("keeps a reproduction as its own result when the original is not cited", () => {
    const groups = groupReproductions([evidence("EVID-0004", ["EVID-0001"])]);
    expect(groups.map((group) => group.primary.id)).toEqual(["EVID-0004"]);
  });
});

describe("match-derived measures", () => {
  const frames: MatchFrame[] = [
    { frame: 0, time_s: 0, entities: [{ player_id: "P1", team: "HOME", x_m: 10, y_m: 10, vx_m_s: 3, vy_m_s: 4 }, { player_id: "P2", team: "AWAY", x_m: 13, y_m: 14, vx_m_s: 0, vy_m_s: 0 }, { player_id: "BALL", team: "BALL", x_m: 10, y_m: 20, vx_m_s: 0, vy_m_s: 0 }] },
    { frame: 1, time_s: 0.1, entities: [{ player_id: "P1", team: "HOME", x_m: 10.3, y_m: 10.4, vx_m_s: 3.6, vy_m_s: 4.8 }, { player_id: "P2", team: "AWAY", x_m: 13, y_m: 14, vx_m_s: 0, vy_m_s: 0 }, { player_id: "BALL", team: "BALL", x_m: 10.3, y_m: 20.4, vx_m_s: 0, vy_m_s: 0 }] },
  ];
  it("derives speed from tracking velocity and acceleration by finite difference", () => {
    const first = frameMeasures(frames, 0, "P1");
    expect(first?.speed).toBeCloseTo(5, 6);
    expect(first?.acceleration).toBeNull();
    expect(first?.nearestOpponent).toEqual({ id: "P2", distance: 5 });
    const second = frameMeasures(frames, 1, "P1");
    expect(second?.acceleration).toBeCloseTo(10, 6); // |Δv| = 1 m/s over 0.1 s
    expect(second?.distanceToBall).toBeCloseTo(10, 6);
    expect(frameMeasures(frames, 1, "NOPE")).toBeNull();
  });
});

describe("model scenarios", () => {
  it("builds deterministic future load scenarios from the observed reference", () => {
    expect(scenarioLoads(300, "MAINTAIN", 3)).toEqual([300, 300, 300]);
    expect(scenarioLoads(300, "TAPER", 2)).toEqual([180, 180]);
    expect(scenarioLoads(300, "OVERLOAD", 1)).toEqual([420]);
    expect(scenarioLoads(300, "CUSTOM", 3, [100, 200, 300, 400])).toEqual([100, 200, 300]);
  });
});

describe("run freshness", () => {
  const block: WorkbenchBlock = { id: "B-ANALYSIS", type: "analysis", title: "", collapsed: false, state: { method_id: "METH-LONG", outcome_metric_id: "MET-CMJ-IMPULSE", parameters: { reference_week: 1, contrast_week: 10, alpha: 0.05 }, run_id: "RUN-0001" } };
  const run = {
    id: "RUN-0001", method_id: "METH-LONG", outcome_metric_id: "MET-CMJ-IMPULSE", parameters: { reference_week: 1, contrast_week: 10, alpha: 0.05 },
    execution: { analysis_spec: { outcome_metric_id: "MET-CMJ-IMPULSE", parameters: {} }, cohort: { excluded_subject_ids: [] } },
  } as unknown as Run;
  it("treats a run as current only for the exact configuration that produced it", () => {
    expect(runMatchesConfig(run, block, [])).toBe(true);
    expect(runMatchesConfig(run, block, ["SUB-001"])).toBe(false);
    expect(runMatchesConfig(run, { ...block, state: { ...block.state, parameters: { reference_week: 1, contrast_week: 8, alpha: 0.05 } } }, [])).toBe(false);
    expect(runMatchesConfig(run, { ...block, state: { ...block.state, outcome_metric_id: "MET-CMJ-HEIGHT" } }, [])).toBe(false);
    expect(runMatchesConfig(undefined, block, [])).toBe(false);
  });
});
