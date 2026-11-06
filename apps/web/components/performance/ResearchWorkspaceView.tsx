"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FolderPlus, Plus } from "lucide-react";
import { scienceApi } from "@/lib/api";
import { displayUnit, fmt } from "@/lib/performance/format";
import type { Evidence } from "@/lib/types";
import { Sparkline } from "./charts";
import { Drawer, PosChip, PosEmpty, PosError, PosLoading, Toast, toneForStatus } from "./ui";

type Tab = "projects" | "evidence" | "model";

export function ResearchWorkspaceView() {
  const client = useQueryClient();
  const router = useRouter();
  const projects = useQuery({ queryKey: ["research-projects"], queryFn: () => scienceApi.projects(true) });
  const studies = useQuery({ queryKey: ["studies"], queryFn: scienceApi.studies });
  const evidence = useQuery({ queryKey: ["evidence"], queryFn: () => scienceApi.evidence() });
  const datasets = useQuery({ queryKey: ["research-datasets"], queryFn: scienceApi.researchDatasets });
  const model = useQuery({ queryKey: ["training-model"], queryFn: scienceApi.trainingModel, enabled: false });
  const [tab, setTab] = useState<Tab>("projects");
  const [createOpen, setCreateOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [objectives, setObjectives] = useState("");
  const [selectedDatasets, setSelectedDatasets] = useState<string[]>([]);
  const [toast, setToast] = useState<string | null>(null);
  const [scenarioLoads, setScenarioLoads] = useState<number[]>([270, 280, 260, 250]);

  const create = useMutation({
    mutationFn: () => scienceApi.createProject({
      title,
      description,
      objectives: objectives.split("\n").map((value) => value.trim()).filter(Boolean),
      dataset_snapshot_ids: selectedDatasets,
    }),
    onSuccess: (project) => {
      void client.invalidateQueries({ queryKey: ["research-projects"] });
      setCreateOpen(false);
      setTitle(""); setDescription(""); setObjectives(""); setSelectedDatasets([]);
      router.push(`/research/projects/${project.id}`);
    },
  });

  const scenario = useMutation({
    mutationFn: () => scienceApi.scenario(scenarioLoads),
    onSuccess: (result) => {
      void client.invalidateQueries({ queryKey: ["training-scenario"] });
      setToast(`Scenario computed · ${result.states.filter((state) => state.segment === "SCENARIO").length} future weeks · persisted ${result.persisted ? "yes" : "no"}.`);
      window.setTimeout(() => setToast(null), 4200);
    },
  });

  const studyList = studies.data ?? [];
  const evidenceList = useMemo(() => evidence.data ?? [], [evidence.data]);
  const syntheticDatasets = (datasets.data ?? []).filter((dataset) => !dataset.real_data);
  const realDatasets = (datasets.data ?? []).filter((dataset) => dataset.real_data);
  const confirmatory = useMemo(() => evidenceList.filter((item) => item.evidence_class === "CONFIRMATORY" || item.quality === "VALID").slice(0, 6), [evidenceList]);
  const primary = confirmatory[0];
  const totalProjects = (projects.data ?? []).filter((project) => project.status !== "ARCHIVED").length;

  if (projects.isLoading || studies.isLoading) {
    return <div className="pos-page"><div className="pos-main"><PosLoading label="Reading the local research store" /></div></div>;
  }
  if (projects.error || studies.error) {
    return <div className="pos-page"><div className="pos-main"><PosError error={projects.error ?? studies.error} onRetry={() => { void projects.refetch(); void studies.refetch(); }} /></div></div>;
  }

  return (
    <div className="pos-page">
      <main className="pos-main" aria-label="Research">
        <div className="pos-main-head">
          <div>
            <div className="pos-kicker">Evidence loop · question → cohort → plan → run → evidence → report</div>
            <h1>Research</h1>
            <p>Research is a first-class workspace inside the Performance OS. Every study binds one immutable snapshot; real data stays separate from the synthetic squad.</p>
          </div>
          <div className="pos-actions">
            <button type="button" className="pos-btn primary" onClick={() => setCreateOpen(true)}><FolderPlus size={10} />New project</button>
          </div>
        </div>

        <div className="pos-tabs" role="tablist" aria-label="Research sections">
          <button type="button" role="tab" aria-selected={tab === "projects"} className={`pos-tab ${tab === "projects" ? "is-active" : ""}`} onClick={() => setTab("projects")}>Projects &amp; studies</button>
          <button type="button" role="tab" aria-selected={tab === "evidence"} className={`pos-tab ${tab === "evidence" ? "is-active" : ""}`} onClick={() => setTab("evidence")}>Evidence ledger</button>
          <button type="button" role="tab" aria-selected={tab === "model"} className={`pos-tab ${tab === "model" ? "is-active" : ""}`} onClick={() => { setTab("model"); if (!model.data) void model.refetch(); }}>Model lab</button>
        </div>

        {tab === "projects" ? (
          <>
            <div className="pos-grid-3">
              <div className="pos-card"><div className="pos-k">Active projects</div><div className="pos-metric-value">{totalProjects}</div><div className="pos-note">{(projects.data ?? []).filter((project) => project.status === "ARCHIVED").length} archived</div></div>
              <div className="pos-card"><div className="pos-k">Studies</div><div className="pos-metric-value">{studyList.filter((study) => study.kind !== "MONITORING").length}</div><div className="pos-note">{studyList.filter((study) => study.kind === "MONITORING").length} monitoring programs</div></div>
              <div className="pos-card"><div className="pos-k">Evidence</div><div className="pos-metric-value">{evidenceList.length}</div><div className="pos-note">{confirmatory.length} confirmatory or valid</div></div>
            </div>

            <div className="pos-section-title"><h2>Research projects</h2><span>synthetic and admitted real data remain separate</span></div>
            <div className="pos-project-grid">
              {(projects.data ?? []).filter((project) => project.status !== "ARCHIVED").map((project) => (
                <Link key={project.id} href={`/research/projects/${project.id}`} className="pos-project">
                  <div className="pos-k">{project.id} · v{project.version} · {project.status}</div>
                  <b>{project.title}</b>
                  <p>{project.description || "No description."}</p>
                  <div className="meta"><span>{project.study_count ?? 0} studies</span><span>{project.program_count ?? 0} programs</span><span>{project.dataset_snapshot_ids.length} datasets</span></div>
                </Link>
              ))}
              {(projects.data ?? []).filter((project) => project.status !== "ARCHIVED").length === 0 ? <PosEmpty title="No research project">Create a project to author a study or monitoring program.</PosEmpty> : null}
            </div>

            <div className="pos-section-title"><h2>Studies and monitoring programs</h2><span>each binds one snapshot</span></div>
            <div className="pos-module">
              <div className="pos-module-body flush">
                <table className="pos-table">
                  <thead><tr><th>ID</th><th>Kind</th><th>Title</th><th>State</th><th>Data</th><th className="r">Participants</th><th className="r">Runs</th><th className="r">Evidence</th><th /></tr></thead>
                  <tbody>{studyList.map((study) => (
                    <tr key={study.id}>
                      <td className="mono">{study.id}</td>
                      <td>{study.kind === "MONITORING" ? <PosChip tone="info">MONITORING</PosChip> : <PosChip tone="neutral">STUDY</PosChip>}</td>
                      <td><Link href={`/research/studies/${study.id}`} className="pos-link">{study.title}</Link><div className="pos-faint" style={{ fontSize: 6.5 }}>{study.research_question}</div></td>
                      <td><PosChip tone={toneForStatus(study.state)}>{study.state}</PosChip></td>
                      <td><PosChip tone={study.real_data ? "info" : "warn"}>{study.real_data ? "REAL" : "SYNTHETIC"}</PosChip></td>
                      <td className="r">{study.participant_count}</td>
                      <td className="r">{study.run_count}</td>
                      <td className="r">{study.evidence_count}</td>
                      <td><Link href={`/research/studies/${study.id}`} className="pos-link">Workbench →</Link></td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
            </div>

            <div className="pos-section-title"><h2>Data admission</h2><span>one source per snapshot · no mixing</span><span className="right"><Link href="/data/admission" className="pos-link">Open admission →</Link></span></div>
            <div className="pos-grid-2">
              <div className="pos-card">
                <div className="pos-k">Admitted datasets</div>
                <div style={{ display: "grid", gap: 5, marginTop: 5 }}>
                  {syntheticDatasets.map((dataset) => <div key={dataset.id}><PosChip tone="warn">SYNTHETIC</PosChip> <span className="pos-mono" style={{ fontSize: 8 }}>{dataset.id}</span> · {dataset.label}</div>)}
                  {realDatasets.slice(0, 4).map((dataset) => <div key={dataset.id}><PosChip tone="info">REAL</PosChip> <span className="pos-mono" style={{ fontSize: 8 }}>{dataset.id}</span> · {dataset.label}</div>)}
                </div>
              </div>
              <div className="pos-card">
                <div className="pos-k">Separation rule</div>
                <p>The synthetic squad dashboard never consumes real-data studies. Real datasets are research-only and must be admitted with rights, privacy and qualification records before analysis.</p>
                <div style={{ marginTop: 6 }}><Link href="/library" className="pos-link">Metric &amp; method registry →</Link></div>
              </div>
            </div>
          </>
        ) : null}

        {tab === "evidence" ? (
          <>
            <div className="pos-grid-2" style={{ gridTemplateColumns: "1.45fr 1fr", alignItems: "start" }}>
              <section className="pos-module">
                <div className="pos-module-head"><h2>Evidence ledger</h2><span className="sub">{evidenceList.length} artifacts · intervals preserved</span><span className="right"><PosChip tone="ok">{confirmatory.length} current</PosChip></span></div>
                <div className="pos-module-body flush">
                  <table className="pos-table">
                    <thead><tr><th>ID</th><th>Title</th><th className="r">Estimate</th><th>Class</th><th>Quality</th></tr></thead>
                    <tbody>{evidenceList.slice(0, 18).map((item: Evidence) => (
                      <tr key={item.id}>
                        <td className="mono"><Link href={`/research/studies/${item.dataset_snapshot_id === "DS-SYNTH-001" ? "STUDY-001" : "STUDY-REAL-001"}?inspect=evidence:${item.id}`} className="pos-link">{item.id}</Link></td>
                        <td>{item.title}<div className="pos-faint" style={{ fontSize: 6.5 }}>{item.population} · n={item.sample_size}</div></td>
                        <td className="r">{fmt(item.estimate, 3)} <span className="pos-faint">{displayUnit(item.unit)}</span>{item.interval ? <div className="pos-faint" style={{ fontSize: 6.5 }}>CI {fmt(item.interval.low, 3)}–{fmt(item.interval.high, 3)}</div> : null}</td>
                        <td><PosChip tone={item.evidence_class === "CONFIRMATORY" ? "ok" : "warn"}>{item.evidence_class ?? "PLANNED"}</PosChip></td>
                        <td><PosChip tone={toneForStatus(item.quality)}>{item.quality}</PosChip></td>
                      </tr>
                    ))}</tbody>
                  </table>
                </div>
              </section>
              <div style={{ display: "grid", gap: 9 }}>
                <section className="pos-module">
                  <div className="pos-module-head"><h2>Decision brief</h2><span className="sub">evidence → decision</span></div>
                  <div className="pos-module-body">
                    {primary ? (
                      <>
                        <div className="pos-k">{primary.id} · {primary.evidence_class}</div>
                        <b style={{ display: "block", fontSize: 10, marginTop: 2 }}>{primary.title}</b>
                        <p className="pos-note" style={{ marginTop: 4 }}>{primary.interpretation}</p>
                        <div className="pos-hr" />
                        <div className="pos-note">This is cohort-level synthetic evidence. It does not make an individual diagnosis, injury prediction or causal claim.</div>
                      </>
                    ) : <PosEmpty title="No evidence promoted">A study must be run and its evidence promoted before a decision brief exists.</PosEmpty>}
                  </div>
                </section>
                <section className="pos-module">
                  <div className="pos-module-head"><h2>Limitations</h2><span className="sub">from the primary evidence</span></div>
                  <div className="pos-module-body">
                    {(primary?.diagnostics?.limitations as string[] | undefined)?.map((limit) => <div key={String(limit)} className="pos-note" style={{ marginBottom: 4 }}>— {String(limit)}</div>) ?? <div className="pos-note">No limitation record.</div>}
                  </div>
                </section>
                <section className="pos-module">
                  <div className="pos-module-head"><h2>Reports</h2><span className="sub">evidence → audience</span></div>
                  <div className="pos-module-body">
                    <div className="pos-note">The scientific report is separate from performance reports. Both retain provenance and do not rewrite frozen versions.</div>
                    <div style={{ marginTop: 6 }}><Link href="/research/studies/STUDY-001?mode=report" className="pos-link">Open scientific report →</Link><br /><Link href="/report" className="pos-link">Compose performance report →</Link></div>
                  </div>
                </section>
              </div>
            </div>
          </>
        ) : null}

        {tab === "model" ? (
          <div className="pos-grid-2" style={{ gridTemplateColumns: "1.4fr 1fr", alignItems: "start" }}>
            <section className="pos-module">
              <div className="pos-module-head"><h2>Training-response model</h2><span className="sub">prototype model · not a prediction product</span><span className="right"><PosChip tone="warn">PROTOTYPE</PosChip></span></div>
              <div className="pos-module-body">
                {model.isLoading ? <PosLoading label="Fitting the training-response model" /> : null}
                {model.error ? <PosError error={model.error} onRetry={() => void model.refetch()} /> : null}
                {model.data ? (
                  <>
                    <div className="pos-k">{model.data.spec.id} · v{model.data.spec.version} · {model.data.spec.kind}</div>
                    <p className="pos-note" style={{ marginTop: 4 }}>{model.data.spec.description}</p>
                    <div className="pos-grid-3" style={{ marginTop: 8 }}>
                      <div className="pos-card"><div className="pos-k">Fit RMSE</div><div className="pos-metric-value">{fmt(model.data.run.output.fit_rmse_outcome_units, 3)}<span className="u">{model.data.run.output.unit}</span></div><div className="pos-note">standardised {fmt(model.data.run.output.fit_rmse_standardized, 3)}</div></div>
                      <div className="pos-card"><div className="pos-k">Weeks fitted</div><div className="pos-metric-value">{model.data.run.output.observed_weeks.length}</div><div className="pos-note">{model.data.run.diagnostics.fit_status}</div></div>
                      <div className="pos-card"><div className="pos-k">Snapshot</div><div className="pos-metric-value" style={{ fontSize: 12 }}>{model.data.run.dataset_snapshot_id}</div><div className="pos-note">{model.data.run.diagnostics.model_class}</div></div>
                    </div>
                    <div className="pos-hr" />
                    <div className="pos-k">Observed vs modelled performance</div>
                    <div className="pos-grid-2" style={{ marginTop: 5 }}>
                      <div><div className="pos-note">observed</div><Sparkline values={model.data.run.output.observed_performance} width={300} height={44} color="#5fd4e8" /></div>
                      <div><div className="pos-note">modelled</div><Sparkline values={model.data.run.output.modelled_performance} width={300} height={44} color="#c8f36b" /></div>
                    </div>
                    <div className="pos-hr" />
                    <div className="pos-note">The model is a local prototype. It is not a validated prediction of injury, availability or individual performance, and its output is never shown as a fact.</div>
                  </>
                ) : null}
              </div>
            </section>
            <section className="pos-module">
              <div className="pos-module-head"><h2>Scenario lab</h2><span className="sub">hypothetical future load · model output</span></div>
              <div className="pos-module-body">
                <div className="pos-note">Future weeks are an explicit scenario input, not observed data.</div>
                <div style={{ display: "grid", gap: 6, marginTop: 8 }}>
                  {scenarioLoads.map((value, index) => (
                    <label key={index} className="pos-field">
                      <span>Scenario week {index + 1} load (AU)</span>
                      <input type="number" min={0} max={800} value={value} onChange={(event) => setScenarioLoads(scenarioLoads.map((item, i) => i === index ? Number(event.target.value) : item))} />
                    </label>
                  ))}
                </div>
                <button type="button" className="pos-btn primary" style={{ marginTop: 8 }} disabled={scenario.isPending} onClick={() => scenario.mutate()}><Plus size={10} />{scenario.isPending ? "Running…" : "Run scenario"}</button>
                {scenario.data ? (
                  <div className="pos-research-card" style={{ marginTop: 8 }}>
                    <div className="k">SCENARIO · {scenario.data.scenario_id}</div>
                    <p>End-of-history performance {fmt(scenario.data.summary.end_of_history_performance, 1)} {scenario.data.unit}; scenario peak {fmt(scenario.data.summary.scenario_peak_performance, 1)} at week {scenario.data.summary.scenario_peak_week ?? "—"}.</p>
                    <div className="pos-note">{(scenario.data.limitations ?? []).join(" ")}</div>
                  </div>
                ) : null}
                {scenario.error ? <PosError error={scenario.error} /> : null}
              </div>
            </section>
          </div>
        ) : null}
      </main>

      <aside className="pos-aside" aria-label="Research context">
        <div className="pos-aside-sec">
          <h3>Research contract</h3>
          <div className="pos-check"><span className="tick done">✓</span>One snapshot per study<span className="status done">BOUND</span></div>
          <div className="pos-check"><span className="tick done">✓</span>Frozen cohort and plan<span className="status done">FROZEN</span></div>
          <div className="pos-check"><span className="tick done">✓</span>Append-only runs<span className="status done">LOCAL</span></div>
          <div className="pos-check"><span className="tick done">✓</span>Evidence with intervals<span className="status done">{evidenceList.length}</span></div>
          <div className="pos-check"><span className="tick done">✓</span>Real vs synthetic separation<span className="status done">SEPARATE</span></div>
        </div>
        <div className="pos-aside-sec">
          <h3>Data reality</h3>
          <div className="pos-note">The squad workspaces use the synthetic 28-athlete fixture. The admitted Mendeley and MoveSmart datasets power separate real-data studies and are never merged into the squad dashboard.</div>
          <div className="pos-hr" />
          <dl className="pos-kv">
            <dt>Synthetic</dt><dd>{syntheticDatasets.length} datasets</dd>
            <dt>Real</dt><dd>{realDatasets.length} datasets</dd>
            <dt>Projects</dt><dd>{totalProjects}</dd>
            <dt>Studies</dt><dd>{studyList.length}</dd>
          </dl>
        </div>
        <div className="pos-aside-sec"><div className="pos-callout info"><b>No invented AI.</b> Bayesian hierarchical models and ML/PIML prediction are not implemented. They are not shown as available.</div></div>
        <div className="pos-aside-sec"><div className="pos-callout"><b>No causal claim.</b> Observational associations remain associations. The report states uncertainty and design limits.</div></div>
        <div className="pos-aside-foot">Research · local SQLite + artifacts<br />Evidence is immutable once promoted<br /><b>PROVENANCE FIRST</b></div>
      </aside>

      {createOpen ? (
        <Drawer title="New research project" subtitle="A project is not a Linear project" onClose={() => setCreateOpen(false)}>
          <div style={{ display: "grid", gap: 9 }}>
            <label className="pos-field"><span>Title</span><input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="e.g. Countermovement jump response study" /></label>
            <label className="pos-field"><span>Description</span><textarea value={description} onChange={(event) => setDescription(event.target.value)} /></label>
            <label className="pos-field"><span>Scientific objectives (one per line)</span><textarea value={objectives} onChange={(event) => setObjectives(event.target.value)} /></label>
            <div>
              <div className="pos-k" style={{ marginBottom: 4 }}>Associated admitted datasets</div>
              <div style={{ display: "grid", gap: 4 }}>
                {(datasets.data ?? []).map((dataset) => (
                  <label key={dataset.id} style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 8.5 }}>
                    <input type="checkbox" checked={selectedDatasets.includes(dataset.id)} onChange={(event) => setSelectedDatasets(event.target.checked ? [...selectedDatasets, dataset.id] : selectedDatasets.filter((id) => id !== dataset.id))} />
                    <span><b>{dataset.label}</b> <span className="pos-mono">{dataset.id}</span> · {dataset.real_data ? "REAL" : "SYNTHETIC"}</span>
                  </label>
                ))}
              </div>
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <button type="button" className="pos-btn primary" disabled={!title.trim() || create.isPending} onClick={() => create.mutate()}><Plus size={10} />{create.isPending ? "Creating…" : "Create project"}</button>
              <button type="button" className="pos-btn" onClick={() => setCreateOpen(false)}>Cancel</button>
            </div>
            {create.error ? <PosError error={create.error} /> : null}
            <div className="pos-note">Datasets are optional at project level; each study binds exactly one immutable snapshot.</div>
          </div>
        </Drawer>
      ) : null}
      <Toast message={toast} />
    </div>
  );
}
