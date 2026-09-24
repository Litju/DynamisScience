"use client";

import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { Activity, BarChart3, BookOpen, Box, ChevronDown, ChevronRight, Command, Database, FileText, FlaskConical, GitBranch, Hexagon, History, LayoutDashboard, LineChart, Menu, Network, PanelRight, Search, Settings2, ShieldCheck, Table2, Users, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { scienceApi } from "@/lib/api";
import type { Snapshot, ViewKey } from "@/lib/types";
import { OverviewView } from "@/components/overview";
import { StudyView } from "@/components/StudyView";
import { MonitorView } from "@/components/MonitorView";
import { ForceLabView } from "@/components/ForceLabView";
import { MatchLabView } from "@/components/activities";
import { AnalysisView } from "@/components/AnalysisView";
import { RegistryView, RunsView, LineageView, ModelLabView, ReportView } from "@/components/knowledge";
import { KeyValue, Panel, StatusBadge } from "@/components/ui";
import "./globals.css";

const queryClient = new QueryClient({ defaultOptions: { queries: { staleTime: 30_000, retry: 1, refetchOnWindowFocus: false } } });

const navGroups: { label: string; items: { id: ViewKey; label: string; icon: typeof LayoutDashboard; shortcut?: string }[] }[] = [
  { label: "Workspace", items: [{ id: "overview", label: "Overview", icon: LayoutDashboard, shortcut: "G O" }, { id: "studies", label: "Studies", icon: BookOpen }, { id: "monitor", label: "Monitor", icon: LineChart }] },
  { label: "Laboratories", items: [{ id: "forcelab", label: "ForceLab", icon: Activity, shortcut: "G F" }, { id: "matchlab", label: "MatchLab", icon: Box, shortcut: "G M" }] },
  { label: "Science", items: [{ id: "analyses", label: "Analyses", icon: Network, shortcut: "G A" }, { id: "models", label: "Models", icon: FlaskConical }, { id: "runs", label: "Runs", icon: History }] },
  { label: "Knowledge", items: [{ id: "registry", label: "Registry", icon: Table2 }, { id: "reports", label: "Reports", icon: BookOpen }, { id: "lineage", label: "Lineage", icon: GitBranch }] },
];

export default function HomePage() {
  return <QueryClientProvider client={queryClient}><DynamisShell /></QueryClientProvider>;
}

function DynamisShell() {
  const [view, setView] = useState<ViewKey>("overview");
  const [contextId, setContextId] = useState<string | undefined>();
  const [commandOpen, setCommandOpen] = useState(false);
  const [mobileNav, setMobileNav] = useState(false);
  const [inspectorOpen, setInspectorOpen] = useState(true);
  const overview = useQuery({ queryKey: ["overview", "shell"], queryFn: scienceApi.overview });

  useEffect(() => {
    const hash = window.location.hash.replace("#", "") as ViewKey;
    if (navGroups.some((group) => group.items.some((item) => item.id === hash))) setView(hash);
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setCommandOpen((open) => !open);
      }
      if (event.key === "Escape") setCommandOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const navigate = useCallback((next: string, id?: string) => {
    const nextView = next as ViewKey;
    if (!navGroups.some((group) => group.items.some((item) => item.id === nextView))) return;
    setView(nextView);
    setContextId(id);
    window.history.replaceState(null, "", `#${nextView}`);
    setCommandOpen(false);
    setMobileNav(false);
  }, []);

  const snapshot = overview.data?.snapshot;

  return (
    <div className="app-shell">
      <aside className={`left-nav ${mobileNav ? "mobile-open" : ""}`}>
        <div className="brand-lockup">
          <div className="brand-symbol"><span>∿</span></div>
          <div><strong>DynamisScience</strong><span>scientific computation layer</span></div>
          <button className="mobile-close" onClick={() => setMobileNav(false)}><X size={15} /></button>
        </div>
        <div className="nav-context">
          <span className="eyebrow">Workspace</span>
          <button><span className="context-dot" />CMJ Intervention<ChevronDown size={13} /></button>
        </div>
        <nav className="nav-groups">
          {navGroups.map((group) => (
            <div className="nav-group" key={group.label}>
              <span className="nav-group-label">{group.label}</span>
              {group.items.map((item) => {
                const Icon = item.icon;
                return (
                  <button key={item.id} className={`nav-item ${view === item.id ? "active" : ""}`} onClick={() => navigate(item.id)}>
                    <Icon size={16} />
                    <span>{item.label}</span>
                    {item.shortcut && <kbd>{item.shortcut}</kbd>}
                  </button>
                );
              })}
            </div>
          ))}
        </nav>
        <div className="nav-bottom">
          <div className="dataset-card">
            <div className="dataset-card-top"><Database size={14} /><span>Dataset</span><StatusBadge tone="cyan">LOCAL</StatusBadge></div>
            <strong className="mono">{snapshot?.id ?? "DS-SYNTH-001"}</strong>
            <span>{snapshot ? `${Object.values(snapshot.row_counts).reduce((sum, value) => sum + value, 0).toLocaleString()} rows · immutable` : "Synthetic · immutable snapshot"}</span>
          </div>
          <div className="nav-footer-links">
            <button><Settings2 size={14} />Workspace settings</button>
            <span className="version">v0.1.0 · local</span>
          </div>
        </div>
      </aside>
      <div className="app-main">
        <header className="top-bar">
          <div className="top-left">
            <button className="mobile-menu" onClick={() => setMobileNav(true)}><Menu size={17} /></button>
            <div className="top-context">
              <span className="eyebrow">Current context</span>
              <strong>{viewLabel(view)}</strong>
              <span className="context-separator">/</span>
              <span className="mono">{contextId ?? snapshot?.id ?? "DS-SYNTH-001"}</span>
            </div>
          </div>
          <div className="top-center">
            <button className="command-trigger" onClick={() => setCommandOpen(true)}>
              <Search size={15} />
              <span>Search commands, athletes, artifacts</span>
              <kbd><Command size={11} /> K</kbd>
            </button>
          </div>
          <div className="top-right">
            <div className="repro-state"><span className="repro-dot" /><span>REPRODUCIBLE</span></div>
            <button className="top-icon" onClick={() => setInspectorOpen((open) => !open)} title="Toggle scientific inspector"><PanelRight size={16} /></button>
            <div className="agent-avatar">DS</div>
          </div>
        </header>
        <div className="workspace">
          <main className="main-workspace">
            <ViewRenderer view={view} contextId={contextId} onNavigate={navigate} />
          </main>
          {inspectorOpen && <InspectorRail view={view} snapshot={snapshot} onNavigate={navigate} />}
        </div>
      </div>
      {commandOpen && <CommandPalette onClose={() => setCommandOpen(false)} onNavigate={navigate} />}
    </div>
  );
}

function viewLabel(view: ViewKey) {
  return navGroups.flatMap((group) => group.items).find((item) => item.id === view)?.label ?? "Overview";
}

function ViewRenderer({ view, contextId, onNavigate }: { view: ViewKey; contextId?: string; onNavigate: (view: string, id?: string) => void }) {
  if (view === "overview") return <OverviewView onNavigate={onNavigate} />;
  if (view === "studies") return <StudyView onNavigate={onNavigate} />;
  if (view === "monitor") return <MonitorView key={contextId ?? "default"} onNavigate={onNavigate} initialSubjectId={contextId} />;
  if (view === "forcelab") return <ForceLabView onNavigate={onNavigate} />;
  if (view === "matchlab") return <MatchLabView onNavigate={onNavigate} />;
  if (view === "analyses") return <AnalysisView key={contextId ?? "default"} onNavigate={onNavigate} initialNodeId={contextId} />;
  if (view === "models") return <ModelLabView />;
  if (view === "runs") return <RunsView key={contextId ?? "default"} initialRunId={contextId} onNavigate={onNavigate} />;
  if (view === "registry") return <RegistryView />;
  if (view === "reports") return <ReportView onNavigate={onNavigate} />;
  return <LineageView key={contextId ?? "root"} initialArtifactId={contextId} />;
}

function InspectorRail({ view, snapshot, onNavigate }: { view: ViewKey; snapshot?: Snapshot; onNavigate: (view: string, id?: string) => void }) {
  const evidence = useQuery({ queryKey: ["evidence", "inspector"], queryFn: scienceApi.evidence });
  const overview = useQuery({ queryKey: ["overview", "shell"], queryFn: scienceApi.overview });
  const selected = evidence.data?.[0];
  const health = overview.data?.data_health;
  return (
    <aside className="inspector-rail">
      <div className="inspector-rail-header">
        <div><span className="eyebrow">Scientific inspector</span><strong>{view === "overview" ? "Workspace context" : `${viewLabel(view)} context`}</strong></div>
        <span className="inspector-live"><span />LIVE</span>
      </div>
      <Panel className="inspector-panel" eyebrow="Reproducibility state" title="Analysis boundary">
        <div className="inspector-status">
          <div className="status-orbit"><ShieldCheck size={19} /></div>
          <div><strong>Local evidence ready</strong><span>All values resolve to a stored artifact.</span></div>
        </div>
        <KeyValue label="Snapshot" value={snapshot?.id ?? "DS-SYNTH-001"} mono />
        <KeyValue label="Generator" value={snapshot?.generator_version ?? "dynamis-synthetic@1.0.0"} mono />
        <KeyValue label="Seed" value={String(snapshot?.seed ?? 20260924)} mono />
        <KeyValue label="Provenance" value={health ? `${health.provenance_completeness.toFixed(1)}% complete` : "—"} mono />
        <div className="inspector-checks">
          <div><CheckMark />input provenance</div>
          <div><CheckMark />method version</div>
          <div><CheckMark />software environment</div>
          <div><CheckMark />artifact reference</div>
        </div>
      </Panel>
      <Panel className="inspector-panel" eyebrow="Active evidence" title="Latest result">
        <button className="inspector-evidence" onClick={() => onNavigate("lineage", selected?.id ?? "EVID-0001")}>
          <span className="evidence-type">{selected?.kind.slice(0, 3) ?? "EFF"}</span>
          <span><strong>{selected?.title ?? "Effect estimate"}</strong><small>{selected?.id ?? "EVID-0001"} · {selected?.analysis_run_id ?? "RUN-0001"}</small></span>
          <ArrowRightIcon />
        </button>
        <div className="inspector-value"><strong>{selected?.value?.toFixed(3) ?? "—"}</strong><span>{selected?.unit ?? "N·s·kg⁻¹"}</span></div>
        <div className="inspector-meta"><span>Uncertainty</span><strong className="mono">{selected?.uncertainty?.toFixed(3) ?? "—"} {selected?.uncertainty_label ?? "SE"}</strong></div>
      </Panel>
      <Panel className="inspector-panel" eyebrow="Navigate provenance" title="Scientific route">
        <button className="route-button" onClick={() => onNavigate("studies")}><span>01</span><BookOpen size={14} />Study &amp; frozen plan<ChevronRight size={13} /></button>
        <button className="route-button" onClick={() => onNavigate("monitor")}><span>02</span><Users size={14} />Athlete observations<ChevronRight size={13} /></button>
        <button className="route-button" onClick={() => onNavigate("forcelab")}><span>03</span><Activity size={14} />Source trial<ChevronRight size={13} /></button>
        <button className="route-button" onClick={() => onNavigate("analyses")}><span>04</span><BarChart3 size={14} />Analysis run<ChevronRight size={13} /></button>
        <button className="route-button" onClick={() => onNavigate("lineage")}><span>05</span><GitBranch size={14} />Lineage to report<ChevronRight size={13} /></button>
      </Panel>
      <div className="inspector-footer"><span>DynamisScience local runtime</span><span className="mono">0.1.0</span></div>
    </aside>
  );
}

function CheckMark() {
  return <span className="check-mark"><CheckIcon /></span>;
}
function CheckIcon() {
  return <span>✓</span>;
}
function ArrowRightIcon() {
  return <span className="arrow-right">→</span>;
}

interface PaletteCommand {
  id: string;
  label: string;
  group: string;
  icon: typeof LayoutDashboard;
  view: string;
  context?: string;
}

function CommandPalette({ onClose, onNavigate }: { onClose: () => void; onNavigate: (view: string, id?: string) => void }) {
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const listRef = useRef<HTMLDivElement>(null);
  const subjects = useQuery({ queryKey: ["subjects", "palette"], queryFn: scienceApi.subjects });
  const evidence = useQuery({ queryKey: ["evidence", "palette"], queryFn: scienceApi.evidence });
  const runs = useQuery({ queryKey: ["runs", "palette"], queryFn: scienceApi.runs });

  const commands = useMemo<PaletteCommand[]>(() => {
    const navigation: PaletteCommand[] = [
      { id: "overview", label: "Open Overview", group: "Navigate", icon: LayoutDashboard, view: "overview" },
      { id: "studies", label: "Open Studies", group: "Navigate", icon: BookOpen, view: "studies" },
      { id: "monitor", label: "Open Monitor", group: "Navigate", icon: LineChart, view: "monitor" },
      { id: "forcelab", label: "Open ForceLab", group: "Navigate", icon: Activity, view: "forcelab" },
      { id: "matchlab", label: "Open MatchLab", group: "Navigate", icon: Box, view: "matchlab" },
      { id: "analyses", label: "Open Analyses", group: "Navigate", icon: Network, view: "analyses" },
      { id: "models", label: "Open ModelLab", group: "Navigate", icon: FlaskConical, view: "models" },
      { id: "runs", label: "Open Runs", group: "Navigate", icon: History, view: "runs" },
      { id: "registry", label: "Open Registry", group: "Navigate", icon: Table2, view: "registry" },
      { id: "reports", label: "Open Report", group: "Navigate", icon: FileText, view: "reports" },
      { id: "lineage", label: "Open Lineage", group: "Navigate", icon: GitBranch, view: "lineage" },
    ];
    const athletes: PaletteCommand[] = (subjects.data ?? []).map((subject) => ({
      id: `athlete-${subject.subject_id}`,
      label: `${subject.display_id} · ${subject.position} · ${subject.intervention_arm === "INTERVENTION" ? "intervention" : "comparison"}`,
      group: "Athlete",
      icon: Users,
      view: "monitor",
      context: subject.subject_id,
    }));
    const evidenceCommands: PaletteCommand[] = (evidence.data ?? []).map((item) => ({
      id: `evidence-${item.id}`,
      label: `${item.id} · ${item.title}`,
      group: "Evidence",
      icon: Hexagon,
      view: "lineage",
      context: item.id,
    }));
    const runCommands: PaletteCommand[] = (runs.data ?? []).map((run) => ({
      id: `run-${run.id}`,
      label: `${run.id} · ${run.method_id} · ${run.snapshot_id}`,
      group: "Run",
      icon: History,
      view: "runs",
      context: run.id,
    }));
    return [...navigation, ...athletes, ...evidenceCommands, ...runCommands];
  }, [evidence.data, runs.data, subjects.data]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return commands.slice(0, 24);
    return commands.filter((command) => `${command.label} ${command.group} ${command.id}`.toLowerCase().includes(needle)).slice(0, 40);
  }, [commands, query]);

  useEffect(() => setActiveIndex(0), [query]);

  const activate = useCallback((command: PaletteCommand | undefined) => {
    if (!command) return;
    onNavigate(command.view, command.context);
  }, [onNavigate]);

  const onKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((index) => Math.min(filtered.length - 1, index + 1));
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((index) => Math.max(0, index - 1));
    }
    if (event.key === "Enter") {
      event.preventDefault();
      activate(filtered[activeIndex]);
    }
  };

  useEffect(() => {
    const node = listRef.current?.querySelector<HTMLElement>(`[data-index="${activeIndex}"]`);
    node?.scrollIntoView({ block: "nearest" });
  }, [activeIndex]);

  return (
    <div className="palette-backdrop" onMouseDown={onClose}>
      <div className="command-palette" onMouseDown={(event) => event.stopPropagation()}>
        <div className="palette-input">
          <Search size={17} />
          <input autoFocus value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={onKeyDown} placeholder="Search modules, athletes, evidence, runs" />
          <kbd>ESC</kbd>
        </div>
        <div className="palette-list" ref={listRef}>
          {filtered.map((command, index) => {
            const Icon = command.icon;
            return (
              <button
                key={command.id}
                data-index={index}
                className={index === activeIndex ? "active" : ""}
                onMouseEnter={() => setActiveIndex(index)}
                onClick={() => activate(command)}
              >
                <span className="palette-icon"><Icon size={15} /></span>
                <span><strong>{command.label}</strong><small>{command.group}{command.context ? ` · ${command.context}` : ""}</small></span>
                <kbd>↵</kbd>
              </button>
            );
          })}
          {filtered.length === 0 && <div className="palette-empty">No local command matches.</div>}
        </div>
        <div className="palette-footer">
          <span><Command size={11} /> K to open · ↑↓ to move · ↵ to open</span>
          <span>Navigation only · no AI commands</span>
        </div>
      </div>
    </div>
  );
}
