import { describe, expect, it } from "vitest";
import type { WorkbenchBlock } from "./types";
import { canMove, createBlock, dependentsOf, insertAfter, isValidOrder, move, nextBlockId, removeBlock, updateState } from "./workbench";
import { layoutLineage } from "./lineageLayout";

const seeded: WorkbenchBlock[] = [
  { id: "B-QUESTION", type: "question", title: "Research question", state: { question_id: "RQ-001" }, collapsed: false },
  { id: "B-DATASET", type: "dataset", title: "DS-SYNTH-001", state: { snapshot_id: "DS-SYNTH-001" }, collapsed: false },
  { id: "B-COHORT", type: "cohort", title: "Cohort", state: { cohort_id: "COHORT-001", excluded_subject_ids: [] }, collapsed: false },
  { id: "B-EXPLORE", type: "explore", title: "Explore", state: { metric_id: "MET-CMJ-IMPULSE", cohort_block_id: "B-COHORT" }, collapsed: false },
  { id: "B-ANALYSIS", type: "analysis", title: "Analysis", state: { spec_id: "SPEC-LONG-001", run_id: "RUN-0001", cohort_block_id: "B-COHORT" }, collapsed: false },
  { id: "B-DIAGNOSTICS", type: "diagnostics", title: "Diagnostics", state: { analysis_block_id: "B-ANALYSIS" }, collapsed: false },
  { id: "B-EVIDENCE", type: "evidence", title: "Evidence", state: { analysis_block_id: "B-ANALYSIS", evidence_id: "EVID-0001" }, collapsed: false },
];

describe("typed investigation document", () => {
  it("accepts the seeded order and rejects a block placed before its dependency", () => {
    expect(isValidOrder(seeded)).toBe(true);
    expect(isValidOrder(move(seeded, 5, -1))).toBe(false); // diagnostics above its analysis
  });

  it("only allows moves that keep semantic dependencies intact", () => {
    expect(canMove(seeded, 4, -1)).toBe(true); // analysis may move above explore (both depend only on the cohort)
    expect(canMove(seeded, 5, -1)).toBe(false);
    expect(canMove(seeded, 3, -1)).toBe(false); // explore cannot move above its cohort
    expect(canMove(seeded, 0, -1)).toBe(false);
    expect(canMove(seeded, seeded.length - 1, 1)).toBe(false);
  });

  it("refuses to remove a block that others depend on", () => {
    expect(dependentsOf(seeded, "B-ANALYSIS").map((block) => block.id)).toEqual(["B-DIAGNOSTICS", "B-EVIDENCE"]);
    expect(removeBlock(seeded, "B-ANALYSIS")).toBeNull();
    expect(removeBlock(seeded, "B-EVIDENCE")?.map((block) => block.id)).not.toContain("B-EVIDENCE");
  });

  it("forks an analysis into a new block without its run so it must be executed", () => {
    const fork = createBlock(seeded, "analysis", { from: seeded[4] });
    expect(fork.id).not.toBe("B-ANALYSIS");
    expect(fork.state.run_id).toBeUndefined();
    expect(fork.state.spec_id).toBeUndefined();
    expect(fork.state.cohort_block_id).toBe("B-COHORT");
  });

  it("creates blocks with serialisable state wired to the cohort", () => {
    const explore = createBlock(seeded, "explore");
    expect(JSON.parse(JSON.stringify(explore))).toEqual(explore);
    expect(explore.state.cohort_block_id).toBe("B-COHORT");
    const model = createBlock(seeded, "model");
    expect(model.state.model_spec_id).toBe("MODEL-FITNESS-FATIGUE");
  });

  it("inserts after an anchor and generates unique IDs", () => {
    const block = createBlock(seeded, "table");
    const next = insertAfter(seeded, block, "B-COHORT");
    expect(next[3].id).toBe(block.id);
    expect(nextBlockId(next, "table")).not.toBe(block.id);
  });

  it("updates block state immutably", () => {
    const next = updateState(seeded, "B-COHORT", { excluded_subject_ids: ["SUB-003"] });
    expect(next[2].state.excluded_subject_ids).toEqual(["SUB-003"]);
    expect(seeded[2].state.excluded_subject_ids).toEqual([]);
  });
});

describe("lineage layout", () => {
  it("ranks nodes by longest path so the generator is left of the report", () => {
    const nodes = ["GEN-001", "TRIAL-INDEX", "MET", "DS", "COHORT", "RUN", "EVID", "REPORT"].map((id) => ({ id, kind: "x", label: id, metadata: "" }));
    const chain = ["GEN-001", "TRIAL-INDEX", "MET", "DS", "COHORT", "RUN", "EVID", "REPORT"];
    const edges = chain.slice(1).map((target, index) => ({ id: `e${index}`, source: chain[index], target, relation: "r", label: "l" }));
    edges.push({ id: "shortcut", source: "DS", target: "RUN", relation: "r", label: "l" });
    const placed = new Map(layoutLineage(nodes, edges).map((item) => [item.node.id, item]));
    expect(placed.get("GEN-001")?.rank).toBe(0);
    expect(placed.get("RUN")?.rank).toBe(5);
    expect(placed.get("REPORT")?.rank).toBe(7);
    expect((placed.get("REPORT")?.x ?? 0) > (placed.get("GEN-001")?.x ?? 0)).toBe(true);
  });
});
