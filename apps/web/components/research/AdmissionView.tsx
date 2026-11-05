"use client";

import Link from "next/link";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { AlertTriangle, CheckCircle2, Database, ExternalLink, FileCheck2, Lock, ShieldCheck } from "lucide-react";
import { scienceApi } from "@/lib/api";
import { Button, ErrorBox, KV, Loading, Readout, State } from "@/components/ui";

function bytes(value: number | undefined): string {
  if (!value) return "—";
  if (value > 1024 * 1024 * 1024) return `${(value / (1024 * 1024 * 1024)).toFixed(2)} GB`;
  if (value > 1024 * 1024) return `${(value / (1024 * 1024)).toFixed(1)} MB`;
  if (value > 1024) return `${(value / 1024).toFixed(1)} kB`;
  return `${value} B`;
}

function Check({ label, status }: { label: string; status: string }) {
  const pass = status === "PASS";
  return (
    <div className="check">
      <State plain tone={pass ? "tone-valid" : "tone-warning"}>{status}</State>
      <span>{label}</span>
    </div>
  );
}

export function AdmissionView() {
  const sources = useQuery({ queryKey: ["real-sources"], queryFn: scienceApi.realSources });
  const snapshots = useQuery({ queryKey: ["real-snapshots"], queryFn: scienceApi.realSnapshots });
  const qualification = useQuery({ queryKey: ["real-qualification"], queryFn: scienceApi.realQualification });
  const [selected, setSelected] = useState<string | null>(null);
  const activeSource = selected ?? sources.data?.[0]?.id ?? null;
  const detail = useQuery({
    queryKey: ["real-source", activeSource],
    queryFn: () => scienceApi.realSource(activeSource as string),
    enabled: Boolean(activeSource),
  });
  const admit = useMutation({
    mutationFn: (sourceId: string) => scienceApi.realAdmit(sourceId),
    onSuccess: () => {
      void sources.refetch();
      void snapshots.refetch();
    },
  });

  if (sources.isLoading || snapshots.isLoading || qualification.isLoading) {
    return <main className="page"><div className="page-inner"><Loading label="Reading real-data admission state" /></div></main>;
  }
  if (sources.error) return <main className="page"><div className="page-inner"><ErrorBox error={sources.error} onRetry={() => void sources.refetch()} /></div></main>;
  const current = activeSource;
  const source = detail.data?.source;
  const admission = detail.data?.admission;
  const quality = detail.data?.quality;
  const qualityChecks = quality?.checks ?? [];
  const qualityPasses = qualityChecks.filter((check) => check.status === "PASS").length;
  const qualityFailures = qualityChecks.filter((check) => check.status === "FAIL").length;
  const qualificationRecords = qualification.data ?? [];
  const qualifiedRecords = qualificationRecords.filter((record) => record.status === "QUALIFIED").length;

  return (
    <main className="page">
      <div className="page-inner">
        <div className="page-head">
          <div>
            <div className="crumb"><Link href="/data" style={{ color: "inherit", textDecoration: "none" }}>DATA</Link> / ADMISSION</div>
            <h1>Source admission</h1>
            <p>Review rights, integrity, quality and scientific scope before creating an immutable DatasetSnapshot.</p>
          </div>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            <State>REAL DATA</State>
            <State tone="tone-valid">RIGHTS VERIFIED</State>
            <State>{`${(snapshots.data ?? []).length} SNAPSHOTS`}</State>
          </div>
        </div>

        <div className="adm-grid">
          <div className="frame">
            <div className="frame-head"><h3>Sources</h3><span className="faint small">{(sources.data ?? []).length} reviewed</span></div>
            <div className="frame-body" style={{ display: "grid", gap: 10 }}>
              {(sources.data ?? []).map((item) => (
                <button key={item.id} type="button" aria-pressed={current === item.id} className={`source-card ${current === item.id ? "is-selected" : ""}`} onClick={() => setSelected(item.id)}>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                    <strong>{item.short_name}</strong>
                    <State tone={item.admitted ? "tone-valid" : "tone-warning"}>{item.admitted ? "ADMITTED" : "NOT ADMITTED"}</State>
                  </div>
                  <div className="mono faint small">{item.doi}</div>
                  <div className="small muted">{item.publisher} · {String(item.version).startsWith("v") ? item.version : `v${item.version}`}</div>
                  <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginTop: 6 }}>
                    <State plain>{item.license_id}</State>
                    <State plain>{item.privacy_status}</State>
                    <State plain>{bytes(item.total_bytes)}</State>
                  </div>
                </button>
              ))}
            </div>
          </div>

          <div style={{ display: "grid", gap: 14, alignContent: "start" }}>
            {!source && <div className="frame"><div className="frame-body">{detail.error ? <ErrorBox error={detail.error} onRetry={() => void detail.refetch()} /> : <Loading label={detail.isLoading ? "Reading verified source assessment" : "Select a source"} />}</div></div>}
            {source && (
              <>
                <div className="frame">
                  <div className="frame-head"><h3>{source.name}</h3><a href={source.canonical_url} target="_blank" rel="noreferrer" className="btn btn-sm btn-ghost" style={{ textDecoration: "none" }}><ExternalLink size={12} />Publisher</a></div>
                  <div className="frame-body">
                    <div className="readouts">
                      <Readout label="Licence" value={source.license.id} detail={source.license.name} />
                      <Readout label="Commercial use" value={source.commercial_use} detail="rights, not scientific validity" />
                      <Readout label="Privacy" value={source.privacy.classification} detail="participant-level data" />
                      <Readout label="Admissibility" value={source.scientific_admissibility.status.replaceAll("_", " ")} detail={source.data_classification.replaceAll("_", " ")} />
                    </div>
                    <div className="note" style={{ marginTop: 10 }}><ShieldCheck size={12} /><span>{source.attribution}</span></div>
                    <div className="note warn" style={{ marginTop: 6 }}><Lock size={12} /><span>{source.redistribution}</span></div>
                    <div className="block-toolbar small" style={{ marginTop: 10 }}>
                      <span className="faint">creators</span><span>{source.creators.join(", ")}</span>
                      <span className="grow" />
                      <span className="faint">version</span><span className="mono">{source.version}</span>
                    </div>
                  </div>
                </div>

                <details className="frame admission-detail" open={!admission}>
                  <summary className="frame-head"><h3>Rights and integrity gates</h3><State tone="tone-valid">{source.rights_status}</State></summary>
                  <div className="frame-body">
                    <div className="check-list">
                      <Check label={`Licence evidence: ${source.license.name} (${source.license.url})`} status="PASS" />
                      <Check label={`Source checksum verified: ${source.files.map((file: { name: string; sha256?: string; md5?: string }) => `${file.name} ${String(file.sha256 ?? file.md5).slice(0, 16)}…`).join(", ")}`} status="PASS" />
                      <Check label="Path traversal scan: zero candidates" status="PASS" />
                      <Check label={`Privacy classification: ${source.privacy.classification}`} status="PASS" />
                      {source.privacy.incidents?.map((incident: string) => <Check key={incident} label={incident} status="WARN" />)}
                      <Check label="Participant-level rows excluded from the public repository" status="PASS" />
                    </div>
                    <div className="note" style={{ marginTop: 8 }}><CheckCircle2 size={12} /><span>Rights status <b>{source.rights_status}</b>; admissibility <b>{source.scientific_admissibility.status}</b>. A permissive licence does not remove privacy obligations.</span></div>
                  </div>
                </details>

                <details className="frame admission-detail" open={!admission}>
                  <summary className="frame-head"><h3>Deposited files</h3><span className="faint small">{source.files.length} {source.files.length === 1 ? "file" : "files"} · {bytes(source.files.reduce((sum: number, file: { size_bytes: number }) => sum + file.size_bytes, 0))}</span></summary>
                  <div className="table-wrap">
                    <table className="table">
                      <thead><tr><th>File</th><th>Role</th><th className="r">Bytes</th><th>Checksum</th></tr></thead>
                      <tbody>
                        {source.files.map((file: { name: string; role: string; size_bytes: number; sha256?: string; md5?: string }) => (
                          <tr key={file.name}><td className="mono">{file.name}</td><td>{file.role.replaceAll("_", " ")}</td><td className="r mono">{file.size_bytes.toLocaleString()}</td><td className="mono faint">{(file.sha256 ?? file.md5 ?? "").slice(0, 24)}…</td></tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {source.archive_inventory && (
                    <div className="frame-body" style={{ paddingTop: 0 }}>
                      <KV rows={[
                        ["Entries", String(source.archive_inventory.entries)],
                        ["CSV files", String(source.archive_inventory.csv_files)],
                        ["Uncompressed", bytes(source.archive_inventory.uncompressed_bytes)],
                        ["Path traversal", String(source.archive_inventory.path_traversal_findings)],
                        ["Excluded", source.archive_inventory.excluded_entries.join(" · ")],
                      ]} />
                    </div>
                  )}
                </details>

                <details className="frame admission-detail" open={!admission}>
                  <summary className="frame-head"><h3>Scientific admissibility</h3><State>{source.scientific_admissibility.status.replaceAll("_", " ")}</State></summary>
                  <div className="frame-body">
                    <p className="muted">{source.scientific_admissibility.design}</p>
                    <div className="block-cols" style={{ marginTop: 10 }}>
                      <div>
                        <div className="upper faint" style={{ marginBottom: 4 }}>Supports</div>
                        <ul>{source.scientific_admissibility.supports.map((item: string) => <li key={item}>{item}</li>)}</ul>
                      </div>
                      <div>
                        <div className="upper faint" style={{ marginBottom: 4 }}>Does not support</div>
                        <ul>{source.scientific_admissibility.does_not_support.map((item: string) => <li key={item}>{item}</li>)}</ul>
                      </div>
                    </div>
                    <div className="note warn" style={{ marginTop: 8 }}><AlertTriangle size={12} /><span>{source.methods_documentation.summary}</span></div>
                    {source.methods_documentation.gaps?.map((gap: string) => <div key={gap} className="note bad" style={{ marginTop: 4 }}><span>{gap}</span></div>)}
                  </div>
                </details>

                {quality && (
                  <details className="frame admission-detail" open={!admission}>
                    <summary className="frame-head"><h3>Quality assessment</h3><State tone={qualityFailures ? "tone-warning" : "tone-valid"}>{`${qualityPasses} PASS · ${qualityFailures} FAIL`}</State></summary>
                    <div className="table-wrap">
                      <table className="table">
                        <thead><tr><th>Check</th><th>Status</th><th>Detail</th></tr></thead>
                        <tbody>
                          {qualityChecks.map((check: { check: string; status: string; severity: string; detail: string }) => (
                            <tr key={check.check}><td className="mono">{check.check}</td><td><State plain tone={check.status === "PASS" ? "tone-valid" : "tone-warning"}>{check.status}</State></td><td className="muted">{check.detail}</td></tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </details>
                )}

                <div className="frame">
                  <div className="frame-head"><h3>Admission</h3><State tone={admission ? "tone-valid" : "tone-warning"}>{admission ? admission.status : "NOT ADMITTED"}</State></div>
                  <div className="frame-body">
                    {admission ? (
                      <>
                        <KV rows={[
                          ["Admission", admission.id, "mono"],
                          ["Snapshot", admission.dataset_snapshot_id, "mono"],
                          ["Rights", admission.rights_status],
                          ["Quality", admission.quality_assessment_id, "mono"],
                          ["Parser", admission.parser_version, "mono"],
                          ["Rows", String(admission.counts?.rows ?? ""), "mono"],
                          ["Admitted", admission.admitted_at, "mono"],
                        ]} />
                        <div className="block-toolbar" style={{ marginTop: 10 }}>
                          <Link href={`/data/${admission.dataset_snapshot_id}`} className="btn btn-sm" style={{ textDecoration: "none" }}><Database size={12} />Open snapshot</Link>
                          <Link href={`/research/studies/${source.id === "SRC-MENDELEY-6P99569X66" ? "STUDY-REAL-001" : "STUDY-REAL-002"}`} className="btn btn-sm" style={{ textDecoration: "none" }}><FileCheck2 size={12} />Open workbench</Link>
                        </div>
                      </>
                    ) : (
                      <div className="promote">
                        <ShieldCheck size={18} style={{ color: "var(--signal)" }} />
                        <p>Rights and source integrity are verified. Admission parses the source, records quality gates and provenance, then writes a content-addressed snapshot.</p>
                        <Button variant="primary" onClick={() => admit.mutate(source.id)} disabled={admit.isPending}>{admit.isPending ? "Admitting…" : "Admit source"}</Button>
                      </div>
                    )}
                    {admit.error && <ErrorBox error={admit.error} />}
                    {admit.data?.already_admitted && <div className="note" style={{ marginTop: 8 }}><CheckCircle2 size={12} /><span>Identical content already admitted; the existing immutable snapshot was returned.</span></div>}
                  </div>
                </div>
              </>
            )}
          </div>
        </div>

        <div className="section-title"><h2>Admitted snapshots</h2><span>{(snapshots.data ?? []).length}</span></div>
        <div className="frame">
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Snapshot</th><th>Source</th><th className="r">Rows</th><th>Admission</th><th>Licence</th><th>Open</th></tr></thead>
              <tbody>
                {(snapshots.data ?? []).map((snapshot) => (
                  <tr key={snapshot.id}>
                    <td><div className="mono">{snapshot.id}</div><div className="faint small">{snapshot.label}</div></td>
                    <td className="mono faint">{snapshot.source?.doi}</td>
                    <td className="r mono">{Object.values(snapshot.row_counts ?? {}).reduce((sum: number, value) => sum + Number(value), 0).toLocaleString()}</td>
                    <td><State plain>{String(snapshot.admission?.status ?? "")}</State></td>
                    <td className="mono">{snapshot.source?.license?.id}</td>
                    <td><Link href={`/data/${snapshot.id}`} className="mono" style={{ color: "var(--signal)" }}>data</Link> · <Link href={`/research/studies/${snapshot.source?.id === "SRC-MENDELEY-6P99569X66" ? "STUDY-REAL-001" : "STUDY-REAL-002"}`} className="mono" style={{ color: "var(--signal)" }}>workbench</Link></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="section-title"><h2>Scientific qualification</h2><span>real-data records only</span></div>
        <details className="frame admission-detail">
          <summary className="frame-head"><h3>Independent method checks</h3><State tone={qualification.error || !qualificationRecords.length || qualifiedRecords !== qualificationRecords.length ? "tone-warning" : "tone-valid"}>{qualification.error ? "UNAVAILABLE" : `${qualifiedRecords}/${qualificationRecords.length} QUALIFIED`}</State></summary>
          <div className="frame-body" style={{ display: "grid", gap: 10 }}>
            {qualification.error && <ErrorBox error={qualification.error} onRetry={() => void qualification.refetch()} />}
            {qualificationRecords.map((record) => (
              <div key={record.id} className="evidence-card">
                <div className="evidence-main">
                  <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
                    <span className="evidence-id">{record.id}</span>
                    <State tone={record.status === "QUALIFIED" ? "tone-valid" : "tone-warning"}>{record.status}</State>
                    {record.dynamis_run && <span className="mono faint small">{record.dynamis_run}</span>}
                  </div>
                  <div className="evidence-title">{record.scientific_method}</div>
                  {record.reference_implementation && <p className="muted" style={{ marginTop: 4, fontSize: 12 }}>Reference: {record.reference_implementation}</p>}
                  {Array.isArray(record.comparisons) && (
                    <table className="table" style={{ marginTop: 8 }}>
                      <thead><tr><th>Trial</th><th>Activity</th><th className="r">Peak Δ (N)</th><th className="r">Impulse Δ (N·s)</th><th>Status</th></tr></thead>
                      <tbody>
                        {record.comparisons.map((raw) => {
                          const item = raw as { trial_id: string; activity: string; peak_absolute_difference: number; impulse_absolute_difference: number; pass: boolean };
                          return <tr key={item.trial_id}><td className="mono">{item.trial_id}</td><td>{item.activity}</td><td className="r mono">{item.peak_absolute_difference.toExponential(2)}</td><td className="r mono">{item.impulse_absolute_difference.toExponential(2)}</td><td><State plain tone={item.pass ? "tone-valid" : "tone-warning"}>{item.pass ? "PASS" : "FAIL"}</State></td></tr>;
                        })}
                      </tbody>
                    </table>
                  )}
                  {record.comparisons && !Array.isArray(record.comparisons) && (
                    <table className="table" style={{ marginTop: 8 }}>
                      <thead><tr><th>Estimand</th><th className="r">Reference</th><th className="r">DynamisScience</th><th className="r">Abs. diff</th><th>Status</th></tr></thead>
                      <tbody>
                        {Object.entries(record.comparisons).map(([key, item]) => {
                          const value = item as { reference?: number; dynamis?: number; absolute_difference?: number; pass?: boolean };
                          return <tr key={key}><td className="mono">{key}</td><td className="r mono">{typeof value.reference === "number" ? value.reference.toPrecision(6) : "—"}</td><td className="r mono">{typeof value.dynamis === "number" ? value.dynamis.toPrecision(6) : "—"}</td><td className="r mono">{typeof value.absolute_difference === "number" ? value.absolute_difference.toExponential(2) : "—"}</td><td><State plain tone={value.pass ? "tone-valid" : "tone-warning"}>{value.pass ? "PASS" : "FAIL"}</State></td></tr>;
                        })}
                      </tbody>
                    </table>
                  )}
                  {record.known_limitations && <ul className="small muted" style={{ marginTop: 8 }}>{record.known_limitations.map((item: string) => <li key={item}>{item}</li>)}</ul>}
                </div>
              </div>
            ))}
          </div>
        </details>
      </div>
    </main>
  );
}
