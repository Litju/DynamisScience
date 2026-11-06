"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, FileText, Snowflake } from "lucide-react";
import { performanceApi } from "@/lib/performance/api";
import { fmt, shortDateTime } from "@/lib/performance/format";
import type { PerformanceReport } from "@/lib/performance/types";
import { useRole } from "@/components/shell/RoleContext";
import { PosChip, PosEmpty, PosError, PosLoading, Toast, toneForStatus } from "./ui";

const AUDIENCES: { id: PerformanceReport["audience"]; label: string; note: string }[] = [
  { id: "coach", label: "Coach", note: "Squad status, flags, load, testing and evidence." },
  { id: "athlete", label: "Athlete", note: "Own readiness, load and testing; no clinical data." },
  { id: "medical", label: "Medical", note: "Availability and testing quality only; no injury table." },
  { id: "board", label: "Board", note: "Aggregate performance, data quality and evidence." },
];

export function ReportsView() {
  const client = useQueryClient();
  const { role } = useRole();
  const reports = useQuery({ queryKey: ["performance-reports"], queryFn: () => performanceApi.reports() });
  const athletes = useQuery({ queryKey: ["performance-athletes"], queryFn: performanceApi.athletes });
  const [audience, setAudience] = useState<PerformanceReport["audience"]>("coach");
  const [athleteId, setAthleteId] = useState("ATH-003");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    const requested = new URLSearchParams(window.location.search).get("report");
    if (requested) setSelectedId(requested);
  }, []);

  useEffect(() => {
    setAudience(role.id === "medical" ? "medical" : role.id === "director" ? "board" : "coach");
    setSelectedId(null);
  }, [role.id]);

  const audienceReports = useMemo(
    () => (reports.data ?? []).filter((report) => report.audience === audience),
    [reports.data, audience],
  );
  const selected = useMemo(
    () => audienceReports.find((report) => report.id === selectedId) ?? audienceReports[0] ?? null,
    [audienceReports, selectedId],
  );

  const compose = useMutation({
    mutationFn: () => performanceApi.createReport({ audience, athlete_id: audience === "athlete" ? athleteId : undefined, role: role.label }),
    onSuccess: (report) => {
      void client.invalidateQueries({ queryKey: ["performance-reports"] });
      setSelectedId(report.id);
      setToast(`${report.title} · v${report.version} composed as ${report.status}.`);
      window.setTimeout(() => setToast(null), 4500);
    },
  });

  const freeze = useMutation({
    mutationFn: (id: string) => performanceApi.freezeReport(id),
    onSuccess: (report) => {
      void client.invalidateQueries({ queryKey: ["performance-reports"] });
      setToast(`${report.id} frozen · content hash ${report.content_hash.slice(0, 12)}…`);
      window.setTimeout(() => setToast(null), 4500);
    },
  });

  if (reports.isLoading) return <div className="pos-page"><div className="pos-main"><PosLoading label="Reading performance report versions" /></div></div>;
  if (reports.error) return <div className="pos-page"><div className="pos-main"><PosError error={reports.error} onRetry={() => void reports.refetch()} /></div></div>;

  return (
    <div className="pos-page">
      <main className="pos-main" aria-label="Reports">
        <div className="pos-main-head">
          <div>
            <div className="pos-kicker">Audience templates · versioned · provenance retained</div>
            <h1>Reports</h1>
            <p>Compose what each audience needs to know, with uncertainty, missingness and the limits of the admitted data stated in the report.</p>
          </div>
          <div className="pos-actions">
            <Link href="/research/studies/STUDY-001?mode=report" className="pos-btn">Scientific report</Link>
            <button type="button" className="pos-btn primary" disabled={compose.isPending} onClick={() => compose.mutate()}><FileText size={10} />{compose.isPending ? "Composing…" : `Compose ${audience} report`}</button>
          </div>
        </div>

        <div className="pos-report-grid">
          {AUDIENCES.map((item) => {
            const versions = (reports.data ?? []).filter((report) => report.audience === item.id);
            return (
              <button key={item.id} type="button" className={`pos-report-card ${audience === item.id ? "is-active" : ""}`} onClick={() => { setAudience(item.id); setSelectedId(null); }}>
                <div className="pos-k">{item.id.toUpperCase()} · {versions.length} version{versions.length === 1 ? "" : "s"}</div>
                <b>{item.label} report</b>
                <p>{item.note}</p>
                <div style={{ marginTop: 5 }}><PosChip tone={versions.length ? "ok" : "neutral"}>{versions.length ? `LATEST ${versions[0].status}` : "NOT COMPOSED"}</PosChip></div>
              </button>
            );
          })}
        </div>

        {audience === "athlete" ? (
          <div className="pos-controls">
            <label className="pos-control"><span>Athlete</span><select value={athleteId} onChange={(event) => setAthleteId(event.target.value)}>{(athletes.data ?? []).map((athlete) => <option key={athlete.display_id} value={athlete.display_id}>{athlete.display_id} · {athlete.position}</option>)}</select></label>
            <span className="pos-note">The athlete template contains only that athlete&apos;s data and never another athlete&apos;s record.</span>
          </div>
        ) : null}

        <div className="pos-grid-2" style={{ gridTemplateColumns: "1.55fr 1fr", alignItems: "start" }}>
          <section className="pos-module">
            <div className="pos-module-head">
              <h2>{selected ? selected.title : `${AUDIENCES.find((item) => item.id === audience)?.label} report`}</h2>
              <span className="sub">{selected ? `${selected.id} · v${selected.version} · ${selected.status}` : "not composed"}</span>
              <span className="right">
                {selected ? <PosChip tone={toneForStatus(selected.status)}>{selected.status}</PosChip> : null}
                {selected && selected.status !== "FROZEN" ? <button type="button" className="pos-btn small" disabled={freeze.isPending} onClick={() => freeze.mutate(selected.id)}><Snowflake size={10} />Freeze</button> : null}
                {selected ? <a className="pos-btn small" href={performanceApi.reportExportUrl(selected.id)} target="_blank" rel="noreferrer"><Download size={10} />Export HTML</a> : null}
              </span>
            </div>
            <div className="pos-module-body">
              {!selected ? (
                <PosEmpty title={`${AUDIENCES.find((item) => item.id === audience)?.label} report is not composed`}>
                  Compose the report to create a version from the current snapshot, role and evidence. Nothing is fabricated when a source table is unavailable; the limitation is written into the report.
                </PosEmpty>
              ) : (
                <article className="pos-report-preview" aria-label="Report preview">
                  <h2>{selected.title}</h2>
                  <div className="pos-report-meta">
                    <span>{selected.id}</span><span>v{selected.version}</span><span>{selected.status}</span><span>{selected.audience}</span><span>by {selected.created_by}</span><span>as of {selected.provenance.as_of.slice(0, 10)}</span>
                  </div>
                  {selected.sections.map((section) => (
                    <section key={section.id}>
                      <h3>{section.title}</h3>
                      {section.body.map((paragraph) => <p key={paragraph}>{paragraph}</p>)}
                      {section.metrics?.length ? (
                        <div className="pos-report-metrics">
                          {section.metrics.map((metric) => (
                            <div className="pos-report-metric" key={metric.label}>
                              <span>{metric.label}</span>
                              <b>{typeof metric.value === "number" ? fmt(metric.value, String(metric.value).includes(".") ? 2 : 0) : metric.value} <em style={{ fontStyle: "normal", color: "var(--pos-muted)", fontSize: 7 }}>{metric.unit}</em></b>
                              <small>{metric.detail}</small>
                            </div>
                          ))}
                        </div>
                      ) : null}
                      {section.table?.length ? (
                        <table className="pos-table" style={{ marginTop: 6 }}>
                          <thead><tr>{Object.keys(section.table[0]).map((header) => <th key={header}>{header}</th>)}</tr></thead>
                          <tbody>{section.table.map((row, index) => <tr key={index}>{Object.keys(section.table![0]).map((header) => <td key={header}>{String(row[header])}</td>)}</tr>)}</tbody>
                        </table>
                      ) : null}
                    </section>
                  ))}
                  <div className="pos-hr" />
                  <h3>Evidence</h3>
                  {selected.evidence.length === 0 ? <p>No promoted evidence is cited in this report.</p> : selected.evidence.map((item) => (
                    <p key={item.id}><span className="pos-evidence-id">{item.id}</span> {item.title} · {fmt(item.estimate, 3)} {item.unit}{item.interval ? ` (95% CI ${fmt(item.interval.low, 3)} to ${fmt(item.interval.high, 3)})` : ""}</p>
                  ))}
                  <h3>Limitations</h3>
                  {selected.limitations.map((item) => <p key={item}>— {item}</p>)}
                  <h3>Provenance</h3>
                  <p>Snapshot {selected.provenance.snapshot_id} · checksums retained · engine {selected.provenance.report_engine} · content hash {selected.content_hash.slice(0, 24)}…</p>
                  <p>Tables: {selected.provenance.source_tables.join(", ")}.</p>
                </article>
              )}
            </div>
          </section>

          <div style={{ display: "grid", gap: 9 }}>
            <section className="pos-module">
              <div className="pos-module-head"><h2>{AUDIENCES.find((item) => item.id === audience)?.label} versions</h2><span className="sub">newest first</span></div>
              <div className="pos-module-body">
                {audienceReports.length === 0 ? <div className="pos-note">No version yet.</div> : (
                  <div className="pos-report-list">
                    {audienceReports.map((report) => (
                      <button key={report.id} type="button" className="pos-report-row" style={{ background: "none", border: 0, borderBottom: "1px solid var(--pos-line)", textAlign: "left", cursor: "pointer", width: "100%" }} onClick={() => setSelectedId(report.id)}>
                        <b>{report.id}</b>
                        <span>v{report.version} · {report.status}</span>
                        <span>{report.frozen_at ? shortDateTime(report.frozen_at) : shortDateTime(report.created_at)}</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </section>
            <section className="pos-module">
              <div className="pos-module-head"><h2>Report contract</h2><span className="sub">what must be true</span></div>
              <div className="pos-module-body">
                <div className="pos-check"><span className="tick done">✓</span>Snapshot and checksums retained<span className="status done">ALWAYS</span></div>
                <div className="pos-check"><span className="tick done">✓</span>Evidence and limitations cited<span className="status done">ALWAYS</span></div>
                <div className="pos-check"><span className="tick done">✓</span>Audience separation<span className="status done">ROLE</span></div>
                <div className="pos-check"><span className="tick done">✓</span>Unavailable data stated<span className="status done">INJURY</span></div>
                <div className="pos-check"><span className="tick"></span>Freeze version before sharing<span className="status pending">{selected?.status === "FROZEN" ? "FROZEN" : "DRAFT"}</span></div>
                <div className="pos-hr" />
                <div className="pos-note">Freezing stores the current content and hash. Later data changes do not rewrite a frozen version.</div>
              </div>
            </section>
            <section className="pos-module">
              <div className="pos-module-head"><h2>Audience boundaries</h2><span className="sub">role-aware</span></div>
              <div className="pos-module-body">
                <dl className="pos-kv">
                  <dt>Coach</dt><dd>squad + evidence</dd>
                  <dt>Medical</dt><dd>roster + limits</dd>
                  <dt>Athlete</dt><dd>own record only</dd>
                  <dt>Board</dt><dd>aggregate + evidence</dd>
                </dl>
                <div className="pos-hr" />
                <div className="pos-note">The medical template does not show clinical notes or injury data because none are admitted. It explicitly states that it is not a clearance.</div>
              </div>
            </section>
          </div>
        </div>

        <section className="pos-module">
          <div className="pos-module-head"><h2>Scientific reports</h2><span className="sub">research workspace · immutable evidence</span><span className="right"><Link href="/research/studies/STUDY-001?mode=report" className="pos-link">Open report →</Link></span></div>
          <div className="pos-module-body">
            <div className="pos-grid-2">
              <div className="pos-card">
                <div className="pos-k">STUDY-001 · REPORT-001</div>
                <b style={{ fontSize: 9 }}>Strength Intervention — Interim Scientific Report</b>
                <p>Full scientific report from the frozen analysis plan, with methods, diagnostics, estimates, figures and provenance.</p>
              </div>
              <div className="pos-card">
                <div className="pos-k">Real-data research</div>
                <b style={{ fontSize: 9 }}>Admitted studies remain separate</b>
                <p>Real datasets are research-only and never mixed into the synthetic squad dashboard or performance reports.</p>
              </div>
            </div>
          </div>
        </section>
      </main>

      <aside className="pos-aside" aria-label="Report context">
        <div className="pos-aside-sec">
          <h3>Report register</h3>
          <dl className="pos-kv">
            <dt>Versions</dt><dd>{reports.data?.length ?? 0}</dd>
            <dt>Coach</dt><dd>{(reports.data ?? []).filter((r) => r.audience === "coach").length}</dd>
            <dt>Athlete</dt><dd>{(reports.data ?? []).filter((r) => r.audience === "athlete").length}</dd>
            <dt>Medical</dt><dd>{(reports.data ?? []).filter((r) => r.audience === "medical").length}</dd>
            <dt>Board</dt><dd>{(reports.data ?? []).filter((r) => r.audience === "board").length}</dd>
          </dl>
        </div>
        <div className="pos-aside-sec">
          <h3>Current role</h3>
          <div className="pos-note">{role.label} · {role.note}</div>
        </div>
        <div className="pos-aside-sec"><div className="pos-callout info"><b>One source of truth.</b> Every report cites DS-SYNTH-001 and the same evidence ledger. Export is an HTML snapshot; frozen versions do not change.</div></div>
        <div className="pos-aside-sec"><div className="pos-callout"><b>No injury claim.</b> Medical and board reports state that injury, exposure and RTP data are unavailable. No injury risk is inferred.</div></div>
        <div className="pos-aside-foot">Reports · local persistence<br />Evidence and versions append-only<br /><b>FROZEN ≠ REWRITTEN</b></div>
      </aside>
      <Toast message={toast} />
    </div>
  );
}
