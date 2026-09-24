"use client";

import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { Activity, BarChart3, BookOpen, Box, ChevronDown, ChevronRight, Command, Database, FlaskConical, GitBranch, History, LayoutDashboard, LineChart, Menu, Network, PanelRight, Search, Settings2, ShieldCheck, Table2, Users, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
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
  useEffect(() => { const hash = window.location.hash.replace("#", "") as ViewKey; if (navGroups.some((group) => group.items.some((item) => item.id === hash))) setView(hash); }, []);
  useEffect(() => { const onKey = (event: KeyboardEvent) => { if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") { event.preventDefault(); setCommandOpen((open) => !open); } if (event.key === "Escape") setCommandOpen(false); }; window.addEventListener("keydown", onKey); return () => window.removeEventListener("keydown", onKey); }, []);
  const navigate = (next: string, id?: string) => { const nextView = next as ViewKey; if (navGroups.some((group) => group.items.some((item) => item.id === nextView))) { setView(nextView); setContextId(id); window.history.replaceState(null, "", `#${nextView}`); setCommandOpen(false); setMobileNav(false); } };
  const snapshot = (overview.data as { snapshot?: Snapshot } | undefined)?.snapshot;
  return <div className="app-shell"><aside className={`left-nav ${mobileNav ? "mobile-open" : ""}`}><div className="brand-lockup"><div className="brand-symbol"><span>∿</span></div><div><strong>DynamisScience</strong><span>scientific computation layer</span></div><button className="mobile-close" onClick={() => setMobileNav(false)}><X size={15} /></button></div><div className="nav-context"><span className="eyebrow">Workspace</span><button><span className="context-dot" />CMJ Intervention<ChevronDown size={13} /></button></div><nav className="nav-groups">{navGroups.map((group) => <div className="nav-group" key={group.label}><span className="nav-group-label">{group.label}</span>{group.items.map((item) => { const Icon = item.icon; return <button key={item.id} className={`nav-item ${view === item.id ? "active" : ""}`} onClick={() => navigate(item.id)}><Icon size={16} /><span>{item.label}</span>{item.shortcut && <kbd>{item.shortcut}</kbd>}</button>; })}</div>)}</nav><div className="nav-bottom"><div className="dataset-card"><div className="dataset-card-top"><Database size={14} /><span>Dataset</span><StatusBadge tone="cyan">LOCAL</StatusBadge></div><strong className="mono">{snapshot?.id ?? "DS-SYNTH-001"}</strong><span>Synthetic · immutable snapshot</span></div><div className="nav-footer-links"><button><Settings2 size={14} />Workspace settings</button><span className="version">v0.1.0 · local</span></div></div></aside><div className="app-main"><header className="top-bar"><div className="top-left"><button className="mobile-menu" onClick={() => setMobileNav(true)}><Menu size={17} /></button><div className="top-context"><span className="eyebrow">Current context</span><strong>{viewLabel(view)}</strong><span className="context-separator">/</span><span className="mono">{snapshot?.id ?? "DS-SYNTH-001"}</span></div></div><div className="top-center"><button className="command-trigger" onClick={() => setCommandOpen(true)}><Search size={15} /><span>Search commands, athletes, artifacts</span><kbd><Command size={11} /> K</kbd></button></div><div className="top-right"><div className="repro-state"><span className="repro-dot" /><span>REPRODUCIBLE</span></div><button className="top-icon" onClick={() => setInspectorOpen((open) => !open)} title="Toggle scientific inspector"><PanelRight size={16} /></button><div className="agent-avatar">DS</div></div></header><div className="workspace"><main className="main-workspace"><ViewRenderer view={view} contextId={contextId} onNavigate={navigate} /></main>{inspectorOpen && <InspectorRail view={view} snapshot={snapshot} onNavigate={navigate} />}</div></div>{commandOpen && <CommandPalette onClose={() => setCommandOpen(false)} onNavigate={navigate} />}</div>;
}

function viewLabel(view: ViewKey) { return navGroups.flatMap((group) => group.items).find((item) => item.id === view)?.label ?? "Overview"; }

function ViewRenderer({ view, contextId, onNavigate }: { view: ViewKey; contextId?: string; onNavigate: (view: string, id?: string) => void }) {
  if (view === "overview") return <OverviewView onNavigate={onNavigate} />;
  if (view === "studies") return <StudyView onNavigate={onNavigate} />;
  if (view === "monitor") return <MonitorView onNavigate={onNavigate} />;
  if (view === "forcelab") return <ForceLabView onNavigate={onNavigate} />;
  if (view === "matchlab") return <MatchLabView onNavigate={onNavigate} />;
  if (view === "analyses") return <AnalysisView onNavigate={onNavigate} initialNodeId={contextId} />;
  if (view === "models") return <ModelLabView />;
  if (view === "runs") return <RunsView initialRunId={contextId} onNavigate={onNavigate} />;
  if (view === "registry") return <RegistryView />;
  if (view === "reports") return <ReportView onNavigate={onNavigate} />;
  return <LineageView initialArtifactId={contextId} />;
}

function InspectorRail({ view, snapshot, onNavigate }: { view: ViewKey; snapshot?: Snapshot; onNavigate: (view: string, id?: string) => void }) {
  const evidence = useQuery({ queryKey: ["evidence", "inspector"], queryFn: scienceApi.evidence });
  const selected = evidence.data?.[0];
  return <aside className="inspector-rail"><div className="inspector-rail-header"><div><span className="eyebrow">Scientific inspector</span><strong>{view === "overview" ? "Workspace context" : `${viewLabel(view)} context`}</strong></div><span className="inspector-live"><span />LIVE</span></div><Panel className="inspector-panel" eyebrow="Reproducibility state" title="Analysis boundary"><div className="inspector-status"><div className="status-orbit"><ShieldCheck size={19} /></div><div><strong>Local evidence ready</strong><span>All values resolve to a stored artifact.</span></div></div><KeyValue label="Snapshot" value={snapshot?.id ?? "DS-SYNTH-001"} mono /><KeyValue label="Generator" value={snapshot?.generator_version ?? "dynamis-synthetic@1.0.0"} mono /><KeyValue label="Seed" value={String(snapshot?.seed ?? 20260924)} mono /><div className="inspector-checks"><div><CheckMark />input provenance</div><div><CheckMark />method version</div><div><CheckMark />software environment</div><div><CheckMark />artifact reference</div></div></Panel><Panel className="inspector-panel" eyebrow="Active evidence" title="Latest result"><button className="inspector-evidence" onClick={() => onNavigate("lineage", selected?.id ?? "EVID-0001")}><span className="evidence-type">EFF</span><span><strong>{selected?.title ?? "Effect estimate"}</strong><small>{selected?.id ?? "EVID-0001"}</small></span><ArrowRightIcon /></button><div className="inspector-value"><strong>{selected?.value?.toFixed(3) ?? "—"}</strong><span>{selected?.unit ?? "N·s·kg⁻¹"}</span></div><div className="inspector-meta"><span>Uncertainty</span><strong className="mono">{selected?.uncertainty?.toFixed(3) ?? "—"} {selected?.uncertainty_label ?? "SE"}</strong></div></Panel><Panel className="inspector-panel" eyebrow="Navigate provenance" title="Scientific route"><button className="route-button" onClick={() => onNavigate("studies")}><span>01</span><BookOpen size={14} />Study & frozen plan<ChevronRight size={13} /></button><button className="route-button" onClick={() => onNavigate("monitor")}><span>02</span><Users size={14} />Athlete observations<ChevronRight size={13} /></button><button className="route-button" onClick={() => onNavigate("forcelab")}><span>03</span><Activity size={14} />Source trial<ChevronRight size={13} /></button><button className="route-button" onClick={() => onNavigate("analyses")}><span>04</span><BarChart3 size={14} />Analysis run<ChevronRight size={13} /></button><button className="route-button" onClick={() => onNavigate("lineage")}><span>05</span><GitBranch size={14} />Lineage to report<ChevronRight size={13} /></button></Panel><div className="inspector-footer"><span>DynamisScience local runtime</span><span className="mono">0.1.0</span></div></aside>;
}

function CheckMark() { return <span className="check-mark"><CheckIcon /></span>; }
function CheckIcon() { return <span>✓</span>; }
function ArrowRightIcon() { return <span className="arrow-right">→</span>; }

function CommandPalette({ onClose, onNavigate }: { onClose: () => void; onNavigate: (view: string, id?: string) => void }) {
  const [query, setQuery] = useState("");
  const commands = useMemo(() => [
    { id: "overview", label: "Open Overview", group: "Navigate", icon: LayoutDashboard },
    { id: "studies", label: "Open Study", group: "Navigate", icon: BookOpen },
    { id: "monitor", label: "Open Monitor", group: "Navigate", icon: LineChart },
    { id: "forcelab", label: "Open ForceLab", group: "Navigate", icon: Activity },
    { id: "matchlab", label: "Open MatchLab", group: "Navigate", icon: Box },
    { id: "analyses", label: "Open Analysis", group: "Navigate", icon: Network },
    { id: "registry", label: "Open Registry", group: "Navigate", icon: Table2 },
    { id: "runs", label: "Open Runs", group: "Navigate", icon: History },
    { id: "reports", label: "Open Report", group: "Navigate", icon: BookOpen },
    { id: "athlete-001", label: "Inspect athlete ATH-001", group: "Athlete lookup", icon: Users, view: "monitor" },
  ].filter((command) => command.label.toLowerCase().includes(query.toLowerCase())), [query]);
  return <div className="palette-backdrop" onMouseDown={onClose}><div className="command-palette" onMouseDown={(event) => event.stopPropagation()}><div className="palette-input"><Search size={17} /><input autoFocus value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search commands or athletes" /><kbd>ESC</kbd></div><div className="palette-list">{commands.map((command) => { const Icon = command.icon; return <button key={command.id} onClick={() => onNavigate(command.view ?? command.id)}><span className="palette-icon"><Icon size={15} /></span><span><strong>{command.label}</strong><small>{command.group}</small></span><kbd>↵</kbd></button>; })}{commands.length === 0 && <div className="palette-empty">No local command matches.</div>}</div><div className="palette-footer"><span><Command size={11} /> K to open</span><span>Navigation only · no AI commands</span></div></div></div>;
}
