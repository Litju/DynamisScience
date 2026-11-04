"use client";

import { useMutation } from "@tanstack/react-query";
import { GitBranch, GitFork, Info, Play, Sigma, Stethoscope } from "lucide-react";
import { useMemo } from "react";
import type { LongitudinalDiagnostics, LongitudinalResult, Run, WorkbenchBlock } from "@/lib/types";
import { scienceApi } from "@/lib/api";
import { METHOD_LABEL, REAL_METHODS, formatSig, formatSignedSig, metricOption, metricOptionsFor, primaryResult } from "@/lib/scientific";
import { createBlock, updateState } from "@/lib/workbench";
import { Button, ErrorBox, Forest, IconButton, KV, Loading, Readout, State } from "@/components/ui";
import { QQChart, ResidualByWeekChart } from "@/components/charts";
import { BlockFrame } from "../Block";
import { useWorkbench } from "../context";
import { useInvalidateScience, useRuns } from "../data";

type Dict = Record<string, unknown>;

const DEFAULT_PARAMETERS: Record<string, Dict> = {
  "METH-LONG": { reference_week: 1, contrast_week: 10, alpha: 0.05 },
  "METH-REL": { baseline_weeks: [1], alpha: 0.05 },
  "METH-IND": { baseline_weeks: [1, 2], post_weeks: [9, 10] },
  "METH-REAL-TREND": { reference_occasion: 1, contrast_occasion: 4, alpha: 0.05 },
  "METH-REAL-DESC": {},
  "METH-REAL-SIGNAL-QA": {},
  "METH-REAL-RELIABILITY": { activity: "Walking", max_trials: 8 },
  "METH-REAL-BODYWEIGHT": { activities: ["Walking", "Heel drop"] },
};

const stable = (value: unknown) => JSON.stringify(value, Object.keys((value as object) ?? {}).sort());

export function analysisConfig(block: WorkbenchBlock) {
  const methodId = String(block.state.method_id ?? "METH-LONG");
  const outcomeId = String(block.state.outcome_metric_id ?? "MET-CMJ-IMPULSE");
  const parameters = { ...(DEFAULT_PARAMETERS[methodId] ?? {}), ...((block.state.parameters as Dict) ?? {}) };
  return { methodId, outcomeId, parameters };
}

/** Whether the block's current configuration equals the run it displays. */
export function runMatchesConfig(run: Run | undefined, block: WorkbenchBlock, excluded: string[]): boolean {
  if (!run) return false;
  const { methodId, outcomeId, parameters } = analysisConfig(block);
  const spec = run.execution?.analysis_spec;
  const runOutcome = run.outcome_metric_id ?? spec?.outcome_metric_id;
  const runExcluded = run.execution?.cohort.excluded_subject_ids ?? [];
  const runParams = run.parameters ?? spec?.parameters ?? {};
  return run.method_id === methodId && runOutcome === outcomeId && stable(runParams) === stable(parameters) && [...runExcluded].sort().join(",") === [...excluded].sort().join(",");
}

export function AnalysisBlock({ block, index }: { block: WorkbenchBlock; index: number }) {
  const wb = useWorkbench();
  const real = wb.study.real_data;
  const runs = useRuns(wb.studyId);
  const invalidate = useInvalidateScience();
  const { methodId, outcomeId, parameters } = analysisConfig(block);
  const metric = metricOption(outcomeId);
  const metricOptions = metricOptionsFor(real, wb.studyId);
  const methodOptions = real ? REAL_METHODS[wb.studyId] ?? [] : ["METH-LONG", "METH-REL", "METH-IND"];
  const runId = block.state.run_id as string | undefined;
  const run = runs.data?.find((item) => item.id === runId);
  const fresh = runMatchesConfig(run, block, wb.excludedSubjectIds);
  const frozenSpec = useMemo(
    () => wb.study.analysis_specs.find((spec) => (spec.status === "FROZEN" || spec.status === "REGISTERED") && spec.method_id === methodId && spec.outcome_metric_id === outcomeId && stable(spec.parameters) === stable(parameters)),
    [methodId, outcomeId, parameters, wb.study.analysis_specs],
  );
  const planned = Boolean(frozenSpec) && wb.excludedSubjectIds.length === 0;
  const set = (patch: Dict) => wb.setBlocks((blocks) => updateState(blocks, block.id, patch));
  const setParam = (key: string, value: unknown) => set({ parameters: { ...parameters, [key]: value } });

  const execute = useMutation({
    mutationFn: () => scienceApi.execute({ study_id: wb.studyId, method_id: methodId, outcome_metric_id: outcomeId, excluded_subject_ids: wb.excludedSubjectIds, parameters }),
    onSuccess: (created) => {
      set({ run_id: created.id, spec_id: created.analysis_spec_id });
      invalidate();
      wb.notify(`${created.id} appended to the ledger · ${created.plan_alignment}${created.reproduces?.length ? ` · reproduces ${created.reproduces.join(", ")}` : ""}`);
    },
  });

  const fork = () => {
    const copy = createBlock(wb.blocks, "analysis", { from: block, title: `${block.title} · fork` });
    const withRun = { ...copy, state: { ...copy.state, outcome_metric_id: outcomeId === "MET-CMJ-IMPULSE" ? "MET-CMJ-BRAKING-DURATION" : outcomeId } };
    const blocksWithFork = [...wb.blocks, withRun];
    const diagnostics = createBlock(blocksWithFork, "diagnostics", { from: withRun, title: "Fork diagnostics" });
    const evidence = createBlock([...blocksWithFork, diagnostics], "evidence", { from: withRun, title: "Fork evidence" });
    wb.setBlocks((blocks) => {
      const reportIndex = blocks.findIndex((item) => item.type === "report_section");
      const at = reportIndex >= 0 ? reportIndex : blocks.length;
      return [...blocks.slice(0, at), withRun, diagnostics, evidence, ...blocks.slice(at)];
    });
    wb.selectBlock(withRun.id, { scroll: true });
  };

  const alignment = run && fresh ? run.plan_alignment ?? "PLANNED" : real && planned ? "REGISTERED" : planned ? "PLANNED" : "EXPLORATORY";
  const states: (string | { label: string; tone?: string; title?: string })[] = [alignment];
  if (run && fresh) states.push(run.status);
  else states.push({ label: "NOT RUN", title: "The configuration differs from the displayed run; execute to create a new immutable run" });

  return (
    <BlockFrame
      block={block}
      index={index}
      icon={<Sigma size={12} />}
      title={block.title}
      sub={`${METHOD_LABEL[methodId]} · ${metric.label}`}
      states={states}
      removable={index > 4}
      actions={<IconButton label="Fork analysis (new block, new spec, new run)" onClick={fork}><GitFork size={13} /></IconButton>}
    >
      <div className="block-toolbar">
        <label className="field"><span>Method</span>
          <select className="select" value={methodId} onChange={(event) => set({ method_id: event.target.value, parameters: DEFAULT_PARAMETERS[event.target.value] })} aria-label="Analysis method">
            {methodOptions.map((id) => <option key={id} value={id}>{id} · {METHOD_LABEL[id] ?? id}</option>)}
          </select>
        </label>
        <label className="field"><span>Outcome</span>
          <select className="select" value={outcomeId} onChange={(event) => set({ outcome_metric_id: event.target.value })} aria-label="Outcome metric">
            {metricOptions.map((option) => <option key={option.id} value={option.id}>{option.label} ({option.unit})</option>)}
          </select>
        </label>
        {methodId === "METH-LONG" && (
          <>
            <label className="field"><span>Reference week</span><input className="input input-num" type="number" min={1} max={15} value={Number(parameters.reference_week)} onChange={(event) => setParam("reference_week", Number(event.target.value))} /></label>
            <label className="field"><span>Contrast week</span><input className="input input-num" type="number" min={2} max={16} value={Number(parameters.contrast_week)} onChange={(event) => setParam("contrast_week", Number(event.target.value))} /></label>
          </>
        )}
        {methodId === "METH-REL" && (
          <div className="field"><span>Baseline weeks</span>
            <div className="seg">{[[1], [1, 2]].map((weeks) => <button key={weeks.join()} type="button" aria-pressed={stable(parameters.baseline_weeks) === stable(weeks)} onClick={() => setParam("baseline_weeks", weeks)}>w{weeks.join("–")}</button>)}</div>
          </div>
        )}
        {methodId === "METH-REAL-TREND" && (
          <>
            <label className="field"><span>Reference occasion</span><input className="input input-num" type="number" min={1} max={3} value={Number(parameters.reference_occasion)} onChange={(event) => setParam("reference_occasion", Number(event.target.value))} /></label>
            <label className="field"><span>Contrast occasion</span><input className="input input-num" type="number" min={2} max={4} value={Number(parameters.contrast_occasion)} onChange={(event) => setParam("contrast_occasion", Number(event.target.value))} /></label>
            <span className="faint small">Occasions are the four deposited testing blocks, not calendar weeks.</span>
          </>
        )}
        {methodId === "METH-REAL-RELIABILITY" && (
          <>
            <label className="field"><span>Activity</span>
              <select className="select" value={String(parameters.activity ?? "Walking")} onChange={(event) => setParam("activity", event.target.value)}>
                {["Walking", "Jogging", "Running", "Heel drop", "Step drop"].map((activity) => <option key={activity} value={activity}>{activity}</option>)}
              </select>
            </label>
            <label className="field"><span>Max trials / participant</span><input className="input input-num" type="number" min={2} max={8} value={Number(parameters.max_trials ?? 8)} onChange={(event) => setParam("max_trials", Number(event.target.value))} /></label>
          </>
        )}
        <span className="grow" />
        <span className="faint small">{planned ? `${real ? "matches registered" : "matches frozen"} ${frozenSpec?.id}` : `deviates from the ${real ? "registered" : "frozen"} plan → exploratory spec`}</span>
        <Button variant="primary" onClick={() => execute.mutate()} disabled={execute.isPending}><Play size={12} />{execute.isPending ? "Executing…" : run && fresh ? "Re-run" : "Run analysis"}</Button>
      </div>
      <div className="small faint">
        Spec <span className="mono" style={{ color: "var(--text)" }}>{run && fresh ? run.analysis_spec_id : frozenSpec && planned ? frozenSpec.id : "new exploratory spec"}</span> ·
        cohort <span className="mono" style={{ color: "var(--text)" }}>{run && fresh ? run.cohort_id : wb.excludedSubjectIds.length ? "draft" : wb.study.cohort.id}</span> ·
        dataset <span className="mono" style={{ color: "var(--text)" }}>{wb.study.snapshot.id}</span>
        {methodId === "METH-LONG" && <> · estimand <span style={{ color: "var(--text)" }}>difference in change, week {String(parameters.reference_week)} → {String(parameters.contrast_week)}, intervention − comparison</span></>}
        {methodId === "METH-REAL-TREND" && <> · estimand <span style={{ color: "var(--text)" }}>within-athlete change per testing occasion; occasion {String(parameters.reference_occasion)} → {String(parameters.contrast_occasion)}</span></>}
      </div>
      {execute.error && <ErrorBox error={execute.error} />}
      {runs.isLoading && <Loading label="Reading run ledger" />}
      {run && !fresh && <div className="note warn"><Info size={12} />Showing {run.id}, which was executed with a different configuration. Results below belong to {run.id}; run the analysis to produce a result for the current configuration.</div>}
      {run && <RunResult run={run} />}
      {!run && !runs.isLoading && <div className="empty">No run yet. Executing appends an immutable AnalysisRun to the ledger; it does not create evidence.</div>}
    </BlockFrame>
  );
}

function RunResult({ run }: { run: Run }) {
  const wb = useWorkbench();
  const result = primaryResult<Dict>(run.result) ?? {};
  const metric = metricOption(run.outcome_metric_id ?? run.execution?.analysis_spec.outcome_metric_id);
  const runChip = (
    <div className="block-toolbar small">
      <span className="mono" style={{ color: "var(--signal)" }}>{run.id}</span>
      <State>{run.status}</State>
      <span className="faint mono">{new Date(run.created_at).toISOString().replace("T", " ").slice(0, 19)}Z · {run.duration_ms.toFixed(0)} ms · {run.software_versions.service}</span>
      {run.reproduces && run.reproduces.length > 0 && <State tone="tone-valid" title="Identical result digest and reproducibility key">{`REPRODUCES ${run.reproduces.join(", ")}`}</State>}
      <span className="grow" />
      <Button size="sm" variant="ghost" onClick={() => wb.inspect({ kind: "run", id: run.id })}>Inspect run</Button>
      <Button size="sm" variant="ghost" onClick={() => wb.openLineage(run.id)}><GitBranch size={12} />Lineage</Button>
    </div>
  );
  if (run.method_id === "METH-REAL-TREND") {
    const result_ = result as Dict;
    const contrasts = (result_.contrasts ?? {}) as Record<string, Dict>;
    const slope = contrasts.occasion_slope;
    const changeKey = `occasion_${String(result_.reference_occasion)}_to_${String(result_.contrast_occasion)}`;
    const change = contrasts[changeKey];
    const random = (result_.random_effects ?? {}) as Dict;
    if (!slope || !change) return <ErrorBox error={`${run.id} has no occasion contrast`} />;
    return (
      <>
        <div className="block-split">
          <div className="estimate-line">
            <div className="label">{String(change.contrast ?? "Change across occasions")}</div>
            <span className="value">{formatSignedSig(Number(change.estimate), 3)}<span className="unit">{String(change.unit ?? metric.unit)}</span></span>
            <span className="ci">95% CI [{formatSig(Number(change.ci_low), 3)}, {formatSig(Number(change.ci_high), 3)}]</span>
            <span className="meta">SE {formatSig(Number(change.std_error), 3)} · Wald</span>
            <div style={{ width: "100%" }}><Forest estimate={Number(change.estimate)} low={Number(change.ci_low)} high={Number(change.ci_high)} unit={String(change.unit ?? metric.unit)} /></div>
          </div>
          <div className="readouts" style={{ gridTemplateColumns: "1fr 1fr" }}>
            <Readout label="Observations" value={Number(result_.n_observations)} detail="complete CMJ rows" />
            <Readout label="Athletes" value={Number(result_.n_subjects)} />
            <Readout label="Estimator" value={<span style={{ fontSize: 11 }}>{String(result_.estimator)}</span>} detail={`${String(result_.optimizer ?? "")} · converged`} />
            <Readout label="Log likelihood" value={formatSig(Number(result_.log_likelihood), 6)} detail="ML" />
          </div>
        </div>
        <div className="block-cols">
          <div>
            <div className="upper faint" style={{ marginBottom: 4 }}>Fixed effects</div>
            <table className="table">
              <thead><tr><th>Term</th><th className="r">Estimate</th><th className="r">SE</th><th className="r">95% CI</th></tr></thead>
              <tbody>
                {Object.entries((result_.coefficients ?? {}) as Record<string, Dict>).map(([term, item]) => (
                  <tr key={term}><td className="mono">{term}</td><td className="r mono">{formatSignedSig(Number(item.estimate), 4)} {metric.unit}</td><td className="r mono">{formatSig(Number(item.std_error), 4)}</td><td className="r mono">[{formatSig(Number(item.ci_low), 3)}, {formatSig(Number(item.ci_high), 3)}]</td></tr>
                ))}
              </tbody>
            </table>
          </div>
          <div>
            <div className="upper faint" style={{ marginBottom: 4 }}>Random effects (athlete)</div>
            <KV rows={[
              ["Intercept variance", formatSig(Number(random.subject_intercept_variance), 3), "mono"],
              ["Occasion-slope variance", formatSig(Number(random.subject_slope_variance), 4), "mono"],
              ["Intercept–slope covariance", formatSig(Number(random.subject_intercept_slope_covariance), 4), "mono"],
              ["Residual variance", formatSig(Number(random.residual_variance), 3), "mono"],
              ["Slope per occasion", `${formatSignedSig(Number(slope.estimate), 3)} ${String(slope.unit)}`, "mono"],
            ]} />
          </div>
        </div>
        <div className="note warn"><Info size={12} />Single-arm repeated-measures design. The model estimates within-athlete change; it does not identify a causal effect of the intervention. Occasions are COND 1–4, not calendar weeks.</div>
        {runChip}
      </>
    );
  }
  if (run.method_id === "METH-REAL-DESC") {
    const result_ = result as Dict;
    const occasions = (result_.occasions ?? []) as Dict[];
    return (
      <>
        <div className="readouts">
          <Readout label="Change 1 → 4" value={formatSignedSig(Number(result_.change_first_to_last), 3)} unit={String(result_.unit ?? metric.unit)} />
          <Readout label="Percent change" value={formatSignedSig(Number(result_.percent_change_first_to_last), 2)} unit="%" />
          <Readout label="Athletes" value={String(result_.n_subjects)} />
          <Readout label="Observations" value={String(result_.n_observations)} />
        </div>
        <table className="table">
          <thead><tr><th>Occasion</th><th className="r">n</th><th className="r">Mean</th><th className="r">SD</th><th className="r">95% CI</th></tr></thead>
          <tbody>
            {occasions.map((item) => (
              <tr key={String(item.occasion)}><td className="mono">Occasion {String(item.occasion)}</td><td className="r mono">{String(item.n)}</td><td className="r mono">{formatSig(Number(item.mean), 3)} {metric.unit}</td><td className="r mono">{formatSig(Number(item.sd), 3)}</td><td className="r mono">[{formatSig(Number(item.ci_low), 3)}, {formatSig(Number(item.ci_high), 3)}]</td></tr>
            ))}
          </tbody>
        </table>
        <div className="note"><Info size={12} />Descriptive only; no model-based inference. Missing occasion-4 rows are shown as missing and not imputed.</div>
        {runChip}
      </>
    );
  }
  if (run.method_id === "METH-REAL-RELIABILITY") {
    return (
      <>
        {String(result.status) !== "COMPUTED" && <div className="error">{String(result.message ?? "Reliability could not be computed")}</div>}
        <div className="readouts">
          <Readout large label="ICC(3,1)" value={formatSig(Number(result.icc_3_1), 3)} detail={`95% CI [${formatSig(Number(result.icc_3_1_ci_low), 3)}, ${formatSig(Number(result.icc_3_1_ci_high), 3)}]`} />
          <Readout label="Typical error" value={formatSig(Number(result.typical_error), 1)} unit={metric.unit} detail={`${formatSig(Number(result.typical_error_percent), 2)} % of mean`} />
          <Readout label="Within-subject CV" value={formatSig(Number(result.mean_cv_percent), 2)} unit="%" detail={`${String(result.activity)} trials`} />
          <Readout label="Smallest worthwhile Δ" value={formatSig(Number(result.smallest_worthwhile_change), 1)} unit={metric.unit} detail="1.96·√2·TE" />
          <Readout label="n × k" value={`${String(result.n_subjects)} × ${String(result.trials_per_subject)}`} detail={`${String(result.n_trials_used)} trials used`} />
        </div>
        <div className="note warn"><Info size={12} />Reproducible but not speed-controlled: within-participant peak-force reliability across repeated {String(result.activity).toLowerCase()} trials. This is not inter-device agreement.</div>
        {runChip}
      </>
    );
  }
  if (run.method_id === "METH-REAL-SIGNAL-QA") {
    const result_ = result as Dict;
    const activities = (result_.activities ?? []) as Dict[];
    const bw = (result_.body_weight ?? {}) as Dict;
    const imu = (result_.imu ?? {}) as Dict;
    return (
      <>
        <div className="readouts">
          <Readout label="Matched trials" value={String(activities.reduce((sum, item) => sum + Number(item.n_trials), 0))} detail={`${activities.length} activities`} />
          <Readout label="Force sampling" value="1000" unit="Hz" detail="5 or 10 s trials" />
          <Readout label="IMU sampling" value={`${formatSig(Number(imu.sampling_hz_min), 1)}–${formatSig(Number(imu.sampling_hz_max), 1)}`} unit="Hz" />
          <Readout label="Gravity |g|" value={`${formatSig(Number(imu.gravity_mean_min_g), 6)}–${formatSig(Number(imu.gravity_mean_max_g), 6)}`} unit="g" />
          <Readout label="BW bias" value={formatSignedSig(Number(bw.bias_n), 0)} unit="N" detail={`${formatSig(Number(bw.mean_percent_error), 1)} % · n=${String(bw.n)}`} />
        </div>
        <table className="table">
          <thead><tr><th>Activity</th><th className="r">Trials</th><th className="r">Participants</th><th className="r">Peak Fz mean</th><th className="r">Peak Fz SD</th><th className="r">3-plate</th><th className="r">Clock offset</th></tr></thead>
          <tbody>
            {activities.map((item) => (
              <tr key={String(item.activity)}><td>{String(item.activity)}</td><td className="r mono">{String(item.n_trials)}</td><td className="r mono">{String(item.n_subjects)}</td><td className="r mono">{formatSig(Number(item.peak_fz_mean_n), 0)} N</td><td className="r mono">{formatSig(Number(item.peak_fz_sd_n), 0)}</td><td className="r mono">{String(item.three_plate_trials)}</td><td className="r mono">{formatSig(Number(item.clock_offset_median_s), 0)} s</td></tr>
            ))}
          </tbody>
        </table>
        <div className="note warn"><Info size={12} />The advertised trial-matching manifest and quality flags are absent from the archive; matching is reconstructed by participant, activity and trial number. Device clocks differ by hours, so no sample-level synchronisation is claimed.</div>
        {runChip}
      </>
    );
  }
  if (run.method_id === "METH-REAL-BODYWEIGHT") {
    return (
      <>
        <div className="readouts">
          <Readout large label="Bias" value={formatSignedSig(Number(result.bias_n), 0)} unit="N" detail={`${formatSig(Number(result.mean_percent_error), 1)} % of body weight`} />
          <Readout label="SD of differences" value={formatSig(Number(result.sd_n), 0)} unit="N" />
          <Readout label="95% LoA" value={`${formatSignedSig(Number(result.loa_low_n), 0)} to ${formatSignedSig(Number(result.loa_high_n), 0)}`} unit="N" />
          <Readout label="Trials" value={String(result.n)} detail="walking + heel drop" />
        </div>
        <div className="note warn"><Info size={12} />Body-weight recovery from the support-window mean was tested and rejected: the bias is large and the limits of agreement are wide. Anthropometric weight is metadata embedded in participant folder names, not an independent scale measurement.</div>
        {runChip}
      </>
    );
  }
  if (run.method_id === "METH-LONG") {
    const long = result as unknown as LongitudinalResult;
    const contrast = long.contrasts?.[long.primary_contrast_id];
    if (!contrast) return <ErrorBox error={`${run.id} has no primary contrast`} />;
    return (
      <>
        <div className="block-split">
          <div className="estimate-line">
            <div className="label">{contrast.contrast}</div>
            <span className="value">{formatSignedSig(contrast.estimate, 3)}<span className="unit">{metric.unit}</span></span>
            <span className="ci">95% CI [{formatSig(contrast.ci_low, 3)}, {formatSig(contrast.ci_high, 3)}]</span>
            <span className="meta">SE {formatSig(contrast.std_error, 3)} · Wald</span>
            <div style={{ width: "100%" }}><Forest estimate={contrast.estimate} low={contrast.ci_low} high={contrast.ci_high} unit={metric.unit} /></div>
          </div>
          <div className="readouts" style={{ gridTemplateColumns: "1fr 1fr" }}>
            <Readout label="Observations" value={long.n_observations} detail="first valid trials" />
            <Readout label="Athletes" value={long.n_subjects} />
            <Readout label="Estimator" value={<span style={{ fontSize: 11 }}>{long.estimator}</span>} detail={long.converged ? "converged" : "fallback"} />
            <Readout label="Std. effect" value={formatSig(long.effect_size, 3)} unit="SD" detail="Δ / post-block SD" />
          </div>
        </div>
        <table className="table">
          <thead><tr><th>Contrast</th><th className="r">Estimate</th><th className="r">SE</th><th className="r">95% CI</th><th>Role</th></tr></thead>
          <tbody>
            {Object.entries(long.contrasts).map(([id, item]) => (
              <tr key={id} className={id === long.primary_contrast_id ? "is-selected" : ""}>
                <td>{item.contrast}</td>
                <td className="r mono">{formatSignedSig(item.estimate, 3)} <span className="unit">{metric.unit}</span></td>
                <td className="r mono">{formatSig(item.std_error, 3)}</td>
                <td className="r mono">[{formatSig(item.ci_low, 3)}, {formatSig(item.ci_high, 3)}]</td>
                <td className="small faint">{id === long.primary_contrast_id ? "primary estimand" : item.interpretation ?? ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {runChip}
      </>
    );
  }
  if (run.method_id === "METH-REL") {
    return (
      <>
        {result.status !== "COMPUTED" && <div className="error">{String(result.message ?? "Reliability could not be computed")}</div>}
        <div className="readouts">
          <Readout large label="ICC(3,1)" value={formatSig(result.icc_3_1 as number, 3)} detail={`95% CI [${formatSig(result.icc_3_1_ci_low as number, 3)}, ${formatSig(result.icc_3_1_ci_high as number, 3)}]`} />
          <Readout label="Typical error" value={formatSig(result.typical_error as number, 3)} unit={metric.unit} detail={`${formatSig(result.typical_error_percent as number, 3)} % of mean`} />
          <Readout label="Within-subject CV" value={formatSig(result.mean_cv_percent as number, 3)} unit="%" detail="mean across athletes" />
          <Readout label="Smallest worthwhile Δ" value={formatSig(result.smallest_worthwhile_change as number, 3)} unit={metric.unit} detail="1.96·√2·TE" />
          <Readout label="n × k" value={`${String(result.n_subjects)} × ${String(result.trials_per_subject)}`} detail={`baseline weeks ${(result.baseline_weeks as number[] | undefined)?.join(",") ?? "—"}`} />
        </div>
        {runChip}
      </>
    );
  }
  return (
    <>
      <div className="readouts">
        <Readout large label="Median change" value={formatSignedSig(result.median_change as number, 3)} unit={metric.unit} />
        <Readout label="Change SD" value={formatSig(result.change_sd as number, 3)} unit={metric.unit} />
        <Readout label="Standardised" value={formatSignedSig(result.standardized_change as number, 3)} unit="SD" />
        <Readout label="TE of change" value={formatSig(result.typical_error as number, 3)} unit={metric.unit} />
        <Readout label="Athletes" value={String(result.n_subjects)} detail={String(result.method)} />
      </div>
      {runChip}
    </>
  );
}

export function DiagnosticsBlock({ block, index }: { block: WorkbenchBlock; index: number }) {
  const wb = useWorkbench();
  const runs = useRuns(wb.studyId);
  const analysis = wb.blocks.find((item) => item.id === block.state.analysis_block_id);
  const run = runs.data?.find((item) => item.id === analysis?.state.run_id);
  const fresh = analysis ? runMatchesConfig(run, analysis, wb.excludedSubjectIds) : false;
  const metric = metricOption(run?.outcome_metric_id ?? run?.execution?.analysis_spec.outcome_metric_id);
  const diagnostics = (run?.diagnostics ?? {}) as Partial<LongitudinalDiagnostics> & Dict;
  const isLong = run?.method_id === "METH-LONG" || run?.method_id === "METH-REAL-TREND";
  const isRealTrend = run?.method_id === "METH-REAL-TREND";
  const attempts = (diagnostics.estimator_attempts ?? []).filter((item) => !item.includes("selected="));
  const optimizer = (diagnostics as Dict).optimizer ?? (attempts.length ? undefined : "selected");
  const complete = isLong ? Boolean(diagnostics.residual_qq?.length && diagnostics.residual_by_week?.length && diagnostics.estimator) : Boolean(run && Object.keys(diagnostics).length);
  const status = !run ? "INCOMPLETE" : !complete ? "INCOMPLETE" : isLong && !diagnostics.converged ? "FALLBACK" : "COMPUTED";
  return (
    <BlockFrame block={block} index={index} icon={<Stethoscope size={12} />} title={block.title} sub={run ? `attached to ${run.id} · ${analysis?.title}` : "no run to evaluate"} states={[status, ...(run && !fresh ? [{ label: "STALE", tone: "tone-warning", title: "The analysis configuration changed since this run" }] : [])]}>
      {!run && <div className="error">No run is attached to this analysis. A result without diagnostics is incomplete and cannot be promoted to evidence.</div>}
      {run && isLong && complete && (
        <>
          <div className="diag-grid">
            <div>
              <div className="upper faint" style={{ marginBottom: 6 }}>Estimation</div>
              <div className="check-list">
                <div className="check"><State plain>{diagnostics.converged ? "VALID" : "WARNING"}</State><span>{String(diagnostics.estimator)} · {diagnostics.converged ? "converged" : "fallback estimator"}{optimizer ? ` · ${String(optimizer)}` : ""}</span></div>
                <div className="check"><State plain tone={attempts.length ? "tone-warning" : "tone-valid"}>{attempts.length ? "WARNING" : "VALID"}</State><span>{attempts.length ? `failed attempts: ${attempts.join(", ")}` : "no estimator fallback needed"}</span></div>
                {!isRealTrend && <div className="check"><State plain>{Math.abs(diagnostics.baseline_balance?.estimate ?? 0) < 1e-12 || (diagnostics.baseline_balance && diagnostics.baseline_balance.ci_low < 0 && diagnostics.baseline_balance.ci_high > 0) ? "VALID" : "WARNING"}</State><span>baseline balance {formatSignedSig(diagnostics.baseline_balance?.estimate, 3)} [{formatSig(diagnostics.baseline_balance?.ci_low, 3)}, {formatSig(diagnostics.baseline_balance?.ci_high, 3)}] {metric.unit}</span></div>}
                <div className="check"><span className="mono faint">logLik</span><span className="mono">{formatSig(diagnostics.log_likelihood, 5)}</span></div>
              </div>
              <div className="upper faint" style={{ margin: "10px 0 6px" }}>Residuals</div>
              <KV rows={[
                ["RMSE", `${formatSig(diagnostics.residual_summary?.rmse, 3)} ${metric.unit}`, "mono"],
                ["Mean residual", formatSig(diagnostics.residual_summary?.mean_residual, 2), "mono"],
                ["Max |residual|", `${formatSig(diagnostics.residual_summary?.max_abs_residual, 3)} ${metric.unit}`, "mono"],
                ...Object.entries(diagnostics.residual_by_arm ?? {}).map(([arm, value]) => [`SD · ${arm.toLowerCase()}`, `${formatSig(value.sd, 3)} (n=${value.n})`, "mono"] as [string, string, "mono"]),
              ]} />
            </div>
            <div>
              <div className="upper faint" style={{ marginBottom: 2 }}>Mean residual by week</div>
              <ResidualByWeekChart rows={diagnostics.residual_by_week ?? []} unit={metric.unit} />
              <div className="faint small">{isRealTrend ? "Residual means by testing occasion. Occasions are COND 1–4, not calendar weeks." : "Structure around weeks 11–12 is the load spike the linear week term cannot represent."}</div>
            </div>
            <div>
              <div className="upper faint" style={{ marginBottom: 2 }}>Normal QQ · standardised residuals</div>
              <QQChart points={diagnostics.residual_qq ?? []} />
              <div className="faint small">{diagnostics.residual_qq?.length} quantiles of {diagnostics.n_observations} residuals (Blom positions).</div>
            </div>
          </div>
          <div className="block-cols">
            <div>
              <div className="upper faint" style={{ marginBottom: 4 }}>Sample and missingness</div>
              <KV rows={[
                ["First trials modelled", String(diagnostics.sample_context?.valid_first_trials_used)],
                ["Athletes", String(diagnostics.n_subjects)],
                ["Obs / athlete", `${diagnostics.sample_context?.observations_per_subject_min}–${diagnostics.sample_context?.observations_per_subject_max}`],
                ["Repeat trials not modelled", String(diagnostics.sample_context?.valid_repeat_trials_not_modelled)],
                ["Excluded in cohort", `${diagnostics.sample_context?.excluded_trials_in_cohort} ${diagnostics.sample_context?.excluded_trial_ids?.length ? `(${diagnostics.sample_context.excluded_trial_ids.join(", ")})` : ""}`],
              ]} />
            </div>
            <div>
              <div className="upper faint" style={{ marginBottom: 4 }}>Assumptions and limitations</div>
              <ul style={{ margin: 0, paddingLeft: 16, color: "var(--text-2)", fontSize: 12 }}>
                {[...(diagnostics.assumptions ?? []), ...(diagnostics.limitations ?? [])].map((item) => <li key={item}>{item}</li>)}
              </ul>
            </div>
          </div>
        </>
      )}
      {run && isLong && !complete && <div className="error">{run.id} predates the computed residual diagnostics; re-run the analysis to attach them.</div>}
      {run && !isLong && (
        <>
          <KV rows={Object.entries(diagnostics).filter(([, value]) => typeof value !== "object").map(([key, value]) => [key.replaceAll("_", " "), String(value), "mono"] as [string, string, "mono"])} />
          <div className="note"><Info size={12} />{run.method_id === "METH-REL" ? "Reliability diagnostics: complete athletes, balanced trials per athlete and the computation status." : run.method_id === "METH-REAL-RELIABILITY" ? "Reliability diagnostics: complete participants, balanced trials per participant, ICC and typical error." : run.method_id === "METH-REAL-SIGNAL-QA" ? "Signal diagnostics: activity-level sampling, plate coverage, device-clock offset and body-weight comparison." : run.method_id === "METH-REAL-BODYWEIGHT" ? "Body-weight estimator diagnostics: bias, SD and limits of agreement against anthropometric metadata." : "Descriptive change: no model is fitted, so there are no residual diagnostics to report."}</div>
        </>
      )}
    </BlockFrame>
  );
}
