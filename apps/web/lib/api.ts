import type {
  Evidence,
  MatchEvent,
  MatchFrame,
  ModelState,
  Registry,
  Run,
  Snapshot,
  Study,
  Subject,
  Trial,
  TracePoint,
  LongitudinalObservation,
} from "./types";

const API_URL = process.env.NEXT_PUBLIC_SCIENCE_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, { cache: "no-store", ...init });
  if (!response.ok) {
    throw new Error(`Science service ${response.status}: ${path}`);
  }
  return response.json() as Promise<T>;
}

export const scienceApi = {
  overview: () => request<Record<string, unknown>>("/overview"),
  studies: () => request<Study[]>("/studies"),
  study: (id: string) => request<Record<string, unknown>>(`/studies/${id}`),
  subjects: () => request<Subject[]>("/subjects"),
  longitudinal: (subjectId: string, metricId = "MET-CMJ-IMPULSE") => request<{ subject: Subject; metric: { column: string; label: string; unit: string; id: string }; observations: LongitudinalObservation[]; typical_error: number; provenance: Record<string, unknown> }>(`/subjects/${subjectId}/longitudinal?metric_id=${metricId}`),
  forceTrials: (query = "") => request<Trial[]>(`/force/trials${query}`),
  forceTrial: (trialId: string) => request<{ trial: Trial; boundaries: Record<string, number>; trace: TracePoint[]; trace_available: boolean; method: Record<string, string> }>(`/force/trials/${trialId}`),
  tracking: (matchId: string) => request<{ match_id: string; sample_rate_hz: number; frame_count: number; duration_s: number; frames: MatchFrame[]; events: MatchEvent[] }>(`/match/${matchId}/tracking`),
  pose: (matchId: string, athleteId: string) => request<{ match_id: string; sample_rate_hz: number; frame_count: number; frames: { frame: number; time_s: number; athlete_id: string; joints: { joint: string; x_m: number; y_m: number; z_m: number; confidence: number }[] }[]; topology: string[] }>(`/match/${matchId}/pose?athlete_id=${athleteId}`),
  registry: () => request<Registry>("/registry"),
  runs: () => request<Run[]>("/runs"),
  run: (id: string) => request<Run & { lineage: Record<string, unknown>[]; evidence: Evidence[] }>(`/runs/${id}`),
  evidence: () => request<Evidence[]>("/evidence"),
  evidenceDetail: (id: string) => request<Evidence & { lineage: Record<string, unknown>[]; source_runs: Run[] }>(`/evidence/${id}`),
  lineage: (id: string) => request<{ artifact_id: string; nodes: Record<string, unknown>[]; edges: Record<string, unknown>[] }>(`/lineage/${id}`),
  trainingModel: () => request<{ spec: Record<string, unknown>; run: { output: { states: ModelState[]; parameters: Record<string, number> }; parameters: Record<string, number>; diagnostics: Record<string, unknown> }; snapshot: Snapshot }>("/models/training-response"),
  simulate: (loadValues: number[], parameters: Record<string, number>) => request<{ states: ModelState[]; parameters: Record<string, number>; interpretation: string }>("/models/training-response/simulate", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ load_values: loadValues, parameters }) }),
  execute: (body: { method_id: string; outcome_metric_id: string; subject_ids?: string[]; parameters?: Record<string, unknown> }) => request<Run>("/analyses/execute", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) }),
};
