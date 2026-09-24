export type ViewKey =
  | "overview"
  | "studies"
  | "monitor"
  | "forcelab"
  | "matchlab"
  | "analyses"
  | "models"
  | "runs"
  | "registry"
  | "reports"
  | "lineage";

export type QualityState = "VALID" | "WARNING" | "EXCLUDED" | "EXPLORATORY" | "FROZEN" | "SYNTHETIC";

export interface Snapshot {
  id: string;
  label: string;
  seed: number;
  generator_version: string;
  schema_version: string;
  generated_at: string;
  row_counts: Record<string, number>;
  checksums: Record<string, string>;
  sample_rates: Record<string, number>;
  subjects: { total: number; weeks: number; positions: string[] };
  pose_athletes: string[];
  missing_observations: number | null;
  provenance: Record<string, unknown>;
}

export interface Study {
  id: string;
  title: string;
  short_title: string;
  state: string;
  research_question: string;
  design: string;
  intervention: string;
  primary_outcomes: string[];
  secondary_outcomes: string[];
  dataset_snapshot_id: string;
  participant_count: number;
  start_week: number;
  end_week: number;
  protocol_ids: string[];
  analysis_spec_ids: string[];
}

export interface ResearchQuestion {
  id: string;
  statement: string;
  estimand: string;
  population: string;
  exposure: string;
  outcomes: string[];
  time_horizon: string;
}

export interface Hypothesis {
  id: string;
  question_id: string;
  statement: string;
  direction: string;
  status: string;
  rationale: string;
}

export interface Protocol {
  id: string;
  study_id: string;
  name: string;
  description: string;
  frequency: string;
  status: string;
  duration_weeks: number;
  visit_labels: string[];
}

export interface AnalysisSpec {
  id: string;
  study_id: string;
  name: string;
  method_id: string;
  method_version: string;
  cohort_id: string;
  snapshot_id: string;
  outcome_metric_id: string;
  model_formula: string;
  parameters: Record<string, unknown>;
  planned_contrasts: string[];
  status: string;
}

export interface StudyPlan {
  id: string;
  status: string;
  frozen_before_inspection: boolean;
  primary_outcomes: string[];
  secondary_outcomes: string[];
  exclusion_criteria: string[];
  planned_models: string[];
  planned_contrasts: string[];
  immutability_rule: string;
}

export interface CohortDefinition {
  id: string;
  study_id: string;
  name: string;
  description: string;
  subject_ids: string[];
  exclusion_criteria: string[];
  snapshot_id: string;
  status: string;
}

export interface DataHealth {
  valid_measurements: number;
  excluded_measurements: number;
  missing_observations: number;
  expected_slots: number;
  missing_slots: { subject_id: string; display_id: string; week: number; trial_number: number; reason: string }[];
  complete_records: number;
  total_records: number;
  provenance_completeness: number;
  total_subjects: number;
}

export interface Subject {
  subject_id: string;
  display_id: string;
  position: string;
  age: number;
  body_mass_kg: number;
  height_cm: number;
  training_age_years: number;
  intervention_arm: "INTERVENTION" | "COMPARISON";
  impulse_factor: number;
  jump_factor: number;
  response_factor: number;
  status: string;
}

export interface Metric {
  id: string;
  canonical_id: string;
  name: string;
  quantity: string;
  unit: string;
  method: string;
  protocol_id: string;
  algorithm: string;
  version: string;
  status: string;
  dependencies: string[];
  known_limitations: string[];
  usage_count: number;
}

export interface RegistryEntry {
  id: string;
  name: string;
  status?: string;
  version?: string;
  description?: string;
  method?: string;
  frequency?: string;
  estimator?: string;
  fallback?: string;
  implementation?: string;
  canonical_id?: string;
  quantity?: string;
  unit?: string;
  protocol_id?: string;
  algorithm?: string;
  dependencies?: string[];
  known_limitations?: string[];
  usage_count?: number;
}

export interface Registry {
  metrics: Metric[];
  protocols: RegistryEntry[];
  algorithms: RegistryEntry[];
  methods: RegistryEntry[];
  models: RegistryEntry[];
}

export interface Run {
  id: string;
  analysis_spec_id: string;
  study_id: string;
  snapshot_id: string;
  cohort_id: string;
  method_id: string;
  status: string;
  created_at: string;
  duration_ms: number;
  software_versions: Record<string, string>;
  seed?: number;
  result: Record<string, unknown>;
  diagnostics: Record<string, unknown>;
  output_artifact_ids: string[];
  reproducibility_key: string;
  execution?: {
    analysis_spec: AnalysisSpec;
    cohort: CohortDefinition;
  };
}

export interface Evidence {
  id: string;
  title: string;
  kind: string;
  metric_id: string;
  value: number | null;
  unit: string;
  estimate: number | null;
  uncertainty: number | null;
  uncertainty_label: string | null;
  effect_size: number | null;
  population: string;
  sample_size: number;
  protocol_id: string;
  dataset_snapshot_id: string;
  analysis_run_id: string;
  diagnostics: Record<string, unknown>;
  quality: string;
  provenance: Record<string, unknown>;
  interpretation: string;
}

export interface FigureArtifact {
  id: string;
  title: string;
  kind: string;
  evidence_ids: string[];
  dataset_snapshot_id: string;
  analysis_run_id: string;
  spec: Record<string, unknown>;
}

export interface Trial {
  trial_id: string;
  subject_id: string;
  display_id: string;
  session_id: string;
  week: number;
  trial_number: number;
  quality_state: "VALID" | "WARNING" | "EXCLUDED";
  exclusion_reason: string;
  intervention_arm: string;
  body_mass_kg: number;
  jump_height_cm: number;
  concentric_impulse_n_s_kg: number;
  eccentric_braking_impulse_n_s_kg: number;
  eccentric_braking_duration_s: number;
  countermovement_depth_cm: number;
  peak_force_n: number;
  peak_power_w_kg: number;
  rsi_mod: number;
  movement_onset_s: number;
  takeoff_s: number;
  landing_s: number;
  phase_boundaries: string;
  trace_path: string;
}

export interface TracePoint {
  trial_id: string;
  time_s: number;
  force_n: number;
  body_weight_n: number;
  phase: string;
}

export interface IndividualChange {
  method: string;
  baseline_weeks: number[];
  post_weeks: number[];
  baseline_mean: number | null;
  post_mean: number | null;
  change: number | null;
  percent_change: number | null;
  standardized_change: number | null;
  exceeds_typical_error: boolean | null;
  typical_error: number;
  cohort_change_sd: number;
  n_subjects: number;
}

export interface LongitudinalObservation {
  week: number;
  value: number | null;
  n_trials: number;
  expected_trials: number;
  missing_trials: number;
  excluded_trials: number;
  quality_state: "VALID" | "WARNING" | "MISSING";
  rolling_mean: number | null;
  rolling_sd: number | null;
  z_score: number | null;
  percent_change_from_baseline: number | null;
  coefficient_of_variation: number | null;
  typical_error: number | null;
  phase: string;
  load: Record<string, unknown> | null;
  wellness: Record<string, unknown> | null;
}

export interface LongitudinalPayload {
  subject: Subject;
  metric: { column: string; label: string; unit: string; id: string };
  observations: LongitudinalObservation[];
  typical_error: number;
  individual: IndividualChange;
  provenance: Record<string, unknown>;
}

export interface MatchEntity {
  player_id: string;
  team: string;
  x_m: number;
  y_m: number;
  vx_m_s: number;
  vy_m_s: number;
}

export interface MatchFrame {
  frame: number;
  time_s: number;
  entities: MatchEntity[];
}

export interface MatchEvent {
  event_id: string;
  event_type: string;
  label: string;
  start_s: number;
  end_s: number;
  athlete_id: string;
}

export interface MatchDetail {
  match_id: string;
  sample_rate_hz: number;
  frame_count: number;
  duration_s: number;
  player_count: number;
  pose_athletes: string[];
  pose_sample_rate_hz: number;
  events: MatchEvent[];
  provenance: Record<string, unknown>;
}

export interface PoseJoint {
  joint: string;
  x_m: number;
  y_m: number;
  z_m: number;
  confidence: number;
}

export interface PoseFrame {
  frame: number;
  time_s: number;
  athlete_id: string;
  joints: PoseJoint[];
}

export interface PoseStream {
  match_id: string;
  athlete_id: string | null;
  available: boolean;
  pose_athletes: string[];
  sample_rate_hz: number;
  frame_count: number;
  frames: PoseFrame[];
  topology: string[];
  message?: string;
}

export interface ModelState {
  week: number;
  load: number;
  fitness: number;
  fatigue: number;
  performance_state: number;
}

export interface ModelRun {
  id: string;
  model_spec_id: string;
  dataset_snapshot_id: string;
  parameters: Record<string, number>;
  output: {
    states: ModelState[];
    parameters: Record<string, number>;
    interpretation: string;
    observed_weeks: number[];
    observed_performance: number[];
    modelled_performance: number[];
    residuals: number[];
    fit_rmse_standardized: number;
    fit_rmse_outcome_units: number;
  };
  diagnostics: Record<string, unknown>;
  created_at: string;
}

export interface ModelSpec {
  id: string;
  name: string;
  kind: string;
  version: string;
  description: string;
  inputs: string[];
  outputs: string[];
  status: string;
  parameters: Record<string, number>;
  roadmap: { capability: string; status: string }[];
}

export interface LineageNode {
  id: string;
  kind: string;
  label: string;
  metadata: string;
  detail?: Record<string, unknown>;
}

export interface LineageEdge {
  id: string;
  source: string;
  target: string;
  relation: string;
  label: string;
}

export interface LineageGraph {
  artifact_id: string;
  focus: LineageNode;
  nodes: LineageNode[];
  edges: LineageEdge[];
}

export interface ReportPayload {
  id: string;
  title: string;
  study_id: string;
  status: string;
  evidence_ids: string[];
  figure_ids: string[];
  sections: string[];
  provenance_note: string;
  created_at: string;
  evidence: Evidence[];
  figures: FigureArtifact[];
  snapshot: Snapshot;
  study: Study;
  data_health: DataHealth;
  longitudinal_signal: { week: number; arm: string; mean: number; sd: number; n: number }[];
}

export interface OverviewData {
  snapshot: Snapshot;
  study: Study;
  research_question: ResearchQuestion;
  groups: Record<string, { label: string; arm: string; block_weeks: number[]; description: string }>;
  plan: StudyPlan;
  recent_analyses: Run[];
  evidence_artifacts: Evidence[];
  data_health: DataHealth;
  longitudinal_signal: { week: number; arm: string; mean: number; sd: number; n: number }[];
  registries: Registry;
  figures: FigureArtifact[];
}

export interface StudyDetail {
  study: Study;
  question: ResearchQuestion;
  hypotheses: Hypothesis[];
  groups: Record<string, { label: string; arm: string; block_weeks: number[]; description: string }>;
  cohort: CohortDefinition;
  protocols: Protocol[];
  analysis_specs: AnalysisSpec[];
  plan: StudyPlan;
  snapshot: Snapshot;
  runs: Run[];
  evidence: Evidence[];
  figures: FigureArtifact[];
  arm_counts: Record<string, number>;
  position_counts: Record<string, number>;
  data_health: DataHealth;
}
