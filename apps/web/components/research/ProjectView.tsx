"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, Archive, Database, FilePlus2, Plus, RotateCcw } from "lucide-react";
import { scienceApi } from "@/lib/api";
import type { ResearchDataset } from "@/lib/types";
import { Button, ErrorBox, Loading, State } from "@/components/ui";

type Mode = "study" | "program";

export function ProjectView({ projectId }: { projectId: string }) {
  const router = useRouter();
  const client = useQueryClient();
  const project = useQuery({ queryKey: ["research-project", projectId], queryFn: () => scienceApi.project(projectId) });
  const datasets = useQuery({ queryKey: ["research-datasets"], queryFn: scienceApi.researchDatasets });
  const [mode, setMode] = useState<Mode | null>(null);
  const [editing, setEditing] = useState(false);
  const [editTitle, setEditTitle] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editObjectives, setEditObjectives] = useState("");
  const [editDatasets, setEditDatasets] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const datasetOptions = useMemo(() => datasets.data ?? [], [datasets.data]);
  const [form, setForm] = useState({
    title: "",
    research_question: "",
    dataset_snapshot_id: "",
    primary_metric_id: "",
    population: "",
    hypothesis: "",
    design: "OBSERVATIONAL_LONGITUDINAL",
    start_week: 5,
    weeks: 12,
    frequency: "weekly",
    missing_policy: "Missing scheduled measurements remain missing and are never imputed.",
  });
  const activeDataset = useMemo<ResearchDataset | undefined>(() => datasetOptions.find((item) => item.id === form.dataset_snapshot_id), [datasetOptions, form.dataset_snapshot_id]);
  useEffect(() => {
    if (activeDataset && !activeDataset.metrics.some((metric) => metric.id === form.primary_metric_id)) {
      setForm((current) => ({ ...current, primary_metric_id: activeDataset.metrics[0]?.id ?? "" }));
    }
    if (activeDataset) {
      const design = activeDataset.metrics[0]?.table === "signal_trials" ? "MEASUREMENT_REPEATED_TRIALS" : "OBSERVATIONAL_LONGITUDINAL";
      setForm((current) => ({ ...current, design }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeDataset?.id]);
  const createStudy = useMutation({
    mutationFn: () => scienceApi.createStudy(projectId, {
      title: form.title,
      research_question: form.research_question,
      dataset_snapshot_id: form.dataset_snapshot_id,
      primary_metric_id: form.primary_metric_id,
      population: form.population,
      design: form.design,
      hypotheses: form.hypothesis ? [{ statement: form.hypothesis, status: "PRIMARY", direction: "change" }] : undefined,
    }),
    onSuccess: (created) => { setError(null); void client.invalidateQueries({ queryKey: ["studies"] }); router.push(`/research/studies/${created.study.id}`); },
    onError: (err) => setError(err instanceof Error ? err.message : String(err)),
  });
  const createProgram = useMutation({
    mutationFn: () => scienceApi.createProgram(projectId, {
      title: form.title,
      research_question: form.research_question,
      dataset_snapshot_id: form.dataset_snapshot_id,
      primary_metric_id: form.primary_metric_id,
      population: form.population,
      start_week: form.start_week,
      weeks: form.weeks,
      frequency: form.frequency,
      missing_policy: form.missing_policy,
    }),
    onSuccess: (created) => { setError(null); void client.invalidateQueries({ queryKey: ["studies"] }); router.push(`/research/studies/${created.study.id}`); },
    onError: (err) => setError(err instanceof Error ? err.message : String(err)),
  });
  if (project.isLoading) return <main className="page"><div className="page-inner"><Loading label="Opening research project" /></div></main>;
  if (project.error || !project.data) return <main className="page"><div className="page-inner"><ErrorBox error={project.error ?? "Project not found"} onRetry={() => void project.refetch()} /></div></main>;
  const data = project.data;
  const studies = data.studies ?? [];
  const programs = data.monitoring_programs ?? [];
  const associated = data.datasets?.length ? data.datasets : datasetOptions.filter((dataset) => (data.dataset_snapshot_ids ?? []).includes(dataset.id));
  const submit = () => {
    if (!form.title.trim() || !form.dataset_snapshot_id || !form.primary_metric_id || !form.research_question.trim()) {
      setError("Title, research question, dataset and primary metric are required.");
      return;
    }
    if (mode === "program") createProgram.mutate(); else createStudy.mutate();
  };
  return (
    <main className="page">
      <div className="page-inner">
        <div className="page-head">
          <div>
            <div className="crumb"><Link href="/research" style={{ color: "inherit" }}>RESEARCH</Link> / PROJECT</div>
            <h1>{data.title}</h1>
            <p>{data.description || "No description."}</p>
          </div>
          <div className="block-toolbar" style={{ margin: 0 }}>
            <State>{data.status}</State><State>{`v${data.version}`}</State>
            <Button variant="ghost" onClick={() => { setEditing((value) => !value); setEditTitle(data.title); setEditDescription(data.description); setEditObjectives(data.objectives.join("\n")); setEditDatasets(data.dataset_snapshot_ids); }}>Edit</Button>
            {data.status === "ARCHIVED" ? <Button onClick={() => scienceApi.restoreProject(projectId).then(() => client.invalidateQueries({ queryKey: ["research-project", projectId] }))}><RotateCcw size={12} />Restore</Button> : <Button variant="ghost" onClick={() => scienceApi.archiveProject(projectId).then(() => client.invalidateQueries({ queryKey: ["research-project", projectId] }))}><Archive size={12} />Archive</Button>}
          </div>
        </div>

        {editing && (
          <div className="frame" style={{ marginBottom: 14 }}>
            <div className="frame-head"><strong>Edit project</strong><span className="faint small">Optimistic version check; historical versions remain.</span></div>
            <div className="frame-body" style={{ display: "grid", gap: 10, padding: 12 }}>
              <label className="field" style={{ display: "grid" }}><span>Title</span><input className="input" value={editTitle} onChange={(event) => setEditTitle(event.target.value)} /></label>
              <label className="field" style={{ display: "grid" }}><span>Description</span><textarea className="input" rows={2} value={editDescription} onChange={(event) => setEditDescription(event.target.value)} /></label>
              <label className="field" style={{ display: "grid" }}><span>Objectives (one per line)</span><textarea className="input" rows={3} value={editObjectives} onChange={(event) => setEditObjectives(event.target.value)} /></label>
              <div>
                <div className="upper faint" style={{ marginBottom: 4 }}>Associated admitted datasets</div>
                <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                  {datasetOptions.map((dataset) => (
                    <label key={dataset.id} className="field" style={{ display: "flex", gap: 6, alignItems: "center" }}>
                      <input type="checkbox" checked={editDatasets.includes(dataset.id)} onChange={(event) => setEditDatasets((current) => event.target.checked ? [...current, dataset.id] : current.filter((id) => id !== dataset.id))} />
                      <span>{dataset.label} <span className="mono faint">{dataset.id}</span></span>
                    </label>
                  ))}
                </div>
              </div>
              {error && <ErrorBox error={error} />}
              <div className="block-toolbar">
                <Button variant="primary" onClick={() => scienceApi.updateProject(projectId, { title: editTitle, description: editDescription, objectives: editObjectives.split("\n").map((item) => item.trim()).filter(Boolean), dataset_snapshot_ids: editDatasets, base_version: data.version }).then(() => { setEditing(false); void client.invalidateQueries({ queryKey: ["research-project", projectId] }); }).catch((err) => setError(err instanceof Error ? err.message : String(err)))}>Save project</Button>
                <Button onClick={() => setEditing(false)}>Cancel</Button>
              </div>
            </div>
          </div>
        )}

        <div className="grid-2">
          <div className="frame">
            <div className="frame-head"><strong>Scientific objectives</strong></div>
            <div className="frame-body">
              {data.objectives.length === 0 ? <span className="faint">No objectives recorded.</span> : <ul>{data.objectives.map((item) => <li key={item}>{item}</li>)}</ul>}
            </div>
          </div>
          <div className="frame">
            <div className="frame-head"><strong>Associated datasets</strong><span className="faint small">{associated.length}</span></div>
            <div className="frame-body" style={{ display: "grid", gap: 8 }}>
              {associated.length === 0 && <span className="faint">No datasets associated yet. Bind one when creating a study.</span>}
              {associated.map((dataset) => (
                <div key={dataset.id} className="note">
                  <Database size={12} />
                  <span><span className="mono">{dataset.id}</span> · {dataset.label} · {dataset.real_data ? "REAL DATA" : "SYNTHETIC"} · {dataset.metrics.length} registered metrics</span>
                  <Link href={`/data/${dataset.id}`} className="cite" style={{ marginLeft: "auto" }}>Data</Link>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="block-toolbar" style={{ marginTop: 18 }}>
          <Button variant="primary" onClick={() => setMode(mode === "study" ? null : "study")}><FilePlus2 size={13} />New study</Button>
          <Button onClick={() => setMode(mode === "program" ? null : "program")}><Plus size={13} />New monitoring program</Button>
          <span className="faint small">Both are authored from this blank project through the same workbench.</span>
        </div>

        {mode && (
          <div className="frame" style={{ marginTop: 10 }}>
            <div className="frame-head"><strong>{mode === "study" ? "New scientist-authored study" : "New monitoring program"}</strong><span className="faint small">{mode === "program" ? "schedule is prospective; readings remain separate" : "observational methods only; no invented arms"}</span></div>
            <div className="frame-body" style={{ display: "grid", gap: 10, padding: 12 }}>
              <div className="split">
                <label className="field" style={{ display: "grid" }}><span>Title</span><input className="input" aria-label={mode === "program" ? "Program title" : "Study title"} value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} /></label>
                <label className="field" style={{ display: "grid" }}><span>Dataset snapshot</span>
                  <select className="select" aria-label="Dataset snapshot" value={form.dataset_snapshot_id} onChange={(event) => setForm({ ...form, dataset_snapshot_id: event.target.value })}>
                    <option value="">— choose an admitted snapshot —</option>
                    {datasetOptions.map((dataset) => <option key={dataset.id} value={dataset.id}>{dataset.label} · {dataset.id} · {dataset.real_data ? "REAL" : "SYNTHETIC"}</option>)}
                  </select>
                </label>
              </div>
              <label className="field" style={{ display: "grid" }}><span>Research question</span><textarea className="input" aria-label="Research question" rows={2} value={form.research_question} onChange={(event) => setForm({ ...form, research_question: event.target.value })} /></label>
              <div className="split">
                <label className="field" style={{ display: "grid" }}><span>Primary metric</span>
                  <select className="select" aria-label="Primary metric" value={form.primary_metric_id} onChange={(event) => setForm({ ...form, primary_metric_id: event.target.value })}>
                    <option value="">— choose a metric —</option>
                    {(activeDataset?.metrics ?? []).map((metric) => <option key={metric.id} value={metric.id}>{metric.label} ({metric.unit}) · {metric.table}</option>)}
                  </select>
                </label>
                <label className="field" style={{ display: "grid" }}><span>Population</span><input className="input" aria-label="Population" value={form.population} onChange={(event) => setForm({ ...form, population: event.target.value })} placeholder="e.g. Adult participants in the admitted snapshot" /></label>
              </div>
              {mode === "study" ? (
                <>
                  <div className="split">
                    <label className="field" style={{ display: "grid" }}><span>Design</span>
                      <select className="select" aria-label="Study design" value={form.design} onChange={(event) => setForm({ ...form, design: event.target.value })}>
                        <option value="OBSERVATIONAL_LONGITUDINAL">Observational longitudinal repeated measures</option>
                        <option value="REPEATED_MEASURES">Repeated-measures measurement study</option>
                        <option value="MEASUREMENT_REPEATED_TRIALS">Repeated-trial measurement study</option>
                        <option value="DESCRIPTIVE">Descriptive study</option>
                      </select>
                    </label>
                    <label className="field" style={{ display: "grid" }}><span>Primary hypothesis (optional)</span><input className="input" aria-label="Primary hypothesis" value={form.hypothesis} onChange={(event) => setForm({ ...form, hypothesis: event.target.value })} /></label>
                  </div>
                  <div className="note"><span>Only designs supported by the qualified runtime are offered. A single-arm observational study is never labelled as a controlled intervention.</span></div>
                </>
              ) : (
                <div className="split">
                  <label className="field" style={{ display: "grid" }}><span>Schedule start week</span><input className="input" aria-label="Schedule start week" type="number" min={1} value={form.start_week} onChange={(event) => setForm({ ...form, start_week: Number(event.target.value) })} /></label>
                  <label className="field" style={{ display: "grid" }}><span>Planned weeks</span><input className="input" aria-label="Planned weeks" type="number" min={1} max={104} value={form.weeks} onChange={(event) => setForm({ ...form, weeks: Number(event.target.value) })} /></label>
                  <label className="field" style={{ display: "grid" }}><span>Frequency</span><input className="input" aria-label="Frequency" value={form.frequency} onChange={(event) => setForm({ ...form, frequency: event.target.value })} /></label>
                </div>
              )}
              {error && <ErrorBox error={error} />}
              <div className="block-toolbar">
                <Button variant="primary" onClick={submit} disabled={createStudy.isPending || createProgram.isPending}>{createStudy.isPending || createProgram.isPending ? "Creating…" : mode === "study" ? "Create study" : "Create monitoring program"}</Button>
                <Button onClick={() => setMode(null)}>Cancel</Button>
                <span className="faint small">The study and its first investigation are persisted immediately; cancel does not create anything.</span>
              </div>
            </div>
          </div>
        )}

        <div className="section-title"><h2>Studies</h2><span>{studies.length}</span></div>
        <div className="frame">
          {studies.length === 0 && <div className="frame-body empty">No studies in this project yet.</div>}
          {studies.map((study) => (
            <Link key={study.id} href={`/research/studies/${study.id}`} className="study-row">
              <div><div className="mono faint">{study.id}</div><State>{study.state}</State></div>
              <div><strong>{study.title}</strong><div className="q">{study.research_question}</div></div>
              <div className="meta"><div className="mono" title={study.dataset_snapshot_id}>{study.dataset_snapshot_id.length > 20 ? `${study.dataset_snapshot_id.slice(0, 18)}…` : study.dataset_snapshot_id}</div><div>{study.participant_count} participants</div></div>
              <div className="meta"><div>{study.run_count} run{study.run_count === 1 ? "" : "s"} · {study.evidence_count} evidence</div><div>Plan <State plain>{study.plan_status}</State></div></div>
              <div className="study-open">Open <ArrowRight size={14} /></div>
            </Link>
          ))}
        </div>

        <div className="section-title"><h2>Monitoring programs</h2><span>{programs.length}</span></div>
        <div className="frame">
          {programs.length === 0 && <div className="frame-body empty">No monitoring programs in this project yet.</div>}
          {programs.map((program) => (
            <Link key={program.id} href={`/research/studies/${program.id}`} className="study-row">
              <div><div className="mono faint">{program.id}</div><State>MONITORING</State></div>
              <div><strong>{program.title}</strong><div className="q">{program.research_question}</div></div>
              <div className="meta"><div className="mono" title={program.dataset_snapshot_id}>{program.dataset_snapshot_id.length > 20 ? `${program.dataset_snapshot_id.slice(0, 18)}…` : program.dataset_snapshot_id}</div><div>{program.participant_count} monitored</div></div>
              <div className="meta"><div>Plan <State plain>{program.plan_status}</State></div><div>{program.run_count} run{program.run_count === 1 ? "" : "s"}</div></div>
              <div className="study-open">Open <ArrowRight size={14} /></div>
            </Link>
          ))}
        </div>

        <div style={{ marginTop: 16 }}><Link href="/research" className="btn btn-ghost btn-sm" style={{ textDecoration: "none" }}><ArrowLeft size={12} />All research</Link></div>
      </div>
    </main>
  );
}





