import type {
  AthleteLongitudinal,
  CohortResolution,
  DatasetDetail,
  DatasetSummary,
  Evidence,
  ExplorePayload,
  ExploreReference,
  FigureArtifact,
  ForceTrialDetail,
  Investigation,
  Library,
  LineageGraph,
  MatchDetail,
  MatchTracking,
  ModelRun,
  ModelSpec,
  PoseStream,
  RealAdmission,
  RealQualificationRecord,
  RealQualityCheck,
  RealSource,
  RealSourceSummary,
  ReportPayload,
  Run,
  ScenarioResult,
  Snapshot,
  StudyDetail,
  StudySummary,
  Subject,
  Trial,
  WorkbenchBlock,
} from "./types";

export const API_URL = process.env.NEXT_PUBLIC_SCIENCE_API_URL ?? "http://localhost:8000";

export class ScienceError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly detail: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, { cache: "no-store", ...init });
  } catch {
    throw new ScienceError(`The local science service at ${API_URL} is not reachable.`, 0, "unreachable");
  }
  if (!response.ok) {
    let detail = "";
    try {
      const payload = (await response.json()) as { detail?: string };
      detail = typeof payload.detail === "string" ? payload.detail : "";
    } catch {
      detail = "";
    }
    throw new ScienceError(`Science service ${response.status}: ${path}${detail ? ` — ${detail}` : ""}`, response.status, detail);
  }
  return response.json() as Promise<T>;
}

const body = (method: string, value: unknown): RequestInit => ({
  method,
  headers: { "content-type": "application/json" },
  body: JSON.stringify(value),
});

export interface ExecuteRequest {
  study_id?: string;
  method_id: string;
  outcome_metric_id: string;
  excluded_subject_ids?: string[];
  parameters?: Record<string, unknown>;
}

const studyQuery = (studyId?: string) => (studyId ? `study_id=${encodeURIComponent(studyId)}` : "");

export const scienceApi = {
  studies: () => request<StudySummary[]>("/studies"),
  study: (id: string) => request<StudyDetail>(`/studies/${id}`),
  subjects: (studyId?: string) => request<Subject[]>(`/subjects${studyId ? `?${studyQuery(studyId)}` : ""}`),
  athlete: (subjectId: string, metricId: string, studyId?: string) => request<AthleteLongitudinal>(`/subjects/${subjectId}/longitudinal?metric_id=${metricId}${studyId ? `&${studyQuery(studyId)}` : ""}`),
  cohort: (excluded: string[], studyId?: string) => request<CohortResolution>("/cohorts/resolve", body("POST", { study_id: studyId, excluded_subject_ids: excluded })),
  explore: (metricId: string, excluded: string[], reference: ExploreReference, studyId?: string) =>
    request<ExplorePayload>(`/explore/longitudinal?metric_id=${metricId}&reference=${reference}&exclude=${encodeURIComponent(excluded.join(","))}${studyId ? `&${studyQuery(studyId)}` : ""}`),
  forceTrials: (subjectId: string) => request<Trial[]>(`/force/trials?subject_id=${subjectId}&limit=64`),
  forceTrial: (trialId: string) => request<ForceTrialDetail>(`/force/trials/${trialId}`),
  match: (matchId: string) => request<MatchDetail>(`/match/${matchId}`),
  tracking: (matchId: string) => request<MatchTracking>(`/match/${matchId}/tracking`),
  pose: (matchId: string, athleteId: string) => request<PoseStream>(`/match/${matchId}/pose?athlete_id=${athleteId}`),
  library: () => request<Library>("/library"),
  datasets: () => request<DatasetSummary[]>("/datasets"),
  dataset: (id: string) => request<DatasetDetail>(`/datasets/${id}`),
  runs: (studyId?: string) => request<Run[]>(`/runs${studyId ? `?${studyQuery(studyId)}` : ""}`),
  run: (id: string) => request<Run & { evidence: Evidence[] }>(`/runs/${id}`),
  execute: (payload: ExecuteRequest) => request<Run>("/analyses/execute", body("POST", payload)),
  evidence: (studyId?: string) => request<Evidence[]>(`/evidence${studyId ? `?${studyQuery(studyId)}` : ""}`),
  evidenceDetail: (id: string) => request<Evidence & { figures: FigureArtifact[]; source_runs: Run[] }>(`/evidence/${id}`),
  promote: (runId: string, studyId?: string) =>
    request<{ evidence_artifact: Evidence; figure_artifact: FigureArtifact | null; already_promoted: boolean }>("/evidence", body("POST", { run_id: runId, study_id: studyId })),
  figure: (id: string) => request<FigureArtifact>(`/figures/${id}`),
  report: (studyId?: string) => request<ReportPayload>(`/report${studyId ? `?${studyQuery(studyId)}` : ""}`),
  cite: (artifactId: string, studyId?: string) =>
    request<{ report_id: string; artifact_id: string; section: string; already_cited: boolean }>("/report/citations", body("POST", { artifact_id: artifactId, study_id: studyId })),
  uncite: (artifactId: string, studyId?: string) => request<{ removed: boolean }>(`/report/citations/${artifactId}${studyId ? `?${studyQuery(studyId)}` : ""}`, { method: "DELETE" }),
  lineage: (id: string, depth = 3) => request<LineageGraph>(`/lineage/${id}?scope=path&depth=${depth}`),
  investigation: (id: string) => request<Investigation>(`/investigations/${id}`),
  saveInvestigation: (id: string, blocks: WorkbenchBlock[], baseVersion: number) =>
    request<Investigation>(`/investigations/${id}`, body("PUT", { blocks, base_version: baseVersion })),
  trainingModel: () => request<{ spec: ModelSpec; run: ModelRun; snapshot: Snapshot }>("/models/training-response"),
  scenario: (futureLoad: number[]) => request<ScenarioResult>("/models/training-response/scenario", body("POST", { future_load_au: futureLoad })),
  admissionSources: () => request<unknown[]>("/admission/sources"),
  admissionRecords: () => request<unknown[]>("/admission/records"),
  admissionSnapshots: () => request<unknown[]>("/admission/snapshots"),
  qualification: () => request<unknown[]>("/qualification"),
  realSources: () => request<RealSourceSummary[]>("/real/sources"),
  realSource: (id: string) =>
    request<{ source: RealSource; admission: RealAdmission | null; quality: { checks: RealQualityCheck[] } | null }>(`/real/sources/${id}`),
  realAdmit: (sourceId: string) =>
    request<{ already_admitted: boolean; snapshot: Snapshot | null; admission: RealAdmission | null }>("/real/admit", body("POST", { source_id: sourceId })),
  realSnapshots: () => request<Snapshot[]>("/real/snapshots"),
  realQualification: () => request<RealQualificationRecord[]>("/real/qualification"),
  realQualificationRun: () => request<RealQualificationRecord[]>("/real/qualification/run", body("POST", {})),
};
