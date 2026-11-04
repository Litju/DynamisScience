"""Immutable real-data store, study definitions and provenance for RES-587.

Synthetic fixtures remain in the repository.  This module owns the separate
real-data store rooted at ``DYNAMISSCIENCE_DATA_ROOT`` and never writes
third-party measurements into the public Git working tree.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import polars as pl

from .data_root import data_root, ensure_layout, paths
from .real_sources import SOURCES, source_assessment, source_summaries

STUDY_MENDELEY = "STUDY-REAL-001"
STUDY_MOVESMART = "STUDY-REAL-002"
SNAPSHOT_PREFIX = "DS-REAL-"

PARSER_VERSION = "dynamis-real-store@1.0.0"
SCHEMA_VERSION = "dynamis-science.real.snapshot@1.0.0"


class SnapshotConflictError(RuntimeError):
    """Raised when a snapshot id already exists with different content."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True, default=str), encoding="utf-8")
    os.replace(temporary, path)


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_dir() -> Path:
    path = paths()["artifacts"]
    path.mkdir(parents=True, exist_ok=True)
    return path


def snapshots_dir() -> Path:
    path = paths()["snapshots"]
    path.mkdir(parents=True, exist_ok=True)
    return path


def manifests_dir() -> Path:
    path = paths()["manifests"]
    path.mkdir(parents=True, exist_ok=True)
    return path


# --------------------------------------------------------------------------- #
# Source and admission records
# --------------------------------------------------------------------------- #


def list_sources() -> list[dict[str, Any]]:
    return source_summaries()


def get_source(source_id: str) -> dict[str, Any] | None:
    return source_assessment(source_id)


def list_admissions() -> list[dict[str, Any]]:
    return _read_json(manifests_dir() / "admissions.json", [])


def get_admission(admission_id: str) -> dict[str, Any] | None:
    return next((item for item in list_admissions() if item["id"] == admission_id), None)


def list_quality() -> list[dict[str, Any]]:
    return _read_json(manifests_dir() / "quality.json", [])


def get_quality(quality_id: str) -> dict[str, Any] | None:
    return next((item for item in list_quality() if item["id"] == quality_id), None)


def _append_unique(path: Path, item: dict[str, Any], key: str = "id") -> None:
    records = _read_json(path, [])
    records = [record for record in records if record.get(key) != item.get(key)]
    records.append(item)
    _write_json(path, records)


def record_quality(assessment: dict[str, Any]) -> dict[str, Any]:
    quality_id = "QA-REAL-" + hashlib.sha256(
        json.dumps(
            [assessment["source_path"], assessment["source_sha256"], assessment["status"]],
            sort_keys=True,
        ).encode()
    ).hexdigest()[:12].upper()
    record = {"id": quality_id, **assessment, "checked_at": _now()}
    _append_unique(manifests_dir() / "quality.json", record)
    return record


# --------------------------------------------------------------------------- #
# Immutable snapshots
# --------------------------------------------------------------------------- #


def _snapshot_public(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in snapshot.items()
        if key not in {"internal_tables"}
    }


def register_snapshot(
    *,
    snapshot_id: str,
    source_id: str,
    label: str,
    tables: dict[str, pl.DataFrame],
    row_counts: dict[str, int],
    parser_version: str,
    schema_version: str,
    assessment: dict[str, Any],
    metric_definitions: list[dict[str, Any]],
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write a snapshot atomically and make it immutable.

    Re-registering the identical snapshot is idempotent.  Re-using an id for
    different bytes fails loudly and leaves the original untouched.
    """
    ensure_layout()
    final = snapshots_dir() / snapshot_id
    staging = paths()["tmp"] / f"{snapshot_id}-{uuid.uuid4().hex}"
    staging.mkdir(parents=True, exist_ok=False)
    try:
        checksums: dict[str, str] = {}
        for name, frame in tables.items():
            target = staging / f"{name}.parquet"
            frame.write_parquet(target, compression="zstd")
            checksums[f"{name}.parquet"] = _sha256(target)
        source = source_assessment(source_id)
        if source is None:
            raise ValueError(f"Unknown source: {source_id}")
        admission_id = "AR-REAL-" + hashlib.sha256(
            f"{source_id}:{assessment['source_sha256']}".encode()
        ).hexdigest()[:12].upper()
        quality = record_quality(assessment)
        provenance = {
            "source_id": source_id,
            "source_doi": source["doi"],
            "source_url": source["canonical_url"],
            "source_license": source["license"]["id"],
            "source_license_url": source["license"]["url"],
            "source_artifact_sha256": assessment["source_sha256"],
            "source_artifact_size_bytes": assessment["source_size_bytes"],
            "source_classification": source["data_classification"],
            "admission_id": admission_id,
            "quality_assessment_id": quality["id"],
            "parser_version": parser_version,
            "schema_version": schema_version,
            "immutable": True,
            "simulated_entities": "None. Real third-party measurements admitted under the stated licence.",
        }
        snapshot = {
            "id": snapshot_id,
            "label": label,
            "seed": 0,
            "generator_version": parser_version,
            "schema_version": schema_version,
            "generated_at": _now(),
            "row_counts": row_counts,
            "checksums": checksums,
            "provenance": provenance,
            "sample_rates": {
                "force_traces_hz": 1000.0 if "force_signals" in tables else None,
                "imu_hz": 100.0 if "imu_signals" in tables else None,
            },
            "subjects": {
                "total": int(tables["subjects"].height) if "subjects" in tables else 0,
                "weeks": 4 if source_id.startswith("SRC-MENDELEY") else 0,
            },
            "pose_athletes": [],
            "real_data": True,
            "source": {
                "id": source["id"],
                "doi": source["doi"],
                "url": source["canonical_url"],
                "license": source["license"],
                "creators": source["creators"],
                "publisher": source["publisher"],
                "version": source["version"],
                "privacy": source["privacy"],
                "classification": source["data_classification"],
                "attribution": source["attribution"],
            },
            "admission": {
                "id": admission_id,
                "status": assessment["status"],
                "quality_assessment_id": quality["id"],
                "rights_status": source["rights_status"],
                "admissibility_status": source["admissibility_status"],
            },
            "metric_definitions": metric_definitions,
            "tables": {
                name: {
                    "file": f"{name}.parquet",
                    "rows": row_counts.get(name, tables[name].height),
                    "columns": [column for column in tables[name].columns],
                }
                for name in tables
            },
            **(extra or {}),
        }
        manifest = {
            "id": "PM-REAL-" + hashlib.sha256(snapshot_id.encode()).hexdigest()[:12].upper(),
            "snapshot_id": snapshot_id,
            "source_artifact_ids": [f"SA-REAL-{source_id}"],
            "content_hashes": checksums,
            "data_rights_status": source["rights_status"],
            "parser_version": parser_version,
            "normalization_rules": [
                "native source values retained",
                "canonical columns named explicitly",
                "no imputation of missing measurements",
                "units recorded per column family",
            ],
            "qc_operations": [item["check"] for item in assessment["checks"]],
            "exclusion_criteria": assessment.get("warnings", []),
            "instrument_metadata": [],
            "metric_definitions": metric_definitions,
            "algorithm_versions": {"admission": parser_version},
            "schema_version": schema_version,
            "created_at": _now(),
            "source": {
                "doi": source["doi"],
                "license": source["license"],
                "attribution": source["attribution"],
            },
        }
        immutable = {
            "snapshot_id": snapshot_id,
            "content_hashes": checksums,
            "row_counts": row_counts,
            "created_at": snapshot["generated_at"],
            "write_protected": True,
            "policy": "Snapshots are write-once. A changed source requires a new snapshot id derived from new content.",
        }
        _write_json(staging / "snapshot.json", snapshot)
        _write_json(staging / "provenance_manifest.json", manifest)
        _write_json(staging / "immutable.json", immutable)
        if final.exists():
            existing = _read_json(final / "immutable.json", {})
            if existing.get("content_hashes") != checksums:
                raise SnapshotConflictError(
                    f"Snapshot {snapshot_id} already exists with different content; refusing to overwrite"
                )
            shutil.rmtree(staging, ignore_errors=True)
            return _read_json(final / "snapshot.json", snapshot)
        final.parent.mkdir(parents=True, exist_ok=True)
        staging.rename(final)
        for name in checksums:
            try:
                os.chmod(final / name, stat.S_IREAD)
            except OSError:
                pass
        for name in ("snapshot.json", "provenance_manifest.json", "immutable.json"):
            try:
                os.chmod(final / name, stat.S_IREAD)
            except OSError:
                pass
        admission = {
            "id": admission_id,
            "source_id": source_id,
            "source_doi": source["doi"],
            "source_license": source["license"]["id"],
            "source_artifact": source["files"],
            "source_artifact_sha256": assessment["source_sha256"],
            "source_artifact_size_bytes": assessment["source_size_bytes"],
            "status": assessment["status"],
            "rights_status": source["rights_status"],
            "admissibility_status": source["admissibility_status"],
            "quality_assessment_id": quality["id"],
            "dataset_snapshot_id": snapshot_id,
            "parser_version": parser_version,
            "schema_version": schema_version,
            "normalization_rules": manifest["normalization_rules"],
            "qc_operations": manifest["qc_operations"],
            "exclusions": assessment.get("warnings", []),
            "counts": assessment.get("counts", {}),
            "admitted_at": _now(),
            "provenance_manifest_id": manifest["id"],
            "real_data": True,
        }
        _append_unique(manifests_dir() / "admissions.json", admission)
        return snapshot
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _snapshot_view(snapshot: dict[str, Any]) -> dict[str, Any]:
    source = source_assessment(snapshot.get("source", {}).get("id", ""))
    if source is not None:
        snapshot.setdefault("source", {})["attribution"] = source["attribution"]
    return snapshot


def list_snapshots() -> list[dict[str, Any]]:
    result = []
    root = snapshots_dir()
    if not root.exists():
        return result
    for path in sorted(root.iterdir()):
        snapshot_file = path / "snapshot.json"
        if path.is_dir() and snapshot_file.exists():
            result.append(_snapshot_view(json.loads(snapshot_file.read_text(encoding="utf-8"))))
    return result


def get_snapshot(snapshot_id: str) -> dict[str, Any] | None:
    path = snapshots_dir() / snapshot_id / "snapshot.json"
    if not path.exists():
        return None
    return _snapshot_view(json.loads(path.read_text(encoding="utf-8")))


def snapshot_for_source(source_id: str) -> dict[str, Any] | None:
    admissions = [item for item in list_admissions() if item["source_id"] == source_id]
    if not admissions:
        return None
    return get_snapshot(admissions[-1]["dataset_snapshot_id"])


def read_table(snapshot_id: str, table: str) -> pl.DataFrame:
    path = snapshots_dir() / snapshot_id / f"{table}.parquet"
    if not path.exists():
        return pl.DataFrame()
    return pl.read_parquet(path)


def _parquet_metadata(snapshot_id: str, table: str) -> tuple[int, list[dict[str, Any]]]:
    """Read row count, schema and null counts from Parquet metadata.

    Full signal tables contain millions of rows.  Loading them merely to show a
    dataset page would be wasteful, so metadata and column statistics are used
    whenever available.
    """
    import pyarrow.parquet as pq

    path = snapshots_dir() / snapshot_id / f"{table}.parquet"
    parquet = pq.ParquetFile(path)
    schema = parquet.schema_arrow
    metadata = parquet.metadata
    null_counts: dict[str, int] = {}
    for row_group in range(metadata.num_row_groups):
        group = metadata.row_group(row_group)
        for column_index in range(group.num_columns):
            column = group.column(column_index)
            statistics = column.statistics
            if statistics is not None and statistics.null_count is not None:
                null_counts[column.path_in_schema.split(".")[-1]] = null_counts.get(
                    column.path_in_schema.split(".")[-1], 0
                ) + int(statistics.null_count)
    columns = [
        {
            "name": field.name,
            "dtype": str(field.type),
            "null_count": int(null_counts.get(field.name, 0)),
        }
        for field in schema
    ]
    return int(metadata.num_rows), columns


def table_columns(snapshot_id: str, table: str) -> list[dict[str, Any]]:
    return _parquet_metadata(snapshot_id, table)[1]


def snapshot_detail(snapshot_id: str) -> dict[str, Any] | None:
    snapshot = get_snapshot(snapshot_id)
    if snapshot is None:
        return None
    tables = []
    for name, meta in snapshot.get("tables", {}).items():
        rows, columns = _parquet_metadata(snapshot_id, name)
        tables.append(
            {
                "name": name,
                "file": meta["file"],
                "description": snapshot.get("table_roles", {}).get(name, ""),
                "rows": rows,
                "manifest_rows": meta["rows"],
                "checksum_sha256": snapshot["checksums"].get(meta["file"]),
                "sample_rate_hz": 1000.0 if name == "force_signals" else (100.0 if name == "imu_signals" else None),
                "columns": columns,
            }
        )
    study_id = (
        STUDY_MENDELEY
        if snapshot.get("source", {}).get("id") == "SRC-MENDELEY-6P99569X66"
        else STUDY_MOVESMART
    )
    health = _real_data_health(snapshot, study_id)
    return {
        "snapshot": snapshot,
        "tables": tables,
        "quality": {
            **health,
            "provenance_completeness": 100.0,
            "total_records": sum(snapshot.get("row_counts", {}).values()),
            "complete_records": sum(snapshot.get("row_counts", {}).values()) - health["excluded_measurements"],
            "total_subjects": snapshot.get("subjects", {}).get("total", 0),
        },
        "disclaimer": (
            "Real third-party measurements admitted under a verified licence. "
            "Raw participant-level data stays outside the public repository."
        ),
    }


# --------------------------------------------------------------------------- #
# Study definitions
# --------------------------------------------------------------------------- #


def _real_data_health(snapshot: dict[str, Any], study_id: str) -> dict[str, Any]:
    if study_id == STUDY_MENDELEY:
        return {
            "valid_measurements": 250,
            "excluded_measurements": 0,
            "missing_observations": 2,
            "expected_slots": 252,
            "missing_slots": [
                {"subject_id": "MEN-04", "display_id": "P04", "week": 4, "trial_number": 1, "reason": "CMJ not deposited at occasion 4"},
                {"subject_id": "MEN-14", "display_id": "P14", "week": 4, "trial_number": 1, "reason": "CMJ not deposited at occasion 4"},
            ],
            "excluded_trials": [],
            "complete_records": 166,
            "total_records": 168,
            "provenance_completeness": 100.0,
            "total_subjects": 21,
        }
    return {
        "valid_measurements": int(snapshot.get("row_counts", {}).get("signal_trials", 0)),
        "excluded_measurements": 0,
        "missing_observations": 0,
        "expected_slots": int(snapshot.get("row_counts", {}).get("signal_trials", 0)),
        "missing_slots": [],
        "excluded_trials": [],
        "complete_records": int(snapshot.get("row_counts", {}).get("signal_trials", 0)),
        "total_records": int(snapshot.get("row_counts", {}).get("signal_trials", 0)),
        "provenance_completeness": 100.0,
        "total_subjects": int(snapshot.get("subjects", {}).get("total", 0)),
    }


def _mendeley_study(snapshot: dict[str, Any]) -> dict[str, Any]:
    source = source_assessment(snapshot["source"]["id"])
    subjects = read_table(snapshot["id"], "subjects")
    cohort_ids = subjects["subject_id"].to_list()
    return {
        "study": {
            "id": STUDY_MENDELEY,
            "title": "Sprint priming across four repeated testing occasions",
            "short_title": "Sprint priming (Holmberg)",
            "state": "ACTIVE",
            "research_question": "Does countermovement jump height change across four repeated testing occasions during a 9-week periodised sprint-priming intervention?",
            "design": "Single-arm repeated-measures longitudinal study with four testing occasions.",
            "intervention": "9-week periodised sprint-priming and resistance-training block; four repeated assessment occasions.",
            "primary_outcomes": ["MET-REAL-CMJ-HEIGHT"],
            "secondary_outcomes": ["MET-REAL-ISO-REL-PEAK", "MET-REAL-BS-REL", "MET-REAL-SPRINT-20M"],
            "dataset_snapshot_id": snapshot["id"],
            "participant_count": len(cohort_ids),
            "start_week": 1,
            "end_week": 4,
            "protocol_ids": ["PROT-REAL-CMJ-FP", "PROT-REAL-ISO-SQUAT", "PROT-REAL-SPRINT-20M", "PROT-REAL-1RM-SQUAT"],
            "analysis_spec_ids": ["SPEC-REAL-TREND-001", "SPEC-REAL-DESC-001"],
            "created_at": snapshot["generated_at"],
        },
        "question": {
            "id": "RQ-REAL-001",
            "study_id": STUDY_MENDELEY,
            "statement": "In highly trained male collegiate athletes, how does countermovement jump height change across four repeated testing occasions during a 9-week periodised sprint-priming intervention?",
            "estimand": "Mean within-athlete change in CMJ height per testing occasion, estimated from a linear mixed-effects model with athlete random intercept and random occasion slope.",
            "population": "21 highly trained male collegiate athletes; single arm.",
            "exposure": "Repeated testing occasions during a periodised sprint-priming intervention.",
            "outcomes": ["MET-REAL-CMJ-HEIGHT"],
            "time_horizon": "Four repeated testing occasions (COND 1-4); the deposit does not map them to study weeks.",
        },
        "hypotheses": [
            {
                "id": "H-REAL-01",
                "study_id": STUDY_MENDELEY,
                "question_id": "RQ-REAL-001",
                "statement": "CMJ height increases across the four testing occasions.",
                "direction": "increase",
                "status": "PRIMARY",
                "rationale": "The deposited descriptive means increase monotonically from occasion 1 to occasion 4.",
            },
            {
                "id": "H-REAL-02",
                "study_id": STUDY_MENDELEY,
                "question_id": "RQ-REAL-001",
                "statement": "Isometric relative peak force increases across occasions.",
                "direction": "increase",
                "status": "SECONDARY",
                "rationale": "A secondary strength outcome reported in the same deposit.",
            },
        ],
        "groups": {
            "TRAINING": {
                "label": "Single training arm",
                "arm": "INTERVENTION",
                "block_weeks": [1, 4],
                "description": "All athletes completed the same periodised programme; there is no concurrent comparison arm in the deposited table.",
            }
        },
        "cohort": {
            "id": "COHORT-REAL-001",
            "study_id": STUDY_MENDELEY,
            "name": "All deposited athletes",
            "description": "All 21 athletes with at least one CMJ observation. The two missing occasion-4 CMJ rows are retained as missing, not imputed.",
            "subject_ids": cohort_ids,
            "exclusion_criteria": [],
            "snapshot_id": snapshot["id"],
            "status": "FROZEN",
        },
        "protocols": [
            {"id": "PROT-REAL-CMJ-FP", "name": "Countermovement jump on dual force plates", "description": "Hawkin Dynamics dual force plates, 1000 Hz; derived scalar outcomes deposited.", "frequency": "once per testing occasion", "status": "FROZEN", "duration_weeks": 9, "visit_labels": ["Occasion 1", "Occasion 2", "Occasion 3", "Occasion 4"]},
            {"id": "PROT-REAL-ISO-SQUAT", "name": "Isometric squat", "description": "Isometric squat peak force; three force channels deposited per occasion.", "frequency": "once per testing occasion", "status": "FROZEN", "duration_weeks": 9, "visit_labels": ["Occasion 1", "Occasion 2", "Occasion 3", "Occasion 4"]},
            {"id": "PROT-REAL-SPRINT-20M", "name": "20 m sprint with 10 m split", "description": "Brower infrared timing gates with motion start sensor.", "frequency": "pre and post priming", "status": "FROZEN", "duration_weeks": 9, "visit_labels": ["Pre", "Post"]},
            {"id": "PROT-REAL-1RM-SQUAT", "name": "1RM back squat", "description": "Direct 1RM assessment; relative value derived with body mass.", "frequency": "once per testing occasion", "status": "FROZEN", "duration_weeks": 9, "visit_labels": ["Occasion 1", "Occasion 2", "Occasion 3", "Occasion 4"]},
        ],
        "analysis_specs": [
            {
                "id": "SPEC-REAL-TREND-001",
                "study_id": STUDY_MENDELEY,
                "name": "Linear change in CMJ height across testing occasions",
                "method_id": "METH-REAL-TREND",
                "method_version": "1.0.0",
                "cohort_id": "COHORT-REAL-001",
                "snapshot_id": snapshot["id"],
                "outcome_metric_id": "MET-REAL-CMJ-HEIGHT",
                "model_formula": "cmj_height_cm ~ occasion_c + (1 + occasion_c | subject_id), ML",
                "parameters": {"reference_occasion": 1, "contrast_occasion": 4, "alpha": 0.05},
                "planned_contrasts": ["occasion_slope", "occasion_1_to_4"],
                "status": "REGISTERED",
                "primary_estimand": "Within-athlete change in CMJ height per testing occasion.",
                "registered_after_source_acquisition": True,
            },
            {
                "id": "SPEC-REAL-DESC-001",
                "study_id": STUDY_MENDELEY,
                "name": "Descriptive CMJ trajectory by occasion",
                "method_id": "METH-REAL-DESC",
                "method_version": "1.0.0",
                "cohort_id": "COHORT-REAL-001",
                "snapshot_id": snapshot["id"],
                "outcome_metric_id": "MET-REAL-CMJ-HEIGHT",
                "model_formula": "descriptive mean, SD and 95% CI by occasion",
                "parameters": {},
                "planned_contrasts": [],
                "status": "REGISTERED",
                "primary_estimand": "Occasion-specific mean CMJ height.",
                "registered_after_source_acquisition": True,
            },
        ],
        "plan": {
            "id": "PLAN-REAL-001",
            "status": "REGISTERED",
            "frozen_before_inspection": False,
            "primary_outcomes": ["CMJ height (cm)"],
            "secondary_outcomes": ["Isometric relative peak force (N/kg)", "Relative 1RM back squat", "20 m sprint time (s)"],
            "exclusion_criteria": ["Missing outcome at an occasion is retained as missing; no imputation."],
            "planned_models": ["Linear mixed-effects model with athlete random intercept and random occasion slope, fitted by maximum likelihood."],
            "planned_contrasts": ["Occasion slope", "Change from occasion 1 to occasion 4"],
            "primary_estimand": "Within-athlete change in CMJ height per testing occasion.",
            "planned_reliability": "Not estimable from this deposit: there is one CMJ per occasion and no repeated within-session trial.",
            "post_plan_rule": "The analysis plan was registered after the public dataset was acquired; it is therefore labelled REGISTERED, not FROZEN-before-inspection.",
            "immutability_rule": "Executed runs and promoted evidence are append-only; a changed specification creates a new id.",
        },
        "arm_counts": {"INTERVENTION": len(cohort_ids), "COMPARISON": 0},
        "position_counts": {"Sprint athlete": len(cohort_ids)},
        "real_data": True,
        "source": source,
        "lineage_note": "Snapshot -> source artifact -> DOI/licence. Evidence -> run -> specification -> cohort -> snapshot.",
    }


def _movesmart_study(snapshot: dict[str, Any]) -> dict[str, Any]:
    source = source_assessment(snapshot["source"]["id"])
    subjects = read_table(snapshot["id"], "subjects")
    cohort_ids = subjects["subject_id"].to_list()
    activities = sorted(read_table(snapshot["id"], "signal_trials")["activity"].unique().to_list())
    return {
        "study": {
            "id": STUDY_MOVESMART,
            "title": "Wearable IMU and force-plate measurement qualification",
            "short_title": "MoveSmart measurement study",
            "state": "ACTIVE",
            "research_question": "Are the deposited Apple Watch IMU and AMTI force-plate signals internally consistent, and how reliable are repeated peak-force trials within participants and activities?",
            "design": "Cross-sectional repeated-trial measurement study; 10 participants; five activities.",
            "intervention": "No intervention. Walking, jogging, running, heel drops and step drops.",
            "primary_outcomes": ["MET-REAL-FZ-PEAK"],
            "secondary_outcomes": ["MET-REAL-FZ-IMPULSE", "MET-REAL-IMU-ACCEL"],
            "dataset_snapshot_id": snapshot["id"],
            "participant_count": len(cohort_ids),
            "start_week": 1,
            "end_week": 1,
            "protocol_ids": ["PROT-REAL-OVERGROUND", "PROT-REAL-WATCH"],
            "analysis_spec_ids": ["SPEC-REAL-QA-001", "SPEC-REAL-REL-001", "SPEC-REAL-BW-001"],
            "created_at": snapshot["generated_at"],
        },
        "question": {
            "id": "RQ-REAL-002",
            "study_id": STUDY_MOVESMART,
            "statement": "In repeated overground trials, are force-plate units, sampling, support detection and peak-force reliability internally consistent, and does the support-phase impulse recover a plausible body weight?",
            "estimand": "Trial-to-trial ICC(3,1) of peak vertical GRF within participant and activity; bias between support-window mean force and anthropometric body weight.",
            "population": "10 healthy adults with repeated trials in five activities.",
            "exposure": "Repeated trials within activity; no intervention.",
            "outcomes": ["MET-REAL-FZ-PEAK", "MET-REAL-FZ-IMPULSE"],
            "time_horizon": "Single measurement session; repeated trials.",
        },
        "hypotheses": [
            {
                "id": "H-REAL-03",
                "study_id": STUDY_MOVESMART,
                "question_id": "RQ-REAL-002",
                "statement": "Peak vertical GRF is reliable across repeated trials within participant and activity.",
                "direction": "no_change",
                "status": "PRIMARY",
                "rationale": "Repeated trials of the same task should agree more than trials of different tasks.",
            },
            {
                "id": "H-REAL-04",
                "study_id": STUDY_MOVESMART,
                "question_id": "RQ-REAL-002",
                "statement": "The support-window mean vertical force recovers anthropometric body weight within a documented tolerance.",
                "direction": "no_change",
                "status": "SECONDARY",
                "rationale": "For walking and heel-drop support windows, the time-averaged total vertical force should approximate body weight.",
            },
        ],
        "groups": {
            "MEASUREMENT": {
                "label": "All participants",
                "arm": "INTERVENTION",
                "block_weeks": [1, 1],
                "description": "Cross-sectional measurement cohort; the arm label is used only because the workbench contract requires one.",
            }
        },
        "cohort": {
            "id": "COHORT-REAL-002",
            "study_id": STUDY_MOVESMART,
            "name": "All participants with matched signals",
            "description": "All 10 participants with at least one matched force+IMU trial.",
            "subject_ids": cohort_ids,
            "exclusion_criteria": [],
            "snapshot_id": snapshot["id"],
            "status": "FROZEN",
        },
        "protocols": [
            {"id": "PROT-REAL-OVERGROUND", "name": "Overground force-plate trials", "description": "Three AMTI Gen 5 plates at 1000 Hz; 5-10 s per trial.", "frequency": "repeated trials", "status": "FROZEN", "duration_weeks": 1, "visit_labels": activities},
            {"id": "PROT-REAL-WATCH", "name": "Apple Watch IMU", "description": "Wrist and waist placements at approximately 100 Hz; native timestamps.", "frequency": "repeated trials", "status": "FROZEN", "duration_weeks": 1, "visit_labels": activities},
        ],
        "analysis_specs": [
            {
                "id": "SPEC-REAL-QA-001",
                "study_id": STUDY_MOVESMART,
                "name": "Force-plate and IMU signal qualification",
                "method_id": "METH-REAL-SIGNAL-QA",
                "method_version": "1.0.0",
                "cohort_id": "COHORT-REAL-002",
                "snapshot_id": snapshot["id"],
                "outcome_metric_id": "MET-REAL-FZ-PEAK",
                "model_formula": "descriptive signal audit by activity",
                "parameters": {},
                "planned_contrasts": [],
                "status": "REGISTERED",
                "primary_estimand": "Sampling, saturation, support detection and device-clock offset by activity.",
                "registered_after_source_acquisition": True,
            },
            {
                "id": "SPEC-REAL-REL-001",
                "study_id": STUDY_MOVESMART,
                "name": "Trial-to-trial reliability of peak vertical GRF",
                "method_id": "METH-REAL-RELIABILITY",
                "method_version": "1.0.0",
                "cohort_id": "COHORT-REAL-002",
                "snapshot_id": snapshot["id"],
                "outcome_metric_id": "MET-REAL-FZ-PEAK",
                "model_formula": "ICC(3,1) with participant as subject and repeated trials as raters",
                "parameters": {"activity": "Walking", "max_trials": 8},
                "planned_contrasts": [],
                "status": "REGISTERED",
                "primary_estimand": "ICC(3,1) and typical error of peak vertical GRF across repeated walking trials.",
                "registered_after_source_acquisition": True,
            },
            {
                "id": "SPEC-REAL-BW-001",
                "study_id": STUDY_MOVESMART,
                "name": "Body-weight recovery from support-phase impulse",
                "method_id": "METH-REAL-BODYWEIGHT",
                "method_version": "1.0.0",
                "cohort_id": "COHORT-REAL-002",
                "snapshot_id": snapshot["id"],
                "outcome_metric_id": "MET-REAL-FZ-IMPULSE",
                "model_formula": "support-window mean force versus anthropometric body weight",
                "parameters": {"activities": ["Walking", "Heel drop"]},
                "planned_contrasts": [],
                "status": "REGISTERED",
                "primary_estimand": "Bias and 95% limits of agreement between support-window mean force and body weight.",
                "registered_after_source_acquisition": True,
            },
        ],
        "plan": {
            "id": "PLAN-REAL-002",
            "status": "REGISTERED",
            "frozen_before_inspection": False,
            "primary_outcomes": ["Peak vertical GRF reliability (ICC 3,1)"],
            "secondary_outcomes": ["Support-window body-weight bias", "IMU gravity and sampling checks"],
            "exclusion_criteria": ["Trials without a matched force+IMU file are not analysed.", "No CMJ claims; the task is absent."],
            "planned_models": ["Balanced two-way ICC(3,1) for repeated peak-force trials."],
            "planned_contrasts": [],
            "primary_estimand": "Within-participant, within-activity reliability of peak vertical GRF.",
            "planned_reliability": "ICC(3,1) with participant as subject and trials as repeated measures.",
            "post_plan_rule": "The plan was registered after source acquisition and is labelled REGISTERED.",
            "immutability_rule": "Runs and evidence are append-only.",
        },
        "arm_counts": {"INTERVENTION": len(cohort_ids), "COMPARISON": 0},
        "position_counts": {"Recreational adult": len(cohort_ids)},
        "real_data": True,
        "source": source,
        "lineage_note": "Snapshot -> source artifact -> DOI/licence. Measurement qualification and reliability derive from matched raw signals.",
    }


def _attach_runtime(study: dict[str, Any]) -> dict[str, Any]:
    from . import realanalysis

    snapshot = get_snapshot(study["study"]["dataset_snapshot_id"])
    if snapshot is None:
        raise ValueError("Study snapshot is not admitted")
    runs = [run for run in realanalysis.list_runs() if run["study_id"] == study["study"]["id"]]
    evidence = [item for item in realanalysis.list_evidence() if item.get("study_id") == study["study"]["id"]]
    figures = [item for item in realanalysis.list_figures() if item.get("study_id") == study["study"]["id"]]
    investigations = [item for item in realanalysis.list_investigations() if item["study_id"] == study["study"]["id"]]
    return {
        **study,
        "snapshot": snapshot,
        "runs": runs,
        "evidence": evidence,
        "figures": figures,
        "data_health": _real_data_health(snapshot, study["study"]["id"]),
        "investigations": [
            {"id": item["id"], "title": item["title"], "status": item["status"], "block_count": len(item["blocks"])}
            for item in investigations
        ],
    }


def list_studies() -> list[dict[str, Any]]:
    result = []
    for study_id in (STUDY_MENDELEY, STUDY_MOVESMART):
        study = get_study(study_id)
        if study is None:
            continue
        runs = [run for run in _read_json(artifact_dir() / "real_runs.json", []) if run["study_id"] == study_id]
        evidence = [item for item in _read_json(artifact_dir() / "real_evidence.json", []) if item.get("study_id") == study_id]
        plan_status = study["plan"]["status"]
        result.append(
            {
                **study["study"],
                "plan_status": plan_status,
                "run_count": len(runs),
                "evidence_count": len(evidence),
                "last_run_at": max([run["created_at"] for run in runs], default=None),
                "investigation_ids": [item["id"] for item in study["investigations"]],
                "real_data": True,
            }
        )
    return result


def get_study(study_id: str) -> dict[str, Any] | None:
    if study_id == STUDY_MENDELEY:
        snapshot = snapshot_for_source("SRC-MENDELEY-6P99569X66")
        if snapshot is None:
            return None
        return _attach_runtime(_mendeley_study(snapshot))
    if study_id == STUDY_MOVESMART:
        snapshot = snapshot_for_source("SRC-ZENODO-17376717")
        if snapshot is None:
            return None
        return _attach_runtime(_movesmart_study(snapshot))
    return None


def real_study_ids() -> list[str]:
    return [STUDY_MENDELEY, STUDY_MOVESMART]


# --------------------------------------------------------------------------- #
# Report and lineage
# --------------------------------------------------------------------------- #


def _report_path(study_id: str) -> Path:
    return artifact_dir() / f"real_report_{study_id}.json"


def get_report(study_id: str) -> dict[str, Any]:
    from . import realanalysis

    default = {
        "id": f"REPORT-REAL-{study_id.split('-')[-1]}",
        "title": f"Evidence report · {study_id}",
        "study_id": study_id,
        "status": "DRAFT",
        "evidence_ids": [],
        "figure_ids": [],
        "sections": ["Intervention result", "Reliability context", "Exploratory results"],
        "citations": [],
        "provenance_note": "Every cited evidence artifact resolves to an AnalysisRun, a cohort, an immutable real-data snapshot and a DOI-identified source.",
        "created_at": _now(),
    }
    report = _read_json(_report_path(study_id), default)
    study = get_study(study_id)
    evidence = realanalysis.list_evidence()
    figures = realanalysis.list_figures()
    runs = realanalysis.list_runs()
    cited_evidence = [item for item in evidence if item["id"] in report.get("evidence_ids", [])]
    cited_figures = [item for item in figures if item["id"] in report.get("figure_ids", [])]
    run_ids = {item["analysis_run_id"] for item in cited_evidence}
    return {
        **report,
        "evidence": cited_evidence,
        "figures": cited_figures,
        "runs": [run for run in runs if run["id"] in run_ids],
        "snapshot": study["snapshot"] if study else {},
        "study": study["study"] if study else {},
        "question": study["question"] if study else {},
        "hypotheses": study["hypotheses"] if study else [],
        "plan": study["plan"] if study else {},
        "cohort": study["cohort"] if study else {},
        "groups": study["groups"] if study else {},
        "data_health": study["data_health"] if study else {},
        "longitudinal_signal": [],
    }


def _default_section(artifact_id: str, study_id: str) -> str:
    from . import realanalysis

    if artifact_id.startswith("FIG-REAL-"):
        figure = realanalysis.get_figure(artifact_id)
        evidence_ids = figure.get("evidence_ids", []) if figure else []
        evidence = realanalysis.get_evidence(evidence_ids[0]) if evidence_ids else None
    else:
        evidence = realanalysis.get_evidence(artifact_id)
    if study_id == STUDY_MOVESMART:
        # The primary result of the measurement study is reliability; the
        # descriptive signal audit is the qualification context.
        if evidence and evidence.get("kind") == "RELIABILITY":
            return "Intervention result"
        return "Reliability context"
    if evidence and evidence.get("kind") == "RELIABILITY":
        return "Reliability context"
    if evidence and evidence.get("kind") == "EFFECT":
        return "Intervention result"
    return "Exploratory results"


def cite(study_id: str, artifact_id: str, section: str | None = None) -> dict[str, Any]:
    report = _read_json(_report_path(study_id), get_report(study_id))
    section = section or _default_section(artifact_id, study_id)
    key = "figure_ids" if artifact_id.startswith("FIG-REAL-") else "evidence_ids"
    if artifact_id in report.get(key, []):
        return {"report_id": report["id"], "artifact_id": artifact_id, "section": section, "already_cited": True}
    report.setdefault(key, []).append(artifact_id)
    report.setdefault("citations", []).append(
        {"artifact_id": artifact_id, "section": section, "added_at": _now()}
    )
    report["updated_at"] = _now()
    _write_json(_report_path(study_id), report)
    return {"report_id": report["id"], "artifact_id": artifact_id, "section": section, "already_cited": False}


def uncite(study_id: str, artifact_id: str) -> dict[str, Any]:
    report = _read_json(_report_path(study_id), get_report(study_id))
    removed = False
    for key in ("evidence_ids", "figure_ids"):
        if artifact_id in report.get(key, []):
            report[key] = [item for item in report[key] if item != artifact_id]
            removed = True
    report["citations"] = [item for item in report.get("citations", []) if item["artifact_id"] != artifact_id]
    _write_json(_report_path(study_id), report)
    return {"removed": removed}


def lineage_graph(artifact_id: str) -> dict[str, Any]:
    from . import realanalysis

    studies = [study for study in (get_study(STUDY_MENDELEY), get_study(STUDY_MOVESMART)) if study]
    nodes: dict[str, dict[str, Any]] = {}
    edges: dict[str, dict[str, Any]] = {}

    def node(node_id: str, kind: str, label: str, metadata: str, detail: dict[str, Any] | None = None) -> None:
        nodes.setdefault(node_id, {"id": node_id, "kind": kind, "label": label, "metadata": metadata, "detail": detail or {}})

    def edge(source: str, target: str, relation: str, label: str) -> None:
        edge_id = f"LE-{source}->{target}"
        edges.setdefault(edge_id, {"id": edge_id, "source": source, "target": target, "relation": relation, "label": label})

    for study in studies:
        snapshot = study["snapshot"]
        source = study["source"]
        study_id = study["study"]["id"]
        source_node = f"SRC-{source['id'].split('-', 1)[1]}"
        artifact_node = f"SA-{source['id'].split('-', 1)[1]}"
        cohort_id = study["cohort"]["id"]
        node(source_node, "source", source["name"], f"DOI {source['doi']} · {source['license']['id']}", {"doi": source["doi"], "license": source["license"], "privacy": source["privacy"]})
        node(artifact_node, "source_artifact", source["files"][0]["name"], f"{source['files'][0]['size_bytes']:,} bytes · sha256 {source['files'][0].get('sha256', source['files'][0].get('md5', ''))[:16]}", source["files"][0])
        node(snapshot["id"], "snapshot", snapshot["label"], f"{sum(snapshot['row_counts'].values()):,} rows · immutable", {"checksums": snapshot["checksums"], "provenance": snapshot["provenance"]})
        node(cohort_id, "cohort", study["cohort"]["name"], f"n={len(study['cohort']['subject_ids'])}", study["cohort"])
        edge(source_node, artifact_node, "published_as", "source file")
        edge(artifact_node, snapshot["id"], "admitted_as", "licence + QC + harmonisation")
        edge(snapshot["id"], cohort_id, "restricted_to", "cohort")
        for spec in study["analysis_specs"]:
            node(spec["id"], "spec", spec["name"], f"{spec['method_id']} · {spec['status']}", spec)
            edge(cohort_id, spec["id"], "analysed_by", "frozen/registered specification")
        for run in study["runs"]:
            node(run["id"], "run", f"{run['method_id']} · {run['status']}", f"{run['created_at']} · {run.get('result_digest', '')[:12]}", run)
            edge(run["analysis_spec_id"], run["id"], "executed_as", "AnalysisRun")
            edge(snapshot["id"], run["id"], "read_from", "immutable input")
        for evidence in study["evidence"]:
            node(evidence["id"], "evidence", evidence["title"], f"{evidence['kind']} · {evidence['quality']}", evidence)
            edge(evidence["analysis_run_id"], evidence["id"], "promoted_to", "explicit promotion")
        for figure in study["figures"]:
            node(figure["id"], "figure", figure["title"], figure["kind"], figure)
            edge(figure["evidence_ids"][0], figure["id"], "rendered_as", "figure artifact")
        for report in [_read_json(_report_path(study_id), {})]:
            if report.get("evidence_ids"):
                node(report["id"], "report", report.get("title", "Report"), report.get("status", "DRAFT"), report)
                for evidence_id in report.get("evidence_ids", []):
                    edge(evidence_id, report["id"], "cited_in", "report citation")

    if artifact_id not in nodes:
        # A snapshot or source can be inspected directly.
        for candidate in nodes:
            if artifact_id in candidate:
                artifact_id = candidate
                break
    if artifact_id not in nodes:
        raise KeyError(f"Unknown real-data artifact: {artifact_id}")
    return {
        "artifact_id": artifact_id,
        "focus": nodes[artifact_id],
        "nodes": list(nodes.values()),
        "edges": list(edges.values()),
    }
