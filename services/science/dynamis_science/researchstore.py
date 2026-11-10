"""Persistent research projects, studies, monitoring programs and reports.

The scientific data (admitted Parquet snapshots) remain in the read-only
real-data store.  This module owns the mutable, scientist-authored research
metadata in a small transactional SQLite database under
``$DYNAMISSCIENCE_DATA_ROOT/research``.  It never writes into a snapshot and
never regenerates or deletes admitted data.

Design notes
------------
* Documents are JSON with an explicit schema version; every mutation appends an
  immutable version row.
* Optimistic concurrency is enforced with ``base_version``.
* Frozen cohorts, analysis plans, runs, evidence, figures and report versions
  are immutable.  A changed object is a new id or a new version.
* Archiving changes status only; it does not cascade or delete artifacts.
"""

from __future__ import annotations

import hashlib
import html
import json
import math
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import polars as pl

from . import realstore
from .data_root import paths

SCHEMA_VERSION = "dynamis-science.research@1.0.0"
DB_SCHEMA_VERSION = 1

STUDY_STATES = ("DRAFT", "READY", "ACTIVE", "ANALYSIS", "COMPLETED", "ARCHIVED")
ALLOWED_TRANSITIONS = {
    "DRAFT": {"READY", "ARCHIVED"},
    "READY": {"ACTIVE", "ANALYSIS", "DRAFT", "ARCHIVED"},
    "ACTIVE": {"ANALYSIS", "COMPLETED", "ARCHIVED"},
    "ANALYSIS": {"COMPLETED", "ACTIVE", "ARCHIVED"},
    "COMPLETED": {"ARCHIVED"},
    "ARCHIVED": {"DRAFT", "READY", "ACTIVE", "COMPLETED"},
}

DESIGN_LABELS = {
    "OBSERVATIONAL_LONGITUDINAL": "Observational longitudinal repeated measures",
    "REPEATED_MEASURES": "Repeated-measures measurement study",
    "MEASUREMENT_REPEATED_TRIALS": "Repeated-trial measurement study",
    "DESCRIPTIVE": "Descriptive study",
}

DESIGN_ALLOWED_TABLES = {
    "OBSERVATIONAL_LONGITUDINAL": {"cmj_occasions", "cmj_trials"},
    "REPEATED_MEASURES": {"cmj_occasions", "signal_trials", "cmj_trials"},
    "MEASUREMENT_REPEATED_TRIALS": {"signal_trials"},
    "DESCRIPTIVE": {"cmj_occasions", "signal_trials", "cmj_trials"},
}

INVESTIGATION_BLOCK_TYPES = frozenset(
    {
        "question", "dataset", "cohort", "schedule", "table", "explore",
        "force_trial", "match_event", "analysis", "diagnostics", "evidence",
        "model", "figure", "interpretation", "report_section",
    }
)
BLOCK_DEPENDENCY_KEYS = ("cohort_block_id", "analysis_block_id", "evidence_block_id")

METHODS: dict[str, dict[str, Any]] = {
    "METH-REAL-TREND": {
        "id": "METH-REAL-TREND",
        "name": "Linear mixed-effects change model",
        "version": "1.0.0",
        "qualification": {
            "status": "QUALIFIED",
            "record": "QUAL-REAL-MIXEDLM",
            "reference": "R 4.6.2 / lme4 2.1-0 (ML)",
            "basis": "Fixed effects, standard errors, log likelihood and variance components compared independently in RES-587.",
        },
        "supported_designs": ["OBSERVATIONAL_LONGITUDINAL", "REPEATED_MEASURES"],
        "required_tables": ["cmj_occasions"],
        "required_shape": "One row per subject and testing occasion; a numeric outcome; at least three subjects and eight complete observations.",
        "constraints": ["Single-arm within-subject change only.", "Occasions are not assumed to be equally spaced calendar time.", "No group or intervention contrast is inferred."],
        "missingness": "Complete-case at the outcome; missing rows are never imputed.",
        "parameter_schema": {
            "reference_occasion": {"type": "integer", "minimum": 1},
            "contrast_occasion": {"type": "integer", "minimum": 2},
            "alpha": {"type": "number", "default": 0.05},
        },
        "assumptions": ["Linear change on the model scale.", "Random intercept and random occasion slope for subject.", "Approximately normal residuals."],
        "diagnostics": ["optimizer selection and all attempts", "convergence", "residual summary", "residuals by occasion", "normal QQ", "sample and missingness context"],
        "output_schema": ["occasion slope with SE and 95% CI", "model-implied change between the selected occasions", "random-effect variances", "effect size against baseline SD"],
    },
    "METH-REAL-DESC": {
        "id": "METH-REAL-DESC",
        "name": "Descriptive occasion trajectory",
        "version": "1.0.0",
        "qualification": {"status": "QUALIFIED", "record": "QUAL-REAL-DESCRIPTIVE", "reference": "Independent deterministic recomputation", "basis": "Means, SD and normal 95% intervals recomputed from the snapshot in qualification."},
        "supported_designs": ["OBSERVATIONAL_LONGITUDINAL", "REPEATED_MEASURES", "DESCRIPTIVE"],
        "required_tables": ["cmj_occasions"],
        "required_shape": "One numeric outcome per subject and occasion.",
        "constraints": ["Descriptive only; no model-based inference.", "No causal claim."],
        "missingness": "Reported as missing; no imputation.",
        "parameter_schema": {},
        "assumptions": [],
        "diagnostics": ["occasion counts", "missingness", "normal 95% intervals"],
        "output_schema": ["occasion means", "SD", "95% CI", "first-to-last change"],
    },
    "METH-U-CHANGE": {
        "id": "METH-U-CHANGE",
        "name": "Individual change with measurement-error context",
        "version": "1.0.0",
        "qualification": {"status": "QUALIFIED_DESCRIPTIVE", "record": "QUAL-U-CHANGE", "reference": "Deterministic recomputation", "basis": "Descriptive change and cohort change SD; not a causal individual response."},
        "supported_designs": ["OBSERVATIONAL_LONGITUDINAL", "REPEATED_MEASURES", "DESCRIPTIVE"],
        "required_tables": ["cmj_occasions", "cmj_trials"],
        "required_shape": "Repeated numeric observations per subject with a reference and contrast occasion/week.",
        "constraints": ["Descriptive; no causal effect.", "Typical error is reported only when repeated same-session trials exist."],
        "missingness": "Complete pairs only; missing pairs are listed.",
        "parameter_schema": {"reference_week": {"type": "integer"}, "contrast_week": {"type": "integer"}},
        "assumptions": ["The selected observations are comparable."],
        "diagnostics": ["paired counts", "cohort change SD", "typical error where estimable"],
        "output_schema": ["individual changes", "median change", "standardised change", "typical error context"],
    },
    "METH-REAL-RELIABILITY": {
        "id": "METH-REAL-RELIABILITY",
        "name": "Repeated-trial reliability (ICC 3,1)",
        "version": "1.1.0",
        "qualification": {"status": "QUALIFIED", "record": "QUAL-REAL-RELIABILITY", "reference": "statsmodels OLS two-way ANOVA; R aov cross-check", "basis": "RES-619: ICC(3,1) uses the two-way residual mean square and trials in acquisition order; 1.0.0 used the one-way within mean square on value-sorted trials and is superseded."},
        "supported_designs": ["REPEATED_MEASURES", "MEASUREMENT_REPEATED_TRIALS"],
        "required_tables": ["signal_trials"],
        "required_shape": "At least three subjects with at least two repeated trials in the same activity.",
        "constraints": ["Balanced subset of the first k trials per subject in acquisition order.", "Within-activity reliability; not device agreement.", "Not a longitudinal adaptation claim."],
        "missingness": "Unbalanced trials are excluded from the balanced matrix and counted.",
        "parameter_schema": {"activity": {"type": "string"}, "max_trials": {"type": "integer", "minimum": 2, "maximum": 8}},
        "assumptions": ["Participants are the random subject effect.", "Trials are the fixed repeated measure.", "The activity is identical across compared trials."],
        "diagnostics": ["balanced design", "trials used and excluded", "ICC F-based 95% CI", "within-subject CV", "typical error (sqrt two-way MSE)", "ICC(1,1) and ICC(2,1) sensitivity"],
        "output_schema": ["ICC(3,1)", "95% CI", "typical error", "mean within-subject CV", "95% minimal detectable change"],
    },
    "METH-REAL-SIGNAL-QA": {
        "id": "METH-REAL-SIGNAL-QA",
        "name": "Force-plate and IMU signal qualification",
        "version": "1.0.0",
        "qualification": {"status": "QUALIFIED", "record": "QUAL-REAL-SIGNAL", "reference": "Independent NumPy re-derivation", "basis": "Four representative trials re-derived exactly; saturation and clock-offset checks recorded in RES-587."},
        "supported_designs": ["MEASUREMENT_REPEATED_TRIALS", "DESCRIPTIVE"],
        "required_tables": ["signal_trials"],
        "required_shape": "Trial-level native signal summaries with sampling rate and activity.",
        "constraints": ["No CMJ claim.", "No sample-level IMU-to-force synchronisation claim.", "Device clock offsets are reported, not corrected."],
        "missingness": "Trials without matched signals are not analysed and are counted.",
        "parameter_schema": {},
        "assumptions": ["Force_Z is vertical in the local plate frame.", "The sum of available plates represents total vertical GRF."],
        "diagnostics": ["sampling rate", "saturation", "plate coverage", "NaN trials", "device clock offset", "body-weight comparison"],
        "output_schema": ["activity-level summaries", "IMU sampling and gravity checks", "body-weight bias and limits of agreement"],
    },
    "METH-U-DESC": {
        "id": "METH-U-DESC",
        "name": "Descriptive longitudinal summary",
        "version": "1.0.0",
        "qualification": {"status": "QUALIFIED_DESCRIPTIVE", "record": "QUAL-U-DESC", "reference": "Deterministic recomputation", "basis": "Mean, SD and 95% interval computed from the selected snapshot and cohort."},
        "supported_designs": ["OBSERVATIONAL_LONGITUDINAL", "REPEATED_MEASURES", "MEASUREMENT_REPEATED_TRIALS", "DESCRIPTIVE"],
        "required_tables": ["cmj_occasions", "cmj_trials", "signal_trials"],
        "required_shape": "A numeric outcome identified by the snapshot metric registry.",
        "constraints": ["Descriptive only.", "No model or causal claim."],
        "missingness": "Reported per axis point; no imputation.",
        "parameter_schema": {},
        "assumptions": [],
        "diagnostics": ["counts per axis point", "missing counts", "interval method"],
        "output_schema": ["per-axis mean", "SD", "95% CI", "coverage"],
    },
}

REJECTED_METHODS = {
    "METH-REAL-BODYWEIGHT": {
        "id": "METH-REAL-BODYWEIGHT",
        "name": "Body-weight recovery from support-window mean force",
        "qualification": {"status": "REJECTED", "record": "QUAL-REAL-SIGNAL", "reference": "Bias and limits of agreement", "basis": "Tested and rejected: bias −169 N (−22.9%), SD 115 N, 95% LoA −395 to +57 N."},
        "reason": "The estimator did not recover body weight within a defensible tolerance and is not offered for execution.",
    }
}


class ResearchNotFound(LookupError):
    pass


class ResearchConflict(RuntimeError):
    pass


class ResearchValidation(ValueError):
    pass


def validate_investigation_blocks(blocks: list[dict[str, Any]]) -> None:
    seen: set[str] = set()
    for block in blocks:
        if not isinstance(block, dict):
            raise ResearchValidation("Investigation blocks must be JSON objects")
        block_id = block.get("id")
        block_type = block.get("type")
        state = block.get("state", {})
        if not isinstance(block_id, str) or not block_id.strip():
            raise ResearchValidation("Investigation blocks require a non-empty ID")
        if not isinstance(block_type, str) or block_type not in INVESTIGATION_BLOCK_TYPES:
            raise ResearchValidation(f"Unknown block type: {block_type}")
        if not isinstance(block.get("title"), str) or not block["title"].strip():
            raise ResearchValidation(f"{block_id} requires a title")
        if not isinstance(state, dict):
            raise ResearchValidation(f"{block_id} state must be a JSON object")
        if block_id in seen:
            raise ResearchValidation(f"Duplicate block ID: {block_id}")
        for key in BLOCK_DEPENDENCY_KEYS:
            reference = state.get(key)
            if reference and (not isinstance(reference, str) or reference not in seen):
                raise ResearchValidation(
                    f"{block_id} depends on {reference}, which must appear earlier in the investigation"
                )
        seen.add(block_id)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _db_path() -> Path:
    directory = paths()["research"]
    directory.mkdir(parents=True, exist_ok=True)
    return directory / "research.db"


_SCHEMA = (
    """CREATE TABLE IF NOT EXISTS projects (
        id TEXT PRIMARY KEY,
        version INTEGER NOT NULL,
        status TEXT NOT NULL,
        document TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        archived_at TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS project_versions (
        project_id TEXT NOT NULL,
        version INTEGER NOT NULL,
        change_type TEXT NOT NULL,
        document TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY (project_id, version)
    )""",
    """CREATE TABLE IF NOT EXISTS entities (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        kind TEXT NOT NULL,
        version INTEGER NOT NULL,
        state TEXT NOT NULL,
        document TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        archived_at TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS entity_versions (
        entity_id TEXT NOT NULL,
        version INTEGER NOT NULL,
        change_type TEXT NOT NULL,
        document TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY (entity_id, version)
    )""",
    """CREATE TABLE IF NOT EXISTS cohorts (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        version INTEGER NOT NULL,
        status TEXT NOT NULL,
        snapshot_id TEXT NOT NULL,
        parent_id TEXT,
        document TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS cohort_versions (
        cohort_id TEXT NOT NULL,
        version INTEGER NOT NULL,
        change_type TEXT NOT NULL,
        document TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY (cohort_id, version)
    )""",
    """CREATE TABLE IF NOT EXISTS plans (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        version INTEGER NOT NULL,
        status TEXT NOT NULL,
        snapshot_id TEXT NOT NULL,
        cohort_id TEXT NOT NULL,
        parent_id TEXT,
        spec_id TEXT,
        content_hash TEXT,
        document TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        frozen_at TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS plan_versions (
        plan_id TEXT NOT NULL,
        version INTEGER NOT NULL,
        change_type TEXT NOT NULL,
        document TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY (plan_id, version)
    )""",
    """CREATE TABLE IF NOT EXISTS investigations (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        version INTEGER NOT NULL,
        status TEXT NOT NULL,
        parent_id TEXT,
        document TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS investigation_versions (
        investigation_id TEXT NOT NULL,
        version INTEGER NOT NULL,
        document TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY (investigation_id, version)
    )""",
    """CREATE TABLE IF NOT EXISTS runs (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        snapshot_id TEXT NOT NULL,
        cohort_id TEXT NOT NULL,
        plan_id TEXT,
        spec_id TEXT NOT NULL,
        method_id TEXT NOT NULL,
        document TEXT NOT NULL,
        result_digest TEXT NOT NULL,
        reproducibility_key TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS evidence (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        run_id TEXT NOT NULL UNIQUE,
        document TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS figures (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        run_id TEXT NOT NULL,
        evidence_id TEXT NOT NULL,
        document TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS reports (
        entity_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        version INTEGER NOT NULL,
        status TEXT NOT NULL,
        document TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS report_versions (
        entity_id TEXT NOT NULL,
        version INTEGER NOT NULL,
        status TEXT NOT NULL,
        content_hash TEXT NOT NULL,
        document TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY (entity_id, version)
    )""",
    """CREATE TABLE IF NOT EXISTS audit (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        at TEXT NOT NULL,
        action TEXT NOT NULL,
        object_type TEXT NOT NULL,
        object_id TEXT NOT NULL,
        detail TEXT
    )""",
)


def _ensure_schema(connection: sqlite3.Connection) -> None:
    version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if version >= DB_SCHEMA_VERSION:
        return
    connection.execute("BEGIN IMMEDIATE")
    try:
        for statement in _SCHEMA:
            connection.execute(statement)
        connection.execute(f"PRAGMA user_version={DB_SCHEMA_VERSION}")
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise


@contextmanager
def _connect():
    connection = sqlite3.connect(str(_db_path()), timeout=30, isolation_level=None)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA foreign_keys=ON")
        _ensure_schema(connection)
        yield connection
    finally:
        connection.close()


@contextmanager
def _tx():
    with _connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            yield connection
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise


def _audit(connection: sqlite3.Connection, action: str, object_type: str, object_id: str, detail: Any = None) -> None:
    connection.execute(
        "INSERT INTO audit (at, action, object_type, object_id, detail) VALUES (?, ?, ?, ?, ?)",
        (_now(), action, object_type, object_id, _canonical(detail) if detail is not None else None),
    )


def _row_document(row: sqlite3.Row) -> dict[str, Any]:
    document = json.loads(row["document"])
    for key in ("version", "state", "status"):
        if key in row.keys() and key not in document:
            document[key] = row[key]
    return document


def _new_id(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(4).upper()}"


# --------------------------------------------------------------------------- #
# Dataset catalogue
# --------------------------------------------------------------------------- #


def _synthetic_snapshot() -> dict[str, Any] | None:
    from .generate import ARTIFACT_DIR

    path = ARTIFACT_DIR / "dataset_snapshot.json"
    if not path.exists():
        return None
    manifest = json.loads(path.read_text(encoding="utf-8"))
    return {
        **manifest,
        "real_data": False,
        "synthetic": True,
        "source": {
            "id": "SRC-SYNTHETIC",
            "doi": None,
            "url": None,
            "license": {"id": "SYNTHETIC"},
            "publisher": "DynamisScience deterministic generator",
            "privacy": {"classification": "SYNTHETIC"},
            "classification": "SYNTHETIC",
            "attribution": "Deterministic synthetic data generated locally; no real athletes or measurements.",
        },
    }


def _real_snapshot(snapshot_id: str) -> dict[str, Any] | None:
    snapshot = realstore.get_snapshot(snapshot_id)
    if snapshot is not None:
        return snapshot
    from .admission import get_admitted_snapshot

    return get_admitted_snapshot(snapshot_id)


def get_snapshot(snapshot_id: str) -> dict[str, Any] | None:
    real = _real_snapshot(snapshot_id)
    if real is not None:
        return {
            **real,
            "real_data": bool(real.get("real_data", True)),
            "synthetic": bool(real.get("synthetic", False)),
        }
    synthetic = _synthetic_snapshot()
    if synthetic is not None and synthetic.get("id") == snapshot_id:
        return synthetic
    return None


def list_snapshots() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    synthetic = _synthetic_snapshot()
    if synthetic is not None:
        result.append(synthetic)
    result.extend({**item, "real_data": True, "synthetic": False} for item in realstore.list_snapshots())
    from .admission import list_admitted_snapshots

    result.extend(
        snapshot
        for item in list_admitted_snapshots()
        if (snapshot := get_snapshot(item["id"])) is not None
    )
    return result


def read_snapshot_table(snapshot_id: str, table: str) -> pl.DataFrame:
    real = _real_snapshot(snapshot_id)
    if real is not None:
        if real.get("admitted_source"):
            if table == "subjects" and table not in _table_names(real):
                observation_table = next(
                    (name for name in ("cmj_trials", "sprint_trials") if name in _table_names(real)),
                    None,
                )
                if observation_table is None:
                    raise ResearchNotFound(f"Snapshot {snapshot_id} has no participant identifiers")
                path = paths()["admitted"] / snapshot_id / f"{observation_table}.parquet"
                schema = pl.read_parquet_schema(path)
                if "subject_id" not in schema:
                    raise ResearchValidation(f"Snapshot {snapshot_id} has no subject_id column")
                fields = [pl.col("subject_id")]
                fields.extend(
                    pl.col(name)
                    for name in ("display_id", "position")
                    if name in schema
                )
                frame = (
                    pl.scan_parquet(path)
                    .select(fields)
                    .unique(subset=["subject_id"], maintain_order=True)
                    .collect(engine="streaming")
                )
                if "display_id" not in frame.columns:
                    frame = frame.with_columns(pl.col("subject_id").alias("display_id"))
                if "position" not in frame.columns:
                    frame = frame.with_columns(pl.lit("Participant").alias("position"))
                return frame
            if table not in _table_names(real):
                raise ResearchNotFound(f"Table {table} is not in snapshot {snapshot_id}")
            path = paths()["admitted"] / snapshot_id / f"{table}.parquet"
            if not path.is_file():
                raise ResearchNotFound(f"Table {table} is unavailable in snapshot {snapshot_id}")
            return pl.read_parquet(path)
        return realstore.read_table(snapshot_id, table)
    synthetic = _synthetic_snapshot()
    if synthetic is not None and synthetic.get("id") == snapshot_id:
        from .generate import PARQUET_DIR

        path = PARQUET_DIR / f"{table}.parquet"
        return pl.read_parquet(path) if path.exists() else pl.DataFrame()
    raise ResearchNotFound(f"Snapshot {snapshot_id} is not admitted")


def _table_names(snapshot: dict[str, Any]) -> list[str]:
    return sorted(snapshot.get("tables", {}).keys()) or sorted(snapshot.get("row_counts", {}).keys())


def dataset_metrics(snapshot_id: str) -> list[dict[str, Any]]:
    snapshot = get_snapshot(snapshot_id)
    if snapshot is None:
        raise ResearchNotFound(f"Snapshot {snapshot_id} is not admitted")
    if snapshot.get("real_data") and not snapshot.get("admitted_source"):
        from .realanalysis import METRICS

        tables = set(_table_names(snapshot))
        result = []
        for metric_id, definition in METRICS.items():
            if definition["table"] not in tables:
                continue
            result.append(
                {
                    "id": metric_id,
                    "metric_id": metric_id,
                    "label": definition["label"],
                    "unit": definition["unit"],
                    "column": definition["column"],
                    "table": definition["table"],
                    "definition_id": definition["id"],
                    "source_column": definition.get("source_column"),
                    "status": "ACTIVE",
                    "role": "PRIMARY" if metric_id in {"MET-REAL-CMJ-HEIGHT", "MET-REAL-FZ-PEAK"} else "SECONDARY",
                }
            )
        return result
    # Synthetic fixture: keep the same metric identities used by the accepted UI.
    tables = set(_table_names(snapshot))
    if snapshot.get("admitted_source") and not (tables & {"cmj_trials"}):
        return []
    candidates = [
        ("MET-CMJ-IMPULSE", "Concentric impulse", "N·s·kg⁻¹", "concentric_impulse_n_s_kg", "cmj_trials", "PRIMARY"),
        ("MET-CMJ-HEIGHT", "Jump height (flight time)", "cm", "jump_height_cm", "cmj_trials", "SECONDARY"),
        ("MET-CMJ-BRAKING-DURATION", "Eccentric braking duration", "s", "eccentric_braking_duration_s", "cmj_trials", "SECONDARY"),
        ("MET-CMJ-POWER", "Peak power", "W·kg⁻¹", "peak_power_w_kg", "cmj_trials", "SECONDARY"),
        ("MET-CMJ-DEPTH", "Countermovement depth", "cm", "countermovement_depth_cm", "cmj_trials", "SECONDARY"),
        ("MET-CMJ-RSI-MOD", "RSI-mod", "cm·s⁻¹", "rsi_mod", "cmj_trials", "CONTEXT"),
    ]
    result = [
        {"id": metric_id, "metric_id": metric_id, "label": label, "unit": unit, "column": column, "table": table, "definition_id": metric_id, "status": "ACTIVE", "role": role}
        for metric_id, label, unit, column, table, role in candidates
        if table in tables
    ]
    if snapshot.get("admitted_source"):
        import pyarrow.parquet as pq

        path = paths()["admitted"] / snapshot_id / "cmj_trials.parquet"
        columns = set(pq.ParquetFile(path).schema_arrow.names)
        result = [item for item in result if item["column"] in columns]
    return result


def dataset_catalogue() -> list[dict[str, Any]]:
    result = []
    for snapshot in list_snapshots():
        used = [
            entity["id"]
            for entity in list_entities()
            if entity.get("dataset_snapshot_id") == snapshot["id"]
        ]
        result.append(
            {
                "id": snapshot["id"],
                "label": snapshot.get("label"),
                "synthetic": bool(snapshot.get("synthetic")),
                "real_data": bool(snapshot.get("real_data")),
                "source": snapshot.get("source", {}),
                "row_counts": snapshot.get("row_counts", {}),
                "checksums": snapshot.get("checksums", {}),
                "tables": _table_names(snapshot),
                "metrics": dataset_metrics(snapshot["id"]),
                "subjects": snapshot.get("subjects", {}),
                "used_by_studies": used,
            }
        )
    return result


def methods_for_snapshot(snapshot_id: str) -> list[dict[str, Any]]:
    snapshot = get_snapshot(snapshot_id)
    if snapshot is None:
        raise ResearchNotFound(f"Snapshot {snapshot_id} is not admitted")
    tables = set(_table_names(snapshot))
    result = []
    for method in METHODS.values():
        if set(method["required_tables"]) & tables:
            result.append(method)
    return result


# --------------------------------------------------------------------------- #
# Projects
# --------------------------------------------------------------------------- #


def create_project(title: str, description: str = "", objectives: list[str] | None = None, dataset_snapshot_ids: list[str] | None = None) -> dict[str, Any]:
    title = title.strip()
    if not title:
        raise ResearchValidation("A project title is required")
    dataset_ids = sorted(set(dataset_snapshot_ids or []))
    for snapshot_id in dataset_ids:
        if get_snapshot(snapshot_id) is None:
            raise ResearchValidation(f"Snapshot {snapshot_id} is not admitted")
    now = _now()
    project = {
        "id": _new_id("PRJ"),
        "schema_version": SCHEMA_VERSION,
        "title": title,
        "description": description.strip(),
        "objectives": [item.strip() for item in (objectives or []) if item.strip()],
        "dataset_snapshot_ids": dataset_ids,
        "status": "ACTIVE",
        "version": 1,
        "created_at": now,
        "updated_at": now,
        "archived_at": None,
    }
    with _tx() as connection:
        connection.execute(
            "INSERT INTO projects (id, version, status, document, created_at, updated_at, archived_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (project["id"], 1, "ACTIVE", _canonical(project), now, now, None),
        )
        connection.execute(
            "INSERT INTO project_versions (project_id, version, change_type, document, created_at) VALUES (?, ?, ?, ?, ?)",
            (project["id"], 1, "CREATED", _canonical(project), now),
        )
        _audit(connection, "project.created", "project", project["id"], {"title": title})
    return project


def list_projects(include_archived: bool = False) -> list[dict[str, Any]]:
    with _connect() as connection:
        rows = connection.execute("SELECT * FROM projects ORDER BY created_at").fetchall()
    projects = [_row_document(row) for row in rows]
    if not include_archived:
        projects = [item for item in projects if item.get("status") != "ARCHIVED"]
    for project in projects:
        entities = list_entities(project["id"], include_archived=include_archived)
        project["study_ids"] = [item["id"] for item in entities if item["kind"] == "STUDY"]
        project["monitoring_program_ids"] = [item["id"] for item in entities if item["kind"] == "MONITORING"]
        project["study_count"] = len(project["study_ids"])
        project["program_count"] = len(project["monitoring_program_ids"])
    return projects


def _entity_summary(entity: dict[str, Any]) -> dict[str, Any]:
    runs = list_runs(entity["id"])
    evidence = list_evidence(entity["id"])
    plan = get_plan(entity.get("analysis_plan_id") or "") if entity.get("analysis_plan_id") else None
    cohort = get_cohort(entity.get("cohort_id") or "") if entity.get("cohort_id") else None
    resolved = (cohort or {}).get("resolved") or {}
    participants = int(resolved.get("n") or len((cohort or {}).get("subject_ids", [])))
    return {
        **{key: value for key, value in entity.items() if key not in {"dataset_snapshot_id"}},
        "dataset_snapshot_id": entity["dataset_snapshot_id"],
        "participant_count": participants,
        "plan_status": plan["status"] if plan else "DRAFT",
        "run_count": len(runs),
        "evidence_count": len(evidence),
        "last_run_at": max((run["created_at"] for run in runs), default=None),
        "investigation_ids": [item["id"] for item in list_investigations(entity["id"])],
        "real_data": bool((get_snapshot(entity["dataset_snapshot_id"]) or {}).get("real_data")),
    }


def get_project(project_id: str, include_archived: bool = True) -> dict[str, Any] | None:
    with _connect() as connection:
        row = connection.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if row is None:
        return None
    project = _row_document(row)
    if not include_archived and project.get("status") == "ARCHIVED":
        return None
    entities = list_entities(project_id, include_archived=True)
    summaries = [_entity_summary(item) for item in entities]
    project["studies"] = [item for item in summaries if item["kind"] == "STUDY"]
    project["monitoring_programs"] = [item for item in summaries if item["kind"] == "MONITORING"]
    project["study_ids"] = [item["id"] for item in project["studies"]]
    project["monitoring_program_ids"] = [item["id"] for item in project["monitoring_programs"]]
    project["datasets"] = [
        dataset for dataset in dataset_catalogue() if dataset["id"] in set(project.get("dataset_snapshot_ids", [])) | {item.get("dataset_snapshot_id") for item in entities}
    ]
    return project


def update_project(project_id: str, patch: dict[str, Any], base_version: int | None = None) -> dict[str, Any]:
    with _tx() as connection:
        row = connection.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if row is None:
            raise ResearchNotFound(f"Project {project_id} not found")
        project = _row_document(row)
        if project.get("status") == "ARCHIVED":
            raise ResearchConflict("Archived projects cannot be edited; restore the project first")
        if base_version is not None and int(base_version) != int(project["version"]):
            raise ResearchConflict(f"Project is at version {project['version']}, not {base_version}")
        for key in ("title", "description", "objectives", "dataset_snapshot_ids"):
            if key in patch:
                project[key] = patch[key]
        if not str(project.get("title", "")).strip():
            raise ResearchValidation("A project title is required")
        for snapshot_id in project.get("dataset_snapshot_ids", []):
            if get_snapshot(snapshot_id) is None:
                raise ResearchValidation(f"Snapshot {snapshot_id} is not admitted")
        project["objectives"] = [str(item).strip() for item in project.get("objectives", []) if str(item).strip()]
        project["version"] = int(project["version"]) + 1
        project["updated_at"] = _now()
        connection.execute(
            "UPDATE projects SET version = ?, document = ?, updated_at = ? WHERE id = ?",
            (project["version"], _canonical(project), project["updated_at"], project_id),
        )
        connection.execute(
            "INSERT INTO project_versions (project_id, version, change_type, document, created_at) VALUES (?, ?, ?, ?, ?)",
            (project_id, project["version"], "UPDATED", _canonical(project), project["updated_at"]),
        )
        _audit(connection, "project.updated", "project", project_id, patch)
    return project


def set_project_archived(project_id: str, archived: bool) -> dict[str, Any]:
    with _tx() as connection:
        row = connection.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if row is None:
            raise ResearchNotFound(f"Project {project_id} not found")
        project = _row_document(row)
        project["status"] = "ARCHIVED" if archived else "ACTIVE"
        project["archived_at"] = _now() if archived else None
        project["version"] = int(project["version"]) + 1
        project["updated_at"] = _now()
        connection.execute(
            "UPDATE projects SET version = ?, status = ?, document = ?, updated_at = ?, archived_at = ? WHERE id = ?",
            (project["version"], project["status"], _canonical(project), project["updated_at"], project["archived_at"], project_id),
        )
        connection.execute(
            "INSERT INTO project_versions (project_id, version, change_type, document, created_at) VALUES (?, ?, ?, ?, ?)",
            (project_id, project["version"], "ARCHIVED" if archived else "RESTORED", _canonical(project), project["updated_at"]),
        )
        _audit(connection, "project.archived" if archived else "project.restored", "project", project_id)
    return project


def project_history(project_id: str) -> list[dict[str, Any]]:
    with _connect() as connection:
        rows = connection.execute(
            "SELECT version, change_type, document, created_at FROM project_versions WHERE project_id = ? ORDER BY version DESC",
            (project_id,),
        ).fetchall()
    return [{**json.loads(row["document"]), "change_type": row["change_type"], "version": row["version"], "recorded_at": row["created_at"]} for row in rows]


# --------------------------------------------------------------------------- #
# Studies and monitoring programs
# --------------------------------------------------------------------------- #


def _axis_for_table(table: str) -> tuple[str, str]:
    if table == "cmj_occasions":
        return "occasion", "Testing occasion"
    if table == "cmj_trials":
        return "week", "Week"
    if table == "signal_trials":
        return "activity", "Activity"
    return "row", "Observation"


def _default_schedule(snapshot_id: str, primary_metric_id: str) -> dict[str, Any]:
    snapshot = get_snapshot(snapshot_id)
    metrics = dataset_metrics(snapshot_id)
    metric = next((item for item in metrics if item["id"] == primary_metric_id), metrics[0] if metrics else None)
    if metric is None:
        return {"kind": "UNSCHEDULED", "points": [], "label": "No schedule", "note": "No compatible metric."}
    frame = read_snapshot_table(snapshot_id, metric["table"])
    axis, label = _axis_for_table(metric["table"])
    values = frame[axis].drop_nulls().unique().to_list() if axis in frame.columns and frame.height else []
    points = sorted({int(value) for value in values}) if axis in {"occasion", "week", "trial_number"} else sorted(str(value) for value in values)
    return {
        "kind": "OBSERVED_OCCASIONS" if axis == "occasion" else ("OBSERVED_WEEKS" if axis == "week" else "OBSERVED_ACTIVITIES"),
        "axis": axis,
        "label": label,
        "points": points,
        "note": (
            "These are deposited testing occasions, not calendar weeks."
            if axis == "occasion"
            else ("These are deposited repeated trials, not a longitudinal season." if axis == "activity" else "Deposited observed schedule.")
        ),
    }


def _protocol_for_snapshot(snapshot_id: str, metric: dict[str, Any]) -> dict[str, Any]:
    snapshot = get_snapshot(snapshot_id) or {}
    source = snapshot.get("source", {})
    return {
        "id": f"PROT-U-{snapshot_id.split('-')[-1]}",
        "name": f"{metric['label']} acquisition",
        "description": f"Observation table {metric['table']} in admitted snapshot {snapshot_id}; native values retained.",
        "frequency": "as deposited",
        "status": "FROZEN",
        "duration_weeks": 0,
        "visit_labels": [],
        "measurement_family": "REAL_DATA" if snapshot.get("real_data") else "SYNTHETIC",
        "source_doi": source.get("doi"),
    }


def _hypothesis_id(index: int) -> str:
    return f"H-U-{index + 1:03d}"


def _normalise_hypotheses(values: Any, question_id: str, statement: str) -> list[dict[str, Any]]:
    if not values:
        return [
            {
                "id": _hypothesis_id(0),
                "question_id": question_id,
                "statement": statement,
                "direction": "change",
                "status": "PRIMARY",
                "rationale": "The primary research question.",
            }
        ]
    result = []
    for index, item in enumerate(values):
        if isinstance(item, str):
            result.append(
                {
                    "id": _hypothesis_id(index),
                    "question_id": question_id,
                    "statement": item.strip(),
                    "direction": "change",
                    "status": "PRIMARY" if index == 0 else "SECONDARY",
                    "rationale": "",
                }
            )
        elif isinstance(item, dict):
            result.append(
                {
                    "id": str(item.get("id") or _hypothesis_id(index)),
                    "question_id": question_id,
                    "statement": str(item.get("statement", "")).strip(),
                    "direction": str(item.get("direction", "change")),
                    "status": str(item.get("status", "PRIMARY" if index == 0 else "SECONDARY")),
                    "rationale": str(item.get("rationale", "")),
                }
            )
    if not result:
        raise ResearchValidation("At least one hypothesis is required")
    return result


def _default_cohort_definition(metric: dict[str, Any], snapshot_id: str) -> dict[str, Any]:
    return {
        "include_subject_ids": [],
        "exclude_subject_ids": [],
        "rules": [],
        "require_metric_id": metric["id"],
        "min_metric_observations": 1,
        "activity": "Walking" if metric["table"] == "signal_trials" else None,
        "snapshot_id": snapshot_id,
    }


def _default_plan(study: dict[str, Any], metric: dict[str, Any], cohort: dict[str, Any]) -> dict[str, Any]:
    methods = methods_for_snapshot(study["dataset_snapshot_id"])
    preferred = next(
        (
            method
            for method in methods
            if method["id"] in {"METH-REAL-TREND", "METH-REAL-RELIABILITY", "METH-U-DESC"}
            and metric["id"] in _metric_ids_for_method(method["id"], study["dataset_snapshot_id"])
        ),
        methods[0] if methods else METHODS["METH-U-DESC"],
    )
    parameters: dict[str, Any] = {}
    if preferred["id"] == "METH-REAL-TREND":
        frame = read_snapshot_table(study["dataset_snapshot_id"], metric["table"])
        occasions = sorted(int(value) for value in frame["occasion"].drop_nulls().unique().to_list()) if "occasion" in frame.columns else [1, 2]
        parameters = {"reference_occasion": occasions[0], "contrast_occasion": occasions[-1], "alpha": 0.05}
    elif preferred["id"] == "METH-REAL-RELIABILITY":
        parameters = {"activity": "Walking", "max_trials": 8}
    return {
        "id": _new_id("PLAN"),
        "study_id": study["id"],
        "name": f"Primary {preferred['name'].lower()} plan",
        "status": "DRAFT",
        "version": 1,
        "method_id": preferred["id"],
        "method_version": preferred["version"],
        "outcome_metric_id": metric["id"],
        "cohort_id": cohort["id"],
        "snapshot_id": study["dataset_snapshot_id"],
        "primary_estimand": _estimand_for_method(preferred["id"], metric),
        "hypotheses": [item["id"] for item in study.get("hypotheses", [])],
        "covariates": [],
        "fixed_effects": ["intercept"],
        "random_effects": ["subject intercept"] if preferred["id"] == "METH-REAL-TREND" else [],
        "time_coding": "occasion centred on the reference occasion" if preferred["id"] == "METH-REAL-TREND" else "not applicable",
        "contrasts": ["primary estimand"],
        "inclusion_criteria": "Resolved cohort definition.",
        "exclusion_criteria": [],
        "missing_data": "Complete-case at the outcome; no imputation.",
        "diagnostics": METHODS.get(preferred["id"], {}).get("diagnostics", []),
        "parameters": parameters,
        "planned_models": [preferred["name"]],
        "planned_reliability": "Not planned unless a repeated-trial method is selected.",
        "prospective": False,
        "frozen_before_inspection": False,
        "parent_id": None,
        "spec_id": None,
        "content_hash": None,
        "frozen_at": None,
        "created_at": _now(),
        "updated_at": _now(),
    }


def _metric_ids_for_method(method_id: str, snapshot_id: str) -> set[str]:
    metrics = dataset_metrics(snapshot_id)
    if method_id in {"METH-REAL-RELIABILITY", "METH-REAL-SIGNAL-QA", "METH-REAL-BODYWEIGHT"}:
        return {item["id"] for item in metrics if item["table"] == "signal_trials"}
    if method_id == "METH-REAL-TREND":
        return {item["id"] for item in metrics if item["table"] == "cmj_occasions"}
    return {item["id"] for item in metrics}


def _estimand_for_method(method_id: str, metric: dict[str, Any]) -> str:
    if method_id == "METH-REAL-TREND":
        return f"Within-subject change in {metric['label'].lower()} per testing occasion."
    if method_id == "METH-REAL-RELIABILITY":
        return f"Trial-to-trial reliability of {metric['label'].lower()} within subject and activity."
    if method_id == "METH-REAL-SIGNAL-QA":
        return "Sampling, saturation, support detection and device-clock consistency of the deposited signals."
    return f"Descriptive trajectory of {metric['label'].lower()}."


def _validate_design(design: str, table: str) -> None:
    if design not in DESIGN_ALLOWED_TABLES:
        raise ResearchValidation(f"Unsupported study design: {design}")
    if table not in DESIGN_ALLOWED_TABLES[design]:
        raise ResearchValidation(f"Design {design} is not supported by observation table {table}")


def create_study(project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    project = get_project(project_id)
    if project is None:
        raise ResearchNotFound(f"Project {project_id} not found")
    if project["status"] == "ARCHIVED":
        raise ResearchConflict("Cannot add a study to an archived project")
    title = str(payload.get("title", "")).strip()
    question = str(payload.get("research_question") or payload.get("question") or "").strip()
    snapshot_id = str(payload.get("dataset_snapshot_id", "")).strip()
    metric_id = str(payload.get("primary_metric_id", "")).strip()
    if not title or not question or not snapshot_id or not metric_id:
        raise ResearchValidation("title, research_question, dataset_snapshot_id and primary_metric_id are required")
    snapshot = get_snapshot(snapshot_id)
    if snapshot is None:
        raise ResearchValidation(f"Snapshot {snapshot_id} is not admitted")
    metrics = dataset_metrics(snapshot_id)
    metric = next((item for item in metrics if item["id"] == metric_id), None)
    if metric is None:
        raise ResearchValidation(f"Metric {metric_id} is not present in {snapshot_id}")
    design = str(payload.get("design") or ("MEASUREMENT_REPEATED_TRIALS" if metric["table"] == "signal_trials" else "OBSERVATIONAL_LONGITUDINAL"))
    _validate_design(design, metric["table"])
    secondary_ids = [str(item) for item in payload.get("secondary_metric_ids", []) if str(item) in {entry["id"] for entry in metrics} and str(item) != metric_id]
    question_id = _new_id("RQ-U")
    hypotheses = _normalise_hypotheses(payload.get("hypotheses"), question_id, question)
    study_id = _new_id("STUDY-U")
    schedule = payload.get("schedule") or _default_schedule(snapshot_id, metric_id)
    protocol = _protocol_for_snapshot(snapshot_id, metric)
    now = _now()
    study = {
        "id": study_id,
        "project_id": project_id,
        "schema_version": SCHEMA_VERSION,
        "kind": "STUDY",
        "title": title,
        "short_title": str(payload.get("short_title") or title)[:120],
        "state": "DRAFT",
        "design": design,
        "design_label": DESIGN_LABELS.get(design, design),
        "research_question": question,
        "question": {
            "id": question_id,
            "study_id": study_id,
            "statement": question,
            "estimand": str(payload.get("estimand") or _estimand_for_method("METH-U-DESC", metric)),
            "population": str(payload.get("population") or "Participants in the admitted snapshot."),
            "exposure": str(payload.get("exposure") or "Repeated measurement; no intervention is inferred."),
            "outcomes": [metric_id, *secondary_ids],
            "time_horizon": str(payload.get("time_horizon") or schedule.get("note", "")),
        },
        "hypotheses": hypotheses,
        "population": str(payload.get("population") or "Participants in the admitted snapshot."),
        "eligibility": [str(item) for item in payload.get("eligibility", []) if str(item).strip()],
        "exclusions": [str(item) for item in payload.get("exclusions", []) if str(item).strip()],
        "intervention": str(payload.get("intervention") or "No intervention is inferred from observational data."),
        "arms": [
            {
                "id": "ARM-ALL",
                "label": "All participants",
                "arm": "INTERVENTION",
                "allocation": "NOT_APPLICABLE",
                "description": "Single observational cohort; no concurrent comparator is inferred.",
            }
        ],
        "outcomes": {
            "primary": [metric],
            "secondary": [item for item in metrics if item["id"] in secondary_ids],
        },
        "protocols": [protocol],
        "schedule": schedule,
        "dataset_snapshot_id": snapshot_id,
        "cohort_id": None,
        "analysis_plan_id": None,
        "created_at": now,
        "updated_at": now,
        "archived_at": None,
        "state_history": [{"state": "DRAFT", "at": now}],
        "version": 1,
    }
    with _tx() as connection:
        connection.execute(
            "INSERT INTO entities (id, project_id, kind, version, state, document, created_at, updated_at, archived_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (study_id, project_id, "STUDY", 1, "DRAFT", _canonical(study), now, now, None),
        )
        connection.execute(
            "INSERT INTO entity_versions (entity_id, version, change_type, document, created_at) VALUES (?, ?, ?, ?, ?)",
            (study_id, 1, "CREATED", _canonical(study), now),
        )
        _audit(connection, "study.created", "study", study_id, {"project_id": project_id, "design": design, "snapshot_id": snapshot_id})
    create_cohort(study_id, "All eligible participants", _default_cohort_definition(metric, snapshot_id), freeze=False)
    create_plan(study_id, plan_payload={})
    _create_default_investigation(get_entity(study_id) or study)
    return study_detail(study_id)


def create_monitoring_program(project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    project = get_project(project_id)
    if project is None:
        raise ResearchNotFound(f"Project {project_id} not found")
    if project["status"] == "ARCHIVED":
        raise ResearchConflict("Cannot add a monitoring program to an archived project")
    title = str(payload.get("title", "")).strip()
    snapshot_id = str(payload.get("dataset_snapshot_id", "")).strip()
    metric_id = str(payload.get("primary_metric_id", "")).strip()
    if not title or not snapshot_id or not metric_id:
        raise ResearchValidation("title, dataset_snapshot_id and primary_metric_id are required")
    snapshot = get_snapshot(snapshot_id)
    if snapshot is None:
        raise ResearchValidation(f"Snapshot {snapshot_id} is not admitted")
    metrics = dataset_metrics(snapshot_id)
    metric = next((item for item in metrics if item["id"] == metric_id), None)
    if metric is None:
        raise ResearchValidation(f"Metric {metric_id} is not present in {snapshot_id}")
    start_week = int(payload.get("start_week") or 5)
    weeks = int(payload.get("weeks") or 12)
    if start_week < 1 or weeks < 1 or weeks > 104:
        raise ResearchValidation("start_week must be ≥ 1 and weeks between 1 and 104")
    question = str(payload.get("research_question") or f"How does {metric['label'].lower()} change during the planned monitoring period?").strip()
    question_id = _new_id("RQ-U")
    study_id = _new_id("PROG-U")
    now = _now()
    schedule_points = [
        {
            "index": index + 1,
            "week": start_week + index,
            "label": f"Week {start_week + index}",
            "planned": True,
        }
        for index in range(weeks)
    ]
    protocol = _protocol_for_snapshot(snapshot_id, metric)
    study = {
        "id": study_id,
        "project_id": project_id,
        "schema_version": SCHEMA_VERSION,
        "kind": "MONITORING",
        "title": title,
        "short_title": str(payload.get("short_title") or title)[:120],
        "state": "DRAFT",
        "design": "OBSERVATIONAL_LONGITUDINAL",
        "design_label": "Prospective monitoring schedule",
        "research_question": question,
        "question": {
            "id": question_id,
            "study_id": study_id,
            "statement": question,
            "estimand": "Descriptive within-individual and cohort trajectories over the planned monitoring period.",
            "population": str(payload.get("population") or "Monitored participants from the bound snapshot."),
            "exposure": "Time and repeated measurement; no causal intervention is inferred.",
            "outcomes": [metric_id],
            "time_horizon": f"{weeks} planned weekly measurements starting at week {start_week}.",
        },
        "hypotheses": [
            {
                "id": _hypothesis_id(0),
                "question_id": question_id,
                "statement": f"{metric['label']} will be summarised as individual and cohort trajectories; no directional effect is assumed.",
                "direction": "change",
                "status": "PRIMARY",
                "rationale": "Monitoring is descriptive and does not test an intervention.",
            }
        ],
        "population": str(payload.get("population") or "Monitored participants from the bound snapshot."),
        "eligibility": [str(item) for item in payload.get("eligibility", []) if str(item).strip()],
        "exclusions": [str(item) for item in payload.get("exclusions", []) if str(item).strip()],
        "intervention": "No intervention. Monitoring program.",
        "arms": [
            {"id": "ARM-ALL", "label": "Monitored cohort", "arm": "INTERVENTION", "allocation": "NOT_APPLICABLE", "description": "Single monitoring cohort; no comparator is inferred."}
        ],
        "outcomes": {"primary": [metric], "secondary": []},
        "protocols": [protocol],
        "schedule": {
            "kind": "PLANNED_WEEKLY",
            "axis": "week",
            "label": "Planned monitoring week",
            "frequency": str(payload.get("frequency") or "weekly"),
            "start_week": start_week,
            "weeks": weeks,
            "points": schedule_points,
            "planned_protocol": protocol["name"],
            "quality_rules": [str(item) for item in payload.get("quality_rules", []) if str(item).strip()] or [
                "A scheduled measurement without a reading is MISSING, not zero.",
                "No readiness score and no injury/fatigue diagnosis is computed.",
            ],
            "missing_policy": str(payload.get("missing_policy") or "Missing scheduled measurements remain missing and are never imputed."),
            "analysis_settings": {
                "analysis": "descriptive trajectories",
                "baseline": "individual and cohort baseline summaries when readings exist",
                "irregular_observations": "reported with the actual measurement dates; never interpolated without a declared rule",
            },
            "future_measurements": schedule_points,
            "note": "The schedule is prospective. Attached historical readings are not relabelled as new observations and are not forced onto the scheduled calendar.",
        },
        "dataset_snapshot_id": snapshot_id,
        "cohort_id": None,
        "analysis_plan_id": None,
        "created_at": now,
        "updated_at": now,
        "archived_at": None,
        "state_history": [{"state": "DRAFT", "at": now}],
        "version": 1,
    }
    with _tx() as connection:
        connection.execute(
            "INSERT INTO entities (id, project_id, kind, version, state, document, created_at, updated_at, archived_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (study_id, project_id, "MONITORING", 1, "DRAFT", _canonical(study), now, now, None),
        )
        connection.execute(
            "INSERT INTO entity_versions (entity_id, version, change_type, document, created_at) VALUES (?, ?, ?, ?, ?)",
            (study_id, 1, "CREATED", _canonical(study), now),
        )
        _audit(connection, "program.created", "monitoring_program", study_id, {"project_id": project_id, "snapshot_id": snapshot_id, "weeks": weeks})
    create_cohort(study_id, "All monitored participants", _default_cohort_definition(metric, snapshot_id), freeze=False)
    create_plan(study_id, plan_payload={"method_id": "METH-U-DESC", "name": "Monitoring descriptive trajectory plan"})
    _create_default_investigation(get_entity(study_id) or study)
    return study_detail(study_id)


def list_entities(project_id: str | None = None, kind: str | None = None, include_archived: bool = True) -> list[dict[str, Any]]:
    query = "SELECT * FROM entities"
    clauses: list[str] = []
    parameters: list[Any] = []
    if project_id:
        clauses.append("project_id = ?")
        parameters.append(project_id)
    if kind:
        clauses.append("kind = ?")
        parameters.append(kind)
    if not include_archived:
        clauses.append("state != 'ARCHIVED'")
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY created_at"
    with _connect() as connection:
        rows = connection.execute(query, parameters).fetchall()
    return [_row_document(row) for row in rows]


def get_entity(entity_id: str) -> dict[str, Any] | None:
    with _connect() as connection:
        row = connection.execute("SELECT * FROM entities WHERE id = ?", (entity_id,)).fetchone()
    return _row_document(row) if row else None


def update_entity(entity_id: str, patch: dict[str, Any], base_version: int | None = None, change_type: str = "UPDATED") -> dict[str, Any]:
    with _tx() as connection:
        row = connection.execute("SELECT * FROM entities WHERE id = ?", (entity_id,)).fetchone()
        if row is None:
            raise ResearchNotFound(f"Research object {entity_id} not found")
        document = _row_document(row)
        if document.get("state") == "ARCHIVED" and change_type != "RESTORED":
            raise ResearchConflict("Archived objects cannot be edited; restore first")
        if base_version is not None and int(base_version) != int(document["version"]):
            raise ResearchConflict(f"{entity_id} is at version {document['version']}, not {base_version}")
        allowed = {
            "title", "short_title", "research_question", "design", "population", "eligibility", "exclusions",
            "intervention", "arms", "outcomes", "protocols", "schedule", "hypotheses", "cohort_id", "analysis_plan_id",
            "dataset_snapshot_id",
        }
        if "dataset_snapshot_id" in patch and patch["dataset_snapshot_id"] != document.get("dataset_snapshot_id"):
            if list_cohorts(entity_id) or list_plans(entity_id):
                raise ResearchValidation("The dataset binding cannot change after cohorts or analysis plans exist; create a new study instead")
            if get_snapshot(str(patch["dataset_snapshot_id"])) is None:
                raise ResearchValidation("The replacement dataset snapshot is not admitted")
        if "design" in patch:
            metrics = dataset_metrics(document["dataset_snapshot_id"])
            primary = (document.get("outcomes", {}).get("primary") or [{}])[0].get("id")
            metric = next((item for item in metrics if item["id"] == primary), metrics[0] if metrics else None)
            if metric is not None:
                _validate_design(str(patch["design"]), metric["table"])
        for key in allowed:
            if key in patch:
                document[key] = patch[key]
        if "question" in patch and isinstance(patch["question"], dict):
            document["question"] = {**document.get("question", {}), **patch["question"]}
        document["version"] = int(document["version"]) + 1
        document["updated_at"] = _now()
        connection.execute(
            "UPDATE entities SET version = ?, state = ?, document = ?, updated_at = ?, archived_at = ? WHERE id = ?",
            (document["version"], document["state"], _canonical(document), document["updated_at"], document.get("archived_at"), entity_id),
        )
        connection.execute(
            "INSERT INTO entity_versions (entity_id, version, change_type, document, created_at) VALUES (?, ?, ?, ?, ?)",
            (entity_id, document["version"], change_type, _canonical(document), document["updated_at"]),
        )
        _audit(connection, f"{document['kind'].lower()}.{change_type.lower()}", document["kind"].lower(), entity_id, patch)
    return document


def transition_entity(entity_id: str, target: str) -> dict[str, Any]:
    entity = get_entity(entity_id)
    if entity is None:
        raise ResearchNotFound(f"Research object {entity_id} not found")
    current = entity["state"]
    target = target.upper()
    if target not in STUDY_STATES:
        raise ResearchValidation(f"Unknown state {target}")
    if target == current:
        return entity
    if target not in ALLOWED_TRANSITIONS.get(current, set()):
        raise ResearchConflict(f"Transition {current} → {target} is not allowed")
    if target in {"READY", "ACTIVE"}:
        required = [
            entity.get("title"),
            entity.get("research_question"),
            entity.get("dataset_snapshot_id"),
            entity.get("cohort_id"),
            entity.get("analysis_plan_id"),
        ]
        if not all(required):
            raise ResearchValidation("A study must have a title, question, dataset, cohort and analysis plan before it can be READY")
        cohort = get_cohort(entity["cohort_id"])
        if cohort is None or cohort["status"] != "FROZEN":
            raise ResearchValidation("Freeze the cohort before moving the study to READY")
        plan = get_plan(entity["analysis_plan_id"])
        if plan is None or plan["status"] != "FROZEN":
            raise ResearchValidation("Freeze the analysis plan before moving the study to READY")
    if target == "ANALYSIS" and not list_runs(entity_id):
        raise ResearchValidation("Execute at least one analysis before moving to ANALYSIS")
    if target == "COMPLETED" and not list_evidence(entity_id):
        raise ResearchValidation("Promote at least one evidence artifact before moving to COMPLETED")
    now = _now()
    entity["state"] = target
    entity["state_history"] = [*entity.get("state_history", []), {"state": target, "at": now}]
    entity["version"] = int(entity["version"]) + 1
    entity["updated_at"] = now
    entity["archived_at"] = now if target == "ARCHIVED" else None
    entity["state_before_archive"] = current if target == "ARCHIVED" else entity.get("state_before_archive")
    with _tx() as connection:
        connection.execute(
            "UPDATE entities SET version = ?, state = ?, document = ?, updated_at = ?, archived_at = ? WHERE id = ?",
            (entity["version"], target, _canonical(entity), now, entity["archived_at"], entity_id),
        )
        connection.execute(
            "INSERT INTO entity_versions (entity_id, version, change_type, document, created_at) VALUES (?, ?, ?, ?, ?)",
            (entity_id, entity["version"], f"STATE_{target}", _canonical(entity), now),
        )
        _audit(connection, "state.changed", entity["kind"].lower(), entity_id, {"from": current, "to": target})
    return entity


def entity_history(entity_id: str) -> list[dict[str, Any]]:
    with _connect() as connection:
        rows = connection.execute(
            "SELECT version, change_type, document, created_at FROM entity_versions WHERE entity_id = ? ORDER BY version DESC",
            (entity_id,),
        ).fetchall()
    return [{**json.loads(row["document"]), "change_type": row["change_type"], "version": row["version"], "recorded_at": row["created_at"]} for row in rows]


# --------------------------------------------------------------------------- #
# Cohorts
# --------------------------------------------------------------------------- #


def _subject_frame(snapshot_id: str) -> pl.DataFrame:
    frame = read_snapshot_table(snapshot_id, "subjects")
    if "subject_id" not in frame.columns:
        raise ResearchValidation(f"Snapshot {snapshot_id} has no subjects table")
    return frame


def _cohort_observations(snapshot_id: str, definition: dict[str, Any]) -> tuple[dict[str, Any], pl.DataFrame]:
    metric_id = definition.get("require_metric_id")
    metrics = dataset_metrics(snapshot_id)
    metric = next((item for item in metrics if item["id"] == metric_id), metrics[0] if metrics else None)
    if metric is None:
        raise ResearchValidation("A cohort requires a metric present in the snapshot")
    frame = read_snapshot_table(snapshot_id, metric["table"])
    activity = definition.get("activity")
    if activity and "activity" in frame.columns:
        frame = frame.filter(pl.col("activity") == activity)
    if definition.get("exclude_subject_ids"):
        frame = frame.filter(~pl.col("subject_id").is_in(definition["exclude_subject_ids"]))
    return metric, frame


def resolve_cohort(definition: dict[str, Any], snapshot_id: str | None = None, excluded_subject_ids: list[str] | None = None) -> dict[str, Any]:
    snapshot_id = snapshot_id or definition.get("snapshot_id")
    if not snapshot_id or get_snapshot(snapshot_id) is None:
        raise ResearchValidation("A cohort must be bound to an admitted snapshot")
    subjects = _subject_frame(snapshot_id).to_dicts()
    metric, observations = _cohort_observations(snapshot_id, definition)
    explicit_excluded = {str(item) for item in definition.get("exclude_subject_ids", [])}
    explicit_included = {str(item) for item in definition.get("include_subject_ids", [])}
    run_excluded = {str(item) for item in (excluded_subject_ids or [])}
    rules = [rule for rule in definition.get("rules", []) if isinstance(rule, dict)]
    min_observations = int(definition.get("min_metric_observations") or 0)
    by_subject: dict[str, list[dict[str, Any]]] = {}
    for row in observations.iter_rows(named=True):
        by_subject.setdefault(str(row["subject_id"]), []).append(row)
    included: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for subject in subjects:
        subject_id = str(subject["subject_id"])
        reason = None
        if explicit_included and subject_id not in explicit_included:
            reason = "Not in the explicitly included subject list"
        elif subject_id in explicit_excluded:
            reason = "Excluded by the saved cohort definition"
        elif subject_id in run_excluded:
            reason = "Excluded in the current investigation (draft cohort)"
        else:
            for rule in rules:
                field = str(rule.get("field", ""))
                op = str(rule.get("operator", "eq"))
                expected = rule.get("value")
                actual = subject.get(field)
                if actual is None:
                    reason = f"Missing subject field {field}"
                    break
                try:
                    if op == "eq" and actual != expected:
                        reason = f"{field} = {actual!r} does not equal {expected!r}"
                    elif op == "ne" and actual == expected:
                        reason = f"{field} = {actual!r} equals the excluded value {expected!r}"
                    elif op == "gte" and float(actual) < float(expected):
                        reason = f"{field} = {actual} is below {expected}"
                    elif op == "lte" and float(actual) > float(expected):
                        reason = f"{field} = {actual} is above {expected}"
                    elif op == "in" and actual not in (expected or []):
                        reason = f"{field} = {actual!r} is not in the allowed set"
                except (TypeError, ValueError):
                    reason = f"Rule for {field} cannot be evaluated"
                if reason:
                    break
        values = by_subject.get(subject_id, [])
        observation_count = sum(1 for row in values if row.get(metric["column"]) is not None) if metric["column"] in observations.columns else 0
        if reason is None and observation_count < min_observations:
            reason = f"Only {observation_count} valid {metric['label'].lower()} observation(s); {min_observations} required"
        display = subject.get("display_id") or subject_id
        record = {
            "subject_id": subject_id,
            "display_id": display,
            "position": subject.get("position") or "Participant",
            "intervention_arm": "INTERVENTION",
            "included": reason is None,
            "valid_trials": observation_count,
            "excluded_trials": 0,
            "missing_trials": 0,
            "reason": reason,
        }
        (included if reason is None else excluded).append(record)
    included_ids = [item["subject_id"] for item in included]
    axis = _axis_for_table(metric["table"])[0]
    axis_values = sorted({row.get(axis) for row in observations.iter_rows(named=True) if row.get(axis) is not None})
    expected = len(included_ids) * len(axis_values)
    observed = sum(item["valid_trials"] for item in included)
    missing = max(0, expected - observed)
    missing_slots: list[dict[str, Any]] = []
    if metric["table"] in {"cmj_occasions", "cmj_trials"}:
        for item in included:
            present = {
                row.get(axis)
                for row in by_subject.get(item["subject_id"], [])
                if row.get(metric["column"]) is not None
            }
            for point in axis_values:
                if point not in present:
                    missing_slots.append(
                        {
                            "subject_id": item["subject_id"],
                            "display_id": item["display_id"],
                            "week": point,
                            "trial_number": 1,
                            "reason": f"No deposited {metric['label'].lower()} at {axis} {point}",
                        }
                    )
    return {
        "cohort": {
            "id": definition.get("id"),
            "study_id": definition.get("study_id"),
            "name": definition.get("name"),
            "description": definition.get("description", ""),
            "subject_ids": included_ids,
            "excluded_subject_ids": sorted(explicit_excluded | run_excluded),
            "exclusion_criteria": [str(rule) for rule in definition.get("rules", [])] + [f"Minimum valid observations: {min_observations}"],
            "snapshot_id": snapshot_id,
            "status": definition.get("status", "DRAFT"),
            "derived_from": definition.get("parent_id"),
        },
        "n": len(included_ids),
        "arm_counts": {"INTERVENTION": len(included_ids), "COMPARISON": 0},
        "inclusion_criteria": ["Subject exists in the admitted snapshot subjects table.", f"At least {min_observations} valid {metric['label'].lower()} observation(s)."],
        "exclusion_criteria": [str(rule) for rule in definition.get("rules", [])] + ([f"Explicitly excluded: {', '.join(sorted(explicit_excluded))}"] if explicit_excluded else []),
        "filters": {"excluded_subject_ids": sorted(run_excluded), "saved_excluded_subject_ids": sorted(explicit_excluded)},
        "trial_quality": {
            "valid": observed,
            "excluded": 0,
            "missing": missing,
            "expected": expected,
            "missing_by_arm": {"INTERVENTION": missing},
            "excluded_trials": [],
            "missing_slots": missing_slots,
        },
        "n_trials": observed,
        "athletes": [*included, *excluded],
        "excluded_subjects": excluded,
        "snapshot_id": snapshot_id,
        "metric": metric,
        "axis": axis,
    }


def create_cohort(entity_id: str, name: str, definition: dict[str, Any], freeze: bool = False, base_version: int | None = None, parent_id: str | None = None) -> dict[str, Any]:
    entity = get_entity(entity_id)
    if entity is None:
        raise ResearchNotFound(f"Research object {entity_id} not found")
    snapshot_id = str(definition.get("snapshot_id") or entity["dataset_snapshot_id"])
    if snapshot_id != entity["dataset_snapshot_id"]:
        raise ResearchValidation("A cohort must be bound to the study's dataset snapshot")
    definition = {
        **definition,
        "snapshot_id": snapshot_id,
        "study_id": entity_id,
        "name": name.strip() or "Untitled cohort",
        "id": _new_id("COHORT-U"),
        "status": "FROZEN" if freeze else "DRAFT",
        "version": 1,
        "parent_id": parent_id,
        "created_at": _now(),
    }
    resolved = resolve_cohort(definition, snapshot_id)
    document = {**definition, "resolved": {k: v for k, v in resolved.items() if k in {"n", "included_subjects", "excluded_subjects", "trial_quality", "metric", "axis"}}}
    document["resolved"]["included_subjects"] = resolved["cohort"]["subject_ids"]
    with _tx() as connection:
        connection.execute(
            "INSERT INTO cohorts (id, project_id, entity_id, version, status, snapshot_id, parent_id, document, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (document["id"], entity["project_id"], entity_id, 1, document["status"], snapshot_id, parent_id, _canonical(document), document["created_at"], document["created_at"]),
        )
        connection.execute(
            "INSERT INTO cohort_versions (cohort_id, version, change_type, document, created_at) VALUES (?, ?, ?, ?, ?)",
            (document["id"], 1, "CREATED", _canonical(document), document["created_at"]),
        )
        _audit(connection, "cohort.created", "cohort", document["id"], {"entity_id": entity_id, "snapshot_id": snapshot_id})
    if freeze:
        return freeze_cohort(document["id"])
    update_entity(entity_id, {"cohort_id": document["id"]}, base_version=entity["version"], change_type="COHORT_BOUND")
    return document


def _cohort_view(document: dict[str, Any], status: str | None = None) -> dict[str, Any]:
    if status:
        document["status"] = status
    if "subject_ids" not in document:
        document["subject_ids"] = (document.get("resolved") or {}).get("included_subjects", [])
    return document


def get_cohort(cohort_id: str) -> dict[str, Any] | None:
    with _connect() as connection:
        row = connection.execute("SELECT * FROM cohorts WHERE id = ?", (cohort_id,)).fetchone()
    if row is None:
        return None
    return _cohort_view(_row_document(row), row["status"])


def list_cohorts(entity_id: str) -> list[dict[str, Any]]:
    with _connect() as connection:
        rows = connection.execute("SELECT * FROM cohorts WHERE entity_id = ? ORDER BY created_at", (entity_id,)).fetchall()
    return [_cohort_view(_row_document(row), row["status"]) for row in rows]


def update_cohort(cohort_id: str, patch: dict[str, Any], base_version: int | None = None) -> dict[str, Any]:
    with _tx() as connection:
        row = connection.execute("SELECT * FROM cohorts WHERE id = ?", (cohort_id,)).fetchone()
        if row is None:
            raise ResearchNotFound(f"Cohort {cohort_id} not found")
        document = _row_document(row)
        if document["status"] == "FROZEN":
            raise ResearchConflict("Frozen cohorts are immutable; fork the cohort to change its rules")
        if base_version is not None and int(base_version) != int(document["version"]):
            raise ResearchConflict(f"Cohort is at version {document['version']}, not {base_version}")
        for key in ("name", "description", "include_subject_ids", "exclude_subject_ids", "rules", "min_metric_observations", "activity"):
            if key in patch:
                document[key] = patch[key]
        document["version"] = int(document["version"]) + 1
        document["updated_at"] = _now()
        resolved = resolve_cohort(document, document["snapshot_id"])
        document["resolved"] = {
            "n": resolved["n"],
            "included_subjects": resolved["cohort"]["subject_ids"],
            "excluded_subjects": resolved["excluded_subjects"],
            "trial_quality": resolved["trial_quality"],
            "metric": resolved["metric"],
            "axis": resolved["axis"],
        }
        connection.execute(
            "UPDATE cohorts SET version = ?, document = ?, updated_at = ? WHERE id = ?",
            (document["version"], _canonical(document), document["updated_at"], cohort_id),
        )
        connection.execute(
            "INSERT INTO cohort_versions (cohort_id, version, change_type, document, created_at) VALUES (?, ?, ?, ?, ?)",
            (cohort_id, document["version"], "UPDATED", _canonical(document), document["updated_at"]),
        )
        _audit(connection, "cohort.updated", "cohort", cohort_id, patch)
    return document


def freeze_cohort(cohort_id: str) -> dict[str, Any]:
    with _tx() as connection:
        row = connection.execute("SELECT * FROM cohorts WHERE id = ?", (cohort_id,)).fetchone()
        if row is None:
            raise ResearchNotFound(f"Cohort {cohort_id} not found")
        document = _row_document(row)
        if document["status"] == "FROZEN":
            return document
        resolved = resolve_cohort(document, document["snapshot_id"])
        document["status"] = "FROZEN"
        document["version"] = int(document["version"]) + 1
        document["updated_at"] = _now()
        document["frozen_at"] = document["updated_at"]
        document["resolved"] = {
            "n": resolved["n"],
            "included_subjects": resolved["cohort"]["subject_ids"],
            "excluded_subjects": resolved["excluded_subjects"],
            "trial_quality": resolved["trial_quality"],
            "metric": resolved["metric"],
            "axis": resolved["axis"],
        }
        connection.execute(
            "UPDATE cohorts SET version = ?, status = 'FROZEN', document = ?, updated_at = ? WHERE id = ?",
            (document["version"], _canonical(document), document["updated_at"], cohort_id),
        )
        connection.execute(
            "INSERT INTO cohort_versions (cohort_id, version, change_type, document, created_at) VALUES (?, ?, ?, ?, ?)",
            (cohort_id, document["version"], "FROZEN", _canonical(document), document["updated_at"]),
        )
        _audit(connection, "cohort.frozen", "cohort", cohort_id, {"n": resolved["n"]})
    return document


def fork_cohort(cohort_id: str, name: str | None = None) -> dict[str, Any]:
    parent = get_cohort(cohort_id)
    if parent is None:
        raise ResearchNotFound(f"Cohort {cohort_id} not found")
    entity = get_entity(parent["study_id"])
    if entity is None:
        raise ResearchNotFound(f"Study {parent['study_id']} not found")
    definition = {
        key: parent.get(key)
        for key in ("include_subject_ids", "exclude_subject_ids", "rules", "min_metric_observations", "activity", "snapshot_id", "description")
    }
    definition["snapshot_id"] = parent["snapshot_id"]
    return create_cohort(entity["id"], name or f"{parent['name']} (fork)", definition, freeze=False, parent_id=cohort_id)


def cohort_history(cohort_id: str) -> list[dict[str, Any]]:
    with _connect() as connection:
        rows = connection.execute(
            "SELECT version, change_type, document, created_at FROM cohort_versions WHERE cohort_id = ? ORDER BY version DESC",
            (cohort_id,),
        ).fetchall()
    return [{**json.loads(row["document"]), "change_type": row["change_type"], "version": row["version"], "recorded_at": row["created_at"]} for row in rows]


# --------------------------------------------------------------------------- #
# Analysis plans
# --------------------------------------------------------------------------- #


def _plan_content(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        key: plan.get(key)
        for key in (
            "study_id", "method_id", "method_version", "outcome_metric_id", "cohort_id", "snapshot_id",
            "primary_estimand", "hypotheses", "covariates", "fixed_effects", "random_effects", "time_coding",
            "contrasts", "inclusion_criteria", "exclusion_criteria", "missing_data", "diagnostics", "parameters",
            "prospective", "frozen_before_inspection",
        )
    }


def create_plan(entity_id: str, plan_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    entity = get_entity(entity_id)
    if entity is None:
        raise ResearchNotFound(f"Research object {entity_id} not found")
    payload = plan_payload or {}
    cohort_id = str(payload.get("cohort_id") or entity.get("cohort_id") or "")
    cohort = get_cohort(cohort_id) if cohort_id else None
    if cohort is None:
        # A plan may be authored with the default cohort created by the study.
        cohorts = list_cohorts(entity_id)
        cohort = cohorts[-1] if cohorts else None
    if cohort is None:
        raise ResearchValidation("A cohort is required before an analysis plan can be created")
    metric_id = str(payload.get("outcome_metric_id") or (entity.get("outcomes", {}).get("primary") or [{}])[0].get("id") or "")
    metrics = dataset_metrics(entity["dataset_snapshot_id"])
    metric = next((item for item in metrics if item["id"] == metric_id), None)
    if metric is None:
        raise ResearchValidation(f"Metric {metric_id} is not present in the study snapshot")
    if payload.get("method_id"):
        method_id = str(payload["method_id"])
    elif metric["table"] == "cmj_occasions":
        method_id = "METH-REAL-TREND"
    elif metric["table"] == "signal_trials":
        method_id = "METH-REAL-RELIABILITY"
    else:
        method_id = "METH-U-DESC"
    if method_id not in METHODS:
        raise ResearchValidation(f"Unknown method {method_id}")
    method = METHODS[method_id]
    if metric["table"] not in method["required_tables"]:
        raise ResearchValidation(f"{method['name']} is not applicable to {metric['table']}")
    default_parameters: dict[str, Any] = {
        "METH-REAL-TREND": {"reference_occasion": 1, "contrast_occasion": 2, "alpha": 0.05},
        "METH-REAL-RELIABILITY": {"activity": "Walking", "max_trials": 8},
        "METH-U-CHANGE": {"reference_week": 1, "contrast_week": 2},
    }.get(method_id, {})
    if method_id == "METH-REAL-TREND":
        frame = read_snapshot_table(entity["dataset_snapshot_id"], metric["table"])
        occasions = sorted(int(value) for value in frame["occasion"].drop_nulls().unique().to_list()) if "occasion" in frame.columns else [1, 2]
        default_parameters = {"reference_occasion": occasions[0], "contrast_occasion": occasions[-1], "alpha": 0.05}
    plan = {
        "id": _new_id("PLAN"),
        "study_id": entity_id,
        "name": str(payload.get("name") or f"{method['name']} plan"),
        "status": "DRAFT",
        "version": 1,
        "method_id": method_id,
        "method_version": method["version"],
        "outcome_metric_id": metric_id,
        "cohort_id": cohort_id,
        "snapshot_id": entity["dataset_snapshot_id"],
        "primary_estimand": str(payload.get("primary_estimand") or _estimand_for_method(method_id, metric)),
        "hypotheses": payload.get("hypotheses") or [item["id"] for item in entity.get("hypotheses", [])],
        "covariates": payload.get("covariates") or [],
        "fixed_effects": payload.get("fixed_effects") or ["intercept"],
        "random_effects": payload.get("random_effects") or (["subject intercept", "subject occasion slope"] if method_id == "METH-REAL-TREND" else []),
        "time_coding": str(payload.get("time_coding") or ("occasion centred at the reference occasion" if method_id == "METH-REAL-TREND" else "not applicable")),
        "contrasts": payload.get("contrasts") or ["primary estimand"],
        "inclusion_criteria": str(payload.get("inclusion_criteria") or "Resolved cohort definition."),
        "exclusion_criteria": payload.get("exclusion_criteria") or [],
        "missing_data": str(payload.get("missing_data") or "Complete-case at the outcome; no imputation."),
        "diagnostics": payload.get("diagnostics") or method["diagnostics"],
        "parameters": {**default_parameters, **(payload.get("parameters") or {})},
        "planned_models": payload.get("planned_models") or [method["name"]],
        "planned_reliability": str(payload.get("planned_reliability") or ("ICC(3,1) as selected" if method_id == "METH-REAL-RELIABILITY" else "Not planned.")),
        "prospective": False,
        "frozen_before_inspection": False,
        "parent_id": payload.get("parent_id"),
        "spec_id": None,
        "content_hash": None,
        "frozen_at": None,
        "created_at": _now(),
        "updated_at": _now(),
    }
    with _tx() as connection:
        connection.execute(
            "INSERT INTO plans (id, project_id, entity_id, version, status, snapshot_id, cohort_id, parent_id, spec_id, content_hash, document, created_at, updated_at, frozen_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (plan["id"], entity["project_id"], entity_id, 1, "DRAFT", plan["snapshot_id"], cohort_id, plan["parent_id"], None, None, _canonical(plan), plan["created_at"], plan["created_at"], None),
        )
        connection.execute(
            "INSERT INTO plan_versions (plan_id, version, change_type, document, created_at) VALUES (?, ?, ?, ?, ?)",
            (plan["id"], 1, "CREATED", _canonical(plan), plan["created_at"]),
        )
        _audit(connection, "plan.created", "analysis_plan", plan["id"], {"entity_id": entity_id, "method_id": method_id})
    update_entity(entity_id, {"analysis_plan_id": plan["id"]}, base_version=entity["version"], change_type="PLAN_BOUND")
    return plan


def get_plan(plan_id: str) -> dict[str, Any] | None:
    with _connect() as connection:
        row = connection.execute("SELECT * FROM plans WHERE id = ?", (plan_id,)).fetchone()
    return _row_document(row) if row else None


def list_plans(entity_id: str) -> list[dict[str, Any]]:
    with _connect() as connection:
        rows = connection.execute("SELECT * FROM plans WHERE entity_id = ? ORDER BY created_at", (entity_id,)).fetchall()
    return [_row_document(row) for row in rows]


def update_plan(plan_id: str, patch: dict[str, Any], base_version: int | None = None) -> dict[str, Any]:
    with _tx() as connection:
        row = connection.execute("SELECT * FROM plans WHERE id = ?", (plan_id,)).fetchone()
        if row is None:
            raise ResearchNotFound(f"Analysis plan {plan_id} not found")
        plan = _row_document(row)
        if plan["status"] == "FROZEN":
            raise ResearchConflict("Frozen plans are immutable; fork the plan to change it")
        if base_version is not None and int(base_version) != int(plan["version"]):
            raise ResearchConflict(f"Plan is at version {plan['version']}, not {base_version}")
        for key in (
            "name", "method_id", "method_version", "outcome_metric_id", "cohort_id", "primary_estimand", "hypotheses",
            "covariates", "fixed_effects", "random_effects", "time_coding", "contrasts", "inclusion_criteria",
            "exclusion_criteria", "missing_data", "diagnostics", "parameters", "planned_models", "planned_reliability",
        ):
            if key in patch:
                plan[key] = patch[key]
        if plan["method_id"] not in METHODS:
            raise ResearchValidation(f"Unknown method {plan['method_id']}")
        metrics = dataset_metrics(plan["snapshot_id"])
        metric = next((item for item in metrics if item["id"] == plan["outcome_metric_id"]), None)
        if metric is None:
            raise ResearchValidation("The plan outcome is not present in the snapshot")
        if metric["table"] not in METHODS[plan["method_id"]]["required_tables"]:
            raise ResearchValidation("The selected method is not applicable to the selected outcome table")
        plan["version"] = int(plan["version"]) + 1
        plan["updated_at"] = _now()
        connection.execute(
            "UPDATE plans SET version = ?, document = ?, updated_at = ? WHERE id = ?",
            (plan["version"], _canonical(plan), plan["updated_at"], plan_id),
        )
        connection.execute(
            "INSERT INTO plan_versions (plan_id, version, change_type, document, created_at) VALUES (?, ?, ?, ?, ?)",
            (plan_id, plan["version"], "UPDATED", _canonical(plan), plan["updated_at"]),
        )
        _audit(connection, "plan.updated", "analysis_plan", plan_id, patch)
    return plan


def freeze_plan(plan_id: str) -> dict[str, Any]:
    with _tx() as connection:
        row = connection.execute("SELECT * FROM plans WHERE id = ?", (plan_id,)).fetchone()
        if row is None:
            raise ResearchNotFound(f"Analysis plan {plan_id} not found")
        plan = _row_document(row)
        if plan["status"] == "FROZEN":
            return plan
        cohort = get_cohort(plan["cohort_id"])
        if cohort is None or cohort["status"] != "FROZEN":
            raise ResearchValidation("Freeze the cohort before freezing the analysis plan")
        content = _plan_content(plan)
        content_hash = _digest(content)
        spec_id = f"SPEC-U-{content_hash[:8].upper()}"
        plan["status"] = "FROZEN"
        plan["version"] = int(plan["version"]) + 1
        plan["updated_at"] = _now()
        plan["frozen_at"] = plan["updated_at"]
        plan["content_hash"] = content_hash
        plan["spec_id"] = spec_id
        plan["prospective"] = False
        plan["frozen_before_inspection"] = False
        plan["freeze_note"] = "Frozen in this local workspace before or during analysis. This is not evidence of external preregistration."
        connection.execute(
            "UPDATE plans SET version = ?, status = 'FROZEN', spec_id = ?, content_hash = ?, document = ?, updated_at = ?, frozen_at = ? WHERE id = ?",
            (plan["version"], spec_id, content_hash, _canonical(plan), plan["updated_at"], plan["frozen_at"], plan_id),
        )
        connection.execute(
            "INSERT INTO plan_versions (plan_id, version, change_type, document, created_at) VALUES (?, ?, ?, ?, ?)",
            (plan_id, plan["version"], "FROZEN", _canonical(plan), plan["updated_at"]),
        )
        _audit(connection, "plan.frozen", "analysis_plan", plan_id, {"content_hash": content_hash, "spec_id": spec_id})
    return plan


def fork_plan(plan_id: str, name: str | None = None) -> dict[str, Any]:
    parent = get_plan(plan_id)
    if parent is None:
        raise ResearchNotFound(f"Analysis plan {plan_id} not found")
    entity = get_entity(parent["study_id"])
    if entity is None:
        raise ResearchNotFound(f"Study {parent['study_id']} not found")
    payload = {
        "name": name or f"{parent['name']} (fork)",
        "method_id": parent["method_id"],
        "outcome_metric_id": parent["outcome_metric_id"],
        "cohort_id": parent["cohort_id"],
        "primary_estimand": parent["primary_estimand"],
        "hypotheses": parent["hypotheses"],
        "covariates": parent["covariates"],
        "fixed_effects": parent["fixed_effects"],
        "random_effects": parent["random_effects"],
        "time_coding": parent["time_coding"],
        "contrasts": parent["contrasts"],
        "inclusion_criteria": parent["inclusion_criteria"],
        "exclusion_criteria": parent["exclusion_criteria"],
        "missing_data": parent["missing_data"],
        "diagnostics": parent["diagnostics"],
        "parameters": parent["parameters"],
        "planned_models": parent["planned_models"],
        "planned_reliability": parent["planned_reliability"],
        "parent_id": plan_id,
    }
    return create_plan(entity["id"], plan_payload=payload)


def plan_history(plan_id: str) -> list[dict[str, Any]]:
    with _connect() as connection:
        rows = connection.execute(
            "SELECT version, change_type, document, created_at FROM plan_versions WHERE plan_id = ? ORDER BY version DESC",
            (plan_id,),
        ).fetchall()
    return [{**json.loads(row["document"]), "change_type": row["change_type"], "version": row["version"], "recorded_at": row["created_at"]} for row in rows]


def plan_as_spec(plan: dict[str, Any], entity: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": plan.get("spec_id") or f"SPEC-U-{_digest(_plan_content(plan))[:8].upper()}",
        "study_id": plan["study_id"],
        "name": plan["name"],
        "method_id": plan["method_id"],
        "method_version": plan["method_version"],
        "cohort_id": plan["cohort_id"],
        "snapshot_id": plan["snapshot_id"],
        "outcome_metric_id": plan["outcome_metric_id"],
        "model_formula": METHODS.get(plan["method_id"], {}).get("name", plan["method_id"]),
        "parameters": plan["parameters"],
        "planned_contrasts": plan.get("contrasts", []),
        "status": "FROZEN" if plan["status"] == "FROZEN" else "DRAFT",
        "primary_estimand": plan["primary_estimand"],
        "plan_id": plan["id"],
        "content_hash": plan.get("content_hash"),
        "frozen_at": plan.get("frozen_at"),
        "prospective": False,
        "frozen_before_inspection": False,
    }


# --------------------------------------------------------------------------- #
# Investigations
# --------------------------------------------------------------------------- #


def _create_default_investigation(entity: dict[str, Any]) -> dict[str, Any]:
    cohort = get_cohort(entity.get("cohort_id") or "") if entity.get("cohort_id") else None
    plan = get_plan(entity.get("analysis_plan_id") or "") if entity.get("analysis_plan_id") else None
    metric = (entity.get("outcomes", {}).get("primary") or [{}])[0]
    method_id = plan["method_id"] if plan else "METH-U-DESC"
    parameters = plan.get("parameters", {}) if plan else {}
    if entity["kind"] == "MONITORING":
        blocks = [
            {"id": "B-QUESTION", "type": "question", "title": "Research question", "state": {"question_id": entity["question"]["id"]}, "collapsed": False},
            {"id": "B-SCHEDULE", "type": "schedule", "title": "Monitoring schedule", "state": {"program_id": entity["id"]}, "collapsed": False},
            {"id": "B-DATASET", "type": "dataset", "title": entity["dataset_snapshot_id"], "state": {"snapshot_id": entity["dataset_snapshot_id"]}, "collapsed": False},
            {"id": "B-COHORT", "type": "cohort", "title": "Monitored cohort", "state": {"cohort_id": cohort["id"] if cohort else None, "excluded_subject_ids": []}, "collapsed": False},
            {"id": "B-EXPLORE", "type": "explore", "title": "Individual and cohort trajectories", "state": {"metric_id": metric.get("id"), "cohort_block_id": "B-COHORT", "reference": "RAW"}, "collapsed": False},
            {"id": "B-INTERPRETATION", "type": "interpretation", "title": "Interpretation", "state": {}, "collapsed": False},
            {"id": "B-REPORT", "type": "report_section", "title": "Report", "state": {}, "collapsed": False},
        ]
    else:
        blocks = [
            {"id": "B-QUESTION", "type": "question", "title": "Research question", "state": {"question_id": entity["question"]["id"]}, "collapsed": False},
            {"id": "B-DATASET", "type": "dataset", "title": entity["dataset_snapshot_id"], "state": {"snapshot_id": entity["dataset_snapshot_id"]}, "collapsed": False},
            {"id": "B-COHORT", "type": "cohort", "title": "Cohort", "state": {"cohort_id": cohort["id"] if cohort else None, "excluded_subject_ids": []}, "collapsed": False},
            {"id": "B-EXPLORE", "type": "explore", "title": "Longitudinal exploration", "state": {"metric_id": metric.get("id"), "cohort_block_id": "B-COHORT", "reference": "RAW"}, "collapsed": False},
            {"id": "B-ANALYSIS", "type": "analysis", "title": "Primary analysis", "state": {"method_id": method_id, "outcome_metric_id": metric.get("id"), "parameters": parameters, "cohort_block_id": "B-COHORT", "spec_id": plan.get("spec_id") if plan else None}, "collapsed": False},
            {"id": "B-DIAGNOSTICS", "type": "diagnostics", "title": "Diagnostics", "state": {"analysis_block_id": "B-ANALYSIS"}, "collapsed": False},
            {"id": "B-EVIDENCE", "type": "evidence", "title": "Evidence", "state": {"analysis_block_id": "B-ANALYSIS"}, "collapsed": False},
            {"id": "B-FIGURE", "type": "figure", "title": "Figure", "state": {"evidence_block_id": "B-EVIDENCE"}, "collapsed": False},
            {"id": "B-INTERPRETATION", "type": "interpretation", "title": "Interpretation", "state": {"evidence_block_id": "B-EVIDENCE"}, "collapsed": False},
            {"id": "B-REPORT", "type": "report_section", "title": "Report", "state": {"evidence_block_id": "B-EVIDENCE"}, "collapsed": False},
        ]
    return create_investigation(entity["id"], "Primary investigation", blocks=blocks)


def create_investigation(entity_id: str, title: str, blocks: list[dict[str, Any]] | None = None, parent_id: str | None = None) -> dict[str, Any]:
    blocks = blocks or []
    validate_investigation_blocks(blocks)
    entity = get_entity(entity_id)
    if entity is None:
        raise ResearchNotFound(f"Research object {entity_id} not found")
    investigate_id = _new_id("INV-U")
    now = _now()
    document = {
        "id": investigate_id,
        "study_id": entity_id,
        "project_id": entity["project_id"],
        "title": title.strip() or "Untitled investigation",
        "status": "DRAFT",
        "version": 1,
        "parent_id": parent_id,
        "blocks": blocks,
        "created_at": now,
        "updated_at": now,
        "schema_version": SCHEMA_VERSION,
    }
    with _tx() as connection:
        connection.execute(
            "INSERT INTO investigations (id, project_id, entity_id, version, status, parent_id, document, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (investigate_id, entity["project_id"], entity_id, 1, "DRAFT", parent_id, _canonical(document), now, now),
        )
        connection.execute(
            "INSERT INTO investigation_versions (investigation_id, version, document, created_at) VALUES (?, ?, ?, ?)",
            (investigate_id, 1, _canonical(document), now),
        )
        _audit(connection, "investigation.created", "investigation", investigate_id, {"entity_id": entity_id})
    return document


def get_investigation(investigation_id: str) -> dict[str, Any] | None:
    with _connect() as connection:
        row = connection.execute("SELECT * FROM investigations WHERE id = ?", (investigation_id,)).fetchone()
    return _row_document(row) if row else None


def list_investigations(entity_id: str) -> list[dict[str, Any]]:
    with _connect() as connection:
        rows = connection.execute("SELECT * FROM investigations WHERE entity_id = ? ORDER BY created_at", (entity_id,)).fetchall()
    return [_row_document(row) for row in rows]


def update_investigation_research(investigation_id: str, blocks: list[dict[str, Any]], base_version: int | None = None, title: str | None = None) -> dict[str, Any]:
    validate_investigation_blocks(blocks)
    with _tx() as connection:
        row = connection.execute("SELECT * FROM investigations WHERE id = ?", (investigation_id,)).fetchone()
        if row is None:
            raise ResearchNotFound(f"Investigation {investigation_id} not found")
        document = _row_document(row)
        if base_version is not None and int(base_version) != int(document["version"]):
            raise ResearchConflict(f"Investigation is at version {document['version']}, not {base_version}")
        document["blocks"] = blocks
        if title:
            document["title"] = title
        document["version"] = int(document["version"]) + 1
        document["updated_at"] = _now()
        connection.execute(
            "UPDATE investigations SET version = ?, document = ?, updated_at = ? WHERE id = ?",
            (document["version"], _canonical(document), document["updated_at"], investigation_id),
        )
        connection.execute(
            "INSERT INTO investigation_versions (investigation_id, version, document, created_at) VALUES (?, ?, ?, ?)",
            (investigation_id, document["version"], _canonical(document), document["updated_at"]),
        )
        _audit(connection, "investigation.updated", "investigation", investigation_id, {"blocks": len(blocks)})
    return document


def fork_investigation(investigation_id: str, title: str | None = None) -> dict[str, Any]:
    parent = get_investigation(investigation_id)
    if parent is None:
        raise ResearchNotFound(f"Investigation {investigation_id} not found")
    return create_investigation(parent["study_id"], title or f"{parent['title']} (fork)", blocks=parent["blocks"], parent_id=investigation_id)


# --------------------------------------------------------------------------- #
# Runs, evidence, figures
# --------------------------------------------------------------------------- #


def append_run(document: dict[str, Any]) -> dict[str, Any]:
    with _tx() as connection:
        count = connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        run_id = f"RUN-U-{int(count) + 1:04d}"
        document = {**document, "id": run_id, "schema_version": SCHEMA_VERSION}
        connection.execute(
            "INSERT INTO runs (id, project_id, entity_id, snapshot_id, cohort_id, plan_id, spec_id, method_id, document, result_digest, reproducibility_key, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run_id,
                document["project_id"],
                document["study_id"],
                document["snapshot_id"],
                document["cohort_id"],
                document.get("plan_id"),
                document["analysis_spec_id"],
                document["method_id"],
                _canonical(document),
                document.get("result_digest", ""),
                document.get("reproducibility_key", ""),
                document["created_at"],
            ),
        )
        _audit(connection, "run.executed", "analysis_run", run_id, {"method_id": document["method_id"], "spec_id": document["analysis_spec_id"]})
    return document


def list_runs(entity_id: str | None = None) -> list[dict[str, Any]]:
    with _connect() as connection:
        if entity_id:
            rows = connection.execute("SELECT * FROM runs WHERE entity_id = ? ORDER BY created_at", (entity_id,)).fetchall()
        else:
            rows = connection.execute("SELECT * FROM runs ORDER BY created_at").fetchall()
    return [_row_document(row) for row in rows]


def get_run(run_id: str) -> dict[str, Any] | None:
    with _connect() as connection:
        row = connection.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    return _row_document(row) if row else None


def append_evidence(project_id: str, entity_id: str, run_id: str, document: dict[str, Any]) -> dict[str, Any]:
    with _tx() as connection:
        existing = connection.execute("SELECT * FROM evidence WHERE run_id = ?", (run_id,)).fetchone()
        if existing is not None:
            return _row_document(existing)
        count = connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]
        evidence_id = f"EVID-U-{int(count) + 1:04d}"
        document = {**document, "id": evidence_id, "study_id": entity_id, "project_id": project_id, "analysis_run_id": run_id, "schema_version": SCHEMA_VERSION, "created_at": _now()}
        connection.execute(
            "INSERT INTO evidence (id, project_id, entity_id, run_id, document, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (evidence_id, project_id, entity_id, run_id, _canonical(document), document["created_at"]),
        )
        _audit(connection, "evidence.promoted", "evidence", evidence_id, {"run_id": run_id})
    return document


def list_evidence(entity_id: str | None = None) -> list[dict[str, Any]]:
    with _connect() as connection:
        if entity_id:
            rows = connection.execute("SELECT * FROM evidence WHERE entity_id = ? ORDER BY created_at", (entity_id,)).fetchall()
        else:
            rows = connection.execute("SELECT * FROM evidence ORDER BY created_at").fetchall()
    return [_row_document(row) for row in rows]


def get_evidence(evidence_id: str) -> dict[str, Any] | None:
    with _connect() as connection:
        row = connection.execute("SELECT * FROM evidence WHERE id = ?", (evidence_id,)).fetchone()
    return _row_document(row) if row else None


def append_figure(project_id: str, entity_id: str, run_id: str, evidence_id: str, document: dict[str, Any]) -> dict[str, Any]:
    with _tx() as connection:
        existing = connection.execute("SELECT * FROM figures WHERE evidence_id = ?", (evidence_id,)).fetchone()
        if existing is not None:
            return _row_document(existing)
        count = connection.execute("SELECT COUNT(*) FROM figures").fetchone()[0]
        figure_id = f"FIG-U-{int(count) + 1:04d}"
        document = {**document, "id": figure_id, "study_id": entity_id, "project_id": project_id, "analysis_run_id": run_id, "evidence_ids": [evidence_id], "schema_version": SCHEMA_VERSION, "created_at": _now()}
        connection.execute(
            "INSERT INTO figures (id, project_id, entity_id, run_id, evidence_id, document, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (figure_id, project_id, entity_id, run_id, evidence_id, _canonical(document), document["created_at"]),
        )
        _audit(connection, "figure.created", "figure", figure_id, {"evidence_id": evidence_id})
    return document


def list_figures(entity_id: str | None = None) -> list[dict[str, Any]]:
    with _connect() as connection:
        if entity_id:
            rows = connection.execute("SELECT * FROM figures WHERE entity_id = ? ORDER BY created_at", (entity_id,)).fetchall()
        else:
            rows = connection.execute("SELECT * FROM figures ORDER BY created_at").fetchall()
    return [_row_document(row) for row in rows]


def get_figure(figure_id: str) -> dict[str, Any] | None:
    with _connect() as connection:
        row = connection.execute("SELECT * FROM figures WHERE id = ?", (figure_id,)).fetchone()
    return _row_document(row) if row else None


# --------------------------------------------------------------------------- #
# Study detail and programme schedule
# --------------------------------------------------------------------------- #


def _count_by(items: Iterable[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        if not item.get("included", True):
            continue
        value = str(item.get(key) or "Participant")
        counts[value] = counts.get(value, 0) + 1
    return counts


def _data_health(entity: dict[str, Any], resolved: dict[str, Any]) -> dict[str, Any]:
    quality = resolved["trial_quality"]
    total = max(1, int(quality["expected"]))
    return {
        "valid_measurements": int(quality["valid"]),
        "excluded_measurements": int(quality["excluded"]),
        "missing_observations": int(quality["missing"]),
        "expected_slots": int(quality["expected"]),
        "missing_slots": quality["missing_slots"],
        "excluded_trials": quality["excluded_trials"],
        "complete_records": int(quality["valid"]),
        "total_records": total,
        "provenance_completeness": round(int(quality["valid"]) / total * 100, 1),
        "total_subjects": resolved["n"],
    }


def program_schedule(entity: dict[str, Any]) -> dict[str, Any]:
    snapshot_id = entity["dataset_snapshot_id"]
    metrics = dataset_metrics(snapshot_id)
    metric = (entity.get("outcomes", {}).get("primary") or [{}])[0]
    catalog_metric = next((item for item in metrics if item["id"] == metric.get("id")), metrics[0] if metrics else None)
    observed_axis = []
    observed_label = "Available readings"
    if catalog_metric:
        frame = read_snapshot_table(snapshot_id, catalog_metric["table"])
        axis = _axis_for_table(catalog_metric["table"])[0]
        if axis in frame.columns:
            values = frame[axis].drop_nulls().unique().to_list()
            observed_axis = sorted({int(value) for value in values}) if axis in {"occasion", "week", "trial_number"} else sorted(str(value) for value in values)
            observed_label = _axis_for_table(catalog_metric["table"])[1]
    schedule = entity.get("schedule", {})
    planned = schedule.get("points") or schedule.get("future_measurements") or []
    return {
        "schedule": schedule,
        "planned": planned,
        "observed_available": observed_axis,
        "observed_label": observed_label,
        "observed_note": "Deposited readings are historical and are not re-labelled as scheduled future measurements." if observed_axis else "No readings are attached yet.",
        "planned_count": len(planned),
        "observed_count": len(observed_axis),
        "status": "PLANNED_WITH_AVAILABLE_BASELINE" if observed_axis else "PLANNED_NO_READINGS",
        "limitations": [
            "A planned measurement without a reading is MISSING, not zero.",
            "No readiness, fatigue or injury score is computed.",
            "The schedule is prospective and is not evidence that a measurement occurred.",
        ],
    }


def study_detail(entity_id: str) -> dict[str, Any]:
    entity = get_entity(entity_id)
    if entity is None:
        raise ResearchNotFound(f"Research object {entity_id} not found")
    project = get_project(entity["project_id"])
    snapshot = get_snapshot(entity["dataset_snapshot_id"])
    if snapshot is None:
        raise ResearchNotFound(f"Snapshot {entity['dataset_snapshot_id']} is not admitted")
    cohorts = list_cohorts(entity_id)
    current_cohort = get_cohort(entity.get("cohort_id") or "") if entity.get("cohort_id") else (cohorts[-1] if cohorts else None)
    if current_cohort is None:
        raise ResearchNotFound(f"No cohort exists for {entity_id}")
    resolved = resolve_cohort(current_cohort, snapshot["id"])
    current_plan = get_plan(entity.get("analysis_plan_id") or "") if entity.get("analysis_plan_id") else None
    plans = list_plans(entity_id)
    specs = [plan_as_spec(plan, entity) for plan in plans if plan["status"] == "FROZEN"]
    if current_plan and current_plan["status"] == "DRAFT":
        specs.append(plan_as_spec(current_plan, entity))
    metrics = dataset_metrics(snapshot["id"])
    methods = methods_for_snapshot(snapshot["id"])
    plan_document = current_plan or (plans[0] if plans else {})
    plan_summary = {
        "id": plan_document.get("id", "—"),
        "status": plan_document.get("status", "DRAFT"),
        "frozen_before_inspection": False,
        "prospective": False,
        "primary_outcomes": [item["label"] for item in entity.get("outcomes", {}).get("primary", [])],
        "secondary_outcomes": [item["label"] for item in entity.get("outcomes", {}).get("secondary", [])],
        "exclusion_criteria": plan_document.get("exclusion_criteria") or entity.get("exclusions", []),
        "planned_models": plan_document.get("planned_models", ["No model frozen."]),
        "planned_contrasts": plan_document.get("contrasts", []),
        "primary_estimand": plan_document.get("primary_estimand", entity["question"]["estimand"]),
        "planned_reliability": plan_document.get("planned_reliability", "Not planned."),
        "post_plan_rule": "Changes after freeze create a new exploratory specification; frozen plans are never edited.",
        "immutability_rule": "Frozen plans, runs, evidence and report versions are append-only.",
        "freeze_note": plan_document.get("freeze_note", ""),
        "content_hash": plan_document.get("content_hash"),
        "parameters": plan_document.get("parameters", {}),
        "method_id": plan_document.get("method_id"),
        "outcome_metric_id": plan_document.get("outcome_metric_id"),
        "cohort_id": plan_document.get("cohort_id"),
        "spec_id": plan_document.get("spec_id"),
        "version": plan_document.get("version", 1),
    }
    protocol = entity.get("protocols", [])
    schedule = entity.get("schedule", {})
    numeric_points = [int(point) for point in schedule.get("points", []) if isinstance(point, (int, float))]
    start_week = int(schedule.get("start_week") or (numeric_points[0] if numeric_points else 1))
    if schedule.get("kind") == "PLANNED_WEEKLY":
        end_week = int(schedule.get("start_week", start_week)) + max(0, int(schedule.get("weeks") or 1) - 1)
    elif numeric_points:
        end_week = max(numeric_points)
    else:
        end_week = max(1, len(schedule.get("points", [])))
    study_summary = {
        "id": entity["id"],
        "title": entity["title"],
        "short_title": entity.get("short_title", entity["title"]),
        "state": entity["state"],
        "research_question": entity["research_question"],
        "design": f"{entity.get('design_label', entity['design'])}. Population: {entity.get('population', '')}",
        "design_code": entity["design"],
        "intervention": entity.get("intervention", ""),
        "primary_outcomes": [item["id"] for item in entity.get("outcomes", {}).get("primary", [])],
        "secondary_outcomes": [item["id"] for item in entity.get("outcomes", {}).get("secondary", [])],
        "dataset_snapshot_id": entity["dataset_snapshot_id"],
        "participant_count": resolved["n"],
        "start_week": start_week,
        "end_week": end_week,
        "protocol_ids": [item["id"] for item in protocol],
        "analysis_spec_ids": [spec["id"] for spec in specs],
        "created_at": entity["created_at"],
        "kind": entity["kind"],
        "project_id": entity["project_id"],
        "version": entity["version"],
    }
    runs = list_runs(entity_id)
    evidence = list_evidence(entity_id)
    figures = list_figures(entity_id)
    investigations = list_investigations(entity_id)
    eligibility = method_eligibility(entity, current_cohort, resolved, current_plan)
    detail = {
        "study": study_summary,
        "project": project,
        "kind": entity["kind"],
        "research": True,
        "real_data": bool(snapshot.get("real_data")),
        "question": entity["question"],
        "hypotheses": entity.get("hypotheses", []),
        "groups": {
            "ALL": {
                "label": entity.get("arms", [{}])[0].get("label", "All participants"),
                "arm": "INTERVENTION",
                "block_weeks": [start_week, end_week],
                "description": entity.get("arms", [{}])[0].get("description", ""),
            }
        },
        "cohort": {
            **{key: current_cohort.get(key) for key in ("id", "study_id", "name", "description", "subject_ids", "excluded_subject_ids", "exclusion_criteria", "snapshot_id", "status", "derived_from")},
            "subject_ids": resolved["cohort"]["subject_ids"],
            "status": current_cohort["status"],
            "included_subject_ids": resolved["cohort"]["subject_ids"],
        },
        "cohorts": cohorts,
        "current_cohort": current_cohort,
        "protocols": protocol,
        "schedule": schedule,
        "analysis_specs": specs,
        "plans": plans,
        "current_plan": current_plan,
        "plan": plan_summary,
        "snapshot": snapshot,
        "runs": runs,
        "evidence": evidence,
        "figures": figures,
        "arm_counts": resolved["arm_counts"],
        "position_counts": _count_by(resolved["athletes"], "position"),
        "data_health": _data_health(entity, resolved),
        "investigations": [{"id": item["id"], "title": item["title"], "status": item["status"], "block_count": len(item.get("blocks", []))} for item in investigations],
        "investigation_documents": investigations,
        "metrics": metrics,
        "methods": methods,
        "eligibility": eligibility,
        "designs": [{"id": key, "label": value} for key, value in DESIGN_LABELS.items()],
        "source": snapshot.get("source", {}),
        "state_history": entity.get("state_history", []),
        "allowed_transitions": sorted(ALLOWED_TRANSITIONS.get(entity["state"], [])),
        "entity_version": entity["version"],
        "resolved_cohort": resolved,
    }
    if entity["kind"] == "MONITORING":
        detail["program"] = program_schedule(entity)
    return detail


def method_eligibility(entity: dict[str, Any], cohort: dict[str, Any], resolved: dict[str, Any], plan: dict[str, Any] | None) -> list[dict[str, Any]]:
    snapshot = get_snapshot(entity["dataset_snapshot_id"])
    metrics = dataset_metrics(entity["dataset_snapshot_id"])
    table_by_metric = {item["id"]: item["table"] for item in metrics}
    outcome = (entity.get("outcomes", {}).get("primary") or [{}])[0].get("id") or (plan or {}).get("outcome_metric_id")
    table = table_by_metric.get(outcome)
    results = []
    for method in methods_for_snapshot(entity["dataset_snapshot_id"]):
        issues: list[str] = []
        if table not in method["required_tables"]:
            issues.append(f"Requires {', '.join(method['required_tables'])}; selected outcome is in {table}.")
        if resolved["n"] < 3 and method["id"] in {"METH-REAL-TREND", "METH-REAL-RELIABILITY"}:
            issues.append("At least three included participants are required.")
        if method["id"] == "METH-REAL-TREND":
            metric = next((item for item in metrics if item["id"] == outcome), None)
            if metric:
                frame = read_snapshot_table(entity["dataset_snapshot_id"], metric["table"])
                complete = 0
                for row in frame.iter_rows(named=True):
                    if row.get("subject_id") in set(resolved["cohort"]["subject_ids"]) and row.get(metric["column"]) is not None:
                        complete += 1
                if complete < 8:
                    issues.append(f"Only {complete} complete observations; at least 8 are required.")
        if method["id"] == "METH-REAL-RELIABILITY":
            activity = str((plan or {}).get("parameters", {}).get("activity") or "Walking")
            frame = read_snapshot_table(entity["dataset_snapshot_id"], "signal_trials")
            subset = frame.filter(pl.col("activity") == activity) if "activity" in frame.columns else frame
            counts: dict[str, int] = {}
            for row in subset.iter_rows(named=True):
                if row.get("subject_id") in set(resolved["cohort"]["subject_ids"]) and row.get("fz_peak_n") is not None:
                    counts[str(row["subject_id"])] = counts.get(str(row["subject_id"]), 0) + 1
            eligible = [subject for subject, count in counts.items() if count >= 2]
            if len(eligible) < 3:
                issues.append(f"Only {len(eligible)} participants have at least two {activity.lower()} trials.")
        results.append(
            {
                "method_id": method["id"],
                "name": method["name"],
                "status": "ELIGIBLE" if not issues else "INELIGIBLE",
                "issues": issues,
                "qualification": method["qualification"],
                "constraints": method["constraints"],
                "missingness": method["missingness"],
            }
        )
    for method in REJECTED_METHODS.values():
        results.append(
            {
                "method_id": method["id"],
                "name": method["name"],
                "status": "REJECTED",
                "issues": [method["reason"]],
                "qualification": method["qualification"],
                "constraints": [],
                "missingness": "",
            }
        )
    return results


# --------------------------------------------------------------------------- #
# Reports
# --------------------------------------------------------------------------- #


def _default_report(entity: dict[str, Any], project: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "id": f"RPT-{entity['id'].split('-')[-1]}",
        "entity_id": entity["id"],
        "study_id": entity["id"],
        "project_id": entity["project_id"],
        "title": f"Research report · {entity['title']}",
        "version": 1,
        "status": "DRAFT",
        "evidence_ids": [],
        "figure_ids": [],
        "citations": [],
        "summary": "",
        "conclusion": "",
        "recommendations": "",
        "narrative_note": "",
        "created_at": _now(),
        "updated_at": _now(),
        "schema_version": SCHEMA_VERSION,
    }


def _ensure_report_row(connection: sqlite3.Connection, entity: dict[str, Any]) -> dict[str, Any]:
    row = connection.execute("SELECT * FROM reports WHERE entity_id = ?", (entity["id"],)).fetchone()
    if row is not None:
        return _row_document(row)
    project = get_project(entity["project_id"])
    report = _default_report(entity, project)
    connection.execute(
        "INSERT INTO reports (entity_id, project_id, version, status, document, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        (entity["id"], entity["project_id"], 1, "DRAFT", _canonical(report), report["updated_at"]),
    )
    return report


def get_report_document(entity_id: str) -> dict[str, Any]:
    entity = get_entity(entity_id)
    if entity is None:
        raise ResearchNotFound(f"Research object {entity_id} not found")
    with _connect() as connection:
        report = _ensure_report_row(connection, entity)
    return report


def update_report(entity_id: str, patch: dict[str, Any], base_version: int | None = None) -> dict[str, Any]:
    entity = get_entity(entity_id)
    if entity is None:
        raise ResearchNotFound(f"Research object {entity_id} not found")
    with _tx() as connection:
        report = _ensure_report_row(connection, entity)
        if base_version is not None and int(base_version) != int(report["version"]):
            raise ResearchConflict(f"Report is at version {report['version']}, not {base_version}")
        for key in ("title", "summary", "conclusion", "recommendations", "narrative_note"):
            if key in patch:
                report[key] = str(patch[key])
        if not report.get("title", "").strip():
            raise ResearchValidation("A report title is required")
        report["version"] = int(report["version"]) + 1
        report["status"] = "DRAFT"
        report.pop("frozen_at", None)
        report.pop("content_hash", None)
        report["updated_at"] = _now()
        connection.execute(
            "UPDATE reports SET version = ?, status = 'DRAFT', document = ?, updated_at = ? WHERE entity_id = ?",
            (report["version"], _canonical(report), report["updated_at"], entity_id),
        )
        _audit(connection, "report.updated", "report", report["id"], patch)
    return report


def report_payload(entity_id: str) -> dict[str, Any]:
    detail = study_detail(entity_id)
    report = get_report_document(entity_id)
    evidence = [item for item in detail["evidence"] if item["id"] in report.get("evidence_ids", [])]
    figures = [item for item in detail["figures"] if item["id"] in report.get("figure_ids", [])]
    runs_by_id = {run["id"]: run for run in detail["runs"]}
    report["evidence"] = evidence
    report["figures"] = [{**figure, "data": figure.get("data")} for figure in figures]
    report["runs"] = [runs_by_id[item["analysis_run_id"]] for item in evidence if item["analysis_run_id"] in runs_by_id]
    report["study"] = detail["study"]
    report["project"] = detail["project"]
    report["question"] = detail["question"]
    report["hypotheses"] = detail["hypotheses"]
    report["plan"] = detail["plan"]
    report["cohort"] = detail["cohort"]
    report["snapshot"] = detail["snapshot"]
    report["groups"] = detail["groups"]
    report["data_health"] = detail["data_health"]
    report["research"] = {
        "kind": detail["kind"],
        "design": detail["study"]["design"],
        "protocols": detail["protocols"],
        "methods": [spec for spec in detail["analysis_specs"] if spec["status"] == "FROZEN"],
        "eligibility": detail["eligibility"],
        "limitations": report_limitations(detail),
        "provenance_note": "Every cited result resolves to a frozen plan, an immutable run, a resolved cohort, an admitted snapshot and its source DOI/licence.",
        "program": detail.get("program"),
    }
    report["provenance_note"] = report["research"]["provenance_note"]
    report["export_url"] = f"/research/studies/{entity_id}/report/export"
    return report


def report_limitations(detail: dict[str, Any]) -> list[str]:
    snapshot = detail["snapshot"]
    source = snapshot.get("source", {})
    limitations = []
    if detail.get("kind") == "MONITORING":
        limitations.extend(
            [
                "Planned measurements are schedule entries, not observations. A planned point without a reading is missing.",
                "No readiness, fatigue or injury diagnosis is computed from deviations.",
                "Historical readings from the bound snapshot are not forced onto the prospective calendar.",
            ]
        )
    if snapshot.get("real_data"):
        limitations.append(
            f"Observational data from {source.get('doi') or source.get('id')}: no causal intervention effect is inferred unless a design with a real comparator is present."
        )
        if "cmj_occasions" in (snapshot.get("tables") or {}):
            limitations.append("Testing occasions are not calendar weeks; the model uses occasion as the time axis.")
            limitations.append("The deposit contains derived scalars only; CMJ height cannot be recomputed from raw force traces.")
        if "signal_trials" in (snapshot.get("tables") or {}):
            limitations.append("Repeated trials measure within-activity reliability; they are not a longitudinal training study.")
            limitations.append("No sample-level IMU-to-force synchronisation is claimed.")
    else:
        limitations.append("The dataset is explicitly SYNTHETIC; results have no external validity.")
    limitations.extend(detail["plan"].get("exclusion_criteria", []) or [])
    return limitations


def cite_artifact(entity_id: str, artifact_id: str, section: str | None = None) -> dict[str, Any]:
    entity = get_entity(entity_id)
    if entity is None:
        raise ResearchNotFound(f"Research object {entity_id} not found")
    evidence = get_evidence(artifact_id)
    figure = get_figure(artifact_id)
    if evidence is None and figure is None:
        raise ResearchNotFound(f"Artifact {artifact_id} not found")
    kind = "figure" if figure is not None else "evidence"
    if section is None:
        section = "Primary result" if evidence and evidence.get("kind") in {"EFFECT", "RELIABILITY"} else ("Measurement qualification" if evidence and evidence.get("kind") == "DESCRIPTIVE" else "Exploratory results")
    with _tx() as connection:
        report = _ensure_report_row(connection, entity)
        if artifact_id in report.get("evidence_ids" if kind == "evidence" else "figure_ids", []):
            return {"report_id": report["id"], "artifact_id": artifact_id, "section": section, "already_cited": True, "version": report["version"]}
        report.setdefault("evidence_ids" if kind == "evidence" else "figure_ids", []).append(artifact_id)
        report.setdefault("citations", []).append({"artifact_id": artifact_id, "kind": kind, "section": section, "added_at": _now()})
        report["version"] = int(report["version"]) + 1
        report["status"] = "DRAFT"
        report["updated_at"] = _now()
        connection.execute(
            "UPDATE reports SET version = ?, status = 'DRAFT', document = ?, updated_at = ? WHERE entity_id = ?",
            (report["version"], _canonical(report), report["updated_at"], entity_id),
        )
        _audit(connection, "report.cited", "report", report["id"], {"artifact_id": artifact_id, "section": section})
    return {"report_id": report["id"], "artifact_id": artifact_id, "section": section, "already_cited": False, "version": report["version"]}


def uncite_artifact(entity_id: str, artifact_id: str) -> dict[str, Any]:
    entity = get_entity(entity_id)
    if entity is None:
        raise ResearchNotFound(f"Research object {entity_id} not found")
    with _tx() as connection:
        report = _ensure_report_row(connection, entity)
        removed = False
        for key in ("evidence_ids", "figure_ids"):
            if artifact_id in report.get(key, []):
                report[key] = [item for item in report[key] if item != artifact_id]
                removed = True
        report["citations"] = [item for item in report.get("citations", []) if item["artifact_id"] != artifact_id]
        if not removed:
            raise ResearchNotFound(f"{artifact_id} is not cited in the report")
        report["version"] = int(report["version"]) + 1
        report["status"] = "DRAFT"
        report["updated_at"] = _now()
        connection.execute(
            "UPDATE reports SET version = ?, status = 'DRAFT', document = ?, updated_at = ? WHERE entity_id = ?",
            (report["version"], _canonical(report), report["updated_at"], entity_id),
        )
        _audit(connection, "report.uncited", "report", report["id"], {"artifact_id": artifact_id})
    return {"report_id": report["id"], "artifact_id": artifact_id, "removed": True, "version": report["version"]}


def freeze_report(entity_id: str) -> dict[str, Any]:
    entity = get_entity(entity_id)
    if entity is None:
        raise ResearchNotFound(f"Research object {entity_id} not found")
    payload = report_payload(entity_id)
    with _tx() as connection:
        report = _ensure_report_row(connection, entity)
        content = {
            "title": payload["title"],
            "summary": payload.get("summary", ""),
            "conclusion": payload.get("conclusion", ""),
            "recommendations": payload.get("recommendations", ""),
            "narrative_note": payload.get("narrative_note", ""),
            "study_id": entity_id,
            "project_id": entity["project_id"],
            "evidence_ids": payload["evidence_ids"],
            "figure_ids": payload["figure_ids"],
            "citations": payload["citations"],
            "evidence": payload["evidence"],
            "figures": payload["figures"],
            "plan": payload["plan"],
            "cohort": payload["cohort"],
            "snapshot_id": payload["snapshot"]["id"],
            "snapshot_checksums": payload["snapshot"].get("checksums", {}),
            "limitations": payload["research"]["limitations"],
        }
        content_hash = _digest(content)
        version = int(report["version"])
        existing = connection.execute(
            "SELECT content_hash FROM report_versions WHERE entity_id = ? AND version = ?",
            (entity_id, version),
        ).fetchone()
        if existing is not None:
            if existing["content_hash"] != content_hash:
                raise ResearchConflict("This report version is already frozen with different content")
            return {"report_id": report["id"], "version": version, "status": "FROZEN", "content_hash": content_hash, "frozen_at": report.get("frozen_at")}
        frozen_at = _now()
        report["status"] = "FROZEN"
        report["frozen_at"] = frozen_at
        report["content_hash"] = content_hash
        report["updated_at"] = frozen_at
        connection.execute(
            "INSERT INTO report_versions (entity_id, version, status, content_hash, document, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (entity_id, version, "FROZEN", content_hash, _canonical({**report, "frozen_content": content}), frozen_at),
        )
        connection.execute(
            "UPDATE reports SET status = 'FROZEN', document = ?, updated_at = ? WHERE entity_id = ?",
            (_canonical(report), report["updated_at"], entity_id),
        )
        _audit(connection, "report.frozen", "report", report["id"], {"version": version, "content_hash": content_hash})
    return {"report_id": report["id"], "version": version, "status": "FROZEN", "content_hash": content_hash, "frozen_at": report["frozen_at"]}


def report_versions(entity_id: str) -> list[dict[str, Any]]:
    with _connect() as connection:
        rows = connection.execute(
            "SELECT version, status, content_hash, created_at FROM report_versions WHERE entity_id = ? ORDER BY version DESC",
            (entity_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_report_version(entity_id: str, version: int) -> dict[str, Any] | None:
    with _connect() as connection:
        row = connection.execute(
            "SELECT * FROM report_versions WHERE entity_id = ? AND version = ?",
            (entity_id, version),
        ).fetchone()
    if row is None:
        return None
    document = json.loads(row["document"])
    document.setdefault("frozen_at", row["created_at"])
    document["status"] = "FROZEN"
    return document


# --------------------------------------------------------------------------- #
# Lineage
# --------------------------------------------------------------------------- #


def lineage(artifact_id: str) -> dict[str, Any]:
    nodes: dict[str, dict[str, Any]] = {}
    edges: dict[str, dict[str, Any]] = {}

    def node(node_id: str, kind: str, label: str, metadata: str, detail: dict[str, Any] | None = None) -> None:
        nodes.setdefault(node_id, {"id": node_id, "kind": kind, "label": label, "metadata": metadata, "detail": detail or {}})

    def edge(source: str, target: str, relation: str, label: str) -> None:
        edge_id = f"LE-{source}->{target}"
        edges.setdefault(edge_id, {"id": edge_id, "source": source, "target": target, "relation": relation, "label": label})

    entity = get_entity(artifact_id)
    if entity:
        pass
    run = get_run(artifact_id)
    evidence = get_evidence(artifact_id)
    figure = get_figure(artifact_id)
    if run:
        entity = get_entity(run["study_id"])
    elif evidence:
        entity = get_entity(evidence["study_id"])
    elif figure:
        entity = get_entity(figure["study_id"])
    if entity is None:
        # Plans, cohorts, reports and snapshots resolve through their own tables.
        plan = get_plan(artifact_id)
        if plan:
            entity = get_entity(plan["study_id"])
        cohort = get_cohort(artifact_id)
        if cohort:
            entity = get_entity(cohort["study_id"])
        if not entity:
            for candidate in list_entities():
                detail = study_detail(candidate["id"])
                report = get_report_document(candidate["id"])
                if artifact_id in {run["id"] for run in detail["runs"]} | {item["id"] for item in detail["evidence"]} | {item["id"] for item in detail["figures"]} | {report["id"], candidate["id"], candidate["dataset_snapshot_id"]}:
                    entity = candidate
                    break
    if entity is None:
        raise KeyError(f"Artifact {artifact_id} is not part of a user-authored research project")
    detail = study_detail(entity["id"])
    snapshot = detail["snapshot"]
    source = snapshot.get("source", {})
    project = detail["project"]
    report = get_report_document(entity["id"])
    node(entity["project_id"], "project", project["title"], f"{project['id']} · research project", project)
    node(entity["id"], "study", entity["title"], f"{entity['kind']} · {entity['state']}", entity)
    edge(entity["project_id"], entity["id"], "contains", "research project")
    source_node = f"SRC-{source.get('id', 'SOURCE')}"
    node(source_node, "source", str(source.get("publisher") or source.get("id") or "Source"), f"DOI {source.get('doi') or '—'} · {source.get('license', {}).get('id') if isinstance(source.get('license'), dict) else source.get('license') or '—'}", source)
    node(snapshot["id"], "snapshot", snapshot.get("label", snapshot["id"]), f"{sum(snapshot.get('row_counts', {}).values()):,} rows · immutable", {"checksums": snapshot.get("checksums", {})})
    edge(source_node, snapshot["id"], "admitted_as", "rights + QC + harmonisation")
    edge(entity["id"], snapshot["id"], "binds", "dataset snapshot")
    for cohort in detail["cohorts"]:
        node(cohort["id"], "cohort", cohort.get("name", cohort["id"]), f"n={len(cohort.get('resolved', {}).get('included_subjects', cohort.get('subject_ids', [])))} · {cohort['status']}", cohort)
        edge(snapshot["id"], cohort["id"], "restricted_to", "declarative cohort")
        edge(entity["id"], cohort["id"], "uses_cohort", "cohort definition")
    for plan in detail["plans"]:
        node(plan["id"], "spec", plan.get("name", plan["id"]), f"{plan.get('method_id')} · {plan['status']}", plan)
        edge(plan.get("cohort_id", ""), plan["id"], "analysed_by", "analysis plan")
        for run in detail["runs"]:
            if run.get("plan_id") == plan["id"]:
                edge(plan["id"], run["id"], "executed_as", "frozen specification")
    for run in detail["runs"]:
        node(run["id"], "run", f"{run.get('method_id')} · {run.get('status')}", f"{run.get('created_at', '')[:19]} · {str(run.get('result_digest', ''))[:12]}", run)
        edge(run["cohort_id"], run["id"], "read_from", "resolved cohort")
        edge(run["snapshot_id"], run["id"], "read_from", "immutable input")
    for item in detail["evidence"]:
        node(item["id"], "evidence", item.get("title", item["id"]), f"{item.get('kind')} · {item.get('quality')}", item)
        edge(item["analysis_run_id"], item["id"], "promoted_to", "explicit promotion")
    for item in detail["figures"]:
        node(item["id"], "figure", item.get("title", item["id"]), item.get("kind", "figure"), item)
        for evidence_id in item.get("evidence_ids", []):
            edge(evidence_id, item["id"], "rendered_as", "figure artifact")
    if report.get("evidence_ids"):
        node(report["id"], "report", report.get("title", "Report"), f"{report.get('status')} · v{report.get('version')}", report)
        for evidence_id in report.get("evidence_ids", []):
            edge(evidence_id, report["id"], "cited_in", "report citation")
        for figure_id in report.get("figure_ids", []):
            edge(figure_id, report["id"], "cited_in", "report citation")
    if artifact_id not in nodes:
        raise KeyError(f"Artifact {artifact_id} is not present in its project lineage")
    return {"nodes": list(nodes.values()), "edges": list(edges.values()), "root": artifact_id, "artifact_id": artifact_id}


# --------------------------------------------------------------------------- #
# HTML export
# --------------------------------------------------------------------------- #


def _svg_line(figure: dict[str, Any], width: int = 640, height: int = 220) -> str:
    series = (figure.get("data") or {}).get("series") or []
    points = [(item.get("week"), item.get("mean")) for item in series if item.get("mean") is not None]
    if not points:
        return "<p class='muted'>No plotted data.</p>"
    xs = [float(item[0]) for item in points]
    ys = [float(item[1]) for item in points]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    if xmax == xmin:
        xmax += 1
    if ymax == ymin:
        ymax += 1
    pad = 30
    def sx(value: float) -> float:
        return pad + (value - xmin) / (xmax - xmin) * (width - 2 * pad)
    def sy(value: float) -> float:
        return height - pad - (value - ymin) / (ymax - ymin) * (height - 2 * pad)
    polyline = " ".join(f"{sx(x):.1f},{sy(y):.1f}" for x, y in points)
    dots = "".join(f"<circle cx='{sx(x):.1f}' cy='{sy(y):.1f}' r='3'/>" for x, y in points)
    labels = "".join(f"<text x='{sx(x):.1f}' y='{height - 8}' font-size='10' text-anchor='middle'>{int(x)}</text>" for x in xs)
    return f"<svg viewBox='0 0 {width} {height}' width='100%' role='img' aria-label='{html.escape(str(figure.get('title', 'figure')))}'><line x1='{pad}' y1='{height-pad}' x2='{width-pad}' y2='{height-pad}' stroke='#4a4a4a'/><line x1='{pad}' y1='{pad}' x2='{pad}' y2='{height-pad}' stroke='#4a4a4a'/><polyline points='{polyline}' fill='none' stroke='#d9a650' stroke-width='2'/>{dots}{labels}</svg>"


def _svg_distribution(figure: dict[str, Any], width: int = 640, height: int = 180) -> str:
    values = [float(value) for value in (figure.get("data") or {}).get("values", []) if value is not None]
    if not values:
        return "<p class='muted'>No plotted data.</p>"
    maximum = max(values) or 1
    bar_width = max(4, (width - 40) / max(1, len(values)) - 4)
    bars = "".join(
        f"<rect x='{20 + index * (bar_width + 4):.1f}' y='{height - 20 - (value / maximum) * (height - 40):.1f}' width='{bar_width:.1f}' height='{(value / maximum) * (height - 40):.1f}' fill='#6fb3a0'/>"
        for index, value in enumerate(values)
    )
    return f"<svg viewBox='0 0 {width} {height}' width='100%' role='img' aria-label='distribution'>{bars}</svg>"


def export_html(entity_id: str, version: int | None = None) -> str:
    payload = report_payload(entity_id)
    generated_at = _now()
    if version is not None:
        frozen = get_report_version(entity_id, version)
        if frozen is None:
            raise ResearchNotFound(f"Report version {version} not found")
        # Frozen content is authoritative for historical exports.
        payload = {**payload, **frozen.get("frozen_content", {}), "status": "FROZEN", "version": version}
        generated_at = frozen.get("created_at") or frozen.get("frozen_at") or generated_at
    detail = study_detail(entity_id)
    snapshot = detail["snapshot"]
    evidence = payload.get("evidence", [])
    figures = payload.get("figures", [])
    limitations = payload.get("research", {}).get("limitations", [])
    manifest = {
        "report_id": payload.get("id"),
        "study_id": entity_id,
        "project_id": detail["project"]["id"],
        "snapshot_id": snapshot["id"],
        "snapshot_checksums": snapshot.get("checksums", {}),
        "source": snapshot.get("source", {}),
        "evidence": [{"id": item["id"], "run": item["analysis_run_id"], "spec": item.get("analysis_spec_id"), "digest": item.get("result_digest"), "interval": item.get("interval")} for item in evidence],
        "figures": [{"id": item["id"], "evidence_ids": item.get("evidence_ids", [])} for item in figures],
        "generated_at": generated_at,
        "limitations": limitations,
    }
    rows = "".join(
        f"<tr><td>{html.escape(item['id'])}</td><td>{html.escape(item.get('title', ''))}</td><td>{html.escape(str(item.get('estimate')))} {html.escape(str(item.get('unit', '')))}</td><td>{html.escape(str(item.get('interval', {}).get('low') if item.get('interval') else ''))} – {html.escape(str(item.get('interval', {}).get('high') if item.get('interval') else ''))}</td><td>{html.escape(item.get('analysis_run_id', ''))}</td><td>{html.escape(item.get('interpretation', ''))}</td></tr>"
        for item in evidence
    )
    figure_html = "".join(
        f"<figure><figcaption><strong>{html.escape(item.get('title', ''))}</strong> · {html.escape(item['id'])}</figcaption>{_svg_line(item) if item.get('kind') == 'LINE' else _svg_distribution(item) if item.get('kind') == 'DISTRIBUTION' else '<p class=\"muted\">Figure data is stored in the manifest.</p>'}</figure>"
        for item in figures
    )
    limitation_html = "".join(f"<li>{html.escape(item)}</li>" for item in limitations)
    source = snapshot.get("source", {})
    title = html.escape(payload.get("title", "Research report"))
    narrative = "".join(
        f"<h2>{html.escape(label)}</h2><p>{html.escape(str(payload.get(key) or ''))}</p>"
        for key, label in (
            ("summary", "Summary"),
            ("conclusion", "Conclusion"),
            ("recommendations", "Recommendations"),
            ("narrative_note", "Researcher notes"),
        )
        if payload.get(key)
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
:root {{ color-scheme: dark; }}
body {{ margin:0; background:#0e0f10; color:#d7d7d3; font:14px/1.55 "IBM Plex Sans",system-ui,sans-serif; }}
main {{ max-width: 940px; margin: 0 auto; padding: 42px 30px 70px; }}
h1 {{ font-size:26px; color:#f1efe9; letter-spacing:-.02em; }}
h2 {{ margin-top:30px; padding-bottom:6px; border-bottom:1px solid #333; font-size:16px; color:#f1efe9; }}
.meta {{ color:#8e8e88; font-family:ui-monospace,monospace; font-size:12px; }}
table {{ border-collapse:collapse; width:100%; font-size:12.5px; }}
th,td {{ border-bottom:1px solid #2e2e2e; padding:7px 6px; text-align:left; vertical-align:top; }}
th {{ color:#a9a9a2; font-weight:600; }}
figure {{ margin:18px 0; border:1px solid #2e2e2e; padding:12px; }}
figcaption {{ color:#a9a9a2; font-size:12px; margin-bottom:8px; }}
.muted {{ color:#8e8e88; }}
.badge {{ display:inline-block; border:1px solid #4a4a4a; padding:1px 6px; font-size:11px; margin-right:6px; }}
pre {{ white-space:pre-wrap; background:#161718; padding:12px; border:1px solid #2e2e2e; font-size:11px; }}
</style></head>
<body><main>
<div class="meta">{html.escape(payload.get('id',''))} · {html.escape(str(payload.get('status','DRAFT')))} · version {html.escape(str(payload.get('version','')))}</div>
<h1>{title}</h1>
<p class="muted">{html.escape(detail['study']['title'])} · {html.escape(detail['project']['title'])}</p>
<h2>1. Question and design</h2>
<p>{html.escape(detail['question']['statement'])}</p>
<p>{html.escape(detail['study']['design'])}</p>
<ul>{''.join(f"<li><span class='meta'>{html.escape(item['id'])}</span> ({html.escape(item['status'].lower())}) {html.escape(item['statement'])}</li>" for item in detail['hypotheses'])}</ul>
<h2>2. Dataset and cohort</h2>
<p>Snapshot <span class="meta">{html.escape(snapshot['id'])}</span>, {html.escape(str(sum(snapshot.get('row_counts', {}).values())))} rows. Source DOI <span class="meta">{html.escape(str(source.get('doi') or '—'))}</span>, licence {html.escape(str(source.get('license', {}).get('id') if isinstance(source.get('license'), dict) else source.get('license') or '—'))}. Privacy {html.escape(str(source.get('privacy', {}).get('classification') if isinstance(source.get('privacy'), dict) else '—'))}.</p>
<p>Cohort <span class="meta">{html.escape(detail['cohort']['id'])}</span> ({html.escape(detail['cohort']['status'])}) includes {len(detail['cohort']['subject_ids'])} participants. {html.escape(str(detail['cohort'].get('description') or ''))}</p>
<h2>3. Methods and estimand</h2>
<p>{html.escape(detail['plan']['primary_estimand'])}</p>
<p class="meta">{html.escape(str(detail['plan'].get('method_id') or ''))} · {html.escape(detail['plan']['status'])} · {html.escape(str(detail['plan'].get('parameters', {})))}</p>
<h2>4. Results</h2>
{'<p class="muted">No evidence is cited. Promote a run and add it to the report.</p>' if not evidence else f'<table><thead><tr><th>Evidence</th><th>Result</th><th>Estimate</th><th>95% interval</th><th>Run</th><th>Computed interpretation</th></tr></thead><tbody>{rows}</tbody></table>'}
{figure_html}
{narrative}
<h2>5. Limitations</h2><ul>{limitation_html}</ul>
<h2>6. Provenance and reproducibility</h2>
<p>Every cited value resolves to an immutable run, a frozen analysis plan, a resolved cohort, the admitted snapshot and its source. The manifest below is embedded in this file.</p>
<pre id="manifest">{html.escape(json.dumps(manifest, indent=2, sort_keys=True))}</pre>
</main></body></html>"""


def report_export_filename(entity_id: str, version: int | None = None) -> str:
    suffix = f"-v{version}" if version else ""
    return f"{entity_id}{suffix}-report.html"
