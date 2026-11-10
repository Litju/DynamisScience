"""Independent scientific qualification for the admitted real datasets.

The record is deliberately explicit about what was compared, against which
reference implementation, with which tolerances, and what remains limited.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from . import realanalysis, realstore
from .data_root import data_root, ensure_layout
from .qualification import anova_icc_reference
from .real_movesmart import _read_force, _support_intervals


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rscript() -> str | None:
    configured = os.environ.get("DYNAMISSCIENCE_RSCRIPT", "").strip()
    if configured and Path(configured).exists():
        return configured
    found = shutil.which("Rscript")
    if found:
        return found
    return None


def _run(command: list[str], timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(command, capture_output=True, text=True, timeout=timeout)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _mixedlm_qualification(snapshot_id: str) -> dict[str, Any]:
    runs = [run for run in realanalysis.list_runs() if run["method_id"] == "METH-REAL-TREND" and run["status"] == "COMPLETED"]
    if not runs:
        return {"id": "QUAL-REAL-MIXEDLM", "status": "BLOCKED", "reason": "No real-data trend run has been executed."}
    run = max(runs, key=lambda item: item["created_at"])
    frame = realstore.read_table(snapshot_id, "cmj_occasions").select(["subject_id", "occasion", "cmj_height_cm"]).drop_nulls()
    qualification = data_root() / "qualification"
    qualification.mkdir(parents=True, exist_ok=True)
    input_csv = qualification / "mixedlm_input.csv"
    output_dir = qualification / "r_mixedlm"
    output_dir.mkdir(parents=True, exist_ok=True)
    frame.write_csv(input_csv)
    rscript = _rscript()
    if rscript is None:
        return {
            "id": "QUAL-REAL-MIXEDLM",
            "scientific_method": "Linear mixed-effects change model",
            "status": "BLOCKED",
            "reason": "Rscript is not available. Set DYNAMISSCIENCE_RSCRIPT to a local R installation.",
            "input_snapshot": snapshot_id,
            "dynamis_run": run["id"],
            "dynamis_result": run["result"]["coefficients"],
        }
    r_version = _run([rscript, "-e", "cat(R.version.string)"]).stdout.strip()
    lme4_version = _run([rscript, "-e", "cat(as.character(packageVersion('lme4')))"]).stdout.strip()
    script = Path(__file__).resolve().parent.parent / "scripts" / "real_mixedlm.R"
    completed = _run([rscript, str(script), str(input_csv), str(output_dir)], timeout=600)
    if completed.returncode != 0:
        return {
            "id": "QUAL-REAL-MIXEDLM",
            "scientific_method": "Linear mixed-effects change model",
            "status": "FAILED",
            "reason": f"R reference failed: {completed.stderr[-1000:]}",
            "dynamis_run": run["id"],
        }
    fixed = {row["term"]: {"estimate": float(row["estimate"]), "se": float(row["se"])} for row in _read_csv(output_dir / "fixed.csv")}
    fit = _read_csv(output_dir / "fit.csv")[0]
    varcorr = {}
    for row in _read_csv(output_dir / "varcorr.csv"):
        var1 = "" if row["var1"] in ("", "NA") else row["var1"]
        var2 = "" if row["var2"] in ("", "NA") else row["var2"]
        key = f"{row['grp']}:{var1}:{var2}"
        varcorr[key] = {
            "vcov": float(row["vcov"]),
            "sdcor": float(row["sdcor"]) if row["sdcor"] not in ("", "NA") else None,
        }
    dynamis = run["result"]
    comparisons = {}
    for term in ("(Intercept)", "occasion_c"):
        key = "intercept" if term == "(Intercept)" else "occasion_slope"
        ref = fixed[term]
        cur = dynamis["coefficients"][key]
        comparisons[f"{key}_estimate"] = {
            "reference": ref["estimate"],
            "dynamis": cur["estimate"],
            "absolute_difference": abs(ref["estimate"] - cur["estimate"]),
            "relative_difference": abs(ref["estimate"] - cur["estimate"]) / max(abs(ref["estimate"]), 1e-12),
            "tolerance_absolute": 1e-4,
            "pass": abs(ref["estimate"] - cur["estimate"]) <= 1e-4,
        }
        comparisons[f"{key}_se"] = {
            "reference": ref["se"],
            "dynamis": cur["std_error"],
            "absolute_difference": abs(ref["se"] - cur["std_error"]),
            "relative_difference": abs(ref["se"] - cur["std_error"]) / max(abs(ref["se"]), 1e-12),
            "tolerance_relative": 5e-3,
            "pass": abs(ref["se"] - cur["std_error"]) / max(abs(ref["se"]), 1e-12) <= 5e-3,
        }
    r_loglik = float(fit["logLik"])
    ll_diff = abs(r_loglik - dynamis["log_likelihood"])
    comparisons["log_likelihood"] = {
        "reference": r_loglik,
        "dynamis": dynamis["log_likelihood"],
        "absolute_difference": ll_diff,
        "tolerance_absolute": 1e-3,
        "pass": ll_diff <= 1e-3,
    }
    r_random = {
        "subject_intercept_variance": varcorr.get("subject_id:(Intercept):", {}).get("vcov"),
        "subject_slope_variance": varcorr.get("subject_id:occasion_c:", {}).get("vcov"),
        "subject_intercept_slope_covariance": varcorr.get("subject_id:(Intercept):occasion_c", {}).get("vcov"),
        "residual_variance": varcorr.get("Residual::", {}).get("vcov"),
    }
    for key, value in r_random.items():
        current = dynamis["random_effects"].get(key)
        if value is not None and current is not None:
            comparisons[key] = {
                "reference": value,
                "dynamis": current,
                "absolute_difference": abs(value - current),
                "relative_difference": abs(value - current) / max(abs(value), 1e-12),
                "tolerance_relative": 1e-3,
                "pass": abs(value - current) / max(abs(value), 1e-12) <= 1e-3,
            }
    passed = all(item["pass"] for item in comparisons.values())
    return {
        "id": "QUAL-REAL-MIXEDLM",
        "scientific_method": "Linear mixed-effects change model (CMJ height, four occasions)",
        "method_version": "1.0.0",
        "status": "QUALIFIED" if passed else "FAILED",
        "pass_fail": "PASS" if passed else "FAIL",
        "input_snapshot": snapshot_id,
        "input_checksum": realstore.get_snapshot(snapshot_id)["checksums"].get("cmj_occasions.parquet"),
        "dynamis_run": run["id"],
        "reference_implementation": f"R {r_version}; lme4 {lme4_version}; lmer(..., REML=FALSE)",
        "dynamis_implementation": f"statsmodels MixedLM; optimizer selected among lbfgs/bfgs/powell/nm by log-likelihood; selected={dynamis.get('optimizer')}",
        "model": "cmj_height_cm ~ occasion_c + (1 + occasion_c | subject_id), ML",
        "reference_result": {"fixed": fixed, "log_likelihood": r_loglik, "random_effects": r_random, "nobs": int(fit["nobs"]), "singular": fit["singular"] == "FALSE"},
        "dynamis_result": {"coefficients": dynamis["coefficients"], "log_likelihood": dynamis["log_likelihood"], "random_effects": dynamis["random_effects"], "n_observations": dynamis["n_observations"]},
        "comparisons": comparisons,
        "ab_histogram": None,
        "known_limitations": [
            "The comparison is a single real dataset with 21 athletes and four occasions.",
            "The initial L-BFGS fit stopped at logLik -215.824 while lme4 found -208.312; the production implementation now selects the best converged optimizer and the pre-fix run is retained in the ledger as RUN-REAL-0001.",
            "Residual diagnostics are not a substitute for external validation on a new cohort.",
        ],
        "reproduction_commands": [
            f"$env:DYNAMISSCIENCE_DATA_ROOT='{data_root()}'",
            f"$env:DYNAMISSCIENCE_RSCRIPT='{rscript}'",
            "python -m dynamis_science.qualification_real",
        ],
        "environment": {"python": sys.version.split()[0], "r": r_version, "lme4": lme4_version},
        "checked_at": _now(),
    }


def _reliability_qualification(snapshot_id: str) -> dict[str, Any]:
    runs = [run for run in realanalysis.list_runs() if run["method_id"] == "METH-REAL-RELIABILITY"]
    if not runs:
        return {"id": "QUAL-REAL-RELIABILITY", "status": "BLOCKED", "reason": "No reliability run has been executed."}
    run = max(runs, key=lambda item: item["created_at"])
    activity = run["result"].get("activity", "Walking")
    frame = realstore.read_table(snapshot_id, "signal_trials")
    rows = [row for row in frame.iter_rows(named=True) if row["activity"] == activity]
    by_subject: dict[str, list[float]] = {}
    for row in sorted(rows, key=lambda item: (item["subject_id"], int(item["trial_number"]))):
        by_subject.setdefault(row["subject_id"], []).append(float(row["fz_peak_n"]))
    complete = {key: values for key, values in by_subject.items() if len(values) >= 2}
    k = min(int(run["parameters"].get("max_trials", 8)), min(len(values) for values in complete.values()))
    subjects = sorted(complete)
    matrix = np.array([complete[subject][:k] for subject in subjects], dtype=float)
    n = matrix.shape[0]
    means = matrix.mean(axis=1)
    anova = anova_icc_reference(matrix)
    icc, te = anova["icc_3_1"], anova["typical_error"]
    cv = float(np.mean(matrix.std(axis=1, ddof=1) / np.maximum(np.abs(means), 1e-9)) * 100)
    result = run["result"]

    def compare(reference: float, current: float) -> dict[str, Any]:
        relative = abs(reference - current) / max(abs(reference), 1e-12)
        return {"reference": reference, "dynamis": current, "absolute_difference": abs(reference - current), "relative_difference": relative, "tolerance_relative": 1e-9, "pass": relative <= 1e-9}

    comparisons = {
        "icc_3_1": compare(icc, result["icc_3_1"]),
        "typical_error": compare(te, result["typical_error"]),
        "mean_cv_percent": compare(cv, result["mean_cv_percent"]),
    }
    passed = all(item["pass"] for item in comparisons.values())
    return {
        "id": "QUAL-REAL-RELIABILITY",
        "scientific_method": "ICC(3,1) repeated-trial reliability of peak vertical GRF",
        "method_version": "1.1.0",
        "status": "QUALIFIED" if passed else "FAILED",
        "pass_fail": "PASS" if passed else "FAIL",
        "input_snapshot": snapshot_id,
        "input_checksum": realstore.get_snapshot(snapshot_id)["checksums"].get("signal_trials.parquet"),
        "dynamis_run": run["id"],
        "activity": activity,
        "reference_implementation": "statsmodels OLS two-way ANOVA (anova_lm, y ~ C(subject) + C(trial)); trials in acquisition order",
        "statistical_model": "Two-way ANOVA; participants random, repeated trials fixed; single measurement, consistency; ICC(3,1).",
        "sample": {"n_subjects": n, "k_trials": k, "trials_used": int(matrix.size), "trials_available": len(rows), "subjects": subjects},
        "reference_result": {"icc_3_1": icc, "typical_error_n": te, "mean_cv_percent": cv, "ms_between": anova["ms_between"], "ms_error": anova["ms_error"]},
        "dynamis_result": {"icc_3_1": result["icc_3_1"], "typical_error_n": result["typical_error"], "mean_cv_percent": result["mean_cv_percent"], "ms_between": result["ms_between"], "ms_error": result.get("ms_error"), "icc_1_1_sensitivity": result.get("icc_1_1_sensitivity"), "icc_2_1_sensitivity": result.get("icc_2_1_sensitivity")},
        "comparisons": comparisons,
        "confidence_interval": {"low": result["icc_3_1_ci_low"], "high": result["icc_3_1_ci_high"], "method": "Shrout-Fleiss F-based 95% interval"},
        "known_limitations": [
            "Only one activity (walking) is the primary reliability analysis; other activities are sensitivity analyses.",
            "Balanced subset uses the first k trials per participant in acquisition order; later trials are excluded.",
            "Method 1.0.0 (RES-587..RES-613) sorted values before trimming and used the one-way MS within; its ICC and typical error are superseded by 1.1.0 (RES-619).",
            "Peak force is not normalised to body weight, so between-participant variation remains.",
            "The deposit contains no calibration log or speed control.",
        ],
        "reproduction_commands": [
            f"$env:DYNAMISSCIENCE_DATA_ROOT='{data_root()}'",
            "python -m dynamis_science.qualification_real",
        ],
        "checked_at": _now(),
    }


def _signal_qualification(snapshot_id: str) -> dict[str, Any]:
    snapshot = realstore.get_snapshot(snapshot_id)
    assert snapshot is not None
    trials = realstore.read_table(snapshot_id, "signal_trials")
    selected = []
    for activity in ("Walking", "Running", "Heel drop", "Step drop"):
        subset = trials.filter(pl.col("activity") == activity).sort(["subject_id", "trial_number"])
        if subset.height:
            selected.append(subset.row(0, named=True))
    comparisons = []
    extracted = data_root() / "extracted" / "zenodo-17376717" / "Dataset"
    for row in selected:
        trial_id = row["trial_id"]
        participant_folder = row["participant_folder"]
        prefix = {"Walking": "walk", "Jogging": "jog", "Running": "run", "Heel drop": "heel", "Step drop": "drop"}[row["activity"]]
        trial_number = int(row["trial_number"])
        plate_files = sorted(
            extracted.glob(f"{participant_folder}/{prefix}{trial_number:04d}_f_*.csv")
        )
        if not plate_files:
            continue
        signals = []
        times = None
        for path in plate_files:
            parsed = _read_force(path)
            signals.append(np.nan_to_num(np.asarray(parsed["fz_n"], dtype=float), nan=0.0))
            if times is None:
                times = np.asarray(parsed["time_s"], dtype=float)
        length = min(len(values) for values in signals)
        total = np.sum([values[:length] for values in signals], axis=0)
        times = times[:length]
        baseline = float(np.median(total[: min(100, length)]))
        intervals = _support_intervals(total, 1000.0, max(20.0, abs(baseline) + 20.0))
        impulse = 0.0
        for start, end in intervals:
            mask = (times >= start) & (times <= end)
            if mask.sum() > 1:
                impulse += float(np.trapezoid(total[mask] - baseline, times[mask]))
        independent_peak = float(np.max(total))
        independent_impulse = float(impulse)
        comparisons.append(
            {
                "trial_id": trial_id,
                "activity": row["activity"],
                "plates": len(plate_files),
                "snapshot_peak_n": float(row["fz_peak_n"]),
                "independent_peak_n": independent_peak,
                "peak_absolute_difference": abs(independent_peak - float(row["fz_peak_n"])),
                "snapshot_impulse_n_s": float(row["support_impulse_n_s"]),
                "independent_impulse_n_s": independent_impulse,
                "impulse_absolute_difference": abs(independent_impulse - float(row["support_impulse_n_s"])),
                "pass": abs(independent_peak - float(row["fz_peak_n"])) <= 1e-6 and abs(independent_impulse - float(row["support_impulse_n_s"])) <= 1e-3,
            }
        )
    passed = bool(comparisons) and all(item["pass"] for item in comparisons)
    return {
        "id": "QUAL-REAL-SIGNAL",
        "scientific_method": "Force-plate sampling, support detection and numerical integration",
        "method_version": "1.0.0",
        "status": "QUALIFIED" if passed else "FAILED",
        "pass_fail": "PASS" if passed else "FAIL",
        "input_snapshot": snapshot_id,
        "input_checksum": snapshot["checksums"].get("force_signals.parquet"),
        "reference_implementation": "Independent NumPy sum, threshold detector and trapezoidal integration from the original CSVs",
        "comparisons": comparisons,
        "sampling": {"force_hz": 1000.0, "imu_nominal_hz": 100.0, "force_duration_s": [5.0, 10.0]},
        "known_limitations": [
            "Only four representative trials are re-derived end-to-end; the snapshot summary is not re-derived for all 398 trials.",
            "The force-plate local Z axis is assumed vertical; the archive provides no orientation calibration record.",
            "No sample-level IMU-to-force synchronisation is claimed; device clocks differ by about four hours.",
            "Body-weight recovery from support-window mean force was tested and rejected: bias -169 N (-22.9%) with wide limits of agreement.",
        ],
        "reproduction_commands": [
            f"$env:DYNAMISSCIENCE_DATA_ROOT='{data_root()}'",
            "python -m dynamis_science.qualification_real",
        ],
        "checked_at": _now(),
    }


def run() -> list[dict[str, Any]]:
    ensure_layout()
    mendeley = realstore.snapshot_for_source("SRC-MENDELEY-6P99569X66")
    movesmart = realstore.snapshot_for_source("SRC-ZENODO-17376717")
    records = []
    if mendeley:
        records.append(_mixedlm_qualification(mendeley["id"]))
    if movesmart:
        records.append(_reliability_qualification(movesmart["id"]))
        records.append(_signal_qualification(movesmart["id"]))
    path = data_root() / "qualification" / "real_qualification.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return records


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
