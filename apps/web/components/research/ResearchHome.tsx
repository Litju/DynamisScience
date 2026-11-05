"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, FolderPlus, Plus } from "lucide-react";
import { scienceApi } from "@/lib/api";
import { Button, ErrorBox, Loading, State } from "@/components/ui";

export function ResearchHome() {
  const studies = useQuery({ queryKey: ["studies"], queryFn: scienceApi.studies });
  const projects = useQuery({ queryKey: ["research-projects"], queryFn: () => scienceApi.projects(true) });
  const datasets = useQuery({ queryKey: ["research-datasets"], queryFn: scienceApi.researchDatasets });
  const client = useQueryClient();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [objectives, setObjectives] = useState("");
  const [selectedDatasets, setSelectedDatasets] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const create = useMutation({
    mutationFn: () => scienceApi.createProject({
      title,
      description,
      objectives: objectives.split("\n").map((item) => item.trim()).filter(Boolean),
      dataset_snapshot_ids: selectedDatasets,
    }),
    onSuccess: (created) => {
      setTitle("");
      setDescription("");
      setObjectives("");
      setSelectedDatasets([]);
      setOpen(false);
      setError(null);
      void client.invalidateQueries({ queryKey: ["research-projects"] });
      void client.invalidateQueries({ queryKey: ["studies"] });
      router.push(`/research/projects/${created.id}`);
    },
    onError: (err) => setError(err instanceof Error ? err.message : String(err)),
  });
  const activeProjects = projects.data?.filter((project) => project.status !== "ARCHIVED") ?? [];
  const programs = (studies.data ?? []).filter((study) => study.kind === "MONITORING");
  const regular = (studies.data ?? []).filter((study) => study.kind !== "MONITORING");

  return (
    <main className="page">
      <div className="page-inner">
        <div className="page-head">
          <div>
            <div className="crumb">RESEARCH</div>
            <h1>Research</h1>
            <p>Projects contain studies, monitoring programs and investigations. Every research object is persisted locally and keeps its scientific history.</p>
          </div>
          <Button variant="primary" onClick={() => setOpen((value) => !value)} aria-expanded={open}><FolderPlus size={13} />New research project</Button>
        </div>

        {open && (
          <div className="frame" style={{ marginBottom: 18 }}>
            <div className="frame-head"><strong>New research project</strong><span className="faint small">A DynamisScience project is not a Linear project.</span></div>
            <div className="frame-body" style={{ display: "grid", gap: 10, padding: 12 }}>
              <label className="field" style={{ display: "grid" }}><span>Title</span><input className="input" aria-label="Project title" value={title} onChange={(event) => setTitle(event.target.value)} placeholder="e.g. Countermovement jump response study" /></label>
              <label className="field" style={{ display: "grid" }}><span>Description</span><textarea className="input" aria-label="Project description" rows={2} value={description} onChange={(event) => setDescription(event.target.value)} placeholder="What is this research programme about?" /></label>
              <label className="field" style={{ display: "grid" }}><span>Scientific objectives (one per line)</span><textarea className="input" aria-label="Scientific objectives" rows={3} value={objectives} onChange={(event) => setObjectives(event.target.value)} /></label>
              <div>
                <div className="upper faint" style={{ marginBottom: 4 }}>Associated admitted datasets</div>
                <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                  {(datasets.data ?? []).map((dataset) => (
                    <label key={dataset.id} className="field" style={{ display: "flex", gap: 6, alignItems: "center" }}>
                      <input
                        type="checkbox"
                        checked={selectedDatasets.includes(dataset.id)}
                        onChange={(event) => setSelectedDatasets((current) => event.target.checked ? [...current, dataset.id] : current.filter((id) => id !== dataset.id))}
                      />
                      <span>{dataset.label} <span className="mono faint">{dataset.id}</span> · {dataset.real_data ? "REAL" : "SYNTHETIC"}</span>
                    </label>
                  ))}
                </div>
              </div>
              {error && <ErrorBox error={error} />}
              <div className="block-toolbar">
                <Button variant="primary" disabled={!title.trim() || create.isPending} onClick={() => create.mutate()}><Plus size={12} />{create.isPending ? "Creating…" : "Create project"}</Button>
                <Button onClick={() => setOpen(false)}>Cancel</Button>
                <span className="faint small">Datasets are optional at project level; each study binds exactly one immutable snapshot.</span>
              </div>
            </div>
          </div>
        )}

        <div className="section-title"><h2>Research projects</h2><span>{activeProjects.length} project{activeProjects.length === 1 ? "" : "s"}</span></div>
        <div className="frame">
          {projects.isLoading && <div className="frame-body"><Loading label="Reading local research projects" /></div>}
          {projects.error && <div className="frame-body"><ErrorBox error={projects.error} onRetry={() => void projects.refetch()} /></div>}
          {projects.data && activeProjects.length === 0 && <div className="frame-body empty">No projects yet. Create one to author a study or monitoring program from a blank workspace.</div>}
          {activeProjects.map((project) => (
            <Link key={project.id} href={`/research/projects/${project.id}`} className="study-row">
              <div>
                <div className="mono faint">{project.id}</div>
                <div style={{ marginTop: 4, display: "flex", gap: 4, flexWrap: "wrap" }}><State>{project.status}</State><State>{`v${project.version}`}</State></div>
              </div>
              <div style={{ minWidth: 0 }}>
                <strong>{project.title}</strong>
                <div className="q">{project.description || "No description."}</div>
              </div>
              <div className="meta">
                <div>{project.study_count ?? 0} {project.study_count === 1 ? "study" : "studies"}</div>
                <div>{project.program_count ?? 0} monitoring program{project.program_count === 1 ? "" : "s"}</div>
              </div>
              <div className="meta">
                <div>{(project.dataset_snapshot_ids ?? []).length} dataset{(project.dataset_snapshot_ids ?? []).length === 1 ? "" : "s"}</div>
                <div className="mono">{project.updated_at ? new Date(project.updated_at).toLocaleDateString() : "—"}</div>
              </div>
              <div className="study-open">Open project <ArrowRight size={14} /></div>
            </Link>
          ))}
        </div>

        <div className="section-title"><h2>Studies</h2><span>{regular.length} research object{regular.length === 1 ? "" : "s"}</span></div>
        <div className="frame">
          {studies.isLoading && <div className="frame-body"><Loading label="Reading local study registry" /></div>}
          {studies.error && <div className="frame-body"><ErrorBox error={studies.error} onRetry={() => void studies.refetch()} /></div>}
          {regular.map((study) => (
            <Link key={study.id} href={`/research/studies/${study.id}`} className="study-row">
              <div>
                <div className="mono faint">{study.id}</div>
                <div style={{ marginTop: 4, display: "flex", gap: 4, flexWrap: "wrap" }}><State>{study.state}</State><State>{study.real_data ? "REAL DATA" : "SYNTHETIC"}</State>{study.kind === "STUDY" && <State>STUDY</State>}</div>
              </div>
              <div style={{ minWidth: 0 }}>
                <strong>{study.title}</strong>
                <div className="q">{study.research_question}</div>
              </div>
              <div className="meta">
                <div className="mono">{study.dataset_snapshot_id}</div>
                <div>{study.participant_count} participants · occasions {study.start_week}–{study.end_week}</div>
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

        <div className="section-title"><h2>Monitoring programs</h2><span>{programs.length} program{programs.length === 1 ? "" : "s"}</span></div>
        <div className="frame">
          {programs.length === 0 && <div className="frame-body entry-types"><span><b>Monitoring programs</b> — create one inside a research project. The schedule is stored separately from recorded observations.</span></div>}
          {programs.map((program) => (
            <Link key={program.id} href={`/research/studies/${program.id}`} className="study-row">
              <div><div className="mono faint">{program.id}</div><div style={{ marginTop: 4 }}><State>MONITORING</State> <State>{program.state}</State></div></div>
              <div style={{ minWidth: 0 }}><strong>{program.title}</strong><div className="q">{program.research_question}</div></div>
              <div className="meta"><div className="mono">{program.dataset_snapshot_id}</div><div>{program.participant_count} monitored participants</div></div>
              <div className="meta"><div>Plan <State plain>{program.plan_status}</State></div><div className="num">{program.run_count} runs · {program.evidence_count} evidence</div></div>
              <div className="study-open">Open program <ArrowRight size={14} /></div>
            </Link>
          ))}
        </div>
      </div>
    </main>
  );
}



