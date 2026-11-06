export interface Threshold {
  id: string;
  label: string;
  metric: string;
  operator: string;
  value: number;
  unit: string;
  severity: string;
  owner: string;
  set_at: string;
  source: string;
  note: string;
}

export interface UnitDefinition {
  quantity: string;
  canonical_unit: string;
  symbol: string;
  dimension: string;
  precision: number;
  example: number | null;
}

export interface Availability {
  status: string;
  label: string;
  reason: string;
}

export interface AthleteFlag {
  rule: string;
  label: string;
  severity: "action" | "attention" | "info" | string;
  value: number | null;
  unit: string;
  threshold: number;
  detail: string;
  priority: number;
}

export interface AthleteSummary {
  subject_id: string;
  display_id: string;
  position: string;
  age: number;
  body_mass_kg: number;
  height_cm: number;
  training_age_years: number;
  intervention_arm: string;
  status: string;
  readiness: number | null;
  sleep_hours: number | null;
  soreness: number | null;
  fatigue: number | null;
  training_impulse_au: number | null;
  external_load_au: number | null;
  hsr_distance_m: number | null;
  session_rpe: number | null;
  match_minutes: number | null;
  load_ratio: number | null;
  cmj_height_cm: number | null;
  baseline_cmj_height_cm: number | null;
  cmj_delta_pct: number | null;
  availability: Availability;
  flags: AthleteFlag[];
  primary_flag: AthleteFlag | null;
}

export interface DataQuality {
  valid_trials: number;
  excluded_trials: number;
  present_trials: number;
  expected_slots: number;
  missing_slots: number;
  completeness_pct: number;
  quality_state: string;
  source: string;
  note: string;
}

export interface WeeklyLoad {
  week: number;
  phase: string;
  match_week: boolean;
  training_impulse_au: number;
  external_load_au: number;
  hsr_distance_m: number;
  session_rpe: number;
  match_minutes: number;
  duration_min: number;
  session_count: number;
  readiness: number | null;
  sleep_hours: number | null;
  soreness: number | null;
  fatigue: number | null;
  cmj_height_cm: number | null;
  peak_force_n: number | null;
  concentric_impulse_n_s_kg: number | null;
  rsi_mod: number | null;
  valid_trials: number;
}

export interface EvidenceSummary {
  id: string;
  title: string;
  estimate: number | null;
  unit: string;
  interval: { low: number | null; high: number | null; level: number; kind: string } | null;
  evidence_class: string;
  quality: string;
  interpretation: string;
}

export interface StudySummary {
  id: string;
  title: string;
  short_title: string;
  state: string;
  design: string;
  participants: number;
  weeks: [number, number];
  snapshot_id: string;
  evidence_count: number;
  primary_evidence: EvidenceSummary[];
  limitations: string[];
}

export interface ChecklistItem {
  id: string;
  label: string;
  done: boolean;
  status: string;
  source: string;
}

export interface AttentionRow {
  athlete_id: string;
  subject_id: string;
  position: string;
  age: number;
  readiness: number | null;
  sleep_hours: number | null;
  load_ratio: number | null;
  cmj_delta_pct: number | null;
  cmj_height_cm: number | null;
  baseline_cmj_height_cm: number | null;
  soreness: number | null;
  fatigue: number | null;
  flag: AthleteFlag;
  flags: AthleteFlag[];
  rank: number;
}

export interface TodayPayload {
  as_of: string;
  week: number;
  phase: string;
  pulse: {
    roster_active: number;
    roster_total: number;
    unavailable: number;
    availability_scope: string;
    readiness: number;
    readiness_below: number;
    readiness_n: number;
    load_ratio: number;
    load_ratio_above: number;
    load_ratio_reference: string;
    cmj_height_cm: number;
    cmj_baseline_cm: number;
    cmj_delta_pct: number;
    cmj_n: number;
    quality: DataQuality;
  };
  readiness_bands: { l1: number; l2: number; l3: number; l4: number };
  attention: AttentionRow[];
  triage_count: number;
  weekly: WeeklyLoad[];
  checklist: ChecklistItem[];
  data_quality: DataQuality;
  movement: {
    scope: string;
    window_label: string;
    player: MovementPlayer | null;
    quality: { status: string; note: string; position_resets_total: number };
  };
  study: StudySummary;
  plan: {
    status: string;
    version: number;
    source_label: string;
    next_microcycle: Microcycle | null;
  };
  session_logs: SessionLogRecord[];
  thresholds: Threshold[];
  force_trial_id: string | null;
  force_trial: {
    trial_id: string;
    display_id: string;
    jump_height_cm: number;
    peak_force_n: number;
    concentric_impulse_n_s_kg: number;
    rsi_mod: number;
    body_mass_kg: number;
    body_weight_n: number;
  } | null;
}

export interface SessionLogRecord {
  id: string;
  date: string;
  session_type: string;
  duration_min: number;
  session_rpe: number;
  srpe_load_au: number;
  attendance: number;
  notes: string;
  author_role: string;
  source: string;
  source_label: string;
  entered_at: string;
}

export interface SquadWeek {
  week: number;
  readiness: number | null;
  sleep_hours: number | null;
  soreness: number | null;
  fatigue: number | null;
  load_ratio: number | null;
  training_impulse_au: number | null;
  cmj_height_cm: number | null;
  cmj_delta_pct: number | null;
  phase: string;
}

export interface SquadWeekAthlete {
  subject_id: string;
  display_id: string;
  position: string;
  availability: Availability;
  weeks: SquadWeek[];
}

export interface SquadWeeksPayload {
  weeks: number[];
  athletes: SquadWeekAthlete[];
  as_of: string;
}

export interface AthleteWeek {
  week: number;
  phase: string;
  readiness: number | null;
  sleep_hours: number | null;
  soreness: number | null;
  fatigue: number | null;
  training_impulse_au: number | null;
  external_load_au: number | null;
  hsr_distance_m: number | null;
  session_rpe: number | null;
  match_minutes: number | null;
  duration_min: number | null;
  session_count: number | null;
  load_ratio: number | null;
  cmj_height_cm: number | null;
  baseline_cmj_height_cm: number | null;
  cmj_delta_pct: number | null;
  peak_force_n: number | null;
  concentric_impulse_n_s_kg: number | null;
  rsi_mod: number | null;
  cmj_trials: number;
  cmj_excluded: number;
  cmj_missing: boolean;
}

export interface AthleteNote {
  id: string;
  athlete_id: string;
  text: string;
  author_role: string;
  created_at: string;
  source: string;
  source_label: string;
}

export interface MovementPlayer {
  player_id: string;
  team: string;
  duration_s: number;
  distance_m: number;
  hsr_m: number;
  max_speed_m_s: number;
  position_resets: number;
  speed_zone_high_m: number;
  sample_rate_hz: number;
}

export interface AthleteDetail {
  subject: {
    subject_id: string;
    display_id: string;
    position: string;
    age: number;
    body_mass_kg: number;
    height_cm: number;
    training_age_years: number;
    intervention_arm: string;
    status: string;
  };
  athlete: AthleteSummary;
  weeks: AthleteWeek[];
  current: AthleteWeek;
  baseline_weeks: number[];
  individual_change: {
    method: string;
    baseline_mean: number;
    current_mean: number;
    change_cm: number;
    percent_change: number;
    n_weeks: number;
    limitations: string;
  };
  force_trial_id: string | null;
  force_trial: {
    trial_id: string;
    jump_height_cm: number;
    peak_force_n: number;
    concentric_impulse_n_s_kg: number;
    rsi_mod: number;
    quality_state: string;
    sample_rate_hz: number;
  } | null;
  availability: Availability;
  notes: AthleteNote[];
  movement: MovementPlayer | null;
  study: StudySummary;
  thresholds: Threshold[];
  as_of: string;
}

export interface ContextPayload {
  club: {
    id: string;
    name: string;
    squad: string;
    season: string;
    athletes: number;
  };
  season: { label: string; current_week: number; phase: string };
  snapshot: {
    id: string;
    label: string;
    generated_at: string;
    seed: number;
    synthetic: boolean;
    row_counts: Record<string, number>;
    sample_rates: Record<string, number>;
    checksums: Record<string, string>;
    provenance: Record<string, unknown>;
  };
  availability: {
    status: string;
    available: number;
    total: number;
    injury_table: boolean;
    message: string;
  };
  thresholds: Threshold[];
  units: UnitDefinition[];
  as_of: string;
}

export interface PlanSession {
  id: string;
  day: string;
  type: string;
  focus: string;
  planned_load_au: number;
  duration_min: number;
  group: string;
}

export interface Microcycle {
  id: string;
  week: number;
  phase: string;
  focus: string;
  status: string;
  reference_load_au: number | null;
  actual_load_au: number | null;
  testing_window: string;
  sessions: PlanSession[];
  published_at?: string;
}

export interface PeriodBlock {
  id: string;
  label: string;
  phase: string;
  start_week: number;
  end_week: number;
  weeks: number[];
  mean_load_au: number;
  match_weeks: number[];
  testing_window: string;
  status: string;
}

export interface PlanPayload {
  schema_version: string;
  club: ContextPayload["club"];
  season: string;
  current_week: number;
  status: string;
  version: number;
  source: string;
  source_label: string;
  source_note: string;
  created_at: string;
  updated_at: string;
  published_at: string | null;
  microcycles: Microcycle[];
  audit: { at: string; action: string; actor: string; detail: string }[];
  periodization: PeriodBlock[];
  actual_weekly: WeeklyLoad[];
  squad: AthleteSummary[];
  testing_calendar: {
    id: string;
    date_week: number;
    window: string;
    protocol: string;
    status: string;
    completeness: string;
  }[];
  limitations: string[];
  as_of: string;
}

export interface ReliabilityMetric {
  metric_id: string;
  label: string;
  unit: string;
  status: string;
  icc: number | null;
  icc_ci_low: number | null;
  icc_ci_high: number | null;
  typical_error: number | null;
  typical_error_percent: number | null;
  mean_cv_percent: number | null;
  smallest_worthwhile_change: number | null;
  n_subjects: number;
  trials_per_subject: number;
  method: string;
  interpretation: string;
}

export interface TestTrial {
  trial_id: string;
  subject_id: string;
  display_id: string;
  week: number;
  trial_number: number;
  quality_state: string;
  exclusion_reason: string;
  jump_height_cm: number;
  peak_force_n: number;
  concentric_impulse_n_s_kg: number;
  rsi_mod: number;
  body_mass_kg: number;
  trace_available: boolean;
}

export interface TestPayload {
  window: {
    week: number;
    label: string;
    protocol: {
      id: string;
      name: string;
      frequency: string;
      device: string;
      device_record_admitted: boolean;
      calibration_record_admitted: boolean;
      sample_rate_hz: number;
      source: string;
    };
    status: string;
    athletes_complete: number;
    athletes_expected: number;
    trials: number;
    valid: number;
    excluded: number;
  };
  battery: {
    id: string;
    name: string;
    protocol: string | null;
    unit: string;
    status: string;
    window: string;
    quality: string;
    note: string;
  }[];
  reliability: ReliabilityMetric[];
  trials: TestTrial[];
  assessments: {
    id: string;
    created_at: string;
    status: string;
    window_week: number;
    method: string;
    n_subjects: number;
    trials_per_subject: number;
  }[];
  data_quality: DataQuality;
  limitations: string[];
  as_of: string;
}

export interface MovementPayload {
  match_id: string;
  duration_s: number;
  sample_rate_hz: number;
  window_label: string;
  scope: string;
  players: MovementPlayer[];
  quality: { status: string; note: string; position_resets_total: number };
  source: string;
}

export interface ForceTrialPoint {
  trial_id: string;
  time_s: number;
  force_n: number;
  body_weight_n: number;
  phase: string;
}

export interface ForceTrialDetail {
  trial: {
    trial_id: string;
    subject_id: string;
    display_id: string;
    week: number;
    trial_number: number;
    quality_state: string;
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
    trace_path: string;
  };
  subject: { display_id: string; position: string };
  boundaries: Record<string, number>;
  trace: ForceTrialPoint[];
  trace_available: boolean;
  method: {
    algorithm: string;
    algorithm_version: string;
    sample_rate_hz: number;
    integration: string;
    phase_detection: string;
    protocol_id: string;
  };
  provenance: Record<string, unknown>;
}


export interface PerformanceReportSection {
  id: string;
  title: string;
  body: string[];
  metrics?: { label: string; value: string | number; unit: string; detail: string }[];
  table?: Record<string, string | number>[];
  evidence_ids?: string[];
}

export interface PerformanceReport {
  id: string;
  schema_version: string;
  audience: "athlete" | "coach" | "medical" | "board";
  title: string;
  version: number;
  status: string;
  role: string;
  athlete_id: string | null;
  created_at: string;
  frozen_at: string | null;
  created_by: string;
  sections: PerformanceReportSection[];
  study: StudySummary;
  evidence_ids: string[];
  evidence: {
    id: string;
    title: string;
    estimate: number | null;
    unit: string;
    interval: { low: number | null; high: number | null; level: number; kind: string } | null;
    evidence_class: string;
    interpretation: string;
  }[];
  limitations: string[];
  provenance: {
    snapshot_id: string;
    snapshot_checksums: Record<string, string>;
    source_tables: string[];
    as_of: string;
    report_engine: string;
  };
  content_hash: string;
}

export interface UnitsPayload {
  units: UnitDefinition[];
  thresholds: Threshold[];
  status_atoms: Record<string, string[]>;
  design_rules: string[];
}
