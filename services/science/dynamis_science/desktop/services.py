"""In-process application facade shared by native workspaces and tests."""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import polars as pl
import pyarrow.parquet as pq

from .. import realanalysis, realstore, researchanalysis, researchstore
from ..data_root import DataRootConfigurationError, data_root, ensure_layout
from ..generate import ARTIFACT_DIR, PARQUET_DIR, SNAPSHOT_ID


class DynamisAppService:
    """Direct Python access to the existing scientific and persistence modules."""

    def __init__(self, root: str | os.PathLike[str] | None = None) -> None:
        configured = data_root(root)
        active = data_root()
        if configured != active:
            raise DataRootConfigurationError(
                "The service root must match DYNAMISSCIENCE_DATA_ROOT"
            )
        self.root = configured
        self._initialized = False
        self.synthetic_available = False

    def ensure_initialized(self) -> dict[str, Any]:
        ensure_layout(self.root)
        if not self._initialized:
            required = (
                ARTIFACT_DIR / "dataset_snapshot.json",
                ARTIFACT_DIR / "investigations.json",
                PARQUET_DIR / "cmj_trials.parquet",
            )
            self.synthetic_available = all(path.is_file() for path in required)
            researchstore.list_projects()  # initializes the versioned SQLite schema
            self._initialized = True
        return self.verify_environment()

    def verify_environment(self) -> dict[str, Any]:
        root = data_root(self.root)
        return {
            "data_root": str(root),
            "exists": root.is_dir(),
            "writable": os.access(root, os.W_OK),
            "database": str(root / "research" / "research.db"),
            "real_snapshot_count": len(realstore.list_snapshots()),
        }

    def list_projects(self) -> list[dict[str, Any]]:
        self.ensure_initialized()
        return researchstore.list_projects(include_archived=True)

    def list_all_studies(self) -> list[dict[str, Any]]:
        self.ensure_initialized()
        synthetic = (
            _read_json(ARTIFACT_DIR / "study.json", {}).get("study", {})
            if self.synthetic_available
            else {}
        )
        authored = []
        for entity in researchstore.list_entities(include_archived=True):
            authored.append(researchstore.study_detail(entity["id"])["study"])
        return [*([synthetic] if synthetic else []), *realstore.list_studies(), *authored]

    def get_study_detail(self, study_id: str) -> dict[str, Any]:
        self.ensure_initialized()
        if study_id == "STUDY-001":
            if not self.synthetic_available:
                raise researchstore.ResearchNotFound("The synthetic regression fixture is unavailable")
            detail = _read_json(ARTIFACT_DIR / "study.json", {})
            if not detail:
                raise researchstore.ResearchNotFound(f"Study {study_id} not found")
            return {
                **detail,
                "snapshot": researchstore.get_snapshot(SNAPSHOT_ID),
                "runs": _read_json(ARTIFACT_DIR / "analysis_runs.json", []),
                "evidence": _read_json(ARTIFACT_DIR / "evidence.json", []),
                "figures": _read_json(ARTIFACT_DIR / "figures.json", []),
                "real_data": False,
            }
        if study_id in realstore.real_study_ids():
            detail = realstore.get_study(study_id)
            if detail is None:
                raise researchstore.ResearchNotFound(f"Study {study_id} not found")
            return detail
        detail = researchstore.study_detail(study_id)
        return detail

    def list_datasets(self) -> list[dict[str, Any]]:
        self.ensure_initialized()
        return [
            item
            for item in researchstore.dataset_catalogue()
            if not item.get("synthetic") or self.synthetic_available
        ]

    def get_dataset_detail(self, snapshot_id: str) -> dict[str, Any]:
        self.ensure_initialized()
        detail = realstore.snapshot_detail(snapshot_id)
        if detail is not None:
            snapshot = detail["snapshot"]
            return {**snapshot, **detail, "snapshot": snapshot}
        snapshot = researchstore.get_snapshot(snapshot_id)
        if snapshot is None:
            raise researchstore.ResearchNotFound(f"Snapshot {snapshot_id} is not admitted")
        if snapshot.get("synthetic") and not self.synthetic_available:
            raise researchstore.ResearchNotFound("The synthetic regression fixture is unavailable")
        tables = []
        for name in _table_names(snapshot):
            path = _table_path(snapshot_id, name, snapshot)
            parquet = pq.ParquetFile(path)
            tables.append(
                {
                    "name": name,
                    "file": path.name,
                    "rows": parquet.metadata.num_rows,
                    "columns": [
                        {"name": field.name, "dtype": str(field.type)}
                        for field in parquet.schema_arrow
                    ],
                }
            )
        return {**snapshot, "tables": tables}

    def read_table_page(
        self, snapshot_id: str, table_name: str, offset: int = 0, limit: int = 500
    ) -> dict[str, Any]:
        self.ensure_initialized()
        if offset < 0 or not 1 <= limit <= 500:
            raise ValueError("offset must be non-negative and limit must be between 1 and 500")
        snapshot = researchstore.get_snapshot(snapshot_id)
        if snapshot is None:
            raise researchstore.ResearchNotFound(f"Snapshot {snapshot_id} is not admitted")
        if snapshot.get("synthetic") and not self.synthetic_available:
            raise researchstore.ResearchNotFound("The synthetic regression fixture is unavailable")
        if table_name not in _table_names(snapshot):
            raise researchstore.ResearchNotFound(
                f"Table {table_name} is not in snapshot {snapshot_id}"
            )
        parquet = pq.ParquetFile(_table_path(snapshot_id, table_name, snapshot))
        total = parquet.metadata.num_rows
        rows: list[dict[str, Any]] = []
        group_start = 0
        for group_index in range(parquet.metadata.num_row_groups):
            group_rows = parquet.metadata.row_group(group_index).num_rows
            group_end = group_start + group_rows
            if group_end <= offset:
                group_start = group_end
                continue
            skip = max(0, offset - group_start)
            for batch in parquet.iter_batches(
                batch_size=limit, row_groups=[group_index]
            ):
                if skip >= batch.num_rows:
                    skip -= batch.num_rows
                    continue
                count = min(limit - len(rows), batch.num_rows - skip)
                rows.extend(batch.slice(skip, count).to_pylist())
                skip = 0
                if len(rows) >= limit:
                    break
            if len(rows) >= limit:
                break
            group_start = group_end
        return {
            "snapshot_id": snapshot_id,
            "table": table_name,
            "offset": offset,
            "limit": limit,
            "total_rows": total,
            "columns": parquet.schema_arrow.names,
            "rows": rows,
        }

    def list_methods(self, snapshot_id: str) -> list[dict[str, Any]]:
        self.ensure_initialized()
        return researchstore.methods_for_snapshot(snapshot_id)

    def list_metrics(self, snapshot_id: str) -> list[dict[str, Any]]:
        self.ensure_initialized()
        return researchstore.dataset_metrics(snapshot_id)

    def resolve_cohort(
        self, study_id: str, excluded_subject_ids: list[str] | None = None
    ) -> dict[str, Any]:
        self.ensure_initialized()
        if study_id in realstore.real_study_ids():
            return realanalysis._cohort(study_id, excluded_subject_ids)
        entity = researchstore.get_entity(study_id)
        if entity is None:
            if study_id == "STUDY-001":
                study = self.get_study_detail(study_id)
                cohort = study.get("cohort", {})
                subjects = researchstore.read_snapshot_table(SNAPSHOT_ID, "subjects")
                known = set(subjects["subject_id"].to_list())
                excluded = set(excluded_subject_ids or [])
                unknown = sorted(excluded - known)
                if unknown:
                    raise researchstore.ResearchValidation(
                        f"Unknown subject IDs: {', '.join(unknown)}"
                    )
                members = [item for item in cohort.get("subject_ids", []) if item not in excluded]
                return {"cohort": {**cohort, "subject_ids": members}, "n": len(members), "snapshot_id": SNAPSHOT_ID}
            raise researchstore.ResearchNotFound(f"Study {study_id} not found")
        cohort = researchstore.get_cohort(entity.get("cohort_id") or "")
        if cohort is None:
            raise researchstore.ResearchNotFound(f"Study {study_id} has no cohort")
        return researchstore.resolve_cohort(
            cohort, entity["dataset_snapshot_id"], excluded_subject_ids
        )

    def explore_longitudinal(
        self,
        study_id: str,
        metric_id: str,
        excluded_subject_ids: list[str] | None = None,
        reference: str = "RAW",
    ) -> dict[str, Any]:
        self.ensure_initialized()
        if study_id in realstore.real_study_ids():
            return realanalysis.explore(study_id, metric_id, excluded_subject_ids, reference)
        entity = researchstore.get_entity(study_id)
        if entity is None:
            raise researchstore.ResearchNotFound(
                "Longitudinal exploration is available for admitted research studies"
            )
        cohort = researchstore.get_cohort(entity.get("cohort_id") or "")
        if cohort is None:
            raise researchstore.ResearchNotFound(f"Study {study_id} has no cohort")
        return researchanalysis.explore(entity, cohort, metric_id, excluded_subject_ids, reference)

    def execute_analysis_run(self, study_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.ensure_initialized()
        if study_id in realstore.real_study_ids():
            return realanalysis.execute(
                study_id,
                payload["method_id"],
                payload["outcome_metric_id"],
                payload.get("excluded_subject_ids"),
                payload.get("parameters"),
            )
        entity = researchstore.get_entity(study_id)
        if entity is None:
            raise researchstore.ResearchNotFound(
                "Run analyses from a persisted research study"
            )
        if entity.get("state") == "ARCHIVED":
            raise researchstore.ResearchConflict("Archived studies cannot execute analyses")
        cohort = researchstore.get_cohort(entity.get("cohort_id") or "")
        if cohort is None:
            raise researchstore.ResearchNotFound(f"Study {study_id} has no cohort")
        plan = researchstore.get_plan(entity.get("analysis_plan_id") or "")
        return researchanalysis.execute(
            entity,
            cohort,
            plan,
            payload["method_id"],
            payload["outcome_metric_id"],
            payload.get("parameters"),
            payload.get("excluded_subject_ids"),
        )

    def execute_analysis_isolated(
        self, study_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        if payload.get("method_id") not in {
            "METH-REAL-TREND",
            "METH-REAL-RELIABILITY",
            "METH-REAL-SIGNAL-QA",
        }:
            return self.execute_analysis_run(study_id, payload)
        request = json.dumps(
            {"data_root": str(self.root), "study_id": study_id, "payload": payload}
        )
        process = subprocess.run(
            [sys.executable, "-m", "dynamis_science.desktop.worker"],
            input=request,
            text=True,
            capture_output=True,
            timeout=1800,
            cwd=Path(__file__).resolve().parents[2],
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        if process.returncode:
            try:
                error = json.loads(process.stderr)
                message = f"{error['type']}: {error['message']}"
            except (KeyError, ValueError):
                message = process.stderr.strip() or process.stdout.strip()
            raise RuntimeError(message or "The isolated scientific worker failed")
        try:
            return json.loads(process.stdout)
        except ValueError as error:
            raise RuntimeError("The isolated scientific worker returned invalid JSON") from error

    def promote_run_to_evidence(self, run_id: str) -> dict[str, Any]:
        self.ensure_initialized()
        if run_id.startswith("RUN-REAL-"):
            return realanalysis.promote(run_id)
        return researchanalysis.promote(run_id)

    def get_lineage_graph(self, artifact_id: str) -> dict[str, Any]:
        self.ensure_initialized()
        if artifact_id.startswith(("RUN-REAL-", "EVID-REAL-", "FIG-REAL-", "DS-REAL-", "SRC-", "COHORT-REAL-", "REPORT-REAL-")):
            return realstore.lineage_graph(artifact_id)
        if artifact_id.startswith(("RUN-U-", "EVID-U-", "FIG-U-", "STUDY-U-", "PROG-U-", "COHORT-U-", "PLAN-U-", "INV-U-", "RPT-", "PRJ-")):
            return researchstore.lineage(artifact_id)
        raise researchstore.ResearchNotFound(f"Lineage is unavailable for {artifact_id}")

    def get_report(self, study_id: str) -> dict[str, Any]:
        self.ensure_initialized()
        if study_id in realstore.real_study_ids():
            return realstore.get_report(study_id)
        if study_id.startswith(("STUDY-U-", "PROG-U-")):
            return researchstore.report_payload(study_id)
        if study_id == "STUDY-001":
            if not self.synthetic_available:
                raise researchstore.ResearchNotFound("The synthetic regression fixture is unavailable")
            return _read_json(ARTIFACT_DIR / "report.json", {})
        raise researchstore.ResearchNotFound(f"Report for {study_id} not found")

    def freeze_report(self, study_id: str) -> dict[str, Any]:
        self.ensure_initialized()
        return researchstore.freeze_report(study_id)

    def cite_report_artifact(
        self, study_id: str, artifact_id: str, section: str | None = None
    ) -> dict[str, Any]:
        self.ensure_initialized()
        return researchstore.cite_artifact(study_id, artifact_id, section)

    def export_report_html(
        self, study_id: str, target_path: str | os.PathLike[str], version: int | None = None
    ) -> Path:
        self.ensure_initialized()
        html = researchstore.export_html(study_id, version)
        path = Path(target_path).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(html, encoding="utf-8")
        return path

    def render_report_html(self, study_id: str, version: int | None = None) -> str:
        self.ensure_initialized()
        return researchstore.export_html(study_id, version)

    def list_signal_trials(
        self, snapshot_id: str, subject_id: str | None = None, activity: str | None = None
    ) -> list[dict[str, Any]]:
        self.ensure_initialized()
        snapshot = researchstore.get_snapshot(snapshot_id)
        if snapshot is None:
            raise researchstore.ResearchNotFound(f"Snapshot {snapshot_id} is not admitted")
        names = _table_names(snapshot)
        if "signal_trials" in names:
            table = "signal_trials"
        elif "force_traces" in names:
            table = "cmj_trials"
        else:
            return []
        frame = researchstore.read_snapshot_table(snapshot_id, table)
        if subject_id and "subject_id" in frame.columns:
            frame = frame.filter(pl.col("subject_id") == subject_id)
        if activity and "activity" in frame.columns:
            frame = frame.filter(pl.col("activity") == activity)
        return frame.to_dicts()

    def get_signal_waveform(
        self, snapshot_id: str, trial_id: str, max_points: int = 2500
    ) -> dict[str, Any]:
        self.ensure_initialized()
        if not 2 <= max_points <= 10000:
            raise ValueError("max_points must be between 2 and 10000")
        snapshot = researchstore.get_snapshot(snapshot_id)
        if snapshot is None:
            raise researchstore.ResearchNotFound(f"Snapshot {snapshot_id} is not admitted")
        signal_table = next(
            (name for name in ("force_signals", "force_traces") if name in _table_names(snapshot)),
            None,
        )
        if signal_table is None:
            raise researchstore.ResearchNotFound(f"Snapshot {snapshot_id} has no force signal table")
        path = _table_path(snapshot_id, signal_table, snapshot)
        frame = pl.scan_parquet(path).filter(pl.col("trial_id") == trial_id).collect()
        if frame.is_empty():
            raise researchstore.ResearchNotFound(f"Trial {trial_id} not found")
        time_column = next((name for name in ("time_s", "timestamp_ms", "sample") if name in frame.columns), None)
        signal_column = next(
            (name for name in ("force_z_n", "fz_n", "vertical_force_n", "fz", "magnitude_g") if name in frame.columns),
            next((name for name in frame.columns if name not in {"trial_id", "time_s", "plate", "sample"}), None),
        )
        if time_column is None or signal_column is None:
            raise researchstore.ResearchValidation(f"Trial {trial_id} has no plottable time series")
        groups = frame.partition_by("plate", maintain_order=True) if "plate" in frame.columns else [frame]
        series = []
        for group in groups:
            samples = group.sort(time_column).select(time_column, signal_column).to_dicts()
            if len(samples) > max_points:
                bucket_count = max_points // 2
                bucket_size = math.ceil(len(samples) / bucket_count)
                reduced = []
                for start in range(0, len(samples), bucket_size):
                    bucket = samples[start : start + bucket_size]
                    reduced.extend(
                        sorted(
                            (
                                min(bucket, key=lambda item: item[signal_column]),
                                max(bucket, key=lambda item: item[signal_column]),
                            ),
                            key=lambda item: item[time_column],
                        )
                    )
                samples = reduced
            series.append(
                {
                    "label": str(group["plate"][0]) if "plate" in group.columns else signal_column,
                    "time_column": time_column,
                    "value_column": signal_column,
                    "rows": samples,
                }
            )
        return {
            "snapshot_id": snapshot_id,
            "trial_id": trial_id,
            "columns": frame.columns,
            "series": series,
            "sample_count": sum(len(item["rows"]) for item in series),
            "source_rows": frame.height,
            "source_rows_bounded": True,
        }


def _read_json(path: Path, default: Any) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default


def _table_names(snapshot: dict[str, Any]) -> list[str]:
    return sorted(snapshot.get("tables", {})) or sorted(snapshot.get("row_counts", {}))


def _table_path(snapshot_id: str, table_name: str, snapshot: dict[str, Any]) -> Path:
    if snapshot.get("synthetic"):
        path = PARQUET_DIR / f"{table_name}.parquet"
    else:
        path = realstore.snapshots_dir() / snapshot_id / f"{table_name}.parquet"
    if not path.is_file():
        raise researchstore.ResearchNotFound(f"Parquet table {table_name} is unavailable")
    return path
