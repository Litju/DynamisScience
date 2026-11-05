"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState, type CSSProperties, type PointerEvent as ReactPointerEvent } from "react";
import { ChevronRight, FileText, History, Layers, PanelLeft, PanelRight, Settings2, X } from "lucide-react";
import { ErrorBox, IconButton, Loading, State } from "@/components/ui";
import { useStudy, useSubjects } from "./data";
import { WorkbenchProvider, useWorkbench, type InspectTarget } from "./context";
import { StudyTree } from "./StudyTree";
import { Workbench } from "./Workbench";
import { Inspector } from "./Inspector";
import { ForceViewer } from "@/components/viewers/ForceViewer";
import { MatchViewer } from "@/components/viewers/MatchViewer";
import { LineageDrawer } from "@/components/viewers/LineageDrawer";
import { RunHistoryDrawer } from "@/components/viewers/RunHistoryDrawer";
import { ReportDocument } from "@/components/report/ReportDocument";
import { StudySetup } from "./StudySetup";

export function StudyWorkspace({ studyId }: { studyId: string }) {
  const study = useStudy(studyId);
  const params = useSearchParams();
  if (study.isLoading) return <main className="page"><div className="page-inner"><Loading label={`Opening ${studyId}`} /></div></main>;
  if (study.error || !study.data) return <main className="page"><div className="page-inner"><ErrorBox error={study.error ?? "Study not found"} onRetry={() => void study.refetch()} /></div></main>;
  const requested = params.get("investigation");
  const investigationId = study.data.investigations.find((item) => item.id === requested)?.id ?? study.data.investigations[0]?.id ?? "INV-001";
  return (
    <WorkbenchProvider study={study.data} investigationId={investigationId}>
      <WorkspaceFrame />
    </WorkbenchProvider>
  );
}

const MIN_TREE = 200;
const MAX_TREE = 380;
const MIN_INSP = 280;
const MAX_INSP = 560;

function useStoredWidth(key: string, initial: number): [number, (value: number) => void] {
  const [width, setWidth] = useState(initial);
  useEffect(() => {
    try {
      const stored = Number(window.localStorage.getItem(key));
      if (Number.isFinite(stored) && stored > 0) setWidth(stored);
    } catch {
      // Storage may be unavailable; the default width still works.
    }
  }, [key]);
  const update = useCallback((value: number) => {
    setWidth(value);
    try {
      window.localStorage.setItem(key, String(Math.round(value)));
    } catch {
      // Non-persistent convenience only.
    }
  }, [key]);
  return [width, update];
}

function parseInspect(value: string | null): InspectTarget | null {
  if (!value) return null;
  const [kind, id] = value.split(":");
  if (!id) return null;
  if (kind === "evidence" || kind === "run" || kind === "trial" || kind === "athlete" || kind === "metric" || kind === "figure") return { kind, id };
  return null;
}

function WorkspaceFrame() {
  const wb = useWorkbench();
  const params = useSearchParams();
  const router = useRouter();
  const [treeOpen, setTreeOpen] = useState(true);
  const [inspOpen, setInspOpen] = useState(true);
  const [treeWidth, setTreeWidth] = useStoredWidth("ds.tree.w", 256);
  const [inspWidth, setInspWidth] = useStoredWidth("ds.insp.w", 356);
  const [dragging, setDragging] = useState<"tree" | "insp" | null>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  const subjects = useSubjects(wb.study.study.id);

  // Deep links from the command palette and from other surfaces.
  const paramKey = params.toString();
  const { select, inspect, selectBlock, setMode, openViewer, blocks } = wb;
  useEffect(() => {
    const athlete = params.get("athlete");
    if (athlete) {
      select({ athleteId: athlete, trialId: null });
      const explore = blocks.find((block) => block.type === "explore");
      if (explore) selectBlock(explore.id, { scroll: true, inspect: false });
      inspect({ kind: "athlete", id: athlete });
      setMode("investigation");
    }
    const target = parseInspect(params.get("inspect"));
    if (target) {
      inspect(target);
      setInspOpen(true);
    }
    const block = params.get("block");
    if (block) {
      setMode("investigation");
      selectBlock(block, { scroll: true });
    }
    const mode = params.get("mode");
    if (mode === "report") setMode("report");
    if (mode === "setup") setMode("setup");
    const viewer = params.get("viewer");
    if (viewer?.startsWith("force:")) openViewer({ kind: "force", trialId: viewer.slice(6) });
    if (viewer?.startsWith("match:")) openViewer({ kind: "match", eventId: viewer.slice(6) || undefined });
    if (athlete || target || block || mode || viewer) router.replace(`/research/studies/${wb.studyId}`, { scroll: false });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [paramKey]);

  useEffect(() => {
    if (!dragging) return;
    const onMove = (event: PointerEvent) => {
      const rect = bodyRef.current?.getBoundingClientRect();
      if (!rect) return;
      if (dragging === "tree") setTreeWidth(Math.min(MAX_TREE, Math.max(MIN_TREE, event.clientX - rect.left)));
      else setInspWidth(Math.min(MAX_INSP, Math.max(MIN_INSP, rect.right - event.clientX)));
    };
    const onUp = () => setDragging(null);
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
  }, [dragging, setInspWidth, setTreeWidth]);

  // Narrow viewports: the side panes behave as drawers.
  useEffect(() => {
    const query = window.matchMedia("(max-width: 1024px)");
    const apply = () => {
      if (query.matches) {
        setTreeOpen(false);
        setInspOpen(false);
      }
    };
    apply();
    query.addEventListener("change", apply);
    return () => query.removeEventListener("change", apply);
  }, []);

  const startDrag = (pane: "tree" | "insp") => (event: ReactPointerEvent) => {
    event.preventDefault();
    setDragging(pane);
  };

  const athlete = subjects.data?.find((subject) => subject.subject_id === wb.selection.athleteId);
  const cohortBlock = wb.blocks.find((block) => block.type === "cohort");
  const analysisBlock = wb.blocks.find((block) => block.type === "analysis");
  const bodyStyle = { "--tree-w": `${treeWidth}px`, "--insp-w": `${inspWidth}px`, "--viewer-left": treeOpen ? `${treeWidth}px` : "0px" } as CSSProperties;
  const study = wb.study;

  return (
    <main className="study" aria-label={`Study workbench ${study.study.id}`}>
      <header className="sbar">
        <IconButton label={treeOpen ? "Collapse study tree" : "Show study tree"} onClick={() => setTreeOpen((open) => !open)} pressed={treeOpen}><PanelLeft size={15} /></IconButton>
        <nav className="sbar-id" aria-label="Breadcrumb"><Link href="/research" style={{ color: "inherit", textDecoration: "none" }}>Research</Link> <ChevronRight size={10} style={{ verticalAlign: "middle" }} /> {study.study.id}</nav>
        <div className="sbar-title">
          <strong>{study.study.title}</strong>
          <span>{study.real_data ? `Real data · ${String((study.source as { doi?: string } | undefined)?.doi ?? "")}` : study.question.statement}</span>
        </div>
        <div className="sbar-states">
          <State>{study.study.state}</State>
          <State title="Analysis plan status">{study.plan.status}</State>
          <State tone="tone-neutral">{study.real_data ? `${study.snapshot.id} · IMMUTABLE` : `${study.snapshot.id} · SEED ${study.snapshot.seed}`}</State>
          <State>{study.real_data ? "REAL DATA" : "SYNTHETIC"}</State>
        </div>
        <div className="sbar-actions">
          <div className="mode-switch" role="group" aria-label="Study mode">
            <button type="button" aria-pressed={wb.mode === "investigation"} onClick={() => wb.setMode("investigation")}><Layers size={13} />Investigation</button>
            <button type="button" aria-pressed={wb.mode === "setup"} onClick={() => wb.setMode("setup")}><Settings2 size={13} />Setup</button>
            <button type="button" aria-pressed={wb.mode === "report"} onClick={() => wb.setMode("report")}><FileText size={13} />Report</button>
          </div>
          <span className="sbar-sep" />
          <IconButton label="Run history (immutable ledger)" onClick={() => wb.setHistoryOpen(true)}><History size={15} /></IconButton>
          <IconButton label={inspOpen ? "Collapse inspector" : "Show inspector"} onClick={() => setInspOpen((open) => !open)} pressed={inspOpen}><PanelRight size={15} /></IconButton>
        </div>
      </header>

      <div className="ctx" aria-label="Linked scientific context">
        <span className="ctx-label">CONTEXT</span>
        <span className="ctx-item"><b>Study</b><span className="mono">{study.study.id}</span></span>
        <span className="ctx-arrow">›</span>
        <span className="ctx-item"><b>Snapshot</b><span className="mono">{study.snapshot.id}</span></span>
        <span className="ctx-arrow">›</span>
        <span className={`ctx-item ${wb.excludedSubjectIds.length ? "linked" : ""}`}>
          <b>Cohort</b>
          <span className="mono">{wb.excludedSubjectIds.length ? `DRAFT · ${study.cohort.subject_ids.length - wb.excludedSubjectIds.length}` : `${study.cohort.id} · ${study.cohort.subject_ids.length}`}</span>
          {cohortBlock && <button type="button" aria-label="Focus cohort block" onClick={() => wb.selectBlock(cohortBlock.id, { scroll: true })}><ChevronRight size={11} /></button>}
        </span>
        {analysisBlock?.state.run_id ? (
          <>
            <span className="ctx-arrow">›</span>
            <span className="ctx-item"><b>Run</b><span className="mono">{String(analysisBlock.state.run_id)}</span><button type="button" aria-label="Inspect run" onClick={() => wb.inspect({ kind: "run", id: String(analysisBlock.state.run_id) })}><ChevronRight size={11} /></button></span>
          </>
        ) : null}
        {wb.selection.athleteId && (
          <>
            <span className="ctx-arrow">·</span>
            <span className="ctx-item linked"><b>Athlete</b><span className="mono">{athlete?.display_id ?? wb.selection.athleteId}</span><button type="button" aria-label="Clear athlete selection" onClick={() => wb.select({ athleteId: null, trialId: null, week: null })}><X size={11} /></button></span>
          </>
        )}
        {wb.selection.week && (
          <span className="ctx-item linked"><b>Week</b><span className="mono">{wb.selection.week}</span><button type="button" aria-label="Clear week selection" onClick={() => wb.select({ week: null })}><X size={11} /></button></span>
        )}
        {wb.selection.trialId && (
          <span className="ctx-item linked"><b>Trial</b><span className="mono">{wb.selection.trialId}</span><button type="button" aria-label="Clear trial selection" onClick={() => wb.select({ trialId: null })}><X size={11} /></button></span>
        )}
        {wb.selection.matchEventId && (
          <span className="ctx-item linked"><b>Event</b><span className="mono">{wb.selection.matchEventId}</span><button type="button" aria-label="Clear event selection" onClick={() => wb.select({ matchEventId: null })}><X size={11} /></button></span>
        )}
        {wb.notice && <span style={{ marginLeft: "auto", color: "var(--signal)" }} role="status">{wb.notice}</span>}
      </div>

      <div ref={bodyRef} className={`study-body ${treeOpen ? "" : "no-tree"} ${inspOpen ? "" : "no-insp"}`} style={bodyStyle}>
        <div className={`pane pane-tree ${treeOpen ? "is-open" : ""}`}>{treeOpen && <StudyTree />}</div>
        <div className="pane pane-bench">{wb.mode === "report" ? <div className="bench"><ReportDocument /></div> : wb.mode === "setup" ? <StudySetup /> : <Workbench />}</div>
        <div className={`pane pane-insp ${inspOpen ? "is-open" : ""}`}>{inspOpen && <Inspector />}</div>
        {treeOpen && <div className={`resizer ${dragging === "tree" ? "dragging" : ""}`} style={{ left: treeWidth - 4 }} onPointerDown={startDrag("tree")} role="separator" aria-orientation="vertical" aria-label="Resize study tree" />}
        {inspOpen && <div className={`resizer ${dragging === "insp" ? "dragging" : ""}`} style={{ right: inspWidth - 4 }} onPointerDown={startDrag("insp")} role="separator" aria-orientation="vertical" aria-label="Resize inspector" />}
        {wb.viewer?.kind === "force" && <ForceViewer trialId={wb.viewer.trialId} />}
        {wb.viewer?.kind === "match" && <MatchViewer initialEventId={wb.viewer.eventId} initialAthleteId={wb.viewer.athleteId} />}
      </div>
      {wb.lineageFor && <LineageDrawer artifactId={wb.lineageFor} />}
      {wb.historyOpen && <RunHistoryDrawer />}
    </main>
  );
}
