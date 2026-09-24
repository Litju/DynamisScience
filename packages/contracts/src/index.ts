export type QualityState = "VALID" | "WARNING" | "EXCLUDED" | "EXPLORATORY" | "FROZEN" | "SYNTHETIC";

export interface Study {
  id: string;
  title: string;
  research_question: string;
  state: "ACTIVE" | "COMPLETED" | "ARCHIVED";
  dataset_snapshot_id: string;
}

export interface ResearchQuestion {
  id: string;
  study_id: string;
  statement: string;
  estimand: string;
  population: string;
  exposure: string;
  outcomes: string[];
  time_horizon: string;
}

export interface Hypothesis {
  id: string;
  study_id: string;
  question_id: string;
  statement: string;
  direction: "increase" | "decrease" | "change" | "no_change";
  status: "PRIMARY" | "SECONDARY" | "EXPLORATORY";
}

export interface Protocol {
  id: string;
  study_id: string;
  name: string;
  frequency: string;
  status: "ACTIVE" | "FROZEN" | "RETIRED";
  visit_labels: string[];
}

export interface Subject {
  id: string;
  display_id: string;
  position: string;
  intervention_arm: "INTERVENTION" | "COMPARISON";
  body_mass_kg: number;
}

export interface MeasurementEvent {
  id: string;
  subject_id: string;
  event_type: string;
  week: number;
  quality_state: QualityState;
  source_id: string;
}

export interface Trial {
  id: string;
  subject_id: string;
  session_id: string;
  week: number;
  quality_state: QualityState;
  metric_values: Record<string, number>;
  trace_path: string;
}

export interface MetricDefinition {
  canonical_id: string;
  name: string;
  quantity: string;
  unit: string;
  method: string;
  protocol_id: string;
  algorithm: string;
  version: string;
  status: "ACTIVE" | "DEPRECATED";
  dependencies: string[];
  known_limitations: string[];
}

export interface DatasetSnapshot {
  id: string;
  seed: number;
  generator_version: string;
  schema_version: string;
  generated_at: string;
  row_counts: Record<string, number>;
  checksums: Record<string, string>;
}

export interface CohortDefinition {
  id: string;
  study_id: string;
  subject_ids: string[];
  exclusion_criteria: string[];
  snapshot_id: string;
  status: "DRAFT" | "FROZEN";
}

export interface AnalysisSpec {
  id: string;
  method_id: string;
  cohort_id: string;
  snapshot_id: string;
  outcome_metric_id: string;
  model_formula: string;
  parameters: Record<string, unknown>;
  status: "FROZEN" | "EXPLORATORY";
}

export interface AnalysisRun {
  id: string;
  analysis_spec_id: string;
  snapshot_id: string;
  cohort_id: string;
  method_id: string;
  status: "COMPLETED" | "FAILED" | "RUNNING";
  created_at: string;
  software_versions: Record<string, string>;
  result: Record<string, unknown>;
  diagnostics: Record<string, unknown>;
  output_artifact_ids: string[];
  reproducibility_key: string;
}

export interface EvidenceArtifact {
  id: string;
  title: string;
  metric_id: string;
  value: number | null;
  unit: string;
  estimate: number | null;
  uncertainty: number | null;
  sample_size: number;
  protocol_id: string;
  dataset_snapshot_id: string;
  analysis_run_id: string;
  quality: QualityState;
  provenance: Record<string, unknown>;
}

export interface FigureArtifact {
  id: string;
  title: string;
  evidence_ids: string[];
  dataset_snapshot_id: string;
  analysis_run_id: string;
  spec: Record<string, unknown>;
}

export interface ModelSpec {
  id: string;
  name: string;
  kind: string;
  version: string;
  inputs: string[];
  outputs: string[];
  status: "PROTOTYPE" | "IMPLEMENTED" | "ROADMAP";
  parameters: Record<string, number>;
}

export interface ModelRun {
  id: string;
  model_spec_id: string;
  dataset_snapshot_id: string;
  parameters: Record<string, number>;
  output: Record<string, unknown>;
  diagnostics: Record<string, unknown>;
}

export interface LineageEdge {
  id: string;
  source: string;
  target: string;
  relation: string;
  label: string;
}

export interface Report {
  id: string;
  title: string;
  study_id: string;
  status: "DRAFT" | "FROZEN";
  evidence_ids: string[];
  figure_ids: string[];
  sections: string[];
}
