"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight } from "lucide-react";
import { scienceApi } from "@/lib/api";
import { ErrorBox, Loading, State } from "@/components/ui";

export function ResearchHome() {
  const studies = useQuery({ queryKey: ["studies"], queryFn: scienceApi.studies });
  return (
    <main className="page">
      <div className="page-inner">
        <div className="page-head">
          <div>
            <div className="crumb">RESEARCH</div>
            <h1>Research</h1>
            <p>Research contexts in this local workspace. A study carries its question, frozen plan, dataset, cohort, investigations, evidence and report.</p>
          </div>
        </div>

        <div className="section-title"><h2>Studies</h2><span>{studies.data ? `${studies.data.length} study` : ""}</span></div>
        <div className="frame">
          {studies.isLoading && <div className="frame-body"><Loading label="Reading local study registry" /></div>}
          {studies.error && <div className="frame-body"><ErrorBox error={studies.error} onRetry={() => void studies.refetch()} /></div>}
          {studies.data?.map((study) => (
            <Link key={study.id} href={`/research/studies/${study.id}`} className="study-row">
              <div>
                <div className="mono faint">{study.id}</div>
                <div style={{ marginTop: 4, display: "flex", gap: 4, flexWrap: "wrap" }}><State>{study.state}</State><State>SYNTHETIC</State></div>
              </div>
              <div style={{ minWidth: 0 }}>
                <strong>{study.title}</strong>
                <div className="q">{study.research_question}</div>
              </div>
              <div className="meta">
                <div className="mono">{study.dataset_snapshot_id}</div>
                <div>{study.participant_count} athletes · weeks {study.start_week}–{study.end_week}</div>
              </div>
              <div className="meta">
                <div>Plan <State plain>{study.plan_status}</State></div>
                <div className="num">{study.run_count} runs · {study.evidence_count} evidence</div>
              </div>
              <div className="meta">
                <div>{study.investigation_ids.length} investigation</div>
                <div className="mono">{study.last_run_at ? new Date(study.last_run_at).toLocaleDateString() : "—"}</div>
              </div>
              <div className="study-open">Open workbench <ArrowRight size={14} /></div>
            </Link>
          ))}
        </div>

        <div className="section-title"><h2>Other research contexts</h2></div>
        <div className="frame">
          <div className="entry-types">
            <span><b>Monitoring programs</b> — entry type not enabled in this MVP</span>
            <span><b>Explorations</b> — entry type not enabled in this MVP</span>
          </div>
        </div>
      </div>
    </main>
  );
}
