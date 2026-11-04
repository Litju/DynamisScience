"use client";

import { useQuery } from "@tanstack/react-query";
import { Activity, Info, LineChart, Pin } from "lucide-react";
import { useMemo } from "react";
import type { ExploreReference, WorkbenchBlock } from "@/lib/types";
import { scienceApi } from "@/lib/api";
import { formatSig, formatSignedSig, metricOption, metricOptionsFor } from "@/lib/scientific";
import { createBlock, insertAfter, updateState } from "@/lib/workbench";
import { ArmLabel, Button, ErrorBox, Loading, Readout, State } from "@/components/ui";
import { CohortLongitudinalChart, COLORS } from "@/components/charts";
import { BlockFrame } from "../Block";
import { useWorkbench } from "../context";

type Population = "ALL" | "INTERVENTION" | "COMPARISON";

export function ExploreBlock({ block, index }: { block: WorkbenchBlock; index: number }) {
  const wb = useWorkbench();
  const real = wb.study.real_data;
  const metricId = String(block.state.metric_id ?? (real ? "MET-REAL-CMJ-HEIGHT" : "MET-CMJ-IMPULSE"));
  const metric = metricOption(metricId);
  const options = metricOptionsFor(real, wb.studyId);
  const population = (block.state.population as Population) ?? "ALL";
  const effectivePopulation = real ? "INTERVENTION" : population;
  const reference = (block.state.reference as ExploreReference) ?? "RAW";
  const context = Array.isArray(block.state.context) ? (block.state.context as string[]) : [];
  const showContext = !real && context.length > 0;
  const set = (patch: Record<string, unknown>) => wb.setBlocks((blocks) => updateState(blocks, block.id, patch));
  const explore = useQuery({
    queryKey: ["explore", wb.studyId, metricId, reference, wb.excludedSubjectIds.join(",")],
    queryFn: () => scienceApi.explore(metricId, wb.excludedSubjectIds, reference, wb.studyId),
    placeholderData: (previous) => previous,
  });
  const data = explore.data;
  const athleteId = wb.selection.athleteId;
  const athleteInCohort = data?.athletes.some((athlete) => athlete.subject_id === athleteId);
  const hasValues = Boolean(data?.summary.some((row) => row.mean !== null));
  const missingWeeks = useMemo(() => (data?.summary ?? []).filter((row) => row.missing_athletes > 0 || row.excluded_trials > 0), [data]);
  const peaks = data?.annotations.load_peaks.map((peak) => peak.week) ?? [];
  const block_ = data?.annotations.intervention_block;
  const focusPoint = wb.selection.week ?? (real ? 4 : 10);
  const weekRows = data?.summary.filter((row) => row.week === focusPoint) ?? [];

  return (
    <BlockFrame
      block={block}
      index={index}
      icon={<LineChart size={12} />}
      title={`${metric.label} · longitudinal trajectory`}
      sub={data ? `${data.cohort.id} · n=${data.cohort.n} · ${data.reference_label.toLowerCase()}` : undefined}
      states={["EXPLORATORY", ...(athleteId ? [{ label: "LINKED: ATHLETE", tone: "tone-signal", title: "Follows the athlete selected in the context strip" }] : [])]}
      removable
    >
      <div className="block-toolbar">
        <label className="field"><span>Metric</span>
          <select className="select" value={metricId} onChange={(event) => set({ metric_id: event.target.value })} aria-label="Explore metric">
            {options.map((option) => <option key={option.id} value={option.id}>{option.label} ({option.unit}){option.role === "PRIMARY" ? " · primary" : ""}</option>)}
          </select>
        </label>
        {!real && <div className="field"><span>Population</span>
          <div className="seg" role="group" aria-label="Population">
            {(["ALL", "INTERVENTION", "COMPARISON"] as Population[]).map((value) => <button key={value} type="button" aria-pressed={population === value} onClick={() => set({ population: value })}>{value === "ALL" ? "Both arms" : value === "INTERVENTION" ? "Intervention" : "Comparison"}</button>)}
          </div>
        </div>}
        <div className="field"><span>Reference</span>
          <div className="seg" role="group" aria-label="Reference">
            {(["RAW", "CHANGE", "PERCENT"] as ExploreReference[]).map((value) => <button key={value} type="button" aria-pressed={reference === value} onClick={() => set({ reference: value })}>{value === "RAW" ? "Observed" : value === "CHANGE" ? "Δ baseline" : "% baseline"}</button>)}
          </div>
        </div>
        {!real && <button type="button" className="chip" aria-pressed={showContext} onClick={() => set({ context: showContext ? [] : ["LOAD", "MATCH"] })}>Context: training load + match exposure</button>}
        <span className="grow" />
        <label className="field"><span>Athlete</span>
          <select className="select" value={athleteId ?? ""} onChange={(event) => { const value = event.target.value || null; wb.select({ athleteId: value, trialId: null }); if (value) wb.inspect({ kind: "athlete", id: value }); }} aria-label="Select athlete">
            <option value="">— none —</option>
            {data?.athletes.map((athlete) => <option key={athlete.subject_id} value={athlete.subject_id}>{athlete.display_id} · {real ? "real" : athlete.intervention_arm === "INTERVENTION" ? "INT" : "CMP"}</option>)}
          </select>
        </label>
      </div>

      {explore.isLoading && <Loading label="Aggregating athlete-week means with DuckDB" />}
      {explore.error && <ErrorBox error={explore.error} onRetry={() => void explore.refetch()} />}
      {data && !hasValues && <div className="error">No valid observations for this metric and cohort — nothing is plotted.</div>}
      {data && hasValues && block_ && (
        <div className="chart-frame">
          <div className="chart-cap">
            <strong>{metric.label}</strong>
            <span className="mono">{data.unit}</span>
            <span>· {real ? "cohort mean ± 95% CI across athletes" : "arm mean ± 95% CI across athletes"} · thin lines = individual athletes · click a line to select</span>
            <span className="legend">
              {(effectivePopulation === "ALL" || effectivePopulation === "INTERVENTION") && <span><i className="swatch" style={{ background: COLORS.int }} />{real ? "Single training arm" : "Intervention"}</span>}
              {!real && (effectivePopulation === "ALL" || effectivePopulation === "COMPARISON") && <span><i className="swatch" style={{ background: COLORS.cmp }} />Comparison</span>}
              {athleteId && athleteInCohort && <span><i className="swatch" style={{ background: COLORS.signal }} />{data.athletes.find((a) => a.subject_id === athleteId)?.display_id}</span>}
            </span>
          </div>
          <CohortLongitudinalChart
            summary={data.summary}
            athletes={data.athletes}
            context={data.context}
            unit={data.unit}
            metricLabel={metric.label}
            population={effectivePopulation}
            blockWeeks={[block_.start_week, block_.end_week]}
            loadPeaks={peaks}
            showContext={showContext}
            selectedAthlete={athleteId}
            selectedWeek={wb.selection.week}
            onSelectAthlete={(id) => { wb.select({ athleteId: id, trialId: null }); wb.inspect({ kind: "athlete", id }); }}
            onSelectWeek={(week) => wb.select({ week })}
          />
        </div>
      )}
      {data && hasValues && (
        <div className="block-toolbar small">
          <span className="faint">{real ? "Occasion" : "Week"} {focusPoint}:</span>
          {weekRows.filter((row) => effectivePopulation === "ALL" || row.arm === effectivePopulation).map((row) => (
            <span key={row.arm}><ArmLabel arm={row.arm} /> <span className="mono">{formatSig(row.mean, 4)}</span><span className="unit">{data.unit}</span> <span className="mono faint">[{formatSig(row.ci_low, 3)}, {formatSig(row.ci_high, 3)}] n={row.n}</span></span>
          ))}
          <span className="grow" />
          <span className="faint">{missingWeeks.length ? `incomplete ${real ? "occasions" : "weeks"}: ${missingWeeks.map((row) => `${real ? "o" : "w"}${row.week}${row.arm === "INTERVENTION" ? "·I" : "·C"}`).join(" ")}` : `complete ${real ? "occasion" : "weekly"} coverage`}</span>
          <span className="faint">load peak (computed): {peaks.length ? peaks.map((week) => `w${week}`).join(", ") : "none"}</span>
        </div>
      )}
      {athleteId && data && athleteInCohort && <AthletePanel blockId={block.id} metricId={metricId} />}
      {athleteId && data && !athleteInCohort && <div className="note warn"><Info size={12} />The selected athlete is excluded from the active cohort.</div>}
      <div className="note"><Info size={12} /><span>{data?.method.note ?? "Descriptive exploration."} Unit of analysis: {data?.method.unit_of_analysis ?? "athlete-week"}. Excluded and missing trials are shown in tooltips and in the athlete trial strip; they are never silently dropped.</span></div>
    </BlockFrame>
  );
}

function AthletePanel({ blockId, metricId }: { blockId: string; metricId: string }) {
  const wb = useWorkbench();
  const athleteId = wb.selection.athleteId as string;
  const athlete = useQuery({ queryKey: ["athlete", wb.studyId, athleteId, metricId], queryFn: () => scienceApi.athlete(athleteId, metricId, wb.studyId) });
  const data = athlete.data;
  const real = wb.study.real_data;
  if (athlete.isLoading) return <Loading label="Loading athlete observations" />;
  if (athlete.error || !data) return <ErrorBox error={athlete.error ?? "Athlete unavailable"} />;
  const individual = data.individual;
  const unit = data.metric.unit;
  const selectedTrial = data.observations.flatMap((observation) => observation.trials.map((trial) => ({ ...trial, week: observation.week }))).find((trial) => trial.trial_id === wb.selection.trialId);
  const pin = () => {
    if (!selectedTrial) return;
    const trialBlock = createBlock(wb.blocks, "force_trial", { title: `Force trial ${selectedTrial.trial_id}`, state: { trial_id: selectedTrial.trial_id, subject_id: athleteId } });
    wb.setBlocks((blocks) => insertAfter(blocks, trialBlock, blockId));
    wb.notify(`${selectedTrial.trial_id} pinned to the investigation`);
  };
  return (
    <div className="athlete-panel">
      <div className="athlete-panel-head">
        <strong>{data.subject.display_id}</strong>
        <span className="faint">{data.subject.position} · age {data.subject.age} · {data.subject.body_mass_kg.toFixed(1)} kg · training age {data.subject.training_age_years} y</span>
        <ArmLabel arm={data.subject.intervention_arm} />
        <span style={{ marginLeft: "auto" }} className="faint small">linked selection · {data.metric.label}</span>
      </div>
      <div style={{ padding: 10, display: "grid", gap: 10 }}>
        <div className="readouts">
          <Readout label={real ? "First occasion" : "Baseline w1–2"} value={formatSig(individual.baseline_mean, 4)} unit={unit} />
          <Readout label={real ? "Final occasion" : "Post w9–10"} value={formatSig(individual.post_mean, 4)} unit={unit} />
          <Readout label="Change" value={formatSignedSig(individual.change, 3)} unit={unit} detail={individual.percent_change === null ? undefined : `${formatSignedSig(individual.percent_change, 3)} %`} />
          <Readout label="Standardised" value={individual.standardized_change === null ? "—" : formatSignedSig(individual.standardized_change, 3)} unit="SD" detail={`cohort change SD ${formatSig(individual.cohort_change_sd, 3)}`} />
          <Readout label="vs typical error" value={individual.exceeds_typical_error === null ? "NOT ESTIMABLE" : individual.exceeds_typical_error ? "EXCEEDS" : "WITHIN"} detail={real ? "no repeated same-session trial" : `TE of change ${formatSig(individual.typical_error, 3)} ${unit}`} />
        </div>
        <div>
          <div className="faint small" style={{ marginBottom: 4 }}>{real ? "Observations by testing occasion — one derived CMJ per occasion; no raw force trace is deposited" : "CMJ trials by week — teal outline: 1000 Hz force trace retained · hatched: EXCLUDED · dashed: not captured"}</div>
          <div className="trial-strip">
            {data.observations.map((observation) => (
              <div key={observation.week} className={`trial-week ${wb.selection.week === observation.week ? "is-selected" : ""}`}>
                <span>{real ? "O" : "w"}{observation.week}</span>
                {[1, 2].map((number) => {
                  const trial = observation.trials.find((item) => item.trial_number === number);
                  if (!trial) return <span key={number} className="trial-dot is-missing" title={`Week ${observation.week} trial ${number}: not captured`}>–</span>;
                  const classes = ["trial-dot", trial.trace_available ? "has-trace" : "", trial.quality_state === "EXCLUDED" ? "is-excluded" : "", wb.selection.trialId === trial.trial_id ? "is-selected" : ""].join(" ");
                  return (
                    <button key={number} type="button" className={classes} title={`${trial.trial_id} · ${trial.quality_state}${trial.exclusion_reason ? ` · ${trial.exclusion_reason}` : ""} · ${formatSig(trial.value, 4)} ${unit}${trial.trace_available ? " · trace" : ""}`} onClick={() => { wb.select({ trialId: trial.trial_id, week: observation.week }); wb.inspect({ kind: "trial", id: trial.trial_id }); }}>
                      T{number}
                    </button>
                  );
                })}
              </div>
            ))}
          </div>
        </div>
        {selectedTrial ? (
          <div className="block-toolbar">
            <span className="mono">{selectedTrial.trial_id}</span>
            <State>{selectedTrial.quality_state}</State>
            <span className="mono">{formatSig(selectedTrial.value, 4)}<span className="unit">{unit}</span></span>
            {selectedTrial.exclusion_reason && <span className="note bad">{selectedTrial.exclusion_reason}</span>}
            <span className="grow" />
            {!real && <Button size="sm" onClick={pin}><Pin size={12} />Pin to investigation</Button>}
            {!real && <Button size="sm" variant="primary" onClick={() => wb.openViewer({ kind: "force", trialId: selectedTrial.trial_id })}><Activity size={12} />{selectedTrial.trace_available ? "Open force signal" : "Open trial (no raw trace)"}</Button>}
            {real && <span className="faint small">Derived scalar only; the deposit contains no force-time trace.</span>}
          </div>
        ) : (
          <div className="faint small">Select a trial to open its force signal.</div>
        )}
        <div className="note"><Info size={12} /><span>{individual.limitations}</span></div>
      </div>
    </div>
  );
}
