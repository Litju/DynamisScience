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

export interface Subject {
  subject_id: string;
  display_id: string;
  position: string;
  age: number;
  body_mass_kg: number;
  height_cm: number;
  training_age_years: number;
  intervention_arm: "INTERVENTION" | "COMPARISON";
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

export interface LongitudinalObservation {
  week: number;
  value: number | null;
  n_trials: number;
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

export interface Registry {
  metrics: Metric[];
  protocols: Record<string, unknown>[];
  algorithms: Record<string, unknown>[];
  methods: Record<string, unknown>[];
  models: Record<string, unknown>[];
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

export interface PoseJoint {
  joint: string;
  x_m: number;
  y_m: number;
  z_m: number;
  confidence: number;
}

export interface ModelState {
  week: number;
  load: number;
  fitness: number;
  fatigue: number;
  performance_state: number;
}
