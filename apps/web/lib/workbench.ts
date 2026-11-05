import type { BlockType, WorkbenchBlock } from "./types";

/**
 * The workbench is an ordered, typed investigation document. Blocks hold
 * serialisable references to domain objects (spec, run, evidence, figure IDs);
 * they never hold scientific values of their own.
 */

export const BLOCK_META: Record<BlockType, { label: string; code: string; description: string; addable: boolean }> = {
  question: { label: "Question", code: "Q", description: "Research question, hypotheses and the frozen analysis plan", addable: true },
  dataset: { label: "Dataset", code: "D", description: "Immutable dataset snapshot and its quality", addable: false },
  cohort: { label: "Cohort", code: "C", description: "Cohort definition, inclusion and exclusions", addable: true },
  schedule: { label: "Schedule", code: "S", description: "Planned monitoring measurements, distinct from recorded readings", addable: false },
  table: { label: "Table", code: "T", description: "Per-athlete individual change table", addable: true },
  explore: { label: "Explore", code: "E", description: "Longitudinal exploration of a metric across the cohort", addable: true },
  force_trial: { label: "Force Trial", code: "F", description: "A pinned CMJ trial with its evidence passport", addable: false },
  match_event: { label: "Match Event", code: "M", description: "Annotated match events with synchronized field and pose", addable: true },
  analysis: { label: "Analysis", code: "A", description: "Executable analysis bound to a spec, cohort and immutable run", addable: true },
  diagnostics: { label: "Diagnostics", code: "Dx", description: "Diagnostics of the analysis run it is attached to", addable: false },
  evidence: { label: "Evidence", code: "Ev", description: "Immutable evidence artifact promoted from a run", addable: false },
  model: { label: "Model", code: "Mo", description: "Mechanistic training-response model and scenario simulation", addable: true },
  figure: { label: "Figure", code: "Fg", description: "Figure artifact bound to evidence", addable: false },
  interpretation: { label: "Interpretation", code: "I", description: "Computed statement and the scientist's interpretation", addable: true },
  report_section: { label: "Report Section", code: "R", description: "Where this investigation enters the study report", addable: false },
};

export const DEPENDENCY_KEYS = ["cohort_block_id", "analysis_block_id", "evidence_block_id"] as const;

export function dependencyOf(block: WorkbenchBlock): string[] {
  return DEPENDENCY_KEYS.map((key) => block.state[key]).filter((value): value is string => typeof value === "string" && value.length > 0);
}

/** Blocks that reference ``blockId`` (directly). */
export function dependentsOf(blocks: WorkbenchBlock[], blockId: string): WorkbenchBlock[] {
  return blocks.filter((block) => dependencyOf(block).includes(blockId));
}

/** An order is valid when every block appears after the blocks it depends on. */
export function isValidOrder(blocks: WorkbenchBlock[]): boolean {
  const seen = new Set<string>();
  for (const block of blocks) {
    if (dependencyOf(block).some((id) => !seen.has(id))) return false;
    seen.add(block.id);
  }
  return true;
}

export function canMove(blocks: WorkbenchBlock[], index: number, direction: -1 | 1): boolean {
  const target = index + direction;
  if (index < 0 || index >= blocks.length || target < 0 || target >= blocks.length) return false;
  return isValidOrder(move(blocks, index, direction));
}

export function move(blocks: WorkbenchBlock[], index: number, direction: -1 | 1): WorkbenchBlock[] {
  const next = [...blocks];
  const [block] = next.splice(index, 1);
  next.splice(index + direction, 0, block);
  return next;
}

export function nextBlockId(blocks: WorkbenchBlock[], type: BlockType): string {
  const prefix = `B-${type.toUpperCase().replace("_", "-")}-`;
  const used = blocks.map((block) => block.id).filter((id) => id.startsWith(prefix)).map((id) => Number(id.slice(prefix.length))).filter(Number.isFinite);
  return `${prefix}${Math.max(1, ...used) + 1}`;
}

export function insertAfter(blocks: WorkbenchBlock[], block: WorkbenchBlock, afterId?: string | null): WorkbenchBlock[] {
  const index = afterId ? blocks.findIndex((item) => item.id === afterId) : -1;
  const at = index >= 0 ? index + 1 : blocks.length;
  return [...blocks.slice(0, at), block, ...blocks.slice(at)];
}

/** Removal is refused while another block still depends on this one. */
export function removeBlock(blocks: WorkbenchBlock[], blockId: string): WorkbenchBlock[] | null {
  if (dependentsOf(blocks, blockId).length > 0) return null;
  return blocks.filter((block) => block.id !== blockId);
}

export function updateState(blocks: WorkbenchBlock[], blockId: string, patch: Record<string, unknown>): WorkbenchBlock[] {
  return blocks.map((block) => (block.id === blockId ? { ...block, state: { ...block.state, ...patch } } : block));
}

export function firstOfType(blocks: WorkbenchBlock[], type: BlockType): WorkbenchBlock | undefined {
  return blocks.find((block) => block.type === type);
}

/**
 * Create a new block wired to the nearest suitable upstream block. Fork of an
 * analysis clears its run so the fork has to be executed to produce a result.
 */
export function createBlock(blocks: WorkbenchBlock[], type: BlockType, options: { from?: WorkbenchBlock; state?: Record<string, unknown>; title?: string } = {}): WorkbenchBlock {
  const cohort = firstOfType(blocks, "cohort");
  const id = nextBlockId(blocks, type);
  const base = { id, type, collapsed: false } as const;
  switch (type) {
    case "explore":
      return { ...base, title: options.title ?? "Longitudinal exploration", state: { metric_id: "MET-CMJ-BRAKING-DURATION", population: "ALL", view: "LONGITUDINAL", reference: "RAW", context: ["LOAD", "MATCH"], cohort_block_id: cohort?.id, ...options.state } };
    case "analysis": {
      const from = options.from;
      return {
        ...base,
        title: options.title ?? (from ? `${from.title} (fork)` : "Analysis"),
        state: {
          method_id: "METH-LONG",
          outcome_metric_id: "MET-CMJ-IMPULSE",
          parameters: { reference_week: 1, contrast_week: 10, alpha: 0.05 },
          cohort_block_id: cohort?.id,
          ...(from ? { ...from.state, spec_id: undefined } : {}),
          run_id: undefined,
          ...options.state,
        },
      };
    }
    case "schedule":
      return { ...base, title: options.title ?? "Monitoring schedule", state: { program_id: options.state?.program_id, ...options.state } };
    case "diagnostics":
      return { ...base, title: options.title ?? "Diagnostics", state: { analysis_block_id: options.from?.id, ...options.state } };
    case "evidence":
      return { ...base, title: options.title ?? "Evidence", state: { analysis_block_id: options.from?.id, evidence_id: undefined, ...options.state } };
    case "model":
      return { ...base, title: options.title ?? "Training-response model", state: { model_spec_id: "MODEL-FITNESS-FATIGUE", scenario: "MAINTAIN", scenario_weeks: 8, ...options.state } };
    case "match_event":
      return { ...base, title: options.title ?? "Match segment events", state: { match_id: "MATCH-SYNTH-001", ...options.state } };
    case "table":
      return { ...base, title: options.title ?? "Individual change table", state: { run_id: "RUN-0003", metric_id: "MET-CMJ-IMPULSE", ...options.state } };
    case "force_trial":
      return { ...base, title: options.title ?? "Force trial", state: { ...options.state } };
    case "interpretation":
      return { ...base, title: options.title ?? "Interpretation", state: { note: "", ...options.state } };
    default:
      return { ...base, title: options.title ?? BLOCK_META[type].label, state: { ...options.state } };
  }
}

/** Numbering shown in the gutter: blocks are numbered in document order. */
export function blockIndexLabel(index: number): string {
  return String(index + 1).padStart(2, "0");
}
