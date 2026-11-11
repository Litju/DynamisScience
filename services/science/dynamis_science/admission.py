from __future__ import annotations

import hashlib
import io
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import polars as pl

from .contracts import utc_now
from .data_root import paths


def _artifact_path(name: str) -> Path:
    return paths()["artifacts"] / name


def _admitted_dir() -> Path:
    return paths()["admitted"]

PARSER_VERSION = "dynamis-admission@0.1.0"
SCHEMA_VERSION = "dynamis-science.admission.schema@1.0.0"

CMJ_REQUIRED_COLUMNS = {
    "subject_id",
    "session_id",
    "trial_id",
    "instrument_id",
    "protocol_id",
    "sampling_hz",
}
CMJ_METRIC_COLUMNS = {
    "body_mass_kg",
    "jump_height_cm",
    "concentric_impulse_n_s_kg",
    "eccentric_braking_impulse_n_s_kg",
    "eccentric_braking_duration_s",
    "countermovement_depth_cm",
    "peak_force_n",
    "peak_power_w_kg",
    "rsi_mod",
}
SPRINT_REQUIRED_COLUMNS = {
    "subject_id",
    "session_id",
    "trial_id",
    "instrument_id",
    "protocol_id",
    "distance_m",
    "time_s",
}
CMJ_RANGES = {
    "body_mass_kg": (30.0, 200.0),
    "jump_height_cm": (0.0, 120.0),
    "concentric_impulse_n_s_kg": (0.0, 8.0),
    "eccentric_braking_impulse_n_s_kg": (0.0, 8.0),
    "eccentric_braking_duration_s": (0.0, 2.0),
    "countermovement_depth_cm": (0.0, 80.0),
    "peak_force_n": (0.0, 10000.0),
    "peak_power_w_kg": (0.0, 100.0),
    "rsi_mod": (0.0, 200.0),
}
SPRINT_RANGES = {
    "distance_m": (1.0, 100.0),
    "time_s": (0.3, 30.0),
}


def _json(path: Path, default: Any) -> Any:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temporary, path)


def _safe_column_values(artifact: dict[str, Any], column: str) -> list[str]:
    try:
        frame = _read_frame(artifact)
    except Exception:
        return []
    if column not in frame.columns:
        return []
    return sorted(set(str(v) for v in frame[column].to_list()))
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_list(path: Path) -> list[dict[str, Any]]:
    value = _json(path, [])
    return value if isinstance(value, list) else []


def _save_list(path: Path, value: list[dict[str, Any]]) -> None:
    _write_json(path, value)


def register_source(payload: dict[str, Any]) -> dict[str, Any]:
    required = ["id", "name", "publisher", "dataset_identity", "version", "acquisition_method", "license_or_agreement", "redistribution_restrictions"]
    missing = [field for field in required if not str(payload.get(field, "")).strip()]
    if missing:
        raise ValueError(f"Missing source fields: {', '.join(missing)}")
    source_id = payload.get("id")
    if not isinstance(source_id, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", source_id
    ):
        raise ValueError("Source id must contain only letters, numbers, dot, underscore or hyphen")
    sources = _load_list(_artifact_path("admission_sources.json"))
    if any(item.get("id") == source_id for item in sources):
        raise ValueError(f"Source already registered: {source_id}")
    source = {
        "id": source_id,
        "name": payload["name"],
        "publisher": payload["publisher"],
        "dataset_identity": payload["dataset_identity"],
        "version": payload["version"],
        "acquisition_method": payload["acquisition_method"],
        "license_or_agreement": payload["license_or_agreement"],
        "permitted_uses": payload.get("permitted_uses", []),
        "redistribution_restrictions": payload["redistribution_restrictions"],
        "privacy_status": payload.get("privacy_status", "NOT_APPLICABLE"),
        "retention_limitations": payload.get("retention_limitations", ""),
        "derived_data_publishable": bool(payload.get("derived_data_publishable", False)),
        "rights_status": payload.get("rights_status", "UNVERIFIED"),
        "rights_verified_at": payload.get("rights_verified_at"),
        "rights_verified_by": payload.get("rights_verified_by"),
        "notes": payload.get("notes", ""),
    }
    sources.append(source)
    _save_list(_artifact_path("admission_sources.json"), sources)
    return source


def list_sources() -> list[dict[str, Any]]:
    return _load_list(_artifact_path("admission_sources.json"))


def get_source(source_id: str) -> dict[str, Any] | None:
    return next((item for item in _load_list(_artifact_path("admission_sources.json")) if item.get("id") == source_id), None)


def verify_rights(source_id: str, verifier: str = "system") -> dict[str, Any]:
    source = get_source(source_id)
    if source is None:
        raise ValueError(f"Unknown source: {source_id}")
    required = ["license_or_agreement", "redistribution_restrictions", "permitted_uses"]
    problems = []
    if not str(source.get("license_or_agreement", "")).strip():
        problems.append("missing license or agreement")
    if not str(source.get("redistribution_restrictions", "")).strip():
        problems.append("missing redistribution restrictions")
    if not source.get("permitted_uses"):
        problems.append("missing permitted uses")
    if source.get("rights_status") == "BLOCKED":
        problems.append("source is blocked")
    status = "VERIFIED" if not problems else "UNVERIFIED"
    if not problems and source.get("rights_status") == "FIXTURE_ONLY":
        status = "FIXTURE_ONLY"
    source["rights_status"] = status if status != "VERIFIED" else ("VERIFIED" if not problems else "UNVERIFIED")
    if source["rights_status"] in {"VERIFIED", "FIXTURE_ONLY"}:
        source["rights_verified_at"] = _now()
        source["rights_verified_by"] = verifier
    sources = [item if item.get("id") != source_id else source for item in _load_list(_artifact_path("admission_sources.json"))]
    _save_list(_artifact_path("admission_sources.json"), sources)
    return {"source_id": source_id, "rights_status": source["rights_status"], "problems": problems, "verified_at": source.get("rights_verified_at")}


def register_instrument(payload: dict[str, Any]) -> dict[str, Any]:
    required = ["id", "measurement_family", "manufacturer", "model", "serial_number"]
    missing = [field for field in required if not str(payload.get(field, "")).strip()]
    if missing:
        raise ValueError(f"Missing instrument fields: {', '.join(missing)}")
    instruments = _load_list(_artifact_path("admission_instruments.json"))
    if any(item.get("id") == payload["id"] for item in instruments):
        raise ValueError(f"Instrument already registered: {payload['id']}")
    instrument = {
        "id": payload["id"],
        "measurement_family": payload["measurement_family"],
        "manufacturer": payload["manufacturer"],
        "model": payload["model"],
        "serial_number": payload["serial_number"],
        "calibration_status": payload.get("calibration_status", "UNKNOWN"),
        "calibration_date": payload.get("calibration_date"),
        "sampling_capabilities_hz": payload.get("sampling_capabilities_hz", []),
        "supported_units": payload.get("supported_units", {}),
        "notes": payload.get("notes", ""),
    }
    instruments.append(instrument)
    _save_list(_artifact_path("admission_instruments.json"), instruments)
    return instrument


def list_instruments() -> list[dict[str, Any]]:
    return _load_list(_artifact_path("admission_instruments.json"))


def get_instrument(instrument_id: str) -> dict[str, Any] | None:
    return next((item for item in _load_list(_artifact_path("admission_instruments.json")) if item.get("id") == instrument_id), None)


def register_protocol(payload: dict[str, Any]) -> dict[str, Any]:
    required = ["id", "measurement_family", "name", "version", "sampling_hz"]
    missing = [field for field in required if payload.get(field) in (None, "")]
    if missing:
        raise ValueError(f"Missing protocol fields: {', '.join(missing)}")
    protocols = _load_list(_artifact_path("admission_protocols.json"))
    if any(item.get("id") == payload["id"] for item in protocols):
        raise ValueError(f"Protocol already registered: {payload['id']}")
    protocol = {
        "id": payload["id"],
        "measurement_family": payload["measurement_family"],
        "name": payload["name"],
        "version": payload["version"],
        "sampling_hz": float(payload["sampling_hz"]),
        "units": payload.get("units", {}),
        "coordinate_convention": payload.get("coordinate_convention", "NOT_SPECIFIED"),
        "processing_method": payload.get("processing_method", "NOT_SPECIFIED"),
        "body_mass_required": bool(payload.get("body_mass_required", True)),
        "known_limitations": payload.get("known_limitations", []),
    }
    protocols.append(protocol)
    _save_list(_artifact_path("admission_protocols.json"), protocols)
    return protocol


def list_protocols() -> list[dict[str, Any]]:
    return _load_list(_artifact_path("admission_protocols.json"))


def get_protocol(protocol_id: str) -> dict[str, Any] | None:
    return next((item for item in _load_list(_artifact_path("admission_protocols.json")) if item.get("id") == protocol_id), None)


def ingest_source_artifact(source_id: str, original_filename: str, content: bytes, acquisition_method: str = "upload") -> dict[str, Any]:
    return _ingest_source_stream(
        source_id, original_filename, io.BytesIO(content), acquisition_method
    )


def ingest_source_file(
    source_id: str, file_path: str | os.PathLike[str], acquisition_method: str = "local_file"
) -> dict[str, Any]:
    path = Path(file_path).expanduser().resolve(strict=True)
    if not path.is_file():
        raise ValueError("Source artifact must be a regular file")
    with path.open("rb") as content:
        return _ingest_source_stream(source_id, path.name, content, acquisition_method)


def _ingest_source_stream(source_id: str, original_filename: str, content, acquisition_method: str) -> dict[str, Any]:
    source = get_source(source_id)
    if source is None:
        raise ValueError(f"Unknown source: {source_id}")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", source_id):
        raise ValueError("Invalid source id")
    source_dir = _admitted_dir() / source_id
    source_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(original_filename).suffix.lower() or ".bin"
    temporary_path = source_dir / f".{uuid.uuid4().hex}.upload"
    content_hash = hashlib.sha256()
    artifact_hash = hashlib.sha256()
    size_bytes = 0
    try:
        with temporary_path.open("wb") as stored:
            while chunk := content.read(1024 * 1024):
                stored.write(chunk)
                content_hash.update(chunk)
                artifact_hash.update(chunk)
                size_bytes += len(chunk)
        artifact_hash.update(original_filename.encode())
        artifact_id = "SA-" + artifact_hash.hexdigest()[:12].upper()
        stored_path = source_dir / f"{artifact_id}{suffix}"
        os.replace(temporary_path, stored_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    fmt = "CSV" if suffix == ".csv" else "PARQUET" if suffix in {".parquet", ".pq"} else "JSON" if suffix == ".json" else "OTHER"
    artifact = {
        "id": artifact_id,
        "source_id": source_id,
        "format": fmt,
        "original_filename": original_filename,
        "stored_path": str(stored_path),
        "content_hash_sha256": content_hash.hexdigest(),
        "size_bytes": size_bytes,
        "acquired_at": _now(),
        "acquisition_method": acquisition_method,
        "rights_record_id": source_id,
    }
    artifacts = _load_list(_artifact_path("admission_source_artifacts.json"))
    if not any(item.get("id") == artifact_id for item in artifacts):
        artifacts.append(artifact)
        _save_list(_artifact_path("admission_source_artifacts.json"), artifacts)
    return artifact


def list_source_artifacts() -> list[dict[str, Any]]:
    return _load_list(_artifact_path("admission_source_artifacts.json"))


def get_source_artifact(artifact_id: str) -> dict[str, Any] | None:
    return next((item for item in _load_list(_artifact_path("admission_source_artifacts.json")) if item.get("id") == artifact_id), None)


def _read_frame(artifact: dict[str, Any]) -> pl.DataFrame:
    path = Path(artifact["stored_path"])
    if artifact["format"] == "CSV":
        return pl.read_csv(path)
    if artifact["format"] == "PARQUET":
        return pl.read_parquet(path)
    raise ValueError(f"Unsupported artifact format: {artifact['format']}")


def _unit_conversion(value: float, unit: str, canonical: str, quantity: str) -> float:
    unit = unit.strip().lower()
    canonical = canonical.strip().lower()
    if unit == canonical:
        return value
    conversions = {
        ("g", "kg"): 0.001,
        ("kg", "kg"): 1.0,
        ("ms", "s"): 0.001,
        ("s", "s"): 1.0,
        ("min", "s"): 60.0,
        ("cm", "m"): 0.01,
        ("m", "m"): 1.0,
        ("n", "n"): 1.0,
    }
    key = (unit, canonical)
    if key in conversions:
        return value * conversions[key]
    raise ValueError(f"Cannot convert {quantity} from {unit} to {canonical}")


def validate_cmj(artifact: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    rejected: list[str] = []
    quarantined: list[str] = []
    counts: dict[str, int] = {}
    try:
        frame = _read_frame(artifact)
    except Exception as exc:  # pragma: no cover - corrupt file path
        errors.append(f"corrupt or unreadable file: {type(exc).__name__}")
        return _quality_result(artifact, "CMJ_FORCE_PLATFORM", metadata, "REJECTED", errors, warnings, rejected, quarantined, counts)

    columns = set(frame.columns)
    missing_required = sorted(CMJ_REQUIRED_COLUMNS - columns)
    if missing_required:
        errors.append(f"missing required columns: {', '.join(missing_required)}")
    if errors:
        return _quality_result(artifact, "CMJ_FORCE_PLATFORM", metadata, "REJECTED", errors, warnings, rejected, quarantined, {"rows": frame.height})

    # Units
    units = metadata.get("units", {})
    mass_unit = str(units.get("body_mass", units.get("mass", "kg"))).lower()
    if mass_unit not in {"kg", "g"}:
        errors.append(f"unrecognized mass unit: {mass_unit}")
    if "mass_unit" not in metadata and "units" not in metadata:
        warnings.append("missing unit metadata; assuming canonical units")
    # We quarantine missing units rather than reject if not explicitly provided.
    if "units" not in metadata:
        warnings.append("unit metadata not provided; scientific interpretation is limited")
    # timestamps / week
    if "timestamp" in columns:
        try:
            pl.Series(frame["timestamp"]).str.to_datetime(strict=False)
        except Exception:
            pass
    if "week" in columns:
        bad_weeks = [int(v) for v in frame["week"].to_list() if v is None or int(v) < 1 or int(v) > 52]
        if bad_weeks:
            errors.append("invalid week values")
    # sampling
    sampling_values = frame["sampling_hz"].unique().to_list() if "sampling_hz" in columns else []
    if "sampling_hz" not in columns:
        errors.append("missing sampling_hz column")
    else:
        if any(v is None or float(v) <= 0 for v in sampling_values):
            errors.append("invalid sampling frequency")
        if len(sampling_values) > 1:
            warnings.append("inconsistent sampling frequency across rows")
    # duplicates
    if "trial_id" in columns:
        dupes = frame.group_by("trial_id").len().filter(pl.col("len") > 1)
        if dupes.height:
            errors.append(f"duplicate trial ids: {dupes['trial_id'].to_list()[:10]}")
            rejected.extend(dupes["trial_id"].to_list())
    # subject/session
    if frame["subject_id"].null_count() or frame["session_id"].null_count():
        errors.append("missing subject or session identifiers")
    # instrument metadata
    instrument_ids = sorted(set(str(v) for v in frame["instrument_id"].to_list()))
    unknown_instruments = [iid for iid in instrument_ids if get_instrument(iid) is None]
    if unknown_instruments:
        warnings.append(f"unrecognized instrument metadata: {unknown_instruments}")
        quarantined.extend(unknown_instruments)
    # protocol
    protocol_ids = sorted(set(str(v) for v in frame["protocol_id"].to_list()))
    unknown_protocols = [pid for pid in protocol_ids if get_protocol(pid) is None]
    if unknown_protocols:
        warnings.append(f"unrecognized protocol: {unknown_protocols}")
    # calibration
    for iid in instrument_ids:
        inst = get_instrument(iid)
        if inst is not None and inst.get("calibration_status") != "CALIBRATED":
            warnings.append(f"instrument {iid} calibration is {inst.get('calibration_status')}")
    # implausible values
    for column, (low, high) in CMJ_RANGES.items():
        if column in columns:
            bad = frame.filter((pl.col(column) < low) | (pl.col(column) > high))
            if bad.height:
                warnings.append(f"implausible {column} in {bad.height} records")
                quarantined.extend(bad["trial_id"].to_list() if "trial_id" in columns else [])
    # missing samples
    metric_present = [c for c in CMJ_METRIC_COLUMNS if c in columns]
    if not metric_present:
        warnings.append("no CMJ metric columns present")
    missing_metric_rows = 0
    for col in metric_present:
        missing_metric_rows += int(frame[col].null_count())
    if missing_metric_rows:
        warnings.append(f"{missing_metric_rows} missing metric values")
    # timestamps monotonic if force trace style time column
    if "time_s" in columns and "trial_id" in columns:
        for trial_id, group in frame.group_by("trial_id"):
            times = group.sort("time_s")["time_s"].to_list()
            if any(times[i] > times[i + 1] for i in range(len(times) - 1)):
                warnings.append(f"nonmonotonic sample timestamps in {trial_id}")
                quarantined.append(str(trial_id))
    # coordinate conventions not applicable

    status = "ADMITTED"
    if errors:
        status = "REJECTED"
    elif quarantined or any("unrecognized" in w or "calibration" in w or "implausible" in w for w in warnings):
        status = "QUARANTINED"
    elif warnings:
        status = "ADMITTED_WITH_WARNINGS"
    counts = {"rows": frame.height, "subjects": int(frame["subject_id"].n_unique()), "trials": int(frame["trial_id"].n_unique())}
    return _quality_result(artifact, "CMJ_FORCE_PLATFORM", metadata, status, errors, warnings, rejected, quarantined, counts)


def validate_sprint(artifact: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    rejected: list[str] = []
    quarantined: list[str] = []
    try:
        frame = _read_frame(artifact)
    except Exception as exc:
        errors.append(f"corrupt or unreadable file: {type(exc).__name__}")
        return _quality_result(artifact, "SPRINT_TIMING", metadata, "REJECTED", errors, warnings, rejected, quarantined, {})
    columns = set(frame.columns)
    missing_required = sorted(SPRINT_REQUIRED_COLUMNS - columns)
    if missing_required:
        errors.append(f"missing required columns: {', '.join(missing_required)}")
    if errors:
        return _quality_result(artifact, "SPRINT_TIMING", metadata, "REJECTED", errors, warnings, rejected, quarantined, {"rows": frame.height})
    if frame["subject_id"].null_count() or frame["session_id"].null_count():
        errors.append("missing subject or session identifiers")
    if "sampling_hz" in columns:
        if any(v is None or float(v) <= 0 for v in frame["sampling_hz"].unique().to_list()):
            errors.append("invalid sampling frequency")
    if "trial_id" in columns:
        dupes = frame.group_by("trial_id").len().filter(pl.col("len") > 1)
        if dupes.height:
            errors.append(f"duplicate trial ids: {dupes['trial_id'].to_list()[:10]}")
            rejected.extend(dupes["trial_id"].to_list())
    instrument_ids = sorted(set(str(v) for v in frame["instrument_id"].to_list()))
    unknown_instruments = [iid for iid in instrument_ids if get_instrument(iid) is None]
    if unknown_instruments:
        warnings.append(f"unrecognized instrument metadata: {unknown_instruments}")
    protocol_ids = sorted(set(str(v) for v in frame["protocol_id"].to_list()))
    unknown_protocols = [pid for pid in protocol_ids if get_protocol(pid) is None]
    if unknown_protocols:
        warnings.append(f"unrecognized protocol: {unknown_protocols}")
    for iid in instrument_ids:
        inst = get_instrument(iid)
        if inst is not None and inst.get("calibration_status") != "CALIBRATED":
            warnings.append(f"instrument {iid} calibration is {inst.get('calibration_status')}")
    for column, (low, high) in SPRINT_RANGES.items():
        if column in columns:
            bad = frame.filter((pl.col(column) < low) | (pl.col(column) > high))
            if bad.height:
                warnings.append(f"implausible {column} in {bad.height} records")
                quarantined.extend(bad["trial_id"].to_list() if "trial_id" in columns else [])
    units = metadata.get("units", {})
    if "units" not in metadata:
        warnings.append("unit metadata not provided; scientific interpretation is limited")
    if "coordinate_system" not in metadata:
        warnings.append("uncertain coordinate conventions: coordinate_system not specified")
        quarantined.append("coordinate_convention")
    status = "ADMITTED"
    if errors:
        status = "REJECTED"
    elif quarantined or any("unrecognized" in w or "calibration" in w or "implausible" in w or "coordinate" in w for w in warnings):
        status = "QUARANTINED"
    elif warnings:
        status = "ADMITTED_WITH_WARNINGS"
    counts = {"rows": frame.height, "subjects": int(frame["subject_id"].n_unique()), "trials": int(frame["trial_id"].n_unique())}
    return _quality_result(artifact, "SPRINT_TIMING", metadata, status, errors, warnings, rejected, quarantined, counts)


def _quality_result(artifact, family, metadata, status, errors, warnings, rejected, quarantined, counts):
    assessment = {
        "source_artifact_id": artifact["id"],
        "measurement_family": family,
        "metadata": metadata,
        "status": status,
        "errors": errors,
        "warnings": warnings,
        "rejected_record_ids": sorted(set(rejected)),
        "quarantined_record_ids": sorted(set(quarantined)),
        "counts": counts,
    }
    digest = hashlib.sha256(json.dumps(assessment, sort_keys=True).encode()).hexdigest()[:12].upper()
    assessment["id"] = "QA-" + digest
    records = _load_list(_artifact_path("admission_quality.json"))
    existing = next((r for r in records if r.get("id") == assessment["id"]), None)
    if existing:
        return existing
    assessment["checked_at"] = _now()
    records.append(assessment)
    _save_list(_artifact_path("admission_quality.json"), records)
    return assessment


def get_quality(assessment_id: str) -> dict[str, Any] | None:
    return next((r for r in _load_list(_artifact_path("admission_quality.json")) if r.get("id") == assessment_id), None)


def harmonize_cmj(artifact: dict[str, Any], metadata: dict[str, Any]) -> pl.DataFrame:
    frame = _read_frame(artifact)
    units = metadata.get("units", {})
    mass_unit = str(units.get("body_mass", units.get("mass", "kg"))).lower() or "kg"
    # Convert mass if needed
    if "body_mass_kg" in frame.columns and mass_unit != "kg":
        frame = frame.with_columns((pl.col("body_mass_kg") * _unit_conversion(1.0, mass_unit, "kg", "mass")).alias("body_mass_kg"))
    # time unit conversion for duration columns
    time_unit = str(units.get("time", "s")).lower() or "s"
    for col in ("eccentric_braking_duration_s",):
        if col in frame.columns and time_unit != "s":
            frame = frame.with_columns((pl.col(col) * _unit_conversion(1.0, time_unit, "s", "time")).alias(col))
    # distance unit conversion for jump height? keep cm canonical for metric
    # Add canonical provenance columns
    frame = frame.with_columns(
        pl.lit(artifact["id"]).alias("source_artifact_id"),
        pl.lit(metadata.get("instrument_default", "")).alias("_instrument_default"),
    )
    return frame


def harmonize_sprint(artifact: dict[str, Any], metadata: dict[str, Any]) -> pl.DataFrame:
    frame = _read_frame(artifact)
    units = metadata.get("units", {})
    distance_unit = str(units.get("distance", "m")).lower() or "m"
    time_unit = str(units.get("time", "s")).lower() or "s"
    if "distance_m" in frame.columns and distance_unit != "m":
        frame = frame.with_columns((pl.col("distance_m") * _unit_conversion(1.0, distance_unit, "m", "distance")).alias("distance_m"))
    if "time_s" in frame.columns and time_unit != "s":
        frame = frame.with_columns((pl.col("time_s") * _unit_conversion(1.0, time_unit, "s", "time")).alias("time_s"))
    frame = frame.with_columns(pl.lit(artifact["id"]).alias("source_artifact_id"))
    return frame


def _snapshot_id(artifact: dict[str, Any], family: str) -> str:
    return "DS-ADMITTED-" + hashlib.sha256(f"{artifact['id']}:{family}".encode()).hexdigest()[:12].upper()


def admit_artifact(artifact_id: str, family: str, metadata: dict[str, Any]) -> dict[str, Any]:
    artifact = get_source_artifact(artifact_id)
    if artifact is None:
        raise ValueError(f"Unknown source artifact: {artifact_id}")
    source = get_source(artifact["source_id"])
    if source is None:
        raise ValueError(f"Unknown source: {artifact['source_id']}")
    existing_id = _snapshot_id(artifact, family)
    existing_dir = _admitted_dir() / existing_id
    if existing_dir.exists():
        snapshot = _json(existing_dir / "snapshot.json", {})
        record = next((r for r in list_admission_records() if r.get("dataset_snapshot_id") == existing_id), None)
        if (snapshot.get("admission_metadata") == metadata and record
                and record.get("rights_status") == source.get("rights_status")):
            return record
        raise ValueError("This artifact already has an immutable snapshot with different or unrecorded metadata. Register a new source for a new admission.")
    # rights gate
    rights_status = source.get("rights_status", "UNVERIFIED")
    if rights_status not in {"VERIFIED", "FIXTURE_ONLY"}:
        record = {
            "id": "AR-" + hashlib.sha256(f"{artifact_id}:{family}".encode()).hexdigest()[:12].upper(),
            "source_id": artifact["source_id"],
            "source_artifact_id": artifact_id,
            "measurement_family": family,
            "status": "REJECTED",
            "rights_status": rights_status,
            "quality_assessment_id": "",
            "dataset_snapshot_id": None,
            "parser_version": PARSER_VERSION,
            "normalization_rules": [],
            "qc_operations": ["rights_verification"],
            "exclusion_criteria": ["rights not verified"],
            "instrument_ids": [],
            "protocol_ids": [],
            "metric_definition_ids": [],
            "algorithm_versions": {},
            "schema_version": SCHEMA_VERSION,
            "admitted_at": _now(),
            "provenance_manifest_id": None,
            "blocked_reason": "source rights are not verified",
        }
        records = _load_list(_artifact_path("admission_records.json"))
        records = [r for r in records if r.get("source_artifact_id") != artifact_id or r.get("measurement_family") != family]
        records.append(record)
        _save_list(_artifact_path("admission_records.json"), records)
        return record

    if family == "CMJ_FORCE_PLATFORM":
        assessment = validate_cmj(artifact, metadata)
        family_name = "CMJ_FORCE_PLATFORM"
    elif family == "SPRINT_TIMING":
        assessment = validate_sprint(artifact, metadata)
        family_name = "SPRINT_TIMING"
    else:
        raise ValueError(f"Unsupported measurement family: {family}")

    status = assessment["status"]
    # harmonize and snapshot only if admitted or admitted with warnings
    snapshot_id = None
    manifest_id = None
    normalization_rules: list[str] = []
    qc_operations = ["schema_validation", "unit_check", "duplicate_check", "range_check", "instrument_check", "protocol_check"]
    if status in {"ADMITTED", "ADMITTED_WITH_WARNINGS"}:
        if family == "CMJ_FORCE_PLATFORM":
            frame = harmonize_cmj(artifact, metadata)
            table_name = "cmj_trials"
        else:
            frame = harmonize_sprint(artifact, metadata)
            table_name = "sprint_trials"
        snapshot_id = _snapshot_id(artifact, family)
        snapshot_dir = _admitted_dir() / snapshot_id
        snapshot_dir.mkdir(parents=True, exist_ok=False)
        out_path = snapshot_dir / f"{table_name}.parquet"
        frame.write_parquet(out_path, compression="zstd")
        normalization_rules = ["canonical mass units", "canonical time units", "canonical distance units", "provenance columns"]
        # manifest
        manifest_id = "PM-" + hashlib.sha256(snapshot_id.encode()).hexdigest()[:12].upper()
        manifest = {
            "id": manifest_id,
            "snapshot_id": snapshot_id,
            "source_artifact_ids": [artifact_id],
            "content_hashes": {f"{table_name}.parquet": hashlib.sha256(out_path.read_bytes()).hexdigest()},
            "data_rights_status": rights_status,
            "parser_version": PARSER_VERSION,
            "normalization_rules": normalization_rules,
            "qc_operations": qc_operations,
            "exclusion_criteria": assessment.get("rejected_record_ids", []) + assessment.get("quarantined_record_ids", []),
            "instrument_metadata": [get_instrument(iid) for iid in sorted(set(str(v) for v in _read_frame(artifact)["instrument_id"].to_list())) if get_instrument(iid)],
            "metric_definitions": [],
            "algorithm_versions": {"admission": PARSER_VERSION},
            "schema_version": SCHEMA_VERSION,
            "created_at": _now(),
        }
        _write_json(snapshot_dir / "provenance_manifest.json", manifest)
        _write_json(snapshot_dir / "snapshot.json", {
            "id": snapshot_id,
            "label": f"Admitted {family} snapshot",
            "source_artifact_id": artifact_id,
            "measurement_family": family,
            "row_count": frame.height,
            "table": table_name,
            "path": str(snapshot_dir),
            "rights_status": rights_status,
            "admission_status": status,
            "admission_metadata": metadata,
        })
    record = {
        "id": "AR-" + hashlib.sha256(f"{artifact_id}:{family}".encode()).hexdigest()[:12].upper(),
        "source_id": artifact["source_id"],
        "source_artifact_id": artifact_id,
        "measurement_family": family_name,
        "status": status,
        "rights_status": rights_status,
        "quality_assessment_id": assessment["id"],
        "dataset_snapshot_id": snapshot_id,
        "parser_version": PARSER_VERSION,
        "normalization_rules": normalization_rules,
        "qc_operations": qc_operations,
        "exclusion_criteria": assessment.get("rejected_record_ids", []) + assessment.get("quarantined_record_ids", []),
        "instrument_ids": _safe_column_values(artifact, "instrument_id"),
        "protocol_ids": _safe_column_values(artifact, "protocol_id"),
        "metric_definition_ids": [],
        "algorithm_versions": {"admission": PARSER_VERSION},
        "schema_version": SCHEMA_VERSION,
        "admitted_at": _now(),
        "provenance_manifest_id": manifest_id,
    }
    records = _load_list(_artifact_path("admission_records.json"))
    records = [r for r in records if r.get("source_artifact_id") != artifact_id or r.get("measurement_family") != family]
    records.append(record)
    _save_list(_artifact_path("admission_records.json"), records)
    return record


def list_admission_records() -> list[dict[str, Any]]:
    return _load_list(_artifact_path("admission_records.json"))


def get_admission_record(record_id: str) -> dict[str, Any] | None:
    return next((r for r in _load_list(_artifact_path("admission_records.json")) if r.get("id") == record_id), None)


def list_admitted_snapshots() -> list[dict[str, Any]]:
    snapshots = []
    admitted_dir = _admitted_dir()
    if admitted_dir.exists():
        for path in admitted_dir.iterdir():
            if path.is_dir():
                snapshot_file = path / "snapshot.json"
                if snapshot_file.exists():
                    snapshot = json.loads(snapshot_file.read_text(encoding="utf-8"))
                    if snapshot.get("id") == path.name:
                        snapshots.append(snapshot)
    return snapshots


def get_admitted_snapshot(snapshot_id: str) -> dict[str, Any] | None:
    snapshot = next(
        (item for item in list_admitted_snapshots() if item.get("id") == snapshot_id),
        None,
    )
    if snapshot is None:
        return None
    if not isinstance(snapshot.get("id"), str) or not re.fullmatch(
        r"DS-ADMITTED-[A-F0-9]{12}", snapshot["id"]
    ):
        return None
    directory = _admitted_dir() / snapshot["id"]
    table = snapshot.get("table", "")
    if table not in {"cmj_trials", "sprint_trials"}:
        return None
    if not (directory / f"{table}.parquet").is_file():
        return None
    artifact = get_source_artifact(snapshot.get("source_artifact_id", ""))
    source = get_source(artifact.get("source_id", "")) if artifact else None
    if source is None:
        return None
    family = snapshot.get("measurement_family", "")
    provenance = _json(directory / "provenance_manifest.json", {})
    admission_record = next(
        (
            item
            for item in list_admission_records()
            if item.get("dataset_snapshot_id") == snapshot_id
        ),
        {},
    )
    license_text = source.get("license_or_agreement", "")
    privacy = {
        "classification": source.get("privacy_status", "NOT_APPLICABLE"),
        "restrictions": source.get("redistribution_restrictions", ""),
        "retention_limitations": source.get("retention_limitations", ""),
    }
    return {
        **snapshot,
        "path": str(directory),
        "real_data": snapshot.get("rights_status") != "FIXTURE_ONLY",
        "synthetic": snapshot.get("rights_status") == "FIXTURE_ONLY",
        "admitted_source": True,
        "tables": {table: {"file": f"{table}.parquet", "rows": snapshot.get("row_count", 0)}},
        "row_counts": {table: snapshot.get("row_count", 0)},
        "checksums": provenance.get("content_hashes", {}),
        "admission": admission_record,
        "provenance": provenance,
        "source": {
            "id": source["id"],
            "name": source["name"],
            "publisher": source["publisher"],
            "doi": None,
            "dataset_identity": source.get("dataset_identity"),
            "version": source.get("version"),
            "license": {"id": license_text, "name": license_text},
            "privacy": privacy,
            "permitted_uses": source.get("permitted_uses", []),
            "redistribution_restrictions": source.get("redistribution_restrictions", ""),
            "attribution": f"{source['publisher']}. {source['dataset_identity']}. {license_text}.",
            "rights_status": source.get("rights_status", "UNVERIFIED"),
        },
    }
