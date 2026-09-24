"use client";

import { useQuery } from "@tanstack/react-query";
import { Activity, AlertTriangle, ArrowRight, Crosshair, Download, Filter, Gauge, Layers3, Ruler, ScanLine, Sigma, SlidersHorizontal } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { scienceApi } from "@/lib/api";
import { ForceTraceChart } from "@/components/charts";
import { Button, EvidencePassport, KeyValue, LoadingState, MetricTile, Panel, SectionHeader, StatusBadge } from "@/components/ui";
import type { Evidence, Metric } from "@/lib/types";

const metricMap = {
  jump_height_cm: { label: "Jump height", unit: "cm", method: "g·t²/8 flight time", metricId: "MET-CMJ-HEIGHT", icon: Ruler },
  concentric_impulse_n_s_kg: { label: "Concentric impulse", unit: "N·s·kg⁻¹", method: "net GRF integration", metricId: "MET-CMJ-IMPULSE", icon: Sigma },
  eccentric_braking_impulse_n_s_kg: { label: "Braking impulse", unit: "N·s·kg⁻¹", method: "eccentric phase integration", metricId: "MET-CMJ-BRAKING-IMPULSE", icon: Gauge },
  eccentric_braking_duration_s: { label: "Braking duration", unit: "s", method: "phase boundary difference", metricId: "MET-CMJ-BRAKING-DURATION", icon: SlidersHorizontal },
  countermovement_depth_cm: { label: "Countermovement depth", unit: "cm", method: "integrated displacement", metricId: "MET-CMJ-DEPTH", icon: Layers3 },
  peak_force_n: { label: "Peak force", unit: "N", method: "maximum vertical GRF", metricId: "MET-CMJ-POWER", icon: Activity },
  peak_power_w_kg: { label: "Peak power", unit: "W·kg⁻¹", method: "force × velocity / mass", metricId: "MET-CMJ-POWER", icon: Crosshair },
  rsi_mod: { label: "RSI-mod", unit: "cm·s⁻¹", method: "jump height / propulsion time", metricId: "MET-CMJ-RSI-MOD", icon: SlidersHorizontal },
} as const;

type MetricKey = keyof typeof metricMap;

export function ForceLabView({ onNavigate }: { onNavigate: (view: string, id?: string) => void }) {
  const subjectsQuery = useQuery({ queryKey: ["subjects"], queryFn: scienceApi.subjects });
  const registryQuery = useQuery({ queryKey: ["registry"], queryFn: scienceApi.registry });
  const [subject, setSubject] = useState("SUB-001");
  const [week, setWeek] = useState(10);
  const [trialId, setTrialId] = useState("");
  const [metricKey, setMetricKey] = useState<MetricKey>("concentric_impulse_n_s_kg");

  const subjects = subjectsQuery.data ?? [];
  const trialsQuery = useQuery({ queryKey: ["force-trials", subject, week], queryFn: () => scienceApi.forceTrials(`?subject_id=${subject}&week=${week}`) });
  const trials = useMemo(() => trialsQuery.data ?? [], [trialsQuery.data]);
  useEffect(() => {
    if (trials.length > 0 && !trials.some((item) => item.trial_id === trialId)) setTrialId(trials[0].trial_id);
    if (trials.length === 0) setTrialId("");
  }, [trialId, trials]);
  const detailQuery = useQuery({ queryKey: ["force-trial", trialId], queryFn: () => scienceApi.forceTrial(trialId), enabled: Boolean(trialId) });
  const detail = detailQuery.data;
  const trial = detail?.trial;
  const metric = metricMap[metricKey];
  const subjectRecord = subjects.find((item) => item.subject_id === subject);
  const registryMetric: Metric | undefined = registryQuery.data?.metrics.find((item) => item.id === metric.metricId);

  const exportTrace = useCallback(() => {
    if (!detail?.trace_available || detail.trace.length === 0) return;
    const header = "trial_id,time_s,force_n,body_weight_n,phase";
    const rows = detail.trace.map((point) => [point.trial_id, point.time_s, point.force_n, point.body_weight_n, point.phase].join(","));
    const blob = new Blob([`${header}\n${rows.join("\n")}\n`], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${detail.trial.trial_id}-force-trace.csv`;
    anchor.click();
    URL.revokeObjectURL(url);
  }, [detail]);

  const evidence = useMemo<Evidence | null>(() => {
    if (!trial || !subjectRecord) return null;
    const value = trial[metricKey];
    return {
      id: `MEAS-${trial.trial_id}-${metricKey}`,
      title: `${metric.label} / ${trial.display_id} week ${trial.week}`,
      kind: "DESCRIPTIVE",
      metric_id: metric.metricId,
      value,
      unit: metric.unit,
      estimate: value,
      uncertainty: null,
      uncertainty_label: "single trial measurement",
      effect_size: null,
      population: `${trial.display_id} · ${subjectRecord.position} · ${trial.intervention_arm.toLowerCase()} arm`,
      sample_size: 1,
      protocol_id: "PROT-CMJ",
      dataset_snapshot_id: "DS-SYNTH-001",
      analysis_run_id: "RUN-0001",
      diagnostics: { quality_state: trial.quality_state, exclusion_reason: trial.exclusion_reason, sample_rate_hz: 1000, trial_number: trial.trial_number },
      quality: trial.quality_state === "EXCLUDED" ? "WARNING" : "VALID",
      provenance: {
        algorithm: registryMetric?.algorithm ?? "cmj-metrics",
        algorithm_version: registryMetric?.version ?? "1.0.0",
        source: trial.trace_path,
        snapshot_checksum: "recorded in DS-SYNTH-001 manifest",
        method: registryMetric?.method ?? metric.method,
      },
      interpretation: `Measured on ${trial.trial_id} by ${registryMetric?.method ?? metric.method}. ${trial.quality_state === "EXCLUDED" ? "Flagged by the deterministic QC rule and excluded from primary inference." : "Included in the primary analysis under the frozen quality rule."}`,
    };
  }, [metric, metricKey, registryMetric, subjectRecord, trial]);

  if (subjectsQuery.isLoading || trialsQuery.isLoading) return <LoadingState label="Loading force-plate trace and derived metrics" />;

  return (
    <div className="view-stack">
      <SectionHeader
        eyebrow="Laboratory / ForceLab"
        title="Force-time evidence"
        description="Inspect the raw synthetic vertical GRF signal, phase boundaries, and metric extraction contract for one CMJ trial."
        actions={
          <>
            <StatusBadge tone="cyan">1000 Hz SYNTHETIC</StatusBadge>
            <Button size="sm" variant="ghost" onClick={exportTrace} disabled={!detail?.trace_available}>
              <Download size={14} /> Export trace CSV
            </Button>
          </>
        }
      />
      <Panel
        className="trial-selector"
        eyebrow="Trial browser"
        title="Select a measurement event"
        action={<span className="subtle">{subjects.length} athletes · flagged trials remain discoverable</span>}
      >
        <div className="trial-controls">
          <div className="select-wrap">
            <Filter size={14} />
            <select value={subject} onChange={(event) => setSubject(event.target.value)}>
              {subjects.map((item) => (
                <option key={item.subject_id} value={item.subject_id}>
                  {item.display_id} · {item.position} · {item.intervention_arm === "INTERVENTION" ? "INT" : "CMP"}
                </option>
              ))}
            </select>
          </div>
          <div className="select-wrap">
            <select value={week} onChange={(event) => setWeek(Number(event.target.value))}>
              {Array.from({ length: 16 }, (_, index) => (
                <option key={index + 1} value={index + 1}>Week {String(index + 1).padStart(2, "0")}</option>
              ))}
            </select>
          </div>
          <div className="trial-count">
            <span>{trials.length} trial summaries</span>
            <span className="mono">{trialId || "—"}</span>
          </div>
        </div>
        <div className="trial-pills">
          {trials.length === 0 && <span className="subtle">No trials recorded for this athlete and week.</span>}
          {trials.map((item) => (
            <button
              key={item.trial_id}
              className={`trial-pill ${trialId === item.trial_id ? "active" : ""} ${item.quality_state === "EXCLUDED" ? "excluded" : ""}`}
              onClick={() => setTrialId(item.trial_id)}
            >
              <span className="mono">T{item.trial_number}</span>
              <StatusBadge tone={item.quality_state === "EXCLUDED" ? "bad" : "good"}>{item.quality_state}</StatusBadge>
            </button>
          ))}
        </div>
      </Panel>
      {trial && detail ? (
        <>
          <div className="force-summary-strip">
            <div><span>Trial</span><strong className="mono">{trial.trial_id}</strong></div>
            <div><span>Session</span><strong>{trial.session_id}</strong></div>
            <div><span>Body mass</span><strong>{trial.body_mass_kg.toFixed(1)} <small>kg</small></strong></div>
            <div><span>Arm</span><StatusBadge tone={trial.intervention_arm === "INTERVENTION" ? "cyan" : "warn"}>{trial.intervention_arm}</StatusBadge></div>
            <div><span>Quality</span><StatusBadge tone={trial.quality_state === "EXCLUDED" ? "bad" : "good"}>{trial.quality_state}</StatusBadge></div>
          </div>
          {trial.quality_state === "EXCLUDED" && (
            <div className="qc-warning">
              <AlertTriangle size={16} />
              <div><strong>Excluded from primary analysis</strong><span>{trial.exclusion_reason}. The signal remains available for audit and method development.</span></div>
              <StatusBadge tone="bad">QC FLAG</StatusBadge>
            </div>
          )}
          <div className="force-main-grid">
            <Panel
              className="force-plot-panel"
              eyebrow="Raw measurement / 1000 Hz"
              title="Vertical ground reaction force"
              action={<div className="chart-legend"><span><i className="legend-line cyan" />GRF</span><span><i className="legend-line gray" />body weight</span><span><i className="legend-area cyan" />phases</span></div>}
            >
              {detail.trace_available ? (
                <ForceTraceChart trace={detail.trace} boundaries={detail.boundaries} />
              ) : (
                <div className="empty-state trace-unavailable">
                  <ScanLine size={20} />
                  <strong>Raw signal not retained for this summary</strong>
                  <span>The trial metrics and phase boundaries remain inspectable. 1000 Hz traces are retained on baseline, mid-block, post and follow-up audit weeks.</span>
                </div>
              )}
              <div className="phase-legend">
                <Phase color="quiet" label="Quiet standing" />
                <Phase color="unweight" label="Unweighting" />
                <Phase color="braking" label="Braking" />
                <Phase color="propulsion" label="Propulsion" />
                <Phase color="flight" label="Flight" />
                <Phase color="landing" label="Landing" />
              </div>
            </Panel>
            <Panel
              className="phase-panel"
              eyebrow="Phase interpretation"
              title="Detected event structure"
              action={<StatusBadge tone="good">DETERMINISTIC</StatusBadge>}
            >
              <div className="phase-stack">
                {[
                  { key: "movement_onset", label: "Movement onset", value: detail.boundaries.movement_onset, className: "quiet" },
                  { key: "unweighting_end", label: "Unweighting end", value: detail.boundaries.unweighting_end, className: "unweight" },
                  { key: "braking_end", label: "Braking → propulsion", value: detail.boundaries.braking_end, className: "braking" },
                  { key: "takeoff", label: "Takeoff", value: detail.boundaries.takeoff, className: "propulsion" },
                  { key: "landing", label: "Landing", value: detail.boundaries.landing, className: "landing" },
                ].map((phase, index) => (
                  <div className="phase-row" key={phase.key}>
                    <span className={`phase-marker ${phase.className}`} />
                    <span>
                      <strong>{phase.label}</strong>
                      <small>{index === 0 ? "quiet → movement" : index === 4 ? "flight → landing" : "phase boundary"}</small>
                    </span>
                    <strong className="mono">{phase.value?.toFixed(3)} s</strong>
                  </div>
                ))}
              </div>
              <div className="phase-method">
                <ScanLine size={14} />
                <span>Boundary detection: deterministic phase template<br /><strong>{String(detail.method.algorithm)}@{String(detail.method.algorithm_version)}</strong></span>
              </div>
            </Panel>
          </div>
          <div className="metric-grid force-metrics">
            {(["concentric_impulse_n_s_kg", "eccentric_braking_duration_s", "jump_height_cm", "peak_power_w_kg"] as MetricKey[]).map((key) => (
              <MetricTile
                key={key}
                label={metricMap[key].label}
                value={trial[key].toFixed(3)}
                unit={metricMap[key].unit}
                detail={key === metricKey ? "selected metric" : "click to inspect"}
                state={trial.quality_state === "EXCLUDED" ? "WARNING" : "VALID"}
                onClick={() => setMetricKey(key)}
              />
            ))}
          </div>
          <div className="force-bottom-grid">
            <Panel eyebrow="Derived metrics" title="Metric extraction results" action={<span className="subtle">click any value for its passport</span>}>
              <div className="derived-metric-grid">
                {(Object.keys(metricMap) as MetricKey[]).map((key) => (
                  <button key={key} className={`derived-metric ${key === metricKey ? "active" : ""}`} onClick={() => setMetricKey(key)}>
                    <span>{metricMap[key].label}</span>
                    <strong>{trial[key].toFixed(3)} <small>{metricMap[key].unit}</small></strong>
                    <em>{metricMap[key].method}</em>
                  </button>
                ))}
              </div>
            </Panel>
            {evidence && (
              <Panel
                eyebrow="Evidence passport"
                title="Selected derived result"
                action={<StatusBadge tone={evidence.quality === "VALID" ? "good" : "warn"}>{evidence.quality}</StatusBadge>}
              >
                <EvidencePassport evidence={evidence} onNavigate={onNavigate} lineageId={trial.trial_id} />
              </Panel>
            )}
          </div>
          <div className="method-footer">
            <KeyValue label="Source" value="force_traces.parquet" mono />
            <KeyValue label="Snapshot" value="DS-SYNTH-001" mono />
            <KeyValue label="Protocol" value="PROT-CMJ · bilateral countermovement jump" />
            <KeyValue label="Reproducibility" value="deterministic / seed 20260924" />
            <Button size="sm" variant="ghost" onClick={() => onNavigate("lineage", trial.trial_id)}>View measurement lineage <ArrowRight size={13} /></Button>
          </div>
        </>
      ) : (
        <div className="empty-state"><Ruler size={20} /><strong>Select a trial</strong><span>Choose a valid or explicitly flagged trial to load its force trace.</span></div>
      )}
    </div>
  );
}

function Phase({ color, label }: { color: string; label: string }) {
  return <span><i className={`phase-swatch ${color}`} />{label}</span>;
}
