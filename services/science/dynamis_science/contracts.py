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


# ---------------------------------------------------------------------------
# Real-data admission contracts (RES-587)
# ---------------------------------------------------------------------------


class DataSource(ContractModel):
    id: str
    name: str
    publisher: str
    dataset_identity: str
    version: str
    acquisition_method: str
    license_or_agreement: str
    permitted_uses: list[str] = Field(default_factory=list)
    redistribution_restrictions: str
    privacy_status: Literal["ANONYMOUS", "PSEUDONYMOUS", "IDENTIFIABLE", "NOT_APPLICABLE"] = "NOT_APPLICABLE"
    retention_limitations: str = ""
    derived_data_publishable: bool = False
    rights_status: Literal["VERIFIED", "UNVERIFIED", "FIXTURE_ONLY", "BLOCKED"] = "UNVERIFIED"
    rights_verified_at: str | None = None
    rights_verified_by: str | None = None
    notes: str = ""


class SourceArtifact(ContractModel):
    id: str
    source_id: str
    format: Literal["CSV", "PARQUET", "JSON", "OTHER"]
    original_filename: str
    stored_path: str
    content_hash_sha256: str
    size_bytes: int
    acquired_at: str = Field(default_factory=utc_now)
    acquisition_method: str
    rights_record_id: str


class Instrument(ContractModel):
    id: str
    measurement_family: Literal["CMJ_FORCE_PLATFORM", "SPRINT_TIMING", "IMU", "GNSS", "OTHER"]
    manufacturer: str
    model: str
    serial_number: str
    calibration_status: Literal["CALIBRATED", "UNCALIBRATED", "UNKNOWN"] = "UNKNOWN"
    calibration_date: str | None = None
    sampling_capabilities_hz: list[float] = Field(default_factory=list)
    supported_units: dict[str, str] = Field(default_factory=dict)
    notes: str = ""


class AcquisitionProtocol(ContractModel):
    id: str
    measurement_family: Literal["CMJ_FORCE_PLATFORM", "SPRINT_TIMING", "IMU", "GNSS", "OTHER"]
    name: str
    version: str
    sampling_hz: float
    units: dict[str, str] = Field(default_factory=dict)
    coordinate_convention: str = "NOT_SPECIFIED"
    processing_method: str = "NOT_SPECIFIED"
    body_mass_required: bool = True
    known_limitations: list[str] = Field(default_factory=list)


class Signal(ContractModel):
    id: str
    trial_id: str
    channel: str
    unit: str
    sampling_hz: float
    samples: list[float] = Field(default_factory=list)
    timestamps_s: list[float] = Field(default_factory=list)
    quality_state: Literal["VALID", "WARNING", "EXCLUDED"] = "VALID"


class Observation(ContractModel):
    id: str
    source_artifact_id: str
    measurement_family: str
    subject_id: str
    session_id: str
    trial_id: str
    instrument_id: str
    protocol_id: str
    sampling_hz: float
    occurred_at: str
    quality_state: Literal["VALID", "WARNING", "EXCLUDED", "QUARANTINED"] = "VALID"
    values: dict[str, float] = Field(default_factory=dict)
    units: dict[str, str] = Field(default_factory=dict)
    derived_metric_ids: list[str] = Field(default_factory=list)


class QualityAssessment(ContractModel):
    id: str
    source_artifact_id: str
    measurement_family: str
    status: Literal["REJECTED", "QUARANTINED", "ADMITTED_WITH_WARNINGS", "ADMITTED"]
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    rejected_record_ids: list[str] = Field(default_factory=list)
    quarantined_record_ids: list[str] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)
    checked_at: str = Field(default_factory=utc_now)


class AdmissionRecord(ContractModel):
    id: str
    source_id: str
    source_artifact_id: str
    measurement_family: str
    status: Literal["REJECTED", "QUARANTINED", "ADMITTED_WITH_WARNINGS", "ADMITTED"]
    rights_status: str
    quality_assessment_id: str
    dataset_snapshot_id: str | None = None
    parser_version: str
    normalization_rules: list[str] = Field(default_factory=list)
    qc_operations: list[str] = Field(default_factory=list)
    exclusion_criteria: list[str] = Field(default_factory=list)
    instrument_ids: list[str] = Field(default_factory=list)
    protocol_ids: list[str] = Field(default_factory=list)
    metric_definition_ids: list[str] = Field(default_factory=list)
    algorithm_versions: dict[str, str] = Field(default_factory=dict)
    schema_version: str
    admitted_at: str = Field(default_factory=utc_now)
    provenance_manifest_id: str | None = None


class ProvenanceManifest(ContractModel):
    id: str
    snapshot_id: str
    source_artifact_ids: list[str] = Field(default_factory=list)
    content_hashes: dict[str, str] = Field(default_factory=dict)
    data_rights_status: str
    parser_version: str
    normalization_rules: list[str] = Field(default_factory=list)
    qc_operations: list[str] = Field(default_factory=list)
    exclusion_criteria: list[str] = Field(default_factory=list)
    instrument_metadata: list[dict[str, Any]] = Field(default_factory=list)
    metric_definitions: list[dict[str, Any]] = Field(default_factory=list)
    algorithm_versions: dict[str, str] = Field(default_factory=dict)
    schema_version: str
    created_at: str = Field(default_factory=utc_now)
