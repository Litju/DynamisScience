import type {
  Evidence,
  FigureArtifact,
  LineageGraph,
  LongitudinalPayload,
  MatchDetail,
  MatchEvent,
  MatchFrame,
  ModelRun,
  ModelSpec,
  ModelState,
  OverviewData,
  PoseStream,
  Registry,
  ReportPayload,
  Run,
  Snapshot,
  Study,
  StudyDetail,
  Subject,
  TracePoint,
  Trial,
} from "./types";

const API_URL = process.env.NEXT_PUBLIC_SCIENCE_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, { cache: "no-store", ...init });
  if (!response.ok) {
    let detail = "";
    try {
      const payload = (await response.json()) as { detail?: string };
      detail = payload.detail ? ` — ${payload.detail}` : "";
    } catch {
      detail = "";
    }
    throw new Error(`Science service ${response.status}: ${path}${detail}`);
  }
  return response.json() as Promise<T>;
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify(body),
});

export const scienceApi = {
  overview: () => request<OverviewData>("/overview"),
  studies: () => request<Study[]>("/studies"),
  study: (id: string) => request<StudyDetail>(`/studies/${id}`),
  subjects: () => request<Subject[]>("/subjects"),
  longitudinal: (subjectId: string, metricId = "MET-CMJ-IMPULSE") =>
    request<LongitudinalPayload>(`/subjects/${subjectId}/longitudinal?metric_id=${metricId}`),
  forceTrials: (query = "") => request<Trial[]>(`/force/trials${query}`),
  forceTrial: (trialId: string) =>
    request<{
      trial: Trial;
      boundaries: Record<string, number>;
      trace: TracePoint[];
      trace_available: boolean;
      method: Record<string, unknown>;
    }>(`/force/trials/${trialId}`),
  match: (matchId: string) => request<MatchDetail>(`/match/${matchId}`),
  tracking: (matchId: string) =>
    request<{ match_id: string; sample_rate_hz: number; frame_count: number; duration_s: number; frames: MatchFrame[]; events: MatchEvent[] }>(
      `/match/${matchId}/tracking`,
    ),
  pose: (matchId: string, athleteId: string) => request<PoseStream>(`/match/${matchId}/pose?athlete_id=${athleteId}`),
  registry: () => request<Registry>("/registry"),
  runs: () => request<Run[]>("/runs"),
  run: (id: string) => request<Run & { lineage: LineageGraph; evidence: Evidence[] }>(`/runs/${id}`),
  evidence: () => request<Evidence[]>("/evidence"),
  evidenceDetail: (id: string) =>
    request<Evidence & { lineage: LineageGraph; source_runs: Run[]; figures: FigureArtifact[]; cited_by_report: boolean }>(
      `/evidence/${id}`,
    ),
  figures: () => request<FigureArtifact[]>("/figures"),
  report: () => request<ReportPayload>("/report"),
  lineage: (id: string) => request<LineageGraph>(`/lineage/${id}`),
  trainingModel: () =>
    request<{ spec: ModelSpec; run: ModelRun; snapshot: Snapshot; load_series: number[] }>("/models/training-response"),
  simulate: (loadValues: number[], parameters: Record<string, number>) =>
    request<{ states: ModelState[]; parameters: Record<string, number>; interpretation: string }>(
      "/models/training-response/simulate",
      json({ load_values: loadValues, parameters }),
    ),
  execute: (body: { method_id: string; outcome_metric_id: string; subject_ids?: string[]; parameters?: Record<string, unknown> }) =>
    request<Run & { evidence_artifact: Evidence; figure_artifact: FigureArtifact }>("/analyses/execute", json(body)),
};
