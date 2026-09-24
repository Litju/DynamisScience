from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class Study(ContractModel):
    id: str
    title: str
    short_title: str
    state: Literal["ACTIVE", "COMPLETED", "ARCHIVED"] = "ACTIVE"
    research_question: str
    design: str
    intervention: str
    primary_outcomes: list[str]
    secondary_outcomes: list[str]
    dataset_snapshot_id: str
    participant_count: int
    start_week: int
    end_week: int
    protocol_ids: list[str]
    analysis_spec_ids: list[str]
    created_at: str = Field(default_factory=utc_now)


class ResearchQuestion(ContractModel):
    id: str
    study_id: str
    statement: str
    estimand: str
    population: str
    exposure: str
    outcomes: list[str]
    time_horizon: str


class Hypothesis(ContractModel):
    id: str
    study_id: str
    question_id: str
    statement: str
    direction: Literal["increase", "decrease", "change", "no_change"]
    status: Literal["PRIMARY", "SECONDARY", "EXPLORATORY"] = "PRIMARY"
    rationale: str


class Protocol(ContractModel):
    id: str
    study_id: str
    name: str
    description: str
    frequency: str
    status: Literal["ACTIVE", "FROZEN", "RETIRED"] = "ACTIVE"
    duration_weeks: int
    visit_labels: list[str]


class Subject(ContractModel):
    id: str
    display_id: str
    position: str
    age: int
    body_mass_kg: float
    height_cm: float
    training_age_years: int
    intervention_arm: Literal["INTERVENTION", "COMPARISON"]
    status: Literal["ACTIVE", "EXCLUDED"] = "ACTIVE"


class MeasurementEvent(ContractModel):
    id: str
    subject_id: str
    event_type: str
    occurred_at: str
    week: int
    quality_state: Literal["VALID", "WARNING", "EXCLUDED"]
    source_id: str
    protocol_id: str | None = None


class Trial(ContractModel):
    id: str
    subject_id: str
    session_id: str
    week: int
    trial_number: int
    quality_state: Literal["VALID", "WARNING", "EXCLUDED"]
    exclusion_reason: str | None = None
    body_mass_kg: float
    jump_height_cm: float
    concentric_impulse_n_s_kg: float
    eccentric_braking_impulse_n_s_kg: float
    eccentric_braking_duration_s: float
    countermovement_depth_cm: float
    peak_force_n: float
    peak_power_w_kg: float
    rsi_mod: float
    movement_onset_s: float
    takeoff_s: float
    landing_s: float
    trace_path: str


class MetricDefinition(ContractModel):
    id: str
    canonical_id: str
    name: str
    quantity: str
    unit: str
    method: str
    protocol_id: str
    algorithm: str
    version: str
    status: Literal["ACTIVE", "DEPRECATED"] = "ACTIVE"
    dependencies: list[str]
    known_limitations: list[str]
    usage_count: int = 0


class DatasetSnapshot(ContractModel):
    id: str
    label: str
    seed: int
    generator_version: str
    schema_version: str
    generated_at: str
    row_counts: dict[str, int]
    checksums: dict[str, str]
    provenance: dict[str, Any]


class CohortDefinition(ContractModel):
    id: str
    study_id: str
    name: str
    description: str
    subject_ids: list[str]
    exclusion_criteria: list[str]
    snapshot_id: str
    status: Literal["FROZEN", "DRAFT"] = "FROZEN"


class AnalysisSpec(ContractModel):
    id: str
    study_id: str
    name: str
    method_id: str
    method_version: str
    cohort_id: str
    snapshot_id: str
    outcome_metric_id: str
    model_formula: str
    parameters: dict[str, Any]
    planned_contrasts: list[str]
    status: Literal["FROZEN", "EXPLORATORY"] = "FROZEN"
    created_at: str = Field(default_factory=utc_now)


class AnalysisRun(ContractModel):
    id: str
    analysis_spec_id: str
    study_id: str
    snapshot_id: str
    cohort_id: str
    method_id: str
    status: Literal["COMPLETED", "FAILED", "RUNNING"] = "COMPLETED"
    created_at: str
    duration_ms: float
    software_versions: dict[str, str]
    seed: int | None = None
    result: dict[str, Any]
    diagnostics: dict[str, Any]
    output_artifact_ids: list[str]
    reproducibility_key: str


class EvidenceArtifact(ContractModel):
    id: str
    title: str
    kind: Literal["EFFECT", "RELIABILITY", "CHANGE", "MODEL", "DESCRIPTIVE"]
    metric_id: str
    value: float | None
    unit: str
    estimate: float | None
    uncertainty: float | None
    uncertainty_label: str | None
    effect_size: float | None
    population: str
    sample_size: int
    protocol_id: str
    dataset_snapshot_id: str
    analysis_run_id: str
    diagnostics: dict[str, Any]
    quality: Literal["VALID", "WARNING", "EXPLORATORY"]
    provenance: dict[str, Any]
    interpretation: str


class FigureArtifact(ContractModel):
    id: str
    title: str
    kind: str
    evidence_ids: list[str]
    dataset_snapshot_id: str
    analysis_run_id: str
    spec: dict[str, Any]
    path: str | None = None


class ModelSpec(ContractModel):
    id: str
    name: str
    kind: str
    version: str
    description: str
    inputs: list[str]
    outputs: list[str]
    status: Literal["PROTOTYPE", "IMPLEMENTED", "ROADMAP"] = "PROTOTYPE"
    parameters: dict[str, Any]


class ModelRun(ContractModel):
    id: str
    model_spec_id: str
    dataset_snapshot_id: str
    subject_ids: list[str]
    parameters: dict[str, float]
    output: dict[str, Any]
    diagnostics: dict[str, Any]
    created_at: str


class LineageEdge(ContractModel):
    id: str
    source: str
    target: str
    relation: str
    label: str


class Report(ContractModel):
    id: str
    title: str
    study_id: str
    status: Literal["DRAFT", "FROZEN"] = "DRAFT"
    evidence_ids: list[str]
    figure_ids: list[str]
    sections: list[str]
    provenance_note: str
    created_at: str
