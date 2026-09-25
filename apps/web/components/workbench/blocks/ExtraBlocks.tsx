"use client";

import { useQuery } from "@tanstack/react-query";
import { Activity, Boxes, Info, MapPin, Table2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { WorkbenchBlock } from "@/lib/types";
import { scienceApi } from "@/lib/api";
import { formatSig, formatSignedSig, metricOption, primaryResult } from "@/lib/scientific";
import { updateState } from "@/lib/workbench";
import { ArmLabel, Button, ErrorBox, KV, Loading, Readout, State } from "@/components/ui";
import { ModelScenarioChart } from "@/components/charts";
import { BlockFrame } from "../Block";
import { useWorkbench } from "../context";
import { useRuns, useSubjects } from "../data";

type Scenario = "MAINTAIN" | "TAPER" | "OVERLOAD" | "CUSTOM";
const SCENARIO_FACTORS: Record<Exclude<Scenario, "CUSTOM">, number> = { MAINTAIN: 1, TAPER: 0.6, OVERLOAD: 1.4 };

export function scenarioLoads(base: number, scenario: Scenario, weeks: number, custom?: number[]): number[] {
  if (scenario === "CUSTOM" && custom?.length) return custom.slice(0, weeks);
  const factor = scenario === "CUSTOM" ? 1 : SCENARIO_FACTORS[scenario];
  return Array.from({ length: weeks }, () => Math.round(base * factor));
}

function useDebounced<T>(value: T, delay = 250): T {
  const [current, setCurrent] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setCurrent(value), delay);
    return () => window.clearTimeout(timer);
  }, [delay, value]);
  return current;
}

export function ModelBlock({ block, index }: { block: WorkbenchBlock; index: number }) {
  const wb = useWorkbench();
  const model = useQuery({ queryKey: ["training-model"], queryFn: scienceApi.trainingModel });
  const scenario = (block.state.scenario as Scenario) ?? "MAINTAIN";
  const weeks = Number(block.state.scenario_weeks ?? 8);
  const history = model.data?.run.output.weekly_load_au ?? [];
  const base = history.length ? history.slice(-4).reduce((sum, value) => sum + value, 0) / Math.min(4, history.length) : 0;
  const custom = Array.isArray(block.state.scenario_loads) ? (block.state.scenario_loads as number[]) : undefined;
  const loads = useMemo(() => scenarioLoads(base, scenario, weeks, custom), [base, custom, scenario, weeks]);
  const debounced = useDebounced(loads);
  const simulation = useQuery({ queryKey: ["scenario", debounced.join(",")], queryFn: () => scienceApi.scenario(debounced), enabled: debounced.length > 0 && base > 0, placeholderData: (previous) => previous });
  const set = (patch: Record<string, unknown>) => wb.setBlocks((blocks) => updateState(blocks, block.id, patch));
  const run = model.data?.run;
  const spec = model.data?.spec;
  const unit = run?.output.unit ?? "N·s·kg⁻¹";
  return (
    <BlockFrame block={block} index={index} icon={<Boxes size={12} />} title={spec?.name ?? block.title} sub={spec ? `${spec.id} v${spec.version} · ${run?.id}` : undefined} states={[{ label: "MECHANISTIC PROTOTYPE", tone: "tone-warning" }, "SYNTHETIC"]} removable>
      {model.isLoading && <Loading label="Loading fitted model run" />}
      {model.error && <ErrorBox error={model.error} />}
      {run && spec && (
        <>
          <div className="block-split">
            <div className="chart-frame">
              <div className="chart-cap"><strong>Concentric impulse, group mean</strong><span className="mono">{unit}</span><span>· observed vs fitted · dashed = forward simulation under the scenario load</span></div>
              {simulation.data ? <ModelScenarioChart states={simulation.data.states} observedWeeks={run.output.observed_weeks} observed={run.output.observed_performance} unit={unit} /> : <Loading label="Simulating scenario" />}
            </div>
            <div style={{ display: "grid", gap: 10, alignContent: "start" }}>
              <div className="mono small" style={{ color: "var(--text-2)", lineHeight: 1.7, border: "1px solid var(--line)", padding: "6px 9px", borderRadius: 3 }}>
                fitness<sub>t</sub> = e<sup>−1/τf</sup>·fitness<sub>t−1</sub> + g·ℓ<sub>t</sub><br />
                fatigue<sub>t</sub> = e<sup>−1/τg</sup>·fatigue<sub>t−1</sub> + ℓ<sub>t</sub><br />
                perf<sub>t</sub> ∝ fitness<sub>t</sub> − k·fatigue<sub>t</sub>
              </div>
              <KV rows={[
                ["Input load", "cohort mean weekly training impulse (AU), standardised"],
                ["Observed", "weekly mean first-trial concentric impulse"],
                ["τ fitness", `${run.parameters.tau_fitness_weeks} weeks`, "mono"],
                ["τ fatigue", `${run.parameters.fatigue_tau_weeks} weeks`, "mono"],
                ["Fatigue penalty k", String(run.parameters.fatigue_penalty), "mono"],
                ["Solver", "deterministic grid search (120 combinations)"],
                ["Fit RMSE", `${formatSig(run.output.fit_rmse_outcome_units, 3)} ${unit} (${formatSig(run.output.fit_rmse_standardized, 3)} standardised)`, "mono"],
                ["Fit status", run.diagnostics.fit_status, "mono"],
              ]} />
            </div>
          </div>
          <div className={`note ${run.output.fit_rmse_standardized >= 1 ? "warn" : ""}`}>
            <Info size={12} />
            <span>
              Fit quality (computed): standardised RMSE {formatSig(run.output.fit_rmse_standardized, 3)}.{" "}
              {run.output.fit_rmse_standardized >= 1
                ? "A value ≥ 1 means the fitted response explains the weekly group-mean CMJ series no better than its mean; treat scenario output as a demonstration of the model mechanics, not as a forecast."
                : "Below 1: the fitted response tracks part of the weekly variation."}
            </span>
          </div>
          <div className="block-toolbar">
            <div className="field"><span>Scenario, weeks 17–{16 + weeks}</span>
              <div className="seg" role="group" aria-label="Load scenario">
                {(["MAINTAIN", "TAPER", "OVERLOAD", "CUSTOM"] as Scenario[]).map((value) => (
                  <button key={value} type="button" aria-pressed={scenario === value} onClick={() => set({ scenario: value, scenario_loads: value === "CUSTOM" ? loads : undefined })}>
                    {value === "MAINTAIN" ? "Maintain" : value === "TAPER" ? "Taper −40%" : value === "OVERLOAD" ? "Overload +40%" : "Custom"}
                  </button>
                ))}
              </div>
            </div>
            <span className="faint small">reference = mean of weeks 13–16 ({base.toFixed(0)} AU)</span>
            <span className="grow" />
            {simulation.data && <span className="mono faint small">{simulation.data.scenario_id} · not persisted · deterministic</span>}
          </div>
          <div className="slider-row" aria-label="Scenario weekly load">
            {loads.map((value, week) => (
              <label key={week}>
                <strong className="num">{value}</strong>
                <input type="range" min={0} max={800} step={10} value={value} aria-label={`Week ${17 + week} load (AU)`} onChange={(event) => { const next = [...loads]; next[week] = Number(event.target.value); set({ scenario: "CUSTOM", scenario_loads: next }); }} />
                w{17 + week}
              </label>
            ))}
          </div>
          {simulation.data && (
            <div className="readouts">
              <Readout label="End of observed (w16)" value={formatSig(simulation.data.summary.end_of_history_performance, 4)} unit={unit} />
              <Readout label={`Scenario end (w${16 + weeks})`} value={formatSig(simulation.data.summary.scenario_final_performance, 4)} unit={unit} detail={`Δ ${formatSignedSig((simulation.data.summary.scenario_final_performance ?? 0) - simulation.data.summary.end_of_history_performance, 3)} ${unit}`} />
              <Readout label="Scenario peak" value={formatSig(simulation.data.summary.scenario_peak_performance, 4)} unit={unit} detail={`week ${simulation.data.summary.scenario_peak_week}`} />
              <Readout label="Mean scenario load" value={formatSig(simulation.data.summary.scenario_mean_load_au, 3)} unit="AU" />
            </div>
          )}
          {simulation.error && <ErrorBox error={simulation.error} />}
          <div className="block-cols">
            <ul style={{ margin: 0, paddingLeft: 16, color: "var(--text-2)", fontSize: 12 }}>
              {(simulation.data?.limitations ?? run.diagnostics.limitations).map((item) => <li key={item}>{item}</li>)}
            </ul>
            <div>
              <div className="faint small" style={{ marginBottom: 4 }}>Other model classes — not implemented in this MVP</div>
              <div className="roadmap">{spec.roadmap.map((item) => <span key={item.capability}>{item.capability} · UNAVAILABLE</span>)}</div>
            </div>
          </div>
        </>
      )}
    </BlockFrame>
  );
}

export function MatchEventBlock({ block, index }: { block: WorkbenchBlock; index: number }) {
  const wb = useWorkbench();
  const matchId = String(block.state.match_id ?? "MATCH-SYNTH-001");
  const match = useQuery({ queryKey: ["match", matchId], queryFn: () => scienceApi.match(matchId) });
  return (
    <BlockFrame block={block} index={index} icon={<MapPin size={12} />} title={block.title} sub={match.data ? `${matchId} · ${match.data.sample_rate_hz} Hz · ${match.data.frame_count} frames · ${match.data.duration_s.toFixed(0)} s` : matchId} states={["SYNTHETIC"]} removable
      actions={<Button size="sm" onClick={() => wb.openViewer({ kind: "match" })}><MapPin size={12} />Open spatial + biomechanical view</Button>}
    >
      {match.isLoading && <Loading label="Loading match segment" />}
      {match.error && <ErrorBox error={match.error} />}
      {match.data && (
        <table className="table">
          <thead><tr><th>Event</th><th>Type</th><th>Interval</th><th>Athlete</th><th>Pose</th><th /></tr></thead>
          <tbody>
            {match.data.events.map((event) => {
              const pose = match.data.pose_athletes.includes(event.athlete_id);
              return (
                <tr key={event.event_id} className={wb.selection.matchEventId === event.event_id ? "is-selected" : ""}>
                  <td className="mono">{event.event_id} <span style={{ color: "var(--text)" }}>{event.label}</span></td>
                  <td className="mono faint">{event.event_type}</td>
                  <td className="mono">{event.start_s}–{event.end_s} s</td>
                  <td className="mono">{event.athlete_id}</td>
                  <td><State plain>{pose ? "VALID" : "UNAVAILABLE"}</State></td>
                  <td className="r"><Button size="sm" variant="primary" onClick={() => { wb.select({ matchEventId: event.event_id }); wb.openViewer({ kind: "match", eventId: event.event_id }); }}>Open event</Button></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
      <div className="note"><Info size={12} />Tracking and pose share one 10 Hz clock. Pose is retained for {match.data?.pose_athletes.join(", ") ?? "a subset of players"} only; other players show an explicit unavailable state.</div>
    </BlockFrame>
  );
}

export function ForceTrialBlock({ block, index }: { block: WorkbenchBlock; index: number }) {
  const wb = useWorkbench();
  const trialId = String(block.state.trial_id ?? "");
  const detail = useQuery({ queryKey: ["force-trial", trialId], queryFn: () => scienceApi.forceTrial(trialId), enabled: Boolean(trialId) });
  const trial = detail.data?.trial;
  return (
    <BlockFrame block={block} index={index} icon={<Activity size={12} />} title={trialId} sub={trial ? `${trial.display_id} · week ${trial.week} · trial ${trial.trial_number}` : undefined} states={trial ? [trial.quality_state] : []} removable
      actions={<Button size="sm" variant="primary" onClick={() => wb.openViewer({ kind: "force", trialId })}><Activity size={12} />Open force signal</Button>}
    >
      {detail.isLoading && <Loading label="Loading trial" />}
      {detail.error && <ErrorBox error={detail.error} />}
      {trial && (
        <div className="readouts">
          <Readout label="Concentric impulse" value={formatSig(trial.concentric_impulse_n_s_kg, 4)} unit="N·s·kg⁻¹" />
          <Readout label="Braking duration" value={formatSig(trial.eccentric_braking_duration_s, 3)} unit="s" />
          <Readout label="Jump height (flight)" value={formatSig(trial.jump_height_cm, 3)} unit="cm" />
          <Readout label="Peak power" value={formatSig(trial.peak_power_w_kg, 3)} unit="W·kg⁻¹" />
          <Readout label="Trace" value={trial.trace_available ? "1000 Hz" : "not retained"} detail={<ArmLabel arm={trial.intervention_arm} />} />
        </div>
      )}
    </BlockFrame>
  );
}

export function TableBlock({ block, index }: { block: WorkbenchBlock; index: number }) {
  const wb = useWorkbench();
  const runs = useRuns();
  const subjects = useSubjects();
  const run = runs.data?.find((item) => item.id === String(block.state.run_id ?? "RUN-0003"));
  const result = primaryResult<{ athletes: { subject_id: string; baseline: number; post: number; change: number; percent_change: number; standardized_change: number; exceeds_typical_error: boolean }[]; typical_error: number; unit: string }>(run?.result);
  const metric = metricOption(String(block.state.metric_id ?? "MET-CMJ-IMPULSE"));
  const [sort, setSort] = useState<"change" | "subject">("change");
  const rows = [...(result?.athletes ?? [])].sort((a, b) => (sort === "change" ? b.change - a.change : a.subject_id.localeCompare(b.subject_id)));
  return (
    <BlockFrame block={block} index={index} icon={<Table2 size={12} />} title={block.title} sub={run ? `${run.id} · ${run.method_id} · TE of change ${formatSig(result?.typical_error, 3)} ${metric.unit}` : undefined} states={["DESCRIPTIVE"]} removable
      actions={<div className="seg"><button type="button" aria-pressed={sort === "change"} onClick={() => setSort("change")}>by change</button><button type="button" aria-pressed={sort === "subject"} onClick={() => setSort("subject")}>by athlete</button></div>}
    >
      {runs.isLoading && <Loading label="Loading run" />}
      {result && (
        <div className="table-wrap" style={{ maxHeight: 340 }}>
          <table className="table">
            <thead><tr><th>Athlete</th><th>Arm</th><th className="r">Baseline</th><th className="r">Post</th><th className="r">Change</th><th className="r">%</th><th className="r">Std.</th><th>vs TE</th></tr></thead>
            <tbody>
              {rows.map((row) => {
                const subject = subjects.data?.find((item) => item.subject_id === row.subject_id);
                return (
                  <tr key={row.subject_id} role="button" tabIndex={0} className={wb.selection.athleteId === row.subject_id ? "is-selected" : ""} onClick={() => { wb.select({ athleteId: row.subject_id, trialId: null }); wb.inspect({ kind: "athlete", id: row.subject_id }); }}>
                    <td className="mono">{subject?.display_id ?? row.subject_id}</td>
                    <td>{subject && <ArmLabel arm={subject.intervention_arm} />}</td>
                    <td className="r mono">{formatSig(row.baseline, 4)}</td>
                    <td className="r mono">{formatSig(row.post, 4)}</td>
                    <td className="r mono">{formatSignedSig(row.change, 3)}</td>
                    <td className="r mono">{formatSignedSig(row.percent_change, 3)}</td>
                    <td className="r mono">{formatSignedSig(row.standardized_change, 3)}</td>
                    <td><State plain tone={row.exceeds_typical_error ? "tone-valid" : "tone-neutral"}>{row.exceeds_typical_error ? "EXCEEDS" : "WITHIN"}</State></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <div className="note"><Info size={12} />Units {metric.unit}. Baseline weeks 1–2, post weeks 9–10. Descriptive context only: exceeding the typical error is not a causal individual response.</div>
    </BlockFrame>
  );
}
