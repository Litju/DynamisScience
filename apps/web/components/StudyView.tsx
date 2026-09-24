"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowRight, CalendarDays, Check, ClipboardList, GitBranch, LockKeyhole, Microscope, ScrollText, Target, UsersRound } from "lucide-react";
import { scienceApi } from "@/lib/api";
import { Button, KeyValue, LockedPlan, LoadingState, Panel, SectionHeader, StatusBadge } from "@/components/ui";
import type { StudyDetail } from "@/lib/types";

export function StudyView({ onNavigate }: { onNavigate: (view: string, id?: string) => void }) {
  const query = useQuery({ queryKey: ["study", "STUDY-001"], queryFn: () => scienceApi.study("STUDY-001") });
  if (query.isLoading) return <LoadingState label="Loading the frozen study specification" />;
  if (query.error || !query.data) return <div className="error-state">Study specification could not be loaded.</div>;
  const data = query.data as StudyDetail;
  const plan = data.plan;
  const interventionCount = data.arm_counts?.INTERVENTION ?? 0;
  const comparisonCount = data.arm_counts?.COMPARISON ?? 0;

  return (
    <div className="view-stack">
      <SectionHeader
        eyebrow="Studies / STUDY-001"
        title={data.study.title}
        description={data.study.research_question}
        actions={<><StatusBadge tone="good">{data.study.state}</StatusBadge><Button size="sm" onClick={() => onNavigate("analyses")}><Microscope size={14} /> Open analyses</Button></>}
      />
      <div className="study-title-strip">
        <div className="study-id-block"><span className="study-id">{data.study.id}</span><span>{data.study.design}</span></div>
        <div className="study-title-meta">
          <span><UsersRound size={13} /> {data.study.participant_count} participants</span>
          <span><CalendarDays size={13} /> weeks {data.study.start_week}–{data.study.end_week}</span>
          <span className="mono">{data.snapshot.id}</span>
        </div>
      </div>
      <div className="study-layout">
        <div className="study-main-column">
          <Panel eyebrow="Research question" title="What is being tested?" action={<StatusBadge tone="cyan">{data.question.id}</StatusBadge>}>
            <div className="research-question"><Target size={20} /><p>{data.question.statement}</p></div>
            <div className="estimand-grid">
              <div><span>Estimand</span><p>{data.question.estimand}</p></div>
              <div><span>Exposure</span><p>{data.question.exposure}</p></div>
              <div><span>Population</span><p>{data.question.population}</p></div>
              <div><span>Time horizon</span><p>{data.question.time_horizon}</p></div>
            </div>
          </Panel>
          <Panel eyebrow="Study design / intervention arms" title="Controlled longitudinal cohort" action={<StatusBadge tone="warn">WEEKS 3–10</StatusBadge>}>
            <div className="arm-grid">
              {Object.values(data.groups ?? {}).map((group) => (
                <div className={`arm-card ${group.arm === "INTERVENTION" ? "intervention" : "comparison"}`} key={group.arm}>
                  <div className="arm-card-head">
                    <strong>{group.label}</strong>
                    <StatusBadge tone={group.arm === "INTERVENTION" ? "cyan" : "warn"}>{group.arm}</StatusBadge>
                  </div>
                  <span className="arm-count mono">{group.arm === "INTERVENTION" ? interventionCount : comparisonCount} athletes</span>
                  <p>{group.description}</p>
                  <span className="arm-window mono">block weeks {group.block_weeks[0]}–{group.block_weeks[1]}</span>
                </div>
              ))}
            </div>
            <StudyTimeline />
            <div className="timeline-legend">
              <span><i className="timeline-dot baseline" />Baseline / familiarization</span>
              <span><i className="timeline-dot block" />Strength block</span>
              <span><i className="timeline-dot taper" />Match / taper</span>
              <span><i className="timeline-dot recovery" />Recovery / follow-up</span>
            </div>
          </Panel>
          <Panel eyebrow="Outcome hierarchy" title="Pre-specified measures" action={<span className="subtle">Protocol PROT-CMJ</span>}>
            <div className="outcome-columns">
              <div className="outcome-column">
                <span className="outcome-label primary">Primary</span>
                <OutcomeList items={data.study.primary_outcomes} />
                <span className="outcome-note">Directly tied to {data.question.id} and the frozen contrast</span>
              </div>
              <div className="outcome-column">
                <span className="outcome-label secondary">Secondary</span>
                <OutcomeList items={data.study.secondary_outcomes} />
                <span className="outcome-note">Directional context, smaller expected effects</span>
              </div>
              <div className="outcome-column">
                <span className="outcome-label contextual">Contextual</span>
                <OutcomeList items={["weekly external load", "match exposure", "sleep / soreness / fatigue"]} />
                <span className="outcome-note">Not readiness scores</span>
              </div>
            </div>
          </Panel>
          <Panel eyebrow="Frozen analysis plan" title={plan?.id ?? "PLAN-001"} action={<StatusBadge tone="purple">{plan?.status ?? "FROZEN"}</StatusBadge>}>
            <LockedPlan>
              <span className="mono">{plan?.frozen_before_inspection ? "created before outcome inspection" : "plan status recorded"}</span>
            </LockedPlan>
            <div className="plan-grid">
              <div><span>Primary outcomes</span>{plan?.primary_outcomes.map((item) => <strong key={item}>{item}</strong>)}</div>
              <div><span>Exclusion criteria</span>{plan?.exclusion_criteria.map((item) => <strong key={item}>{item}</strong>)}</div>
              <div><span>Planned models</span>{plan?.planned_models.map((item) => <strong key={item}>{item}</strong>)}</div>
              <div><span>Planned contrasts</span>{plan?.planned_contrasts.map((item) => <strong key={item}>{item}</strong>)}</div>
            </div>
            <div className="plan-footer"><LockKeyhole size={14} /> {plan?.immutability_rule ?? "Changing the plan requires a new AnalysisSpec and a new immutable AnalysisRun."}</div>
          </Panel>
        </div>
        <aside className="study-side-column">
          <Panel eyebrow="Cohort definition" title={data.cohort.id} action={<StatusBadge tone="purple">{data.cohort.status}</StatusBadge>}>
            <KeyValue label="Members" value={`${data.cohort.subject_ids.length} athletes`} />
            <KeyValue label="Arms" value={`${interventionCount} intervention · ${comparisonCount} comparison`} />
            <KeyValue label="Snapshot" value={data.cohort.snapshot_id} mono />
            <div className="cohort-rule"><ScrollText size={14} /><div><strong>Eligibility rule</strong><span>{data.cohort.description}</span></div></div>
            <div className="cohort-rule"><ClipboardList size={14} /><div><strong>Exclusions</strong><span>{data.cohort.exclusion_criteria.join(" · ")}</span></div></div>
            <div className="cohort-rule"><Check size={14} /><div><strong>Observed quality</strong><span>{data.data_health.valid_measurements} valid · {data.data_health.excluded_measurements} excluded · {data.data_health.missing_observations} missing slots</span></div></div>
            <Button size="sm" variant="ghost" onClick={() => onNavigate("monitor")}>Open cohort monitor <ArrowRight size={13} /></Button>
          </Panel>
          <Panel eyebrow="Hypotheses" title="Scientific claims" action={<span className="mono subtle">{data.hypotheses.length} registered</span>}>
            <div className="hypothesis-list">
              {data.hypotheses.map((hypothesis) => (
                <div className="hypothesis" key={hypothesis.id}>
                  <div className="hypothesis-top">
                    <span className="mono">{hypothesis.id}</span>
                    <StatusBadge tone={hypothesis.status === "PRIMARY" ? "cyan" : "neutral"}>{hypothesis.status}</StatusBadge>
                  </div>
                  <p>{hypothesis.statement}</p>
                  <small>{hypothesis.rationale}</small>
                  <span className="hypothesis-direction mono">expected {hypothesis.direction}</span>
                </div>
              ))}
            </div>
          </Panel>
          <Panel eyebrow="Protocols" title="Measurement contracts" action={<span className="subtle">{data.protocols.length} active</span>}>
            <div className="protocol-list">
              {data.protocols.map((protocol) => (
                <button key={protocol.id} className="protocol-row" onClick={() => onNavigate("registry")}>
                  <span className="protocol-icon"><GitBranch size={14} /></span>
                  <span><strong>{protocol.name}</strong><small>{protocol.frequency} · {protocol.id} · {protocol.duration_weeks} weeks</small></span>
                  <ArrowRight size={13} />
                </button>
              ))}
            </div>
          </Panel>
          <Panel eyebrow="Analysis specifications" title="Machine-readable plans" action={<span className="subtle">{data.analysis_specs.length} specs</span>}>
            <div className="spec-list">
              {data.analysis_specs.map((spec) => (
                <button key={spec.id} className="spec-row" onClick={() => onNavigate("analyses", spec.id)}>
                  <span className="spec-status"><Check size={12} /></span>
                  <span><strong className="mono">{spec.id}</strong><small>{spec.name}</small><small className="mono">{spec.model_formula}</small></span>
                  <StatusBadge tone="purple">{spec.status}</StatusBadge>
                </button>
              ))}
            </div>
          </Panel>
        </aside>
      </div>
      <Panel eyebrow="Snapshot provenance" title={data.snapshot.id} action={<Button size="sm" variant="ghost" onClick={() => onNavigate("lineage", data.snapshot.id)}>Inspect lineage <ArrowRight size={13} /></Button>}>
        <div className="snapshot-grid">
          <KeyValue label="Seed" value={String(data.snapshot.seed)} mono />
          <KeyValue label="Generator" value={data.snapshot.generator_version} mono />
          <KeyValue label="Schema" value={data.snapshot.schema_version} mono />
          <KeyValue label="Generated" value={data.snapshot.generated_at} mono />
          <KeyValue label="Rows" value={Object.values(data.snapshot.row_counts).reduce((sum, value) => sum + value, 0).toLocaleString()} />
          <KeyValue label="Checksums" value={`${Object.keys(data.snapshot.checksums).length} files`} />
        </div>
        <div className="snapshot-checksum mono">{data.snapshot.checksums["cmj_trials.parquet"] ?? "checksum unavailable"}</div>
      </Panel>
    </div>
  );
}

function OutcomeList({ items }: { items: string[] }) {
  return <ul className="outcome-list">{items.map((item) => <li key={item}><Check size={12} />{item}</li>)}</ul>;
}

function StudyTimeline() {
  const blocks = [
    { label: "Baseline", range: "W1–2", className: "baseline" },
    { label: "Intervention", range: "W3–10", className: "block" },
    { label: "Post", range: "W11–12", className: "taper" },
    { label: "Follow-up", range: "W13–16", className: "recovery" },
  ];
  return (
    <div className="study-timeline">
      {blocks.map((block, index) => (
        <div className={`study-timeline-block ${block.className}`} key={block.label}>
          <span>{String(index + 1).padStart(2, "0")}</span>
          <strong>{block.label}</strong>
          <small>{block.range}</small>
        </div>
      ))}
    </div>
  );
}
