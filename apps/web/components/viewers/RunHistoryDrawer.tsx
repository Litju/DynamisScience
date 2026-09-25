"use client";

import { GitBranch, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { metricOption, primaryResult, formatSig, formatSignedSig } from "@/lib/scientific";
import { Button, KV, Loading, State } from "@/components/ui";
import { useWorkbench } from "@/components/workbench/context";
import { useRuns } from "@/components/workbench/data";
import type { Run } from "@/lib/types";

function headline(run: Run): string {
  const result = primaryResult<Record<string, unknown>>(run.result) ?? {};
  const unit = metricOption(run.outcome_metric_id ?? run.execution?.analysis_spec.outcome_metric_id).unit;
  if (run.method_id === "METH-LONG") {
    const contrasts = result.contrasts as Record<string, { estimate: number; ci_low: number; ci_high: number }> | undefined;
    const primary = contrasts?.[String(result.primary_contrast_id)];
    return primary ? `Δ ${formatSignedSig(primary.estimate, 3)} ${unit} [${formatSig(primary.ci_low, 3)}, ${formatSig(primary.ci_high, 3)}]` : "—";
  }
  if (run.method_id === "METH-REL") return `ICC ${formatSig(result.icc_3_1 as number, 3)} · TE ${formatSig(result.typical_error as number, 3)} ${unit}`;
  return `median Δ ${formatSignedSig(result.median_change as number, 3)} ${unit}`;
}

/** The immutable run ledger, available from the study bar rather than as a destination. */
export function RunHistoryDrawer() {
  const wb = useWorkbench();
  const runs = useRuns();
  const [selected, setSelected] = useState<string | null>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    closeRef.current?.focus({ preventScroll: true });
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        wb.setHistoryOpen(false);
      }
    };
    window.addEventListener("keydown", onKey, true);
    return () => {
      window.removeEventListener("keydown", onKey, true);
      previous?.focus?.({ preventScroll: true });
    };
  }, [wb]);
  const run = runs.data?.find((item) => item.id === selected) ?? runs.data?.[0];
  return (
    <div className="drawer-backdrop" onMouseDown={() => wb.setHistoryOpen(false)}>
      <div className="drawer" role="dialog" aria-modal="true" aria-label="Run history" onMouseDown={(event) => event.stopPropagation()}>
        <header className="viewer-head">
          <span className="kind">Run history</span>
          <strong>Immutable execution ledger</strong>
          <span className="faint">{runs.data?.length ?? 0} runs · append-only · runs are never edited; a changed configuration is a new run</span>
          <span className="spacer" />
          <button ref={closeRef} type="button" className="btn btn-sm" onClick={() => wb.setHistoryOpen(false)}><X size={12} />Close</button>
        </header>
        <div className="drawer-body">
          <div className="table-wrap" style={{ minHeight: 0 }}>
            {runs.isLoading && <Loading label="Reading ledger" />}
            <table className="table">
              <thead><tr><th>Run</th><th>Spec</th><th>Method</th><th>Outcome</th><th>Cohort</th><th>Plan</th><th>Result</th><th>Evidence</th><th>Created</th></tr></thead>
              <tbody>
                {runs.data?.map((item) => (
                  <tr key={item.id} role="button" tabIndex={0} className={run?.id === item.id ? "is-selected" : ""} onClick={() => setSelected(item.id)} onKeyDown={(event) => event.key === "Enter" && setSelected(item.id)}>
                    <td className="mono">{item.id}</td>
                    <td className="mono faint">{item.analysis_spec_id}</td>
                    <td className="mono">{item.method_id}</td>
                    <td className="mono faint">{(item.outcome_metric_id ?? item.execution?.analysis_spec.outcome_metric_id ?? "").replace("MET-CMJ-", "")}</td>
                    <td className="mono faint">{item.cohort_id}</td>
                    <td><State plain>{item.plan_alignment ?? "PLANNED"}</State></td>
                    <td className="mono small">{headline(item)}{item.reproduces?.length ? <span className="faint"> · ≡ {item.reproduces.join(",")}</span> : null}</td>
                    <td className="mono">{item.evidence_ids?.join(", ") || <span className="faint">—</span>}</td>
                    <td className="mono faint">{item.created_at.slice(0, 19).replace("T", " ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <aside className="inspector" style={{ borderLeft: "1px solid var(--line)" }}>
            {run && (
              <>
                <div className="insp-head"><div className="insp-kind"><span>AnalysisRun</span><State>{run.status}</State></div><div className="insp-title mono">{run.id}</div></div>
                <div className="insp-scroll">
                  <section className="insp-sec"><KV rows={[["Spec", run.analysis_spec_id, "mono"], ["Method", run.method_id, "mono"], ["Snapshot", run.snapshot_id, "mono"], ["Cohort", run.cohort_id, "mono"], ["Plan alignment", run.plan_alignment ?? "PLANNED"], ["Result", headline(run), "mono"], ["Digest", run.result_digest, "mono"], ["Reproduces", run.reproduces?.join(", ") || "—", "mono"], ["Duration", `${run.duration_ms.toFixed(1)} ms`, "mono"], ["Seed", String(run.seed ?? ""), "mono"]]} /></section>
                  <section className="insp-sec"><h4>Reproducibility key</h4><div className="mono small" style={{ overflowWrap: "anywhere" }}>{run.reproducibility_key}</div></section>
                  <section className="insp-sec">
                    <div className="insp-actions">
                      <Button size="sm" variant="primary" onClick={() => { wb.inspect({ kind: "run", id: run.id }); wb.setHistoryOpen(false); }}>Inspect in workbench</Button>
                      <Button size="sm" onClick={() => { wb.setHistoryOpen(false); wb.openLineage(run.id); }}><GitBranch size={12} />Lineage</Button>
                    </div>
                  </section>
                </div>
              </>
            )}
          </aside>
        </div>
      </div>
    </div>
  );
}
