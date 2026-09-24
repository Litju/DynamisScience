"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import ReactFlow, { Background, Controls, type Edge, type Node } from "reactflow";
import { ArrowRight, BookOpen, Check, ChevronRight, CircleDot, Code2, Database, FileCheck2, Gauge, GitBranch, History, Info, LockKeyhole, Network, Play, RefreshCw, SlidersHorizontal, Sparkles, TerminalSquare, Waypoints } from "lucide-react";
import { scienceApi } from "@/lib/api";
import { DistributionChart, LongitudinalChart, ModelChart, ModelFitChart } from "@/components/charts";
import { Button, CodeBlock, EmptyState, KeyValue, LoadingState, MetricTile, Panel, SectionHeader, StatusBadge } from "@/components/ui";
import type { Evidence, LineageNode, Registry, RegistryEntry } from "@/lib/types";

type Dict = Record<string, unknown>;
const dict = (value: unknown): Dict => (value && typeof value === "object" ? (value as Dict) : {});
const text = (value: unknown, fallback = "—") => (typeof value === "string" ? value : fallback);

const TABS: { id: keyof Registry; label: string }[] = [
  { id: "metrics", label: "Metrics" },
  { id: "protocols", label: "Protocols" },
  { id: "algorithms", label: "Algorithms" },
  { id: "methods", label: "Methods" },
  { id: "models", label: "Models" },
];

export function RegistryView() {
  const query = useQuery({ queryKey: ["registry"], queryFn: scienceApi.registry });
  const [tab, setTab] = useState<keyof Registry>("metrics");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const registry = query.data;
  const items = useMemo<RegistryEntry[]>(() => (registry ? (registry[tab] as RegistryEntry[]) : []), [registry, tab]);
  const selected = items.find((item) => item.id === selectedId) ?? items[0];

  if (query.isLoading) return <LoadingState label="Loading scientific registry" />;
  if (!registry) return <EmptyState title="Registry unavailable" detail="Start the local science service to load metric contracts." />;

  return (
    <div className="view-stack">
      <SectionHeader
        eyebrow="Knowledge / Registry"
        title="Scientific contracts"
        description="Canonical definitions, protocols, algorithms, methods, and model specifications used by the local evidence layer."
        actions={<StatusBadge tone="cyan">VERSIONED</StatusBadge>}
      />
      <div className="registry-tabs">
        {TABS.map((item) => (
          <button key={item.id} className={tab === item.id ? "active" : ""} onClick={() => { setTab(item.id); setSelectedId(null); }}>
            {item.label}<span>{registry[item.id].length}</span>
          </button>
        ))}
      </div>
      <div className="registry-layout">
        <Panel
          className="registry-table-panel"
          eyebrow={`${tab} / contract catalog`}
          title={TABS.find((item) => item.id === tab)?.label ?? "Registry"}
          action={<span className="subtle">select a row for its definition</span>}
        >
          <div className="registry-table">
            <div className="registry-row registry-head"><span>Canonical ID</span><span>Name</span><span>Status</span><span>Usage</span></div>
            {items.map((item) => (
              <button
                key={item.id}
                className={`registry-row ${selected?.id === item.id ? "selected" : ""}`}
                onClick={() => setSelectedId(item.id)}
              >
                <span className="mono">{item.canonical_id ?? item.id}</span>
                <span>
                  <strong>{item.name}</strong>
                  <small>{item.method ?? item.description ?? item.estimator ?? item.frequency ?? ""}</small>
                </span>
                <StatusBadge tone={item.status === "ACTIVE" || item.status === "FROZEN" ? "good" : item.status === "PROTOTYPE" ? "warn" : "neutral"}>{item.status ?? "—"}</StatusBadge>
                <span className="mono">{item.usage_count ?? item.version ?? "—"}</span>
              </button>
            ))}
          </div>
        </Panel>
        <aside className="registry-inspector">
          <Panel
            eyebrow="Definition inspector"
            title={selected ? selected.name : "Select a contract"}
            action={selected && <StatusBadge tone="good">{selected.status ?? "—"}</StatusBadge>}
          >
            {selected ? <RegistryDetail item={selected} tab={tab} /> : <div className="empty-state"><BookOpen size={19} /><strong>Contract details</strong><span>Select a metric, protocol, or method to inspect its dependencies and limitations.</span></div>}
          </Panel>
          <Panel eyebrow="Registry principles" title="Authority boundaries">
            <div className="principle-list">
              <div><Code2 size={15} /><span>Canonical IDs distinguish computational definitions that share a unit.</span></div>
              <div><GitBranch size={15} /><span>Algorithms are versioned independently from study questions.</span></div>
              <div><LockKeyhole size={15} /><span>Frozen methods are never silently changed by a screen.</span></div>
            </div>
          </Panel>
        </aside>
      </div>
    </div>
  );
}

function RegistryDetail({ item, tab }: { item: RegistryEntry; tab: keyof Registry }) {
  const dependencies = Array.isArray(item.dependencies) ? item.dependencies : [];
  const limitations = Array.isArray(item.known_limitations) ? item.known_limitations : [];
  return (
    <div className="registry-detail">
      <KeyValue label="Canonical ID" value={item.canonical_id ?? item.id} mono />
      {tab === "metrics" && <KeyValue label="Quantity" value={item.quantity ?? "—"} />}
      {tab === "metrics" && <KeyValue label="Unit" value={item.unit ?? "—"} mono />}
      {item.description && <KeyValue label="Description" value={item.description} />}
      {item.method && <KeyValue label="Method" value={item.method} />}
      {item.estimator && <KeyValue label="Estimator" value={item.estimator} />}
      {item.fallback && <KeyValue label="Fallback" value={item.fallback} />}
      {item.frequency && <KeyValue label="Frequency" value={item.frequency} />}
      {item.protocol_id && <KeyValue label="Protocol" value={item.protocol_id} mono />}
      {item.algorithm && <KeyValue label="Algorithm" value={`${item.algorithm}@${item.version ?? "—"}`} mono />}
      {item.implementation && <KeyValue label="Implementation" value={item.implementation} mono />}
      {!item.algorithm && item.version && <KeyValue label="Version" value={item.version} mono />}
      {typeof item.usage_count === "number" && <KeyValue label="Referenced by specs" value={String(item.usage_count)} />}
      {dependencies.length > 0 && (
        <div className="detail-section">
          <span>Dependencies</span>
          <div className="tag-list">{dependencies.map((dependency) => <span className="tag" key={String(dependency)}>{String(dependency)}</span>)}</div>
        </div>
      )}
      {limitations.length > 0 && (
        <div className="detail-section">
          <span>Known limitations</span>
          {limitations.map((limitation) => <div className="limitation" key={String(limitation)}><Info size={13} />{String(limitation)}</div>)}
        </div>
      )}
    </div>
  );
}

export function RunsView({ initialRunId, onNavigate }: { initialRunId?: string; onNavigate: (view: string, id?: string) => void }) {
  const query = useQuery({ queryKey: ["runs"], queryFn: scienceApi.runs });
  const [selectedId, setSelectedId] = useState(initialRunId ?? "");
  const runs = query.data ?? [];
  const selected = runs.find((run) => run.id === selectedId) ?? runs[0];
  if (query.isLoading) return <LoadingState label="Loading immutable execution ledger" />;
  return (
    <div className="view-stack">
      <SectionHeader
        eyebrow="Science / Runs"
        title="Execution ledger"
        description="Every execution is append-only: specification, snapshot, software environment, diagnostics, and outputs are retained. Changing the configuration creates a new run."
        actions={<><StatusBadge tone="purple">APPEND-ONLY</StatusBadge><Button size="sm" variant="ghost" onClick={() => void query.refetch()}><RefreshCw size={13} /> Refresh</Button></>}
      />
      <div className="metric-grid run-metrics">
        <MetricTile label="Completed runs" value={String(runs.length).padStart(2, "0")} detail="all retained locally" state="FROZEN" />
        <MetricTile label="Methods" value={String(new Set(runs.map((run) => run.method_id)).size).padStart(2, "0")} detail="registered method contracts" state="VALID" />
        <MetricTile label="Snapshots" value={String(new Set(runs.map((run) => run.snapshot_id)).size).padStart(2, "0")} detail="immutable inputs" state="SYNTHETIC" />
        <MetricTile label="Repro keys" value={String(runs.filter((run) => run.reproducibility_key).length)} detail="machine-readable" state="VALID" />
      </div>
      <Panel eyebrow="Run table / append-only" title="Scientific executions" action={<span className="subtle">select a row to inspect</span>}>
        <div className="table-scroll">
          <table className="data-table runs-table">
            <thead>
              <tr><th>Run</th><th>Spec</th><th>Method</th><th>Dataset</th><th>Cohort</th><th>Status</th><th>Duration</th><th>Created</th><th>Outputs</th></tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr key={run.id} className={selected?.id === run.id ? "selected" : ""} onClick={() => setSelectedId(run.id)}>
                  <td className="mono strong-cell">{run.id}</td>
                  <td className="mono">{run.analysis_spec_id}</td>
                  <td className="mono">{run.method_id}</td>
                  <td className="mono">{run.snapshot_id}</td>
                  <td className="mono">{run.cohort_id}</td>
                  <td><StatusBadge tone={run.status === "COMPLETED" ? "good" : "warn"}>{run.status}</StatusBadge></td>
                  <td className="mono">{run.duration_ms.toFixed(0)} ms</td>
                  <td className="mono">{new Date(run.created_at).toLocaleString([], { month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit" })}</td>
                  <td className="mono">{run.output_artifact_ids.length}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
      {selected && (
        <div className="run-detail-grid">
          <Panel eyebrow="Run specification" title={selected.id} action={<StatusBadge tone="good">{selected.status}</StatusBadge>}>
            <div className="run-detail-hero">
              <div><span>Method</span><strong className="mono">{selected.method_id}</strong></div>
              <div><span>Snapshot</span><strong className="mono">{selected.snapshot_id}</strong></div>
              <div><span>Seed</span><strong className="mono">{selected.seed ?? "—"}</strong></div>
              <div><span>Cohort</span><strong className="mono">{selected.cohort_id}</strong></div>
            </div>
            <CodeBlock
              value={{
                analysis_spec_id: selected.analysis_spec_id,
                analysis_spec: selected.execution?.analysis_spec,
                cohort: selected.execution?.cohort,
                software_versions: selected.software_versions,
                reproducibility_key: selected.reproducibility_key,
              }}
              label="Execution envelope"
            />
            <div className="run-detail-actions">
              <Button size="sm" onClick={() => onNavigate("analyses", selected.id)}>Open analysis <ArrowRight size={13} /></Button>
              <Button size="sm" variant="ghost" onClick={() => onNavigate("lineage", selected.id)}>View lineage <GitBranch size={13} /></Button>
            </div>
          </Panel>
          <Panel eyebrow="Outputs and diagnostics" title="Run outputs" action={<span className="mono subtle">{selected.output_artifact_ids.length} artifacts</span>}>
            <div className="output-list">
              {(selected.output_artifact_ids.length ? selected.output_artifact_ids : ["No output artifacts"]).map((id) => (
                <button key={id} onClick={() => onNavigate("lineage", id)}>
                  <FileOutputIcon />
                  <span><strong className="mono">{id}</strong><small>open provenance</small></span>
                  <ArrowRight size={13} />
                </button>
              ))}
            </div>
            <div className="diagnostic-json"><span>Diagnostics</span><pre>{JSON.stringify(selected.diagnostics, null, 2)}</pre></div>
          </Panel>
        </div>
      )}
    </div>
  );
}

function FileOutputIcon() {
  return <span className="output-icon"><FileCheck2 size={14} /></span>;
}

export function LineageView({ initialArtifactId }: { initialArtifactId?: string }) {
  const artifactId = initialArtifactId ?? "REPORT-001";
  const query = useQuery({ queryKey: ["lineage", artifactId], queryFn: () => scienceApi.lineage(artifactId) });
  const [selected, setSelected] = useState(artifactId);

  const nodes = useMemo(() => query.data?.nodes ?? [], [query.data]);
  const edges = useMemo(() => query.data?.edges ?? [], [query.data]);
  const graph = useMemo(() => createLineageGraph(nodes, edges), [nodes, edges]);
  const node: LineageNode | undefined = nodes.find((item) => item.id === selected) ?? query.data?.focus ?? nodes[0];

  if (query.isLoading) return <LoadingState label="Resolving provenance graph" />;
  if (query.error) return <EmptyState title="Provenance unavailable" detail={String((query.error as Error).message)} />;

  const incoming = edges.filter((edge) => edge.target === node?.id);
  const outgoing = edges.filter((edge) => edge.source === node?.id);

  return (
    <div className="view-stack">
      <SectionHeader
        eyebrow="Knowledge / Lineage"
        title="Every result has a route home"
        description="Move from report → evidence → analysis → cohort → snapshot → measurement without losing the scientific context. Nodes are derived from stored artifacts, not asserted."
        actions={<StatusBadge tone="cyan">{artifactId}</StatusBadge>}
      />
      <div className="lineage-toolbar">
        <div className="lineage-path">
          <span>REPORT-001</span><ChevronRight size={13} />
          <span>EVIDENCE</span><ChevronRight size={13} />
          <strong>{artifactId}</strong>
        </div>
        <div className="lineage-legend">
          <span><i className="edge-cyan" />derived</span>
          <span><i className="edge-amber" />included</span>
          <span><i className="edge-gray" />cited</span>
        </div>
      </div>
      <div className="lineage-layout">
        <Panel
          className="lineage-panel"
          eyebrow="Provenance DAG"
          title="Source-to-result graph"
          action={<span className="subtle">{nodes.length} nodes · {edges.length} edges</span>}
        >
          <div className="flow-canvas lineage-canvas">
            <ReactFlow
              nodes={graph.nodes}
              edges={graph.edges}
              nodeTypes={{ scientific: LineageNodeView }}
              onNodeClick={(_, item) => setSelected(String(item.id))}
              fitView
              fitViewOptions={{ padding: 0.22 }}
              nodesDraggable={false}
              nodesConnectable={false}
            >
              <Background color="#24343f" gap={22} size={1} />
              <Controls showInteractive={false} />
            </ReactFlow>
          </div>
        </Panel>
        <aside className="lineage-inspector">
          <Panel eyebrow="Node inspector" title={node?.id ?? "Select node"} action={<StatusBadge tone="cyan">{node?.kind ?? "—"}</StatusBadge>}>
            {node && (
              <div className="lineage-detail">
                <div className="lineage-node-hero"><Network size={22} /><div><strong>{node.label}</strong><span>{node.kind}</span></div></div>
                <KeyValue label="Node ID" value={node.id} mono />
                <KeyValue label="Metadata" value={node.metadata} />
                {node.detail && Object.entries(node.detail).slice(0, 10).map(([key, value]) => (
                  <KeyValue key={key} label={key.replaceAll("_", " ")} value={typeof value === "object" && value !== null ? JSON.stringify(value).slice(0, 90) : String(value)} mono={typeof value === "number" || typeof value === "string"} />
                ))}
                <div className="detail-section">
                  <span>Incoming relations</span>
                  <div className="tag-list">
                    {incoming.length === 0 ? <span className="subtle">This is a source node.</span> : incoming.map((edge) => <span className="tag" key={edge.id}>{edge.source} · {edge.label}</span>)}
                  </div>
                </div>
                <div className="detail-section">
                  <span>Outgoing relations</span>
                  <div className="tag-list">
                    {outgoing.length === 0 ? <span className="subtle">This is a terminal node.</span> : outgoing.map((edge) => <span className="tag" key={edge.id}>{edge.target} · {edge.label}</span>)}
                  </div>
                </div>
              </div>
            )}
          </Panel>
          <Panel eyebrow="Reproducibility record" title="Local evidence">
            <div className="repro-card"><Check size={15} /><div><strong>Deterministic regeneration available</strong><span>Seed 20260924 · generator v1.0.0</span></div></div>
            <div className="repro-card"><LockKeyhole size={15} /><div><strong>Snapshot checksums retained</strong><span>8 analytical files hashed</span></div></div>
          </Panel>
        </aside>
      </div>
    </div>
  );
}

function LineageNodeView({ data }: { data: Dict }) {
  const kind = String(data.kind);
  const icon = kind === "generator" ? <Code2 size={14} /> : kind === "measurement" || kind === "trial" ? <Waypoints size={14} /> : kind === "snapshot" ? <Database size={14} /> : kind === "evidence" ? <GitBranch size={14} /> : kind === "run" ? <History size={14} /> : <CircleDot size={14} />;
  return (
    <div className={`lineage-node lineage-${kind}`}>
      <span className="lineage-node-icon">{icon}</span>
      <div><strong>{String(data.label)}</strong><small>{kind}</small></div>
    </div>
  );
}

function createLineageGraph(nodes: LineageNode[], edges: { id: string; source: string; target: string; relation: string; label: string }[]): { nodes: Node[]; edges: Edge[] } {
  return {
    nodes: nodes.map((node, index) => ({
      id: node.id,
      type: "scientific",
      position: { x: 30 + (index % 4) * 220, y: 35 + Math.floor(index / 4) * 130 },
      data: { kind: node.kind, label: node.label, metadata: node.metadata },
    })),
    edges: edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      label: edge.label,
      style: { stroke: edge.relation === "derives" || edge.relation === "extracted_from" ? "#59d6c7" : edge.relation === "included_in" || edge.relation === "stored_in" ? "#e5b567" : "#617785" },
      labelStyle: { fill: "#8da1ad", fontSize: 9 },
      labelBgStyle: { fill: "#101820", fillOpacity: 0.9 },
    })),
  };
}

export function ModelLabView() {
  const query = useQuery({ queryKey: ["training-model"], queryFn: scienceApi.trainingModel });
  const [load, setLoad] = useState<number[] | null>(null);
  const [params, setParams] = useState({ tau_fitness_weeks: 4, fatigue_tau_weeks: 1.8, fitness_gain: 1, fatigue_penalty: 0.35 });
  const simulation = useMutation({ mutationFn: () => scienceApi.simulate(load ?? [], params) });

  const run = query.data?.run;
  const observedLoad = useMemo(() => {
    if (load) return load;
    const states = run?.output.states ?? [];
    return states.map((state) => state.load);
  }, [load, run]);

  if (query.isLoading) return <LoadingState label="Loading mechanistic prototype" />;
  if (!run || !query.data) return <EmptyState title="Model unavailable" detail="Start the local science service to load the fitted prototype." />;

  const simulated = simulation.data?.states ?? [];
  const activeStates = simulated.length ? simulated : run.output.states;
  const fitted = run.parameters;

  return (
    <div className="view-stack">
      <SectionHeader
        eyebrow="Science / ModelLab"
        title="Training response, made inspectable"
        description="A real lightweight fitness–fatigue impulse model fitted to the generated training-load and CMJ observations. It is a prototype, not a black-box prediction engine."
        actions={<><StatusBadge tone="warn">MECHANISTIC PROTOTYPE</StatusBadge><StatusBadge tone="purple">SYNTHETIC DEMONSTRATION</StatusBadge></>}
      />
      <div className="model-hero">
        <div>
          <div className="eyebrow">ModelSpec / {query.data.spec.id}</div>
          <h2>{query.data.spec.name}</h2>
          <p>{query.data.spec.description}</p>
          <div className="model-tags">
            <span>Spec v{query.data.spec.version}</span>
            <span>Local executor</span>
            <span>No GPU / no hosted AI</span>
            <span>Status {query.data.spec.status}</span>
          </div>
        </div>
        <div className="model-equation mono">
          fitness<sub>t</sub> = decay(τ<sub>f</sub>) · fitness<sub>t−1</sub> + gain · load<sub>t</sub><br />
          fatigue<sub>t</sub> = decay(τ<sub>g</sub>) · fatigue<sub>t−1</sub> + load<sub>t</sub><br />
          <strong>state = fitness − penalty · fatigue</strong>
        </div>
      </div>
      <div className="model-grid">
        <Panel
          className="model-chart-panel"
          eyebrow="Fitted prototype / observed versus modelled"
          title="Fitness–fatigue fit against the generated CMJ series"
          action={<StatusBadge tone="good">FIT RMSE {run.output.fit_rmse_outcome_units.toFixed(4)}</StatusBadge>}
        >
          <ModelFitChart
            weeks={run.output.observed_weeks}
            observed={run.output.observed_performance}
            modelled={run.output.modelled_performance}
            residuals={run.output.residuals}
            unit="N·s·kg⁻¹"
          />
          <div className="model-chart-legend">
            <span><i className="legend-dot cyan" />observed CMJ (group mean)</span>
            <span><i className="legend-line amber" />modelled response</span>
            <span className="mono subtle">standardised RMSE {run.output.fit_rmse_standardized.toFixed(3)}</span>
          </div>
        </Panel>
        <Panel eyebrow="Scenario controls" title="Change the input" action={<StatusBadge tone="cyan">INTERACTIVE</StatusBadge>}>
          <div className="scenario-editor">
            <div className="scenario-row">
              <span>Weekly load scenario (AU)</span>
              <Button size="sm" variant="ghost" onClick={() => setLoad(null)}>Reset to observed</Button>
            </div>
            <div className="load-sliders">
              {observedLoad.map((value, index) => (
                <label key={index}>
                  <span>W{index + 1}</span>
                  <input
                    type="range"
                    min="150"
                    max="700"
                    step="10"
                    value={value}
                    onChange={(event) => {
                      const next = [...observedLoad];
                      next[index] = Number(event.target.value);
                      setLoad(next);
                    }}
                  />
                  <strong className="mono">{value}</strong>
                </label>
              ))}
            </div>
          </div>
          <div className="parameter-grid">
            <Parameter label="Fitness τ (weeks)" value={params.tau_fitness_weeks} min={1} max={10} step={0.1} onChange={(value) => setParams((current) => ({ ...current, tau_fitness_weeks: value }))} />
            <Parameter label="Fatigue τ (weeks)" value={params.fatigue_tau_weeks} min={0.5} max={5} step={0.1} onChange={(value) => setParams((current) => ({ ...current, fatigue_tau_weeks: value }))} />
            <Parameter label="Fitness gain" value={params.fitness_gain} min={0.1} max={1.5} step={0.01} onChange={(value) => setParams((current) => ({ ...current, fitness_gain: value }))} />
            <Parameter label="Fatigue penalty" value={params.fatigue_penalty} min={0} max={0.8} step={0.01} onChange={(value) => setParams((current) => ({ ...current, fatigue_penalty: value }))} />
          </div>
          <div className="scenario-actions">
            <Button size="sm" variant="primary" onClick={() => simulation.mutate()} disabled={simulation.isPending}>
              <Play size={13} />{simulation.isPending ? "Simulating…" : "Run scenario"}
            </Button>
            <span className="subtle">{simulation.data ? "Showing simulated scenario" : "Showing the fitted baseline"}</span>
          </div>
        </Panel>
      </div>
      <Panel className="model-chart-panel" eyebrow="Simulated state" title="Load, fitness, fatigue and performance state" action={<StatusBadge tone={simulation.data ? "cyan" : "neutral"}>{simulation.data ? "SCENARIO SIMULATED" : "BASELINE FIT"}</StatusBadge>}>
        <ModelChart states={activeStates} />
        <div className="model-chart-legend">
          <span><i className="legend-block" />weekly load</span>
          <span><i className="legend-line cyan" />performance state</span>
          <span className="mono subtle">arbitrary units · aggregate prototype</span>
        </div>
      </Panel>
      <div className="model-bottom">
        <Panel eyebrow="Fitted parameters" title="Time constants selected by the fit" action={<StatusBadge tone="good">COMPUTED</StatusBadge>}>
          <div className="parameter-readout">
            <div><span>tau fitness weeks</span><strong className="mono">{fitted.tau_fitness_weeks}</strong></div>
            <div><span>fatigue tau weeks</span><strong className="mono">{fitted.fatigue_tau_weeks}</strong></div>
            <div><span>fitness gain</span><strong className="mono">{fitted.fitness_gain}</strong></div>
            <div><span>fatigue penalty</span><strong className="mono">{fitted.fatigue_penalty}</strong></div>
          </div>
          <div className="model-residuals">
            <span>Fit status</span><strong>{text(run.diagnostics.fit_status)}</strong>
            <span>Observed weeks</span><strong className="mono">{run.output.observed_weeks.length}</strong>
            <span>RMSE (standardised)</span><strong className="mono">{run.output.fit_rmse_standardized.toFixed(4)}</strong>
            <span>RMSE ({text(dict(run.output).unit, "N·s·kg⁻¹")})</span><strong className="mono">{run.output.fit_rmse_outcome_units.toFixed(4)}</strong>
          </div>
          <div className="formula-note"><Info size={14} /><span>Parameters are selected by a deterministic grid search over time constants and fatigue penalty, minimising the standardised residual against the observed weekly CMJ mean.</span></div>
        </Panel>
        <Panel eyebrow="Model boundaries" title="What is real here">
          <div className="model-boundaries">
            <div><Check size={14} /><span>Uses generated training impulse and CMJ observations.</span></div>
            <div><Check size={14} /><span>Exposes fitted parameters, observed and modelled series, and residuals.</span></div>
            <div><Check size={14} /><span>Changing load or time constants changes the computed output.</span></div>
            <div><Info size={14} /><span>Does not claim individual readiness, injury risk, or causal prediction.</span></div>
          </div>
          <div className="roadmap-cards">
            <span className="roadmap-label">Architecture-ready, not implemented</span>
            {(query.data.spec.roadmap ?? []).map((item) => (
              <div key={item.capability}>
                {item.capability.includes("Bayesian") ? <TerminalSquare size={14} /> : item.capability.includes("Machine") ? <Sparkles size={14} /> : item.capability.includes("Physics") ? <Gauge size={14} /> : <SlidersHorizontal size={14} />}
                {item.capability}
              </div>
            ))}
          </div>
        </Panel>
      </div>
    </div>
  );
}

function Parameter({ label, value, min, max, step, onChange }: { label: string; value: number; min: number; max: number; step: number; onChange: (value: number) => void }) {
  return (
    <label className="parameter">
      <span>{label}</span>
      <input type="range" min={min} max={max} step={step} value={value} onChange={(event) => onChange(Number(event.target.value))} />
      <strong className="mono">{value.toFixed(2)}</strong>
    </label>
  );
}

export function ReportView({ onNavigate }: { onNavigate: (view: string, id?: string) => void }) {
  const report = useQuery({ queryKey: ["report"], queryFn: scienceApi.report });
  if (report.isLoading) return <LoadingState label="Assembling the interim report from evidence artifacts" />;
  if (report.error || !report.data) return <EmptyState title="Report unavailable" detail="Start the local science service to assemble the report from stored artifacts." />;

  const data = report.data;
  const effect = data.evidence.find((item) => item.kind === "EFFECT");
  const reliability = data.evidence.find((item) => item.kind === "RELIABILITY");
  const change = data.evidence.find((item) => item.kind === "CHANGE");
  const cvFigure = data.figures.find((figure) => figure.id === "FIG-0002");
  const cvValues = Array.isArray(cvFigure?.spec.values) ? (cvFigure.spec.values as number[]) : [];

  return (
    <div className="view-stack report-view">
      <SectionHeader
        eyebrow="Knowledge / Reports"
        title={data.title}
        description="A reproducible in-app report assembled from frozen specifications, computed runs, and evidence artifacts."
        actions={<><StatusBadge tone="warn">{data.status}</StatusBadge><Button size="sm" onClick={() => onNavigate("lineage", "REPORT-001")}><GitBranch size={14} /> Trace report</Button></>}
      />
      <div className="report-paper">
        <div className="report-cover">
          <div className="report-stamp">DYNAMISSCIENCE / INTERIM</div>
          <h2>Strength Intervention</h2>
          <p>{data.study.title}</p>
          <div className="report-meta">
            <span>{data.study.id}</span>
            <span>{data.snapshot.id}</span>
            <span>FROZEN {data.study.analysis_spec_ids.length} SPECS</span>
            <span>SYNTHETIC</span>
          </div>
        </div>

        <ReportSection number="01" title="Study information">
          <p>{data.study.research_question}</p>
          <div className="report-facts">
            <span>Design</span><strong>{data.study.design}</strong>
            <span>Population</span><strong>{data.study.participant_count} synthetic elite football athletes</strong>
            <span>Intervention</span><strong>{data.study.intervention}</strong>
            <span>Snapshot</span><strong className="mono">{data.snapshot.id}</strong>
          </div>
        </ReportSection>

        <ReportSection number="02" title="Methods">
          <p>
            Primary inference uses a group × time repeated-measures model with athlete-level random effects and a week-centred
            parameterisation, so the pre-specified intervention × time contrast is the difference in change from week 1 to week 10.
            Reliability is estimated from repeated baseline trials using ICC(3,1) with within-subject CV and typical error. Individual
            change is descriptive and benchmarked against the typical error of a change. Force metrics are extracted from the 1000 Hz
            synthetic traces by deterministic phase-aware integration.
          </p>
          <div className="method-chips">
            <span>MixedLM / athlete random slope</span>
            <span>ICC(3,1) + 95% CI</span>
            <span>typical error = √MSE</span>
            <span>phase-aware force integration</span>
            <span>seed {data.snapshot.seed}</span>
          </div>
        </ReportSection>

        <ReportSection number="03" title="Cohort and data quality">
          <div className="report-quality">
            <div><strong>{data.data_health.valid_measurements.toLocaleString()}</strong><span>valid trials</span></div>
            <div><strong>{data.data_health.excluded_measurements}</strong><span>excluded, still visible</span></div>
            <div><strong>{data.data_health.missing_observations}</strong><span>missing slots</span></div>
            <div><strong>{data.data_health.provenance_completeness.toFixed(1)}%</strong><span>provenance complete</span></div>
          </div>
          <p>
            Excluded trials remain in the registry and are omitted from primary inference only when the frozen quality rule applies.
            {data.data_health.missing_slots.length > 0 && ` ${data.data_health.missing_slots.length} expected trial slots were not captured during match-congestion weeks and are reported rather than imputed.`}
          </p>
        </ReportSection>

        <ReportSection
          number="04"
          title="Longitudinal finding"
          action={<Button size="sm" variant="ghost" onClick={() => onNavigate("analyses", effect?.analysis_run_id ?? "RUN-0001")}>Open analysis <ArrowRight size={13} /></Button>}
        >
          <LongitudinalChart data={data.longitudinal_signal} />
          <div className="report-figure-caption">
            <span className="mono">FIG-0001</span>
            <span>Weekly group mean concentric impulse with the weeks 3–10 strength block marked. Values are computed from {data.snapshot.id}.</span>
          </div>
          <EvidenceBlock evidence={effect} onNavigate={onNavigate} />
        </ReportSection>

        <ReportSection
          number="05"
          title="Reliability evidence"
          action={<Button size="sm" variant="ghost" onClick={() => onNavigate("lineage", reliability?.id ?? "EVID-0002")}>Inspect evidence <ArrowRight size={13} /></Button>}
        >
          {cvValues.length > 0 && (
            <>
              <DistributionChart values={cvValues} title="Within-subject CV across baseline athletes" unit="%" />
              <div className="report-figure-caption">
                <span className="mono">FIG-0002</span>
                <span>Per-athlete within-subject coefficient of variation computed from the repeated valid baseline trials of {data.snapshot.id}.</span>
              </div>
            </>
          )}
          <EvidenceBlock evidence={reliability} onNavigate={onNavigate} />
          <EvidenceBlock evidence={change} onNavigate={onNavigate} />
        </ReportSection>

        <ReportSection number="06" title="Interpretation and limitations">
          <p>
            The computed intervention × time contrast is a demonstration of longitudinal analysis against a known synthetic intervention
            structure. It must not be generalised to real athletes, clinical decisions, or readiness decisions.
          </p>
          <ul className="report-list">
            <li>Synthetic measurements emulate a future DynamisETL contract and contain no real athlete data.</li>
            <li>Force phase boundaries are deterministic and intentionally inspectable; biomechanical perfection is not claimed.</li>
            <li>Wellness variables are contextual observations, not a proprietary readiness score.</li>
            <li>ModelLab is a mechanistic prototype, not an individual prediction system.</li>
            <li>Reliability is estimated from two baseline trials per athlete, which bounds the precision of the ICC.</li>
          </ul>
        </ReportSection>

        <ReportSection number="07" title="Reproducibility">
          <div className="report-repro">
            <div><Code2 size={15} /><span>Generator</span><strong className="mono">{data.snapshot.generator_version}</strong></div>
            <div><LockKeyhole size={15} /><span>Snapshot</span><strong className="mono">{data.snapshot.id} / {Object.keys(data.snapshot.checksums).length} checksums</strong></div>
            <div><History size={15} /><span>Evidence chain</span><strong className="mono">{data.evidence.map((item) => item.id).join(" · ")}</strong></div>
          </div>
          <p className="report-provenance-note">{data.provenance_note}</p>
        </ReportSection>
      </div>
      <div className="report-footer">
        <span>Generated from local analytical artifacts · no external services</span>
        <Button size="sm" variant="ghost" onClick={() => onNavigate("runs")}>Open execution ledger <ArrowRight size={13} /></Button>
      </div>
    </div>
  );
}

function ReportSection({ number, title, action, children }: { number: string; title: string; action?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="report-section">
      <div className="report-section-heading"><span className="mono">{number}</span><h3>{title}</h3>{action}</div>
      {children}
    </section>
  );
}

function EvidenceBlock({ evidence, onNavigate }: { evidence?: Evidence; onNavigate: (view: string, id?: string) => void }) {
  if (!evidence) return <EmptyState title="Evidence pending" detail="Run the analysis to create an evidence artifact." />;
  const halfWidth = evidence.uncertainty;
  const low = evidence.value !== null && halfWidth !== null ? evidence.value - halfWidth : null;
  const high = evidence.value !== null && halfWidth !== null ? evidence.value + halfWidth : null;
  return (
    <div className="report-evidence">
      <div className="report-evidence-value">
        <strong>{evidence.value?.toFixed(3) ?? "—"}</strong>
        <span>{evidence.unit}</span>
        <small>{evidence.uncertainty_label ?? "estimate"}: {halfWidth?.toFixed(3) ?? "—"}</small>
        {low !== null && high !== null && <small className="mono">{low.toFixed(3)} → {high.toFixed(3)}</small>}
      </div>
      <div>
        <h4>{evidence.title}</h4>
        <p>{evidence.interpretation}</p>
        <div className="report-evidence-meta">
          <span>Population: {evidence.population}</span>
          <span>n = {evidence.sample_size}</span>
          <span className="mono">{evidence.analysis_run_id}</span>
          <span className="mono">{evidence.id}</span>
          <Button size="sm" variant="ghost" onClick={() => onNavigate("lineage", evidence.id)}>Evidence passport <ArrowRight size={13} /></Button>
        </div>
      </div>
    </div>
  );
}
