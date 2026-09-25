import type { LineageEdge, LineageNode } from "./types";

export interface PositionedNode {
  node: LineageNode;
  rank: number;
  x: number;
  y: number;
}

/**
 * Layered (Sugiyama-style, longest-path ranking) layout of a provenance DAG:
 * sources on the left, the focused artefact's consumers on the right. The
 * graph is data-driven; this only decides where each stored node is drawn.
 */
export function layoutLineage(nodes: LineageNode[], edges: LineageEdge[], columnWidth = 236, rowHeight = 64): PositionedNode[] {
  const ids = new Set(nodes.map((node) => node.id));
  const incoming = new Map<string, string[]>();
  for (const edge of edges) {
    if (!ids.has(edge.source) || !ids.has(edge.target) || edge.source === edge.target) continue;
    incoming.set(edge.target, [...(incoming.get(edge.target) ?? []), edge.source]);
  }
  const rank = new Map<string, number>();
  const visiting = new Set<string>();
  const resolve = (id: string): number => {
    const known = rank.get(id);
    if (known !== undefined) return known;
    if (visiting.has(id)) return 0; // defensive: a cycle would be a data error, never loop
    visiting.add(id);
    const parents = incoming.get(id) ?? [];
    const value = parents.length ? Math.max(...parents.map(resolve)) + 1 : 0;
    visiting.delete(id);
    rank.set(id, value);
    return value;
  };
  nodes.forEach((node) => resolve(node.id));
  const columns = new Map<number, LineageNode[]>();
  for (const node of nodes) {
    const value = rank.get(node.id) ?? 0;
    columns.set(value, [...(columns.get(value) ?? []), node]);
  }
  const tallest = Math.max(1, ...[...columns.values()].map((column) => column.length));
  const positioned: PositionedNode[] = [];
  for (const [value, column] of [...columns.entries()].sort((a, b) => a[0] - b[0])) {
    const sorted = [...column].sort((a, b) => a.kind.localeCompare(b.kind) || a.id.localeCompare(b.id));
    const offset = ((tallest - sorted.length) * rowHeight) / 2;
    sorted.forEach((node, index) => positioned.push({ node, rank: value, x: value * columnWidth, y: offset + index * rowHeight }));
  }
  return positioned;
}

export const LINEAGE_KIND_COLOR: Record<string, string> = {
  generator: "#9db3c6",
  trial: "#4fc4b6",
  protocol: "#7d8a92",
  metric: "#86a0f0",
  snapshot: "#9db3c6",
  cohort: "#74c27a",
  study: "#7d8a92",
  plan: "#9db3c6",
  question: "#7d8a92",
  hypothesis: "#7d8a92",
  spec: "#d6bf6a",
  run: "#e3a74e",
  evidence: "#e3a74e",
  figure: "#e5716c",
  report: "#f3f6f7",
  model: "#86a0f0",
  model_run: "#86a0f0",
  match: "#4fc4b6",
};
