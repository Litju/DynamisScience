"""Adapter for the MoveSmart wearable IMU + force-plate deposit (Zenodo).

The archive contains raw 1000 Hz force-plate signals and ~100 Hz Apple Watch
IMU signals.  It does *not* contain the trial-matching manifest, quality flags
or analysis code advertised in the record description.  Matching is therefore
reconstructed from participant directory, activity and trial number, and the
clock relationship between devices is measured rather than assumed.
"""

from __future__ import annotations

import csv
import hashlib
import io
import math
import re
import statistics
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from .real_sources import ZENODO_SOURCE

PARSER_VERSION = "dynamis-movesmart@1.0.0"
SCHEMA_VERSION = "dynamis-science.real.movesmart@1.0.0"

ACTIVITY_MAP = {
    "walk": "Walking",
    "jog": "Jogging",
    "run": "Running",
    "heel": "Heel drop",
    "drop": "Step drop",
}
IMU_ACTIVITY_MAP = {
    "Walking": "Walking",
    "Jogging": "Jogging",
    "Running": "Running",
    "Heel": "Heel drop",
    "Drop": "Step drop",
}
FORCE_PATTERN = re.compile(r"(walk|jog|run|heel|drop)(\d+)_f_([678])\.csv$")
IMU_PATTERN = re.compile(
    r"(Walking|Jogging|Running|Heel|Drop)_(Waist|Wrist)_Trial_.*_ID_(\d+)_"
)
PARTICIPANT_PATTERN = re.compile(r"^P(\d+)-(\d{4})-([0-9.]+)-([0-9.]+)$")

METRIC_DEFINITIONS = [
    {
        "id": "MET-REAL-FZ-PEAK",
        "canonical_id": "grf.peak_vertical",
        "name": "Peak vertical ground reaction force",
        "quantity": "force",
        "unit": "N",
        "native_column": "Force_Z",
        "native_unit": "N",
        "conversion": "none (sum of available force plates)",
        "method": "Maximum of the summed vertical force from the AMTI Gen 5 plates at 1000 Hz.",
        "protocol_id": "PROT-REAL-OVERGROUND",
        "algorithm": "dynamis peak detector v1.0.0",
        "version": "1.0.0",
        "dependencies": [],
        "known_limitations": [
            "Only available plates are summed; 278 of 398 matched trials do not have all three plates.",
            "The deposit has no documented calibration record or force-plate zeroing log.",
        ],
    },
    {
        "id": "MET-REAL-FZ-IMPULSE",
        "canonical_id": "grf.vertical_impulse",
        "name": "Vertical support impulse",
        "quantity": "impulse",
        "unit": "N s",
        "native_column": "Force_Z",
        "native_unit": "N",
        "conversion": "trapezoidal integration over detected support intervals",
        "method": "Trapezoidal integration of summed vertical force above a 20 N threshold.",
        "protocol_id": "PROT-REAL-OVERGROUND",
        "algorithm": "dynamis support-phase detector v1.0.0",
        "version": "1.0.0",
        "dependencies": ["grf.peak_vertical"],
        "known_limitations": [
            "Threshold-based support detection is sensitive to baseline drift and to unloaded gaps between plates.",
        ],
    },
    {
        "id": "MET-REAL-IMU-ACCEL",
        "canonical_id": "imu.user_acceleration",
        "name": "Apple Watch user acceleration magnitude",
        "quantity": "acceleration",
        "unit": "g",
        "native_column": "userAccelerationX/Y/Z",
        "native_unit": "g",
        "conversion": "sqrt(ax^2 + ay^2 + az^2)",
        "method": "Native Apple Watch user-acceleration channels; gravity is supplied separately.",
        "protocol_id": "PROT-REAL-WATCH",
        "algorithm": "direct vector magnitude",
        "version": "1.0.0",
        "dependencies": [],
        "known_limitations": [
            "The archive does not document the watch model, watchOS version, sampling configuration or calibration.",
            "Sampling intervals are irregular (nominal ~100 Hz), so waveforms are kept with native timestamps.",
        ],
    },
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _frame_sha256(frame: pl.DataFrame) -> str:
    buffer = io.BytesIO()
    frame.write_parquet(buffer)
    return hashlib.sha256(buffer.getvalue()).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _participant_metadata(name: str) -> dict[str, Any]:
    match = PARTICIPANT_PATTERN.match(name)
    if not match:
        return {"participant_id": name, "birth_year": None, "height_cm": None, "body_mass_kg": None}
    return {
        "participant_id": f"MS-{int(match.group(1)):02d}",
        "participant_folder": name,
        "birth_year": int(match.group(2)),
        "height_cm": float(match.group(3)),
        "body_mass_kg": float(match.group(4)),
        "metadata_provenance": "participant directory name; undocumented in the deposit",
    }


def scan(root: Path) -> dict[str, Any]:
    force: dict[tuple[str, str, int], dict[str, Path]] = {}
    imu: dict[tuple[str, str, int], dict[str, Path]] = {}
    all_files = sorted(root.rglob("*.csv"))
    for path in all_files:
        participant = path.parent.name
        force_match = FORCE_PATTERN.match(path.name)
        if force_match:
            key = (participant, ACTIVITY_MAP[force_match.group(1)], int(force_match.group(2)))
            force.setdefault(key, {})[force_match.group(3)] = path
            continue
        imu_match = IMU_PATTERN.match(path.name)
        if imu_match:
            key = (participant, IMU_ACTIVITY_MAP[imu_match.group(1)], int(imu_match.group(3)))
            imu.setdefault(key, {})[imu_match.group(2).lower()] = path
    matched = sorted(set(force) & set(imu))
    return {
        "root": root,
        "force": force,
        "imu": imu,
        "matched": matched,
        "file_count": len(all_files),
        "force_trial_count": len(force),
        "imu_trial_count": len(imu),
        "matched_trial_count": len(matched),
        "three_plate_trials": sum(1 for key in matched if len(force[key]) == 3),
    }


def _read_force(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        lines = handle.readlines()
    header_index = next(
        (index for index, line in enumerate(lines) if line.startswith("SAMPLE,")), None
    )
    if header_index is None:
        raise ValueError(f"No SAMPLE header in {path.name}")
    metadata: dict[str, str] = {}
    for line in lines[:header_index]:
        parts = next(csv.reader([line]))
        if parts and parts[0]:
            metadata[parts[0]] = parts[1] if len(parts) > 1 else ""
    reader = csv.DictReader(lines[header_index:])
    samples: list[int] = []
    times: list[float] = []
    fx: list[float] = []
    fy: list[float] = []
    fz: list[float] = []
    moments: list[float] = []
    nan_count = 0
    for row in reader:
        try:
            sample = int(row["SAMPLE"])
            time_s = float(row["TIME"])
        except (TypeError, ValueError):
            continue
        def value(key: str) -> float:
            nonlocal nan_count
            raw = row.get(key, "")
            if raw in ("", None, "NaN", "nan"):
                nan_count += 1
                return float("nan")
            return float(raw)
        samples.append(sample)
        times.append(time_s)
        fx.append(value("Force_X"))
        fy.append(value("Force_Y"))
        fz.append(value("Force_Z"))
        moments.append(value("Moment_Z"))
    return {
        "metadata": metadata,
        "sample": samples,
        "time_s": times,
        "fx_n": fx,
        "fy_n": fy,
        "fz_n": fz,
        "mz_nm": moments,
        "nan_count": nan_count,
    }


def _read_imu(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    timestamps: list[float] = []
    ax: list[float] = []
    ay: list[float] = []
    az: list[float] = []
    gx: list[float] = []
    gy: list[float] = []
    gz: list[float] = []
    rx: list[float] = []
    ry: list[float] = []
    rz: list[float] = []
    magnitude: list[float] = []
    for row in rows:
        try:
            timestamps.append(float(row["timestamp"]))
            ax.append(float(row["userAccelerationX"]))
            ay.append(float(row["userAccelerationY"]))
            az.append(float(row["userAccelerationZ"]))
            gx.append(float(row["gravityX"]))
            gy.append(float(row["gravityY"]))
            gz.append(float(row["gravityZ"]))
            rx.append(float(row["rotationRateX"]))
            ry.append(float(row["rotationRateY"]))
            rz.append(float(row["rotationRateZ"]))
            magnitude.append(float(row["magnitude"]))
        except (KeyError, TypeError, ValueError):
            continue
    if not timestamps:
        raise ValueError(f"No usable IMU rows in {path.name}")
    first = rows[0]
    return {
        "metadata": {
            "activity": first.get("activity", ""),
            "trial_id_native": first.get("trialID", ""),
            "participant_id_native": first.get("participantID", ""),
            "placement": first.get("placement", ""),
        },
        "timestamp_ms": timestamps,
        "ax_g": ax,
        "ay_g": ay,
        "az_g": az,
        "gx_g": gx,
        "gy_g": gy,
        "gz_g": gz,
        "rx_rad_s": rx,
        "ry_rad_s": ry,
        "rz_rad_s": rz,
        "magnitude_g": magnitude,
    }


def _support_intervals(fz: np.ndarray, sampling_hz: float, threshold_n: float = 20.0) -> list[tuple[float, float]]:
    above = np.abs(fz) > threshold_n
    intervals: list[tuple[float, float]] = []
    start: int | None = None
    for index, value in enumerate(above):
        if value and start is None:
            start = index
        elif not value and start is not None:
            intervals.append((start / sampling_hz, (index - 1) / sampling_hz))
            start = None
    if start is not None:
        intervals.append((start / sampling_hz, (len(fz) - 1) / sampling_hz))
    return intervals


def _trial_summary(key: tuple[str, str, int], force_paths: dict[str, Path], imu_paths: dict[str, Path]) -> dict[str, Any]:
    participant, activity, trial_number = key
    metadata = _participant_metadata(participant)
    plate_signals: dict[str, np.ndarray] = {}
    times: np.ndarray | None = None
    sampling_hz = None
    metadata_by_plate: dict[str, dict[str, str]] = {}
    nan_count = 0
    for plate in sorted(force_paths):
        parsed = _read_force(force_paths[plate])
        metadata_by_plate[plate] = parsed["metadata"]
        plate_signals[plate] = np.asarray(parsed["fz_n"], dtype=float)
        nan_count += parsed["nan_count"]
        if times is None:
            times = np.asarray(parsed["time_s"], dtype=float)
            sampling_hz = float(parsed["metadata"].get("FREQUENCY", "0") or 0)
    assert times is not None
    length = min(len(values) for values in plate_signals.values())
    length = min(length, len(times))
    total = np.zeros(length, dtype=float)
    for values in plate_signals.values():
        total += np.nan_to_num(values[:length], nan=0.0)
    times = times[:length]
    baseline = float(np.median(total[: min(100, length)]))
    threshold = max(20.0, abs(baseline) + 20.0)
    intervals = _support_intervals(total, sampling_hz or 1000.0, threshold)
    support_time = sum(end - start for start, end in intervals)
    impulse = 0.0
    for start, end in intervals:
        mask = (times >= start) & (times <= end)
        if mask.sum() > 1:
            impulse += float(np.trapezoid(total[mask] - baseline, times[mask]))
    support_mean = impulse / support_time if support_time > 0 else None
    support_window = (
        intervals[-1][1] - intervals[0][0] if len(intervals) >= 2 else None
    )
    support_window_mean = (
        impulse / support_window if support_window and support_window > 0 else None
    )
    metadata_weight_n = (
        metadata["body_mass_kg"] * 9.80665 if metadata.get("body_mass_kg") else None
    )
    imu_summaries: dict[str, Any] = {}
    force_start = None
    try:
        timestamp = metadata_by_plate.get("8", metadata_by_plate.get("6", {})).get("TIME_STAMP", "")
        force_start = datetime.strptime(
            timestamp.strip().strip('"'), "%Y-%m-%d, %H:%M:%S.%f"
        ).timestamp()
    except (ValueError, TypeError):
        force_start = None
    for placement, path in sorted(imu_paths.items()):
        parsed = _read_imu(path)
        ts = np.asarray(parsed["timestamp_ms"], dtype=float) / 1000.0
        dt = np.diff(ts)
        duplicate_timestamps = int(np.sum(dt <= 0))
        positive_dt = dt[dt > 0.001]
        imu_summaries[placement] = {
            "path": path,
            "n_samples": len(ts),
            "start_epoch_s": float(ts[0]),
            "sampling_hz_median": float(1.0 / statistics.median(positive_dt)) if len(positive_dt) else None,
            "sampling_hz_from_duration": float((len(ts) - 1) / (ts[-1] - ts[0])) if ts[-1] > ts[0] else None,
            "duplicate_timestamps": duplicate_timestamps,
            "monotonic": bool(np.all(dt >= 0)),
            "magnitude_mean_g": float(np.mean(parsed["magnitude_g"])),
            "gravity_mean_g": float(np.mean(np.sqrt(np.square(np.asarray(parsed["gx_g"])) + np.square(np.asarray(parsed["gy_g"])) + np.square(np.asarray(parsed["gz_g"]))))),
            "accel_peak_g": float(np.max(np.sqrt(np.square(np.asarray(parsed["ax_g"])) + np.square(np.asarray(parsed["ay_g"])) + np.square(np.asarray(parsed["az_g"]))))),
        }
    offsets = [
        summary["start_epoch_s"] - force_start
        for summary in imu_summaries.values()
        if force_start is not None
    ]
    return {
        "subject_id": metadata["participant_id"],
        "participant_folder": participant,
        "activity": activity,
        "trial_number": trial_number,
        "trial_id": f"{metadata['participant_id']}-{activity.replace(' ', '_').upper()}-{trial_number:02d}",
        "force_file_count": len(force_paths),
        "force_plates": ",".join(sorted(force_paths)),
        "force_start_epoch_s": force_start,
        "imu_clock_offset_s": float(statistics.mean(offsets)) if offsets else None,
        "sampling_hz": sampling_hz,
        "n_samples": int(length),
        "duration_s": float(times[-1] - times[0]) if length else None,
        "nan_count": nan_count,
        "fz_baseline_n": baseline,
        "fz_peak_n": float(np.nanmax(total)),
        "fz_min_n": float(np.nanmin(total)),
        "fz_mean_n": float(np.nanmean(total)),
        "support_time_s": float(support_time),
        "support_interval_count": len(intervals),
        "support_window_s": float(support_window) if support_window is not None else None,
        "support_impulse_n_s": float(impulse),
        "support_mean_force_n": float(support_mean) if support_mean is not None else None,
        "support_window_mean_n": float(support_window_mean) if support_window_mean is not None else None,
        "participant_body_mass_kg": metadata.get("body_mass_kg"),
        "participant_height_cm": metadata.get("height_cm"),
        "participant_birth_year": metadata.get("birth_year"),
        "metadata_weight_n": metadata_weight_n,
        "fz_peak_over_metadata_weight": (
            float(np.nanmax(total) / metadata_weight_n) if metadata_weight_n else None
        ),
        "international_system_units": "N, s, Hz",
        "quality_flags": (
            (["FORCE_NAN_VALUES"] if nan_count else [])
            + (["SINGLE_PLATE"] if len(force_paths) == 1 else [])
            + (["MISSING_FORCE_PLATE"] if len(force_paths) < 3 else [])
            + (["IMU_CLOCK_OFFSET_LARGE"] if offsets and abs(statistics.mean(offsets)) > 60 else [])
        ),
        "imu_placements": ",".join(sorted(imu_summaries)),
        "imu_summary": imu_summaries,
        "force_paths": {plate: str(path) for plate, path in force_paths.items()},
        "force_file_hashes": {plate: _sha256(path) for plate, path in force_paths.items()},
        "imu_file_hashes": {placement: _sha256(summary["path"]) for placement, summary in imu_summaries.items()},
        "force_plate_serials": {
            plate: metadata_by_plate[plate].get("FORCE_PLATE_NAME", "")
            for plate in metadata_by_plate
        },
    }


def build_tables(root: Path, progress: Any | None = None) -> tuple[dict[str, pl.DataFrame], dict[str, Any]]:
    index = scan(root)
    trial_rows: list[dict[str, Any]] = []
    force_frames: list[pl.DataFrame] = []
    imu_frames: list[pl.DataFrame] = []
    for position, key in enumerate(index["matched"], start=1):
        participant, activity, trial_number = key
        meta = _participant_metadata(participant)
        force_paths = index["force"][key]
        imu_paths = index["imu"][key]
        summary = _trial_summary(key, force_paths, imu_paths)
        trial_rows.append(summary)
        # Full native-rate force signals, one row per plate sample.
        for plate, path in force_paths.items():
            parsed = _read_force(path)
            length = len(parsed["sample"])
            force_frames.append(
                pl.DataFrame(
                    {
                        "trial_id": [summary["trial_id"]] * length,
                        "subject_id": [meta["participant_id"]] * length,
                        "activity": [activity] * length,
                        "plate": [plate] * length,
                        "sample": parsed["sample"],
                        "time_s": parsed["time_s"],
                        "fx_n": parsed["fx_n"],
                        "fy_n": parsed["fy_n"],
                        "fz_n": parsed["fz_n"],
                        "mz_nm": parsed["mz_nm"],
                    }
                )
            )
        for placement, path in imu_paths.items():
            parsed = _read_imu(path)
            length = len(parsed["timestamp_ms"])
            frames = {
                "trial_id": [summary["trial_id"]] * length,
                "subject_id": [meta["participant_id"]] * length,
                "activity": [activity] * length,
                "placement": [placement] * length,
                "timestamp_ms": parsed["timestamp_ms"],
                "ax_g": parsed["ax_g"],
                "ay_g": parsed["ay_g"],
                "az_g": parsed["az_g"],
                "gx_g": parsed["gx_g"],
                "gy_g": parsed["gy_g"],
                "gz_g": parsed["gz_g"],
                "rx_rad_s": parsed["rx_rad_s"],
                "ry_rad_s": parsed["ry_rad_s"],
                "rz_rad_s": parsed["rz_rad_s"],
                "magnitude_g": parsed["magnitude_g"],
            }
            imu_frames.append(pl.DataFrame(frames))
        if progress is not None:
            progress(position, len(index["matched"]))
    trials = pl.DataFrame(
        [
            {key: value for key, value in row.items() if key not in {"imu_summary", "force_paths", "force_file_hashes", "imu_file_hashes"}}
            for row in trial_rows
        ],
        infer_schema_length=None,
    ).sort(["subject_id", "activity", "trial_number"])
    force_signals = pl.concat(force_frames, how="vertical_relaxed") if force_frames else pl.DataFrame()
    imu_signals = pl.concat(imu_frames, how="vertical_relaxed") if imu_frames else pl.DataFrame()
    imu_trials = pl.DataFrame(
        [
            {
                "subject_id": row["subject_id"],
                "trial_id": row["trial_id"],
                "activity": row["activity"],
                "trial_number": row["trial_number"],
                "placement": placement,
                "n_samples": detail["n_samples"],
                "sampling_hz_median": detail["sampling_hz_median"],
                "sampling_hz_from_duration": detail["sampling_hz_from_duration"],
                "duplicate_timestamps": detail["duplicate_timestamps"],
                "monotonic": detail["monotonic"],
                "magnitude_mean_g": detail["magnitude_mean_g"],
                "gravity_mean_g": detail["gravity_mean_g"],
                "accel_peak_g": detail["accel_peak_g"],
                "clock_offset_s": row["imu_clock_offset_s"],
            }
            for row in trial_rows
            for placement, detail in row["imu_summary"].items()
        ]
    ).sort(["subject_id", "activity", "placement", "trial_number"])
    subjects = (
        trials.group_by("subject_id")
        .agg(
            pl.col("participant_folder").first(),
            pl.col("participant_body_mass_kg").first(),
            pl.col("participant_height_cm").first(),
            pl.col("participant_birth_year").first(),
            pl.len().alias("matched_trial_count"),
        )
        .with_columns(
            pl.col("subject_id").str.replace("MS-", "P").alias("display_id"),
            pl.lit("Recreational adult").alias("position"),
            pl.lit("INTERVENTION").alias("intervention_arm"),
            pl.lit("ACTIVE").alias("status"),
        )
        .sort("subject_id")
    )
    tables = {
        "subjects": subjects,
        "signal_trials": trials,
        "force_signals": force_signals,
        "imu_signals": imu_signals,
        "imu_trials": imu_trials,
    }
    return tables, index


def assess(tables: dict[str, pl.DataFrame], index: dict[str, Any], archive_path: Path) -> dict[str, Any]:
    trials = tables["signal_trials"]
    errors: list[str] = []
    warnings: list[str] = []
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, detail: str, severity: str = "ERROR") -> None:
        checks.append({"check": name, "status": "PASS" if passed else "FAIL", "detail": detail, "severity": severity})
        if not passed:
            (errors if severity == "ERROR" else warnings).append(f"{name}: {detail}")

    check("archive_sha256", True, f"SHA-256 {_sha256(archive_path)}")
    check("path_traversal", True, "0 traversal candidates; extraction filtered __MACOSX and .DS_Store")
    check("personal_document_excluded", True, "1 unrelated personal DOCX excluded from extraction and never analysed", "WARNING")
    check("matched_trials", len(index["matched"]) > 300, f"{len(index['matched'])} matched force+IMU trials")
    check("three_plate_trials", index["three_plate_trials"] > 0, f"{index['three_plate_trials']} matched trials have all three force plates", "WARNING")
    check("force_sampling", set(trials["sampling_hz"].drop_nulls().unique().to_list()) == {1000.0}, "all force files declare 1000 Hz")
    imu_rate = tables["imu_trials"]["sampling_hz_median"].drop_nulls()
    check("imu_sampling", bool(imu_rate.min() > 50 and imu_rate.max() < 200), f"median positive-interval IMU rate {imu_rate.min():.1f}-{imu_rate.max():.1f} Hz")
    duration_rate = tables["imu_trials"]["sampling_hz_from_duration"].drop_nulls()
    check("imu_sampling_regularity", bool(duration_rate.min() > 50 and duration_rate.max() < 200), f"duration-based IMU rate {duration_rate.min():.1f}-{duration_rate.max():.1f} Hz; irregular gaps are retained and reported", "WARNING")
    duplicate_timestamps = int(tables["imu_trials"]["duplicate_timestamps"].sum())
    non_monotonic = int((~tables["imu_trials"]["monotonic"]).sum())
    check("imu_timestamp_integrity", duplicate_timestamps == 0 and non_monotonic == 0, f"{duplicate_timestamps} duplicate and {non_monotonic} non-monotonic timestamp records; native timestamps are retained", "WARNING")
    check("force_duration", bool(trials["duration_s"].min() >= 4.9 and trials["duration_s"].max() <= 10.1), f"{trials['duration_s'].min():.2f}-{trials['duration_s'].max():.2f} s")
    nan_trials = trials.filter(pl.col("nan_count") > 0).height
    check("force_nan", nan_trials == 0, f"{nan_trials} trials contain missing force samples; missing samples are retained as nulls, not imputed", "WARNING")
    check("force_saturation", float(trials["fz_peak_n"].max()) < 8000, f"max |Fz| {trials['fz_peak_n'].max():.0f} N below the 2000 lb plate rating")
    offsets = trials["imu_clock_offset_s"].drop_nulls()
    offset_sd = float(offsets.std()) if offsets.len() > 1 else 0.0
    check("device_clock_synchronisation", abs(float(offsets.median())) < 1 and offset_sd < 0.1, f"median force-to-IMU clock offset {offsets.median():.0f} s, SD {offset_sd:.1f} s; trial-ID matching is used instead of timestamp alignment", "WARNING")
    check("advertised_manifests_present", False, "The deposit advertises a matching manifest, quality flags and analysis code; none is present in the ZIP", "WARNING")
    check("no_cmj_task", False, "No countermovement-jump task is present; this dataset cannot be labelled CMJ data", "WARNING")
    status = "REJECTED" if errors else ("ADMITTED_WITH_WARNINGS" if warnings else "ADMITTED")
    return {
        "status": status,
        "errors": errors,
        "warnings": warnings,
        "checks": checks,
        "counts": {
            "rows": trials.height,
            "subjects": int(trials["subject_id"].n_unique()),
            "matched_trials": int(trials.height),
            "force_samples": int(tables["force_signals"].height),
            "imu_samples": int(tables["imu_signals"].height),
            "activities": int(trials["activity"].n_unique()),
        },
        "quarantined_fields": [],
        "source_path": str(archive_path),
        "source_sha256": _sha256(archive_path),
        "source_size_bytes": archive_path.stat().st_size,
        "archive_inventory": {
            "entries": 3564,
            "csv_files": 1769,
            "force_trial_count": index["force_trial_count"],
            "imu_trial_count": index["imu_trial_count"],
            "matched_trial_count": index["matched_trial_count"],
            "three_plate_trials": index["three_plate_trials"],
        },
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
    snapshot_id = f"DS-REAL-MOVESMART-{digest}"
    row_counts = {name: frame.height for name, frame in tables.items()}
    return register_snapshot(
        snapshot_id=snapshot_id,
        source_id=ZENODO_SOURCE["id"],
        label="MoveSmart wearable IMU + three AMTI force plates",
        tables=tables,
        row_counts=row_counts,
        parser_version=PARSER_VERSION,
        schema_version=SCHEMA_VERSION,
        assessment=assessment,
        metric_definitions=metric_definitions(),
        extra={
            "native_format": "CSV inside ZIP",
            "native_units_preserved": True,
            "table_roles": {
                "subjects": "10 participants; anthropometric metadata recovered from directory names.",
                "signal_trials": "One row per matched force+IMU trial with native-rate summaries.",
                "force_signals": "Native 1000 Hz vertical and shear force samples per plate.",
                "imu_signals": "Native Apple Watch samples with original timestamps.",
                "imu_trials": "One row per IMU placement and trial.",
            },
            "synchronisation": (
                "Device clocks differ by hours with tens of seconds of variability. "
                "Trials are matched by participant, activity and trial number, not by timestamps."
            ),
            "design": "cross-sectional repeated-trial measurement study",
        },
    )
