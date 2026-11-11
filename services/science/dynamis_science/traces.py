"""Sample-level time-series contract (RES-636): family RAW_FORCE_TIME.

Grain: Subject -> Session -> Trial -> Trace -> sample (time_s, optional sample_index) -> channel -> value (N).
A trial identifier legitimately repeats across thousands of sample rows; the unique key is
(subject_id, session_id, trial_id, time_s). QC streams the normalized Parquet in bounded batches, so memory
is O(batch + number of traces), never O(file). Raw samples are stored unchanged apart from unit/time
normalization; no derived metric is computed here.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import Any

import polars as pl
import pyarrow.parquet as pq

from . import admission

FAMILY = "RAW_FORCE_TIME"
CHANNELS = ("force_z_n", "force_left_n", "force_right_n", "force_combined_n")
KEYS = ["subject_id", "session_id", "trial_id"]
REQUIRED = KEYS + ["instrument_id", "protocol_id", "time_s"]
BATCH_ROWS = 500_000
MAX_ROWS = 100_000_000  # explicit resource limit; larger recordings must be split by the researcher
FORCE_RANGE = (-2000.0, 20000.0)  # N; outside this the record is implausible for a force platform
SAMPLING_TOLERANCE = (0.01, 0.10)  # relative: warn above the first, reject above the second
SIGNALS, TRIALS = "force_signals", "trace_index"  # not "signal_trials": qualified methods bind to that name


def scan(path: Path, channels: list[str]) -> dict[str, Any]:
    """One bounded pass over the normalized Parquet: per-trace statistics and totals."""
    state: dict[tuple, dict[str, Any]] = {}
    bad = {"missing_id": 0, "missing_time": 0, "missing_value": 0}
    rows = 0
    for batch in pq.ParquetFile(path).iter_batches(batch_size=BATCH_ROWS):
        frame = pl.from_arrow(batch)
        rows += frame.height
        bad["missing_id"] += sum(frame[k].null_count() for k in KEYS)
        bad["missing_time"] += frame["time_s"].null_count() + int(frame["time_s"].is_nan().sum())
        invalid = [(pl.col(c).is_null() | pl.col(c).is_nan() | pl.col(c).is_infinite()) for c in channels]
        bad["missing_value"] += int(frame.select(pl.sum_horizontal(invalid).sum()).item())
        grouped = frame.drop_nulls(KEYS + ["time_s"]).group_by(KEYS, maintain_order=True).agg(
            n=pl.len(), t0=pl.col("time_s").first(), t1=pl.col("time_s").last(),
            dmin=pl.col("time_s").diff().min(), dmax=pl.col("time_s").diff().max(),
            fmin=pl.min_horizontal([pl.col(c).min() for c in channels]),
            fmax=pl.max_horizontal([pl.col(c).max() for c in channels]),
        )
        for row in grouped.iter_rows(named=True):
            key = tuple(row[k] for k in KEYS)
            old = state.get(key)
            if old is None:
                state[key] = {k: row[k] for k in ("n", "t0", "t1", "dmin", "dmax", "fmin", "fmax")}
                continue
            boundary = row["t0"] - old["t1"]
            dmins = [d for d in (old["dmin"], row["dmin"], boundary) if d is not None]
            dmaxs = [d for d in (old["dmax"], row["dmax"], boundary) if d is not None]
            old.update(n=old["n"] + row["n"], t1=row["t1"], dmin=min(dmins), dmax=max(dmaxs),
                       fmin=min(x for x in (old["fmin"], row["fmin"]) if x is not None) if old["fmin"] is not None or row["fmin"] is not None else None,
                       fmax=max(x for x in (old["fmax"], row["fmax"]) if x is not None) if old["fmax"] is not None or row["fmax"] is not None else None)
    return {"rows": rows, "traces": state, "bad": bad}


def _channels(path: Path) -> list[str]:
    return [c for c in CHANNELS if c in pq.ParquetFile(path).schema_arrow.names]


def validate_trace(artifact: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    """Conservative QC. Returns an admission quality assessment (same shape as validate_cmj)."""
    errors: list[str] = []
    warnings: list[str] = []
    quarantined: list[str] = []
    rejected: list[str] = []
    path = Path(artifact["stored_path"])
    try:
        names = pq.ParquetFile(path).schema_arrow.names
    except Exception as exc:
        return admission._quality_result(artifact, FAMILY, metadata, "REJECTED",
                                         [f"corrupt or unreadable file: {type(exc).__name__}"], [], [], [], {})
    channels = _channels(path)
    missing = [c for c in REQUIRED if c not in names]
    if missing:
        errors.append(f"missing required columns: {', '.join(missing)}")
    if not channels:
        errors.append("no force channel columns present")
    if errors:
        return admission._quality_result(artifact, FAMILY, metadata, "REJECTED", errors, warnings, rejected, quarantined, {})
    result = scan(path, channels)
    rows, traces, bad = result["rows"], result["traces"], result["bad"]
    if rows == 0:
        errors.append("dataset contains no records")
    if rows > MAX_ROWS:
        errors.append(f"more than {MAX_ROWS:,} samples; split the recording")
    if bad["missing_id"]:
        errors.append("missing subject, session or trial identifiers")
    if bad["missing_time"]:
        errors.append(f"{bad['missing_time']} samples without a valid time")
    spans: dict[tuple, set] = {}
    for subject, session, trial in traces:
        spans.setdefault(trial, set()).add((subject, session))
    for trial, owners in spans.items():
        if len(owners) > 1:
            errors.append(f"trial id {trial} belongs to several subjects or sessions; traces were not merged")
            rejected.append(str(trial))
    declared = metadata.get("sampling_hz")
    for (subject, session, trial), t in traces.items():
        label = str(trial)
        if t["n"] < 2:
            errors.append(f"trace {label} has fewer than 2 samples")
            continue
        if t["dmin"] is not None and t["dmin"] <= 0:
            errors.append(f"trace {label} has duplicate or non-increasing sample times")
            rejected.append(label)
            continue
        implied = (t["n"] - 1) / (t["t1"] - t["t0"])
        if declared:
            deviation = abs(implied - declared) / declared
            if deviation > SAMPLING_TOLERANCE[1]:
                errors.append(f"trace {label} timestamps imply {implied:.3f} Hz, not the declared {declared:g} Hz")
            elif deviation > SAMPLING_TOLERANCE[0]:
                warnings.append(f"trace {label} timestamps imply {implied:.3f} Hz versus declared {declared:g} Hz")
            if t["dmax"] is not None and t["dmax"] > 5 / declared:
                warnings.append(f"trace {label} has a time gap of {t['dmax']:.4g} s")
        if t["fmin"] is not None and (t["fmin"] < FORCE_RANGE[0] or t["fmax"] > FORCE_RANGE[1]):
            warnings.append(f"implausible force range in trace {label}: {t['fmin']:.1f} to {t['fmax']:.1f} N")
            quarantined.append(label)
    if bad["missing_value"]:
        warnings.append(f"{bad['missing_value']} missing or non-finite channel values")
    if not metadata.get("coordinate_system"):
        warnings.append("force orientation, plate coordinate system and zeroing are not specified; "
                        "interpretation of the sign and bodyweight offset is limited")
    if metadata.get("sampling_source") == "estimated_from_timestamps":
        warnings.append("sampling rate was estimated from the timestamps, not declared")
    instruments = sorted({str(v) for v in pl.scan_parquet(path).select("instrument_id").unique().collect()["instrument_id"].to_list()})
    for iid in instruments:
        instrument = admission.get_instrument(iid)
        if instrument is None:
            warnings.append(f"unrecognized instrument metadata: {iid}")
            quarantined.append(iid)
        elif instrument.get("measurement_family") != FAMILY:
            errors.append(f"instrument {iid} belongs to a different measurement family")
    for pid in sorted({str(v) for v in pl.scan_parquet(path).select("protocol_id").unique().collect()["protocol_id"].to_list()}):
        protocol = admission.get_protocol(pid)
        if protocol is None:
            warnings.append(f"unrecognized protocol: {pid}")
        elif protocol.get("measurement_family") != FAMILY:
            errors.append(f"protocol {pid} belongs to a different measurement family")
    warnings.extend(admission._calibration_warnings(artifact, instruments))
    status = "ADMITTED"
    if errors:
        status = "REJECTED"
    elif quarantined or any("unrecognized" in w or "calibration" in w or "implausible" in w for w in warnings):
        status = "QUARANTINED"
    elif warnings:
        status = "ADMITTED_WITH_WARNINGS"
    counts = {"samples": rows, "traces": len(traces), "subjects": len({k[0] for k in traces}),
              "channels": len(channels)}
    return admission._quality_result(artifact, FAMILY, metadata, status, errors, warnings, rejected, quarantined, counts)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_snapshot(artifact: dict[str, Any], metadata: dict[str, Any], directory: Path) -> dict[str, Any]:
    """Copy the samples unchanged (streamed) and add one row per trace. Returns {table: rows} and hashes."""
    source = Path(artifact["stored_path"])
    channels = _channels(source)
    signals = directory / f"{SIGNALS}.parquet"
    shutil.copyfile(source, signals)
    stats = scan(signals, channels)["traces"]
    declared = metadata.get("sampling_hz")
    index = [
        {"subject_id": s, "session_id": se, "trial_id": t, "trial_number": number,
         "activity": metadata.get("protocol_default", ""), "n_samples": v["n"], "time_origin_s": v["t0"],
         "duration_s": v["t1"] - v["t0"], "sampling_hz_declared": declared,
         "sampling_hz_implied": (v["n"] - 1) / (v["t1"] - v["t0"]) if v["n"] > 1 and v["t1"] > v["t0"] else None,
         "sampling_source": metadata.get("sampling_source", "declared"), "channels": ",".join(channels),
         "instrument_id": metadata.get("instrument_default", ""), "protocol_id": metadata.get("protocol_default", ""),
         "source_artifact_id": artifact["id"]}
        for number, ((s, se, t), v) in enumerate(sorted(stats.items(), key=lambda kv: tuple(map(str, kv[0]))), 1)
    ]
    trials = directory / f"{TRIALS}.parquet"
    pl.DataFrame(index).write_parquet(trials, compression="zstd")
    return {"rows": {TRIALS: len(index), SIGNALS: sum(v["n"] for v in stats.values())},
            "hashes": {f"{SIGNALS}.parquet": _sha256(signals), f"{TRIALS}.parquet": _sha256(trials)}}
