"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { BarChart3, FileText, GitBranch, Hexagon, Info, Microscope, NotebookPen, Plus, ScanSearch, Stethoscope } from "lucide-react";
import type { Evidence, FigureArtifact, Run, WorkbenchBlock } from "@/lib/types";
import { scienceApi } from "@/lib/api";
import { formatSig, formatSignedSig, intervalExcludes, metricOption, primaryResult, shortChecksum } from "@/lib/scientific";
import { updateState } from "@/lib/workbench";
import { Button, ErrorBox, Forest, KV, Loading, State } from "@/components/ui";
import { ChangeScatterChart, DistributionChart, GroupFigureChart } from "@/components/charts";
import { BlockFrame } from "../Block";
import { useWorkbench } from "../context";
import { useEvidenceList, useFigure, useInvalidateScience, useReport, useRuns } from "../data";
import { runMatchesConfig } from "./AnalysisBlocks";

/** Resolve the analysis → run → evidence chain an evidence block points at. */
function useEvidenceChain(evidenceBlock: WorkbenchBlock | undefined) {
  const wb = useWorkbench();
  const runs = useRuns();
  const evidence = useEvidenceList();
  const analysis = wb.blocks.find((item) => item.id === evidenceBlock?.state.analysis_block_id);
  const run = runs.data?.find((item) => item.id === analysis?.state.run_id);
  const fresh = analysis ? runMatchesConfig(run, analysis, wb.excludedSubjectIds) : false;
  const item = evidence.data?.find((entry) => entry.analysis_run_id === run?.id);
  return { analysis, run, fresh, evidence: item, loading: runs.isLoading || evidence.isLoading };
}

function useCite() {
  const wb = useWorkbench();
  const invalidate = useInvalidateScience();
  return useMutation({
    mutationFn: (artifactId: string) => scienceApi.cite(artifactId),
    onSuccess: (result) => {
      invalidate();
      wb.notify(result.already_cited ? `${result.artifact_id} is already cited in ${result.report_id}` : `${result.artifact_id} added to ${result.report_id} · ${result.section}`);
    },
  });
}

export function EvidenceCard({ evidence, run, cited, onCite, citing, diagnosticsBlockId }: { evidence: Evidence; run?: Run; cited: boolean; onCite?: () => void; citing?: boolean; diagnosticsBlockId?: string }) {
  const wb = useWorkbench();
  const metric = metricOption(evidence.metric_id);
  const interval = evidence.interval;
  const excludesZero = interval ? intervalExcludes(interval.low, interval.high, 0) : null;
  const methodId = run?.method_id ?? (evidence.kind === "EFFECT" ? "METH-LONG" : evidence.kind === "RELIABILITY" ? "METH-REL" : "METH-IND");
  return (
    <div className="evidence-card">
      <div className="evidence-main">
        <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
          <span className="evidence-id">{evidence.id}</span>
          <State>{evidence.evidence_class ?? "PLANNED"}</State>
          <State>{evidence.state ?? "CURRENT"}</State>
          <State>{evidence.quality}</State>
          {cited && <State tone="tone-valid">CITED</State>}
          {evidence.reproduces && evidence.reproduces.length > 0 && <State tone="tone-valid" title="Identical reproducibility key and result digest">{`REPRODUCES ${evidence.reproduces.join(", ")}`}</State>}
        </div>
        <div className="evidence-title">{evidence.title}</div>
        <div className="estimate-line" style={{ borderLeftColor: evidence.evidence_class === "EXPLORATORY" ? "var(--exploratory)" : "var(--signal)" }}>
          <span className="value">{evidence.kind === "EFFECT" ? formatSignedSig(evidence.estimate, 3) : formatSig(evidence.estimate, 3)}<span className="unit">{evidence.unit}</span></span>
          {interval && interval.low !== null && interval.high !== null && <span className="ci">{Math.round(interval.level * 100)}% CI [{formatSig(interval.low, 3)}, {formatSig(interval.high, 3)}]</span>}
          <span className="meta">{evidence.uncertainty_label ?? "uncertainty"} {formatSig(evidence.uncertainty, 3)}{evidence.effect_size !== null && evidence.kind === "EFFECT" ? ` · standardised ${formatSig(evidence.effect_size, 3)} SD` : ""}{evidence.kind === "RELIABILITY" && evidence.effect_size !== null ? ` · mean CV ${formatSig(evidence.effect_size, 3)} %` : ""}</span>
          {interval && interval.low !== null && interval.high !== null && evidence.estimate !== null && evidence.kind === "EFFECT" && (
            <div style={{ width: "100%" }}><Forest estimate={evidence.estimate} low={interval.low} high={interval.high} unit={evidence.unit} /></div>
          )}
          {excludesZero !== null && evidence.kind === "EFFECT" && <span className="meta">{excludesZero ? "interval excludes zero" : "interval includes zero"} · {interval?.kind}</span>}
        </div>
        <p className="muted" style={{ marginTop: 8, fontSize: 12 }}>{evidence.interpretation}</p>
        <div className="evidence-actions" style={{ marginTop: 10 }}>
          <Button size="sm" onClick={() => wb.inspect({ kind: "run", id: evidence.analysis_run_id })}><ScanSearch size={12} />Inspect run</Button>
          <Button size="sm" onClick={() => wb.inspect({ kind: "method", id: methodId })}><Microscope size={12} />Methodology</Button>
          <Button size="sm" onClick={() => diagnosticsBlockId && wb.selectBlock(diagnosticsBlockId, { scroll: true })} disabled={!diagnosticsBlockId}><Stethoscope size={12} />Diagnostics</Button>
          <Button size="sm" onClick={() => wb.openLineage(evidence.id)}><GitBranch size={12} />Inspect lineage</Button>
          {onCite && <Button size="sm" variant={cited ? "default" : "primary"} onClick={onCite} disabled={cited || citing}><Plus size={12} />{cited ? "In report" : "Add to report"}</Button>}
        </div>
      </div>
      <div className="evidence-side">
        <KV rows={[
          ["Metric", <button key="m" type="button" className="mono" style={{ color: "var(--signal)" }} onClick={() => wb.inspect({ kind: "metric", id: evidence.metric_id })}>{evidence.metric_id}</button>],
          ["Definition", metric.label],
          ["Population", evidence.population],
          ["n", String(evidence.sample_size)],
          ["Protocol", evidence.protocol_id, "mono"],
          ["Spec", evidence.analysis_spec_id, "mono"],
          ["Run", evidence.analysis_run_id, "mono"],
          ["Cohort", evidence.cohort_id, "mono"],
          ["Dataset", evidence.dataset_snapshot_id, "mono"],
          ["Checksum", shortChecksum(evidence.provenance.snapshot_checksum, 14), "mono"],
          ["Algorithm", `${String(evidence.provenance.estimator ?? evidence.provenance.algorithm ?? "—")}`, "mono"],
          ["Version", `v${evidence.version ?? 1} · immutable`],
        ]} />
      </div>
    </div>
  );
}

export function EvidenceBlock({ block, index }: { block: WorkbenchBlock; index: number }) {
  const wb = useWorkbench();
  const invalidate = useInvalidateScience();
  const report = useReport();
  const cite = useCite();
  const { run, fresh, evidence, loading } = useEvidenceChain(block);
  const diagnosticsBlock = wb.blocks.find((item) => item.type === "diagnostics" && item.state.analysis_block_id === block.state.analysis_block_id);
  const diagnosticsComplete = run ? (run.method_id === "METH-LONG" ? Array.isArray((run.diagnostics as Record<string, unknown>).residual_qq) : Object.keys(run.diagnostics ?? {}).length > 0) : false;
  const promote = useMutation({
    mutationFn: (runId: string) => scienceApi.promote(runId),
    onSuccess: (result) => {
      wb.setBlocks((blocks) => {
        const withEvidence = updateState(blocks, block.id, { evidence_id: result.evidence_artifact.id });
        return withEvidence.map((item) => (item.type === "figure" && item.state.evidence_block_id === block.id ? { ...item, state: { ...item.state, figure_id: result.figure_artifact?.id } } : item));
      });
      invalidate();
      wb.notify(result.already_promoted ? `${run?.id} was already promoted as ${result.evidence_artifact.id}` : `${result.evidence_artifact.id} promoted from ${run?.id} · ${result.evidence_artifact.evidence_class}`);
    },
  });
  const cited = Boolean(evidence && report.data?.evidence_ids.includes(evidence.id));
  const states = evidence ? [evidence.evidence_class ?? "PLANNED", evidence.state ?? "CURRENT"] : [run ? "NOT PROMOTED" : "INCOMPLETE"];
  return (
    <BlockFrame block={block} index={index} icon={<Hexagon size={12} />} title={evidence ? evidence.title : block.title} sub={evidence ? `${evidence.id} ← ${evidence.analysis_run_id}` : run ? `from ${run.id}` : undefined} states={states.map((label) => (label === "NOT PROMOTED" ? { label, tone: "tone-warning" } : label))}>
      {loading && <Loading label="Resolving evidence" />}
      {!loading && evidence && <EvidenceCard evidence={evidence} run={run} cited={cited} onCite={() => cite.mutate(evidence.id)} citing={cite.isPending} diagnosticsBlockId={diagnosticsBlock?.id} />}
      {!loading && !evidence && run && (
        <div className="promote">
          <Hexagon size={18} style={{ color: "var(--signal)" }} />
          <p>
            {run.id} is a completed, immutable run{run.reproduces?.length ? ` that reproduces ${run.reproduces.join(", ")}` : ""}. Promotion creates an immutable EvidenceArtifact bound to its spec, cohort, dataset and diagnostics
            {run.plan_alignment === "EXPLORATORY" ? "; it will be classed EXPLORATORY because the run deviates from the frozen plan." : "; it will be classed from the frozen plan."}
            {!fresh && " The analysis configuration has changed since this run — promotion applies to the run, not the current configuration."}
          </p>
          <Button variant="primary" onClick={() => promote.mutate(run.id)} disabled={promote.isPending || !diagnosticsComplete} title={diagnosticsComplete ? undefined : "Diagnostics are missing; a result without diagnostics cannot become evidence"}>
            <Hexagon size={12} />{promote.isPending ? "Promoting…" : `Promote ${run.id} to evidence`}
          </Button>
        </div>
      )}
      {!loading && !run && <div className="error">The attached analysis has no run. Execute it before evidence can exist.</div>}
      {promote.error && <ErrorBox error={promote.error} />}
      {cite.error && <ErrorBox error={cite.error} />}
    </BlockFrame>
  );
}

export function FigureView({ figure }: { figure: FigureArtifact }) {
  const data = figure.data;
  if (!data) return <Loading label="Rendering figure from stored artifact" />;
  if (data.kind === "LINE" && data.series) return <GroupFigureChart series={data.series} unit={data.unit} />;
  if (data.kind === "DISTRIBUTION" && data.values?.length) return <DistributionChart values={data.values} unit={data.unit} label="within-subject CV" />;
  if (data.points?.length) return <ChangeScatterChart points={data.points} typicalError={data.typical_error} unit={data.unit} />;
  return <div className="error">Figure {figure.id} has no renderable data.</div>;
}

export function FigureBlock({ block, index }: { block: WorkbenchBlock; index: number }) {
  const wb = useWorkbench();
  const report = useReport();
  const cite = useCite();
  const evidenceBlock = wb.blocks.find((item) => item.id === block.state.evidence_block_id);
  const { evidence } = useEvidenceChain(evidenceBlock);
  const detail = useQuery({ queryKey: ["evidence-detail", evidence?.id], queryFn: () => scienceApi.evidenceDetail(evidence?.id as string), enabled: Boolean(evidence?.id) });
  const figureId = detail.data?.figures[0]?.id;
  const figure = useFigure(figureId);
  const cited = Boolean(figureId && report.data?.figure_ids.includes(figureId));
  return (
    <BlockFrame block={block} index={index} icon={<BarChart3 size={12} />} title={figure.data?.title ?? block.title} sub={figure.data ? `${figure.data.id} · bound to ${figure.data.evidence_ids.join(", ")}` : undefined} states={figure.data ? ["COMPUTED", ...(cited ? ["CITED"] : [])] : ["INCOMPLETE"]}
      actions={figure.data ? <><Button size="sm" variant="ghost" onClick={() => wb.openLineage(figure.data.id)}><GitBranch size={12} />Lineage</Button><Button size="sm" variant={cited ? "ghost" : "default"} disabled={cited || cite.isPending} onClick={() => cite.mutate(figure.data.id)}><Plus size={12} />{cited ? "In report" : "Add figure to report"}</Button></> : undefined}
    >
      {!evidence && <div className="empty">No evidence yet: a figure artifact is created when the run is promoted.</div>}
      {figure.isLoading && <Loading label="Loading figure artifact" />}
      {figure.data && (
        <div className="chart-frame">
          <div className="chart-cap">
            <strong>{figure.data.title}</strong>
            <span>· {String(figure.data.spec.summary ?? figure.data.kind.toLowerCase())} · {figure.data.dataset_snapshot_id} · cohort {String(figure.data.spec.cohort_id ?? "")}</span>
          </div>
          <FigureView figure={figure.data} />
        </div>
      )}
      {cite.error && <ErrorBox error={cite.error} />}
    </BlockFrame>
  );
}

export function InterpretationBlock({ block, index }: { block: WorkbenchBlock; index: number }) {
  const wb = useWorkbench();
  const runs = useRuns();
  const evidenceBlock = wb.blocks.find((item) => item.id === block.state.evidence_block_id);
  const { evidence } = useEvidenceChain(evidenceBlock);
  const reliability = runs.data?.find((run) => run.id === "RUN-0002");
  const reliabilityResult = primaryResult<Record<string, number>>(reliability?.result);
  const swc = reliabilityResult?.smallest_worthwhile_change;
  const comparable = evidence?.kind === "EFFECT" && evidence.metric_id === "MET-CMJ-IMPULSE" && typeof swc === "number";
  const note = String(block.state.note ?? "");
  return (
    <BlockFrame block={block} index={index} icon={<NotebookPen size={12} />} title={block.title} sub={evidence ? `reading ${evidence.id}` : undefined} states={[{ label: "SCIENTIST NOTE", tone: "tone-neutral" }]} removable>
      {evidence ? (
        <div>
          <div className="interp-label"><State plain>COMPUTED</State>statement generated from {evidence.id} values</div>
          <div className="interp-computed">{evidence.interpretation}</div>
        </div>
      ) : (
        <div className="empty">No evidence is attached yet; the computed statement appears after promotion.</div>
      )}
      {comparable && evidence?.estimate !== null && evidence && (
        <div>
          <div className="interp-label"><State plain>COMPUTED</State>practical relevance against baseline reliability (RUN-0002)</div>
          <div className="interp-computed">
            Difference-in-change {formatSignedSig(evidence.estimate, 3)} {evidence.unit} versus smallest worthwhile change {formatSig(swc, 3)} {evidence.unit} (1.96·√2·typical error):{" "}
            <strong style={{ color: "var(--text-strong)" }}>{Math.abs(evidence.estimate ?? 0) > (swc ?? 0) ? "the estimate exceeds" : "the estimate does not exceed"}</strong> the individual-level measurement noise threshold
            {evidence.interval?.low !== null && evidence.interval?.low !== undefined ? `; the lower 95% limit (${formatSig(evidence.interval.low, 3)}) ${evidence.interval.low > (swc ?? 0) ? "also exceeds it" : "does not"}` : ""}.
          </div>
        </div>
      )}
      <div>
        <div className="interp-label"><State plain tone="tone-neutral">SCIENTIST</State>interpretation — authored, not computed; saved with the investigation</div>
        <textarea className="input" rows={3} value={note} onChange={(event) => wb.setBlocks((blocks) => updateState(blocks, block.id, { note: event.target.value }))} aria-label="Scientist interpretation" />
      </div>
      <div className="note"><Info size={12} />Synthetic demonstration: no statement here generalises to real athletes.</div>
    </BlockFrame>
  );
}

export function ReportSectionBlock({ block, index }: { block: WorkbenchBlock; index: number }) {
  const wb = useWorkbench();
  const report = useReport();
  const cite = useCite();
  const evidenceIds = new Set<string>();
  const evidence = useEvidenceList();
  const runs = useRuns();
  for (const item of wb.blocks.filter((entry) => entry.type === "evidence")) {
    const analysis = wb.blocks.find((entry) => entry.id === item.state.analysis_block_id);
    const found = evidence.data?.find((entry) => entry.analysis_run_id === analysis?.state.run_id);
    if (found) evidenceIds.add(found.id);
  }
  const section = String(block.state.section ?? "Intervention result");
  const citations = report.data?.citations.filter((citation) => citation.section === section) ?? [];
  const uncited = [...evidenceIds].filter((id) => !report.data?.evidence_ids.includes(id));
  return (
    <BlockFrame block={block} index={index} icon={<FileText size={12} />} title={`Report · ${section}`} sub={report.data ? `${report.data.id} · ${report.data.status}` : undefined} states={[report.data?.status ?? "DRAFT"]}
      actions={<Button size="sm" onClick={() => wb.setMode("report")}><FileText size={12} />Open report</Button>}
    >
      {report.isLoading && <Loading label="Loading report" />}
      {report.data && (
        <>
          <table className="table">
            <thead><tr><th>Cited artifact</th><th>Kind</th><th>Class</th><th>Source run</th><th>Added</th></tr></thead>
            <tbody>
              {citations.map((citation) => {
                const item = report.data?.evidence.find((entry) => entry.id === citation.artifact_id);
                const figure = report.data?.figures.find((entry) => entry.id === citation.artifact_id);
                return (
                  <tr key={citation.artifact_id} role="button" tabIndex={0} onClick={() => (item ? wb.inspect({ kind: "evidence", id: item.id }) : figure && wb.inspect({ kind: "figure", id: figure.id }))}>
                    <td className="mono">{citation.artifact_id} <span className="faint">{item?.title ?? figure?.title}</span></td>
                    <td className="mono faint">{item ? item.kind : "FIGURE"}</td>
                    <td>{item?.evidence_class ? <State plain>{item.evidence_class}</State> : <span className="faint">—</span>}</td>
                    <td className="mono">{item?.analysis_run_id ?? figure?.analysis_run_id}</td>
                    <td className="mono faint">{citation.added_at.slice(0, 16).replace("T", " ")}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {uncited.length > 0 ? (
            <div className="block-toolbar">
              <span className="note warn"><Info size={12} />Evidence in this investigation not yet in the report: {uncited.join(", ")}</span>
              {uncited.map((id) => <Button key={id} size="sm" variant="primary" onClick={() => cite.mutate(id)} disabled={cite.isPending}><Plus size={12} />Add {id}</Button>)}
            </div>
          ) : (
            <div className="faint small">All evidence in this investigation is cited. {runs.data ? `${runs.data.length} runs in the ledger.` : ""}</div>
          )}
        </>
      )}
      {cite.error && <ErrorBox error={cite.error} />}
    </BlockFrame>
  );
}
