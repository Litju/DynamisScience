"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { performanceApi } from "@/lib/performance/api";
import { fmt, fmtSigned } from "@/lib/performance/format";
import type { SquadWeekAthlete } from "@/lib/performance/types";
import { LoadLineChart, SpeedZoneBars, SquadHeatmap, Sparkline, TrendChart } from "./charts";
import { PosChip, PosEmpty, PosError, PosLoading } from "./ui";

type Metric = "load" | "wellness" | "cmj" | "availability" | "movement";
type Reference = "baseline" | "rolling" | "season";
type Cohort = "squad" | "position" | "individual";

const METRICS: { id: Metric; label: string }[] = [
  { id: "load", label: "Training load" },
  { id: "wellness", label: "Wellness" },
  { id: "cmj", label: "CMJ" },
  { id: "availability", label: "Availability" },
  { id: "movement", label: "Movement / GPS" },
];

const POSITIONS = ["GK", "RB", "CB", "LB", "DM", "CM", "AM", "RW", "LW", "ST"];

export function MonitorView() {
  const today = useQuery({ queryKey: ["performance-today"], queryFn: performanceApi.today });
  const squad = useQuery({ queryKey: ["performance-squad-weeks"], queryFn: performanceApi.squadWeeks });
  const athletes = useQuery({ queryKey: ["performance-athletes"], queryFn: performanceApi.athletes });
  const movement = useQuery({ queryKey: ["performance-movement"], queryFn: performanceApi.movement });
  const [metric, setMetric] = useState<Metric>("load");
  const [reference, setReference] = useState<Reference>("baseline");
  const [cohort, setCohort] = useState<Cohort>("squad");
  const [position, setPosition] = useState("CB");
  const [athleteId, setAthleteId] = useState("ATH-003");
  const [playerId, setPlayerId] = useState("PLAYER-14");

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const requested = params.get("metric") as Metric | null;
    if (requested && METRICS.some((item) => item.id === requested)) setMetric(requested);
    const player = params.get("player");
    if (player) { setMetric("movement"); setPlayerId(player); }
    const athlete = params.get("athlete");
    if (athlete) { setCohort("individual"); setAthleteId(athlete); }
  }, []);

  const selected = useQuery({
    queryKey: ["performance-athlete", athleteId],
    queryFn: () => performanceApi.athlete(athleteId),
    enabled: cohort === "individual",
  });

  const filtered = useMemo<SquadWeekAthlete[]>(() => {
    const list = squad.data?.athletes ?? [];
    if (cohort === "position") return list.filter((athlete) => athlete.position === position);
    if (cohort === "individual") return list.filter((athlete) => athlete.display_id === athleteId);
    return list;
  }, [squad.data, cohort, position, athleteId]);

  if (today.isLoading || squad.isLoading) return <div className="pos-page"><div className="pos-main"><PosLoading label="Composing longitudinal monitoring from the admitted tables" /></div></div>;
  if (today.error || squad.error) return <div className="pos-page"><div className="pos-main"><PosError error={today.error ?? squad.error} onRetry={() => { void today.refetch(); void squad.refetch(); }} /></div></div>;
  const data = today.data!;
  const weekly = data.weekly;
  const selectedMovement = movement.data?.players.find((player) => player.player_id === playerId) ?? movement.data?.players[0];
  const readinessBand = (weeks: SquadWeekAthlete["weeks"]): [number, number] | null => {
    const baseline = weeks.filter((week) => week.week <= 4).map((week) => week.readiness).filter((value): value is number => value !== null);
    return baseline.length ? [Math.min(...baseline), Math.max(...baseline)] : null;
  };
  const cmjBand = (weeks: SquadWeekAthlete["weeks"]): [number, number] | null => {
    const baseline = weeks.filter((week) => week.week <= 4).map((week) => week.cmj_height_cm).filter((value): value is number => value !== null);
    return baseline.length ? [Math.min(...baseline), Math.max(...baseline)] : null;
  };
  const referenceWeek = (() => {
    if (reference === "baseline") return 4;
    if (reference === "rolling") return 4;
    return 16;
  })();

  return (
    <div className="pos-page">
      <main className="pos-main" aria-label="Monitor">
        <div className="pos-main-head">
          <div>
            <div className="pos-kicker">Weekly loop · weeks 1–16 · cohort {cohort === "squad" ? "squad" : cohort === "position" ? position : athleteId}</div>
            <h1>Monitor</h1>
            <p>Ask what is changing over time, with the athlete&apos;s own baseline before the cohort and a visible reference window on every chart.</p>
          </div>
          <div className="pos-actions"><Link href="/test" className="pos-btn">Open testing</Link><Link href="/report" className="pos-btn">Compose report</Link><PosChip tone="info">16 WEEKS</PosChip><PosChip tone="warn">DESCRIPTIVE</PosChip></div>
        </div>

        <div className="pos-controls" aria-label="Monitoring controls">
          <label className="pos-control"><span>Metric</span><select value={metric} onChange={(event) => setMetric(event.target.value as Metric)}>{METRICS.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>
          <label className="pos-control"><span>Cohort</span><select value={cohort} onChange={(event) => setCohort(event.target.value as Cohort)}><option value="squad">Squad</option><option value="position">Position group</option><option value="individual">Individual athlete</option></select></label>
          {cohort === "position" ? <label className="pos-control"><span>Position</span><select value={position} onChange={(event) => setPosition(event.target.value)}>{POSITIONS.map((item) => <option key={item}>{item}</option>)}</select></label> : null}
          {cohort === "individual" ? <label className="pos-control"><span>Athlete</span><select value={athleteId} onChange={(event) => setAthleteId(event.target.value)}>{(athletes.data ?? []).map((athlete) => <option key={athlete.display_id} value={athlete.display_id}>{athlete.display_id} · {athlete.position}</option>)}</select></label> : null}
          <label className="pos-control"><span>Reference</span><select value={reference} onChange={(event) => setReference(event.target.value as Reference)}><option value="baseline">Own W1–4 baseline</option><option value="rolling">Rolling 4-week</option><option value="season">Season window</option></select></label>
          <span className="pos-note" style={{ marginLeft: "auto" }}>Reference week boundary W{referenceWeek} · source DS-SYNTH-001</span>
        </div>

        {metric === "load" ? (
          <>
            <section className="pos-chart-frame">
              <div className="pos-module-head"><h2>Team training impulse</h2><span className="sub">AU · team mean · match weeks shaded</span><span className="right"><PosChip tone="info">LOAD</PosChip></span></div>
              <div className="chart" style={{ height: 230 }}><LoadLineChart data={weekly} height={230} reference={reference === "season" ? null : reference === "baseline" ? weekly.slice(0, 4).reduce((sum, row) => sum + row.training_impulse_au, 0) / 4 : weekly.slice(-4).reduce((sum, row) => sum + row.training_impulse_au, 0) / 4} /></div>
              <div className="pos-chart-foot"><span><b>W16</b> {fmt(weekly[15]?.training_impulse_au, 1)} AU</span><span><b>Season mean</b> {fmt(weekly.reduce((sum, row) => sum + row.training_impulse_au, 0) / weekly.length, 1)} AU ? n=28</span><span><b>Reference</b> {reference === "baseline" ? "W1–4 mean" : reference === "rolling" ? "4-week mean" : "season"}</span><span className="right">Load ratio is not an injury predictor</span></div>
            </section>
            <div className="pos-grid-2" style={{ gridTemplateColumns: "1.3fr 1fr", alignItems: "start" }}>
              <section className="pos-module">
                <div className="pos-module-head"><h2>Squad load ledger</h2><span className="sub">current week · actual only</span></div>
                <div className="pos-module-body flush">
                  <table className="pos-table">
                    <thead><tr><th>Athlete</th><th className="r">TI AU</th><th className="r">External AU</th><th className="r">HSR m</th><th className="r">Load ratio</th><th>Flag</th></tr></thead>
                    <tbody>{filtered.map((athlete) => {
                      const current = athlete.weeks[athlete.weeks.length - 1];
                      const summary = athletes.data?.find((item) => item.display_id === athlete.display_id);
                      return (
                        <tr key={athlete.display_id}>
                          <td><Link href={`/athletes/${athlete.display_id}`} className="pos-link">{athlete.display_id}</Link> <span className="pos-faint">{athlete.position}</span></td>
                          <td className="r">{fmt(current?.training_impulse_au, 1)}</td>
                          <td className="r">{fmt(summary?.external_load_au, 1)}</td>
                          <td className="r">{fmt(summary?.hsr_distance_m, 1)}</td>
                          <td className="r">{fmt(current?.load_ratio, 2)}</td>
                          <td>{summary?.primary_flag ? <PosChip tone={summary.primary_flag.severity === "action" ? "bad" : "warn"}>{summary.primary_flag.label}</PosChip> : <span className="pos-faint">—</span>}</td>
                        </tr>
                      );
                    })}</tbody>
                  </table>
                </div>
              </section>
              <section className="pos-module">
                <div className="pos-module-head"><h2>Load context</h2><span className="sub">descriptive reference</span></div>
                <div className="pos-module-body">
                  <div className="pos-stat-strip" style={{ gridTemplateColumns: "1fr 1fr", border: 0 }}>
                    <div className="pos-stat"><div className="k">Team readiness</div><div className="v">{fmt(data.pulse.readiness, 1)}<span className="u">/10</span></div><div className="s">n={data.pulse.readiness_n}</div></div>
                    <div className="pos-stat"><div className="k">Load ratio</div><div className="v">{fmt(data.pulse.load_ratio, 2)}<span className="u">AU</span></div><div className="s">{data.pulse.load_ratio_above} above 1.30</div></div>
                  </div>
                  <div className="pos-hr" />
                  <div className="pos-note">The 4-week load ratio is a descriptive summary of observed load. It must not be presented as an injury risk or prediction.</div>
                  <div className="pos-hr" />
                  <div className="pos-note">No planned load exists for the historical weeks; only the current microcycle target is persisted separately in Plan.</div>
                </div>
              </section>
            </div>
          </>
        ) : null}

        {metric === "wellness" ? (
          <>
            <section className="pos-chart-frame">
              <div className="pos-module-head"><h2>Squad readiness</h2><span className="sub">0–10 · team mean · own baseline band</span><span className="right"><PosChip tone="ok">SELF-REPORT</PosChip></span></div>
              <div className="chart" style={{ height: 230 }}><TrendChart data={weekly.map((row) => ({ week: row.week, value: row.readiness, phase: row.phase }))} unit="0–10" band={[Math.min(...weekly.slice(0, 4).map((row) => row.readiness ?? 10)), Math.max(...weekly.slice(0, 4).map((row) => row.readiness ?? 0))]} bandLabel="team W1–4 range" reference={weekly.slice(0, 4).reduce((sum, row) => sum + (row.readiness ?? 0), 0) / 4} referenceLabel="baseline mean" color="#c8f36b" height={230} digits={1} /></div>
              <div className="pos-chart-foot"><span><b>W16</b> {fmt(weekly[15]?.readiness, 1)}/10</span><span><b>Sleep</b> {fmt(weekly[15]?.sleep_hours, 2)} h</span><span><b>Soreness</b> {fmt(weekly[15]?.soreness, 1)}</span><span className="right">Missing is visible; never zero</span></div>
            </section>
            <SquadHeatmap athletes={filtered} weeks={squad.data?.weeks ?? []} height={220} metric="readiness" />
            <section className="pos-module">
              <div className="pos-module-head"><h2>Readiness distribution · W16</h2><span className="sub">bands 5.5 / 6.5 / 7.5</span></div>
              <div className="pos-module-body">
                <div className="pos-pulse" style={{ gridTemplateColumns: "repeat(4,minmax(0,1fr))" }}>
                  <div className="cell"><div className="k">&lt; 5.5</div><div className="v pos-red">{data.readiness_bands.l1}</div><div className="s">review</div></div>
                  <div className="cell"><div className="k">5.5–6.5</div><div className="v pos-amber">{data.readiness_bands.l2}</div><div className="s">watch</div></div>
                  <div className="cell"><div className="k">6.5–7.5</div><div className="v pos-cyan">{data.readiness_bands.l3}</div><div className="s">typical</div></div>
                  <div className="cell"><div className="k">≥ 7.5</div><div className="v pos-lime">{data.readiness_bands.l4}</div><div className="s">high</div></div>
                </div>
              </div>
            </section>
          </>
        ) : null}

        {metric === "cmj" ? (
          <>
            <section className="pos-chart-frame">
              <div className="pos-module-head"><h2>CMJ height</h2><span className="sub">cm · team mean · own baseline band</span><span className="right"><PosChip tone="info">FORCE PLATE</PosChip></span></div>
              <div className="chart" style={{ height: 230 }}><TrendChart data={weekly.map((row) => ({ week: row.week, value: row.cmj_height_cm, phase: row.phase }))} unit="cm" band={[Math.min(...weekly.slice(0, 4).map((row) => row.cmj_height_cm ?? 100)), Math.max(...weekly.slice(0, 4).map((row) => row.cmj_height_cm ?? 0))]} bandLabel="team W1–4 range" reference={weekly.slice(0, 4).reduce((sum, row) => sum + (row.cmj_height_cm ?? 0), 0) / 4} referenceLabel="baseline mean" color="#5fd4e8" height={230} digits={2} /></div>
              <div className="pos-chart-foot"><span><b>W16</b> {fmt(weekly[15]?.cmj_height_cm, 2)} cm</span><span><b>Baseline</b> {fmt(weekly.slice(0, 4).reduce((sum, row) => sum + (row.cmj_height_cm ?? 0), 0) / 4, 2)} cm</span><span><b>Valid trials</b> {data.data_quality.valid_trials}</span><span className="right">Trial-level missingness visible</span></div>
            </section>
            <SquadHeatmap athletes={filtered} weeks={squad.data?.weeks ?? []} height={220} metric="cmj" />
            <div className="pos-grid-2" style={{ alignItems: "start" }}>
              <section className="pos-module">
                <div className="pos-module-head"><h2>Athlete CMJ change</h2><span className="sub">W16 vs own W1–4</span></div>
                <div className="pos-module-body flush">
                  <table className="pos-table">
                    <thead><tr><th>Athlete</th><th>Position</th><th className="r">Baseline cm</th><th className="r">W16 cm</th><th className="r">Δ</th><th>Flag</th></tr></thead>
                    <tbody>{filtered.slice().sort((a, b) => (a.weeks.at(-1)?.cmj_delta_pct ?? 0) - (b.weeks.at(-1)?.cmj_delta_pct ?? 0)).map((athlete) => {
                      const current = athlete.weeks.at(-1);
                      const baseline = athlete.weeks.slice(0, 4).reduce((sum, week) => sum + (week.cmj_height_cm ?? 0), 0) / Math.max(1, athlete.weeks.slice(0, 4).filter((week) => week.cmj_height_cm !== null).length);
                      return <tr key={athlete.display_id}><td><Link href={`/athletes/${athlete.display_id}`} className="pos-link">{athlete.display_id}</Link></td><td>{athlete.position}</td><td className="r">{fmt(baseline, 2)}</td><td className="r">{fmt(current?.cmj_height_cm, 2)}</td><td className={`r ${current?.cmj_delta_pct !== null && current?.cmj_delta_pct !== undefined && current.cmj_delta_pct < -2.5 ? "pos-red" : ""}`}>{fmtSigned(current?.cmj_delta_pct, 1)}</td><td>{current?.cmj_delta_pct !== null && current?.cmj_delta_pct !== undefined && current.cmj_delta_pct < -2.5 ? <PosChip tone="warn">CMJ drop</PosChip> : <span className="pos-faint">—</span>}</td></tr>;
                    })}</tbody>
                  </table>
                </div>
              </section>
              <section className="pos-module">
                <div className="pos-module-head"><h2>Small multiples</h2><span className="sub">squad trajectories · cm</span></div>
                <div className="pos-module-body">
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(4,minmax(0,1fr))", gap: 6 }}>
                    {filtered.map((athlete) => (
                      <Link key={athlete.display_id} href={`/athletes/${athlete.display_id}`} style={{ textDecoration: "none", color: "inherit", border: "1px solid var(--pos-line)", padding: "4px 5px" }}>
                        <div className="pos-k" style={{ fontSize: 6 }}>{athlete.display_id} · {athlete.position}</div>
                        <Sparkline values={athlete.weeks.map((week) => week.cmj_height_cm)} width={110} height={24} color="#5fd4e8" band={cmjBand(athlete.weeks)} />
                      </Link>
                    ))}
                  </div>
                </div>
              </section>
            </div>
          </>
        ) : null}

        {metric === "availability" ? (
          <>
            <div className="pos-callout" style={{ marginBottom: 2 }}><b>Injury module unavailable.</b> The snapshot has no injury, exposure or return-to-play table. Availability is roster status only; the product does not infer injury risk.</div>
            <div className="pos-grid-2" style={{ alignItems: "start" }}>
              <section className="pos-module">
                <div className="pos-module-head"><h2>Roster status</h2><span className="sub">28 athletes · roster source only</span><span className="right"><PosChip tone="warn">NO INJURY TABLE</PosChip></span></div>
                <div className="pos-module-body flush">
                  <table className="pos-table">
                    <thead><tr><th>Athlete</th><th>Position</th><th>Availability</th><th>Reason</th></tr></thead>
                    <tbody>{(athletes.data ?? []).map((athlete) => <tr key={athlete.display_id}><td><Link href={`/athletes/${athlete.display_id}`} className="pos-link">{athlete.display_id}</Link></td><td>{athlete.position}</td><td><PosChip tone="ok">Roster only</PosChip></td><td className="pos-faint">{athlete.availability.reason}</td></tr>)}</tbody>
                  </table>
                </div>
              </section>
              <section className="pos-module">
                <div className="pos-module-head"><h2>Availability and injury</h2><span className="sub">explicit empty states</span></div>
                <div className="pos-module-body">
                  <PosEmpty title="Injury burden unavailable">Injury incidence requires injuries and an exposure denominator. Neither is admitted. No injury count, rate per 1000 h or return-to-play stage is displayed.</PosEmpty>
                  <div className="pos-hr" />
                  <PosEmpty title="Return to play not configured" info>RTP requires injury, criteria and clearance data. This module is unavailable rather than simulated.</PosEmpty>
                  <div className="pos-hr" />
                  <PosEmpty title="Session attendance is P2" info>Planned sessions exist, but no attendance contract is admitted. The planner does not claim who attended.</PosEmpty>
                </div>
              </section>
            </div>
          </>
        ) : null}

        {metric === "movement" ? (
          <>
            <div className="pos-callout info"><b>Bounded segment, not a full match.</b> {movement.data?.window_label}; {movement.data?.quality.note}</div>
            <div className="pos-grid-2" style={{ gridTemplateColumns: "1.2fr 1fr", alignItems: "start" }}>
              <section className="pos-module">
                <div className="pos-module-head"><h2>Tracking channels</h2><span className="sub">10 Hz · positional path length</span><span className="right"><PosChip tone="info">SEGMENT</PosChip></span></div>
                <div className="pos-module-body flush">
                  <table className="pos-table">
                    <thead><tr><th>Channel</th><th>Team</th><th className="r">Distance m</th><th className="r">HSR m</th><th className="r">Max m/s</th><th className="r">Resets</th></tr></thead>
                    <tbody>{movement.data?.players.map((player) => <tr key={player.player_id} className={player.player_id === playerId ? "is-selected" : ""}><td><button type="button" className="pos-link" style={{ background: "none", border: 0, padding: 0 }} onClick={() => setPlayerId(player.player_id)}>{player.player_id}</button></td><td>{player.team}</td><td className="r">{fmt(player.distance_m, 1)}</td><td className="r">{fmt(player.hsr_m, 1)}</td><td className="r">{fmt(player.max_speed_m_s, 1)}</td><td className="r">{player.position_resets}</td></tr>)}</tbody>
                  </table>
                </div>
              </section>
              <section className="pos-module">
                <div className="pos-module-head"><h2>{selectedMovement?.player_id ?? "—"} segment</h2><span className="sub">speed zones · positional</span></div>
                <div className="pos-module-body">
                  {selectedMovement ? (
                    <>
                      <div className="pos-grid-3" style={{ marginBottom: 8 }}>
                        <div className="pos-card"><div className="pos-k">Distance</div><div className="pos-metric-value">{fmt(selectedMovement.distance_m, 0)}<span className="u">m</span></div></div>
                        <div className="pos-card"><div className="pos-k">HSR</div><div className="pos-metric-value">{fmt(selectedMovement.hsr_m, 0)}<span className="u">m</span></div></div>
                        <div className="pos-card"><div className="pos-k">Max</div><div className="pos-metric-value">{fmt(selectedMovement.max_speed_m_s, 1)}<span className="u">m/s</span></div></div>
                      </div>
                      <SpeedZoneBars distance={selectedMovement.distance_m} hsr={selectedMovement.hsr_m} maxSpeed={selectedMovement.max_speed_m_s} />
                      <div className="pos-hr" />
                      <div className="pos-warn-note">Tracking channel upload is not mapped to the athlete identity. No claim is made that a roster athlete is this channel.</div>
                    </>
                  ) : <PosEmpty title="No segment">No tracking data.</PosEmpty>}
                </div>
              </section>
            </div>
          </>
        ) : null}

        {cohort === "individual" ? (
          <section className="pos-module">
            <div className="pos-module-head"><h2>{athleteId} · individual trajectory</h2><span className="sub">own baseline · one athlete model</span><span className="right"><Link href={`/athletes/${athleteId}`} className="pos-link">Open Athlete 360 →</Link></span></div>
            <div className="pos-module-body">
              {selected.isLoading ? <PosLoading label="Reading athlete record" /> : selected.data ? (
                <>
                  <div className="pos-stat-strip" style={{ border: 0 }}>
                    <div className="pos-stat"><div className="k">Readiness</div><div className="v">{fmt(selected.data.current.readiness, 1)}<span className="u">/10</span></div></div>
                    <div className="pos-stat"><div className="k">Load ratio</div><div className="v">{fmt(selected.data.current.load_ratio, 2)}<span className="u">AU</span></div></div>
                    <div className="pos-stat"><div className="k">CMJ</div><div className="v">{fmt(selected.data.current.cmj_height_cm, 2)}<span className="u">cm</span></div></div>
                    <div className="pos-stat"><div className="k">Δ baseline</div><div className="v">{fmtSigned(selected.data.current.cmj_delta_pct, 1)}</div></div>
                    <div className="pos-stat"><div className="k">Availability</div><div className="v" style={{ fontSize: 10 }}>ROSTER</div><div className="s">no injury table</div></div>
                  </div>
                  <div className="chart" style={{ height: 200, marginTop: 6 }}><TrendChart data={selected.data.weeks.map((week) => ({ week: week.week, value: week.cmj_height_cm, phase: week.phase }))} unit="cm" band={cmjBand(selected.data.weeks.map((week) => ({ ...week, cmj_delta_pct: week.cmj_delta_pct })))} reference={selected.data.current.baseline_cmj_height_cm} color="#5fd4e8" height={200} /></div>
                </>
              ) : <PosEmpty title="No record">No longitudinal record for this athlete.</PosEmpty>}
            </div>
          </section>
        ) : null}

        <section className="pos-module">
          <div className="pos-module-head"><h2>Squad small multiples</h2><span className="sub">{filtered.length} athletes · readiness sparkline · W1–16</span><span className="right"><PosChip tone="info">{cohort === "squad" ? "SQUAD" : cohort === "position" ? position : "INDIVIDUAL"}</PosChip></span></div>
          <div className="pos-module-body">
            <div style={{ display: "grid", gridTemplateColumns: "repeat(7,minmax(0,1fr))", gap: 5 }}>
              {filtered.map((athlete) => (
                <Link key={athlete.display_id} href={`/athletes/${athlete.display_id}`} style={{ textDecoration: "none", color: "inherit", border: "1px solid var(--pos-line)", padding: "4px 5px" }} title={`${athlete.display_id} · readiness`}>
                  <div className="pos-k" style={{ fontSize: 6 }}>{athlete.display_id}</div>
                  <Sparkline values={athlete.weeks.map((week) => week.readiness)} width={100} height={22} color="#c8f36b" band={readinessBand(athlete.weeks)} />
                </Link>
              ))}
            </div>
          </div>
        </section>
      </main>

      <aside className="pos-aside" aria-label="Monitoring context">
        <div className="pos-aside-sec">
          <h3>Data quality</h3>
          <dl className="pos-kv">
            <dt>Valid trials</dt><dd>{data.data_quality.valid_trials} / {data.data_quality.present_trials}</dd>
            <dt>Missing slots</dt><dd>{data.data_quality.missing_slots}</dd>
            <dt>Excluded</dt><dd>{data.data_quality.excluded_trials}</dd>
            <dt>Completeness</dt><dd>{fmt(data.data_quality.completeness_pct, 2)}%</dd>
            <dt>Snapshot</dt><dd>DS-SYNTH-001</dd>
          </dl>
          <div className="pos-note" style={{ marginTop: 5 }}>Missing and excluded are distinct states; no zero-fill.</div>
        </div>
        <div className="pos-aside-sec">
          <h3>Reference rules</h3>
          <div className="pos-note">The athlete&apos;s own baseline is used before the cohort. Every chart states its reference window. A threshold is a review prompt, not a diagnosis.</div>
          <div className="pos-hr" />
          <dl className="pos-kv">
            <dt>Readiness</dt><dd>&lt; 5.5</dd>
            <dt>Load ratio</dt><dd>&gt; 1.30</dd>
            <dt>CMJ drop</dt><dd>&lt; −2.5%</dd>
          </dl>
        </div>
        <div className="pos-aside-sec">
          <div className="pos-callout"><b>No injury or exposure table.</b> This workspace cannot show injury burden, availability beyond roster status, or RTP.</div>
        </div>
        <div className="pos-aside-sec">
          <div className="pos-callout info"><b>Movement is bounded.</b> 3-minute tracking segment with position resets; not full-match distance or a GPS device validation.</div>
        </div>
        <div className="pos-aside-foot">Monitor · {data.as_of.slice(0, 10)}<br />DS-SYNTH-001 · synthetic<br /><b>REFERENCE FIRST</b></div>
      </aside>
    </div>
  );
}
