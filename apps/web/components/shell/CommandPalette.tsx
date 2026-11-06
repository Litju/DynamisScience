"use client";

import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Activity, BookOpen, CalendarRange, Database, FileText, FlaskConical, Grid3x3, Hexagon, History, Library, Ruler, Search, TestTubes, User } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { scienceApi } from "@/lib/api";
import { performanceApi } from "@/lib/performance/api";

interface Command {
  id: string;
  label: string;
  hint: string;
  group: string;
  href: string;
  icon: typeof Search;
}

/** Navigation and search only: the palette never runs AI or hidden computation. */
export function CommandPalette({ onClose }: { onClose: () => void }) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const listRef = useRef<HTMLDivElement>(null);
  const restoreRef = useRef<HTMLElement | null>(null);
  const subjects = useQuery({ queryKey: ["subjects"], queryFn: () => scienceApi.subjects() });
  const evidence = useQuery({ queryKey: ["evidence"], queryFn: () => scienceApi.evidence() });
  const library = useQuery({ queryKey: ["library"], queryFn: scienceApi.library });
  const reports = useQuery({ queryKey: ["performance-reports"], queryFn: () => performanceApi.reports() });

  useEffect(() => {
    restoreRef.current = document.activeElement as HTMLElement | null;
    return () => restoreRef.current?.focus?.({ preventScroll: true });
  }, []);

  const commands = useMemo<Command[]>(() => {
    const actions: Command[] = [
      { id: "today", label: "Open Today · Squad command", hint: "Daily", group: "Workspaces", href: "/today", icon: Activity },
      { id: "plan", label: "Open Plan · Microcycle", hint: "Weekly", group: "Workspaces", href: "/plan", icon: CalendarRange },
      { id: "monitor", label: "Open Monitor · Longitudinal", hint: "Trends", group: "Workspaces", href: "/monitor", icon: Activity },
      { id: "test", label: "Open Test · CMJ battery", hint: "Testing", group: "Workspaces", href: "/test", icon: TestTubes },
      { id: "research", label: "Open Research", hint: "Studies · evidence", group: "Workspaces", href: "/research", icon: FlaskConical },
      { id: "report", label: "Open Reports", hint: "Audience templates", group: "Workspaces", href: "/report", icon: FileText },
      { id: "atlas", label: "Open Component & unit atlas", hint: "Conventions", group: "Workspaces", href: "/atlas", icon: Grid3x3 },
      { id: "study", label: "Open study · CMJ Response to 8-Week Strength Intervention", hint: "STUDY-001", group: "Research", href: "/research/studies/STUDY-001", icon: BookOpen },
      { id: "report-science", label: "Open scientific report", hint: "REPORT-001", group: "Research", href: "/research/studies/STUDY-001?mode=report", icon: FileText },
      { id: "dataset", label: "Open dataset DS-SYNTH-001", hint: "Data admission", group: "Research", href: "/data/DS-SYNTH-001", icon: Database },
      { id: "library", label: "Open metric & method registry", hint: "Library", group: "Research", href: "/library", icon: Library },
    ];
    const athletes = (subjects.data ?? []).map<Command>((subject) => ({
      id: `ath-${subject.subject_id}`,
      label: `${subject.display_id} · ${subject.position} · athlete 360`,
      hint: subject.subject_id,
      group: "Athletes",
      href: `/athletes/${subject.display_id}`,
      icon: User,
    }));
    const evidenceItems = (evidence.data ?? []).map<Command>((item) => ({
      id: `ev-${item.id}`,
      label: `${item.id} · ${item.title}`,
      hint: `${item.evidence_class ?? item.quality} · ${item.analysis_run_id}`,
      group: "Evidence",
      href: `/research/studies/STUDY-001?inspect=evidence:${item.id}`,
      icon: Hexagon,
    }));
    const metrics = (library.data?.metrics ?? []).map<Command>((metric) => ({
      id: `met-${metric.id}`,
      label: metric.name,
      hint: `${metric.canonical_id} · ${metric.unit}`,
      group: "Metrics",
      href: `/library?tab=metrics&id=${metric.id}`,
      icon: Ruler,
    }));
    const reportItems = (reports.data ?? []).map<Command>((report) => ({
      id: `report-${report.id}`,
      label: `${report.title} · v${report.version}`,
      hint: `${report.status} · ${report.audience}`,
      group: "Performance reports",
      href: `/report?report=${report.id}`,
      icon: History,
    }));
    return [...actions, ...athletes, ...evidenceItems, ...reportItems, ...metrics];
  }, [evidence.data, library.data, reports.data, subjects.data]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const matches = needle ? commands.filter((command) => `${command.label} ${command.hint} ${command.group}`.toLowerCase().includes(needle)) : commands.filter((command) => command.group !== "Metrics").slice(0, 18);
    return matches.slice(0, 60);
  }, [commands, query]);

  useEffect(() => setActive(0), [query]);
  useEffect(() => {
    listRef.current?.querySelector<HTMLElement>(`[data-index="${active}"]`)?.scrollIntoView({ block: "nearest" });
  }, [active]);

  const run = useCallback(
    (command?: Command) => {
      if (!command) return;
      onClose();
      router.push(command.href);
    },
    [onClose, router],
  );

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      onClose();
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      setActive((index) => Math.min(filtered.length - 1, index + 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((index) => Math.max(0, index - 1));
    } else if (event.key === "Enter") {
      event.preventDefault();
      run(filtered[active]);
    } else if (event.key === "Tab") {
      event.preventDefault();
    }
  };

  let lastGroup = "";
  return (
    <div className="palette-backdrop" onMouseDown={onClose}>
      <div className="palette" role="dialog" aria-modal="true" aria-label="Command palette" onMouseDown={(event) => event.stopPropagation()} onKeyDown={onKeyDown}>
        <div className="palette-input">
          <Search size={15} className="faint" />
          <input autoFocus value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Open athlete, session, test, study, evidence, report…" aria-label="Search commands" role="combobox" aria-expanded="true" aria-controls="palette-list" aria-activedescendant={filtered[active] ? `cmd-${filtered[active].id}` : undefined} />
          <kbd>Esc</kbd>
        </div>
        <div className="palette-list" id="palette-list" role="listbox" ref={listRef}>
          {filtered.map((command, index) => {
            const Icon = command.icon;
            const header = command.group !== lastGroup ? <div className="palette-group">{command.group}</div> : null;
            lastGroup = command.group;
            return (
              <div key={command.id}>
                {header}
                <button type="button" id={`cmd-${command.id}`} role="option" aria-selected={index === active} data-index={index} className="palette-item" onMouseEnter={() => setActive(index)} onClick={() => run(command)}>
                  <Icon size={14} />
                  <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{command.label}</span>
                  <small>{command.hint}</small>
                </button>
              </div>
            );
          })}
          {filtered.length === 0 && <div className="empty" style={{ padding: 14 }}>No match in the local workspace.</div>}
        </div>
        <div className="palette-foot">
          <span>↑↓ move · ↵ open · Esc close</span>
          <span>Local navigation only · no AI commands</span>
        </div>
      </div>
    </div>
  );
}
