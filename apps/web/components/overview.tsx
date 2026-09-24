"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Database, FileCheck2, FlaskConical, GitBranch, ShieldCheck } from "lucide-react";
import { scienceApi } from "@/lib/api";
import { LongitudinalChart } from "@/components/charts";
import { Button, ErrorState, LoadingState, MetricTile, Panel, SectionHeader, StatusBadge } from "@/components/ui";
import type { OverviewData } from "@/lib/types";

export function OverviewView({ onNavigate }: { onNavigate: (view: string, id?: string) => void }) {
  const query = useQuery({ queryKey: ["overview"], queryFn: scienceApi.overview });
  if (query.isLoading) return <LoadingState />;
  if (query.error || !query.data) return <ErrorState message="Start the local FastAPI service to load the analytical snapshot." onRetry={() => query.refetch()} />;
  const data = query.data as OverviewData;
  const groups = Object.values(data.groups ?? {});
  const totalRows = Object.values(data.snapshot.row_counts).reduce((sum, value) => sum + value, 0);

  return (
    <div className="view-stack">
      <SectionHeader
        eyebrow="Command center / local synthetic workspace"
        title="DynamisScience"
        description="Scientific computation and evidence layer for human performance."
        actions={<><StatusBadge tone="cyan">LOCAL / SYNTHETIC</StatusBadge><Button size="sm" onClick={() => onNavigate("studies")}><FileCheck2 size={14} /> Open study</Button></>}
      />
      <div className="overview-strip">
        <div className="context-mark">
          <span className="mark-glyph">∿</span>
          <div><strong>Research context</strong><span>Question → Data → Cohort → Method → Analysis → Evidence</span></div>
        </div>
        <div className="snapshot-inline">
          <span className="mono">{data.snapshot.id}</span>
          <span>{totalRows.toLocaleString()} rows · {Object.keys(data.snapshot.checksums).length} checksums</span>
          <ShieldCheck size={14} />
        </div>
      </div>
      <div className="metric-grid overview-metrics">
        <MetricTile label="Participants" value={String(data.study.participant_count)} detail={`${groups.map((group) => `${group.arm === "INTERVENTION" ? "INT" : "CMP"} ${data.data_health.total_subjects / Math.max(1, groups.length)}`).join(" · ") || "synthetic cohort"}`} state="SYNTHETIC" onClick={() => onNavigate("studies")} />
        <MetricTile label="Valid trials" value={data.data_health.valid_measurements.toLocaleString()} detail={`${data.data_health.excluded_measurements} excluded · ${data.data_health.missing_observations} missing slots`} state="VALID" onClick={() => onNavigate("monitor")} />
        <MetricTile label="Provenance" value={`${data.data_health.provenance_completeness.toFixed(1)}%`} detail={`${data.data_health.complete_records}/${data.data_health.total_records} records complete`} state="VALID" onClick={() => onNavigate("lineage")} />
        <MetricTile label="Analysis runs" value={String(data.recent_analyses.length).padStart(2, "0")} detail="immutable executions" state="FROZEN" onClick={() => onNavigate("runs")} />
      </div>
      <div className="overview-grid">
        <Panel className="study-command" eyebrow="Active study / STUDY-001" title={data.study.title} action={<StatusBadge tone="good">{data.study.state}</StatusBadge>}>
          <div className="question-block"><span className="quote-mark">“</span><p>{data.study.research_question}</p></div>
          <div className="study-facts">
            <div><span>Design</span><strong>{data.study.design}</strong></div>
            <div><span>Population</span><strong>{data.study.participant_count} synthetic athletes</strong></div>
            <div><span>Intervention</span><strong>{data.study.intervention}</strong></div>
            <div><span>Snapshot</span><strong className="mono">{data.snapshot.id}</strong></div>
          </div>
          <div className="panel-footer">
            <Button size="sm" variant="primary" onClick={() => onNavigate("studies")}>Inspect study <ArrowRight size={14} /></Button>
            <span className="subtle">{data.plan?.status ?? "FROZEN"} plan · {data.study.analysis_spec_ids.length} planned analyses</span>
          </div>
        </Panel>
        <Panel eyebrow="Data health / provenance" title="Measurement integrity" action={<Button size="sm" variant="ghost" onClick={() => onNavigate("registry")}>View registry <ArrowRight size={13} /></Button>}>
          <div className="health-rows">
            <HealthRow label="Valid trials" value={data.data_health.valid_measurements} state="VALID" detail="included in primary analyses" />
            <HealthRow label="Excluded trials" value={data.data_health.excluded_measurements} state="EXCLUDED" detail="flagged, not silently removed" />
            <HealthRow label="Missing trial slots" value={data.data_health.missing_observations} state="WARNING" detail={`of ${data.data_health.expected_slots} expected`} />
            <HealthRow label="Provenance completeness" value={`${data.data_health.provenance_completeness.toFixed(1)}%`} state="VALID" detail="source → method → artifact" />
          </div>
          <div className="integrity-note"><ShieldCheck size={15} /><span>Every displayed result can be traced to a snapshot, method, and run.</span></div>
        </Panel>
      </div>
      <Panel
        className="signal-panel"
        eyebrow="Longitudinal signal / group mean"
        title="Intervention response in concentric impulse"
        action={
          <div className="chart-legend">
            <span><i className="legend-line cyan" />Intervention</span>
            <span><i className="legend-line amber" />Comparison</span>
            <span className="mono subtle">N·s·kg⁻¹</span>
          </div>
        }
      >
        <LongitudinalChart data={data.longitudinal_signal} />
        <div className="chart-caption">
          <span><span className="caption-mark intervention" />Weeks 3–10 strength block</span>
          <span><span className="caption-mark load" />Week 11 load spike → week 12 transient suppression</span>
          <span><span className="caption-mark recovery" />Follow-up recovery</span>
          <Button size="sm" variant="ghost" onClick={() => onNavigate("analyses")}>Open analysis <ArrowRight size={13} /></Button>
        </div>
      </Panel>
      <div className="lower-grid">
        <Panel eyebrow="Dataset snapshot" title={data.snapshot.id} action={<Button size="sm" variant="ghost" onClick={() => onNavigate("lineage", data.snapshot.id)}>Trace snapshot <ArrowRight size={13} /></Button>}>
          <div className="snapshot-grid">
            <div><span className="eyebrow">Seed</span><strong className="mono">{data.snapshot.seed}</strong></div>
            <div><span className="eyebrow">Generator</span><strong className="mono">{data.snapshot.generator_version}</strong></div>
            <div><span className="eyebrow">Schema</span><strong className="mono">{data.snapshot.schema_version}</strong></div>
            <div><span className="eyebrow">Generated</span><strong className="mono">{data.snapshot.generated_at}</strong></div>
          </div>
          <div className="table-scroll">
            <table className="data-table compact">
              <thead><tr><th>Table</th><th>Rows</th><th>Checksum</th></tr></thead>
              <tbody>
                {Object.entries(data.snapshot.row_counts).map(([name, count]) => (
                  <tr key={name}>
                    <td className="mono">{name}</td>
                    <td className="mono">{count.toLocaleString()}</td>
                    <td className="mono subtle">{String(data.snapshot.checksums[`${name}.parquet`] ?? "—").slice(0, 12)}…</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="snapshot-footnote"><Database size={13} /> 1000 Hz force traces · 10 Hz tracking and pose · {data.snapshot.pose_athletes.length} pose athletes retained</div>
        </Panel>
        <Panel eyebrow="Execution ledger" title="Recent analyses" action={<Button size="sm" variant="ghost" onClick={() => onNavigate("runs")}>All runs <ArrowRight size={13} /></Button>}>
          <div className="run-list">
            {(data.recent_analyses ?? []).map((run) => (
              <button className="run-row" key={run.id} onClick={() => onNavigate("runs", run.id)}>
                <span className="run-icon"><FlaskConical size={14} /></span>
                <span className="run-main"><strong>{run.id} · {run.method_id}</strong><small>{run.analysis_spec_id} · {run.snapshot_id}</small></span>
                <StatusBadge tone="good">{run.status}</StatusBadge>
                <span className="mono subtle">{run.duration_ms.toFixed(0)} ms</span>
                <ArrowRight size={13} />
              </button>
            ))}
          </div>
        </Panel>
        <Panel eyebrow="Evidence objects" title="First-class results" action={<Button size="sm" variant="ghost" onClick={() => onNavigate("reports")}>Open report <ArrowRight size={13} /></Button>}>
          <div className="evidence-mini-list">
            {(data.evidence_artifacts ?? []).map((evidence) => (
              <button key={evidence.id} className="evidence-mini" onClick={() => onNavigate("lineage", evidence.id)}>
                <span className="evidence-type">{evidence.kind.slice(0, 4)}</span>
                <span><strong>{evidence.title}</strong><small>{evidence.id} · {evidence.analysis_run_id} · n={evidence.sample_size}</small></span>
                <StatusBadge tone={evidence.quality === "VALID" ? "good" : "warn"}>{evidence.quality}</StatusBadge>
              </button>
            ))}
          </div>
          <div className="evidence-note"><GitBranch size={14} /> Evidence is not a chart decoration; it is a versioned scientific object.</div>
        </Panel>
      </div>
    </div>
  );
}

function HealthRow({ label, value, state, detail }: { label: string; value: number | string; state: string; detail: string }) {
  return (
    <div className="health-row">
      <div><span>{label}</span><small>{detail}</small></div>
      <strong className="mono">{value}</strong>
      <StatusBadge tone={state === "VALID" ? "good" : state === "WARNING" ? "warn" : "bad"}>{state}</StatusBadge>
    </div>
  );
}
