"use client";

import { useMutation } from "@tanstack/react-query";
import { GitBranch, X } from "lucide-react";
import type { ReactNode } from "react";
import type { Evidence } from "@/lib/types";
import { scienceApi } from "@/lib/api";
import { formatSig, formatSignedSig, metricOption, primaryResult, shortChecksum } from "@/lib/scientific";
import { Button, ErrorBox, Loading, State } from "@/components/ui";
import { FigureView } from "@/components/workbench/blocks/EvidenceBlocks";
import { useWorkbench } from "@/components/workbench/context";
import { useInvalidateScience, useReport, useRuns } from "@/components/workbench/data";

function Cite({ id, kind }: { id: string; kind: "evidence" | "run" | "figure" | "metric" }) {
  const wb = useWorkbench();
  return <button type="button" className="cite" onClick={() => wb.inspect({ kind, id })} title={`Inspect ${id}`}>{id}</button>;
}

function Section({ n, title, children }: { n: string; title: string; children: ReactNode }) {
  return <section aria-label={title}><h2><span className="n">{n}</span>{title}</h2>{children}</section>;
}

/** Collapse evidence that independently reproduces an already-cited artifact into one reported result. */
export function groupReproductions(items: Evidence[]): { primary: Evidence; reproductions: Evidence[] }[] {
  const byId = new Map(items.map((item) => [item.id, item]));
  const groups: { primary: Evidence; reproductions: Evidence[] }[] = [];
  const consumed = new Set<string>();
  for (const item of items) {
    if (consumed.has(item.id)) continue;
    const earlier = (item.reproduces ?? []).find((id) => byId.has(id));
    if (earlier) continue;
    const reproductions = items.filter((other) => other.id !== item.id && (other.reproduces ?? []).includes(item.id));
    reproductions.forEach((other) => consumed.add(other.id));
    groups.push({ primary: item, reproductions });
  }
  return groups;
}

function Result({ evidence, reproductions, onRemove }: { evidence: Evidence; reproductions: Evidence[]; onRemove?: (id: string) => void }) {
  const interval = evidence.interval;
  return (
    <div className={`report-result ${evidence.evidence_class === "EXPLORATORY" ? "exploratory" : ""}`}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
        <strong style={{ color: "var(--text-strong)" }}>{evidence.title}</strong>
        <State>{evidence.evidence_class ?? "PLANNED"}</State>
        <span style={{ marginLeft: "auto" }} className="faint small">
          <Cite id={evidence.id} kind="evidence" /> ← <Cite id={evidence.analysis_run_id} kind="run" /> · <span className="mono">{evidence.analysis_spec_id}</span>
          {onRemove && <button type="button" className="icon-btn" style={{ width: 18, height: 18, verticalAlign: "middle" }} aria-label={`Remove ${evidence.id} from the report`} onClick={() => onRemove(evidence.id)}><X size={11} /></button>}
        </span>
      </div>
      <div style={{ marginTop: 4 }}>
        <span className="v">{evidence.kind === "EFFECT" ? formatSignedSig(evidence.estimate, 3) : formatSig(evidence.estimate, 3)}</span>
        <span className="unit">{evidence.unit}</span>
        {interval && interval.low !== null && interval.high !== null && <span className="mono muted" style={{ marginLeft: 10 }}>95% CI [{formatSig(interval.low, 3)}, {formatSig(interval.high, 3)}]</span>}
        <span className="faint small" style={{ marginLeft: 10 }}>{evidence.uncertainty_label} {formatSig(evidence.uncertainty, 3)} · n = {evidence.sample_size} · {evidence.population}</span>
      </div>
      <p style={{ marginTop: 6, fontSize: 13 }}>{evidence.interpretation}</p>
      {reproductions.length > 0 && (
        <div className="faint small" style={{ marginTop: 4 }}>
          Independently re-executed and reproduced (identical result digest) by {reproductions.map((item, index) => <span key={item.id}>{index > 0 && ", "}<Cite id={item.id} kind="evidence" /> (<Cite id={item.analysis_run_id} kind="run" />)</span>)}.
        </div>
      )}
    </div>
  );
}

export function ReportDocument() {
  const wb = useWorkbench();
  const report = useReport();
  const runs = useRuns();
  const invalidate = useInvalidateScience();
  const uncite = useMutation({ mutationFn: (id: string) => scienceApi.uncite(id), onSuccess: () => invalidate() });
  if (report.isLoading) return <div className="report"><Loading label="Composing report from cited artifacts" /></div>;
  if (report.error || !report.data) return <div className="report"><ErrorBox error={report.error ?? "Report unavailable"} /></div>;
  const data = report.data;
  const sectionOf = (id: string) => data.citations.find((citation) => citation.artifact_id === id)?.section;
  const inSection = (section: string) => data.evidence.filter((item) => sectionOf(item.id) === section);
  const figuresIn = (section: string) => data.figures.filter((figure) => sectionOf(figure.id) === section);
  const intervention = groupReproductions(inSection("Intervention result"));
  const reliability = groupReproductions(inSection("Reliability context"));
  const exploratory = groupReproductions(inSection("Exploratory results"));
  const reliabilityRun = runs.data?.find((run) => run.id === inSection("Reliability context").find((item) => item.kind === "RELIABILITY")?.analysis_run_id);
  const reliabilityResult = primaryResult<Record<string, number>>(reliabilityRun?.result);
  const note = wb.blocks.find((block) => block.type === "interpretation")?.state.note;
  const estimators = [...new Set(data.evidence.map((item) => String(item.provenance.algorithm ?? "")).filter(Boolean))];
  const remove = (id: string) => uncite.mutate(id);

  let figureNumber = 0;
  // A figure bound to evidence that merely reproduces cited evidence is identical by construction; show it once.
  const reproductionIds = new Set(data.evidence.filter((item) => (item.reproduces ?? []).some((id) => data.evidence_ids.includes(id))).map((item) => item.id));
  const renderFigures = (section: string) =>
    figuresIn(section).filter((figure) => !figure.evidence_ids.every((id) => reproductionIds.has(id))).map((figure) => {
      const duplicates = figuresIn(section).filter((other) => other.id !== figure.id && other.evidence_ids.every((id) => reproductionIds.has(id)) && other.kind === figure.kind && other.spec.metric_id === figure.spec.metric_id && other.spec.cohort_id === figure.spec.cohort_id);
      figureNumber += 1;
      return (
        <figure key={figure.id} className="report-fig">
          <div className="chart-frame"><FigureView figure={figure} /></div>
          <figcaption>
            <strong style={{ color: "var(--text-2)" }}>Figure {figureNumber}.</strong> {figure.title}.{duplicates.length > 0 && <> Identical figure{duplicates.length > 1 ? "s" : ""} from the reproduction: {duplicates.map((item) => <Cite key={item.id} id={item.id} kind="figure" />)}.</>} {String(figure.spec.summary ?? "")} Computed from {figure.dataset_snapshot_id} for cohort {String(figure.spec.cohort_id ?? "COHORT-001")}; bound to {figure.evidence_ids.map((id) => <Cite key={id} id={id} kind="evidence" />)} · <Cite id={figure.id} kind="figure" />
            <button type="button" className="icon-btn" style={{ width: 18, height: 18, verticalAlign: "middle" }} aria-label={`Remove ${figure.id} from the report`} onClick={() => remove(figure.id)}><X size={11} /></button>
          </figcaption>
        </figure>
      );
    });

  return (
    <article className="report" aria-label={data.title}>
      <div className="report-paper">
        <div className="report-meta">
          <span>{data.id}</span><span>{data.status}</span><span>{data.study.id}</span><span>{data.snapshot.id} · seed {data.snapshot.seed}</span><span>{data.evidence.length} evidence · {data.figures.length} figures cited</span><span>SYNTHETIC</span>
          <span style={{ marginLeft: "auto" }}><Button size="sm" onClick={() => wb.openLineage(data.id)}><GitBranch size={12} />Inspect report lineage</Button></span>
        </div>
        <h1>{data.title}</h1>
        <p className="lede">{data.study.title}</p>

        <Section n="1" title="Study question and design">
          <p>{data.question.statement}</p>
          <p style={{ marginTop: 6 }}>{data.study.design} {data.study.intervention} Primary estimand (frozen in {data.plan.id} before data inspection): {data.plan.primary_estimand.toLowerCase()}.</p>
          <ul>{data.hypotheses.map((hypothesis) => <li key={hypothesis.id}><span className="mono faint">{hypothesis.id}</span> ({hypothesis.status.toLowerCase()}) {hypothesis.statement}</li>)}</ul>
        </Section>

        <Section n="2" title="Dataset and cohort">
          <p>
            Data are the deterministic synthetic snapshot <span className="mono">{data.snapshot.id}</span> ({data.snapshot.generator_version}, seed {data.snapshot.seed}, schema {data.snapshot.schema_version}; cmj_trials SHA-256 {shortChecksum(data.snapshot.checksums["cmj_trials.parquet"], 16)}…).
            The frozen cohort <span className="mono">{data.cohort.id}</span> comprises {data.cohort.subject_ids.length} athletes ({Object.values(data.groups).map((group) => `${group.label.toLowerCase()} ${wb.study.arm_counts[group.arm] ?? "—"}`).join(", ")}) observed over {data.study.end_week} weeks with two CMJ trials per week.
          </p>
          <p style={{ marginTop: 6 }}>
            Of {data.data_health.expected_slots} expected trials, {data.data_health.valid_measurements} were valid, {data.data_health.excluded_measurements} was excluded by the deterministic QC rule ({data.data_health.excluded_trials.map((trial) => `${trial.trial_id}: ${trial.reason.toLowerCase()}`).join("; ")}) and {data.data_health.missing_observations} were not captured; missing trials are reported, not imputed, and the excluded trial remains discoverable.
          </p>
        </Section>

        <Section n="3" title="Methods">
          <p>
            Primary outcomes were analysed with a group × time repeated-measures model of the first valid weekly trial with week centred on week 1, so the interaction contrast equals the difference in change from week 1 to week 10 between arms.
            Estimators actually used by the cited runs: {estimators.join("; ") || "—"}. Uncertainty is reported as Wald 95% confidence intervals from the fitted covariance.
            Reliability used balanced repeated baseline trials (ICC(3,1) with Shrout–Fleiss 95% CI, within-subject CV and typical error). Individual change is descriptive and benchmarked against the typical error of a change.
            Force metrics are extracted from 1000 Hz synthetic traces by deterministic phase-aware integration; each metric is a versioned MetricDefinition.
          </p>
        </Section>

        <Section n="4" title="Intervention result">
          {intervention.length === 0 && <p className="faint">No intervention evidence is cited. Promote a run and add it to the report from the workbench.</p>}
          {intervention.map((group) => <Result key={group.primary.id} evidence={group.primary} reproductions={group.reproductions} onRemove={remove} />)}
          {renderFigures("Intervention result")}
        </Section>

        <Section n="5" title="Reliability context">
          {reliability.map((group) => <Result key={group.primary.id} evidence={group.primary} reproductions={group.reproductions} onRemove={remove} />)}
          {reliabilityResult?.smallest_worthwhile_change !== undefined && (
            <p>Smallest worthwhile change for concentric impulse (1.96·√2·typical error, from <Cite id={reliabilityRun?.id ?? ""} kind="run" />): {formatSig(reliabilityResult.smallest_worthwhile_change, 3)} N·s·kg⁻¹.</p>
          )}
          {renderFigures("Reliability context")}
        </Section>

        {exploratory.length > 0 && (
          <Section n="5b" title="Exploratory results (not pre-specified)">
            {exploratory.map((group) => <Result key={group.primary.id} evidence={group.primary} reproductions={group.reproductions} onRemove={remove} />)}
            {renderFigures("Exploratory results")}
          </Section>
        )}

        <Section n="6" title="Interpretation">
          {intervention.map((group) => {
            const metric = metricOption(group.primary.metric_id);
            const swc = metric.id === "MET-CMJ-IMPULSE" ? reliabilityResult?.smallest_worthwhile_change : undefined;
            return (
              <p key={group.primary.id}>
                <State plain>COMPUTED</State> {metric.label}: {formatSignedSig(group.primary.estimate, 3)} {group.primary.unit}
                {group.primary.interval ? `, 95% CI ${formatSig(group.primary.interval.low, 3)} to ${formatSig(group.primary.interval.high, 3)}` : ""}
                {group.primary.interval && group.primary.interval.low !== null && group.primary.interval.high !== null ? (group.primary.interval.low > 0 || group.primary.interval.high < 0 ? " — the 95% interval excludes zero difference in change" : " — the 95% interval includes zero difference in change") : ""}
                {swc !== undefined ? `; the point estimate ${Math.abs(group.primary.estimate ?? 0) > swc ? "exceeds" : "does not exceed"} the smallest worthwhile change (${formatSig(swc, 3)} ${group.primary.unit})` : ""}. <Cite id={group.primary.id} kind="evidence" />
              </p>
            );
          })}
          {typeof note === "string" && note.trim() && <p style={{ marginTop: 8 }}><State plain tone="tone-neutral">SCIENTIST</State> {note}</p>}
        </Section>

        <Section n="7" title="Limitations">
          <ul>
            <li>All data are synthetic ({data.snapshot.provenance.simulated_entities as string}); results have no external validity and support no clinical, performance or readiness decision.</li>
            <li>The longitudinal model uses a linear week term; the week-11 load spike and week-12 transient suppression appear as structured residuals rather than being modelled.</li>
            <li>Force traces are internally coherent demonstrations; flight time and propulsive impulse are generated separately, so impulse-momentum jump height is not materialised.</li>
            <li>Reliability rests on two baseline trials per athlete, which bounds ICC precision.</li>
            <li>The training-response model is an aggregate mechanistic prototype without parameter uncertainty; it is not an individual predictor.</li>
          </ul>
        </Section>

        <Section n="8" title="Reproducibility and provenance">
          <table className="report-table">
            <thead><tr><th>Artifact</th><th>Run</th><th>Spec</th><th>Cohort</th><th>Snapshot</th><th>Result digest</th></tr></thead>
            <tbody>
              {data.evidence.map((item) => (
                <tr key={item.id}><td><Cite id={item.id} kind="evidence" /></td><td><Cite id={item.analysis_run_id} kind="run" /></td><td className="mono">{item.analysis_spec_id}</td><td className="mono">{item.cohort_id}</td><td className="mono">{item.dataset_snapshot_id}</td><td className="mono faint">{item.result_digest}</td></tr>
              ))}
            </tbody>
          </table>
          <p className="faint small" style={{ marginTop: 8 }}>{data.provenance_note} Every cited value resolves to an immutable run; select any identifier to inspect it, or inspect the report lineage to trace back to the generator.</p>
        </Section>
      </div>
    </article>
  );
}
