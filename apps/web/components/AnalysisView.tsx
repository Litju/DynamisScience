"use client";

import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import ReactFlow, { Background, Controls, MiniMap, type Edge, type Node, type NodeProps } from "reactflow";
import { ArrowRight, CheckCircle2, CircleDot, Database, FileOutput, Filter, GitBranch, Hexagon, Play, RotateCcw, Sigma, SlidersHorizontal, TestTube2, TriangleAlert } from "lucide-react";
import { scienceApi } from "@/lib/api";
import { Button, CodeBlock, EvidencePassport, KeyValue, LoadingState, MetricTile, Panel, SectionHeader, StatusBadge } from "@/components/ui";
import type { Evidence, Run } from "@/lib/types";

type Dict = Record<string, unknown>;
function dict(value: unknown): Dict { return value && typeof value === "object" ? (value as Dict) : {}; }
function num(value: unknown, fallback = 0) { return typeof value === "number" && Number.isFinite(value) ? value : fallback; }
function text(value: unknown, fallback = "—") { return typeof value === "string" ? value : fallback; }

const METHODS = [
  { id: "METH-LONG", label: "Group × time longitudinal model" },
  { id: "METH-REL", label: "Baseline repeated-trial reliability" },
  { id: "METH-IND", label: "Individual change context" },
];

const OUTCOMES = [
  { id: "MET-CMJ-IMPULSE", label: "Concentric impulse" },
  { id: "MET-CMJ-BRAKING-DURATION", label: "Eccentric braking duration" },
  { id: "MET-CMJ-HEIGHT", label: "Jump height" },
  { id: "MET-CMJ-BRAKING-IMPULSE", label: "Braking impulse" },
  { id: "MET-CMJ-POWER", label: "Peak power" },
  { id: "MET-CMJ-DEPTH", label: "Countermovement depth" },
  { id: "MET-CMJ-RSI-MOD", label: "RSI-mod" },
];

function ScienceNode({ data }: NodeProps) {
  const kind = String(data.kind ?? "default");
  const icon = kind === "question" ? <CircleDot size={15} /> : kind === "data" ? <Database size={15} /> : kind === "cohort" ? <Filter size={15} /> : kind === "method" ? <SlidersHorizontal size={15} /> : kind === "analysis" ? <Sigma size={15} /> : kind === "diagnostic" ? <TestTube2 size={15} /> : kind === "evidence" ? <Hexagon size={15} /> : <FileOutput size={15} />;
  return (
    <div className={`flow-node flow-node-${kind}`}>
      <div className="flow-node-icon">{icon}</div>
      <div><strong>{String(data.label)}</strong><small>{String(data.sublabel ?? kind)}</small></div>
      <span className="flow-state">{String(data.state ?? "VALID")}</span>
    </div>
  );
}

const nodeTypes = { scientific: ScienceNode };

export function AnalysisView({ onNavigate, initialNodeId }: { onNavigate: (view: string, id?: string) => void; initialNodeId?: string }) {
  const queryClient = useQueryClient();
  const runsQuery = useQuery({ queryKey: ["runs"], queryFn: scienceApi.runs });
  const evidenceQuery = useQuery({ queryKey: ["evidence"], queryFn: scienceApi.evidence });
  const [selectedNode, setSelectedNode] = useState(initialNodeId ?? "RUN-0001");
  const [methodId, setMethodId] = useState("METH-LONG");
  const [outcomeId, setOutcomeId] = useState("MET-CMJ-IMPULSE");

  const execute = useMutation({
    mutationFn: () => scienceApi.execute({ method_id: methodId, outcome_metric_id: outcomeId, parameters: { reference_week: 1, contrast_week: 10 } }),
    onSuccess: (created) => {
      void queryClient.invalidateQueries({ queryKey: ["runs"] });
      void queryClient.invalidateQueries({ queryKey: ["evidence"] });
      setSelectedNode(created.id);
    },
  });

  const runs = useMemo(() => runsQuery.data ?? [], [runsQuery.data]);
  const evidence = useMemo(() => evidenceQuery.data ?? [], [evidenceQuery.data]);

  const selectedRun = useMemo(() => {
    if (!selectedNode) return runs[0];
    return (
      runs.find((run) => run.id === selectedNode) ??
      runs.find((run) => run.analysis_spec_id === selectedNode) ??
      runs.find((run) => run.method_id === selectedNode) ??
      runs[0]
    );
  }, [runs, selectedNode]);

  const selectedEvidence = useMemo(
    () => evidence.find((item) => item.analysis_run_id === selectedRun?.id) ?? evidence[0],
    [evidence, selectedRun],
  );

  useEffect(() => {
    if (selectedRun && selectedNode !== selectedRun.id && !runs.some((run) => run.id === selectedNode)) {
      setSelectedNode(selectedRun.id);
    }
  }, [runs, selectedNode, selectedRun]);

  const flow = useMemo(() => createFlow(selectedRun, selectedEvidence), [selectedEvidence, selectedRun]);

  if (runsQuery.isLoading) return <LoadingState label="Loading analysis specifications and immutable runs" />;

  return (
    <div className="view-stack">
      <SectionHeader
        eyebrow="Science / Analysis Canvas"
        title="From question to evidence"
        description="A typed scientific DAG. Nodes are executable specifications or immutable outputs; the GUI is not the authority."
        actions={
          <>
            <StatusBadge tone="purple">FROZEN SPECS</StatusBadge>
            <Button size="sm" variant="primary" onClick={() => execute.mutate()} disabled={execute.isPending}>
              <Play size={14} />{execute.isPending ? "Executing…" : "Execute analysis"}
            </Button>
          </>
        }
      />
      <div className="analysis-toolbar">
        <div className="analysis-selector">
          <span>Method</span>
          <select value={methodId} onChange={(event) => setMethodId(event.target.value)}>
            {METHODS.map((method) => <option key={method.id} value={method.id}>{method.label}</option>)}
          </select>
        </div>
        <div className="analysis-selector">
          <span>Outcome</span>
          <select value={outcomeId} onChange={(event) => setOutcomeId(event.target.value)}>
            {OUTCOMES.map((outcome) => <option key={outcome.id} value={outcome.id}>{outcome.label}</option>)}
          </select>
        </div>
        <div className="analysis-toolbar-note">
          <GitBranch size={14} />
          <span>Changing configuration creates a new <strong>RUN-xxxx</strong> with its own EvidenceArtifact; completed runs are never mutated.</span>
        </div>
        <Button size="sm" variant="ghost" onClick={() => execute.reset()}><RotateCcw size={13} /> Clear status</Button>
      </div>
      {execute.isSuccess && (
        <div className="execution-banner">
          <CheckCircle2 size={16} />
          <span>
            New immutable run created: <strong>{execute.data.id}</strong> with evidence <strong>{execute.data.evidence_artifact.id}</strong>.
          </span>
          <Button size="sm" variant="ghost" onClick={() => onNavigate("runs", execute.data.id)}>Open run <ArrowRight size={13} /></Button>
          <Button size="sm" variant="ghost" onClick={() => onNavigate("lineage", execute.data.evidence_artifact.id)}>Trace evidence <ArrowRight size={13} /></Button>
        </div>
      )}
      {execute.isError && (
        <div className="execution-banner error">
          <TriangleAlert size={16} />
          <span>Execution failed: {String((execute.error as Error).message)}</span>
        </div>
      )}
      <div className="analysis-workspace">
        <Panel
          className="dag-panel"
          eyebrow="Scientific lineage / executable graph"
          title="Analysis DAG"
          action={
            <div className="dag-legend">
              <span><i className="node-dot question" />question</span>
              <span><i className="node-dot data" />data</span>
              <span><i className="node-dot method" />method</span>
              <span><i className="node-dot evidence" />evidence</span>
            </div>
          }
        >
          <div className="flow-canvas">
            <ReactFlow nodes={flow.nodes} edges={flow.edges} nodeTypes={nodeTypes} onNodeClick={(_, node) => setSelectedNode(String(node.id))} fitView fitViewOptions={{ padding: 0.2 }} nodesDraggable={false} nodesConnectable={false} elementsSelectable>
              <Background color="#24343f" gap={22} size={1} />
              <Controls showInteractive={false} />
              <MiniMap nodeColor={(node) => (node.data?.kind === "evidence" ? "#59d6c7" : "#425966")} maskColor="rgba(11,16,22,.7)" />
            </ReactFlow>
          </div>
          <div className="dag-footer">
            <span><span className="flow-state-dot" />All edges carry a typed relation</span>
            <span>Click a node to inspect its specification and provenance</span>
          </div>
        </Panel>
        <aside className="analysis-inspector">
          <Panel eyebrow="Inspector / selected node" title={selectedRun?.id ?? "Run not selected"} action={<StatusBadge tone={selectedRun?.status === "COMPLETED" ? "good" : "warn"}>{selectedRun?.status ?? "—"}</StatusBadge>}>
            {selectedRun ? <RunInspector run={selectedRun} evidence={selectedEvidence} onNavigate={onNavigate} /> : <div className="empty-state">Execute or select a run.</div>}
          </Panel>
          {selectedRun && (
            <Panel eyebrow="Machine-readable spec" title="AnalysisSpec">
              <CodeBlock
                value={
                  selectedRun.execution?.analysis_spec ?? {
                    id: selectedRun.analysis_spec_id,
                    method_id: selectedRun.method_id,
                    snapshot_id: selectedRun.snapshot_id,
                    cohort_id: selectedRun.cohort_id,
                    outcome_metric_id: outcomeId,
                    parameters: { reference_week: 1, contrast_week: 10 },
                    status: "FROZEN",
                    reproducibility_key: selectedRun.reproducibility_key,
                  }
                }
              />
            </Panel>
          )}
        </aside>
      </div>
      <div className="analysis-bottom-grid">
        <Panel eyebrow="Method diagnostics" title="Model status and assumptions" action={<StatusBadge tone="cyan">COMPUTED</StatusBadge>}>
          <DiagnosticBlock run={selectedRun} />
          <div className="assumption-list">
            <div><CheckCircle2 size={14} /><span>Athlete-level dependence is modelled explicitly by the estimator ladder.</span></div>
            <div><CheckCircle2 size={14} /><span>The intervention × time contrast is specified before inspection.</span></div>
            <div><TriangleAlert size={14} /><span>Synthetic data demonstrate computation, not external validity.</span></div>
          </div>
        </Panel>
        <Panel eyebrow="Evidence outputs" title="Result objects" action={<Button size="sm" variant="ghost" onClick={() => onNavigate("lineage", selectedEvidence?.id)} disabled={!selectedEvidence}>Trace evidence <ArrowRight size={13} /></Button>}>
          {selectedEvidence ? <EvidencePassport evidence={selectedEvidence} onNavigate={onNavigate} /> : <div className="empty-state">No evidence artifact is attached to this run.</div>}
        </Panel>
      </div>
    </div>
  );
}

function createFlow(run: Run | undefined, evidence: Evidence | undefined): { nodes: Node[]; edges: Edge[] } {
  const runId = run?.id ?? "RUN-0001";
  const evidenceId = evidence?.id ?? "EVID-0001";
  const nodes: Node[] = [
    { id: "RQ-001", type: "scientific", position: { x: 20, y: 30 }, data: { kind: "question", label: "Research Question", sublabel: "RQ-001", state: "FROZEN" } },
    { id: "DS-SYNTH-001", type: "scientific", position: { x: 20, y: 140 }, data: { kind: "data", label: "Dataset Snapshot", sublabel: run?.snapshot_id ?? "immutable", state: "SYNTHETIC" } },
    { id: "COHORT-001", type: "scientific", position: { x: 20, y: 250 }, data: { kind: "cohort", label: "Cohort", sublabel: run?.cohort_id ?? "COHORT-001", state: "FROZEN" } },
    { id: "QUALITY-001", type: "scientific", position: { x: 250, y: 250 }, data: { kind: "method", label: "Quality Filter", sublabel: "QC + exclusions", state: "VALID" } },
    { id: runId, type: "scientific", position: { x: 250, y: 140 }, data: { kind: "analysis", label: "Analysis Run", sublabel: run?.method_id ?? "METH-LONG", state: run?.status ?? "READY" } },
    { id: "DIAG-001", type: "scientific", position: { x: 480, y: 140 }, data: { kind: "diagnostic", label: "Diagnostics", sublabel: text(dict(run?.diagnostics).estimator, "residuals + fit"), state: "VALID" } },
    { id: evidenceId, type: "scientific", position: { x: 710, y: 140 }, data: { kind: "evidence", label: "Evidence Artifact", sublabel: evidence?.kind ?? "pending", state: evidence?.quality ?? "READY" } },
    { id: "FIG-0001", type: "scientific", position: { x: 710, y: 30 }, data: { kind: "figure", label: "Figure Artifact", sublabel: "computed output", state: "VALID" } },
    { id: "REPORT-001", type: "scientific", position: { x: 710, y: 250 }, data: { kind: "report", label: "Report", sublabel: "interim draft", state: "DRAFT" } },
  ];
  const edges: Edge[] = ([
    ["RQ-001", "DS-SYNTH-001", "defines"],
    ["DS-SYNTH-001", "COHORT-001", "filters"],
    ["COHORT-001", "QUALITY-001", "applies"],
    ["COHORT-001", runId, "input_to"],
    ["QUALITY-001", runId, "gates"],
    [runId, "DIAG-001", "diagnoses"],
    ["DIAG-001", evidenceId, "qualifies"],
    [evidenceId, "FIG-0001", "visualised_as"],
    [evidenceId, "REPORT-001", "cited_by"],
  ] as [string, string, string][]).map(([source, target, label]) => ({
    id: `${source}-${target}`,
    source,
    target,
    label,
    animated: false,
    style: { stroke: "#3e6470", strokeWidth: 1.2 },
    labelStyle: { fill: "#78909c", fontSize: 9 },
    labelBgStyle: { fill: "#101820", fillOpacity: 0.9 },
  }));
  return { nodes, edges };
}

function RunInspector({ run, evidence, onNavigate }: { run: Run; evidence?: Evidence; onNavigate: (view: string, id?: string) => void }) {
  const result = dict(run.result);
  const primary = dict(result.primary ?? result);
  const method = run.method_id;
  return (
    <div className="run-inspector">
      <div className="inspector-hero">
        <div className="eyebrow">Immutable execution</div>
        <strong className="mono">{run.id}</strong>
        <span>{text(run.analysis_spec_id)} · {text(run.method_id)}</span>
      </div>
      {method === "METH-LONG" && <GroupResult primary={primary} />}
      {method === "METH-REL" && <ReliabilityResult result={result} />}
      {method === "METH-IND" && <ChangeResult result={result} />}
      <KeyValue label="Model" value={text(primary.method, text(result.method, "—"))} />
      <KeyValue label="Estimator" value={text(primary.estimator, text(result.estimator, "—"))} mono />
      <KeyValue label="Status" value={<StatusBadge tone="good">{text(primary.model_status, text(result.status, "COMPLETED"))}</StatusBadge>} />
      <KeyValue label="Duration" value={`${run.duration_ms.toFixed(1)} ms`} mono />
      <KeyValue label="Snapshot" value={run.snapshot_id} mono />
      <KeyValue label="Reproducibility" value={run.reproducibility_key} mono />
      <div className="inspector-actions">
        <Button size="sm" onClick={() => onNavigate("runs", run.id)}>Open run <ArrowRight size={13} /></Button>
        <Button size="sm" variant="ghost" onClick={() => onNavigate("lineage", evidence?.id ?? run.id)}>Lineage <GitBranch size={13} /></Button>
      </div>
    </div>
  );
}

function GroupResult({ primary }: { primary: Dict }) {
  const contrasts = dict(primary.contrasts);
  const primaryContrast = dict(contrasts[text(primary.primary_contrast_id)]);
  const weekTen = dict(contrasts["intervention_vs_comparison_week_10"]);
  const balance = dict(contrasts["baseline_balance_week_1"]);
  return (
    <>
      <div className="inspector-metrics">
        <div><span>{text(primaryContrast.contrast, "Intervention × Time")}</span><strong>{num(primaryContrast.estimate).toFixed(3)}</strong><small>{text(primaryContrast.unit, "N·s·kg⁻¹")}</small></div>
        <div><span>95% CI</span><strong>{num(primaryContrast.ci_low).toFixed(3)} → {num(primaryContrast.ci_high).toFixed(3)}</strong><small>difference in change</small></div>
        <div><span>Sample</span><strong>{num(primary.n_observations).toLocaleString()}</strong><small>{num(primary.n_subjects)} athletes</small></div>
      </div>
      <div className="inspector-contrast-list">
        <div><span>Week 10 model-implied difference</span><strong className="mono">{num(weekTen.estimate).toFixed(3)} ({num(weekTen.ci_low).toFixed(3)} → {num(weekTen.ci_high).toFixed(3)})</strong></div>
        <div><span>Baseline balance (week 1)</span><strong className="mono">{num(balance.estimate).toFixed(3)} ({num(balance.ci_low).toFixed(3)} → {num(balance.ci_high).toFixed(3)})</strong></div>
        <div><span>Effect size</span><strong className="mono">{num(primary.effect_size).toFixed(3)} SD</strong></div>
        <div><span>Week centring</span><strong className="mono">week {num(primary.week_centering, 1)}</strong></div>
      </div>
    </>
  );
}

function ReliabilityResult({ result }: { result: Dict }) {
  return (
    <div className="inspector-metrics">
      <div><span>ICC(3,1)</span><strong>{num(result.icc_3_1).toFixed(3)}</strong><small>95% CI {num(result.icc_3_1_ci_low).toFixed(3)} → {num(result.icc_3_1_ci_high).toFixed(3)}</small></div>
      <div><span>Typical error</span><strong>{num(result.typical_error).toFixed(3)}</strong><small>{text(result.unit)}</small></div>
      <div><span>Sample</span><strong>{num(result.n_subjects)}</strong><small>{num(result.trials_per_subject)} trials each</small></div>
    </div>
  );
}

function ChangeResult({ result }: { result: Dict }) {
  return (
    <div className="inspector-metrics">
      <div><span>Median change</span><strong>{num(result.median_change).toFixed(3)}</strong><small>{text(result.unit)}</small></div>
      <div><span>Standardized</span><strong>{num(result.standardized_change).toFixed(2)}</strong><small>SD</small></div>
      <div><span>Athletes</span><strong>{num(result.n_subjects)}</strong><small>typical error {num(result.typical_error).toFixed(3)}</small></div>
    </div>
  );
}

function DiagnosticBlock({ run }: { run?: Run }) {
  if (!run) return <div className="empty-state">No run selected.</div>;
  const result = dict(run.result);
  const primary = dict(result.primary ?? result);
  const residual = dict(primary.residual_summary);
  const diagnostics = dict(run.diagnostics);
  const isGroup = run.method_id === "METH-LONG";
  return (
    <div className="diagnostic-grid">
      {isGroup ? (
        <>
          <MetricTile label="RMSE" value={num(residual.rmse).toFixed(3)} unit="outcome units" state="VALID" />
          <MetricTile label="Mean residual" value={num(residual.mean_residual).toFixed(3)} unit="outcome units" state="VALID" />
          <MetricTile label="Max abs residual" value={num(residual.max_abs_residual).toFixed(3)} unit="outcome units" state="WARNING" />
        </>
      ) : (
        <>
          <MetricTile label="Typical error" value={num(primary.typical_error, num(result.typical_error)).toFixed(3)} unit={text(primary.unit, text(result.unit, ""))} state="VALID" />
          <MetricTile label="Athletes" value={String(num(primary.n_subjects, num(result.n_subjects)))} unit="subjects" state="VALID" />
          <MetricTile label="Method" value={text(run.method_id)} unit="frozen spec" state="FROZEN" />
        </>
      )}
      <div className="diagnostic-notes">
        <div><span>estimator</span><strong>{text(primary.estimator, text(result.estimator, "—"))}</strong></div>
        <div><span>convergence</span><strong>{primary.converged === false ? "FALLBACK" : "COMPLETED"}</strong></div>
        <div><span>quality handling</span><strong>{num(primary.n_observations, num(result.n_subjects)) > 0 ? "EXPLICIT" : "EMPTY"}</strong></div>
        <div><span>diagnostic fields</span><strong>{Object.keys(diagnostics).length}</strong></div>
      </div>
    </div>
  );
}
