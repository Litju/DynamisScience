"use client";

import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Play } from "lucide-react";
import { performanceApi } from "@/lib/performance/api";
import { fmt } from "@/lib/performance/format";
import { ForceTimeChart, ReliabilityForest } from "./charts";
import { PosChip, PosEmpty, PosError, PosLoading, Toast, toneForStatus } from "./ui";

export function TestView() {
  const client = useQueryClient();
  const tests = useQuery({ queryKey: ["performance-tests"], queryFn: performanceApi.tests });
  const [trialId, setTrialId] = useState<string | null>(null);
  const [quality, setQuality] = useState("ALL");
  const [query, setQuery] = useState("");
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    if (!trialId && tests.data?.trials.length) {
      const preferred = tests.data.trials.find((trial) => trial.display_id === "ATH-001" && trial.quality_state === "VALID");
      setTrialId(preferred?.trial_id ?? tests.data.trials[0].trial_id);
    }
  }, [tests.data, trialId]);

  const force = useQuery({
    queryKey: ["performance-force", trialId],
    queryFn: () => performanceApi.forceTrial(trialId!),
    enabled: Boolean(trialId),
  });

  const assessment = useMutation({
    mutationFn: performanceApi.runReliability,
    onSuccess: (record) => {
      void client.invalidateQueries({ queryKey: ["performance-tests"] });
      setToast(`Reliability assessment ${record.id} computed and saved · ${record.status}.`);
      window.setTimeout(() => setToast(null), 4500);
    },
  });

  const filteredTrials = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return (tests.data?.trials ?? []).filter((trial) => {
      if (quality !== "ALL" && trial.quality_state !== quality) return false;
      if (!needle) return true;
      return `${trial.display_id} ${trial.trial_id}`.toLowerCase().includes(needle);
    });
  }, [tests.data, quality, query]);

  if (tests.isLoading) return <div className="pos-page"><div className="pos-main"><PosLoading label="Reading the week-16 testing battery" /></div></div>;
  if (tests.error) return <div className="pos-page"><div className="pos-main"><PosError error={tests.error} onRetry={() => void tests.refetch()} /></div></div>;
  const data = tests.data!;
  const testWindow = data.window;

  return (
    <div className="pos-page">
      <main className="pos-main" aria-label="Test">
        <div className="pos-main-head">
          <div>
            <div className="pos-kicker">Week {testWindow.week} benchmark · {testWindow.protocol.id} · {testWindow.protocol.sample_rate_hz} Hz</div>
            <h1>Test</h1>
            <p>What can this squad do, how reliable is the measurement, and what is actually missing from the testing record?</p>
          </div>
          <div className="pos-actions">
            <PosChip tone={toneForStatus(testWindow.status)}>{testWindow.status}</PosChip>
            <a className="pos-btn" href="/report">Compose report</a>
            <button type="button" className="pos-btn primary" disabled={assessment.isPending} onClick={() => assessment.mutate()}><Play size={10} />{assessment.isPending ? "Computing…" : "Run reliability check"}</button>
          </div>
        </div>

        <div className="pos-stat-strip">
          <div className="pos-stat"><div className="k">Athletes complete</div><div className="v">{testWindow.athletes_complete}<span className="u">/ {testWindow.athletes_expected}</span></div><div className="s">valid week-16 trials</div></div>
          <div className="pos-stat"><div className="k">Trials</div><div className="v">{testWindow.valid}<span className="u">valid / {testWindow.trials}</span></div><div className="s">{testWindow.excluded} excluded</div></div>
          <div className="pos-stat"><div className="k">Sample rate</div><div className="v">1000<span className="u">Hz</span></div><div className="s">force plate</div></div>
          <div className="pos-stat"><div className="k">Protocol</div><div className="v" style={{ fontSize: 12 }}>CMJ</div><div className="s">2 trials / week</div></div>
          <div className="pos-stat"><div className="k">Device record</div><div className="v" style={{ fontSize: 10 }}>NOT ADMITTED</div><div className="s">calibration unavailable</div></div>
        </div>

        <div className="pos-grid-2" style={{ gridTemplateColumns: "1.3fr 1fr", alignItems: "start" }}>
          <section className="pos-module">
            <div className="pos-module-head"><h2>Testing battery</h2><span className="sub">admitted vs unavailable</span><span className="right"><PosChip tone="warn">{data.battery.filter((item) => item.status === "ADMITTED").length} admitted</PosChip></span></div>
            <div className="pos-module-body">
              <div className="pos-battery">
                {data.battery.map((item) => (
                  <div className="pos-test-card" key={item.id}>
                    <div className="pos-k">{item.id} · {item.status}</div>
                    <h3>{item.name}</h3>
                    <div className="pos-note">{item.unit} · {item.window}</div>
                    <p>{item.note}</p>
                    <div className="foot"><PosChip tone={toneForStatus(item.status === "ADMITTED" ? "VALID" : "UNAVAILABLE")}>{item.quality}</PosChip>{item.protocol ? <PosChip tone="info">{item.protocol}</PosChip> : null}</div>
                  </div>
                ))}
              </div>
            </div>
          </section>

          <section className="pos-module">
            <div className="pos-module-head"><h2>Test window</h2><span className="sub">protocol, device and calibration</span></div>
            <div className="pos-module-body">
              <dl className="pos-kv">
                <dt>Window</dt><dd>{testWindow.label}</dd>
                <dt>Protocol</dt><dd>{testWindow.protocol.name}</dd>
                <dt>Frequency</dt><dd>{testWindow.protocol.frequency}</dd>
                <dt>Device</dt><dd>{testWindow.protocol.device}</dd>
                <dt>Calibration</dt><dd>{testWindow.protocol.calibration_record_admitted ? "admitted" : "not admitted"}</dd>
                <dt>Sample rate</dt><dd>{testWindow.protocol.sample_rate_hz} Hz</dd>
                <dt>Source</dt><dd>{testWindow.protocol.source}</dd>
              </dl>
              <div className="pos-hr" />
              <div className="pos-warn-note">The fixture provides a 1000 Hz trace but no device serial, calibration date or plate coverage. Treat the device as a fixture, not a qualified instrument.</div>
            </div>
          </section>
        </div>

        <section className="pos-module">
          <div className="pos-module-head"><h2>Within-session reliability</h2><span className="sub">ICC(3,1) · typical error · within-subject CV · n=28 · k=2</span><span className="right"><PosChip tone="info">W16</PosChip></span></div>
          <div className="pos-module-body">
            <ReliabilityForest metrics={data.reliability} />
            <div className="pos-note" style={{ marginTop: 6 }}>Reliability is trial agreement within the week-16 session, not agreement between devices or methods. A high ICC does not make a change meaningful; compare with the typical error and the athlete&apos;s own baseline.</div>
          </div>
        </section>

        <div className="pos-grid-2" style={{ gridTemplateColumns: "1.4fr 1fr", alignItems: "start" }}>
          <section className="pos-module">
            <div className="pos-module-head">
              <h2>Force lab</h2>
              <span className="sub">{trialId ?? "select a trial"} · {testWindow.protocol.sample_rate_hz} Hz</span>
              <span className="right"><PosChip tone="ok">VALID</PosChip><PosChip tone="info">SYNTHETIC</PosChip></span>
            </div>
            <div className="pos-module-body">
              <div className="pos-filter" style={{ marginBottom: 6 }}>
                <label className="pos-control"><span>Trial</span><select value={trialId ?? ""} onChange={(event) => setTrialId(event.target.value)}>{data.trials.filter((trial) => trial.quality_state === "VALID").map((trial) => <option key={trial.trial_id} value={trial.trial_id}>{trial.display_id} · {trial.trial_id} · T{trial.trial_number}</option>)}</select></label>
                {force.data ? <span className="pos-note">quality {force.data.trial.quality_state} · {force.data.method.algorithm} v{force.data.method.algorithm_version}</span> : null}
              </div>
              {force.isLoading ? <PosLoading label="Reading force trace" /> : null}
              {force.error ? <PosError error={force.error} onRetry={() => void force.refetch()} /> : null}
              {force.data ? (
                <>
                  <ForceTimeChart trace={force.data.trace} bodyWeight={force.data.trial.body_weight_n} height={245} />
                  <div className="pos-force-legend">
                    <span><i style={{ background: "rgba(127,145,157,.5)" }} />Standing</span>
                    <span><i style={{ background: "rgba(95,212,232,.5)" }} />Unweight</span>
                    <span><i style={{ background: "rgba(224,164,88,.5)" }} />Brake</span>
                    <span><i style={{ background: "rgba(200,243,107,.5)" }} />Propulsion</span>
                    <span><i style={{ background: "rgba(167,139,250,.5)" }} />Flight</span>
                    <span><i style={{ background: "rgba(239,107,99,.5)" }} />Landing</span>
                  </div>
                </>
              ) : null}
            </div>
          </section>

          <section className="pos-module">
            <div className="pos-module-head"><h2>Trial metrics</h2><span className="sub">audit extraction</span></div>
            <div className="pos-module-body">
              {force.data ? (
                <>
                  <dl className="pos-kv">
                    <dt>Athlete</dt><dd>{force.data.trial.display_id} · {force.data.subject.position}</dd>
                    <dt>Jump height</dt><dd>{fmt(force.data.trial.jump_height_cm, 2)} cm</dd>
                    <dt>Peak force</dt><dd>{fmt(force.data.trial.peak_force_n, 0)} N</dd>
                    <dt>Peak power</dt><dd>{fmt(force.data.trial.peak_power_w_kg, 2)} W/kg</dd>
                    <dt>Concentric impulse</dt><dd>{fmt(force.data.trial.concentric_impulse_n_s_kg, 3)} N·s·kg⁻¹</dd>
                    <dt>Braking duration</dt><dd>{fmt(force.data.trial.eccentric_braking_duration_s, 3)} s</dd>
                    <dt>RSI modified</dt><dd>{fmt(force.data.trial.rsi_mod, 1)} cm/s</dd>
                    <dt>Body mass</dt><dd>{fmt(force.data.trial.body_mass_kg, 2)} kg</dd>
                  </dl>
                  <div className="pos-hr" />
                  <div className="pos-note">Phase boundaries and trace checksum are preserved in provenance. The force trace is not re-synthesised by the client.</div>
                </>
              ) : <PosEmpty title="No trial selected">Select a valid trial to inspect its force trace.</PosEmpty>}
            </div>
          </section>
        </div>

        <section className="pos-module">
          <div className="pos-module-head"><h2>Trial register · Week {testWindow.week}</h2><span className="sub">{filteredTrials.length} of {data.trials.length} trials · quality is explicit</span>
            <span className="right pos-filter">
              <input placeholder="ATH-… or trial id" value={query} onChange={(event) => setQuery(event.target.value)} aria-label="Filter trials" />
              <select value={quality} onChange={(event) => setQuality(event.target.value)} aria-label="Filter quality"><option value="ALL">All quality</option><option value="VALID">Valid</option><option value="EXCLUDED">Excluded</option><option value="WARNING">Warning</option></select>
            </span>
          </div>
          <div className="pos-module-body flush pos-trials">
            <table className="pos-table">
              <thead><tr><th>Trial</th><th>Athlete</th><th>T</th><th className="r">Jump cm</th><th className="r">Peak N</th><th className="r">Impulse N·s·kg⁻¹</th><th className="r">RSI cm/s</th><th>Quality</th><th>Trace</th></tr></thead>
              <tbody>{filteredTrials.map((trial) => (
                <tr key={trial.trial_id} onClick={() => trial.quality_state === "VALID" && setTrialId(trial.trial_id)} style={{ cursor: trial.quality_state === "VALID" ? "pointer" : "default" }} className={trial.trial_id === trialId ? "is-selected" : ""}>
                  <td className="mono">{trial.trial_id}</td>
                  <td>{trial.display_id}</td>
                  <td>{trial.trial_number}</td>
                  <td className="r">{fmt(trial.jump_height_cm, 2)}</td>
                  <td className="r">{fmt(trial.peak_force_n, 0)}</td>
                  <td className="r">{fmt(trial.concentric_impulse_n_s_kg, 3)}</td>
                  <td className="r">{fmt(trial.rsi_mod, 1)}</td>
                  <td><PosChip tone={toneForStatus(trial.quality_state)}>{trial.quality_state}</PosChip>{trial.exclusion_reason ? <div className="pos-faint" style={{ fontSize: 6.5 }}>{trial.exclusion_reason}</div> : null}</td>
                  <td>{trial.trace_available ? <span className="pos-cyan">yes</span> : <span className="pos-faint">no</span>}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        </section>

        <div className="pos-grid-2" style={{ alignItems: "start" }}>
          <section className="pos-module">
            <div className="pos-module-head"><h2>Reliability assessments</h2><span className="sub">append-only computed records</span></div>
            <div className="pos-module-body">
              {data.assessments.length === 0 ? <div className="pos-note">No reliability assessment has been saved in this workspace. Run the check above to create one.</div> : data.assessments.slice().reverse().map((item) => (
                <div key={item.id} className="pos-evidence-row" style={{ gridTemplateColumns: "130px 1fr 70px" }}>
                  <span className="pos-evidence-id">{item.id}</span>
                  <span className="pos-evidence-title">{item.method}<small>W{item.window_week} · n={item.n_subjects} · k={item.trials_per_subject}</small></span>
                  <PosChip tone={toneForStatus(item.status)}>{item.status}</PosChip>
                </div>
              ))}
              {assessment.error ? <PosError error={assessment.error} /> : null}
            </div>
          </section>
          <section className="pos-module">
            <div className="pos-module-head"><h2>Limitations</h2><span className="sub">no invented validity</span></div>
            <div className="pos-module-body">{data.limitations.map((item) => <div key={item} className="pos-note" style={{ marginBottom: 4 }}>— {item}</div>)}</div>
          </section>
        </div>
      </main>
      <aside className="pos-aside" aria-label="Test context">
        <div className="pos-aside-sec">
          <h3>Data quality</h3>
          <dl className="pos-kv">
            <dt>Valid trials</dt><dd>{data.data_quality.valid_trials} / {data.data_quality.present_trials}</dd>
            <dt>Excluded</dt><dd>{data.data_quality.excluded_trials}</dd>
            <dt>Missing slots</dt><dd>{data.data_quality.missing_slots}</dd>
            <dt>Completeness</dt><dd>{fmt(data.data_quality.completeness_pct, 2)}%</dd>
          </dl>
          <div className="pos-note" style={{ marginTop: 5 }}>{data.data_quality.note}</div>
        </div>
        <div className="pos-aside-sec">
          <h3>Testing windows</h3>
          <div className="pos-check"><span className="tick done">✓</span>Week 4 benchmark<span className="status done">COMPLETE</span></div>
          <div className="pos-check"><span className="tick done">✓</span>Week 8 benchmark<span className="status done">COMPLETE</span></div>
          <div className="pos-check"><span className="tick done">✓</span>Week 12 benchmark<span className="status done">COMPLETE</span></div>
          <div className="pos-check"><span className="tick done">✓</span>Week 16 benchmark<span className="status done">CURRENT</span></div>
        </div>
        <div className="pos-aside-sec"><div className="pos-callout info"><b>Reliability is not agreement.</b> ICC and typical error describe trial repeatability. Bland–Altman is required for device or method agreement, and is not shown here.</div></div>
        <div className="pos-aside-sec"><div className="pos-callout"><b>No strength or sprint battery.</b> Only the CMJ force plate is admitted for this squad. Unavailable tests are shown as unavailable, not replaced with fabricated data.</div></div>
        <div className="pos-aside-foot">Test · {data.as_of.slice(0, 10)}<br />DS-SYNTH-001 · synthetic<br /><b>PROTOCOL · DEVICE · TRIAL · QUALITY</b></div>
      </aside>
      <Toast message={toast} />
    </div>
  );
}
