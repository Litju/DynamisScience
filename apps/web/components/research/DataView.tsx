"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { scienceApi } from "@/lib/api";
import { ErrorBox, KV, Loading, State } from "@/components/ui";
import { shortChecksum } from "@/lib/scientific";

export function DataView({ snapshotId }: { snapshotId: string }) {
  const datasets = useQuery({ queryKey: ["datasets"], queryFn: scienceApi.datasets });
  const detail = useQuery({ queryKey: ["dataset", snapshotId], queryFn: () => scienceApi.dataset(snapshotId) });
  const [table, setTable] = useState<string>("cmj_trials");
  const selected = detail.data?.tables.find((item) => item.name === table);
  const snapshot = detail.data?.snapshot;
  return (
    <main className="page">
      <div className="page-inner">
        <div className="page-head">
          <div>
            <div className="crumb">DATA / {snapshotId}</div>
            <h1>{snapshot?.label ?? snapshotId}</h1>
            <p>Immutable analytical snapshot. Every analysis, figure and report in this workspace resolves to these files and checksums.</p>
          </div>
          <div style={{ display: "flex", gap: 6 }}>
            <State>FROZEN</State>
            <State>SYNTHETIC</State>
          </div>
        </div>
        {detail.isLoading && <Loading label="Reading snapshot manifest and Parquet schemas" />}
        {detail.error && <ErrorBox error={detail.error} onRetry={() => void detail.refetch()} />}
        {detail.data && snapshot && (
          <div className="data-grid">
            <div style={{ display: "grid", gap: 14, alignContent: "start" }}>
              <div className="frame">
                <div className="frame-head"><h3>Tables</h3><span className="faint small">{detail.data.tables.length} Parquet files · row counts verified against the manifest</span></div>
                <div className="table-wrap">
                  <table className="table">
                    <thead><tr><th>Table</th><th>Description</th><th className="r">Rows</th><th className="r">Rate</th><th>SHA-256</th><th>Manifest</th></tr></thead>
                    <tbody>
                      {detail.data.tables.map((item) => (
                        <tr key={item.name} role="button" tabIndex={0} className={item.name === table ? "is-selected" : ""} onClick={() => setTable(item.name)} onKeyDown={(event) => event.key === "Enter" && setTable(item.name)}>
                          <td className="mono">{item.file}</td>
                          <td className="muted">{item.description}</td>
                          <td className="r mono num">{item.rows.toLocaleString()}</td>
                          <td className="r mono">{item.sample_rate_hz ? `${item.sample_rate_hz} Hz` : "—"}</td>
                          <td className="mono faint">{shortChecksum(item.checksum_sha256, 16)}</td>
                          <td><State plain>{item.rows === item.manifest_rows ? "VALID" : "WARNING"}</State></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
              {selected && (
                <div className="frame">
                  <div className="frame-head"><h3 className="mono">{selected.file}</h3><span className="faint small">{selected.columns.length} columns</span></div>
                  <div className="table-wrap" style={{ maxHeight: 380 }}>
                    <table className="table">
                      <thead><tr><th>Column</th><th>Type</th><th className="r">Nulls</th></tr></thead>
                      <tbody>
                        {selected.columns.map((column) => (
                          <tr key={column.name}><td className="mono">{column.name}</td><td className="mono faint">{column.dtype}</td><td className="r mono num">{column.null_count}</td></tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
            <div style={{ display: "grid", gap: 14, alignContent: "start" }}>
              <div className="frame">
                <div className="frame-head"><h3>Snapshot</h3></div>
                <div className="frame-body">
                  <KV rows={[
                    ["Snapshot ID", snapshot.id, "mono"],
                    ["Seed", String(snapshot.seed), "mono"],
                    ["Generator", snapshot.generator_version, "mono"],
                    ["Schema", snapshot.schema_version, "mono"],
                    ["Generated", snapshot.generated_at, "mono"],
                    ["Athletes", `${snapshot.subjects.total} · ${snapshot.subjects.weeks} weeks`],
                    ["Pose athletes", snapshot.pose_athletes.join(", "), "mono"],
                    ["Source", String(snapshot.provenance.generator ?? ""), "mono"],
                  ]} />
                </div>
              </div>
              <div className="frame">
                <div className="frame-head"><h3>Quality</h3></div>
                <div className="frame-body">
                  <KV rows={[
                    ["Valid trials", detail.data.quality.valid_measurements.toLocaleString()],
                    ["Excluded trials", `${detail.data.quality.excluded_measurements} (remain discoverable)`],
                    ["Missing slots", `${detail.data.quality.missing_observations} of ${detail.data.quality.expected_slots}`],
                    ["Provenance complete", `${detail.data.quality.provenance_completeness.toFixed(1)}% of ${detail.data.quality.total_records} records`],
                  ]} />
                  <div className="hr" />
                  {detail.data.quality.excluded_trials.map((trial) => (
                    <div key={trial.trial_id} className="note bad"><span className="mono">{trial.trial_id}</span><span>{trial.reason}</span></div>
                  ))}
                  <div className="note" style={{ marginTop: 6 }}>{detail.data.quality.missing_slots.length} missing trial slots are reported, never imputed.</div>
                </div>
              </div>
              <div className="frame">
                <div className="frame-body">
                  <div className="note warn">{detail.data.disclaimer}</div>
                  <div className="note" style={{ marginTop: 8 }}>Used by {datasets.data?.find((item) => item.id === snapshotId)?.used_by_studies.map((id) => <Link key={id} href={`/research/studies/${id}`} className="mono" style={{ color: "var(--signal)", marginLeft: 4 }}>{id}</Link>)}</div>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
