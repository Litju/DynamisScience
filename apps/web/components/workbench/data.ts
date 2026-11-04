"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
import { scienceApi } from "@/lib/api";

export const keys = {
  study: (id: string) => ["study", id] as const,
  runs: (studyId?: string) => ["runs", studyId ?? "STUDY-001"] as const,
  evidence: (studyId?: string) => ["evidence", studyId ?? "STUDY-001"] as const,
  report: (studyId?: string) => ["report", studyId ?? "STUDY-001"] as const,
  library: ["library"] as const,
  subjects: (studyId?: string) => ["subjects", studyId ?? "STUDY-001"] as const,
};

export const useStudy = (id: string) => useQuery({ queryKey: keys.study(id), queryFn: () => scienceApi.study(id) });
export const useRuns = (studyId?: string) => useQuery({ queryKey: keys.runs(studyId), queryFn: () => scienceApi.runs(studyId) });
export const useEvidenceList = (studyId?: string) => useQuery({ queryKey: keys.evidence(studyId), queryFn: () => scienceApi.evidence(studyId) });
export const useReport = (studyId?: string) => useQuery({ queryKey: keys.report(studyId), queryFn: () => scienceApi.report(studyId) });
export const useLibrary = () => useQuery({ queryKey: keys.library, queryFn: scienceApi.library });
export const useSubjects = (studyId?: string) => useQuery({ queryKey: keys.subjects(studyId), queryFn: () => scienceApi.subjects(studyId) });
export const useFigure = (id: string | undefined) => useQuery({ queryKey: ["figure", id], queryFn: () => scienceApi.figure(id as string), enabled: Boolean(id) });
export const useRun = (id: string | undefined, studyId?: string) => {
  const runs = useRuns(studyId);
  return { ...runs, data: runs.data?.find((run) => run.id === id) };
};

/** After an execution, promotion or citation, every view of the ledger refreshes together. */
export function useInvalidateScience() {
  const client = useQueryClient();
  return useCallback(() => {
    void client.invalidateQueries({ queryKey: ["runs"] });
    void client.invalidateQueries({ queryKey: ["evidence"] });
    void client.invalidateQueries({ queryKey: ["report"] });
    void client.invalidateQueries({ queryKey: ["figure"] });
    void client.invalidateQueries({ queryKey: ["study"] });
    void client.invalidateQueries({ queryKey: ["lineage"] });
    void client.invalidateQueries({ queryKey: ["library"] });
  }, [client]);
}
