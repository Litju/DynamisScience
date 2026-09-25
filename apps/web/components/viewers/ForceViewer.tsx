"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowLeft, ChevronLeft, ChevronRight, Download, GitBranch, Pin } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Trial } from "@/lib/types";
import { scienceApi } from "@/lib/api";
import { formatSig } from "@/lib/scientific";
import { createBlock, insertAfter } from "@/lib/workbench";
import { ArmLabel, Button, ErrorBox, EvidencePassport, KV, Loading, State } from "@/components/ui";
import { ForceTraceChart, PHASES } from "@/components/charts";
import { useWorkbench } from "@/components/workbench/context";
import { useLibrary } from "@/components/workbench/data";

type MetricKey = keyof Pick<Trial, "concentric_impulse_n_s_kg" | "eccentric_braking_duration_s" | "eccentric_braking_impulse_n_s_kg" | "jump_height_cm" | "countermovement_depth_cm" | "peak_power_w_kg" | "rsi_mod" | "peak_force_n">;

export const TRIAL_METRICS: { key: MetricKey; label: string; unit: string; metricId: string | null; digits: number }[] = [
  { key: "concentric_impulse_n_s_kg", label: "Concentric impulse", unit: "N·s·kg⁻¹", metricId: "MET-CMJ-IMPULSE", digits: 4 },
  { key: "eccentric_braking_duration_s", label: "Eccentric braking duration", unit: "s", metricId: "MET-CMJ-BRAKING-DURATION", digits: 3 },
  { key: "eccentric_braking_impulse_n_s_kg", label: "Eccentric braking impulse", unit: "N·s·kg⁻¹", metricId: "MET-CMJ-BRAKING-IMPULSE", digits: 4 },
  { key: "jump_height_cm", label: "Jump height (flight time)", unit: "cm", metricId: "MET-CMJ-HEIGHT", digits: 3 },
  { key: "countermovement_depth_cm", label: "Countermovement depth", unit: "cm", metricId: "MET-CMJ-DEPTH", digits: 3 },
  { key: "peak_power_w_kg", label: "Peak power", unit: "W·kg⁻¹", metricId: "MET-CMJ-POWER", digits: 3 },
  { key: "rsi_mod", label: "RSI-mod", unit: "cm·s⁻¹", metricId: "MET-CMJ-RSI-MOD", digits: 4 },
  { key: "peak_force_n", label: "Peak force", unit: "N", metricId: null, digits: 4 },
];

export function ForceViewer({ trialId }: { trialId: string }) {
  const wb = useWorkbench();
  const library = useLibrary();
  const [current, setCurrent] = useState(trialId);
  const [metricKey, setMetricKey] = useState<MetricKey>("concentric_impulse_n_s_kg");
  const closeRef = useRef<HTMLButtonElement>(null);
  const restore = useRef<HTMLElement | null>(null);
  useEffect(() => setCurrent(trialId), [trialId]);
  const detail = useQuery({ queryKey: ["force-trial", current], queryFn: () => scienceApi.forceTrial(current) });
  const subjectId = detail.data?.trial.subject_id;
  const siblings = useQuery({ queryKey: ["force-trials", subjectId], queryFn: () => scienceApi.forceTrials(subjectId as string), enabled: Boolean(subjectId) });
  const traced = useMemo(() => (siblings.data ?? []).filter((trial) => trial.trace_available).sort((a, b) => a.week - b.week || a.trial_number - b.trial_number), [siblings.data]);
  const position = traced.findIndex((trial) => trial.trial_id === current);

  const close = useCallback(() => wb.closeViewer(), [wb]);
  useEffect(() => {
    restore.current = document.activeElement as HTMLElement | null;
    closeRef.current?.focus({ preventScroll: true });
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !document.querySelector(".palette-backdrop, .drawer-backdrop")) close();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      restore.current?.focus?.({ preventScroll: true });
    };
  }, [close]);

  const go = (trial: Trial | undefined) => {
    if (!trial) return;
    setCurrent(trial.trial_id);
    wb.select({ trialId: trial.trial_id, week: trial.week, athleteId: trial.subject_id });
  };
  const pin = () => {
    if (!detail.data) return;
    const anchor = wb.blocks.find((block) => block.type === "explore")?.id;
    const block = createBlock(wb.blocks, "force_trial", { title: `Force trial ${current}`, state: { trial_id: current, subject_id: detail.data.trial.subject_id } });
    wb.setBlocks((blocks) => insertAfter(blocks, block, anchor));
    wb.notify(`${current} pinned to the investigation`);
  };
  const exportCsv = () => {
    if (!detail.data?.trace_available) return;
    const rows = detail.data.trace.map((point) => [point.trial_id, point.time_s, point.force_n, point.body_weight_n, point.phase].join(","));
    const blob = new Blob([`trial_id,time_s,force_n,body_weight_n,phase\n${rows.join("\n")}\n`], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${current}-vgrf-1000hz.csv`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  const data = detail.data;
  const trial = data?.trial;
  const selected = TRIAL_METRICS.find((metric) => metric.key === metricKey) ?? TRIAL_METRICS[0];
  const definition = library.data?.metrics.find((metric) => metric.id === selected.metricId);

  return (
    <section className="viewer" role="dialog" aria-modal="false" aria-label={`Force signal viewer ${current}`}>
      <header className="viewer-head">
        <button ref={closeRef} type="button" className="btn btn-sm" onClick={close}><ArrowLeft size={12} />Return to investigation</button>
        <span className="kind">Force signal</span>
        <strong className="mono">{current}</strong>
        {trial && <span className="faint">{trial.display_id} · {trial.session_id} · week {trial.week} · trial {trial.trial_number}</span>}
        {trial && <ArmLabel arm={trial.intervention_arm} />}
        {trial && <State>{trial.quality_state}</State>}
        <span className="spacer" />
        <Button size="sm" variant="ghost" disabled={position <= 0} onClick={() => go(traced[position - 1])} aria-label="Previous traced trial"><ChevronLeft size={13} /></Button>
        <span className="mono faint small">{position >= 0 ? `${position + 1}/${traced.length} traced` : "—"}</span>
        <Button size="sm" variant="ghost" disabled={position < 0 || position >= traced.length - 1} onClick={() => go(traced[position + 1])} aria-label="Next traced trial"><ChevronRight size={13} /></Button>
        <Button size="sm" onClick={exportCsv} disabled={!data?.trace_available}><Download size={12} />CSV</Button>
        <Button size="sm" onClick={pin}><Pin size={12} />Pin</Button>
        <Button size="sm" onClick={() => wb.openLineage(current)}><GitBranch size={12} />Lineage</Button>
        <kbd>Esc</kbd>
      </header>
      <div className="viewer-body">
        {detail.isLoading && <Loading label="Loading bounded 1000 Hz trace" />}
        {detail.error && <ErrorBox error={detail.error} onRetry={() => void detail.refetch()} />}
        {data && trial && (
          <>
            {trial.quality_state === "EXCLUDED" && (
              <div className="qc-flag"><AlertTriangle size={15} /><div><strong>EXCLUDED from primary inference.</strong> {trial.exclusion_reason}. The signal stays available for audit; excluded trials are omitted from weekly means and models, never deleted.</div></div>
            )}
            <div className="viewer-grid">
              <div style={{ display: "grid", gap: 12, minWidth: 0 }}>
                <div className="chart-frame">
                  <div className="chart-cap">
                    <strong>Vertical ground reaction force</strong><span className="mono">N · 1000 Hz · {data.trace.length} samples</span>
                    <span className="legend">
                      <span><i className="swatch" style={{ background: "#dde4e8" }} />vGRF</span>
                      <span><i className="swatch" style={{ background: "#e3a74e" }} />body weight</span>
                      {PHASES.map((phase) => <span key={phase.key}><i className="swatch band" style={{ background: phase.color }} />{phase.label.toLowerCase()}</span>)}
                    </span>
                  </div>
                  {data.trace_available ? (
                    <ForceTraceChart trace={data.trace} boundaries={data.boundaries} bodyWeight={trial.body_weight_n} />
                  ) : (
                    <div className="empty" style={{ padding: 30, textAlign: "center" }}>Raw 1000 Hz trace not retained for this trial (traces are kept on audit weeks 1, 6, 10, 12 and 16). Phase boundaries and derived metrics below remain inspectable.</div>
                  )}
                </div>
                <div className="block-cols">
                  <div className="frame">
                    <div className="frame-head"><h3>Phases</h3><span className="faint small">{data.method.phase_detection}</span></div>
                    <table className="table phase-table">
                      <thead><tr><th /><th>Phase</th><th className="r">Start (s)</th><th className="r">End (s)</th><th className="r">Duration (s)</th></tr></thead>
                      <tbody>
                        <tr><td><i className="phase-key" style={{ background: "#56636b" }} /></td><td>Quiet standing</td><td className="r mono">0.000</td><td className="r mono">{data.boundaries.movement_onset.toFixed(3)}</td><td className="r mono">{data.boundaries.movement_onset.toFixed(3)}</td></tr>
                        {PHASES.map((phase) => (
                          <tr key={phase.key}><td><i className="phase-key" style={{ background: phase.color }} /></td><td>{phase.label}</td><td className="r mono">{data.boundaries[phase.from].toFixed(3)}</td><td className="r mono">{data.boundaries[phase.to].toFixed(3)}</td><td className="r mono">{(data.boundaries[phase.to] - data.boundaries[phase.from]).toFixed(3)}</td></tr>
                        ))}
                        <tr><td><i className="phase-key" style={{ background: "#7d8a92" }} /></td><td>Landing</td><td className="r mono">{data.boundaries.landing.toFixed(3)}</td><td className="r mono">—</td><td className="r mono">—</td></tr>
                      </tbody>
                    </table>
                  </div>
                  <div className="frame">
                    <div className="frame-head"><h3>Derived metrics</h3><span className="faint small">{data.method.algorithm}@{data.method.algorithm_version} · click for passport</span></div>
                    <table className="table metric-table">
                      <tbody>
                        {TRIAL_METRICS.map((metric) => (
                          <tr key={metric.key} className={metric.key === metricKey ? "is-selected" : ""} role="button" tabIndex={0} onClick={() => setMetricKey(metric.key)} onKeyDown={(event) => event.key === "Enter" && setMetricKey(metric.key)}>
                            <td>{metric.label}</td>
                            <td className="r mono">{formatSig(trial[metric.key], metric.digits)}<span className="unit">{metric.unit}</span></td>
                            <td className="mono faint small">{metric.metricId ?? "unregistered"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    <div className="note" style={{ padding: "6px 8px" }}>Jump height here is the flight-time definition (MET-CMJ-HEIGHT, g·t²/8). The impulse-momentum definition (MET-CMJ-HEIGHT-IMPULSE) is a separate MetricDefinition with the same unit; it is not materialised in DS-SYNTH-001, so no value is shown for it. Peak force has no registered MetricDefinition.</div>
                  </div>
                </div>
              </div>
              <div className="viewer-side">
                <EvidencePassport
                  metricLabel={selected.label}
                  value={trial[selected.key]}
                  unit={selected.unit}
                  metricId={selected.metricId ?? "no registered MetricDefinition"}
                  canonicalId={definition?.canonical_id}
                  method={definition?.method}
                  algorithm={`${data.method.algorithm}@${data.method.algorithm_version}`}
                  protocolId={data.method.protocol_id}
                  sourceId={trial.trial_id}
                  snapshotId={data.provenance.snapshot_id}
                  quality={trial.quality_state}
                  checksum={data.provenance.traces_checksum}
                  reproducible
                  onInspectSource={() => wb.inspect({ kind: "trial", id: trial.trial_id })}
                  onInspectMethod={selected.metricId ? () => wb.inspect({ kind: "metric", id: selected.metricId as string }) : undefined}
                  onInspectLineage={() => wb.openLineage(trial.trial_id)}
                />
                <div className="frame">
                  <div className="frame-head"><h3>Measurement</h3></div>
                  <div className="frame-body">
                    <KV rows={[
                      ["Athlete", `${trial.display_id} · ${data.subject.position}`],
                      ["Body mass", `${trial.body_mass_kg.toFixed(2)} kg`],
                      ["Body weight", `${trial.body_weight_n.toFixed(1)} N`],
                      ["Sample rate", `${data.method.sample_rate_hz} Hz`],
                      ["Integration", data.method.integration],
                      ["Source", data.provenance.source, "mono"],
                      ["Seed", String(data.provenance.seed), "mono"],
                    ]} />
                  </div>
                </div>
                {definition && (
                  <div className="frame">
                    <div className="frame-head"><h3>Known limitations</h3><span className="mono faint small">{definition.id}</span></div>
                    <div className="frame-body"><ul style={{ margin: 0, paddingLeft: 16, color: "var(--text-2)", fontSize: 12 }}>{definition.known_limitations.map((item) => <li key={item}>{item}</li>)}</ul></div>
                  </div>
                )}
              </div>
            </div>
          </>
        )}
      </div>
    </section>
  );
}
