"use client";

import Link from "next/link";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { performanceApi } from "@/lib/performance/api";
import { fmt, fmtSigned, severityTone, todayLabel } from "@/lib/performance/format";
import type { AthleteFlag } from "@/lib/performance/types";
import { ForceTimeChart, LoadLineChart } from "./charts";
import { Drawer, PosChip, PosEmpty, PosError, PosLoading, Toast } from "./ui";

function shortFlagDetail(flag: AthleteFlag): string {
  if (flag.rule === "readiness_low") return "lowest readiness";
  if (flag.rule === "load_ratio_high") return "4-week baseline";
  if (flag.rule === "cmj_drop") return "vs weeks 1–4";
  if (flag.rule === "soreness_high") return `soreness ${fmt(flag.value, 1)}/10`;
  return flag.detail;
}

function SessionLogForm({ onDone, onClose }: { onDone: (message: string) => void; onClose: () => void }) {
  const client = useQueryClient();
  const [form, setForm] = useState({
    date: new Date().toISOString().slice(0, 10),
    session_type: "Field",
    duration_min: 75,
    session_rpe: 6,
    attendance: 28,
    notes: "",
  });
  const mutation = useMutation({
    mutationFn: () => performanceApi.logSession({ ...form, author_role: "Head of Performance" }),
    onSuccess: (record) => {
      void client.invalidateQueries({ queryKey: ["performance-today"] });
      onDone(`Session recorded · ${fmt(record.srpe_load_au, 1)} AU (duration × RPE). Source: coach-entered.`);
      onClose();
    },
  });
  return (
    <div style={{ display: "grid", gap: 10 }}>
      <div className="pos-callout info">
        <b>Operational log, not a measurement.</b> The fixture tables stay immutable. This entry is stored separately and labelled coach-entered.
      </div>
      <div className="pos-form-grid">
        <label className="pos-field"><span>Date</span><input type="date" value={form.date} onChange={(event) => setForm({ ...form, date: event.target.value })} /></label>
        <label className="pos-field"><span>Session type</span><select value={form.session_type} onChange={(event) => setForm({ ...form, session_type: event.target.value })}><option>Field</option><option>Strength</option><option>Recovery</option><option>Match</option><option>Testing</option></select></label>
        <label className="pos-field"><span>Duration (min)</span><input type="number" min={1} max={600} value={form.duration_min} onChange={(event) => setForm({ ...form, duration_min: Number(event.target.value) })} /></label>
        <label className="pos-field"><span>Session RPE (0–10)</span><input type="number" min={0} max={10} step={0.5} value={form.session_rpe} onChange={(event) => setForm({ ...form, session_rpe: Number(event.target.value) })} /></label>
        <label className="pos-field"><span>Attendance</span><input type="number" min={0} max={200} value={form.attendance} onChange={(event) => setForm({ ...form, attendance: Number(event.target.value) })} /></label>
      </div>
      <label className="pos-field"><span>Notes</span><textarea value={form.notes} onChange={(event) => setForm({ ...form, notes: event.target.value })} placeholder="Adjusted session, group, or context. Do not enter clinical notes." /></label>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <button type="button" className="pos-btn primary" disabled={mutation.isPending} onClick={() => mutation.mutate()}>
          <Plus size={11} />{mutation.isPending ? "Recording…" : "Record session log"}
        </button>
        <span className="pos-note">sRPE load = duration (min) × RPE = {fmt(form.duration_min * form.session_rpe, 1)} AU</span>
      </div>
      {mutation.error ? <PosError error={mutation.error} /> : null}
    </div>
  );
}

export function TodayView() {
  const today = useQuery({ queryKey: ["performance-today"], queryFn: performanceApi.today });
  const context = useQuery({ queryKey: ["performance-context"], queryFn: performanceApi.context });
  const [sessionOpen, setSessionOpen] = useState(false);
  const [triageOpen, setTriageOpen] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const notify = (message: string) => {
    setToast(message);
    window.setTimeout(() => setToast(null), 4200);
  };

  const force = useQuery({
    queryKey: ["performance-force", today.data?.force_trial_id],
    queryFn: () => performanceApi.forceTrial(today.data!.force_trial_id!),
    enabled: Boolean(today.data?.force_trial_id),
  });

  if (today.isLoading) {
    return <div className="pos-page"><div className="pos-main"><PosLoading label="Composing squad command from the admitted snapshot" /></div></div>;
  }
  if (today.error) {
    return <div className="pos-page"><div className="pos-main"><PosError error={today.error} onRetry={() => void today.refetch()} /></div></div>;
  }
  const data = today.data!;
  const pulse = data.pulse;
  const bands = data.readiness_bands;
  const bandTotal = bands.l1 + bands.l2 + bands.l3 + bands.l4 || 1;
  const nextWeek = data.plan.next_microcycle;
  const weekly = data.weekly;

  return (
    <div className="pos-page">
      <main className="pos-main" aria-label="Squad command">
        <div className="pos-main-head">
          <div>
            <div className="pos-kicker">{todayLabel()} · Week {data.week} · {data.phase}</div>
            <h1>Squad command</h1>
            <p>One screen for the daily performance question: who needs attention, what changed, and what do we do next?</p>
          </div>
          <div className="pos-actions">
            <Link href="/plan" className="pos-btn">Open week plan</Link>
            <button type="button" className="pos-btn primary" onClick={() => setSessionOpen(true)}><Plus size={10} />Log session</button>
          </div>
        </div>

        <div className="pos-pulse" aria-label="Squad pulse">
          <div className="cell">
            <div className="k">Roster active</div>
            <div className="v">{pulse.roster_active}<span className="u">/ {pulse.roster_total}</span></div>
            <div className="s"><b>{pulse.unavailable}</b> unavailable · roster only</div>
          </div>
          <div className="cell">
            <div className="k">Readiness</div>
            <div className="v">{fmt(pulse.readiness, 1)}<span className="u">/ 10</span></div>
            <div className="s"><b className="warn">{pulse.readiness_below}</b> below 5.5 · {pulse.readiness_n} records</div>
          </div>
          <div className="cell">
            <div className="k">Load ratio</div>
            <div className="v">{fmt(pulse.load_ratio, 2)}<span className="u">AU</span></div>
            <div className="s"><b className="warn">{pulse.load_ratio_above}</b> above 1.30 · 4-week baseline</div>
          </div>
          <div className="cell">
            <div className="k">CMJ height</div>
            <div className="v">{fmt(pulse.cmj_height_cm, 2)}<span className="u">cm</span></div>
            <div className="s"><b>{fmtSigned(pulse.cmj_delta_pct, 1)}</b> vs baseline · n={pulse.cmj_n}</div>
          </div>
          <div className="cell">
            <div className="k">Data quality</div>
            <div className="v">{pulse.quality.valid_trials}<span className="u">/ {pulse.quality.present_trials}</span></div>
            <div className="s"><b className="warn">{pulse.quality.missing_slots}</b> missing slots · {pulse.quality.excluded_trials} excluded</div>
          </div>
        </div>

        <div className="pos-row top">
          <section className="pos-module" aria-label="Athletes to review">
            <div className="pos-module-head">
              <h2>Athletes to review</h2>
              <span className="sub">today · ranked by readiness, load, CMJ</span>
              <span className="right" title={`${data.triage_count} athletes meet at least one threshold; top five shown`}><PosChip tone="warn">{data.attention.length} flags</PosChip></span>
            </div>
            <div className="pos-module-body pos-attention">
              {data.attention.map((athlete) => (
                <Link key={athlete.athlete_id} href={`/athletes/${athlete.athlete_id}`} className="pos-ath-row">
                  <div className="pos-ath-id"><b>{athlete.athlete_id}</b><span>{athlete.position} · age {athlete.age}</span></div>
                  <div className="pos-ath-metrics">
                    {athlete.flag.rule === "readiness_low" ? (
                      <>
                        <div className="pos-ath-metric"><div className="k">Readiness</div><div className="v bad">{fmt(athlete.readiness, 1)}</div></div>
                        <div className="pos-ath-metric"><div className="k">Sleep</div><div className="v">{fmt(athlete.sleep_hours, 1)} h</div></div>
                        <div className="pos-ath-metric"><div className="k">CMJ</div><div className="v">{fmtSigned(athlete.cmj_delta_pct, 1)}</div></div>
                      </>
                    ) : athlete.flag.rule === "load_ratio_high" ? (
                      <>
                        <div className="pos-ath-metric"><div className="k">Load ratio</div><div className="v warn">{fmt(athlete.load_ratio, 2)}</div></div>
                        <div className="pos-ath-metric"><div className="k">Fatigue</div><div className="v">{fmt(athlete.fatigue, 2)}</div></div>
                        <div className="pos-ath-metric"><div className="k">Readiness</div><div className="v">{fmt(athlete.readiness, 1)}</div></div>
                      </>
                    ) : (
                      <>
                        <div className="pos-ath-metric"><div className="k">CMJ</div><div className="v bad">{fmtSigned(athlete.cmj_delta_pct, 1)}</div></div>
                        <div className="pos-ath-metric"><div className="k">Baseline</div><div className="v">{fmt(athlete.baseline_cmj_height_cm, 1)} cm</div></div>
                        <div className="pos-ath-metric"><div className="k">Latest</div><div className="v">{fmt(athlete.cmj_height_cm, 1)} cm</div></div>
                      </>
                    )}
                  </div>
                  <div className="pos-ath-flag">
                    <PosChip tone={severityTone(athlete.flag.severity)}>{athlete.flag.label}</PosChip>
                    <small>{shortFlagDetail(athlete.flag)}</small>
                    <span className="review">Review →</span>
                  </div>
                </Link>
              ))}
            </div>
          </section>

          <section className="pos-module" aria-label="Weekly training load">
            <div className="pos-module-head">
              <h2>Weekly training impulse</h2>
              <span className="sub">team mean · AU · 16 weeks</span>
              <span className="right"><PosChip tone="info">BUILD</PosChip></span>
            </div>
            <div className="pos-chart-body">
              <div className="pos-chart" style={{ height: 218 }}>
                <LoadLineChart data={weekly} height={218} />
              </div>
              <div className="pos-chart-foot">
                <span><b>Week {data.week}</b> {fmt(weekly[weekly.length - 1]?.training_impulse_au, 1)} AU</span>
                <span><b>4-week mean</b> {fmt(weekly.slice(-4).reduce((sum, row) => sum + row.training_impulse_au, 0) / 4, 1)} AU ? n=28</span>
                <span><b>Match weeks</b> {weekly.filter((row) => row.match_week).map((row) => row.week).join(" · ")}</span>
                <span className="right">Descriptive, not an injury predictor</span>
              </div>
            </div>
          </section>
        </div>

        <div className="pos-row bottom">
          <section className="pos-module" aria-label="CMJ force lab">
            <div className="pos-module-head">
              <h2>CMJ force–time</h2>
              <span className="sub">audit trial {data.force_trial_id ?? "not available"} · 1000 Hz</span>
              <span className="right"><PosChip tone="ok">VALID</PosChip><PosChip tone="info">SYNTHETIC</PosChip></span>
            </div>
            <div className="pos-module-body" style={{ display: "flex", flexDirection: "column" }}>
              {force.data && data.force_trial ? (
                <>
                  <div className="pos-force-grid">
                    <div className="pos-chart" style={{ height: 192 }}>
                      <ForceTimeChart trace={force.data.trace} bodyWeight={force.data.trial.body_weight_n} height={192} />
                    </div>
                    <div className="pos-force-metrics">
                      <div className="pos-fm"><div className="k">Jump height</div><div className="v">{fmt(force.data.trial.jump_height_cm, 2)}<span className="u">cm</span></div><div className="s">flight-time method</div></div>
                      <div className="pos-fm"><div className="k">Peak force</div><div className="v">{fmt(force.data.trial.peak_force_n, 0)}<span className="u">N</span></div><div className="s">body mass {fmt(force.data.trial.body_mass_kg, 1)} kg</div></div>
                      <div className="pos-fm"><div className="k">Concentric impulse</div><div className="v">{fmt(force.data.trial.concentric_impulse_n_s_kg, 3)}<span className="u">N·s·kg⁻¹</span></div><div className="s">phase integration</div></div>
                      <div className="pos-fm"><div className="k">RSI modified</div><div className="v">{fmt(force.data.trial.rsi_mod, 1)}<span className="u">cm/s</span></div><div className="s">jump / propulsion</div></div>
                    </div>
                  </div>
                  <div className="pos-force-legend">
                    <span><i style={{ background: "rgba(127,145,157,.5)" }} />Standing</span>
                    <span><i style={{ background: "rgba(95,212,232,.5)" }} />Unweight</span>
                    <span><i style={{ background: "rgba(224,164,88,.5)" }} />Brake</span>
                    <span><i style={{ background: "rgba(200,243,107,.5)" }} />Propulsion</span>
                    <span><i style={{ background: "rgba(167,139,250,.5)" }} />Flight</span>
                    <span><i style={{ background: "rgba(239,107,99,.5)" }} />Landing</span>
                    <span className="right">Trial length {fmt(force.data.trace[force.data.trace.length - 1]?.time_s, 2)} s · 1000 Hz · body weight {fmt(force.data.trial.body_weight_n, 0)} N</span>
                  </div>
                </>
              ) : (
                <PosEmpty title="No force trace available">The week-16 audit trial is not present in the admitted snapshot.</PosEmpty>
              )}
            </div>
          </section>

          <section className="pos-module" aria-label="Research and next actions">
            <div className="pos-module-head">
              <h2>Research &amp; next actions</h2>
              <span className="sub">evidence → decision</span>
            </div>
            <div className="pos-module-body pos-research-body">
              <div className="pos-research-card">
                <div className="k">Linked study · synthetic</div>
                <b>{data.study.title}</b>
                <p>{data.study.participants} athletes · weeks {data.study.weeks[0]}–{data.study.weeks[1]} · group × time CMJ response. Snapshot {data.study.snapshot_id}.</p>
                <Link href={`/research/studies/${data.study.id}`}>Open research →</Link>
              </div>
              <div className="pos-research-card">
                <div className="k">Today&apos;s decision</div>
                <b>Review {data.attention.length} flags before the session</b>
                <p>{data.attention.map((item) => `${item.athlete_id} ${item.flag.label.toLowerCase()}`).join(", ")}. Do not infer injury or readiness from a single metric.</p>
                <button type="button" className="pos-link" onClick={() => setTriageOpen(true)} style={{ background: "none", border: 0, padding: 0 }}>Open triage →</button>
              </div>
              <div className="pos-research-card">
                <div className="k">Movement · bounded segment</div>
                <b>{data.movement.window_label}</b>
                <p>
                  {data.movement.player ? `${data.movement.player.player_id} ${fmt(data.movement.player.distance_m, 0)} m · ${fmt(data.movement.player.hsr_m, 0)} m HSR · ${fmt(data.movement.player.max_speed_m_s, 1)} m/s max.` : "No tracking segment admitted."} Segment only; not full-match distance.
                </p>
                <Link href="/monitor?metric=movement&player=PLAYER-14">Open movement →</Link>
              </div>
            </div>
          </section>
        </div>
      </main>

      <aside className="pos-aside" aria-label="Daily context">
        <div className="pos-aside-sec">
          <h3>Today&apos;s checklist</h3>
          {data.checklist.map((item) => {
            const content = (
              <>
                <span className={`tick ${item.done ? "done" : ""}`}>{item.done ? "✓" : ""}</span>
                {item.label}
                <span className={`status ${item.done ? "done" : "pending"}`}>{item.status}</span>
              </>
            );
            return item.id === "report"
              ? <Link href="/report" className="pos-check" key={item.id} style={{ textDecoration: "none", color: "inherit" }}>{content}</Link>
              : <div className="pos-check" key={item.id}>{content}</div>;
          })}
        </div>
        <div className="pos-aside-sec">
          <h3>Readiness distribution</h3>
          <div className="pos-dist" aria-label={`Readiness bands: ${bands.l1} below 5.5, ${bands.l2} from 5.5 to 6.5, ${bands.l3} from 6.5 to 7.5, ${bands.l4} above 7.5`}>
            <i className="l1" style={{ width: `${(bands.l1 / bandTotal) * 100}%` }} />
            <i className="l2" style={{ width: `${(bands.l2 / bandTotal) * 100}%` }} />
            <i className="l3" style={{ width: `${(bands.l3 / bandTotal) * 100}%` }} />
            <i className="l4" style={{ width: `${(bands.l4 / bandTotal) * 100}%` }} />
          </div>
          <div className="pos-dist-legend">
            <span><i style={{ background: "#ef6b63" }} />&lt;5.5 · {bands.l1}</span>
            <span><i style={{ background: "#e0a458" }} />5.5–6.5 · {bands.l2}</span>
            <span><i style={{ background: "#5fd4e8" }} />6.5–7.5 · {bands.l3}</span>
            <span><i style={{ background: "#c8f36b" }} />≥7.5 · {bands.l4}</span>
          </div>
        </div>
        {data.session_logs.length > 0 ? (
          <div className="pos-aside-sec">
            <h3>Coach-entered session logs</h3>
            {data.session_logs.slice().reverse().map((log) => (
              <div key={log.id} className="pos-check" title={log.source_label}>
                <span className="tick done">✓</span>
                {log.session_type} · {fmt(log.srpe_load_au, 0)} AU
                <span className="status done">{log.attendance} att.</span>
              </div>
            ))}
            <div className="pos-note" style={{ marginTop: 4 }}>Operational logs are stored separately from the immutable snapshot.</div>
          </div>
        ) : null}
        <div className="pos-aside-sec">
          <h3>Data admission</h3>
          <dl className="pos-kv">
            <dt>Snapshot</dt><dd>{context.data?.snapshot.id ?? data.study.snapshot_id}</dd>
            <dt>Type</dt><dd>SYNTHETIC</dd>
            <dt>Valid trials</dt><dd>{data.data_quality.valid_trials} / {data.data_quality.present_trials}</dd>
            <dt>Missing slots</dt><dd>{data.data_quality.missing_slots}</dd>
            <dt>Force rate</dt><dd>1000 Hz</dd>
            <dt>Next week</dt><dd>{nextWeek?.week ?? "—"} · {nextWeek?.status ?? "—"}</dd>
          </dl>
        </div>
        <div className="pos-aside-sec">
          <div className="pos-callout"><b>Injury module unavailable.</b> This snapshot has no injury or exposure table. Availability is roster status only; do not infer injury risk.</div>
        </div>
        <div className="pos-aside-sec">
          <div className="pos-callout info"><b>GPS is a bounded segment.</b> Match tracking covers a 3-minute window, not full-match distance. The synthetic segment includes position resets; use the Movement module for the admitted segment only.</div>
        </div>
        <div className="pos-aside-foot">
          {context.data?.snapshot.label ?? "Synthetic football longitudinal snapshot"}<br />
          No real athletes, clubs or matches<br />
          <b>UNIT REGISTRY</b> · cm · N · N·s·kg⁻¹ · AU · h
        </div>
      </aside>

      {sessionOpen ? (
        <Drawer title="Log session" subtitle="Planned and actual are separate" onClose={() => setSessionOpen(false)}>
          <SessionLogForm onDone={notify} onClose={() => setSessionOpen(false)} />
        </Drawer>
      ) : null}

      {triageOpen ? <TriageDrawer onClose={() => setTriageOpen(false)} /> : null}
      <Toast message={toast} />
    </div>
  );
}

function TriageDrawer({ onClose }: { onClose: () => void }) {
  const athletes = useQuery({ queryKey: ["performance-athletes"], queryFn: performanceApi.athletes });
  return (
    <Drawer title="Triage" subtitle="Every threshold breach, not only the top five" onClose={onClose}>
      <div className="pos-callout info">
        <b>Review is a human action.</b> No value here diagnoses injury or predicts availability. Thresholds are listed in the Component atlas with their owner and date. Persistent alert assignment, status and review timestamps are P2 and are not simulated.
      </div>
      <div className="pos-module" style={{ marginTop: 8 }}>
        <div className="pos-module-head"><h2>All athletes with flags</h2><span className="right"><PosChip tone="warn">{athletes.data?.filter((athlete) => athlete.flags.length > 0).length ?? 0} athletes</PosChip></span></div>
        <div className="pos-module-body flush">
          {athletes.isLoading ? <PosLoading label="Reading athlete flags" /> : null}
          {athletes.data ? (
            <table className="pos-table">
              <thead><tr><th>Athlete</th><th>Pos</th><th>Readiness</th><th>Load ratio</th><th>CMJ Δ</th><th>Flags</th><th /></tr></thead>
              <tbody>
                {athletes.data.filter((athlete) => athlete.flags.length > 0).map((athlete) => (
                  <tr key={athlete.display_id}>
                    <td className="mono">{athlete.display_id}</td>
                    <td>{athlete.position}</td>
                    <td>{fmt(athlete.readiness, 1)}</td>
                    <td>{fmt(athlete.load_ratio, 2)}</td>
                    <td className={athlete.cmj_delta_pct !== null && athlete.cmj_delta_pct < -2.5 ? "pos-red" : ""}>{fmtSigned(athlete.cmj_delta_pct, 1)}</td>
                    <td>{athlete.flags.map((flag) => <PosChip key={flag.rule} tone={severityTone(flag.severity)}>{flag.label}</PosChip>)}</td>
                    <td><Link href={`/athletes/${athlete.display_id}`} className="pos-link">Open 360 →</Link></td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
        </div>
      </div>
    </Drawer>
  );
}
