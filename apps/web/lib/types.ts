export type Dict = Record<string, unknown>;

export type Arm = "INTERVENTION" | "COMPARISON";

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

export interface StudySummary extends Study {
  plan_status: string;
  run_count: number;
  evidence_count: number;
  last_run_at: string | null;
  investigation_ids: string[];
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
  study_id?: string;
  name: string;
  description?: string;
  method?: string;
  frequency: string;
  status: string;
  duration_weeks?: number;
  visit_labels?: string[];
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
  primary_estimand?: string;
  status: string;
  deviates_from?: string[];
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
  primary_estimand: string;
  planned_reliability: string;
  post_plan_rule: string;
  immutability_rule: string;
}

export interface CohortDefinition {
  id: string;
  study_id: string;
  name: string;
  description: string;
  subject_ids: string[];
  excluded_subject_ids?: string[];
  exclusion_criteria: string[];
  snapshot_id: string;
  status: string;
  derived_from?: string;
}

export interface StudyGroup {
  label: string;
  arm: Arm;
  block_weeks: number[];
  description: string;
}

export interface MissingSlot {
  subject_id: string;
  display_id: string;
  week: number;
  trial_number: number;
  reason: string;
}

export interface ExcludedTrial {
  trial_id: string;
  subject_id: string;
  display_id: string;
  week: number;
  trial_number: number;
  reason: string;
}

export interface DataHealth {
  valid_measurements: number;
  excluded_measurements: number;
  missing_observations: number;
  expected_slots: number;
  missing_slots: MissingSlot[];
  excluded_trials: ExcludedTrial[];
  complete_records: number;
  total_records: number;
  provenance_completeness: number;
  total_subjects: number;
}

export interface StudyDetail {
  study: Study;
  question: ResearchQuestion;
  hypotheses: Hypothesis[];
  groups: Record<string, StudyGroup>;
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
  investigations: { id: string; title: string; status: string; block_count: number }[];
}

export interface Subject {
  subject_id: string;
  display_id: string;
  position: string;
  age: number;
  body_mass_kg: number;
  height_cm: number;
  training_age_years: number;
  intervention_arm: Arm;
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
  usages?: string[];
}

export interface MethodEntry {
  id: string;
  name: string;
  version: string;
  status: string;
  algorithm?: string;
  estimator: string;
  fallback?: string;
  estimand?: string;
  requirements?: string[];
  outputs?: string[];
  known_limitations?: string[];
  runs?: string[];
  specs?: string[];
}

export interface AlgorithmEntry {
  id: string;
  name: string;
  version: string;
  status: string;
  implementation: string;
  description: string;
}

export interface ModelEntry {
  id: string;
  name: string;
  version?: string;
  status: string;
  kind: string;
  description: string;
  inputs?: string[];
  known_limitations?: string[];
}

export interface Library {
  metrics: Metric[];
  protocols: Protocol[];
  algorithms: AlgorithmEntry[];
  methods: MethodEntry[];
  models: ModelEntry[];
  model_spec: ModelSpec;
}

export interface Contrast {
  estimate: number;
  std_error: number;
  ci_low: number;
  ci_high: number;
  unit: string;
  contrast: string;
  interpretation?: string;
}

export interface LongitudinalResult {
  method: string;
  formula: string;
  outcome: string;
  unit: string;
  reference_week: number;
  contrast_week: number;
  n_observations: number;
  n_subjects: number;
  coefficients: Record<string, { estimate: number; std_error: number; ci_low: number; ci_high: number }>;
  model_status: string;
  estimator: string;
  estimator_attempts?: string[];
  convergence_note: string;
  converged: boolean;
  log_likelihood: number | null;
  contrasts: Record<string, Contrast>;
  primary_contrast_id: string;
  effect_size: number | null;
  effect_size_basis: string;
}

export interface LongitudinalDiagnostics {
  estimator: string;
  model_status: string;
  converged: boolean;
  n_observations: number;
  n_subjects: number;
  residual_summary: { rmse: number; mean_residual: number; max_abs_residual: number };
  week_centering: number;
  quality_note: string;
  estimator_attempts: string[];
  log_likelihood: number | null;
  residual_by_week: { week: number; mean_residual: number }[];
  residual_qq: { theoretical: number; observed: number }[];
  residual_by_arm: Record<string, { n: number; sd: number | null; mean: number | null }>;
  sample_context: {
    valid_first_trials_used: number;
    excluded_trials_in_cohort: number;
    excluded_trial_ids: string[];
    valid_repeat_trials_not_modelled: number;
    observations_per_subject_min: number;
    observations_per_subject_max: number;
    weeks_observed: number[];
  };
  baseline_balance: Contrast;
  assumptions: string[];
  limitations: string[];
}

export interface Run {
  id: string;
  analysis_spec_id: string;
  study_id: string;
  snapshot_id: string;
  cohort_id: string;
  method_id: string;
  outcome_metric_id?: string;
  status: string;
  plan_alignment?: "PLANNED" | "EXPLORATORY";
  created_at: string;
  duration_ms: number;
  software_versions: Record<string, string>;
  seed?: number;
  parameters?: Record<string, unknown>;
  result: Dict;
  diagnostics: Dict;
  output_artifact_ids: string[];
  reproducibility_key: string;
  result_digest?: string;
  reproduces?: string[];
  evidence_ids?: string[];
  execution?: { analysis_spec: AnalysisSpec; cohort: CohortDefinition };
}

export interface EvidenceInterval {
  low: number | null;
  high: number | null;
  level: number;
  kind: string;
}

export interface Evidence {
  id: string;
  title: string;
  kind: "EFFECT" | "RELIABILITY" | "CHANGE" | string;
  metric_id: string;
  value: number | null;
  unit: string;
  estimate: number | null;
  uncertainty: number | null;
  uncertainty_label: string | null;
  interval?: EvidenceInterval | null;
  effect_size: number | null;
  contrast_id?: string | null;
  population: string;
  sample_size: number;
  protocol_id: string;
  dataset_snapshot_id: string;
  analysis_run_id: string;
  analysis_spec_id?: string;
  cohort_id?: string;
  diagnostics: Dict;
  quality: string;
  evidence_class?: "CONFIRMATORY" | "PLANNED" | "EXPLORATORY";
  reproducibility_key?: string;
  result_digest?: string;
  version?: number;
  state?: "CURRENT" | "SUPERSEDED";
  reproduces?: string[];
  reproduced_by?: string[];
  superseded_by?: string[];
  cited_by_report?: boolean;
  created_at?: string;
  provenance: Dict;
  interpretation: string;
}

export interface FigureSeriesPoint {
  arm: Arm;
  week: number;
  n: number;
  mean: number | null;
  sd: number | null;
  ci_low: number | null;
  ci_high: number | null;
}

export interface FigureData {
  kind: string;
  unit: string;
  metric?: { label: string; unit: string; id: string; metric_id: string };
  series?: FigureSeriesPoint[];
  values?: number[];
  points?: { subject_id: string; baseline: number; change: number }[];
  typical_error?: number;
}

export interface FigureArtifact {
  id: string;
  title: string;
  kind: string;
  evidence_ids: string[];
  dataset_snapshot_id: string;
  analysis_run_id: string;
  spec: Dict;
  data?: FigureData;
  cited_by_report?: boolean;
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
  intervention_arm: Arm;
  body_mass_kg: number;
  body_weight_n: number;
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
  trace_available: boolean;
}

export interface TracePoint {
  trial_id: string;
  time_s: number;
  force_n: number;
  body_weight_n: number;
  phase: string;
}

export interface ForceTrialDetail {
  trial: Trial;
  subject: Subject;
  boundaries: Record<string, number>;
  trace: TracePoint[];
  trace_available: boolean;
  method: { algorithm: string; algorithm_version: string; sample_rate_hz: number; integration: string; phase_detection: string; protocol_id: string; metrics: Metric[] };
  provenance: { snapshot_id: string; seed: number; generator_version: string; source: string; trials_checksum: string; traces_checksum: string };
}

export interface WeekTrial {
  trial_id: string;
  trial_number: number;
  quality_state: string;
  exclusion_reason: string;
  value: number;
  trace_available: boolean;
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
  load: Dict | null;
  wellness: Dict | null;
  trials: WeekTrial[];
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
  limitations: string;
}

export interface AthleteLongitudinal {
  subject: Subject;
  metric: { column: string; label: string; unit: string; id: string };
  observations: LongitudinalObservation[];
  typical_error: number;
  individual: IndividualChange;
  provenance: Dict;
}

export type ExploreReference = "RAW" | "CHANGE" | "PERCENT";

export interface ExploreSummaryRow extends FigureSeriesPoint {
  n_athletes: number;
  missing_athletes: number;
  excluded_trials: number;
  missing_trials: number;
}

export interface ExploreAthlete {
  subject_id: string;
  display_id: string;
  intervention_arm: Arm;
  raw: (number | null)[];
  values: (number | null)[];
  n_valid: number[];
  n_excluded: number[];
  n_missing: number[];
  baseline: number | null;
}

export interface ExploreContextRow {
  week: number;
  arm: Arm;
  training_impulse_au: number;
  external_load_au: number;
  match_minutes: number;
  session_rpe: number;
}

export interface ExplorePayload {
  metric: { column: string; label: string; unit: string; id: string; metric_id: string };
  unit: string;
  reference: ExploreReference;
  reference_label: string;
  cohort: { id: string; status: string; n: number; excluded_subject_ids: string[] };
  summary: ExploreSummaryRow[];
  athletes: ExploreAthlete[];
  context: ExploreContextRow[];
  annotations: {
    intervention_block: { start_week: number; end_week: number; source: string };
    load_peaks: { week: number; training_impulse_au: number; z: number }[];
    load_peak_rule: string;
  };
  method: { unit_of_analysis: string; interval: string; engine: string; note: string };
  provenance: Dict;
}

export interface CohortAthlete {
  subject_id: string;
  display_id: string;
  position: string;
  intervention_arm: Arm;
  included: boolean;
  valid_trials: number;
  excluded_trials: number;
  missing_trials: number;
}

export interface CohortResolution {
  cohort: CohortDefinition;
  n: number;
  arm_counts: Record<Arm, number>;
  inclusion_criteria: string[];
  exclusion_criteria: string[];
  filters: { excluded_subject_ids: string[] };
  trial_quality: {
    valid: number;
    excluded: number;
    missing: number;
    expected: number;
    missing_by_arm: Record<string, number>;
    excluded_trials: ExcludedTrial[];
    missing_slots: MissingSlot[];
  };
  n_trials: number;
  athletes: CohortAthlete[];
  snapshot_id: string;
}

export interface DatasetTable {
  name: string;
  file: string;
  description: string;
  rows: number;
  manifest_rows: number;
  checksum_sha256: string;
  sample_rate_hz: number | null;
  columns: { name: string; dtype: string; null_count: number }[];
}

export interface DatasetSummary {
  id: string;
  label: string;
  seed: number;
  generator_version: string;
  schema_version: string;
  generated_at: string;
  table_count: number;
  row_total: number;
  synthetic: boolean;
  used_by_studies: string[];
}

export interface DatasetDetail {
  snapshot: Snapshot;
  tables: DatasetTable[];
  quality: DataHealth;
  disclaimer: string;
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
  provenance: Dict;
}

export interface MatchTracking {
  match_id: string;
  sample_rate_hz: number;
  frame_count: number;
  duration_s: number;
  frames: MatchFrame[];
  events: MatchEvent[];
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
    observed_weeks: number[];
    observed_performance: number[];
    modelled_performance: number[];
    residuals: number[];
    fit_rmse_standardized: number;
    fit_rmse_outcome_units: number;
    unit: string;
    weekly_load_au: number[];
    transform: Record<string, number | string>;
  };
  diagnostics: { fit_status: string; observed_weeks: number; model_class: string; search_grid: Record<string, number[]>; limitations: string[] };
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

export interface ScenarioState {
  week: number;
  load_au: number;
  segment: "OBSERVED_LOAD" | "SCENARIO";
  fitness: number;
  fatigue: number;
  modelled_performance: number;
}

export interface ScenarioResult {
  scenario_id: string;
  model_run_id: string;
  model_spec_id: string;
  parameters: Record<string, number>;
  unit: string;
  history_weeks: number;
  scenario_weeks: number;
  states: ScenarioState[];
  summary: {
    end_of_history_performance: number;
    scenario_final_performance: number | null;
    scenario_peak_performance: number | null;
    scenario_peak_week: number | null;
    scenario_mean_load_au: number | null;
  };
  limitations: string[];
  persisted: boolean;
}

export interface LineageNode {
  id: string;
  kind: string;
  label: string;
  metadata: string;
  detail?: Dict;
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
  scope?: string;
  ancestor_ids?: string[];
  descendant_ids?: string[];
}

export interface ReportCitation {
  artifact_id: string;
  section: string;
  added_at: string;
}

export interface ReportPayload {
  id: string;
  title: string;
  study_id: string;
  status: string;
  evidence_ids: string[];
  figure_ids: string[];
  sections: string[];
  citations: ReportCitation[];
  provenance_note: string;
  created_at: string;
  updated_at?: string;
  evidence: Evidence[];
  figures: FigureArtifact[];
  runs: Run[];
  snapshot: Snapshot;
  study: Study;
  question: ResearchQuestion;
  hypotheses: Hypothesis[];
  plan: StudyPlan;
  cohort: CohortDefinition;
  groups: Record<string, StudyGroup>;
  data_health: DataHealth;
}

export type BlockType =
  | "question"
  | "dataset"
  | "cohort"
  | "table"
  | "explore"
  | "force_trial"
  | "match_event"
  | "analysis"
  | "diagnostics"
  | "evidence"
  | "model"
  | "figure"
  | "interpretation"
  | "report_section";

export interface WorkbenchBlock {
  id: string;
  type: BlockType;
  title: string;
  state: Dict;
  collapsed: boolean;
}

export interface Investigation {
  id: string;
  study_id: string;
  title: string;
  status: string;
  version: number;
  created_at: string;
  updated_at: string;
  blocks: WorkbenchBlock[];
}
