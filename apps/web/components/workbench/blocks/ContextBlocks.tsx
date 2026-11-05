"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { CircleHelp, Database, ExternalLink, Info, Lock, RotateCcw, Users } from "lucide-react";
import type { Arm, WorkbenchBlock } from "@/lib/types";
import { scienceApi } from "@/lib/api";
import { shortChecksum } from "@/lib/scientific";
import { updateState } from "@/lib/workbench";
import { ArmLabel, Button, ErrorBox, Loading, Readout, State } from "@/components/ui";
import { BlockFrame } from "../Block";
import { useWorkbench } from "../context";

interface BlockProps {
  block: WorkbenchBlock;
  index: number;
}

export function QuestionBlock({ block, index }: BlockProps) {
  const { study, inspect } = useWorkbench();
  const plan = study.plan;
  return (
    <BlockFrame block={block} index={index} icon={<CircleHelp size={12} />} title="Research question" sub={study.question.id} states={[plan.status]}>
      <p className="question">{study.question.statement}</p>
      <div className="block-cols">
        <div>
          <div className="upper faint" style={{ marginBottom: 4 }}>Primary estimand</div>
          <div>{plan.primary_estimand}</div>
          <div className="faint small" style={{ marginTop: 4 }}>{study.question.population} · exposure {study.question.exposure.toLowerCase()} · {study.question.time_horizon.toLowerCase()}</div>
        </div>
        <div>
          <div className="upper faint" style={{ marginBottom: 4 }}>Hypotheses</div>
          {study.hypotheses.map((hypothesis) => (
            <div className="hyp" key={hypothesis.id}>
              <span className="mono faint">{hypothesis.id}</span>
              <span><State plain tone={hypothesis.status === "PRIMARY" ? "tone-frozen" : "tone-neutral"}>{hypothesis.status}</State></span>
              <span>{hypothesis.statement}</span>
            </div>
          ))}
        </div>
      </div>
      <div className="plan">
        <div className="plan-head">
          <Lock size={12} />
          <strong style={{ color: "var(--text-strong)", fontWeight: 600 }}>{plan.frozen_before_inspection || study.research ? "Frozen analysis plan" : "Registered analysis plan"}</strong>
          <span className="mono faint">{plan.id}</span>
          <span className="faint">· {study.research ? "frozen locally, not externally preregistered" : plan.frozen_before_inspection ? "frozen before data inspection" : "registered after source acquisition"} · changes create new specs, never edits</span>
          <span style={{ marginLeft: "auto" }}><Button size="sm" variant="ghost" onClick={() => inspect({ kind: "design", section: "plan" })}>Inspect plan</Button></span>
        </div>
        <div className="plan-row"><span>Primary outcomes</span><span>{plan.primary_outcomes.join(" · ")}</span></div>
        <div className="plan-row"><span>Secondary outcomes</span><span>{plan.secondary_outcomes.join(" · ")}</span></div>
        <div className="plan-row"><span>Exclusion criteria</span><span>{plan.exclusion_criteria.join(" · ")}</span></div>
        <div className="plan-row"><span>Planned longitudinal</span><span>{plan.planned_models[0]}</span></div>
        <div className="plan-row"><span>Planned reliability</span><span>{plan.planned_reliability}</span></div>
        <div className="plan-row"><span>Post-plan analyses</span><span>{plan.post_plan_rule}</span></div>
      </div>
    </BlockFrame>
  );
}

export function DatasetBlock({ block, index }: BlockProps) {
  const { study, inspect } = useWorkbench();
  const snapshot = study.snapshot;
  const health = study.data_health;
  const rows = snapshot.row_counts;
  const real = study.real_data;
  const source = snapshot.source;
  const rowTotal = Object.values(rows).reduce((sum, value) => sum + value, 0);
  return (
    <BlockFrame
      block={block}
      index={index}
      icon={<Database size={12} />}
      title={snapshot.id}
      sub={snapshot.label}
      states={["FROZEN", real ? "REAL DATA" : "SYNTHETIC"]}
      actions={<Link href={`/data/${snapshot.id}`} className="btn btn-sm btn-ghost" style={{ textDecoration: "none" }}><ExternalLink size={12} />Data</Link>}
    >
      <div className="readouts">
        <Readout label="Participants" value={snapshot.subjects.total} detail={real ? "real measured participants" : `${study.arm_counts.INTERVENTION} intervention · ${study.arm_counts.COMPARISON} comparison`} />
        <Readout label={real ? "Source class" : "Weeks"} value={real ? <span className="readout-small">{String(source?.classification ?? "—")}</span> : snapshot.subjects.weeks} detail={real ? String(source?.license?.id ?? "") : "2 CMJ trials / week"} />
        <Readout label="Rows" value={rowTotal.toLocaleString()} detail={`${Object.keys(rows).length} tables · ${health.valid_measurements} valid`} />
        {real ? (
          <Readout label="Valid observations" value={health.valid_measurements.toLocaleString()} detail={`${health.missing_observations} missing slots · never imputed`} />
        ) : (
          <>
            <Readout label="Force samples" value={rows.force_traces?.toLocaleString()} detail={`${snapshot.sample_rates.force_traces_hz} Hz audit traces`} />
            <Readout label="Tracking rows" value={rows.match_tracking?.toLocaleString()} detail={`${snapshot.sample_rates.match_tracking_hz} Hz · pose ${snapshot.pose_athletes.length} athletes`} />
          </>
        )}
      </div>
      <div className="block-toolbar small">
        {real ? (
          <>
            <span className="faint">source <span className="mono" style={{ color: "var(--text)" }}>{source?.id}</span></span>
            <span className="faint">snapshot files <span className="mono" style={{ color: "var(--text)" }}>{Object.keys(snapshot.checksums).length}</span></span>
          </>
        ) : (
          <>
            <span className="faint">seed <span className="mono" style={{ color: "var(--text)" }}>{snapshot.seed}</span></span>
            <span className="faint">generator <span className="mono" style={{ color: "var(--text)" }}>{snapshot.generator_version}</span></span>
            <span className="faint">schema <span className="mono" style={{ color: "var(--text)" }}>{snapshot.schema_version}</span></span>
            <span className="faint">cmj_trials sha256 <span className="mono" style={{ color: "var(--text)" }}>{shortChecksum(snapshot.checksums["cmj_trials.parquet"])}</span></span>
          </>
        )}
        <span className="grow" />
        <span className="faint">missing slots <span className="mono" style={{ color: "var(--warning)" }}>{health.missing_observations}</span> · provenance <span className="mono" style={{ color: "var(--text)" }}>{health.provenance_completeness.toFixed(1)}%</span></span>
        <Button size="sm" variant="ghost" onClick={() => inspect({ kind: "block", id: block.id })}>Inspect</Button>
      </div>
    </BlockFrame>
  );
}

export function CohortBlock({ block, index }: BlockProps) {
  const wb = useWorkbench();
  const real = wb.study.real_data;
  const excluded = Array.isArray(block.state.excluded_subject_ids) ? (block.state.excluded_subject_ids as string[]) : [];
  const cohort = useQuery({ queryKey: ["cohort", wb.studyId, excluded.join(",")], queryFn: () => scienceApi.cohort(excluded, wb.studyId), placeholderData: (previous) => previous });
  const toggle = (subjectId: string) => {
    const next = excluded.includes(subjectId) ? excluded.filter((id) => id !== subjectId) : [...excluded, subjectId].sort();
    wb.setBlocks((blocks) => updateState(blocks, block.id, { excluded_subject_ids: next }));
  };
  const reset = () => wb.setBlocks((blocks) => updateState(blocks, block.id, { excluded_subject_ids: [] }));
  const data = cohort.data;
  const status = data?.cohort.status ?? (excluded.length ? "DRAFT" : "FROZEN");
  return (
    <BlockFrame
      block={block}
      index={index}
      icon={<Users size={12} />}
      title={data?.cohort.name ?? "Study cohort"}
      sub={data?.cohort.id}
      states={[status]}
      actions={excluded.length > 0 ? <Button size="sm" variant="ghost" onClick={reset}><RotateCcw size={12} />Restore frozen cohort</Button> : undefined}
    >
      {cohort.isLoading && <Loading label={`Resolving cohort against ${wb.study.snapshot.id}`} />}
      {cohort.error && <ErrorBox error={cohort.error} onRetry={() => void cohort.refetch()} />}
      {data && (
        <>
          <div className="readouts">
            <Readout label="Participants (n)" value={data.n} detail={excluded.length ? `${excluded.length} excluded by scientist` : data.cohort.id} />
            <Readout label={real ? "Single arm" : "Intervention"} value={data.arm_counts.INTERVENTION} detail={real ? "no concurrent comparator" : "strength block w3–10"} />
            {!real && <Readout label="Comparison" value={data.arm_counts.COMPARISON} detail="usual care" />}
            <Readout label="Valid observations" value={data.trial_quality.valid} detail={`of ${data.trial_quality.expected} expected`} />
            <Readout label="Missing / excluded" value={`${data.trial_quality.missing} / ${data.trial_quality.excluded}`} detail={`missing: ${Object.entries(data.trial_quality.missing_by_arm).map(([arm, n]) => `${arm.slice(0, 3).toLowerCase()} ${n}`).join(" · ") || "none"}`} />
          </div>
          {(real ? (["INTERVENTION"] as Arm[]) : (["INTERVENTION", "COMPARISON"] as Arm[])).map((arm) => (
            <div key={arm}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                {real ? <span className="mono small">Single training arm</span> : <ArmLabel arm={arm} />}
                <span className="faint small">click a name to select the {real ? "participant" : "athlete"} · untick to exclude</span>
              </div>
              <div className="athlete-grid">
                {data.athletes.filter((athlete) => athlete.intervention_arm === arm).map((athlete) => (
                  <div key={athlete.subject_id} className={`athlete-cell ${excluded.includes(athlete.subject_id) ? "is-out" : ""} ${wb.selection.athleteId === athlete.subject_id ? "is-selected" : ""}`}>
                    <input type="checkbox" checked={!excluded.includes(athlete.subject_id)} onChange={() => toggle(athlete.subject_id)} aria-label={`Include ${athlete.display_id}`} />
                    <button type="button" className="mono" onClick={() => { wb.select({ athleteId: athlete.subject_id, trialId: null }); wb.inspect({ kind: "athlete", id: athlete.subject_id }); }}>{athlete.display_id}</button>
                    <span className="faint" style={{ marginLeft: "auto" }}>{athlete.position}</span>
                    {(athlete.missing_trials > 0 || athlete.excluded_trials > 0) && <span title={`${athlete.missing_trials} missing, ${athlete.excluded_trials} excluded trials`} style={{ color: "var(--warning)" }}>•</span>}
                  </div>
                ))}
              </div>
            </div>
          ))}
          <div className="block-cols">
            <div className="note"><Info size={12} /><span>Inclusion: {data.inclusion_criteria.join("; ")}. Exclusion: {data.exclusion_criteria.join("; ")}.</span></div>
            <div>
              {data.trial_quality.excluded_trials.map((trial) => (
                <div key={trial.trial_id} className="note bad"><State>EXCLUDED</State><span className="mono">{trial.trial_id}</span><span>{trial.reason}</span></div>
              ))}
              {excluded.length > 0 && <div className="note warn" style={{ marginTop: 4 }}><Info size={12} />Draft cohort: analyses executed on it are recorded as EXPLORATORY and never overwrite frozen runs.</div>}
            </div>
          </div>
        </>
      )}
    </BlockFrame>
  );
}
