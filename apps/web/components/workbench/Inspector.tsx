"use client";

import { useQuery } from "@tanstack/react-query";
import { Activity, ArrowLeft, GitBranch } from "lucide-react";
import type { ReactNode } from "react";
import type { Run, WorkbenchBlock } from "@/lib/types";
import { scienceApi } from "@/lib/api";
import { METHOD_LABEL, formatSig, formatSignedSig, metricOption, primaryResult, shortChecksum } from "@/lib/scientific";
import { BLOCK_META } from "@/lib/workbench";
import { ArmLabel, Button, ErrorBox, KV, Loading, State } from "@/components/ui";
import { MethodDetail, MetricDetail, ModelDetail, ProtocolDetail } from "@/components/research/LibraryDetail";
import { useWorkbench, type InspectTarget } from "./context";
import { useEvidenceList, useLibrary, useReport, useRuns } from "./data";
import { analysisConfig } from "./blocks/AnalysisBlocks";

function Sec({ title, children, aside }: { title: string; children: ReactNode; aside?: ReactNode }) {
  return <section className="insp-sec"><h4>{title}{aside}</h4>{children}</section>;
}

function Head({ kind, title, states = [] }: { kind: string; title: ReactNode; states?: string[] }) {
  const wb = useWorkbench();
  return (
    <div className="insp-head">
      {wb.canInspectBack && <button type="button" className="insp-back" onClick={wb.inspectBack}><ArrowLeft size={11} />back</button>}
      <div className="insp-kind"><span>{kind}</span><span style={{ display: "flex", gap: 4 }}>{states.map((state) => <State key={state}>{state}</State>)}</span></div>
      <div className="insp-title">{title}</div>
    </div>
  );
}

export function Inspector() {
  const wb = useWorkbench();
  const target: InspectTarget = wb.inspector ?? { kind: "design", section: "plan" };
  return (
    <aside className="inspector" aria-label="Inspector">
      <InspectorContent target={target} />
    </aside>
  );
}

function InspectorContent({ target }: { target: InspectTarget }) {
  const wb = useWorkbench();
  switch (target.kind) {
    case "block": {
      const block = wb.blocks.find((item) => item.id === target.id);
      return block ? <BlockInspector block={block} /> : <Head kind="Block" title="Block removed" />;
    }
    case "athlete":
      return <AthleteInspector id={target.id} />;
    case "trial":
      return <TrialInspector id={target.id} />;
    case "run":
      return <RunInspector id={target.id} />;
    case "evidence":
      return <EvidenceInspector id={target.id} />;
    case "figure":
      return <FigureInspector id={target.id} />;
    case "metric":
    case "method":
    case "protocol":
      return <LibraryInspector kind={target.kind} id={target.id} />;
    case "design":
      return <DesignInspector section={target.section} />;
    case "report":
      return <ReportInspector />;
  }
}

function DesignInspector({ section }: { section: "hypotheses" | "arms" | "timeline" | "plan" }) {
  const { study } = useWorkbench();
  const plan = study.plan;
  return (
    <>
      <Head kind={`Study design · ${section}`} title={section === "plan" ? "Frozen analysis plan" : section === "arms" ? "Study arms" : section === "timeline" ? "Timeline" : "Hypotheses"} states={section === "plan" ? [plan.status] : []} />
      <div className="insp-scroll">
        {section === "plan" && (
          <>
            <Sec title="Plan"><KV rows={[["Plan ID", plan.id, "mono"], ["Status", plan.status], ["Frozen before inspection", plan.frozen_before_inspection ? "yes" : "no"], ["Primary estimand", plan.primary_estimand]]} /></Sec>
            <Sec title="Outcomes"><KV rows={[["Primary", plan.primary_outcomes.join(" · ")], ["Secondary", plan.secondary_outcomes.join(" · ")]]} /></Sec>
            <Sec title="Planned analyses"><ul>{plan.planned_models.map((item) => <li key={item}>{item}</li>)}<li>{plan.planned_reliability}</li></ul></Sec>
            <Sec title="Frozen specifications">
              {study.analysis_specs.map((spec) => (
                <div key={spec.id} style={{ marginBottom: 8 }}>
                  <div style={{ display: "flex", justifyContent: "space-between" }}><span className="mono">{spec.id}</span><State plain>{spec.status}</State></div>
                  <div className="small muted">{spec.name} · {spec.outcome_metric_id}</div>
                  <div className="mono small faint">{JSON.stringify(spec.parameters)}</div>
                </div>
              ))}
            </Sec>
            <Sec title="Rules"><p>{plan.immutability_rule}</p><p style={{ marginTop: 6 }}>{plan.post_plan_rule}</p></Sec>
            <Sec title="Exclusion criteria"><ul>{plan.exclusion_criteria.map((item) => <li key={item}>{item}</li>)}</ul></Sec>
          </>
        )}
        {section === "hypotheses" && study.hypotheses.map((hypothesis) => (
          <Sec key={hypothesis.id} title={hypothesis.id} aside={<State plain>{hypothesis.status}</State>}>
            <p style={{ color: "var(--text)" }}>{hypothesis.statement}</p>
            <p style={{ marginTop: 4 }}>Direction: {hypothesis.direction}. {hypothesis.rationale}</p>
          </Sec>
        ))}
        {section === "arms" && Object.values(study.groups).map((group) => (
          <Sec key={group.arm} title={group.label} aside={<span className="mono">{study.arm_counts[group.arm]} athletes</span>}>
            <p><ArmLabel arm={group.arm} /> {group.description}</p>
            <KV rows={[["Block weeks", `${group.block_weeks[0]}–${group.block_weeks[1]}`, "mono"]]} />
          </Sec>
        ))}
        {section === "timeline" && (
          <Sec title="Design">
            <KV rows={[["Design", study.study.design], ["Intervention", study.study.intervention], ["Weeks", `${study.study.start_week}–${study.study.end_week}`, "mono"], ["Baseline", "weeks 1–2"], ["Strength block", "weeks 3–10 (intervention arm)"], ["Primary contrast", "week 1 → week 10"], ["Follow-up", "weeks 11–16"]]} />
          </Sec>
        )}
      </div>
    </>
  );
}

function BlockInspector({ block }: { block: WorkbenchBlock }) {
  const wb = useWorkbench();
  const meta = BLOCK_META[block.type];
  const head = <Head kind={`${meta.label} block · ${block.id}`} title={block.title} />;
  const stateSection = (
    <Sec title="Serialised block state"><pre className="code">{JSON.stringify({ id: block.id, type: block.type, state: block.state }, null, 2)}</pre></Sec>
  );
  if (block.type === "question") return <DesignInspector section="plan" />;
  if (block.type === "dataset") {
    const snapshot = wb.study.snapshot;
    return (
      <>
        {head}
        <div className="insp-scroll">
          <Sec title="Snapshot"><KV rows={[["Snapshot ID", snapshot.id, "mono"], ["Source", String(snapshot.provenance.source ?? "")], ["Generator", snapshot.generator_version, "mono"], ["Seed", String(snapshot.seed), "mono"], ["Schema", snapshot.schema_version, "mono"], ["Generated", snapshot.generated_at, "mono"]]} /></Sec>
          <Sec title="Row counts"><KV rows={Object.entries(snapshot.row_counts).map(([name, count]) => [name, count.toLocaleString(), "mono"] as [string, string, "mono"])} /></Sec>
          <Sec title="Checksums (SHA-256)"><KV rows={Object.entries(snapshot.checksums).map(([name, sum]) => [name.replace(".parquet", ""), shortChecksum(sum, 20), "mono"] as [string, string, "mono"])} /></Sec>
          <Sec title="Quality"><KV rows={[["Valid trials", String(wb.study.data_health.valid_measurements)], ["Excluded", String(wb.study.data_health.excluded_measurements)], ["Missing slots", String(wb.study.data_health.missing_observations)], ["Provenance complete", `${wb.study.data_health.provenance_completeness.toFixed(1)} %`]]} /></Sec>
          <Sec title="Provenance"><p>{String(snapshot.provenance.simulated_entities ?? "")}</p><div className="insp-actions" style={{ marginTop: 8 }}><Button size="sm" onClick={() => wb.openLineage(snapshot.id)}><GitBranch size={12} />Inspect lineage</Button></div></Sec>
        </div>
      </>
    );
  }
  if (block.type === "cohort") return <><>{head}</><CohortInspector block={block} /></>;
  if (block.type === "explore") {
    const metric = metricOption(String(block.state.metric_id));
    return (
      <>
        {head}
        <div className="insp-scroll">
          <Sec title="Configuration"><KV rows={[["Metric", `${metric.label}`], ["MetricDefinition", metric.id, "mono"], ["Unit", metric.unit, "mono"], ["Population", String(block.state.population)], ["Grouping", "intervention arm"], ["Reference", String(block.state.reference) === "RAW" ? "observed values" : `individual baseline (weeks 1–2), ${String(block.state.reference) === "PERCENT" ? "percent" : "absolute"} change`], ["View", "longitudinal · arm mean ± 95% CI, athlete traces"], ["Context overlays", Array.isArray(block.state.context) && block.state.context.length ? "training impulse (AU) · match minutes" : "none"], ["Cohort", wb.excludedSubjectIds.length ? `draft (−${wb.excludedSubjectIds.length})` : "COHORT-001"]]} /></Sec>
          <Sec title="Computation"><p>DuckDB aggregates valid trials to athlete-week means from cmj_trials.parquet; arm summaries use t-based 95% intervals across athletes. Descriptive, not inferential.</p></Sec>
          <Sec title="Metric definition" aside={<Button size="sm" variant="ghost" onClick={() => wb.inspect({ kind: "metric", id: metric.id })}>Open</Button>}><p>Select to view the Library MetricDefinition, method and limitations.</p></Sec>
          {stateSection}
        </div>
      </>
    );
  }
  if (block.type === "analysis") return <AnalysisInspector block={block} />;
  if (block.type === "diagnostics" || block.type === "evidence" || block.type === "figure" || block.type === "interpretation") {
    const analysis = wb.blocks.find((item) => item.id === block.state.analysis_block_id) ?? wb.blocks.find((item) => item.id === wb.blocks.find((entry) => entry.id === block.state.evidence_block_id)?.state.analysis_block_id);
    const runId = analysis?.state.run_id as string | undefined;
    return <ChainInspector block={block} runId={runId} />;
  }
  if (block.type === "model") return <ModelInspector />;
  if (block.type === "force_trial") return <TrialInspector id={String(block.state.trial_id)} />;
  return (
    <>
      {head}
      <div className="insp-scroll">
        <Sec title="About"><p>{meta.description}</p></Sec>
        {stateSection}
      </div>
    </>
  );
}

function CohortInspector({ block }: { block: WorkbenchBlock }) {
  const excluded = Array.isArray(block.state.excluded_subject_ids) ? (block.state.excluded_subject_ids as string[]) : [];
  const cohort = useQuery({ queryKey: ["cohort", excluded.join(",")], queryFn: () => scienceApi.cohort(excluded) });
  if (!cohort.data) return <div className="insp-scroll"><Loading label="Resolving cohort" /></div>;
  const data = cohort.data;
  return (
    <div className="insp-scroll">
      <Sec title="Definition" aside={<State>{data.cohort.status}</State>}><KV rows={[["Cohort ID", data.cohort.id, "mono"], ["Derived from", data.cohort.derived_from ?? "—", "mono"], ["n", String(data.n)], ["Intervention", String(data.arm_counts.INTERVENTION)], ["Comparison", String(data.arm_counts.COMPARISON)], ["Snapshot", data.snapshot_id, "mono"]]} /></Sec>
      <Sec title="Inclusion criteria"><ul>{data.inclusion_criteria.map((item) => <li key={item}>{item}</li>)}</ul></Sec>
      <Sec title="Exclusion criteria"><ul>{data.exclusion_criteria.map((item) => <li key={item}>{item}</li>)}</ul></Sec>
      <Sec title="Filters"><div className="mono small">{data.filters.excluded_subject_ids.length ? `excluded: ${data.filters.excluded_subject_ids.join(", ")}` : "none"}</div></Sec>
      <Sec title="Missingness"><KV rows={[["Valid trials", `${data.trial_quality.valid} / ${data.trial_quality.expected}`], ["Missing slots", String(data.trial_quality.missing)], ["By arm", Object.entries(data.trial_quality.missing_by_arm).map(([arm, n]) => `${arm.toLowerCase()} ${n}`).join(" · ")], ["Excluded trials", String(data.trial_quality.excluded)]]} />
        <ul style={{ marginTop: 6 }}>{data.trial_quality.missing_slots.map((slot) => <li key={`${slot.subject_id}-${slot.week}-${slot.trial_number}`} className="mono small">{slot.display_id} w{slot.week} T{slot.trial_number} · {slot.reason}</li>)}</ul>
      </Sec>
    </div>
  );
}

function AnalysisInspector({ block }: { block: WorkbenchBlock }) {
  const wb = useWorkbench();
  const runs = useRuns();
  const { methodId, outcomeId, parameters } = analysisConfig(block);
  const run = runs.data?.find((item) => item.id === block.state.run_id);
  const spec = run?.execution?.analysis_spec;
  const result = primaryResult<Record<string, unknown>>(run?.result);
  const isLong = methodId === "METH-LONG";
  return (
    <>
      <Head kind={`Analysis block · ${block.id}`} title={block.title} states={run ? [run.plan_alignment ?? "PLANNED"] : ["NOT RUN"]} />
      <div className="insp-scroll">
        <Sec title="AnalysisSpec"><KV rows={[["Spec ID", spec?.id ?? "created at execution", "mono"], ["Status", spec?.status ?? "—"], ["Method", `${methodId} · ${METHOD_LABEL[methodId]}`], ["Method version", spec?.method_version ?? "1.1.0", "mono"], ["Outcome", `${outcomeId} (${metricOption(outcomeId).unit})`, "mono"], ["Formula", spec?.model_formula ?? String(result?.formula ?? "")]]} /></Sec>
        {isLong && <Sec title="Model structure"><KV rows={[["Predictors", "week (centred on reference), group"], ["Interaction", "week × group"], ["Random effects", "athlete intercept + week slope"], ["Repeated structure", "athlete-weeks, first valid trial"], ["Primary estimand", `difference in change, week ${String(parameters.reference_week)} → ${String(parameters.contrast_week)}`]]} /></Sec>}
        <Sec title="Parameters"><pre className="code">{JSON.stringify(parameters, null, 2)}</pre></Sec>
        <Sec title="Inputs"><KV rows={[["Dataset", wb.study.snapshot.id, "mono"], ["Cohort", run?.cohort_id ?? (wb.excludedSubjectIds.length ? "draft" : "COHORT-001"), "mono"], ["Excluded athletes", wb.excludedSubjectIds.join(", ") || "none", "mono"]]} /></Sec>
        {isLong && Array.isArray((run?.diagnostics as Record<string, unknown> | undefined)?.assumptions) && <Sec title="Assumptions"><ul>{((run?.diagnostics as Record<string, unknown>).assumptions as string[]).map((item) => <li key={item}>{item}</li>)}</ul></Sec>}
        <Sec title="Execution state">{run ? <RunSummary run={run} /> : <p>Not executed. Running appends a new immutable AnalysisRun.</p>}</Sec>
      </div>
    </>
  );
}

function RunSummary({ run }: { run: Run }) {
  const wb = useWorkbench();
  return (
    <>
      <KV rows={[["Run", run.id, "mono"], ["Status", run.status], ["Plan alignment", run.plan_alignment ?? "PLANNED"], ["Created", run.created_at, "mono"], ["Duration", `${run.duration_ms.toFixed(1)} ms`, "mono"], ["Seed", String(run.seed ?? ""), "mono"], ["Result digest", run.result_digest ?? "—", "mono"], ["Reproduces", run.reproduces?.join(", ") || "—", "mono"], ["Evidence", run.evidence_ids?.join(", ") || "not promoted", "mono"]]} />
      <div className="insp-actions" style={{ marginTop: 8 }}>
        <Button size="sm" onClick={() => wb.inspect({ kind: "run", id: run.id })}>Full run record</Button>
        <Button size="sm" onClick={() => wb.openLineage(run.id)}><GitBranch size={12} />Lineage</Button>
      </div>
    </>
  );
}

function ChainInspector({ block, runId }: { block: WorkbenchBlock; runId?: string }) {
  const evidence = useEvidenceList();
  const item = evidence.data?.find((entry) => entry.analysis_run_id === runId);
  if (block.type === "evidence" && item) return <EvidenceInspector id={item.id} />;
  if (block.type === "figure" && item) return <EvidenceInspector id={item.id} />;
  if (runId) return <RunInspector id={runId} />;
  return <Head kind={BLOCK_META[block.type].label} title="No run attached" />;
}

function RunInspector({ id }: { id: string }) {
  const wb = useWorkbench();
  const run = useQuery({ queryKey: ["run", id], queryFn: () => scienceApi.run(id) });
  if (run.isLoading) return <div className="insp-scroll"><Loading label={`Loading ${id}`} /></div>;
  if (run.error || !run.data) return <ErrorBox error={run.error ?? id} />;
  const data = run.data;
  return (
    <>
      <Head kind="AnalysisRun · immutable" title={data.id} states={[data.status, data.plan_alignment ?? "PLANNED"]} />
      <div className="insp-scroll">
        <Sec title="Record"><RunSummary run={data} /></Sec>
        <Sec title="Specification"><KV rows={[["Spec", data.analysis_spec_id, "mono"], ["Method", data.method_id, "mono"], ["Snapshot", data.snapshot_id, "mono"], ["Cohort", data.cohort_id, "mono"]]} /></Sec>
        <Sec title="Reproducibility key"><div className="mono small" style={{ overflowWrap: "anywhere" }}>{data.reproducibility_key}</div></Sec>
        <Sec title="Software"><KV rows={Object.entries(data.software_versions).map(([key, value]) => [key, value, "mono"] as [string, string, "mono"])} /></Sec>
        <Sec title="Execution envelope"><pre className="code">{JSON.stringify(data.execution ?? { analysis_spec_id: data.analysis_spec_id }, null, 2)}</pre></Sec>
        <Sec title="Evidence">{data.evidence.length ? data.evidence.map((item) => <Button key={item.id} size="sm" onClick={() => wb.inspect({ kind: "evidence", id: item.id })}>{item.id}</Button>) : <p>Not promoted.</p>}</Sec>
      </div>
    </>
  );
}

function EvidenceInspector({ id }: { id: string }) {
  const wb = useWorkbench();
  const detail = useQuery({ queryKey: ["evidence-detail", id], queryFn: () => scienceApi.evidenceDetail(id) });
  const report = useReport();
  if (detail.isLoading) return <div className="insp-scroll"><Loading label={`Loading ${id}`} /></div>;
  if (detail.error || !detail.data) return <ErrorBox error={detail.error ?? id} />;
  const item = detail.data;
  const cited = report.data?.evidence_ids.includes(item.id);
  return (
    <>
      <Head kind="EvidenceArtifact · immutable" title={<><span className="mono" style={{ color: "var(--signal)" }}>{item.id}</span> {item.title}</>} states={[item.evidence_class ?? "PLANNED", item.state ?? "CURRENT"]} />
      <div className="insp-scroll">
        <Sec title="Result"><KV rows={[["Estimate", `${item.kind === "EFFECT" ? formatSignedSig(item.estimate, 4) : formatSig(item.estimate, 4)} ${item.unit}`, "mono"], ["Interval", item.interval ? `[${formatSig(item.interval.low, 4)}, ${formatSig(item.interval.high, 4)}] · ${item.interval.kind}` : "not computed for this method", "mono"], [item.uncertainty_label ?? "Uncertainty", formatSig(item.uncertainty, 4), "mono"], ["Effect size", item.effect_size === null ? "—" : formatSig(item.effect_size, 3), "mono"], ["n", String(item.sample_size)]]} /></Sec>
        <Sec title="Context"><KV rows={[["Metric", item.metric_id, "mono"], ["Population", item.population], ["Protocol", item.protocol_id, "mono"], ["Method", String(item.provenance.algorithm ?? "")], ["Dataset", item.dataset_snapshot_id, "mono"], ["Spec", item.analysis_spec_id, "mono"], ["Run", item.analysis_run_id, "mono"], ["Cohort", item.cohort_id, "mono"]]} /></Sec>
        <Sec title="Quality and version"><KV rows={[["Quality", item.quality], ["Class", item.evidence_class], ["State", item.state], ["Version", `v${item.version ?? 1}`], ["Reproduces", item.reproduces?.join(", ") || "—", "mono"], ["Reproduced by", item.reproduced_by?.join(", ") || "—", "mono"], ["In report", cited ? "yes" : "no"]]} /></Sec>
        <Sec title="Provenance"><KV rows={[["Snapshot checksum", shortChecksum(item.provenance.snapshot_checksum, 20), "mono"], ["Seed", String(item.provenance.seed ?? ""), "mono"], ["Algorithm version", String(item.provenance.algorithm_version ?? ""), "mono"], ["Digest", item.result_digest, "mono"]]} /></Sec>
        <Sec title="Actions">
          <div className="insp-actions">
            <Button size="sm" onClick={() => wb.inspect({ kind: "run", id: item.analysis_run_id })}>Inspect run</Button>
            <Button size="sm" onClick={() => wb.inspect({ kind: "method", id: item.kind === "EFFECT" ? "METH-LONG" : item.kind === "RELIABILITY" ? "METH-REL" : "METH-IND" })}>Methodology</Button>
            <Button size="sm" onClick={() => wb.inspect({ kind: "metric", id: item.metric_id })}>Metric</Button>
            <Button size="sm" variant="primary" onClick={() => wb.openLineage(item.id)}><GitBranch size={12} />Inspect lineage</Button>
          </div>
        </Sec>
        <Sec title="Interpretation (computed)"><p>{item.interpretation}</p></Sec>
      </div>
    </>
  );
}

function FigureInspector({ id }: { id: string }) {
  const wb = useWorkbench();
  const figure = useQuery({ queryKey: ["figure", id], queryFn: () => scienceApi.figure(id) });
  if (!figure.data) return <div className="insp-scroll"><Loading label={`Loading ${id}`} /></div>;
  return (
    <>
      <Head kind="FigureArtifact" title={<><span className="mono">{id}</span> {figure.data.title}</>} states={["COMPUTED"]} />
      <div className="insp-scroll">
        <Sec title="Binding"><KV rows={[["Evidence", figure.data.evidence_ids.join(", "), "mono"], ["Run", figure.data.analysis_run_id, "mono"], ["Dataset", figure.data.dataset_snapshot_id, "mono"], ["Kind", figure.data.kind]]} /></Sec>
        <Sec title="Spec"><pre className="code">{JSON.stringify({ ...figure.data.spec, subject_ids: Array.isArray(figure.data.spec.subject_ids) ? `${(figure.data.spec.subject_ids as string[]).length} athletes` : undefined, values: Array.isArray(figure.data.spec.values) ? `${(figure.data.spec.values as number[]).length} values` : undefined }, null, 2)}</pre></Sec>
        <Sec title="Actions"><Button size="sm" onClick={() => wb.openLineage(id)}><GitBranch size={12} />Inspect lineage</Button></Sec>
      </div>
    </>
  );
}

function LibraryInspector({ kind, id }: { kind: "metric" | "method" | "protocol"; id: string }) {
  const library = useLibrary();
  if (!library.data) return <div className="insp-scroll"><Loading label="Loading Library" /></div>;
  const lib = library.data;
  let body: ReactNode = null;
  if (kind === "metric") {
    const metric = lib.metrics.find((item) => item.id === id);
    body = metric ? <MetricDetail metric={metric} /> : null;
  } else if (kind === "method") {
    const method = lib.methods.find((item) => item.id === id);
    body = method ? <MethodDetail method={method} algorithm={lib.algorithms.find((item) => item.id === method.algorithm)} /> : null;
  } else {
    const protocol = lib.protocols.find((item) => item.id === id);
    body = protocol ? <ProtocolDetail protocol={protocol} /> : null;
  }
  return (
    <>
      <Head kind={`Library · ${kind}`} title={id} />
      <div className="insp-scroll"><div className="insp-sec lib-detail" style={{ padding: "10px 12px" }}>{body ?? <p>Not found in the Library.</p>}</div></div>
    </>
  );
}

function ModelInspector() {
  const model = useQuery({ queryKey: ["training-model"], queryFn: scienceApi.trainingModel });
  const library = useLibrary();
  const run = model.data?.run;
  const spec = model.data?.spec;
  if (!run || !spec) return <div className="insp-scroll"><Loading label="Loading model" /></div>;
  const entry = library.data?.models.find((item) => item.id === spec.id);
  return (
    <>
      <Head kind="ModelSpec / ModelRun" title={spec.name} states={[spec.status, "SYNTHETIC"]} />
      <div className="insp-scroll">
        <Sec title="Model"><KV rows={[["Kind", spec.kind], ["Spec", `${spec.id} v${spec.version}`, "mono"], ["Run", run.id, "mono"], ["Inputs", spec.inputs.join(", "), "mono"], ["Outputs", spec.outputs.join(", "), "mono"]]} /></Sec>
        <Sec title="Fitted parameters"><KV rows={Object.entries(run.parameters).map(([key, value]) => [key, String(value), "mono"] as [string, string, "mono"])} /></Sec>
        <Sec title="Solver"><KV rows={Object.entries(run.diagnostics.search_grid).map(([key, values]) => [key, values.join(", "), "mono"] as [string, string, "mono"])} /><p style={{ marginTop: 6 }}>Deterministic grid search minimising standardised RMSE between modelled and observed weekly means.</p></Sec>
        <Sec title="Fit"><KV rows={[["Observed weeks", String(run.output.observed_weeks.length)], ["RMSE (outcome units)", `${formatSig(run.output.fit_rmse_outcome_units, 4)} ${run.output.unit}`, "mono"], ["RMSE (standardised)", formatSig(run.output.fit_rmse_standardized, 4), "mono"], ["Max |residual|", formatSig(Math.max(...run.output.residuals.map(Math.abs)), 4), "mono"]]} /></Sec>
        <Sec title="Simulation settings"><KV rows={Object.entries(run.output.transform).filter(([key]) => key !== "note").map(([key, value]) => [key, typeof value === "number" ? formatSig(value, 5) : String(value), "mono"] as [string, string, "mono"])} /><p style={{ marginTop: 6 }}>{String(run.output.transform.note)}</p></Sec>
        {entry && <div className="insp-sec lib-detail" style={{ padding: "10px 12px" }}><ModelDetail model={entry} /></div>}
      </div>
    </>
  );
}

function AthleteInspector({ id }: { id: string }) {
  const wb = useWorkbench();
  const athlete = useQuery({ queryKey: ["athlete", id, "MET-CMJ-IMPULSE"], queryFn: () => scienceApi.athlete(id, "MET-CMJ-IMPULSE") });
  if (!athlete.data) return <div className="insp-scroll"><Loading label={`Loading ${id}`} /></div>;
  const data = athlete.data;
  const traced = data.observations.flatMap((observation) => observation.trials.filter((trial) => trial.trace_available).map((trial) => ({ ...trial, week: observation.week })));
  const flagged = data.observations.filter((observation) => observation.quality_state !== "VALID");
  return (
    <>
      <Head kind="Athlete · linked selection" title={<><span className="mono">{data.subject.display_id}</span> · {data.subject.position}</>} states={[data.subject.status, "SYNTHETIC"]} />
      <div className="insp-scroll">
        <Sec title="Subject"><KV rows={[["Subject ID", data.subject.subject_id, "mono"], ["Arm", <ArmLabel key="arm" arm={data.subject.intervention_arm} />], ["Age", `${data.subject.age} y`], ["Body mass", `${data.subject.body_mass_kg.toFixed(1)} kg`], ["Height", `${data.subject.height_cm.toFixed(1)} cm`], ["Training age", `${data.subject.training_age_years} y`]]} /></Sec>
        <Sec title="Concentric impulse · individual change"><KV rows={[["Baseline w1–2", `${formatSig(data.individual.baseline_mean, 4)} N·s·kg⁻¹`, "mono"], ["Post w9–10", `${formatSig(data.individual.post_mean, 4)} N·s·kg⁻¹`, "mono"], ["Change", `${formatSignedSig(data.individual.change, 3)} (${formatSignedSig(data.individual.percent_change, 3)} %)`, "mono"], ["vs TE of change", data.individual.exceeds_typical_error ? "exceeds" : "within"]]} /></Sec>
        <Sec title="Force traces retained">
          <div style={{ display: "grid", gap: 4 }}>
            {traced.map((trial) => (
              <div key={trial.trial_id} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span className="mono small">w{trial.week} {trial.trial_id}</span>
                <State plain>{trial.quality_state}</State>
                <span style={{ marginLeft: "auto" }}><Button size="sm" onClick={() => { wb.select({ athleteId: id, trialId: trial.trial_id, week: trial.week }); wb.openViewer({ kind: "force", trialId: trial.trial_id }); }}><Activity size={11} />Open</Button></span>
              </div>
            ))}
          </div>
        </Sec>
        <Sec title="Quality flags">{flagged.length ? <ul>{flagged.map((observation) => <li key={observation.week} className="small">w{observation.week}: {observation.quality_state} · {observation.missing_trials} missing, {observation.excluded_trials} excluded</li>)}</ul> : <p>All weekly observations complete.</p>}</Sec>
      </div>
    </>
  );
}

function TrialInspector({ id }: { id: string }) {
  const wb = useWorkbench();
  const detail = useQuery({ queryKey: ["force-trial", id], queryFn: () => scienceApi.forceTrial(id) });
  if (!detail.data) return <div className="insp-scroll">{detail.error ? <ErrorBox error={detail.error} /> : <Loading label={`Loading ${id}`} />}</div>;
  const { trial, provenance, boundaries } = detail.data;
  return (
    <>
      <Head kind="Measurement · CMJ trial" title={<span className="mono">{trial.trial_id}</span>} states={[trial.quality_state]} />
      <div className="insp-scroll">
        <Sec title="Context"><KV rows={[["Athlete", trial.display_id, "mono"], ["Session", trial.session_id, "mono"], ["Week / trial", `${trial.week} / ${trial.trial_number}`], ["Body mass", `${trial.body_mass_kg.toFixed(2)} kg`], ["Trace", trial.trace_available ? "1000 Hz retained" : "summary only"], ["Exclusion", trial.exclusion_reason || "—"]]} /></Sec>
        <Sec title="Phase boundaries (s)"><KV rows={Object.entries(boundaries).sort((a, b) => a[1] - b[1]).map(([key, value]) => [key.replaceAll("_", " "), value.toFixed(3), "mono"] as [string, string, "mono"])} /></Sec>
        <Sec title="Provenance"><KV rows={[["Snapshot", provenance.snapshot_id, "mono"], ["Seed", String(provenance.seed), "mono"], ["Generator", provenance.generator_version, "mono"], ["Source", provenance.source, "mono"], ["Trace checksum", shortChecksum(provenance.traces_checksum, 16), "mono"]]} /></Sec>
        <Sec title="Actions"><div className="insp-actions"><Button size="sm" variant="primary" onClick={() => wb.openViewer({ kind: "force", trialId: trial.trial_id })}><Activity size={12} />Open force signal</Button><Button size="sm" onClick={() => wb.openLineage(trial.trial_id)}><GitBranch size={12} />Lineage</Button></div></Sec>
      </div>
    </>
  );
}

function ReportInspector() {
  const wb = useWorkbench();
  const report = useReport();
  if (!report.data) return <div className="insp-scroll"><Loading label="Loading report" /></div>;
  const data = report.data;
  return (
    <>
      <Head kind="Report · terminal artifact" title={<><span className="mono">{data.id}</span> {data.title}</>} states={[data.status]} />
      <div className="insp-scroll">
        <Sec title="Composition"><KV rows={[["Study", data.study.id, "mono"], ["Snapshot", data.snapshot.id, "mono"], ["Evidence cited", String(data.evidence_ids.length)], ["Figures cited", String(data.figure_ids.length)], ["Updated", (data.updated_at ?? data.created_at).slice(0, 19).replace("T", " "), "mono"]]} /></Sec>
        <Sec title="Citations">
          {data.citations.map((citation) => (
            <div key={citation.artifact_id} style={{ display: "flex", gap: 8, alignItems: "baseline", marginBottom: 3 }}>
              <button type="button" className="mono" style={{ color: "var(--signal)" }} onClick={() => wb.inspect(citation.artifact_id.startsWith("FIG-") ? { kind: "figure", id: citation.artifact_id } : { kind: "evidence", id: citation.artifact_id })}>{citation.artifact_id}</button>
              <span className="small muted">{citation.section}</span>
            </div>
          ))}
        </Sec>
        <Sec title="Source runs"><div className="mono small">{[...new Set(data.evidence.map((item) => item.analysis_run_id))].join(" · ")}</div></Sec>
        <Sec title="Provenance"><p>{data.provenance_note}</p><div className="insp-actions" style={{ marginTop: 8 }}><Button size="sm" variant="primary" onClick={() => wb.openLineage(data.id)}><GitBranch size={12} />Inspect report lineage</Button></div></Sec>
      </div>
    </>
  );
}
