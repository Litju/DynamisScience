"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
import { scienceApi } from "@/lib/api";

export const keys = {
  study: (id: string) => ["study", id] as const,
  runs: ["runs"] as const,
  evidence: ["evidence"] as const,
  report: ["report"] as const,
  library: ["library"] as const,
  subjects: ["subjects"] as const,
};

export const useStudy = (id: string) => useQuery({ queryKey: keys.study(id), queryFn: () => scienceApi.study(id) });
export const useRuns = () => useQuery({ queryKey: keys.runs, queryFn: scienceApi.runs });
export const useEvidenceList = () => useQuery({ queryKey: keys.evidence, queryFn: scienceApi.evidence });
export const useReport = () => useQuery({ queryKey: keys.report, queryFn: scienceApi.report });
export const useLibrary = () => useQuery({ queryKey: keys.library, queryFn: scienceApi.library });
export const useSubjects = () => useQuery({ queryKey: keys.subjects, queryFn: scienceApi.subjects });
export const useFigure = (id: string | undefined) => useQuery({ queryKey: ["figure", id], queryFn: () => scienceApi.figure(id as string), enabled: Boolean(id) });
export const useRun = (id: string | undefined) => {
  const runs = useRuns();
  return { ...runs, data: runs.data?.find((run) => run.id === id) };
};

/** After an execution, promotion or citation, every view of the ledger refreshes together. */
export function useInvalidateScience() {
  const client = useQueryClient();
  return useCallback(() => {
    void client.invalidateQueries({ queryKey: keys.runs });
    void client.invalidateQueries({ queryKey: keys.evidence });
    void client.invalidateQueries({ queryKey: keys.report });
    void client.invalidateQueries({ queryKey: ["figure"] });
    void client.invalidateQueries({ queryKey: ["study"] });
    void client.invalidateQueries({ queryKey: ["lineage"] });
    void client.invalidateQueries({ queryKey: ["library"] });
  }, [client]);
}
