"use client";

import { useQuery } from "@tanstack/react-query";
import { Crosshair, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import ReactFlow, { Background, Controls, Handle, MarkerType, Position, type Edge, type Node, type NodeProps } from "reactflow";
import { scienceApi } from "@/lib/api";
import { LINEAGE_KIND_COLOR, layoutLineage } from "@/lib/lineageLayout";
import { Button, ErrorBox, KV, Loading, State } from "@/components/ui";
import { useWorkbench, type InspectTarget } from "@/components/workbench/context";

function LineageNodeView({ data }: NodeProps<{ kind: string; label: string; id: string; focus: boolean; selected: boolean }>) {
  return (
    <div className={`lineage-node ${data.focus ? "is-focus" : ""} ${data.selected ? "is-selected" : ""}`} style={{ ["--node-color" as string]: LINEAGE_KIND_COLOR[data.kind] ?? "#7d8a92" }}>
      <Handle type="target" position={Position.Left} isConnectable={false} />
      <div className="k">{data.kind.replace("_", " ")}</div>
      <div className="t" title={data.label}>{data.label}</div>
      <div className="i">{data.id}</div>
      <Handle type="source" position={Position.Right} isConnectable={false} />
    </div>
  );
}

const nodeTypes = { scientific: LineageNodeView };

function formatDetail(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toPrecision(5);
  if (typeof value === "object") return JSON.stringify(value).slice(0, 140);
  return String(value);
}

export function LineageDrawer({ artifactId }: { artifactId: string }) {
  const wb = useWorkbench();
  const [focusId, setFocusId] = useState(artifactId);
  useEffect(() => setFocusId(artifactId), [artifactId]);
  const depth = focusId.startsWith("CMJ-") || focusId.startsWith("DS-") ? 2 : 3;
  const graph = useQuery({ queryKey: ["lineage", focusId, depth], queryFn: () => scienceApi.lineage(focusId, depth) });
  const [selectedId, setSelectedId] = useState<string>(artifactId);
  useEffect(() => setSelectedId(focusId), [focusId]);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    closeRef.current?.focus({ preventScroll: true });
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        wb.closeLineage();
      }
    };
    window.addEventListener("keydown", onKey, true);
    return () => {
      window.removeEventListener("keydown", onKey, true);
      previous?.focus?.({ preventScroll: true });
    };
  }, [wb]);

  const flow = useMemo(() => {
    if (!graph.data) return { nodes: [] as Node[], edges: [] as Edge[] };
    const positioned = layoutLineage(graph.data.nodes, graph.data.edges);
    const path = new Set([...(graph.data.ancestor_ids ?? []), focusId]);
    return {
      nodes: positioned.map(({ node, x, y }) => ({ id: node.id, type: "scientific", position: { x, y }, data: { kind: node.kind, label: node.label, id: node.id, focus: node.id === focusId, selected: node.id === selectedId } })),
      edges: graph.data.edges.map((edge) => {
        const onPath = path.has(edge.source) && path.has(edge.target);
        const touchesSelected = edge.source === selectedId || edge.target === selectedId;
        return {
          id: edge.id,
          source: edge.source,
          target: edge.target,
          label: touchesSelected ? edge.label : undefined,
          markerEnd: { type: MarkerType.ArrowClosed, width: 12, height: 12, color: onPath ? "#e3a74e" : "#3a4750" },
          style: { stroke: touchesSelected ? "#f3c47a" : onPath ? "rgba(227,167,78,0.55)" : "#2f3a41", strokeWidth: touchesSelected ? 1.8 : 1.1 },
          labelStyle: { fill: "#a3afb6", fontSize: 9, fontFamily: "IBM Plex Mono, monospace" },
          labelBgStyle: { fill: "#0c0f11" },
        } satisfies Edge;
      }),
    };
  }, [focusId, graph.data, selectedId]);

  const node = graph.data?.nodes.find((item) => item.id === selectedId) ?? graph.data?.focus;
  const incoming = graph.data?.edges.filter((edge) => edge.target === node?.id) ?? [];
  const outgoing = graph.data?.edges.filter((edge) => edge.source === node?.id) ?? [];
  const inspectTarget: InspectTarget | null = !node ? null : node.kind === "evidence" ? { kind: "evidence", id: node.id } : node.kind === "run" ? { kind: "run", id: node.id } : node.kind === "trial" && node.id.startsWith("CMJ-") ? { kind: "trial", id: node.id } : node.kind === "metric" ? { kind: "metric", id: node.id } : node.kind === "figure" ? { kind: "figure", id: node.id } : null;

  return (
    <div className="drawer-backdrop" onMouseDown={wb.closeLineage}>
      <div className="drawer" role="dialog" aria-modal="true" aria-label={`Lineage of ${focusId}`} onMouseDown={(event) => event.stopPropagation()}>
        <header className="viewer-head">
          <span className="kind">Lineage</span>
          <strong className="mono">{focusId}</strong>
          <span className="faint">{graph.data ? `${graph.data.nodes.length} nodes · ${graph.data.edges.length} edges · ancestors complete, consumers to depth ${depth} · scroll to zoom, drag to pan` : ""}</span>
          <span className="spacer" />
          {focusId !== artifactId && <Button size="sm" onClick={() => setFocusId(artifactId)}>Back to {artifactId}</Button>}
          <button ref={closeRef} type="button" className="btn btn-sm" onClick={wb.closeLineage}><X size={12} />Close</button>
        </header>
        <div className="drawer-body">
          <div className="flow-host">
            {graph.isLoading && <div style={{ padding: 16 }}><Loading label="Computing provenance from stored artifacts" /></div>}
            {graph.error && <div style={{ padding: 16 }}><ErrorBox error={graph.error} /></div>}
            {graph.data && (
              <ReactFlow
                key={focusId}
                nodes={flow.nodes}
                edges={flow.edges}
                nodeTypes={nodeTypes}
                onInit={(instance) => {
                  // Readable scale, centred on the focused artefact; "fit view" in the controls shows the whole graph.
                  const focus = flow.nodes.find((item) => item.id === focusId);
                  if (focus) instance.setCenter(focus.position.x - 380, focus.position.y + 24, { zoom: 0.8 });
                }}
                minZoom={0.2} nodesDraggable={false} nodesConnectable={false} elementsSelectable onNodeClick={(_, item) => setSelectedId(item.id)} proOptions={{ hideAttribution: true }}>
                <Background color="transparent" />
                <Controls showInteractive={false} />
              </ReactFlow>
            )}
          </div>
          <aside className="inspector" style={{ borderLeft: "1px solid var(--line)" }}>
            {node ? (
              <>
                <div className="insp-head">
                  <div className="insp-kind"><span>{node.kind.replace("_", " ")}</span>{node.id === focusId && <State tone="tone-signal">FOCUS</State>}</div>
                  <div className="insp-title"><span className="mono">{node.id}</span> {node.label !== node.id ? node.label : ""}</div>
                </div>
                <div className="insp-scroll">
                  <section className="insp-sec"><h4>Metadata</h4><p>{node.metadata}</p></section>
                  {node.detail && (
                    <section className="insp-sec"><h4>Stored record</h4>
                      <KV rows={Object.entries(node.detail).slice(0, 18).map(([key, value]) => [key.replaceAll("_", " "), formatDetail(value), "mono"] as [string, string, "mono"])} />
                    </section>
                  )}
                  <section className="insp-sec"><h4>Derived from ({incoming.length})</h4>
                    {incoming.length ? incoming.map((edge) => <button key={edge.id} type="button" className="tree-item" style={{ paddingLeft: 0 }} onClick={() => setSelectedId(edge.source)}><span className="mono small">{edge.source}</span><span className="tag">{edge.label}</span></button>) : <p>Source node.</p>}
                  </section>
                  <section className="insp-sec"><h4>Consumed by ({outgoing.length})</h4>
                    {outgoing.length ? outgoing.map((edge) => <button key={edge.id} type="button" className="tree-item" style={{ paddingLeft: 0 }} onClick={() => setSelectedId(edge.target)}><span className="mono small">{edge.target}</span><span className="tag">{edge.label}</span></button>) : <p>Terminal within this scope.</p>}
                  </section>
                  <section className="insp-sec">
                    <div className="insp-actions">
                      {node.id !== focusId && <Button size="sm" onClick={() => setFocusId(node.id)}><Crosshair size={12} />Trace from this node</Button>}
                      {inspectTarget && <Button size="sm" variant="primary" onClick={() => { wb.inspect(inspectTarget); wb.closeLineage(); }}>Inspect in workbench</Button>}
                    </div>
                  </section>
                </div>
              </>
            ) : null}
          </aside>
        </div>
      </div>
    </div>
  );
}
