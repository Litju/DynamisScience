"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Plus } from "lucide-react";
import { performanceApi } from "@/lib/performance/api";
import { fmt, fmtSigned, severityTone } from "@/lib/performance/format";
import { ForceTimeChart, Sparkline, TrendChart } from "./charts";
import { Drawer, PosChip, PosEmpty, PosError, PosLoading, PosReadout, Toast } from "./ui";

const TABS = [
  ["overview", "Overview"],
  ["wellness", "Wellness"],
  ["load", "Load"],
  ["testing", "Testing"],
  ["movement", "Movement"],
  ["research", "Research"],
] as const;

type Tab = typeof TABS[number][0];

export function AthleteView({ athleteId }: { athleteId: string }) {
  const client = useQueryClient();
  const athlete = useQuery({ queryKey: ["performance-athlete", athleteId], queryFn: () => performanceApi.athlete(athleteId) });
  const [tab, setTab] = useState<Tab>("overview");
  const [metric, setMetric] = useState<"cmj" | "readiness" | "load" | "sleep">("cmj");
  const [noteOpen, setNoteOpen] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [note, setNote] = useState("");

  useEffect(() => {
    const requested = new URLSearchParams(window.location.search).get("tab") as Tab | null;
    if (requested && TABS.some(([id]) => id === requested)) setTab(requested);
  }, []);

  const noteMutation = useMutation({
    mutationFn: () => performanceApi.addNote(athleteId, note, "Head of Performance"),
    onSuccess: () => {
      setNote("");
      setNoteOpen(false);
      void client.invalidateQueries({ queryKey: ["performance-athlete", athleteId] });
      setToast("Performance note saved. It is not a clinical record.");
      window.setTimeout(() => setToast(null), 4200);
    },
  });

  if (athlete.isLoading) return <div className="pos-page"><div className="pos-main"><PosLoading label={`Reading ${athleteId} longitudinal record`} /></div></div>;
  if (athlete.error) return <div className="pos-page"><div className="pos-main"><PosError error={athlete.error} onRetry={() => void athlete.refetch()} /></div></div>;
  const data = athlete.data!;
  const current = data.current;
  const weeks = data.weeks;
  const baselineValues = weeks.filter((week) => data.baseline_weeks.includes(week.week)).map((week) => week.cmj_height_cm).filter((value): value is number => value !== null);
  const baselineBand: [number, number] | null = baselineValues.length ? [Math.min(...baselineValues), Math.max(...baselineValues)] : null;
  const readinessBaseline = weeks.filter((week) => data.baseline_weeks.includes(week.week)).map((week) => week.readiness).filter((value): value is number => value !== null);
  const readinessBand: [number, number] | null = readinessBaseline.length ? [Math.min(...readinessBaseline), Math.max(...readinessBaseline)] : null;
  const loadValues = weeks.map((week) => week.training_impulse_au);
  const cmjValues = weeks.map((week) => week.cmj_height_cm);
  const metricConfig = {
    cmj: { label: "CMJ height", unit: "cm", color: "#5fd4e8", values: cmjValues, band: baselineBand, reference: current.baseline_cmj_height_cm, digits: 2 },
    readiness: { label: "Readiness", unit: "0–10", color: "#c8f36b", values: weeks.map((week) => week.readiness), band: readinessBand, reference: data.weeks.slice(0, 4).reduce((sum, week) => sum + (week.readiness ?? 0), 0) / 4, digits: 1 },
    load: { label: "Training impulse", unit: "AU", color: "#e0a458", values: loadValues, band: null, reference: null, digits: 1 },
    sleep: { label: "Sleep", unit: "h", color: "#a78bfa", values: weeks.map((week) => week.sleep_hours), band: null, reference: 7.5, digits: 2 },
  }[metric];

  return (
    <div className="pos-page">
      <main className="pos-main" aria-label={`Athlete 360 · ${athleteId}`}>
        <div className="pos-athlete-head">
          <div>
            <Link href="/today" className="pos-link" style={{ display: "inline-flex", alignItems: "center", gap: 4, marginBottom: 6 }}><ArrowLeft size={10} />Back to squad command</Link>
            <div className="pos-athlete-identity">
              <div className="pos-avatar-lg">{data.subject.display_id.replace("ATH-", "")}</div>
              <div>
                <h1>{data.subject.display_id}</h1>
                <div className="pos-athlete-meta">
                  <PosChip tone="info">{data.subject.position}</PosChip>
                  <span>age {data.subject.age}</span>
                  <span>{fmt(data.subject.height_cm, 1)} cm</span>
                  <span>{fmt(data.subject.body_mass_kg, 1)} kg</span>
                  <span>training age {data.subject.training_age_years} y</span>
                  <PosChip tone="warn">ROSTER ONLY</PosChip>
                  <span className="pos-faint">Subject {data.subject.subject_id}</span>
                </div>
              </div>
            </div>
            <p style={{ marginTop: 6, color: "var(--pos-muted)", fontSize: 9 }}>One athlete model across wellness, load, testing, movement and research. Availability is roster status only; no injury table is admitted.</p>
          </div>
          <div className="pos-actions">
            <Link href={`/monitor?athlete=${athleteId}`} className="pos-btn">Monitor trajectory</Link>
            <button type="button" className="pos-btn" onClick={() => setNoteOpen(true)}><Plus size={10} />Performance note</button>
            <Link href={`/research/studies/${data.study.id}`} className="pos-btn">Open linked study</Link>
          </div>
        </div>

        <div className="pos-stat-strip">
          <PosReadout label="Readiness" value={fmt(current.readiness, 1)} unit="/10" detail={`sleep ${fmt(current.sleep_hours, 1)} h`} />
          <PosReadout label="Load ratio" value={fmt(current.load_ratio, 2)} unit="AU" detail="4-week baseline" />
          <PosReadout label="CMJ latest" value={fmt(current.cmj_height_cm, 2)} unit="cm" detail={`baseline ${fmt(current.baseline_cmj_height_cm, 2)} cm`} />
          <PosReadout label="CMJ change" value={fmtSigned(current.cmj_delta_pct, 1)} unit="" detail={`vs weeks 1–4 · TE context`} />
          <PosReadout label="Trials" value={`${current.cmj_trials - current.cmj_excluded}/${current.cmj_trials}`} unit="" detail={current.cmj_excluded ? `${current.cmj_excluded} excluded · missing visible` : "valid trials · no missing"} />
        </div>

        <div className="pos-tabs" role="tablist" aria-label="Athlete 360 sections">
          {TABS.map(([id, label]) => (
            <button key={id} type="button" role="tab" aria-selected={tab === id} className={`pos-tab ${tab === id ? "is-active" : ""}`} onClick={() => setTab(id)}>{label}</button>
          ))}
        </div>

        {tab === "overview" ? (
          <>
            <div className="pos-grid-2" style={{ gridTemplateColumns: "1.5fr 1fr", alignItems: "start" }}>
              <section className="pos-chart-frame">
                <div className="pos-module-head">
                  <h2>{metricConfig.label} trajectory</h2>
                  <span className="sub">{metricConfig.unit} · 16 weeks · own baseline band W1–4</span>
                  <span className="right">
                    <select aria-label="Trend metric" value={metric} onChange={(event) => setMetric(event.target.value as typeof metric)} className="pos-select">
                      <option value="cmj">CMJ height</option>
                      <option value="readiness">Readiness</option>
                      <option value="load">Training impulse</option>
                      <option value="sleep">Sleep</option>
                    </select>
                  </span>
                </div>
                <div className="chart">
                  <TrendChart
                    data={weeks.map((week) => ({ week: week.week, value: metric === "cmj" ? week.cmj_height_cm : metric === "readiness" ? week.readiness : metric === "load" ? week.training_impulse_au : week.sleep_hours, phase: week.phase }))}
                    unit={metricConfig.unit}
                    band={metricConfig.band}
                    bandLabel={metricConfig.band ? "own W1–4 baseline range" : undefined}
                    reference={metricConfig.reference}
                    referenceLabel={metric === "sleep" ? "reference" : "baseline mean"}
                    color={metricConfig.color}
                    digits={metricConfig.digits}
                    height={240}
                  />
                </div>
                <div className="pos-legend">
                  <span><i style={{ background: metricConfig.color }} />observed</span>
                  <span><i className="band" style={{ background: "#c8f36b" }} />baseline band</span>
                  <span><i style={{ background: "#ef6b63", height: 3, width: 3, borderRadius: "50%" }} />missing week</span>
                  <span className="right" style={{ marginLeft: "auto" }}>Descriptive; no causal claim</span>
                </div>
              </section>

              <div style={{ display: "grid", gap: 9 }}>
                <section className="pos-module">
                  <div className="pos-module-head"><h2>Individual change</h2><span className="sub">W16 vs W1–4</span></div>
                  <div className="pos-module-body">
                    <div className="pos-estimate" style={{ border: "1px solid var(--pos-line)", borderLeft: "2px solid var(--pos-lime)", padding: "8px 10px", background: "var(--pos-panel-2)" }}>
                      <div className="pos-k">CMJ height change</div>
                      <div style={{ fontFamily: "var(--pos-mono)", fontSize: 24, color: "var(--pos-text)" }}>{fmtSigned(current.cmj_delta_pct, 1)}</div>
                      <div className="pos-note">{fmt(data.individual_change.change_cm, 2)} cm · baseline {fmt(data.individual_change.baseline_mean, 2)} cm → current {fmt(data.individual_change.current_mean, 2)} cm</div>
                    </div>
                    <p className="pos-note" style={{ marginTop: 6 }}>{data.individual_change.limitations}</p>
                    <div className="pos-hr" />
                    <dl className="pos-kv">
                      <dt>Force trial</dt><dd>{data.force_trial_id ?? "not available"}</dd>
                      <dt>Peak force</dt><dd>{fmt(data.force_trial?.peak_force_n, 0)} N</dd>
                      <dt>Impulse</dt><dd>{fmt(data.force_trial?.concentric_impulse_n_s_kg, 3)} N·s·kg⁻¹</dd>
                      <dt>RSI mod</dt><dd>{fmt(data.force_trial?.rsi_mod, 1)} cm/s</dd>
                    </dl>
                  </div>
                </section>
                <section className="pos-module">
                  <div className="pos-module-head"><h2>Availability</h2><span className="sub">roster status only</span></div>
                  <div className="pos-module-body">
                    <PosEmpty title="Injury module unavailable" info>
                      No injury, exposure or return-to-play table is admitted. This athlete is available on the roster; the product does not infer injury risk or clearance.
                    </PosEmpty>
                  </div>
                </section>
              </div>
            </div>

            <div className="pos-grid-3">
              <section className="pos-card">
                <div className="pos-k">Wellness · week 16</div>
                <div className="pos-metric-value">{fmt(current.readiness, 1)}<span className="u">/10 readiness</span></div>
                <div className="pos-note">sleep {fmt(current.sleep_hours, 1)} h · soreness {fmt(current.soreness, 1)} · fatigue {fmt(current.fatigue, 1)}</div>
                <div style={{ marginTop: 6 }}><Sparkline values={weeks.map((week) => week.readiness)} width={220} height={32} color="#c8f36b" band={readinessBand} /></div>
              </section>
              <section className="pos-card">
                <div className="pos-k">Training load · week 16</div>
                <div className="pos-metric-value">{fmt(current.training_impulse_au, 1)}<span className="u">AU</span></div>
                <div className="pos-note">load ratio {fmt(current.load_ratio, 2)} · {fmt(current.session_count, 0)} sessions · {fmt(current.duration_min, 0)} min</div>
                <div style={{ marginTop: 6 }}><Sparkline values={loadValues} width={220} height={32} color="#e0a458" /></div>
              </section>
              <section className="pos-card">
                <div className="pos-k">CMJ · week 16</div>
                <div className="pos-metric-value">{fmt(current.cmj_height_cm, 2)}<span className="u">cm</span></div>
                <div className="pos-note">baseline {fmt(current.baseline_cmj_height_cm, 2)} cm · {current.cmj_trials} trials</div>
                <div style={{ marginTop: 6 }}><Sparkline values={cmjValues} width={220} height={32} color="#5fd4e8" band={baselineBand} /></div>
              </section>
            </div>

            <section className="pos-module">
              <div className="pos-module-head"><h2>All flags for this athlete</h2><span className="sub">thresholds and owners in the atlas</span><span className="right"><PosChip tone={data.athlete.flags.length ? "warn" : "ok"}>{data.athlete.flags.length} flag{data.athlete.flags.length === 1 ? "" : "s"}</PosChip></span></div>
              <div className="pos-module-body">
                {data.athlete.flags.length === 0 ? <div className="pos-note">No threshold breach at week 16.</div> : (
                  <table className="pos-table">
                    <thead><tr><th>Flag</th><th>Value</th><th>Threshold</th><th>Detail</th><th>Owner</th></tr></thead>
                    <tbody>
                      {data.athlete.flags.map((flag) => (
                        <tr key={flag.rule}>
                          <td><PosChip tone={severityTone(flag.severity)}>{flag.label}</PosChip></td>
                          <td className="mono">{fmt(flag.value, flag.unit === "%" ? 1 : 2)} {flag.unit}</td>
                          <td className="mono">{flag.threshold} {flag.unit}</td>
                          <td>{flag.detail}</td>
                          <td>{(data.thresholds.find((threshold) => threshold.id === flag.rule)?.owner) ?? "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </section>
          </>
        ) : null}

        {tab === "wellness" ? (
          <div className="pos-grid-2" style={{ gridTemplateColumns: "1.5fr 1fr", alignItems: "start" }}>
            <section className="pos-chart-frame">
              <div className="pos-module-head"><h2>Readiness</h2><span className="sub">0–10 · 16 weeks · own baseline band</span></div>
              <div className="chart"><TrendChart data={weeks.map((week) => ({ week: week.week, value: week.readiness, phase: week.phase }))} unit="0–10" band={readinessBand} bandLabel="own W1–4 range" reference={data.weeks.slice(0, 4).reduce((sum, week) => sum + (week.readiness ?? 0), 0) / 4} referenceLabel="baseline mean" color="#c8f36b" height={240} digits={1} /></div>
              <div className="pos-legend"><span><i style={{ background: "#c8f36b" }} />readiness</span><span>Missing is visible; never zero-filled</span></div>
            </section>
            <section className="pos-module">
              <div className="pos-module-head"><h2>Week 16 wellness</h2><span className="sub">self-report · 0–10</span></div>
              <div className="pos-module-body">
                <dl className="pos-kv">
                  <dt>Readiness</dt><dd>{fmt(current.readiness, 1)} / 10</dd>
                  <dt>Sleep</dt><dd>{fmt(current.sleep_hours, 2)} h</dd>
                  <dt>Soreness</dt><dd>{fmt(current.soreness, 2)} / 10</dd>
                  <dt>Fatigue</dt><dd>{fmt(current.fatigue, 2)} / 10</dd>
                  <dt>Source</dt><dd>wellness.parquet · W16</dd>
                  <dt>Sample</dt><dd>1 record · athlete</dd>
                </dl>
                <div className="pos-hr" />
                <div className="pos-note">Wellness is a self-report questionnaire. It is not a clinical assessment, diagnosis or return-to-play criterion.</div>
              </div>
            </section>
            <section className="pos-module" style={{ gridColumn: "1 / -1" }}>
              <div className="pos-module-head"><h2>Wellness ledger</h2><span className="sub">week · readiness · sleep · soreness · fatigue · phase</span></div>
              <div className="pos-module-body flush">
                <table className="pos-table">
                  <thead><tr><th>Week</th><th>Phase</th><th className="r">Readiness</th><th className="r">Sleep h</th><th className="r">Soreness</th><th className="r">Fatigue</th><th>Flag</th></tr></thead>
                  <tbody>
                    {weeks.slice().reverse().map((week) => (
                      <tr key={week.week}>
                        <td className="mono">W{week.week}</td>
                        <td>{week.phase}</td>
                        <td className="r">{fmt(week.readiness, 1)}</td>
                        <td className="r">{fmt(week.sleep_hours, 2)}</td>
                        <td className="r">{fmt(week.soreness, 2)}</td>
                        <td className="r">{fmt(week.fatigue, 2)}</td>
                        <td>{week.readiness !== null && week.readiness < 5.5 ? <PosChip tone="bad">Readiness</PosChip> : week.soreness !== null && week.soreness > 7 ? <PosChip tone="warn">Soreness</PosChip> : <span className="pos-faint">—</span>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          </div>
        ) : null}

        {tab === "load" ? (
          <div className="pos-grid-2" style={{ gridTemplateColumns: "1.5fr 1fr", alignItems: "start" }}>
            <section className="pos-chart-frame">
              <div className="pos-module-head"><h2>Training impulse</h2><span className="sub">AU · weekly athlete value</span></div>
              <div className="chart"><TrendChart data={weeks.map((week) => ({ week: week.week, value: week.training_impulse_au, phase: week.phase }))} unit="AU" color="#e0a458" height={240} digits={1} /></div>
              <div className="pos-legend"><span><i style={{ background: "#e0a458" }} />actual load</span><span>No planned target recorded for this athlete</span></div>
            </section>
            <section className="pos-module">
              <div className="pos-module-head"><h2>Week 16 load</h2><span className="sub">actual · AU</span></div>
              <div className="pos-module-body">
                <dl className="pos-kv">
                  <dt>Training impulse</dt><dd>{fmt(current.training_impulse_au, 1)} AU</dd>
                  <dt>External load</dt><dd>{fmt(current.external_load_au, 1)} AU</dd>
                  <dt>HSR distance</dt><dd>{fmt(current.hsr_distance_m, 1)} m</dd>
                  <dt>Session RPE</dt><dd>{fmt(current.session_rpe, 2)}</dd>
                  <dt>Match minutes</dt><dd>{fmt(current.match_minutes, 0)} min</dd>
                  <dt>Load ratio</dt><dd>{fmt(current.load_ratio, 2)} AU</dd>
                </dl>
                <div className="pos-hr" />
                <div className="pos-warn-note">Load ratio is descriptive context from a 4-week baseline. It is not an injury predictor.</div>
              </div>
            </section>
            <section className="pos-module" style={{ gridColumn: "1 / -1" }}>
              <div className="pos-module-head"><h2>Load ledger</h2><span className="sub">week · TI · external · HSR · RPE · match min · ratio</span></div>
              <div className="pos-module-body flush">
                <table className="pos-table">
                  <thead><tr><th>Week</th><th className="r">TI AU</th><th className="r">External AU</th><th className="r">HSR m</th><th className="r">RPE</th><th className="r">Match min</th><th className="r">Load ratio</th></tr></thead>
                  <tbody>{weeks.slice().reverse().map((week) => <tr key={week.week}><td className="mono">W{week.week}</td><td className="r">{fmt(week.training_impulse_au, 1)}</td><td className="r">{fmt(week.external_load_au, 1)}</td><td className="r">{fmt(week.hsr_distance_m, 1)}</td><td className="r">{fmt(week.session_rpe, 2)}</td><td className="r">{fmt(week.match_minutes, 0)}</td><td className="r">{fmt(week.load_ratio, 2)}</td></tr>)}</tbody>
                </table>
              </div>
            </section>
          </div>
        ) : null}

        {tab === "testing" ? (
          <div className="pos-grid-2" style={{ gridTemplateColumns: "1.4fr 1fr", alignItems: "start" }}>
            <section className="pos-module">
              <div className="pos-module-head"><h2>CMJ force–time · {data.force_trial_id ?? "no trace"}</h2><span className="sub">1000 Hz · {data.force_trial?.quality_state ?? "not available"}</span><span className="right"><PosChip tone="ok">VALID</PosChip><PosChip tone="info">SYNTHETIC</PosChip></span></div>
              <div className="pos-module-body">
                <ForceTrialForAthlete trialId={data.force_trial_id} />
              </div>
            </section>
            <div style={{ display: "grid", gap: 9 }}>
              <section className="pos-module">
                <div className="pos-module-head"><h2>Trial metrics</h2><span className="sub">week 16 audit trial</span></div>
                <div className="pos-module-body">
                  <dl className="pos-kv">
                    <dt>Jump height</dt><dd>{fmt(data.force_trial?.jump_height_cm, 2)} cm</dd>
                    <dt>Peak force</dt><dd>{fmt(data.force_trial?.peak_force_n, 0)} N</dd>
                    <dt>Concentric impulse</dt><dd>{fmt(data.force_trial?.concentric_impulse_n_s_kg, 3)} N·s·kg⁻¹</dd>
                    <dt>RSI modified</dt><dd>{fmt(data.force_trial?.rsi_mod, 1)} cm/s</dd>
                    <dt>Quality</dt><dd>{data.force_trial?.quality_state ?? "—"}</dd>
                    <dt>Device record</dt><dd>not admitted</dd>
                  </dl>
                  <div className="pos-hr" />
                  <div className="pos-note">Device serial, calibration date and plate coverage are not admitted. Reliability is within-session trial agreement, not device agreement.</div>
                </div>
              </section>
              <section className="pos-module">
                <div className="pos-module-head"><h2>Test history</h2><span className="sub">CMJ mean by week</span></div>
                <div className="pos-module-body flush">
                  <table className="pos-table">
                    <thead><tr><th>Week</th><th className="r">CMJ cm</th><th className="r">Δ baseline</th><th>Quality</th></tr></thead>
                    <tbody>{weeks.slice().reverse().map((week) => <tr key={week.week}><td className="mono">W{week.week}</td><td className="r">{fmt(week.cmj_height_cm, 2)}</td><td className="r">{fmtSigned(week.cmj_delta_pct, 1)}</td><td>{week.cmj_missing ? <PosChip tone="bad">MISSING</PosChip> : week.cmj_excluded ? <PosChip tone="warn">EXCLUDED</PosChip> : <PosChip tone="ok">VALID</PosChip>}</td></tr>)}</tbody>
                  </table>
                </div>
              </section>
            </div>
          </div>
        ) : null}

        {tab === "movement" ? (
          <div className="pos-grid-2" style={{ gridTemplateColumns: "1.4fr 1fr", alignItems: "start" }}>
            <section className="pos-module">
              <div className="pos-module-head"><h2>Bounded tracking segment</h2><span className="sub">3-minute window · 10 Hz · segment only</span><span className="right"><PosChip tone="info">SEGMENT</PosChip></span></div>
              <div className="pos-module-body">
                {data.movement ? (
                  <>
                    <div className="pos-grid-3">
                      <div className="pos-card"><div className="pos-k">Distance</div><div className="pos-metric-value">{fmt(data.movement.distance_m, 1)}<span className="u">m</span></div><div className="pos-note">positional path length</div></div>
                      <div className="pos-card"><div className="pos-k">HSR</div><div className="pos-metric-value">{fmt(data.movement.hsr_m, 1)}<span className="u">m</span></div><div className="pos-note">&gt;5.0 m·s⁻¹</div></div>
                      <div className="pos-card"><div className="pos-k">Max speed</div><div className="pos-metric-value">{fmt(data.movement.max_speed_m_s, 1)}<span className="u">m·s⁻¹</span></div><div className="pos-note">segment peak</div></div>
                    </div>
                    <div className="pos-callout info" style={{ marginTop: 8 }}><b>Not full-match distance.</b> Tracking channel {data.movement.player_id}; this is a 180 s bounded segment with {data.movement.position_resets} position resets. It is not a GPS device validation and not an athlete identity mapping.</div>
                  </>
                ) : <PosEmpty title="No movement segment admitted">No tracking channel is linked to this athlete.</PosEmpty>}
              </div>
            </section>
            <section className="pos-module">
              <div className="pos-module-head"><h2>Identity</h2><span className="sub">one athlete model</span></div>
              <div className="pos-module-body">
                <PosEmpty title="Tracking mapping not admitted" info>
                  The snapshot has tracking channels PLAYER-07, 09, 11 and 14 but no roster-to-channel mapping. The product does not claim this athlete is PLAYER-14. The Movement workspace shows the admitted segment as a separate entity.
                </PosEmpty>
              </div>
            </section>
          </div>
        ) : null}

        {tab === "research" ? (
          <div className="pos-grid-2" style={{ gridTemplateColumns: "1.35fr 1fr", alignItems: "start" }}>
            <section className="pos-module">
              <div className="pos-module-head"><h2>{data.study.title}</h2><span className="sub">{data.study.participants} athletes · weeks {data.study.weeks[0]}–{data.study.weeks[1]}</span><span className="right"><PosChip tone="warn">SYNTHETIC</PosChip></span></div>
              <div className="pos-module-body">
                <p style={{ fontSize: 9, color: "var(--pos-text-2)", lineHeight: 1.55 }}>{data.study.design}</p>
                <div className="pos-hr" />
                <div className="pos-section-title"><h2>Primary evidence</h2><span>not an individual prediction</span></div>
                {data.study.primary_evidence.map((item) => (
                  <div key={item.id} className="pos-research-card" style={{ marginTop: 6 }}>
                    <div className="k">{item.id} · {item.evidence_class} · {item.quality}</div>
                    <b>{item.title}</b>
                    <p>{item.interpretation}</p>
                    <div className="pos-note" style={{ marginTop: 3 }}>{fmt(item.estimate, 3)} {item.unit}{item.interval ? ` · 95% CI ${fmt(item.interval.low, 3)} to ${fmt(item.interval.high, 3)}` : ""}</div>
                  </div>
                ))}
                <div style={{ marginTop: 8 }}><Link href={`/research/studies/${data.study.id}`} className="pos-link">Open study workbench →</Link></div>
              </div>
            </section>
            <section className="pos-module">
              <div className="pos-module-head"><h2>Evidence limits</h2><span className="sub">what cannot be claimed</span></div>
              <div className="pos-module-body">
                {data.study.limitations.map((limit) => <div key={limit} className="pos-note" style={{ marginBottom: 5 }}>— {limit}</div>)}
                <div className="pos-hr" />
                <div className="pos-note">Research evidence is cohort-level. It does not diagnose this athlete, predict injury or establish a causal individual response.</div>
              </div>
            </section>
          </div>
        ) : null}
      </main>

      <aside className="pos-aside" aria-label="Athlete context">
        <div className="pos-aside-sec">
          <h3>Current flags</h3>
          {data.athlete.flags.length ? data.athlete.flags.map((flag) => (
            <div key={flag.rule} style={{ marginBottom: 5 }}>
              <PosChip tone={severityTone(flag.severity)}>{flag.label}</PosChip>
              <div className="pos-note" style={{ marginTop: 2 }}>{flag.detail}</div>
            </div>
          )) : <div className="pos-note">No threshold breach at week 16.</div>}
        </div>
        <div className="pos-aside-sec">
          <h3>References</h3>
          <dl className="pos-kv">
            <dt>Baseline</dt><dd>weeks 1–4</dd>
            <dt>CMJ baseline</dt><dd>{fmt(current.baseline_cmj_height_cm, 2)} cm</dd>
            <dt>Readiness</dt><dd>0–10 self-report</dd>
            <dt>Load ratio</dt><dd>4-week baseline</dd>
            <dt>As of</dt><dd>{data.as_of.slice(0, 10)}</dd>
          </dl>
        </div>
        <div className="pos-aside-sec">
          <h3>Performance notes</h3>
          <button type="button" className="pos-btn small" onClick={() => setNoteOpen(true)}><Plus size={10} />Add note</button>
          <div style={{ marginTop: 6 }}>
            {data.notes.length === 0 ? <div className="pos-note">No coach-entered note for this athlete.</div> : data.notes.slice().reverse().map((note) => (
              <div key={note.id} className="pos-research-card" style={{ marginBottom: 5 }}>
                <div className="k">{note.created_at.slice(0, 10)} · {note.author_role}</div>
                <p>{note.text}</p>
                <div className="pos-note" style={{ marginTop: 2 }}>{note.source_label}</div>
              </div>
            ))}
          </div>
        </div>
        <div className="pos-aside-sec">
          <div className="pos-callout"><b>No clinical record.</b> Notes are performance observations entered by staff. They are not diagnosis, injury surveillance or return-to-play evidence.</div>
        </div>
        <div className="pos-aside-foot">Athlete 360 · {data.subject.display_id}<br />Snapshot DS-SYNTH-001 · synthetic<br /><b>ONE ATHLETE IDENTITY</b></div>
      </aside>

      {noteOpen ? (
        <Drawer title="Performance note" subtitle="User-entered · not clinical" onClose={() => setNoteOpen(false)}>
          <label className="pos-field"><span>Note</span><textarea value={note} onChange={(event) => setNote(event.target.value)} placeholder="Observation, context or follow-up action. Do not record diagnosis or injury status." /></label>
          <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
            <button type="button" className="pos-btn primary" disabled={!note.trim() || noteMutation.isPending} onClick={() => noteMutation.mutate()}><Plus size={10} />{noteMutation.isPending ? "Saving…" : "Save note"}</button>
            <button type="button" className="pos-btn" onClick={() => setNoteOpen(false)}>Cancel</button>
          </div>
          {noteMutation.error ? <PosError error={noteMutation.error} /> : null}
        </Drawer>
      ) : null}
      <Toast message={toast} />
    </div>
  );
}

function ForceTrialForAthlete({ trialId }: { trialId: string | null }) {
  const trial = useQuery({
    queryKey: ["performance-force", trialId],
    queryFn: () => performanceApi.forceTrial(trialId!),
    enabled: Boolean(trialId),
  });
  if (!trialId) return <PosEmpty title="No force trace">No audit trial is available for this athlete.</PosEmpty>;
  if (trial.isLoading) return <PosLoading label="Reading force trace" />;
  if (trial.error) return <PosError error={trial.error} />;
  if (!trial.data) return null;
  return (
    <>
      <ForceTimeChart trace={trial.data.trace} bodyWeight={trial.data.trial.body_weight_n} height={250} />
      <div className="pos-force-legend">
        <span><i style={{ background: "rgba(127,145,157,.5)" }} />Standing</span>
        <span><i style={{ background: "rgba(95,212,232,.5)" }} />Unweight</span>
        <span><i style={{ background: "rgba(224,164,88,.5)" }} />Brake</span>
        <span><i style={{ background: "rgba(200,243,107,.5)" }} />Propulsion</span>
        <span><i style={{ background: "rgba(167,139,250,.5)" }} />Flight</span>
        <span><i style={{ background: "rgba(239,107,99,.5)" }} />Landing</span>
        <span className="right">{trial.data.method.sample_rate_hz} Hz · {trial.data.method.algorithm}</span>
      </div>
    </>
  );
}
