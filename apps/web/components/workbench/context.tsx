"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { scienceApi, ScienceError } from "@/lib/api";
import type { StudyDetail, WorkbenchBlock } from "@/lib/types";
import { firstOfType } from "@/lib/workbench";

export type InspectTarget =
  | { kind: "block"; id: string }
  | { kind: "athlete"; id: string }
  | { kind: "trial"; id: string }
  | { kind: "run"; id: string }
  | { kind: "evidence"; id: string }
  | { kind: "figure"; id: string }
  | { kind: "metric"; id: string }
  | { kind: "method"; id: string }
  | { kind: "protocol"; id: string }
  | { kind: "design"; section: "hypotheses" | "arms" | "timeline" | "plan" }
  | { kind: "report" };

export type Viewer = { kind: "force"; trialId: string } | { kind: "match"; eventId?: string; athleteId?: string };

/**
 * Linked scientific selection. Only these fields are shared across blocks, and
 * every one is visible in the context strip so linking is never silent.
 */
export interface Selection {
  athleteId: string | null;
  week: number | null;
  trialId: string | null;
  matchEventId: string | null;
}

export type SaveState = "idle" | "saving" | "saved" | "error";

interface WorkbenchValue {
  studyId: string;
  study: StudyDetail;
  investigationId: string;
  blocks: WorkbenchBlock[];
  version: number;
  saveState: SaveState;
  saveError: string | null;
  setBlocks: (update: (blocks: WorkbenchBlock[]) => WorkbenchBlock[]) => void;
  excludedSubjectIds: string[];
  selection: Selection;
  select: (patch: Partial<Selection>) => void;
  selectedBlockId: string | null;
  selectBlock: (id: string | null, options?: { scroll?: boolean; inspect?: boolean }) => void;
  inspector: InspectTarget | null;
  inspect: (target: InspectTarget | null) => void;
  inspectBack: () => void;
  canInspectBack: boolean;
  viewer: Viewer | null;
  openViewer: (viewer: Viewer) => void;
  closeViewer: () => void;
  lineageFor: string | null;
  openLineage: (artifactId: string) => void;
  closeLineage: () => void;
  historyOpen: boolean;
  setHistoryOpen: (open: boolean) => void;
  mode: "investigation" | "report";
  setMode: (mode: "investigation" | "report") => void;
  notice: string | null;
  notify: (message: string) => void;
}

const Context = createContext<WorkbenchValue | null>(null);

export function useWorkbench(): WorkbenchValue {
  const value = useContext(Context);
  if (!value) throw new Error("useWorkbench must be used inside WorkbenchProvider");
  return value;
}

export function WorkbenchProvider({ study, investigationId, children }: { study: StudyDetail; investigationId: string; children: ReactNode }) {
  const investigation = useQuery({ queryKey: ["investigation", investigationId], queryFn: () => scienceApi.investigation(investigationId), staleTime: Infinity });
  const [blocks, setBlocksState] = useState<WorkbenchBlock[] | null>(null);
  const [version, setVersion] = useState(0);
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [saveError, setSaveError] = useState<string | null>(null);
  const dirty = useRef(false);
  const versionRef = useRef(0);

  useEffect(() => {
    if (investigation.data && blocks === null) {
      setBlocksState(investigation.data.blocks);
      setVersion(investigation.data.version);
      versionRef.current = investigation.data.version;
    }
  }, [blocks, investigation.data]);

  const setBlocks = useCallback((update: (current: WorkbenchBlock[]) => WorkbenchBlock[]) => {
    setBlocksState((current) => {
      if (!current) return current;
      const next = update(current);
      if (next !== current) dirty.current = true;
      return next;
    });
  }, []);

  // Persist the investigation document (debounced). Versions guard against lost updates.
  useEffect(() => {
    if (!blocks || !dirty.current) return;
    setSaveState("saving");
    const timer = window.setTimeout(async () => {
      dirty.current = false;
      try {
        let saved;
        try {
          saved = await scienceApi.saveInvestigation(investigationId, blocks, versionRef.current);
        } catch (error) {
          // A rapid fork/run can overlap two debounced saves. The server keeps the
          // first one; refetch the authoritative version and retry with the local
          // blocks, which are the scientist's latest intent.
          if (error instanceof ScienceError && error.status === 409) {
            const latest = await scienceApi.investigation(investigationId);
            versionRef.current = latest.version;
            saved = await scienceApi.saveInvestigation(investigationId, blocks, latest.version);
          } else {
            throw error;
          }
        }
        versionRef.current = saved.version;
        setVersion(saved.version);
        setSaveState("saved");
        setSaveError(null);
      } catch (error) {
        setSaveState("error");
        setSaveError(error instanceof ScienceError ? error.detail || error.message : String(error));
      }
    }, 500);
    return () => window.clearTimeout(timer);
  }, [blocks, investigationId]);

  const [selection, setSelection] = useState<Selection>({ athleteId: null, week: null, trialId: null, matchEventId: null });
  const select = useCallback((patch: Partial<Selection>) => setSelection((current) => ({ ...current, ...patch })), []);

  const [selectedBlockId, setSelectedBlockId] = useState<string | null>(null);
  const [inspector, setInspector] = useState<InspectTarget | null>(null);
  const history = useRef<InspectTarget[]>([]);
  const [canInspectBack, setCanInspectBack] = useState(false);
  const inspectorRef = useRef<InspectTarget | null>(null);
  const inspect = useCallback((target: InspectTarget | null) => {
    const current = inspectorRef.current;
    if (current && target && JSON.stringify(current) !== JSON.stringify(target)) history.current = [...history.current.slice(-12), current];
    inspectorRef.current = target;
    setCanInspectBack(history.current.length > 0);
    setInspector(target);
  }, []);
  const inspectBack = useCallback(() => {
    const previous = history.current.pop();
    setCanInspectBack(history.current.length > 0);
    if (previous) {
      inspectorRef.current = previous;
      setInspector(previous);
    }
  }, []);

  const selectBlock = useCallback((id: string | null, options: { scroll?: boolean; inspect?: boolean } = {}) => {
    setSelectedBlockId(id);
    if (id && options.inspect !== false) inspect({ kind: "block", id });
    if (id && options.scroll) {
      window.requestAnimationFrame(() => document.getElementById(`block-${id}`)?.scrollIntoView({ block: "start", behavior: "smooth" }));
    }
  }, [inspect]);

  const [viewer, setViewer] = useState<Viewer | null>(null);
  const [lineageFor, setLineageFor] = useState<string | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [mode, setMode] = useState<"investigation" | "report">("investigation");
  const [notice, setNotice] = useState<string | null>(null);
  const noticeTimer = useRef<number | undefined>(undefined);
  const notify = useCallback((message: string) => {
    setNotice(message);
    window.clearTimeout(noticeTimer.current);
    noticeTimer.current = window.setTimeout(() => setNotice(null), 4200);
  }, []);

  const excludedSubjectIds = useMemo(() => {
    const cohort = blocks ? firstOfType(blocks, "cohort") : undefined;
    const value = cohort?.state.excluded_subject_ids;
    return Array.isArray(value) ? (value as string[]) : [];
  }, [blocks]);

  const value = useMemo<WorkbenchValue | null>(() => {
    if (!blocks) return null;
    return {
      studyId: study.study.id,
      study,
      investigationId,
      blocks,
      version,
      saveState,
      saveError,
      setBlocks,
      excludedSubjectIds,
      selection,
      select,
      selectedBlockId,
      selectBlock,
      inspector,
      inspect,
      inspectBack,
      canInspectBack,
      viewer,
      openViewer: setViewer,
      closeViewer: () => setViewer(null),
      lineageFor,
      openLineage: setLineageFor,
      closeLineage: () => setLineageFor(null),
      historyOpen,
      setHistoryOpen,
      mode,
      setMode: (next: "investigation" | "report") => {
        setMode(next);
        if (next === "report") inspect({ kind: "report" });
      },
      notice,
      notify,
    };
  }, [blocks, canInspectBack, excludedSubjectIds, historyOpen, inspect, inspectBack, inspector, investigationId, lineageFor, mode, notice, notify, saveError, saveState, select, selectBlock, selectedBlockId, selection, setBlocks, study, version, viewer]);

  if (investigation.error) throw investigation.error;
  if (!value) return null;
  return <Context.Provider value={value}>{children}</Context.Provider>;
}
