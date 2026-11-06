"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
import { performanceApi } from "@/lib/performance/api";
import { fmt } from "@/lib/performance/format";
import type { PlanSession } from "@/lib/performance/types";
import { PlannedActualBars } from "./charts";
import { PosChip, PosEmpty, PosError, PosLoading, Toast, toneForStatus } from "./ui";

const emptySession = (): PlanSession => ({
  id: `SES-W17-${Math.random().toString(36).slice(2, 6).toUpperCase()}`,
  day: "Wednesday",
  type: "Field",
  focus: "",
  planned_load_au: 60,
  duration_min: 60,
  group: "Squad",
});

export function PlanView() {
  const client = useQueryClient();
  const plan = useQuery({ queryKey: ["performance-plan"], queryFn: performanceApi.plan });
  const [sessions, setSessions] = useState<PlanSession[]>([]);
  const [focus, setFocus] = useState("");
  const [testingWindow, setTestingWindow] = useState("");
  const [toast, setToast] = useState<string | null>(null);
  const [initialized, setInitialized] = useState(false);

  useEffect(() => {
    if (!plan.data || initialized) return;
    const next = plan.data.microcycles.find((item) => item.week === plan.data!.current_week + 1);
    if (next) {
      setSessions(next.sessions);
      setFocus(next.focus);
      setTestingWindow(next.testing_window);
      setInitialized(true);
    }
  }, [plan.data, initialized]);

  const mutation = useMutation({
    mutationFn: (publish: boolean) =>
      performanceApi.updatePlan({
        week: (plan.data?.current_week ?? 16) + 1,
        focus,
        testing_window: testingWindow,
        sessions,
        publish,
        actor: "Head of Performance",
      }),
    onSuccess: (result) => {
      void client.invalidateQueries({ queryKey: ["performance-plan"] });
      void client.invalidateQueries({ queryKey: ["performance-today"] });
      void client.invalidateQueries({ queryKey: ["performance-load"] });
      setToast(result.status === "PUBLISHED" ? `Week ${(plan.data?.current_week ?? 16) + 1} plan published · version ${result.version}.` : `Draft saved · version ${result.version}.`);
      window.setTimeout(() => setToast(null), 4200);
    },
  });

  if (plan.isLoading) return <div className="pos-page"><div className="pos-main"><PosLoading label="Reading the persisted microcycle plan" /></div></div>;
  if (plan.error) return <div className="pos-page"><div className="pos-main"><PosError error={plan.error} onRetry={() => void plan.refetch()} /></div></div>;
  const data = plan.data!;
  const next = data.microcycles.find((item) => item.week === data.current_week + 1);
  const current = data.microcycles.find((item) => item.week === data.current_week);
  const total = sessions.reduce((sum, session) => sum + Number(session.planned_load_au || 0), 0);
  const actual = data.actual_weekly.map((row) => row.training_impulse_au);
  const planned = data.actual_weekly.map((row) => (row.week === data.current_week ? current?.reference_load_au ?? null : null));

  return (
    <div className="pos-page">
      <main className="pos-main" aria-label="Plan">
        <div className="pos-main-head">
          <div>
            <div className="pos-kicker">Season {data.season} · Block 4 · Week {data.current_week} → {data.current_week + 1}</div>
            <h1>Plan</h1>
            <p>Build the microcycle, separate planned targets from observed load, and publish the week with its testing window.</p>
          </div>
          <div className="pos-actions">
            <PosChip tone={toneForStatus(data.status)}>{data.status} · v{data.version}</PosChip>
            <button type="button" className="pos-btn" disabled={mutation.isPending} onClick={() => mutation.mutate(false)}>Save draft</button>
            <button type="button" className="pos-btn primary" disabled={mutation.isPending || sessions.length === 0} onClick={() => mutation.mutate(true)}>Publish week</button>
          </div>
        </div>

        <div className="pos-section-title"><h2>Periodization</h2><span>16 weeks · actual load by block · planned only where a plan is recorded</span><span className="right"><PosChip tone="info">SYNTHETIC SNAPSHOT</PosChip></span></div>
        <div className="pos-blocks">
          {data.periodization.map((block) => (
            <div key={block.id} className={`pos-block ${block.end_week >= data.current_week && block.start_week <= data.current_week ? "is-current" : ""}`}>
              <div className="k">{block.label} · {block.status}</div>
              <b>{block.phase === "BUILD" ? "Build" : "Match"} · weeks {block.start_week}–{block.end_week}</b>
              <div className="weeks">match weeks {block.match_weeks.length ? block.match_weeks.join(" · ") : "none"} · testing {block.testing_window}</div>
              <div className="load">{fmt(block.mean_load_au, 1)}<span> AU mean actual</span></div>
            </div>
          ))}
        </div>

        <div className="pos-grid-2" style={{ gridTemplateColumns: "1.45fr 1fr", alignItems: "start" }}>
          <section className="pos-module">
            <div className="pos-module-head">
              <h2>Microcycle W{data.current_week + 1}</h2>
              <span className="sub">{next?.status ?? "DRAFT"} · {sessions.length} sessions · coach-editable</span>
              <span className="right"><PosChip tone={toneForStatus(next?.status)}>{next?.status ?? "DRAFT"}</PosChip></span>
            </div>
            <div className="pos-module-body">
              <div className="pos-form-grid" style={{ marginBottom: 8 }}>
                <label className="pos-field"><span>Microcycle focus</span><input value={focus} onChange={(event) => setFocus(event.target.value)} /></label>
                <label className="pos-field"><span>Testing window</span><input value={testingWindow} onChange={(event) => setTestingWindow(event.target.value)} /></label>
              </div>
              <div className="pos-callout info" style={{ marginBottom: 8 }}>
                <b>Planned targets are not measurements.</b> {data.source_note}
              </div>
              <table className="pos-table pos-plan-table">
                <thead>
                  <tr><th>Day</th><th>Type</th><th>Focus</th><th className="r">Load AU</th><th className="r">Min</th><th>Group</th><th /></tr>
                </thead>
                <tbody>
                  {sessions.map((session, index) => (
                    <tr key={session.id}>
                      <td><select value={session.day} onChange={(event) => setSessions(sessions.map((item, i) => i === index ? { ...item, day: event.target.value } : item))}>{["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"].map((day) => <option key={day}>{day}</option>)}</select></td>
                      <td><select value={session.type} onChange={(event) => setSessions(sessions.map((item, i) => i === index ? { ...item, type: event.target.value } : item))}>{["Recovery","Strength","Field","Match","Testing"].map((type) => <option key={type}>{type}</option>)}</select></td>
                      <td><input className="text" value={session.focus} onChange={(event) => setSessions(sessions.map((item, i) => i === index ? { ...item, focus: event.target.value } : item))} /></td>
                      <td className="r"><input type="number" min={0} max={5000} value={session.planned_load_au} onChange={(event) => setSessions(sessions.map((item, i) => i === index ? { ...item, planned_load_au: Number(event.target.value) } : item))} /></td>
                      <td className="r"><input type="number" min={0} max={600} value={session.duration_min} onChange={(event) => setSessions(sessions.map((item, i) => i === index ? { ...item, duration_min: Number(event.target.value) } : item))} /></td>
                      <td>{session.group}</td>
                      <td><button type="button" className="pos-btn small ghost" aria-label="Remove session" onClick={() => setSessions(sessions.filter((_, i) => i !== index))}><Trash2 size={10} /></button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="pos-plan-total" style={{ marginTop: 8 }}>
                <b>{fmt(total, 0)}</b><span>AU planned · 4 sessions · vs W{data.current_week} reference {fmt(current?.reference_load_au, 1)} AU (actual {fmt(current?.actual_load_au, 1)} AU)</span>
                <button type="button" className="pos-btn small" style={{ marginLeft: "auto" }} onClick={() => setSessions([...sessions, emptySession()])}><Plus size={10} />Add session</button>
              </div>
              {mutation.error ? <PosError error={mutation.error} /> : null}
            </div>
          </section>

          <div style={{ display: "grid", gap: 9 }}>
            <section className="pos-module">
              <div className="pos-module-head"><h2>Testing calendar</h2><span className="sub">protocol-bound windows</span></div>
              <div className="pos-module-body">
                <table className="pos-table">
                  <thead><tr><th>Week</th><th>Window</th><th>Protocol</th><th>Status</th></tr></thead>
                  <tbody>
                    {data.testing_calendar.map((item) => (
                      <tr key={item.id}>
                        <td className="mono">W{item.date_week}</td>
                        <td>{item.window}</td>
                        <td className="mono">{item.protocol}</td>
                        <td><PosChip tone={toneForStatus(item.status)}>{item.status}</PosChip><div className="pos-faint" style={{ fontSize: 6.5, marginTop: 1 }}>{item.completeness}</div></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
            <section className="pos-module">
              <div className="pos-module-head"><h2>Plan status</h2><span className="sub">source and separation</span></div>
              <div className="pos-module-body">
                <dl className="pos-kv">
                  <dt>Source</dt><dd>{data.source_label}</dd>
                  <dt>Plan version</dt><dd>v{data.version}</dd>
                  <dt>Published</dt><dd>{data.published_at ? new Date(data.published_at).toLocaleString("en-GB") : "not yet"}</dd>
                  <dt>W{data.current_week} target</dt><dd>{fmt(current?.reference_load_au, 1)} AU (derived reference)</dd>
                  <dt>W{data.current_week} actual</dt><dd>{fmt(current?.actual_load_au, 1)} AU (observed)</dd>
                  <dt>Attendance</dt><dd>unavailable</dd>
                </dl>
                <div className="pos-hr" />
                <PosEmpty title="Attendance is P2 and unavailable" info>
                  No attendance contract is admitted, so the planner does not claim who attended. Session logs are recorded separately as coach-entered operational data.
                </PosEmpty>
              </div>
            </section>
          </div>
        </div>

        <section className="pos-module">
          <div className="pos-module-head">
            <h2>Planned versus actual load</h2>
            <span className="sub">bars actual · dashed lime planned or derived reference · AU</span>
            <span className="right"><Link href="/monitor?metric=load" className="pos-link">Open training load →</Link><PosChip tone="warn">DESCRIPTIVE</PosChip></span>
          </div>
          <div className="pos-chart-body">
            <div className="pos-chart" style={{ height: 160 }}>
              <PlannedActualBars weeks={data.actual_weekly.map((row) => row.week)} actual={actual} planned={planned} height={160} />
            </div>
            <div className="pos-chart-foot">
              <span><b>W{data.current_week}</b> actual {fmt(current?.actual_load_au, 1)} AU</span>
              <span><b>Reference</b> {fmt(current?.reference_load_au, 1)} AU · mean W12–W15</span>
              <span><b>W{data.current_week + 1}</b> planned {fmt(total, 0)} AU · {next?.status}</span>
              <span className="right">No causal or injury-prediction claim</span>
            </div>
          </div>
        </section>

        <div className="pos-grid-2" style={{ alignItems: "start" }}>
          <section className="pos-module">
            <div className="pos-module-head"><h2>Plan audit</h2><span className="sub">append-only actions</span></div>
            <div className="pos-module-body pos-audit">
              {data.audit.slice().reverse().map((entry, index) => (
                <div className="pos-evidence-row" key={`${entry.at}-${index}`} style={{ gridTemplateColumns: "90px 70px 1fr" }}>
                  <span className="pos-evidence-id">{entry.at.slice(0, 10)}</span>
                  <PosChip tone={toneForStatus(entry.action)}>{entry.action}</PosChip>
                  <span className="pos-evidence-title">{entry.detail}<small>{entry.actor}</small></span>
                </div>
              ))}
            </div>
          </section>
          <section className="pos-module">
            <div className="pos-module-head"><h2>Limits</h2><span className="sub">what this plan does not claim</span></div>
            <div className="pos-module-body">
              {data.limitations.map((item) => <div key={item} className="pos-note" style={{ marginBottom: 4 }}>— {item}</div>)}
            </div>
          </section>
        </div>
      </main>
      <aside className="pos-aside" aria-label="Plan context">
        <div className="pos-aside-sec">
          <h3>Squad availability</h3>
          <div className="pos-squad-number" style={{ fontSize: 22 }}>28<span>/ 28 active</span></div>
          <div className="pos-squad-note"><b>No injury table admitted</b><br />Availability is roster status only.</div>
        </div>
        <div className="pos-aside-sec">
          <h3>Thresholds that generate flags</h3>
          <dl className="pos-kv">
            <dt>Readiness</dt><dd>&lt; 5.5</dd>
            <dt>Load ratio</dt><dd>&gt; 1.30</dd>
            <dt>CMJ</dt><dd>&lt; −2.5%</dd>
            <dt>Soreness</dt><dd>&gt; 7.0</dd>
          </dl>
          <div className="pos-note" style={{ marginTop: 5 }}>Owner: Head of Performance / Sports Scientist · set 2026-11-05.</div>
        </div>
        <div className="pos-aside-sec">
          <div className="pos-callout info"><b>One athlete model.</b> Plan sessions and monitoring link to the same athlete identity. The plan does not create or alter measurements.</div>
        </div>
        <div className="pos-aside-sec">
          <PosEmpty title="Session planner is P1" info>
            Planned sessions, targets and testing windows are persisted. Attendance, drills and availability clearance require P2 contracts and are not simulated.
          </PosEmpty>
        </div>
        <div className="pos-aside-foot">Plan store · local JSON<br />Snapshot DS-SYNTH-001 · {data.as_of.slice(0, 10)}<br /><b>PLANNED ≠ ACTUAL</b></div>
      </aside>
      <Toast message={toast} />
    </div>
  );
}
