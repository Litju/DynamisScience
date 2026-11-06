import { API_URL, ScienceError } from "@/lib/api";
import type {
  AthleteDetail,
  AthleteNote,
  AthleteSummary,
  ContextPayload,
  ForceTrialDetail,
  MovementPayload,
  PerformanceReport,
  PlanPayload,
  SessionLogRecord,
  TestPayload,
  TodayPayload,
  UnitsPayload,
} from "./types";

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

const json = (method: string, value: unknown): RequestInit => ({
  method,
  headers: { "content-type": "application/json" },
  body: JSON.stringify(value),
});

export const performanceApi = {
  context: () => request<ContextPayload>("/performance/context"),
  today: () => request<TodayPayload>("/performance/today"),
  athletes: () => request<AthleteSummary[]>("/performance/athletes"),
  squadWeeks: () => request<import("./types").SquadWeeksPayload>("/performance/squad-weeks"),
  athlete: (id: string) => request<AthleteDetail>(`/performance/athletes/${encodeURIComponent(id)}`),
  addNote: (id: string, text: string, role: string) =>
    request<AthleteNote>(`/performance/athletes/${encodeURIComponent(id)}/notes`, json("POST", { text, author_role: role })),
  load: () => request<PlanPayload>("/performance/load"),
  plan: () => request<PlanPayload>("/performance/plan"),
  updatePlan: (payload: {
    week: number;
    focus: string;
    testing_window: string;
    sessions: PlanPayload["microcycles"][number]["sessions"];
    publish: boolean;
    actor: string;
  }) => request<PlanPayload>("/performance/plan", json("PUT", payload)),
  publishPlan: () => request<PlanPayload>("/performance/plan/publish", json("POST", {})),
  logSession: (payload: {
    date: string;
    session_type: string;
    duration_min: number;
    session_rpe: number;
    attendance: number;
    notes: string;
    author_role: string;
  }) => request<SessionLogRecord>("/performance/sessions", json("POST", payload)),
  tests: () => request<TestPayload>("/performance/tests"),
  runReliability: () => request<{ id: string; created_at: string; status: string }>("/performance/tests/reliability", json("POST", {})),
  movement: () => request<MovementPayload>("/performance/movement"),
  units: () => request<UnitsPayload>("/performance/units"),
  research: () => request<{
    study: TodayPayload["study"];
    evidence: Record<string, unknown>[];
    report: { id: string; title: string; status: string; study_id: string };
    synthetic: boolean;
    as_of: string;
  }>("/performance/research"),
  forceTrial: (id: string) => request<ForceTrialDetail>(`/force/trials/${encodeURIComponent(id)}`),
  reports: (audience?: string) => request<PerformanceReport[]>(`/performance/reports${audience ? `?audience=${audience}` : ""}`),
  createReport: (payload: { audience: PerformanceReport["audience"]; athlete_id?: string; role: string; freeze?: boolean }) =>
    request<PerformanceReport>("/performance/reports", json("POST", payload)),
  freezeReport: (id: string) => request<PerformanceReport>(`/performance/reports/${id}/freeze`, json("POST", {})),
  reportExportUrl: (id: string) => `${API_URL}/performance/reports/${id}/export`,
};
