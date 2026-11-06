"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { performanceApi } from "@/lib/performance/api";
import { fmt, fmtSigned } from "@/lib/performance/format";
import { ForceTimeChart, SpeedZoneBars, SquadHeatmap, Sparkline, TrendChart } from "./charts";
import { PosChip, PosEmpty, PosError, PosLoading } from "./ui";

export function AtlasView() {
  const units = useQuery({ queryKey: ["performance-units"], queryFn: performanceApi.units });
  const today = useQuery({ queryKey: ["performance-today"], queryFn: performanceApi.today });
  const athletes = useQuery({ queryKey: ["performance-athletes"], queryFn: performanceApi.athletes });
  const squad = useQuery({ queryKey: ["performance-squad-weeks"], queryFn: performanceApi.squadWeeks });
  const tests = useQuery({ queryKey: ["performance-tests"], queryFn: performanceApi.tests });
  const force = useQuery({
    queryKey: ["performance-force", today.data?.force_trial_id],
    queryFn: () => performanceApi.forceTrial(today.data!.force_trial_id!),
    enabled: Boolean(today.data?.force_trial_id),
  });

  if (units.isLoading || today.isLoading || athletes.isLoading) return <div className="pos-page no-aside"><div className="pos-main"><PosLoading label="Composing the component and unit atlas" /></div></div>;
  if (units.error || today.error || athletes.error) return <div className="pos-page no-aside"><div className="pos-main"><PosError error={units.error ?? today.error ?? athletes.error} /></div></div>;
  const data = units.data!;
  const t = today.data!;
  const athleteList = athletes.data ?? [];
  const sample = athleteList.find((athlete) => athlete.display_id === "ATH-003") ?? athleteList[0];
  const evidence = t.study.primary_evidence[0];
  const reliability = tests.data?.reliability ?? [];

  return (
    <div className="pos-page no-aside">
      <main className="pos-main" aria-label="Component and unit atlas">
        <div className="pos-main-head">
          <div>
            <div className="pos-kicker">Performance OS · design pattern</div>
            <h1>Component &amp; unit atlas</h1>
            <p>Sports science is not a generic dashboard. Every value carries a unit, every chart states a reference window, and missingness and sample size stay visible.</p>
          </div>
          <div className="pos-actions">
            <PosChip tone="info">SYNTHETIC FIXTURE</PosChip>
            <span className="pos-note">DS-SYNTH-001 · 28 athletes · 16 weeks</span>
          </div>
        </div>

        <div className="pos-atlas-section" style={{ marginTop: 0, borderTop: 0, paddingTop: 0 }}>
          <div className="pos-section-title"><h2>Status language</h2><span>never colour alone</span></div>
          <div className="pos-atoms" style={{ marginTop: 6 }}>
            {["Available", "Modified", "Rehab", "Unavailable", "No data", "Valid", "Excluded", "Missing", "Derived", "Modelled", "Direct measure", "Self-report", "Device"].map((atom) => (
              <span key={atom} className={`pos-atom ${["Available", "Valid", "Direct measure", "Self-report", "Device"].includes(atom) ? "ok" : ["Modified", "Missing", "Modelled", "Unavailable", "No data"].includes(atom) ? "warn" : "info"}`}>{atom}</span>
            ))}
          </div>
        </div>

        <div className="pos-atlas-section">
          <div className="pos-section-title"><h2>Units registry</h2><span>canonical display units · {data.units.length} quantities</span><span className="right"><Link href="/library" className="pos-link">Metric registry →</Link></span></div>
          <div className="pos-unit-grid" style={{ marginTop: 6 }}>
            {data.units.map((unit) => (
              <div className="pos-unit" key={unit.quantity} title={`${unit.quantity} · ${unit.dimension}`}>
                <b>{unit.symbol}</b>
                <span>{unit.quantity}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="pos-atlas-section">
          <div className="pos-section-title"><h2>Cards</h2><span>each card answers one question</span></div>
          <div className="pos-specimen-grid" style={{ marginTop: 6 }}>
            <div className="pos-specimen">
              <div className="k">Athlete status</div>
              <h3>{sample?.display_id ?? "ATH-003"} <span className="pos-faint" style={{ fontWeight: 400, fontSize: 7 }}>{sample?.position ?? "CB"} · age {sample?.age ?? 18}</span></h3>
              <div className="body"><div className="pos-metric-value" style={{ fontSize: 18 }}>{fmt(sample?.readiness, 1)}<span className="u">/10 ready</span></div><div className="pos-note">sleep {fmt(sample?.sleep_hours, 1)} h · load ratio {fmt(sample?.load_ratio, 2)}</div></div>
              <div className="foot"><PosChip tone={sample?.primary_flag ? (sample.primary_flag.severity === "action" ? "bad" : "warn") : "ok"}>{sample?.primary_flag?.label ?? "No flag"}</PosChip><Link href={`/athletes/${sample?.display_id ?? "ATH-003"}`} className="pos-link">Review →</Link></div>
            </div>
            <div className="pos-specimen">
              <div className="k">Metric · CMJ</div>
              <h3>{fmt(t.pulse.cmj_height_cm, 2)}<span className="pos-unit">cm</span></h3>
              <div className="body"><Sparkline values={t.weekly.map((row) => row.cmj_height_cm)} width={220} height={44} color="#5fd4e8" /><div className="pos-note">baseline {fmt(t.pulse.cmj_baseline_cm, 2)} cm · {fmtSigned(t.pulse.cmj_delta_pct, 1)} · n={t.pulse.cmj_n}</div></div>
              <div className="foot">W1–16 · own baseline band</div>
            </div>
            <div className="pos-specimen">
              <div className="k">Session load</div>
              <h3>{fmt(t.weekly[15]?.training_impulse_au, 1)}<span className="pos-unit">AU</span></h3>
              <div className="body"><div className="pos-note">week 16 · team mean · 28 athletes</div><div className="pos-k" style={{ marginTop: 5 }}>actual · not planned</div><div className="pos-note">external {fmt(t.weekly[15]?.external_load_au, 1)} AU · HSR {fmt(t.weekly[15]?.hsr_distance_m, 1)} m</div></div>
              <div className="foot"><PosChip tone="info">OBSERVED</PosChip></div>
            </div>
            <div className="pos-specimen">
              <div className="k">Test trial</div>
              <h3>{fmt(t.force_trial?.peak_force_n, 0)}<span className="pos-unit">N peak</span></h3>
              <div className="body"><div className="pos-note">{t.force_trial_id} · {t.force_trial?.display_id} · 1000 Hz</div><div className="pos-note">jump {fmt(t.force_trial?.jump_height_cm, 2)} cm · impulse {fmt(t.force_trial?.concentric_impulse_n_s_kg, 3)} N·s·kg⁻¹</div></div>
              <div className="foot"><PosChip tone="ok">VALID</PosChip><PosChip tone="info">TRIAL</PosChip></div>
            </div>
          </div>
        </div>

        <div className="pos-atlas-section">
          <div className="pos-section-title"><h2>Chart specimens</h2><span>question → chart → unit</span></div>
          <div className="pos-specimen-grid" style={{ marginTop: 6 }}>
            <div className="pos-specimen">
              <div className="k">Individual trajectory</div><h3>Is this athlete changing?</h3>
              <div className="body"><TrendChart data={t.weekly.map((row) => ({ week: row.week, value: row.readiness }))} unit="0–10" height={102} color="#c8f36b" digits={1} /></div>
              <div className="foot">0–10 · own baseline</div>
            </div>
            <div className="pos-specimen">
              <div className="k">Load periodization</div><h3>Actual load · planned not recorded</h3>
              <div className="body"><Sparkline values={t.weekly.map((row) => row.training_impulse_au)} width={230} height={72} color="#e0a458" /></div>
              <div className="foot">AU · actual only · match weeks 4 · 8 · 12 · 15</div>
            </div>
            <div className="pos-specimen">
              <div className="k">CMJ force–time</div><h3>What does the trace show?</h3>
              <div className="body">{force.data ? <ForceTimeChart trace={force.data.trace} bodyWeight={force.data.trial.body_weight_n} height={100} /> : <div className="pos-note">No trace</div>}</div>
              <div className="foot">N · 1000 Hz · phase shading</div>
            </div>
            <div className="pos-specimen">
              <div className="k">Squad heatmap</div><h3>Who is ready?</h3>
              <div className="body">{squad.data ? <SquadHeatmap athletes={squad.data.athletes} weeks={squad.data.weeks} height={102} /> : <div className="pos-note">No squad rows</div>}</div>
              <div className="foot">0–10 · 28 athletes · 16 weeks</div>
            </div>
            <div className="pos-specimen">
              <div className="k">Reliability</div><h3>Is the test reliable?</h3>
              <div className="body">{reliability.length ? <div className="pos-note">ICC {fmt(reliability[0].icc, 2)} · 95% CI {fmt(reliability[0].icc_ci_low, 2)}–{fmt(reliability[0].icc_ci_high, 2)}<br />TE {fmt(reliability[0].typical_error, 3)} cm · CV {fmt(reliability[0].mean_cv_percent, 1)}%</div> : <div className="pos-note">No reliability computed</div>}</div>
              <div className="foot">ICC · TE · CV · n=28</div>
            </div>
            <div className="pos-specimen">
              <div className="k">Speed zones</div><h3>How did they move?</h3>
              <div className="body">{t.movement.player ? <SpeedZoneBars distance={t.movement.player.distance_m} hsr={t.movement.player.hsr_m} maxSpeed={t.movement.player.max_speed_m_s} /> : <div className="pos-note">No segment</div>}</div>
              <div className="foot">m · m·s⁻¹ · segment only</div>
            </div>
            <div className="pos-specimen">
              <div className="k">Injury incidence</div><h3>Is injury burden high?</h3>
              <div className="body"><PosEmpty title="Not admitted" info>No injury or exposure table. No rate is invented.</PosEmpty></div>
              <div className="foot">per 1000 h · unavailable</div>
            </div>
            <div className="pos-specimen">
              <div className="k">Evidence forest</div><h3>Is this effect real?</h3>
              <div className="body">
                {evidence && evidence.interval ? (
                  <div style={{ paddingTop: 18 }}>
                    <div style={{ position: "relative", height: 4, background: "#23333e" }}>
                      <div style={{ position: "absolute", left: "18%", width: "56%", height: 4, background: "#304552" }} />
                      <div style={{ position: "absolute", left: "44%", width: 3, height: 12, top: -4, background: "#c8f36b" }} />
                    </div>
                    <div className="pos-note" style={{ marginTop: 4 }}>{fmt(evidence.estimate, 3)} {evidence.unit}<br />95% CI {fmt(evidence.interval.low, 3)} to {fmt(evidence.interval.high, 3)}</div>
                  </div>
                ) : <div className="pos-note">No evidence interval.</div>}
              </div>
              <div className="foot">N·s·kg⁻¹ · 95% CI · cohort</div>
            </div>
          </div>
        </div>

        <div className="pos-atlas-section">
          <div className="pos-grid-2" style={{ gridTemplateColumns: "1.25fr 1fr", alignItems: "start" }}>
            <section>
              <div className="pos-section-title"><h2>Table specimen</h2><span>dense, sortable, unit-bearing</span></div>
              <div className="pos-module" style={{ marginTop: 6 }}>
                <div className="pos-module-body flush">
                  <table className="pos-table">
                    <thead><tr><th>Athlete</th><th>Pos</th><th className="r">Readiness</th><th className="r">Load ratio</th><th className="r">CMJ Δ</th><th>Status</th></tr></thead>
                    <tbody>{athleteList.slice(0, 5).map((athlete) => <tr key={athlete.display_id}><td><Link href={`/athletes/${athlete.display_id}`} className="pos-link">{athlete.display_id}</Link></td><td>{athlete.position}</td><td className="r">{fmt(athlete.readiness, 1)}/10</td><td className="r">{fmt(athlete.load_ratio, 2)}</td><td className="r">{fmtSigned(athlete.cmj_delta_pct, 1)}</td><td>{athlete.primary_flag ? <PosChip tone={athlete.primary_flag.severity === "action" ? "bad" : "warn"}>{athlete.primary_flag.label}</PosChip> : <PosChip tone="ok">Clear</PosChip>}</td></tr>)}</tbody>
                  </table>
                </div>
              </div>
              <div className="pos-note" style={{ marginTop: 5 }}>Readiness 4.9/10 is a self-report value; ATH-003 is on the roster and has no admitted injury status.</div>
            </section>
            <section>
              <div className="pos-section-title"><h2>Module map</h2><span>six workspaces + specialist modules</span></div>
              <div className="pos-module-map" style={{ marginTop: 6 }}>
                {[["Today", "squad status · triage"], ["Plan", "sessions · periodization"], ["Monitor", "load · wellness · trends"], ["Test", "battery · force lab · reliability"], ["Research", "study · model · evidence"], ["Report", "athlete · coach · board"], ["Availability", "P2 · injury · exposure · RTP"], ["Data quality", "missing · calibration"], ["Alerts", "P2 · rules · owners · review"]].map(([name, sub]) => <div key={name}><b>{name}</b><span>{sub}</span></div>)}
              </div>
              <div className="pos-section-title" style={{ marginTop: 10 }}><h2>Design rules</h2><span>enforced in every module</span></div>
              <div className="pos-rules" style={{ marginTop: 5 }}>
                {data.design_rules.map((rule) => <div className="pos-rule" key={rule}>{rule}</div>)}
              </div>
            </section>
          </div>
        </div>

        <div className="pos-atlas-section">
          <div className="pos-grid-2">
            <section>
              <div className="pos-section-title"><h2>Thresholds</h2><span>each states owner and date</span></div>
              <table className="pos-table" style={{ marginTop: 6 }}>
                <thead><tr><th>Rule</th><th>Threshold</th><th>Severity</th><th>Owner</th><th>Set</th></tr></thead>
                <tbody>{data.thresholds.map((threshold) => <tr key={threshold.id}><td>{threshold.label}</td><td className="mono">{threshold.operator} {threshold.value} {threshold.unit}</td><td><PosChip tone={threshold.severity === "action" ? "bad" : "warn"}>{threshold.severity}</PosChip></td><td>{threshold.owner}</td><td className="mono">{threshold.set_at}</td></tr>)}</tbody>
              </table>
            </section>
            <section>
              <div className="pos-section-title"><h2>Evidence and role boundaries</h2><span>what is not pretended</span></div>
              <div className="pos-note" style={{ marginTop: 6 }}>Bayesian hierarchical models and ML/PIML prediction are not implemented and are not presented as features. Injury surveillance, return-to-play and session attendance are P2 and require new data contracts.</div>
              <div className="pos-note" style={{ marginTop: 5 }}>The synthetic fixture has no injury or exposure table. The product shows that absence; it does not invent an injury risk or availability state.</div>
            </section>
          </div>
        </div>

        <div className="pos-note" style={{ borderTop: "1px solid var(--pos-line)", paddingTop: 8, marginTop: 4 }}>
          Prototype authority: docs/design/res588-ux/prototypes/f. This atlas uses live values computed from DS-SYNTH-001; no real athletes or clubs are represented.
        </div>
      </main>
    </div>
  );
}
