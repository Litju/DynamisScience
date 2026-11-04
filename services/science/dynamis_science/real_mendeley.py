"""Adapter for the Mendeley Sprint Priming longitudinal deposit.

The deposit is a single Excel workbook of *derived* scalar outcomes.  It does
not contain force-time traces.  The adapter preserves every native column,
adds explicitly named canonical columns, and records the inferential limits of
the deposit rather than pretending it is raw force data.
"""

from __future__ import annotations

import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import polars as pl

from .real_sources import MENDELEY_SOURCE

PARSER_VERSION = "dynamis-mendeley-sprint@1.0.0"
SCHEMA_VERSION = "dynamis-science.real.mendeley@1.0.0"

# Native column -> canonical name.  All source values are preserved verbatim;
# canonical columns are explicit conversions, never silent replacements.
COLUMN_MAP: dict[str, str] = {
    "ID": "native_subject_id",
    "COND": "occasion",
    "prevspost": "phase",
    "age": "age_years",
    "ht": "height_cm",
    "wt": "body_mass_kg",
    "sprinttimea": "sprint_20m_s",
    "sprinttimeb": "sprint_0_10m_s",
    "sprinttimec": "sprint_10_20m_s",
    "isonetpeakforce": "isometric_net_peak_force_n",
    "isopeakforce": "isometric_peak_force_n",
    "isorelativepeakforce": "isometric_relative_peak_force_n_kg",
    "isoforcea": "isometric_force_a_n",
    "isoforceb": "isometric_force_b_n",
    "isoforcec": "isometric_force_c_n",
    "CMJht": "cmj_height_m",
    "CONmeanforce": "cmj_concentric_mean_force_n",
    "CONphasetime": "cmj_concentric_phase_duration_s",
    "meanbrakingforce": "cmj_mean_braking_force_n",
    "brakingphasetime": "cmj_braking_phase_duration_s",
    "CMdisplacement": "cmj_countermovement_displacement_m",
    "RSI": "rsi_modified_m_s",
    "BS": "back_squat_1rm_kg",
    "BSrel": "back_squat_relative_kg_kg",
}

METRIC_DEFINITIONS = [
    {
        "id": "MET-REAL-CMJ-HEIGHT",
        "canonical_id": "cmj.jump_height.deposited",
        "name": "Countermovement jump height",
        "quantity": "length",
        "unit": "cm",
        "native_column": "CMJht",
        "native_unit": "m",
        "conversion": "x 100 (m -> cm)",
        "method": "Deposited scalar from dual Hawkin Dynamics force plates (1000 Hz); exact jump-height algorithm not documented in the deposit.",
        "protocol_id": "PROT-REAL-CMJ-FP",
        "algorithm": "deposited derived outcome",
        "version": "1.0.0",
        "dependencies": [],
        "known_limitations": [
            "No raw force trace is deposited, so the derivation cannot be independently recomputed.",
            "The workbook does not state whether height is flight-time derived or take-off velocity derived.",
        ],
    },
    {
        "id": "MET-REAL-ISO-REL-PEAK",
        "canonical_id": "isometric.relative_peak_force.deposited",
        "name": "Isometric squat relative peak force",
        "quantity": "force per mass",
        "unit": "N/kg",
        "native_column": "isorelativepeakforce",
        "native_unit": "N/kg",
        "conversion": "none",
        "method": "Deposited relative peak force from an isometric squat on dual force plates.",
        "protocol_id": "PROT-REAL-ISO-SQUAT",
        "algorithm": "deposited derived outcome",
        "version": "1.0.0",
        "dependencies": [],
        "known_limitations": [
            "The deposited relative value is not exactly reproducible from the deposited body mass and peak force for every row; the reference mass is not documented.",
        ],
    },
    {
        "id": "MET-REAL-SPRINT-20M",
        "canonical_id": "sprint.20m_time",
        "name": "20 m sprint time",
        "quantity": "time",
        "unit": "s",
        "native_column": "sprinttimea",
        "native_unit": "s",
        "conversion": "none",
        "method": "Brower infrared timing gates with a motion start sensor.",
        "protocol_id": "PROT-REAL-SPRINT-20M",
        "algorithm": "direct timing",
        "version": "1.0.0",
        "dependencies": ["sprint.0_10m_time", "sprint.10_20m_time"],
        "known_limitations": [
            "The 20 m time equals the sum of the two 10 m splits to machine precision, so the splits are not independent measurements.",
        ],
    },
    {
        "id": "MET-REAL-BS-REL",
        "canonical_id": "strength.back_squat.relative_1rm",
        "name": "Relative 1RM back squat",
        "quantity": "mass ratio",
        "unit": "kg/kg",
        "native_column": "BSrel",
        "native_unit": "kg/kg",
        "conversion": "none",
        "method": "1RM back squat divided by body mass; four deposited values are inconsistent with BS/wt and are quarantined from analysis.",
        "protocol_id": "PROT-REAL-1RM-SQUAT",
        "algorithm": "deposited derived outcome",
        "version": "1.0.0",
        "dependencies": ["strength.back_squat.1rm"],
        "known_limitations": [
            "Four of 82 rows disagree with BS/wt by more than 0.05 kg/kg; the native values are retained but flagged.",
        ],
    },
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _frame_sha256(frame: pl.DataFrame) -> str:
    buffer = io.BytesIO()
    frame.write_parquet(buffer)
    return hashlib.sha256(buffer.getvalue()).hexdigest()


def _read_workbook(path: Path) -> list[dict[str, Any]]:
    import openpyxl

    workbook = openpyxl.load_workbook(path, data_only=True, read_only=True)
    sheet = workbook["DATA"]
    rows = list(sheet.iter_rows(values_only=True))
    header = [str(value).strip() if value is not None else "" for value in rows[0]]
    records: list[dict[str, Any]] = []
    for index, row in enumerate(rows[1:], start=2):
        if row[0] is None:
            continue
        record = {header[i]: row[i] for i in range(len(header)) if header[i]}
        record["_excel_row"] = index
        records.append(record)
    workbook.close()
    return records


def _qualify(record: dict[str, Any]) -> tuple[str, list[str], list[str]]:
    """Return (quality_state, flags, quarantined_fields) for one native row."""
    flags: list[str] = []
    quarantined: list[str] = []
    if record["prevspost"] == "pre":
        flags.append("SPRINT_ONLY_BY_PROTOCOL")
    if record["prevspost"] == "post" and record.get("CMJht") is None:
        flags.append("CMJ_NOT_DEPOSITED")
        quarantined.append("cmj_height_m")
    if record.get("body_mass_kg") is None or record["body_mass_kg"] <= 0:
        flags.append("BODY_MASS_MISSING")
        quarantined.append("body_mass_kg")
    if record.get("BSrel") is not None and record.get("BS") is not None and record.get("wt"):
        computed = float(record["BS"]) / float(record["wt"])
        if abs(float(record["BSrel"]) - computed) > 0.05:
            flags.append("BSREL_INCONSISTENT_WITH_BS_OVER_WT")
            quarantined.append("back_squat_relative_kg_kg")
    if record.get("isorelativepeakforce") and record.get("isopeakforce") and record.get("wt"):
        computed = float(record["isopeakforce"]) / float(record["wt"])
        if abs(float(record["isorelativepeakforce"]) - computed) > 0.2:
            flags.append("ISO_RELATIVE_REFERENCE_MASS_UNDOCUMENTED")
    status = "VALID"
    if quarantined:
        status = "WARNING"
    if record["prevspost"] == "post" and record.get("CMJht") is None:
        status = "MISSING"
    return status, flags, quarantined


def build_tables(path: Path) -> dict[str, pl.DataFrame]:
    records = _read_workbook(path)
    if len(records) != 168:
        raise ValueError(f"Expected 168 athlete-occasion-phase rows, found {len(records)}")
    mapped: list[dict[str, Any]] = []
    for record in records:
        row: dict[str, Any] = {}
        for native, canonical in COLUMN_MAP.items():
            row[canonical] = record.get(native)
        row["source_row"] = record["_excel_row"]
        row["subject_id"] = f"MEN-{int(record['ID']):02d}"
        row["session_id"] = f"MEN-{int(record['ID']):02d}-O{int(record['COND'])}"
        row["trial_id"] = f"MEN-{int(record['ID']):02d}-O{int(record['COND'])}-{record['prevspost'].upper()}"
        row["occasion"] = int(record["COND"])
        row["phase"] = str(record["prevspost"]).upper()
        row["cmj_height_cm"] = (
            float(record["CMJht"]) * 100.0 if record.get("CMJht") is not None else None
        )
        if record.get("CMJht") is not None:
            row["cmj_flight_time_s"] = (8.0 * float(record["CMJht"]) / 9.80665) ** 0.5
        else:
            row["cmj_flight_time_s"] = None
        row["body_weight_n"] = (
            float(record["wt"]) * 9.80665 if record.get("wt") is not None else None
        )
        row["sprint_split_sum_s"] = (
            float(record["sprinttimeb"]) + float(record["sprinttimec"])
            if record.get("sprinttimeb") is not None and record.get("sprinttimec") is not None
            else None
        )
        row["sprint_split_residual_s"] = (
            float(record["sprinttimea"]) - row["sprint_split_sum_s"]
            if row.get("sprint_split_sum_s") is not None
            else None
        )
        status, flags, quarantined = _qualify(record)
        row["quality_state"] = status
        row["quality_flags"] = flags
        row["quarantined_fields"] = quarantined
        row["source_artifact_id"] = "SA-MENDELEY-DATA-XLSX"
        row["instrument_id"] = "INST-REAL-HAWKIN-DUAL"
        row["protocol_id"] = "PROT-REAL-CMJ-FP"
        mapped.append(row)

    frame = pl.DataFrame(mapped, infer_schema_length=None)

    subjects = (
        frame.sort(["subject_id", "occasion", "phase"])
        .group_by("subject_id", maintain_order=True)
        .agg(
            pl.col("age_years").first().alias("age"),
            pl.col("height_cm").first().alias("height_cm"),
            pl.col("body_mass_kg").first().alias("body_mass_kg"),
        )
        .with_columns(
            pl.col("subject_id").str.replace("MEN-", "P").alias("display_id"),
            pl.lit("Sprint athlete").alias("position"),
            pl.lit(0).alias("training_age_years"),
            pl.lit("INTERVENTION").alias("intervention_arm"),
            pl.lit("ACTIVE").alias("status"),
            pl.lit("Single-arm repeated-measures cohort; no concurrent control arm is identifiable.").alias("design_note"),
        )
        .sort("subject_id")
    )

    cmj = (
        frame.filter((pl.col("phase") == "POST") & (pl.col("cmj_height_cm").is_not_null()))
        .select(
            "subject_id",
            "session_id",
            "trial_id",
            "occasion",
            "body_mass_kg",
            "body_weight_n",
            "height_cm",
            "age_years",
            "cmj_height_m",
            "cmj_height_cm",
            "cmj_flight_time_s",
            "cmj_concentric_mean_force_n",
            "cmj_concentric_phase_duration_s",
            "cmj_mean_braking_force_n",
            "cmj_braking_phase_duration_s",
            "cmj_countermovement_displacement_m",
            "rsi_modified_m_s",
            "isometric_net_peak_force_n",
            "isometric_peak_force_n",
            "isometric_relative_peak_force_n_kg",
            "back_squat_1rm_kg",
            "back_squat_relative_kg_kg",
            "quality_state",
            "quality_flags",
            "quarantined_fields",
            "source_row",
            "source_artifact_id",
            "instrument_id",
            "protocol_id",
        )
        .sort(["subject_id", "occasion"])
    )

    sprint = frame.select(
        "subject_id",
        "session_id",
        "trial_id",
        "occasion",
        "phase",
        "sprint_20m_s",
        "sprint_0_10m_s",
        "sprint_10_20m_s",
        "sprint_split_sum_s",
        "sprint_split_residual_s",
        "body_mass_kg",
        "quality_state",
        "quality_flags",
        "source_row",
        "source_artifact_id",
        "instrument_id",
        "protocol_id",
    ).sort(["subject_id", "occasion", "phase"])

    long = frame.select(
        "subject_id",
        "session_id",
        "trial_id",
        "occasion",
        "phase",
        "age_years",
        "height_cm",
        "body_mass_kg",
        "sprint_20m_s",
        "sprint_0_10m_s",
        "sprint_10_20m_s",
        "cmj_height_m",
        "cmj_height_cm",
        "isometric_net_peak_force_n",
        "isometric_peak_force_n",
        "isometric_relative_peak_force_n_kg",
        "isometric_force_a_n",
        "isometric_force_b_n",
        "isometric_force_c_n",
        "cmj_concentric_mean_force_n",
        "cmj_concentric_phase_duration_s",
        "cmj_mean_braking_force_n",
        "cmj_braking_phase_duration_s",
        "cmj_countermovement_displacement_m",
        "rsi_modified_m_s",
        "back_squat_1rm_kg",
        "back_squat_relative_kg_kg",
        "quality_state",
        "quality_flags",
        "quarantined_fields",
        "source_row",
        "source_artifact_id",
        "instrument_id",
        "protocol_id",
    ).sort(["subject_id", "occasion", "phase"])

    return {
        "subjects": subjects,
        "measurements_long": long,
        "cmj_occasions": cmj,
        "sprint_trials": sprint,
    }


def assess(tables: dict[str, pl.DataFrame], source_path: Path) -> dict[str, Any]:
    long = tables["measurements_long"]
    cmj = tables["cmj_occasions"]
    sprint = tables["sprint_trials"]
    errors: list[str] = []
    warnings: list[str] = []
    quarantined_fields: list[str] = []
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, detail: str, severity: str = "ERROR") -> None:
        checks.append({"check": name, "status": "PASS" if passed else "FAIL", "detail": detail, "severity": severity})
        if not passed:
            (errors if severity == "ERROR" else warnings).append(f"{name}: {detail}")

    check("row_count", long.height == 168, f"{long.height} rows (expected 168)")
    check("subject_count", long["subject_id"].n_unique() == 21, f"{long['subject_id'].n_unique()} subjects (expected 21)")
    check("occasion_structure", long.group_by(["subject_id", "occasion"]).len()["len"].unique().to_list() == [2], "each subject has two phases per occasion")
    check("occasion_count", sorted(long["occasion"].unique().to_list()) == [1, 2, 3, 4], "occasions 1-4")
    check("body_mass", bool(long["body_mass_kg"].min() >= 40 and long["body_mass_kg"].max() <= 150), f"{long['body_mass_kg'].min():.1f}-{long['body_mass_kg'].max():.1f} kg")
    check("cmj_range", bool(cmj["cmj_height_cm"].min() >= 15 and cmj["cmj_height_cm"].max() <= 90), f"{cmj['cmj_height_cm'].min():.1f}-{cmj['cmj_height_cm'].max():.1f} cm")
    max_residual = float(sprint["sprint_split_residual_s"].abs().max() or 0.0)
    check("sprint_split_consistency", max_residual < 1e-9, f"max |20m - (0-10m + 10-20m)| = {max_residual:.2e} s")
    check("sprint_time_range", bool(sprint["sprint_20m_s"].min() >= 2.5 and sprint["sprint_20m_s"].max() <= 4.0), f"{sprint['sprint_20m_s'].min():.2f}-{sprint['sprint_20m_s'].max():.2f} s")
    missing_cmj = cmj.height
    check("cmj_completeness", missing_cmj == 82, f"{missing_cmj} post-occasion CMJ rows (84 expected; 2 not deposited)", "WARNING")
    bsrel_flags = cmj.filter(pl.col("quality_flags").list.contains("BSREL_INCONSISTENT_WITH_BS_OVER_WT"))
    check("bsrel_consistency", bsrel_flags.height == 0, f"{bsrel_flags.height} rows have BSrel inconsistent with BS/wt beyond 0.05", "WARNING")
    for row in bsrel_flags.iter_rows(named=True):
        quarantined_fields.extend([f"{row['trial_id']}:back_squat_relative_kg_kg"])
    iso_flags = cmj.filter(pl.col("quality_flags").list.contains("ISO_RELATIVE_REFERENCE_MASS_UNDOCUMENTED"))
    check("iso_relative_reproducibility", iso_flags.height == 0, f"{iso_flags.height} rows have a relative isometric value not reproducible from deposited mass and peak force", "WARNING")
    check("raw_force_traces", False, "No force-time traces are deposited; only derived scalars", "WARNING")

    status = "REJECTED" if errors else ("ADMITTED_WITH_WARNINGS" if warnings else "ADMITTED")
    return {
        "status": status,
        "errors": errors,
        "warnings": warnings,
        "checks": checks,
        "counts": {
            "rows": long.height,
            "subjects": int(long["subject_id"].n_unique()),
            "occasions": int(long["occasion"].n_unique()),
            "cmj_observations": int(cmj.height),
            "sprint_observations": int(sprint.height),
        },
        "quarantined_fields": sorted(set(quarantined_fields)),
        "source_path": str(source_path),
        "source_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        "source_size_bytes": source_path.stat().st_size,
    }


def metric_definitions() -> list[dict[str, Any]]:
    return METRIC_DEFINITIONS


def write_snapshot(tables: dict[str, pl.DataFrame], assessment: dict[str, Any]) -> dict[str, Any]:
    from .realstore import register_snapshot

    digest = hashlib.sha256(
        "|".join(
            f"{name}:{_frame_sha256(tables[name])}"
            for name in sorted(tables)
        ).encode()
    ).hexdigest()[:12].upper()
    snapshot_id = f"DS-REAL-MENDELEY-{digest}"
    row_counts = {name: frame.height for name, frame in tables.items()}
    return register_snapshot(
        snapshot_id=snapshot_id,
        source_id=MENDELEY_SOURCE["id"],
        label="Holmberg sprint priming — four repeated testing occasions",
        tables=tables,
        row_counts=row_counts,
        parser_version=PARSER_VERSION,
        schema_version=SCHEMA_VERSION,
        assessment=assessment,
        metric_definitions=metric_definitions(),
        extra={
            "native_format": "XLSX",
            "native_units_preserved": True,
            "table_roles": {
                "subjects": "One row per athlete; stable traits only.",
                "measurements_long": "168 athlete-occasion-phase rows with all native fields.",
                "cmj_occasions": "Analysis-ready post-occasion CMJ/strength rows (82).",
                "sprint_trials": "168 sprint rows including the pre/post priming phases.",
            },
            "occasion_semantics": (
                "COND 1-4 are four repeated testing occasions. The deposit does not map "
                "them to study weeks, so analyses use occasion (1-4), not invented weeks."
            ),
            "design": "single-arm repeated measures",
        },
    )
