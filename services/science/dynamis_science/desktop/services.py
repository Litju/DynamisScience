"""In-process application facade shared by native workspaces and tests."""

from __future__ import annotations

import json
import math
import os
import sqlite3
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

import polars as pl
import pyarrow.parquet as pq

from .. import admission, dataworkspace, importer, realanalysis, realstore, researchanalysis, researchstore
from ..data_root import DataRootConfigurationError, data_root, ensure_layout, paths
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
            database = self.root / "research" / "research.db"
            connection = sqlite3.connect(
                f"{database.as_uri()}?mode=ro", uri=True, timeout=5
            )
            try:
                connection.execute("PRAGMA foreign_keys=ON")
                integrity = connection.execute("PRAGMA quick_check").fetchone()[0]
                foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
                journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
            finally:
                connection.close()
            if integrity != "ok" or foreign_keys or journal_mode.lower() != "wal":
                raise DataRootConfigurationError(
                    "Research database failed startup integrity checks "
                    f"(integrity={integrity}, foreign_key_violations={len(foreign_keys)}, "
                    f"journal_mode={journal_mode}). Use the Tools backup and restore workflow."
                )
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

    def get_project(self, project_id: str) -> dict[str, Any]:
        self.ensure_initialized()
        project = researchstore.get_project(project_id)
        if project is None:
            raise researchstore.ResearchNotFound(f"Project {project_id} not found")
        return project

    def create_project(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.ensure_initialized()
        return researchstore.create_project(
            payload["title"],
            payload.get("description", ""),
            payload.get("objectives", []),
            payload.get("dataset_snapshot_ids", []),
        )

    def update_project(self, project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.ensure_initialized()
        patch = {key: value for key, value in payload.items() if key != "base_version"}
        return researchstore.update_project(project_id, patch, payload.get("base_version"))

    def archive_project(self, project_id: str, archived: bool = True) -> dict[str, Any]:
        self.ensure_initialized()
        return researchstore.set_project_archived(project_id, archived)

    def project_history(self, project_id: str) -> list[dict[str, Any]]:
        self.ensure_initialized()
        return researchstore.project_history(project_id)

    def create_study(self, project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.ensure_initialized()
        return researchstore.create_study(project_id, payload)

    def create_monitoring_program(self, project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.ensure_initialized()
        return researchstore.create_monitoring_program(project_id, payload)

    def update_study(
        self, study_id: str, payload: dict[str, Any], base_version: int | None = None
    ) -> dict[str, Any]:
        self.ensure_initialized()
        entity = researchstore.get_entity(study_id)
        if entity is None:
            raise researchstore.ResearchNotFound(f"Research object {study_id} not found")
        if entity.get("kind") == "MONITORING":
            return self.update_monitoring_program(study_id, payload, base_version)
        patch = {key: value for key, value in payload.items() if key != "base_version"}
        question = dict(patch.get("question", {}))
        if "research_question" in patch:
            question["statement"] = patch["research_question"]
        for key in ("estimand", "population"):
            if key in patch:
                question[key] = patch[key]
        if question:
            patch["question"] = question
        if isinstance(patch.get("hypotheses"), list) and patch["hypotheses"]:
            patch["hypotheses"] = researchstore._normalise_hypotheses(
                patch["hypotheses"], entity["question"]["id"],
                patch.get("research_question", entity.get("research_question", "")),
            )
        return researchstore.update_entity(study_id, patch, base_version)

    def update_monitoring_program(
        self, program_id: str, payload: dict[str, Any], base_version: int | None = None
    ) -> dict[str, Any]:
        self.ensure_initialized()
        entity = researchstore.get_entity(program_id)
        if entity is None or entity.get("kind") != "MONITORING":
            raise researchstore.ResearchNotFound(f"Monitoring program {program_id} not found")
        schedule = dict(entity.get("schedule", {}))
        start_week = int(payload.get("start_week", schedule.get("start_week", 1)))
        weeks = int(payload.get("weeks", schedule.get("weeks", 1)))
        if start_week < 1 or weeks < 1 or weeks > 104:
            raise researchstore.ResearchValidation("start_week must be ≥ 1 and weeks between 1 and 104")
        points = [
            {"index": index + 1, "week": start_week + index, "label": f"Week {start_week + index}", "planned": True}
            for index in range(weeks)
        ]
        schedule.update(start_week=start_week, weeks=weeks, points=points, future_measurements=points)
        patch = {
            key: payload[key]
            for key in ("title", "short_title", "research_question", "population", "eligibility", "exclusions")
            if key in payload
        }
        question = dict(entity.get("question", {}))
        if "research_question" in payload:
            question["statement"] = str(payload["research_question"]).strip()
            question["time_horizon"] = f"{weeks} planned weekly measurements starting at week {start_week}."
        if "population" in payload:
            question["population"] = payload["population"]
        patch.update(question=question, schedule=schedule)
        return researchstore.update_entity(program_id, patch, base_version)

    def transition_study(self, study_id: str, state: str) -> dict[str, Any]:
        self.ensure_initialized()
        return researchstore.transition_entity(study_id, state)

    def study_history(self, study_id: str) -> list[dict[str, Any]]:
        self.ensure_initialized()
        return researchstore.entity_history(study_id)

    def create_cohort(self, study_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.ensure_initialized()
        definition = {
            key: payload[key]
            for key in (
                "include_subject_ids", "exclude_subject_ids", "rules",
                "min_metric_observations", "activity", "snapshot_id",
            )
            if key in payload
        }
        return researchstore.create_cohort(
            study_id,
            payload["name"],
            definition,
            bool(payload.get("freeze", False)),
            payload.get("base_version"),
            payload.get("parent_id"),
        )

    def update_cohort(self, cohort_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.ensure_initialized()
        patch = {key: value for key, value in payload.items() if key != "base_version"}
        return researchstore.update_cohort(cohort_id, patch, payload.get("base_version"))

    def freeze_cohort(self, cohort_id: str) -> dict[str, Any]:
        self.ensure_initialized()
        return researchstore.freeze_cohort(cohort_id)

    def fork_cohort(self, cohort_id: str, name: str | None = None) -> dict[str, Any]:
        self.ensure_initialized()
        return researchstore.fork_cohort(cohort_id, name)

    def cohort_history(self, cohort_id: str) -> list[dict[str, Any]]:
        self.ensure_initialized()
        return researchstore.cohort_history(cohort_id)

    def list_cohorts(self, study_id: str) -> list[dict[str, Any]]:
        self.ensure_initialized()
        return researchstore.list_cohorts(study_id)

    def get_cohort(self, cohort_id: str) -> dict[str, Any]:
        self.ensure_initialized()
        cohort = researchstore.get_cohort(cohort_id)
        if cohort is None:
            raise researchstore.ResearchNotFound(f"Cohort {cohort_id} not found")
        return cohort

    def create_plan(self, study_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        self.ensure_initialized()
        return researchstore.create_plan(study_id, payload)

    def update_plan(self, plan_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.ensure_initialized()
        patch = {key: value for key, value in payload.items() if key != "base_version"}
        return researchstore.update_plan(plan_id, patch, payload.get("base_version"))

    def freeze_plan(self, plan_id: str) -> dict[str, Any]:
        self.ensure_initialized()
        return researchstore.freeze_plan(plan_id)

    def fork_plan(self, plan_id: str, name: str | None = None) -> dict[str, Any]:
        self.ensure_initialized()
        return researchstore.fork_plan(plan_id, name)

    def plan_history(self, plan_id: str) -> list[dict[str, Any]]:
        self.ensure_initialized()
        return researchstore.plan_history(plan_id)

    def list_plans(self, study_id: str) -> list[dict[str, Any]]:
        self.ensure_initialized()
        return researchstore.list_plans(study_id)

    def get_plan(self, plan_id: str) -> dict[str, Any]:
        self.ensure_initialized()
        plan = researchstore.get_plan(plan_id)
        if plan is None:
            raise researchstore.ResearchNotFound(f"Analysis plan {plan_id} not found")
        return plan

    def list_admission_sources(self) -> list[dict[str, Any]]:
        self.ensure_initialized()
        return admission.list_sources()

    def get_admission_source(self, source_id: str) -> dict[str, Any]:
        self.ensure_initialized()
        source = admission.get_source(source_id)
        if source is None:
            raise researchstore.ResearchNotFound(f"Source {source_id} not found")
        return source

    def register_admission_source(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.ensure_initialized()
        return admission.register_source(payload)

    def verify_source_rights(self, source_id: str, verifier: str = "desktop") -> dict[str, Any]:
        self.ensure_initialized()
        return admission.verify_rights(source_id, verifier)

    def ingest_local_source_file(
        self, source_id: str, file_path: str | os.PathLike[str]
    ) -> dict[str, Any]:
        self.ensure_initialized()
        return admission.ingest_source_file(source_id, file_path)

    def list_source_artifacts(self) -> list[dict[str, Any]]:
        self.ensure_initialized()
        return admission.list_source_artifacts()

    def list_admission_instruments(self) -> list[dict[str, Any]]:
        self.ensure_initialized()
        return admission.list_instruments()

    def register_admission_instrument(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.ensure_initialized()
        return admission.register_instrument(payload)

    def list_admission_protocols(self) -> list[dict[str, Any]]:
        self.ensure_initialized()
        return admission.list_protocols()

    def register_admission_protocol(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.ensure_initialized()
        return admission.register_protocol(payload)

    def validate_source_artifact(
        self, artifact_id: str, family: str, metadata: dict[str, Any]
    ) -> dict[str, Any]:
        self.ensure_initialized()
        artifact = admission.get_source_artifact(artifact_id)
        if artifact is None:
            raise researchstore.ResearchNotFound(f"Source artifact {artifact_id} not found")
        if family == "CMJ_FORCE_PLATFORM":
            return admission.validate_cmj(artifact, metadata)
        if family == "SPRINT_TIMING":
            return admission.validate_sprint(artifact, metadata)
        raise researchstore.ResearchValidation(f"Unsupported measurement family: {family}")

    def admit_source_artifact(
        self, artifact_id: str, family: str, metadata: dict[str, Any]
    ) -> dict[str, Any]:
        self.ensure_initialized()
        return admission.admit_artifact(artifact_id, family, metadata)

    def list_admission_records(self) -> list[dict[str, Any]]:
        self.ensure_initialized()
        return admission.list_admission_records()

    def get_admission_record(self, record_id: str) -> dict[str, Any]:
        self.ensure_initialized()
        record = admission.get_admission_record(record_id)
        if record is None:
            raise researchstore.ResearchNotFound(f"Admission record {record_id} not found")
        return record

    def list_admission_quality(self) -> list[dict[str, Any]]:
        self.ensure_initialized()
        return admission.list_quality()

    def get_admission_quality(self, quality_id: str) -> dict[str, Any]:
        self.ensure_initialized()
        quality = admission.get_quality(quality_id)
        if quality is None:
            raise researchstore.ResearchNotFound(f"Quality assessment {quality_id} not found")
        return quality

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
            if item.get("id") != SNAPSHOT_ID or self.synthetic_available
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
        if snapshot_id == SNAPSHOT_ID and not self.synthetic_available:
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
        if snapshot_id == SNAPSHOT_ID and not self.synthetic_available:
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

    def scientific_library(self) -> dict[str, Any]:
        self.ensure_initialized()
        from ..scientific_library import get_scientific_library

        return get_scientific_library()

    def resolve_cohort(
        self,
        study_id: str,
        excluded_subject_ids: list[str] | None = None,
        cohort_id: str | None = None,
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
        cohort = researchstore.get_cohort(cohort_id or entity.get("cohort_id") or "")
        if cohort is None:
            raise researchstore.ResearchNotFound(f"Study {study_id} has no cohort")
        if cohort.get("study_id") != study_id:
            raise researchstore.ResearchValidation("The selected cohort belongs to a different study")
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
        """Isolate the real-data MixedLM and signal analyses from the GUI process."""
        if payload.get("method_id") not in {
            "METH-REAL-TREND",
            "METH-REAL-RELIABILITY",
            "METH-REAL-SIGNAL-QA",
        }:
            return self.execute_analysis_run(study_id, payload)
        return self._run_isolated_worker(
            {
                "operation": "analysis",
                "data_root": str(self.root),
                "study_id": study_id,
                "payload": payload,
            }
        )

    def run_independent_qualification(self) -> list[dict[str, Any]]:
        self.ensure_initialized()
        return self._run_isolated_worker(
            {"operation": "real_qualification", "data_root": str(self.root)}
        )

    def _run_isolated_worker(self, request: dict[str, Any]) -> Any:
        encoded_request = json.dumps(request)
        if getattr(sys, "frozen", False):
            self.ensure_initialized()
            request_path = self.root / "tmp" / f"worker-{uuid.uuid4().hex}-request.json"
            response_path = self.root / "tmp" / f"worker-{uuid.uuid4().hex}-response.json"
            request_path.write_text(encoded_request, encoding="utf-8")
            try:
                process = subprocess.run(
                    [sys.executable, "--worker", str(request_path), str(response_path)],
                    capture_output=True,
                    text=True,
                    timeout=1800,
                    cwd=self.root,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
                output = response_path.read_text(encoding="utf-8") if response_path.is_file() else ""
                if process.returncode:
                    try:
                        error = json.loads(output)
                        message = f"{error['type']}: {error['message']}"
                    except (KeyError, ValueError):
                        message = process.stderr.strip() or "The isolated scientific worker failed"
                    raise RuntimeError(message)
                try:
                    return json.loads(output)
                except ValueError as error:
                    raise RuntimeError("The isolated scientific worker returned invalid JSON") from error
            finally:
                request_path.unlink(missing_ok=True)
                response_path.unlink(missing_ok=True)
        process = subprocess.run(
            [sys.executable, "-m", "dynamis_science.desktop.worker"],
            input=encoded_request,
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

    def update_report(
        self, study_id: str, payload: dict[str, Any], base_version: int | None = None
    ) -> dict[str, Any]:
        self.ensure_initialized()
        return researchstore.update_report(study_id, payload, base_version)

    def freeze_report(self, study_id: str) -> dict[str, Any]:
        self.ensure_initialized()
        return researchstore.freeze_report(study_id)

    def report_versions(self, study_id: str) -> list[dict[str, Any]]:
        self.ensure_initialized()
        return researchstore.report_versions(study_id)

    def get_report_version(self, study_id: str, version: int) -> dict[str, Any]:
        self.ensure_initialized()
        report = researchstore.get_report_version(study_id, version)
        if report is None:
            raise researchstore.ResearchNotFound(
                f"Frozen report version {version} not found for {study_id}"
            )
        return report

    def list_investigations(self, study_id: str) -> list[dict[str, Any]]:
        self.ensure_initialized()
        if study_id == "STUDY-001":
            records = _read_json(ARTIFACT_DIR / "investigations.json", [])
            return [record for record in records if record.get("study_id") == study_id]
        if study_id in realstore.real_study_ids():
            return [
                record
                for record in realanalysis.list_investigations()
                if record.get("study_id") == study_id
            ]
        return researchstore.list_investigations(study_id)

    def create_investigation(
        self, study_id: str, title: str, blocks: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        self.ensure_initialized()
        researchstore.validate_investigation_blocks(blocks or [])
        return researchstore.create_investigation(study_id, title, blocks)

    def update_investigation(
        self,
        investigation_id: str,
        blocks: list[dict[str, Any]],
        base_version: int,
        title: str | None = None,
    ) -> dict[str, Any]:
        self.ensure_initialized()
        researchstore.validate_investigation_blocks(blocks)
        if investigation_id.startswith("INV-U-"):
            return researchstore.update_investigation_research(
                investigation_id, blocks, base_version, title
            )
        if investigation_id.startswith("INV-REAL-"):
            try:
                return realanalysis.update_investigation(
                    investigation_id, blocks, base_version
                )
            except ValueError as error:
                raise researchstore.ResearchConflict(str(error)) from error
        raise researchstore.ResearchValidation(
            "The bundled synthetic investigation is read-only"
        )

    def fork_investigation(self, investigation_id: str) -> dict[str, Any]:
        self.ensure_initialized()
        if not investigation_id.startswith("INV-U-"):
            raise researchstore.ResearchValidation(
                "Only authored research investigations can be forked"
            )
        return researchstore.fork_investigation(investigation_id)

    def cite_report_artifact(
        self, study_id: str, artifact_id: str, section: str | None = None
    ) -> dict[str, Any]:
        self.ensure_initialized()
        if study_id in realstore.real_study_ids():
            return realstore.cite(study_id, artifact_id, section)
        return researchstore.cite_artifact(study_id, artifact_id, section)

    def uncite_report_artifact(self, study_id: str, artifact_id: str) -> dict[str, Any]:
        self.ensure_initialized()
        if study_id in realstore.real_study_ids():
            return realstore.uncite(study_id, artifact_id)
        return researchstore.uncite_artifact(study_id, artifact_id)

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
        elif "trace_index" in names:
            table = "trace_index"
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
        channels = [c for c in ("force_z_n", "force_combined_n", "force_left_n", "force_right_n") if c in frame.columns]
        signal_column = next(
            (name for name in ("force_z_n", "fz_n", "vertical_force_n", "fz", "magnitude_g") if name in frame.columns),
            next((name for name in frame.columns if name not in {"trial_id", "time_s", "plate", "sample"}), None),
        )
        if time_column is None or signal_column is None:
            raise researchstore.ResearchValidation(f"Trial {trial_id} has no plottable time series")
        if "plate" in frame.columns:
            plan = [(str(g["plate"][0]), g, signal_column) for g in frame.partition_by("plate", maintain_order=True)]
        elif len(channels) > 1:  # sample-level recordings with several force channels: one series per channel
            plan = [(c.replace("force_", "").replace("_n", ""), frame, c) for c in channels]
        else:
            plan = [(signal_column, frame, signal_column)]
        series = []
        for label, group, signal_column in plan:
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
                    "label": label,
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

    # ---- Data Workspace (read-only access to admitted tables)
    def _workspace_tables(self, snapshot_id: str) -> dict[str, Path]:
        self.ensure_initialized()
        snapshot = researchstore.get_snapshot(snapshot_id)
        if snapshot is None:
            raise researchstore.ResearchNotFound(f"Snapshot {snapshot_id} is not admitted")
        if snapshot_id == SNAPSHOT_ID and not self.synthetic_available:
            raise researchstore.ResearchNotFound("The synthetic regression fixture is unavailable")
        return {name: _table_path(snapshot_id, name, snapshot) for name in _table_names(snapshot)}

    def table_profile(self, snapshot_id: str, table: str) -> dict[str, Any]:
        tables = self._workspace_tables(snapshot_id)
        if table not in tables:
            raise researchstore.ResearchNotFound(f"Table {table} not found")
        return dataworkspace.profile(tables[table])

    def query_table(self, snapshot_id: str, table: str, offset: int = 0, limit: int = 200,
                    filters: list[dict[str, Any]] | None = None, sort: str | None = None,
                    descending: bool = False, columns: list[str] | None = None) -> dict[str, Any]:
        tables = self._workspace_tables(snapshot_id)
        if table not in tables:
            raise researchstore.ResearchNotFound(f"Table {table} not found")
        return dataworkspace.page(tables[table], offset, limit, filters, sort, descending, columns)

    def run_readonly_query(self, snapshot_id: str, sql: str, limit: int = 1000) -> dict[str, Any]:
        return dataworkspace.query(self._workspace_tables(snapshot_id), sql, limit)

    def dataset_inspector(self, snapshot_id: str) -> dict[str, Any]:
        """Rights, QC, exclusions, instruments, provenance and import receipts for one snapshot."""
        self.ensure_initialized()
        snapshot = researchstore.get_snapshot(snapshot_id)
        if snapshot is None:
            raise researchstore.ResearchNotFound(f"Snapshot {snapshot_id} is not admitted")
        record = snapshot.get("admission") or {}
        quality = admission.get_quality(record.get("quality_assessment_id", "")) if record else None
        artifact_id = record.get("source_artifact_id")
        return {
            "id": snapshot_id, "label": snapshot.get("label"), "synthetic": bool(snapshot.get("synthetic")),
            "real_data": bool(snapshot.get("real_data")), "admission_class": snapshot.get("admission_class"),
            "source": snapshot.get("source", {}), "admission": record, "quality": quality,
            "provenance": snapshot.get("provenance", {}), "checksums": snapshot.get("checksums", {}),
            "row_counts": snapshot.get("row_counts", {}),
            "receipts": [r for r in importer.list_receipts() if artifact_id and r.get("source_artifact_id") == artifact_id],
            "used_by_studies": next((d.get("used_by_studies", []) for d in researchstore.dataset_catalogue() if d["id"] == snapshot_id), []),
        }

    def performance_page_data(self, page: str) -> dict[str, Any]:
        self.ensure_initialized()
        from .. import performance

        if page == "context":
            return {"context": performance.context()}
        if page == "today":
            return {"today": performance.today(), "athletes": performance.athletes()}
        if page == "athlete":
            return {"athletes": performance.athletes()}
        if page == "plan":
            return {"plan": performance.get_plan()}
        if page == "monitor":
            return {"load": performance.load_overview(), "movement": performance.movement()}
        if page == "test":
            return {"tests": performance.tests()}
        if page == "research":
            return {
                "research": performance.research_link(),
                "units": performance.units(),
                "metrics": self.list_metrics("DS-SYNTH-001"),
            }
        if page == "report":
            return {"reports": performance.list_reports(), "athletes": performance.athletes()}
        if page == "match":
            return {"movement": performance.movement(), "roster": self.performance_match_roster()}
        raise ValueError(f"Unknown Performance OS workspace: {page}")

    def performance_athlete(self, athlete_id: str) -> dict[str, Any]:
        self.ensure_initialized()
        from .. import performance

        return performance.athlete_detail(athlete_id)

    def performance_tracking(self, player_id: str, limit: int = 2500) -> dict[str, Any]:
        self.ensure_initialized()
        if not 2 <= limit <= 10000:
            raise ValueError("limit must be between 2 and 10000")
        path = PARQUET_DIR / "match_tracking.parquet"
        frame = (
            pl.scan_parquet(path)
            .filter(pl.col("player_id") == player_id)
            .sort("time_s")
            .limit(limit)
            .collect()
        )
        if frame.is_empty():
            raise researchstore.ResearchNotFound(f"Tracking data for {player_id} is unavailable")
        return {"player_id": player_id, "rows": frame.to_dicts(), "source": "DS-SYNTH-001 / match_tracking.parquet"}

    def performance_match_roster(self) -> dict[str, Any]:
        self.ensure_initialized()
        tracking = pl.scan_parquet(PARQUET_DIR / "match_tracking.parquet")
        pose = pl.scan_parquet(PARQUET_DIR / "match_pose.parquet")
        return {
            "players": tracking.select("player_id", "team").unique().sort("player_id").collect().to_dicts(),
            "pose_players": pose.select("athlete_id").unique().sort("athlete_id").collect()["athlete_id"].to_list(),
            "events": pl.scan_parquet(PARQUET_DIR / "match_events.parquet").limit(100).collect().to_dicts(),
            "source": "DS-SYNTH-001 / 10 Hz synthetic match segment",
        }

    def performance_match_frame(self, frame_number: int, athlete_id: str) -> dict[str, Any]:
        self.ensure_initialized()
        if not 0 <= frame_number < 1800:
            raise ValueError("frame_number must be between 0 and 1799")
        tracking = (
            pl.scan_parquet(PARQUET_DIR / "match_tracking.parquet")
            .filter(pl.col("frame") == frame_number)
            .limit(24)
            .collect()
            .to_dicts()
        )
        pose = (
            pl.scan_parquet(PARQUET_DIR / "match_pose.parquet")
            .filter((pl.col("frame") == frame_number) & (pl.col("athlete_id") == athlete_id))
            .limit(32)
            .collect()
            .to_dicts()
        )
        return {"frame": frame_number, "time_s": frame_number / 10, "tracking": tracking, "pose": pose}

    def performance_log_session(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.ensure_initialized()
        from .. import performance

        return performance.log_session(performance.SessionLog.model_validate(payload))

    def performance_add_athlete_note(
        self, athlete_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        self.ensure_initialized()
        from .. import performance

        return performance.add_athlete_note(
            athlete_id, performance.AthleteNote.model_validate(payload)
        )

    def performance_update_plan(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.ensure_initialized()
        from .. import performance

        return performance.update_plan(performance.PlanUpdate.model_validate(payload))

    def performance_publish_plan(self) -> dict[str, Any]:
        self.ensure_initialized()
        from .. import performance

        return performance.publish_plan()

    def performance_run_reliability(self) -> dict[str, Any]:
        self.ensure_initialized()
        from .. import performance

        return performance.run_reliability()

    def performance_create_report(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.ensure_initialized()
        from .. import performance

        return performance.create_report(performance.ReportRequest.model_validate(payload))

    def performance_freeze_report(self, report_id: str) -> dict[str, Any]:
        self.ensure_initialized()
        from .. import performance

        return performance.freeze_report(report_id)

    def performance_render_report(self, report: dict[str, Any]) -> str:
        from .. import performance

        return performance.render_report(report)

    def performance_export_report(self, report_id: str, target_path: str | os.PathLike[str]) -> Path:
        self.ensure_initialized()
        from .. import performance

        html = performance.export_report(report_id)
        path = Path(target_path).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(html, encoding="utf-8")
        return path

    def verify_research_database(self) -> dict[str, Any]:
        self.ensure_initialized()
        from scripts.sqlite_recovery import inspect_database

        return inspect_database(self.root / "research" / "research.db")

    def backup_research_database(self) -> dict[str, Any]:
        self.ensure_initialized()
        from datetime import UTC, datetime

        from scripts.sqlite_recovery import backup_database

        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        target = self.root / "backups" / f"research-{stamp}-{uuid.uuid4().hex[:8]}.sqlite3"
        result = backup_database(target)
        return {"path": str(target), **result}

    def rehearse_research_restore(
        self, backup_path: str | os.PathLike[str]
    ) -> dict[str, Any]:
        self.ensure_initialized()
        from scripts.sqlite_recovery import restore_database

        target = self.root / "tmp" / f"restore-{uuid.uuid4().hex}"
        return restore_database(Path(backup_path).expanduser(), target)


def _read_json(path: Path, default: Any) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default


def _table_names(snapshot: dict[str, Any]) -> list[str]:
    return sorted(snapshot.get("tables", {})) or sorted(snapshot.get("row_counts", {}))


def _table_path(snapshot_id: str, table_name: str, snapshot: dict[str, Any]) -> Path:
    if snapshot.get("admitted_source"):
        path = paths()["admitted"] / snapshot_id / f"{table_name}.parquet"
    elif snapshot.get("synthetic"):
        path = PARQUET_DIR / f"{table_name}.parquet"
    else:
        path = realstore.snapshots_dir() / snapshot_id / f"{table_name}.parquet"
    if not path.is_file():
        raise researchstore.ResearchNotFound(f"Parquet table {table_name} is unavailable")
    return path
