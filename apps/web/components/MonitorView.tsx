"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowRight, CalendarRange, ChevronDown, Dumbbell, HeartPulse, Info, Moon, Search, ShieldAlert, Timer } from "lucide-react";
import { useMemo, useState } from "react";
import { scienceApi } from "@/lib/api";
import { AthleteChart } from "@/components/charts";
import { Button, EvidencePassport, ErrorState, KeyValue, LoadingState, MetricTile, Panel, SectionHeader, StatusBadge } from "@/components/ui";
import type { Evidence } from "@/lib/types";

const metricOptions = [
  { id: "MET-CMJ-IMPULSE", label: "Concentric impulse", unit: "N·s·kg⁻¹" },
  { id: "MET-CMJ-HEIGHT", label: "Jump height", unit: "cm" },
  { id: "MET-CMJ-BRAKING-DURATION", label: "Braking duration", unit: "s" },
  { id: "MET-CMJ-BRAKING-IMPULSE", label: "Braking impulse", unit: "N·s·kg⁻¹" },
  { id: "MET-CMJ-POWER", label: "Peak power", unit: "W·kg⁻¹" },
  { id: "MET-CMJ-DEPTH", label: "Countermovement depth", unit: "cm" },
  { id: "MET-CMJ-RSI-MOD", label: "RSI-mod", unit: "cm·s⁻¹" },
];

function numberValue(value: unknown, fallback = 0) {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

export function MonitorView({ onNavigate, initialSubjectId }: { onNavigate: (view: string, id?: string) => void; initialSubjectId?: string }) {
  const subjectsQuery = useQuery({ queryKey: ["subjects"], queryFn: scienceApi.subjects });
  const [subjectId, setSubjectId] = useState(initialSubjectId ?? "SUB-001");
  const [metricId, setMetricId] = useState("MET-CMJ-IMPULSE");
  const [selectedWeek, setSelectedWeek] = useState(10);
  const longitudinal = useQuery({ queryKey: ["longitudinal", subjectId, metricId], queryFn: () => scienceApi.longitudinal(subjectId, metricId), enabled: Boolean(subjectId) });
  const subjects = subjectsQuery.data ?? [];
  const subject = subjects.find((item) => item.subject_id === subjectId);
  const selected = longitudinal.data?.observations.find((item) => item.week === selectedWeek);
  const individual = longitudinal.data?.individual;

  const missingWeeks = useMemo(
    () => (longitudinal.data?.observations ?? []).filter((item) => item.missing_trials > 0 || item.excluded_trials > 0),
    [longitudinal.data],
  );

  const localEvidence = useMemo<Evidence | null>(() => {
    if (!selected || !subject || !longitudinal.data) return null;
    const metric = longitudinal.data.metric;
    return {
      id: `CTX-${subject.display_id}-W${selected.week}`,
      title: `${metric.label} · ${subject.display_id} week ${selected.week}`,
      kind: "CHANGE",
      metric_id: metricId,
      value: selected.value,
      unit: metric.unit,
      estimate: selected.value,
      uncertainty: selected.typical_error,
      uncertainty_label: "typical error of a change",
      effect_size: selected.z_score,
      population: `${subject.display_id} longitudinal context`,
      sample_size: selected.n_trials,
      protocol_id: "PROT-CMJ",
      dataset_snapshot_id: "DS-SYNTH-001",
      analysis_run_id: "RUN-0003",
      diagnostics: {
        rolling_sd: selected.rolling_sd,
        coefficient_of_variation: selected.coefficient_of_variation,
        percent_change: selected.percent_change_from_baseline,
        n_trials: selected.n_trials,
        missing_trials: selected.missing_trials,
        excluded_trials: selected.excluded_trials,
        quality_state: selected.quality_state,
      },
      quality: selected.value === null ? "WARNING" : "VALID",
      provenance: {
        algorithm: "descriptive athlete context",
        algorithm_version: "1.1.0",
        method: "weekly mean of valid trials with rolling baseline and typical-error context",
        source: "cmj_trials.parquet",
        snapshot_checksum: "recorded in DS-SYNTH-001 manifest",
      },
      interpretation: "Descriptive individual context; interpret against the baseline repeated-trial typical error rather than as a causal estimate.",
    };
  }, [longitudinal.data, metricId, selected, subject]);

  if (subjectsQuery.isLoading || longitudinal.isLoading) return <LoadingState label="Aligning athlete observations and context" />;
  if (subjectsQuery.error || longitudinal.error) {
    return <ErrorState message="Longitudinal observations could not be loaded from the local snapshot." onRetry={() => { void subjectsQuery.refetch(); void longitudinal.refetch(); }} />;
  }

  return (
    <div className="view-stack">
      <SectionHeader
        eyebrow="Monitor / longitudinal athlete analysis"
        title="Individual signal, in context"
        description="Aligned CMJ, training-load, match, and wellness observations for one athlete. Descriptive changes are benchmarked against repeated-trial typical error."
        actions={<StatusBadge tone="cyan">COHORT-001 · FROZEN</StatusBadge>}
      />
      <Panel className="athlete-selector" eyebrow="Subject selection" title="Choose an athlete" action={<span className="subtle">{subjects.length} synthetic subjects · arm and position retained</span>}>
        <div className="selector-row">
          <div className="select-wrap">
            <Search size={14} />
            <select value={subjectId} onChange={(event) => setSubjectId(event.target.value)}>
              {subjects.map((item) => (
                <option key={item.subject_id} value={item.subject_id}>
                  {item.display_id} · {item.position} · {item.intervention_arm === "INTERVENTION" ? "intervention" : "comparison"}
                </option>
              ))}
            </select>
            <ChevronDown size={14} />
          </div>
          {subject && (
            <div className="subject-summary">
              <div className="subject-avatar">{subject.display_id.slice(-3)}</div>
              <div>
                <strong>{subject.display_id}</strong>
                <span>{subject.position} · age {subject.age} · {subject.training_age_years} y training age · {subject.body_mass_kg.toFixed(1)} kg</span>
              </div>
              <StatusBadge tone={subject.intervention_arm === "INTERVENTION" ? "cyan" : "warn"}>{subject.intervention_arm}</StatusBadge>
            </div>
          )}
        </div>
      </Panel>
      <div className="monitor-toolbar">
        <div className="metric-tabs">
          {metricOptions.map((metric) => (
            <button key={metric.id} className={metricId === metric.id ? "active" : ""} onClick={() => setMetricId(metric.id)}>
              <span>{metric.label}</span>
              <small>{metric.unit}</small>
            </button>
          ))}
        </div>
        <div className="monitor-context">
          <span className="context-chip"><CalendarRange size={13} /> 16 weeks</span>
          <span className="context-chip"><Timer size={13} /> 2 CMJ trials / week</span>
          <span className="context-chip"><ShieldAlert size={13} /> {missingWeeks.length} weeks carry missing or excluded trials</span>
        </div>
      </div>
      {subject && longitudinal.data && (
        <>
          <div className="metric-grid monitor-metrics">
            <MetricTile
              label="Week observation"
              value={selected?.value?.toFixed(3) ?? "—"}
              unit={longitudinal.data.metric.unit}
              detail={`week ${selectedWeek} · ${selected?.n_trials ?? 0}/${selected?.expected_trials ?? 2} valid trials`}
              state={selected?.quality_state === "VALID" ? "VALID" : "WARNING"}
            />
            <MetricTile label="Change from baseline" value={selected?.percent_change_from_baseline?.toFixed(1) ?? "—"} unit="%" detail="weeks 1–2 reference" state="EXPLORATORY" />
            <MetricTile label="z-score" value={selected?.z_score?.toFixed(2) ?? "—"} unit="SD" detail="vs rolling baseline" state="EXPLORATORY" />
            <MetricTile label="Typical error" value={longitudinal.data.typical_error?.toFixed(3) ?? "—"} unit={longitudinal.data.metric.unit} detail="repeated-trial context" state="VALID" />
          </div>
          <div className="monitor-grid">
            <Panel
              className="athlete-signal"
              eyebrow="Performance signal"
              title={`${longitudinal.data.metric.label} / ${subject.display_id}`}
              action={
                <div className="chart-legend">
                  <span><i className="legend-dot cyan" />weekly mean</span>
                  <span><i className="legend-line amber" />rolling baseline</span>
                  <span className="mono subtle">±1 SD band</span>
                </div>
              }
            >
              <AthleteChart data={longitudinal.data.observations} unit={longitudinal.data.metric.unit} />
              <div className="annotation-strip">
                <span className="annotation baseline">Baseline w1–2</span>
                {subject.intervention_arm === "INTERVENTION" && <span className="annotation block">Strength block w3–10</span>}
                <span className="annotation load">Load spike w11</span>
                <span className="annotation recovery">Transient w12</span>
              </div>
            </Panel>
            <Panel
              className="context-panel"
              eyebrow="Selected observation"
              title={`Week ${selectedWeek} / ${selected?.phase ?? "—"}`}
              action={<StatusBadge tone={selected?.quality_state === "VALID" ? "good" : "warn"}>{selected?.quality_state ?? "—"}</StatusBadge>}
            >
              {selected && (
                <>
                  <div className="observation-value">
                    <strong>{selected.value?.toFixed(3) ?? "—"}</strong>
                    <span>{longitudinal.data.metric.unit}</span>
                    <small>mean of {selected.n_trials} valid trial observation{selected.n_trials === 1 ? "" : "s"}</small>
                  </div>
                  <div className="context-key-grid">
                    <KeyValue label="Rolling mean" value={selected.rolling_mean?.toFixed(3) ?? "—"} />
                    <KeyValue label="Rolling SD" value={selected.rolling_sd?.toFixed(3) ?? "—"} />
                    <KeyValue label="Typical error" value={selected.typical_error?.toFixed(3) ?? "—"} />
                    <KeyValue label="Within-athlete CV" value={selected.coefficient_of_variation === null ? "—" : `${selected.coefficient_of_variation.toFixed(1)} %`} />
                    <KeyValue label="Missing trials" value={String(selected.missing_trials)} />
                    <KeyValue label="Excluded trials" value={String(selected.excluded_trials)} />
                  </div>
                  <div className="context-block">
                    <div className="context-block-title"><Dumbbell size={14} />Training load</div>
                    <div className="context-load">
                      <span>{String(selected.load?.phase ?? "—")}</span>
                      <strong>{numberValue(selected.load?.external_load_au).toFixed(0)} <small>AU</small></strong>
                      <span>{numberValue(selected.load?.session_rpe).toFixed(1)} RPE</span>
                      <span>{numberValue(selected.load?.match_minutes).toFixed(0)} min match</span>
                    </div>
                  </div>
                  <div className="context-block">
                    <div className="context-block-title"><HeartPulse size={14} />Wellness context</div>
                    <div className="wellness-row">
                      <span><Moon size={12} /> sleep</span><strong>{numberValue(selected.wellness?.sleep_hours).toFixed(1)} h</strong>
                      <span>soreness {numberValue(selected.wellness?.soreness_0_10).toFixed(1)}</span>
                      <span>fatigue {numberValue(selected.wellness?.fatigue_0_10).toFixed(1)}</span>
                      <span>readiness {numberValue(selected.wellness?.readiness_0_10).toFixed(1)}</span>
                    </div>
                  </div>
                </>
              )}
            </Panel>
          </div>
          <div className="monitor-grid">
            <Panel
              eyebrow="Individual change context"
              title={`${individual?.method ?? "Baseline versus post-block"}`}
              action={<StatusBadge tone="purple">METH-IND · RUN-0003</StatusBadge>}
            >
              {individual && (
                <>
                  <div className="individual-change-grid">
                    <div><span>Baseline mean</span><strong>{individual.baseline_mean?.toFixed(3) ?? "—"} <small>{longitudinal.data.metric.unit}</small></strong><em>weeks {individual.baseline_weeks.join("–")}</em></div>
                    <div><span>Post-block mean</span><strong>{individual.post_mean?.toFixed(3) ?? "—"} <small>{longitudinal.data.metric.unit}</small></strong><em>weeks {individual.post_weeks.join("–")}</em></div>
                    <div><span>Observed change</span><strong>{individual.change === null ? "—" : `${individual.change > 0 ? "+" : ""}${individual.change.toFixed(3)}`} <small>{longitudinal.data.metric.unit}</small></strong><em>{individual.percent_change === null ? "—" : `${individual.percent_change.toFixed(1)} %`}</em></div>
                    <div><span>Standardized change</span><strong>{individual.standardized_change?.toFixed(2) ?? "—"} <small>SD</small></strong><em>cohort change SD {individual.cohort_change_sd.toFixed(3)}</em></div>
                  </div>
                  <div className={`individual-verdict ${individual.exceeds_typical_error ? "above" : "within"}`}>
                    <Info size={14} />
                    <span>
                      {individual.exceeds_typical_error === null
                        ? "Change context unavailable for this athlete."
                        : individual.exceeds_typical_error
                          ? `Change exceeds the typical error of a change (${individual.typical_error.toFixed(3)} ${longitudinal.data.metric.unit}); still descriptive, not a causal individual inference.`
                          : `Change is within the typical error of a change (${individual.typical_error.toFixed(3)} ${longitudinal.data.metric.unit}) and should not be interpreted as a real individual response.`}
                    </span>
                  </div>
                </>
              )}
            </Panel>
            <Panel eyebrow="Data quality" title="Missingness and exclusions" action={<StatusBadge tone={missingWeeks.length ? "warn" : "good"}>{missingWeeks.length ? "WARNING" : "VALID"}</StatusBadge>}>
              {missingWeeks.length === 0 ? (
                <div className="empty-state"><ShieldAlert size={18} /><strong>Complete weekly coverage</strong><span>All expected trials were captured and passed the QC rule.</span></div>
              ) : (
                <div className="quality-list">
                  {missingWeeks.map((item) => (
                    <div className="quality-row" key={item.week}>
                      <span className="mono">W{String(item.week).padStart(2, "0")}</span>
                      <span>{item.missing_trials > 0 ? `${item.missing_trials} trial not captured` : `${item.excluded_trials} trial excluded`}</span>
                      <StatusBadge tone="warn">{item.missing_trials > 0 ? "MISSING" : "EXCLUDED"}</StatusBadge>
                    </div>
                  ))}
                </div>
              )}
              <div className="formula-note"><Info size={14} /><span>Missing and excluded trials remain visible; weekly means use valid trials only.</span></div>
            </Panel>
          </div>
          <Panel eyebrow="Observation ledger" title="Weekly alignment" action={<span className="subtle">click a row to inspect · raw values remain inspectable</span>}>
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr><th>Week</th><th>Phase</th><th>Observed</th><th>Trials</th><th>Rolling mean</th><th>SD</th><th>z-score</th><th>Change</th><th>Load</th><th>State</th></tr>
                </thead>
                <tbody>
                  {longitudinal.data.observations.map((observation) => (
                    <tr key={observation.week} className={selectedWeek === observation.week ? "selected" : ""} onClick={() => setSelectedWeek(observation.week)}>
                      <td className="mono">{String(observation.week).padStart(2, "0")}</td>
                      <td><span className={`phase-label ${observation.phase === "Strength block" ? "phase-block" : observation.phase === "Match week" ? "phase-match" : ""}`}>{observation.phase}</span></td>
                      <td className="mono strong-cell">{observation.value?.toFixed(3) ?? "—"}</td>
                      <td className="mono">{observation.n_trials}/{observation.expected_trials}</td>
                      <td className="mono">{observation.rolling_mean?.toFixed(3) ?? "—"}</td>
                      <td className="mono">{observation.rolling_sd?.toFixed(3) ?? "—"}</td>
                      <td className="mono">{observation.z_score?.toFixed(2) ?? "—"}</td>
                      <td className="mono">{observation.percent_change_from_baseline?.toFixed(1) ?? "—"}%</td>
                      <td className="mono">{numberValue(observation.load?.external_load_au).toFixed(0)} AU</td>
                      <td><StatusBadge tone={observation.quality_state === "VALID" ? "good" : "warn"}>{observation.quality_state}</StatusBadge></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
          {localEvidence && (
            <Panel
              eyebrow="Evidence passport"
              title="Point-level provenance"
              action={<Button size="sm" variant="ghost" onClick={() => onNavigate("runs", "RUN-0003")}>Open source run <ArrowRight size={13} /></Button>}
            >
              <EvidencePassport evidence={localEvidence} onNavigate={onNavigate} lineageId={subjectId} />
            </Panel>
          )}
        </>
      )}
      <div className="method-note">
        <Info size={14} />
        <span>Change is calculated from valid observations only. Rolling mean, SD, z-score, percentage change, CV, and typical error are descriptive; no readiness score is inferred.</span>
      </div>
    </div>
  );
}
