"use client";

import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { BookOpen, Database, FileText, FlaskConical, Hexagon, History, Library, Ruler, Search, User } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { scienceApi } from "@/lib/api";

const STUDY = "/research/studies/STUDY-001";

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
  const subjects = useQuery({ queryKey: ["subjects"], queryFn: scienceApi.subjects });
  const evidence = useQuery({ queryKey: ["evidence"], queryFn: scienceApi.evidence });
  const runs = useQuery({ queryKey: ["runs"], queryFn: scienceApi.runs });
  const library = useQuery({ queryKey: ["library"], queryFn: scienceApi.library });

  useEffect(() => {
    restoreRef.current = document.activeElement as HTMLElement | null;
    return () => restoreRef.current?.focus?.({ preventScroll: true });
  }, []);

  const commands = useMemo<Command[]>(() => {
    const actions: Command[] = [
      { id: "open-study", label: "Open study · CMJ Response to 8-Week Strength Intervention", hint: "STUDY-001", group: "Actions", href: STUDY, icon: FlaskConical },
      { id: "jump-investigation", label: "Jump to investigation · Primary Intervention Analysis", hint: "INV-001", group: "Actions", href: `${STUDY}?block=B-QUESTION`, icon: BookOpen },
      { id: "jump-report", label: "Jump to report", hint: "REPORT-001", group: "Actions", href: `${STUDY}?mode=report`, icon: FileText },
      { id: "open-dataset", label: "Open dataset DS-SYNTH-001", hint: "Data", group: "Actions", href: "/data/DS-SYNTH-001", icon: Database },
      { id: "open-library", label: "Open Library", hint: "Metrics · Protocols · Methods · Models", group: "Actions", href: "/library", icon: Library },
      { id: "open-research", label: "Open Research", hint: "Studies", group: "Actions", href: "/research", icon: FlaskConical },
    ];
    const athletes = (subjects.data ?? []).map<Command>((subject) => ({
      id: `ath-${subject.subject_id}`,
      label: `${subject.display_id} · ${subject.position} · ${subject.intervention_arm === "INTERVENTION" ? "intervention" : "comparison"}`,
      hint: subject.subject_id,
      group: "Athletes",
      href: `${STUDY}?athlete=${subject.subject_id}`,
      icon: User,
    }));
    const evidenceItems = (evidence.data ?? []).map<Command>((item) => ({
      id: `ev-${item.id}`,
      label: `${item.id} · ${item.title}`,
      hint: `${item.evidence_class ?? item.quality} · ${item.analysis_run_id}`,
      group: "Evidence",
      href: `${STUDY}?inspect=evidence:${item.id}`,
      icon: Hexagon,
    }));
    const metrics = (library.data?.metrics ?? []).map<Command>((metric) => ({
      id: `met-${metric.id}`,
      label: `${metric.name}`,
      hint: `${metric.canonical_id} · ${metric.unit}`,
      group: "Metrics",
      href: `/library?tab=metrics&id=${metric.id}`,
      icon: Ruler,
    }));
    const runItems = (runs.data ?? []).map<Command>((run) => ({
      id: `run-${run.id}`,
      label: `${run.id} · ${run.method_id} · ${run.plan_alignment ?? ""}`,
      hint: `${run.analysis_spec_id} · ${run.cohort_id}`,
      group: "Runs",
      href: `${STUDY}?inspect=run:${run.id}`,
      icon: History,
    }));
    return [...actions, ...athletes, ...evidenceItems, ...metrics, ...runItems];
  }, [evidence.data, library.data, runs.data, subjects.data]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const matches = needle ? commands.filter((command) => `${command.label} ${command.hint} ${command.group}`.toLowerCase().includes(needle)) : commands.filter((command) => command.group !== "Runs" && command.group !== "Metrics").slice(0, 16);
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
          <input autoFocus value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Open study, search athlete, evidence, metric, run…" aria-label="Search commands" role="combobox" aria-expanded="true" aria-controls="palette-list" aria-activedescendant={filtered[active] ? `cmd-${filtered[active].id}` : undefined} />
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
