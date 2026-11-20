"""Dated research read models and immutable contextual Results."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta
from pathlib import Path
from statistics import mean
from typing import Literal

import polars as pl
from pydantic import BaseModel, ConfigDict

from . import admission, experiments, importer, longitudinal, measurement_trust
from . import researchstore as store, training_context as context
from .data_root import paths

METHOD = "training-context-timeline@1"
ASSESSMENT_TABLES = {"cmj_trials"}
KINDS = ("TRAINING", "WELLNESS", "ASSESSMENT", "PLAN", "VISIT")
LIMITATIONS = [
    "The timeline shows temporal context. It cannot establish whether training caused a performance change.",
    "Calendar-day assessments have unknown within-day order. Same-day exposures stay outside the comparison window.",
    "Missing or unrecorded exposures cannot be treated as zero. Source summaries are reported separately.",
]


class TimelineQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subject_id: str | None = None
    cohort_id: str | None = None
    source_versions: list[str] | None = None
    metric_id: str | None = None
    kind: Literal["TRAINING", "WELLNESS", "ASSESSMENT", "PLAN", "VISIT"] | None = None
    start: date | None = None
    end: date | None = None
    week_one: date | None = None
    local_offset: str = "+00:00"


def _calendar(query: TimelineQuery):
    try:
        if len(query.local_offset) != 6 or query.local_offset[0] not in "+-" or query.local_offset[3] != ":":
            raise ValueError
        hours, minutes = int(query.local_offset[1:3]), int(query.local_offset[4:])
        if not (0 <= minutes < 60 and 0 <= hours <= 14 and (hours < 14 or minutes == 0)):
            raise ValueError
        offset = datetime.fromisoformat(f"2000-01-01T00:00:00{query.local_offset}").tzinfo
    except ValueError as error:
        raise store.ResearchValidation("Use a fixed UTC offset such as -03:00 for study calendar alignment.") from error
    if query.start and query.end and query.start > query.end:
        raise store.ResearchValidation("The start date must be on or before the end date.")
    return offset


def _rights_signature(source: dict) -> dict:
    keys = ("id", "rights_status", "license_or_agreement", "permitted_uses",
            "redistribution_restrictions", "privacy_status", "retention_limitations")
    return {key: source[key] for key in keys}


def _performance_source(snapshot: dict, table: str) -> dict:
    record = snapshot["admission"]
    source = context._rights(record["source_id"])
    pinned = snapshot["source"]
    if (source["rights_status"] != snapshot["rights_status"]
            or source["license_or_agreement"] != pinned["license"]["id"]
            or source["permitted_uses"] != pinned["permitted_uses"]
            or source["privacy_status"] != pinned["privacy"]["classification"]
            or source["redistribution_restrictions"] != pinned["redistribution_restrictions"]):
        raise store.ResearchValidation("Performance data rights differ from the admitted source.")
    artifact = admission.get_source_artifact(record["source_artifact_id"])
    quality = admission.get_quality(record["quality_assessment_id"])
    if (not artifact or artifact["source_id"] != source["id"]
            or importer._sha256(Path(artifact["stored_path"])) != artifact["content_hash_sha256"]):
        raise store.ResearchValidation("The performance source artifact failed its checksum check.")
    if not quality or quality["source_artifact_id"] != artifact["id"] or quality["status"] not in importer.ADMITTABLE:
        raise store.ResearchValidation("Performance source QC is unavailable.")
    expected = measurement_trust._parquet_check(snapshot, table)
    originals = []
    for item in importer.list_receipts():
        if item["source_artifact_id"] == artifact["id"]:
            if importer._sha256(Path(item["raw_copy"])) != item["raw_sha256"]:
                raise store.ResearchValidation("The retained performance export failed its checksum check.")
            originals.append({"filename": item["raw_filename"], "sha256": item["raw_sha256"],
                              "quarantined": item["row_quarantine"]["count"]})
    return {"snapshot_id": snapshot["id"], "artifact_id": artifact["id"], "source": source,
            "artifact_sha256": artifact["content_hash_sha256"], "parquet_sha256": expected,
            "retained_exports": originals, "quality_id": quality["id"], "quality_status": quality["status"],
            "units": snapshot["admission_metadata"].get("units", {}),
            "height_calculation": snapshot["admission_metadata"].get("jump_height_provenance"),
            "instruments": snapshot["provenance"].get("instrument_metadata", []),
            "protocols": snapshot["provenance"].get("protocol_metadata", [])}


def _assessment_rows(revision: dict, metric: dict | None, subjects: list[str]) -> tuple[list[dict], dict, list[str]]:
    if not metric:
        return [], {}, ["This revision has no supported dated performance outcome."]
    table, column = metric["table"], metric["column"]
    snapshot = revision["snapshot"]
    analytical_sha = measurement_trust._parquet_check(snapshot, table)
    sources = [_performance_source(item, table) for item in revision["inputs"] if table in item["tables"]]
    lookup = {item["artifact_id"]: item for item in sources}
    frame = store.read_snapshot_table(snapshot["id"], table).filter(pl.col("subject_id").is_in(subjects))
    diagnostics = {"snapshot_id": snapshot["id"], "parquet_sha256": analytical_sha, "sources": sources}
    needed = {"session_id", "trial_id", "source_artifact_id", "date", column}
    if needed - set(frame.columns):
        return [], diagnostics, ["Assessment alignment requires a recorded date, visit and trial identity."]
    output, undated = [], 0
    duplicates = set(frame.filter(pl.col("trial_id").is_duplicated())["trial_id"])
    for group in frame.partition_by(["subject_id", "session_id"]):
        trials = group.to_dicts()
        subject, session = trials[0]["subject_id"], trials[0]["session_id"]
        dates = {str(trial["date"]) for trial in trials}
        try:
            day = date.fromisoformat(next(iter(dates))) if len(dates) == 1 else None
        except ValueError:
            day = None
        if not day or not session:
            undated += 1
            continue
        facts = {}
        issues = set()
        values = []
        trial_details = []
        for trial in trials:
            source = lookup.get(trial["source_artifact_id"])
            sample = trial.get(column)
            quality = trial.get("quality_state") or "NOT_RECORDED"
            if not trial["trial_id"] or trial["trial_id"] in duplicates:
                issues.add("MISSING_OR_REUSED_TRIAL_ID")
            if quality not in {"NOT_RECORDED", "VALID"}:
                issues.add("TRIAL_QC_EXCLUDED")
            elif not isinstance(sample, (int, float)) or not math.isfinite(sample):
                issues.add("MISSING_OUTCOME")
            else:
                values.append(sample)
            trial_details.append({"trial_id": trial["trial_id"],
                                  "value": sample if isinstance(sample, (int, float)) and math.isfinite(sample) else None,
                                  "quality": quality, "artifact_id": trial["source_artifact_id"]})
            if not source:
                issues.add("UNRESOLVED_TRIAL_SOURCE")
                continue
            if source["units"].get("distance") != "cm" and column == "jump_height_cm":
                issues.add("HEIGHT_UNIT_NOT_DOCUMENTED")
            if any(item["quarantined"] for item in source["retained_exports"]):
                issues.add("SOURCE_QUARANTINED_ROWS")
            protocol = next((item for item in source["protocols"] if item["id"] == trial.get("protocol_id")), None)
            instrument = next((item for item in source["instruments"] if item["id"] == trial.get("instrument_id")), None)
            height = source["height_calculation"] if column == "jump_height_cm" else None
            for key, value in {"protocol": protocol, "instrument": instrument, "sampling_hz": trial.get("sampling_hz"),
                               "rights_status": source["source"]["rights_status"], "height_calculation": height}.items():
                facts.setdefault(key, {})[store._canonical(value)] = value
        if any(len(options) != 1 for options in facts.values()):
            issues.add("MIXED_ACQUISITION")
        acquisition = {key: next(iter(options.values())) if len(options) == 1 else None for key, options in facts.items()}
        if not acquisition.get("instrument") or not acquisition.get("protocol"):
            issues.add("ACQUISITION_NOT_DOCUMENTED")
        instrument = acquisition.get("instrument") or {}
        expected_calibration = "SIMULATED" if acquisition.get("rights_status") == "FIXTURE_ONLY" else "CALIBRATED"
        if instrument and instrument.get("calibration_status") != expected_calibration:
            issues.add("CALIBRATION_NOT_ESTABLISHED")
        if (column == "jump_height_cm" and acquisition.get("rights_status") == "VERIFIED"
                and not acquisition.get("height_calculation")):
            issues.add("HEIGHT_CALCULATION_NOT_DOCUMENTED")
        artifacts = sorted({trial["source_artifact_id"] or "" for trial in trials})
        weeks = {trial.get("week") for trial in trials}
        week = next(iter(weeks)) if len(weeks) == 1 else None
        week = int(week) if isinstance(week, (int, float)) and math.isfinite(week) and week == int(week) else None
        output.append({
            "id": store._digest([revision["id"], subject, session, metric["id"]]), "kind": "ASSESSMENT",
            "subject_id": subject, "session_id": session, "date": day.isoformat(), "week": week, "day_precision": True,
            "value": mean(values) if values and not issues else None, "n_trials": len(trials),
            "valid_trials": len(values), "aggregation": "Arithmetic mean of complete eligible trials",
            "unit": metric["unit"], "measure": metric["label"], "status": "OBSERVED" if not issues else "UNQUALIFIED",
            "source_name": ", ".join(sorted({lookup[item]["source"]["name"] for item in artifacts if item in lookup})),
            "artifact_ids": artifacts, "quality": sorted(issues), "trials": trial_details, "acquisition": acquisition,
            "data_revision_id": revision["id"],
        })
    notes = [f"{undated} assessment visits lack a usable unambiguous calendar date or visit identity."] if undated else []
    return output, diagnostics, notes


def _experiment_rows(workspace: str, subjects: list[str], base: str, query: TimelineQuery,
                     conflicting_weeks: set[str]) -> tuple[list[dict], list[str]]:
    events, notes = [], []
    for investigation in longitudinal.individual_investigations(workspace):
        subject = investigation["scope"]["subject_id"]
        if subject not in subjects:
            continue
        relevant = [plan for plan in investigation.get("experiment_protocols", [])
                    if context.anchor_id(context.workspace_revision(workspace, plan["data_revision_id"])[1]) == base]
        if not relevant:
            continue
        plan = relevant[-1]
        protocol_version = plan["version"]
        timeline = experiments.timeline(investigation["id"], protocol_version, investigation=investigation)
        origin = f"{investigation['title']} · protocol v{protocol_version}"
        binding = {"subject_id": subject, "source_name": origin, "investigation_id": investigation["id"],
                   "investigation_version": investigation["version"], "protocol_version": protocol_version,
                   "protocol_revision_id": plan["data_revision_id"], "amendment_reason": plan["amendment_reason"]}
        if query.week_one and plan["axis"] == "week" and subject not in conflicting_weeks:
            for period in plan["periods"]:
                start = query.week_one + timedelta(weeks=period["start"] - 1)
                end = query.week_one + timedelta(weeks=period["end"]) - timedelta(days=1)
                events.append({**binding, "kind": "PLAN", "status": "PLANNED", "day_precision": True,
                               "date": start.isoformat(), "end_date": end.isoformat(), "period": period})
        elif subject in conflicting_weeks and plan["axis"] == "week":
            notes.append(f"{subject} · {origin}: the Week 1 date conflicts with recorded assessment weeks. Planned dates are unavailable.")
        else:
            notes.append(f"{subject} · {origin}: planned {plan['axis']} periods have no calendar alignment. "
                         "Set a documented Week 1 date for week-based plans.")
        for row in timeline["rows"]:
            visit = row["visit"]
            if not visit:
                continue
            _, revision = context.workspace_revision(workspace, visit["data_revision_id"])
            if visit["subject_id"] != subject or context.anchor_id(revision) != base:
                notes.append(f"{subject} · visit {visit['id']} uses a different participant lineage.")
                continue
            events.append({**binding, "kind": "VISIT", "status": visit["measurement_status"],
                           "occurred_at": visit["occurred_at"], "visit": visit, "period": row["period"],
                           "observed_period": row["observed_period"]})
    return events, notes


def options(workspace: str, revision_id: str) -> dict:
    _, revision = context.workspace_revision(workspace, revision_id)
    snapshot = revision["snapshot"]
    metrics = [item for item in store.dataset_metrics(snapshot["id"])
               if item["table"] in ASSESSMENT_TABLES and snapshot.get("admitted_source")]
    anchor = context.anchor_id(revision)
    eligible_snapshots = {item["snapshot_id"] for item in store.data_revisions(workspace)
                          if context.anchor_id(item) == anchor}
    cohorts = [item for item in store.list_cohorts(workspace) if item["snapshot_id"] in eligible_snapshots]
    return {"participants": context.roster(revision), "cohorts": cohorts, "metrics": metrics,
            "sources": context.source_history(workspace, revision_id)}


def build(workspace: str, revision_id: str, query: TimelineQuery) -> dict:
    offset = _calendar(query)
    _, revision = context.workspace_revision(workspace, revision_id)
    choices = options(workspace, revision_id)
    subjects = choices["participants"]
    cohort = None
    if query.subject_id and query.cohort_id:
        raise store.ResearchValidation("Choose one existing athlete or cohort.")
    if query.subject_id:
        if query.subject_id not in subjects:
            raise store.ResearchValidation("The participant is absent from this data revision.")
        subjects = [query.subject_id]
    if query.cohort_id:
        cohort = next((item for item in choices["cohorts"] if item["id"] == query.cohort_id), None)
        if not cohort or not set(cohort["subject_ids"]) <= set(subjects):
            raise store.ResearchValidation("The selected cohort does not resolve within this participant lineage.")
        subjects = sorted(cohort["subject_ids"])
    metrics = choices["metrics"]
    metric = next((item for item in metrics if item["id"] == query.metric_id), None) if query.metric_id else None
    if query.metric_id and not metric:
        raise store.ResearchValidation("Choose an available outcome from the selected data revision.")
    metric = metric or next((item for item in metrics if item["id"] == measurement_trust.METRIC), None) or next(iter(metrics), None)
    sources, exposure = context.observations(workspace, revision_id, subjects, query.source_versions)
    assessed, performance, notes = _assessment_rows(revision, metric, subjects)
    conflicts = {row["subject_id"] for row in assessed if query.week_one and row["week"] is not None
                 and (date.fromisoformat(row["date"]) - query.week_one).days // 7 + 1 != row["week"]}
    conduct, plan_notes = _experiment_rows(workspace, subjects, context.anchor_id(revision), query, conflicts)
    output = []
    for event in [*exposure, *assessed, *conduct]:
        if event.get("date"):
            day = date.fromisoformat(event["date"])
            when = datetime.combine(day, time.min, tzinfo=offset)
        else:
            when = datetime.fromisoformat(event.get("occurred_at") or event["scheduled_at"]).astimezone(offset)
            day = when.date()
        last_day = date.fromisoformat(event.get("end_date", day.isoformat()))
        if (query.start and last_day < query.start) or (query.end and day > query.end):
            continue
        event["calendar_date"] = day.isoformat()
        event["axis_time"] = when.timestamp()
        if event.get("end_date"):
            event["axis_end"] = datetime.combine(last_day + timedelta(days=1), time.min, tzinfo=offset).timestamp()
        output.append(event)
    output.sort(key=lambda row: (row["axis_time"], row["subject_id"], row["kind"], row.get("record_id", "")))
    return {"method": METHOD, "workspace_id": workspace, "revision_id": revision_id, "query": query.model_dump(mode="json"),
            "subject_ids": subjects, "cohort": {key: cohort[key] for key in ("id", "version", "name")} if cohort else None,
            "metric": metric, "sources": sources, "performance": performance, "notes": notes + plan_notes,
            "limitations": LIMITATIONS, "events": output}


def compare(view: dict, first_id: str, second_id: str) -> dict:
    assessments = {row["id"]: row for row in view["events"] if row["kind"] == "ASSESSMENT"}
    first, second = assessments.get(first_id), assessments.get(second_id)
    if not first or not second or first["subject_id"] != second["subject_id"] or first["date"] >= second["date"]:
        raise store.ResearchValidation("Choose two dated assessments in chronological order for the same athlete.")
    reasons = []
    if first["value"] is None or second["value"] is None:
        reasons.append("One or both session scores have unresolved trial QC or acquisition provenance.")
    if first["acquisition"] != second["acquisition"] or first["unit"] != second["unit"]:
        reasons.append("The assessment acquisition, calculation or units differ.")
    if first["n_trials"] != second["n_trials"]:
        reasons.append("The sessions use different numbers of trials in their means.")
    counts = defaultdict(Counter)
    loads = defaultdict(list)
    for row in view["events"]:
        if (row["subject_id"] == first["subject_id"] and row["kind"] in {"TRAINING", "WELLNESS"}
                and first["date"] < row["calendar_date"] < second["date"]):
            bucket = counts[row["context_source_id"]]
            bucket[f"{row['kind']} {row['status']}"] += 1
            bucket.update(row.get("qc", []))
            if row.get("session_load_au") is not None:
                loads[row["context_source_id"]].append(row["session_load_au"])
    return {"reference": {key: first[key] for key in ("id", "subject_id", "session_id", "date", "value")},
            "comparison": {key: second[key] for key in ("id", "subject_id", "session_id", "date", "value")},
            "status": "INCOMPARABLE" if reasons else "DESCRIPTIVE", "reasons": reasons,
            "change": None if reasons else second["value"] - first["value"], "unit": first["unit"],
            "between_exclusive_dates_by_source": {
                key: {"counts": dict(bucket), "recorded_load_sum_au": sum(loads[key]) if loads[key] else None,
                      "sessions_with_load": len(loads[key])}
                for key, bucket in counts.items()
            }, "limitations": LIMITATIONS}


def freeze(view: dict, title: str, pair: tuple[str, str] | None = None) -> dict:
    title = title.strip()
    if not title or len(title) > 150:
        raise store.ResearchValidation("Enter a view title of up to 150 characters.")
    workspace, revision_id = view["workspace_id"], view["revision_id"]
    with store._tx() as connection:
        entity, _ = context.workspace_revision(workspace, revision_id)
        if entity["state"] == "ARCHIVED" or entity["active_data_revision_id"] != revision_id:
            raise store.ResearchConflict("Refresh the active revision before saving a contextual view.")
        current = build(workspace, revision_id, TimelineQuery.model_validate(view["query"]))
        if store._digest(current) != store._digest(view):
            raise store.ResearchConflict("Context observations or protocol conduct changed. Refresh before saving.")
        # Preserve the reviewed analytical model and displayed filter, including its provenance.
        if len(current["events"]) > 10_000:
            raise store.ResearchValidation("Narrow the athlete, cohort or date range to save up to 10,000 events.")
        document = {"id": store._new_id("VIEW-U"), "created_at": store._now(), "title": title, "view": current,
                    "comparison": compare(current, *pair) if pair else None}
        digest = store._digest(document)
        connection.execute("INSERT INTO context_views VALUES (?, ?, ?, ?, ?, ?)",
                           (document["id"], workspace, revision_id, document["created_at"], digest, store._canonical(document)))
        store._audit(connection, "workspace.context_frozen", "study", workspace, {"id": document["id"], "sha256": digest})
    return {**document, "content_hash": digest}


def history(workspace: str) -> list[dict]:
    with store._connect() as connection:
        return [dict(row) for row in connection.execute(
            """SELECT id, revision_id, created_at, content_hash, json_extract(document, '$.title') AS title,
                      json_extract(document, '$.view.subject_ids') AS participants
               FROM context_views WHERE workspace_id = ? ORDER BY created_at DESC""", (workspace,))]


def reopen(workspace: str, view_id: str) -> dict:
    with store._connect() as connection:
        row = connection.execute("SELECT * FROM context_views WHERE workspace_id = ? AND id = ?",
                                 (workspace, view_id)).fetchone()
    if not row:
        raise store.ResearchNotFound("The saved context view is unavailable in this workspace.")
    document = store._row_document(row)
    if store._digest(document) != row["content_hash"]:
        raise store.ResearchValidation("The saved context view failed its integrity check.")
    view = document["view"]
    attached = [item["source"] for item in view["sources"]]
    measured = [item["source"] for item in view["performance"].get("sources", [])]
    for pinned in [*attached, *measured]:
        if _rights_signature(context._rights(pinned["id"])) != _rights_signature(pinned):
            raise store.ResearchValidation("A saved source no longer has the original research permissions.")
    return {**document, "content_hash": row["content_hash"]}
