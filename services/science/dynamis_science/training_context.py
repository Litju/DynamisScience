"""Versioned training and self-report observations in a research workspace."""

from __future__ import annotations

import math
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import polars as pl
from pydantic import BaseModel, ConfigDict, Field

from . import admission, importer, reconciliation, researchstore as store
from .data_root import paths

MAX_BYTES = 20 * 1024**2
MAX_ROWS = 50_000
SOURCE_METHOD = "training-context-source@1"
REQUIRED = ("participant", "record_id", "kind", "status")
OPTIONAL = (
    "occurred_at", "scheduled_at", "recorded_at", "duration", "duration_unit", "rpe", "rpe_scale",
    "measure", "value", "unit", "questionnaire", "questionnaire_version",
    "adherence", "deviation", "reason",
)
TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?(Z|([+-])(\d{2}):(\d{2}))")


class SourceMapping(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    columns: dict[str, str] = Field(default_factory=dict)
    participants: dict[str, str] = Field(default_factory=dict)


class Observation(BaseModel):
    subject_id: str
    external_id: str
    record_id: str
    kind: Literal["TRAINING", "WELLNESS"]
    status: Literal["OBSERVED", "MISSING", "OMITTED"]
    occurred_at: str | None = None
    scheduled_at: str | None = None
    recorded_at: str | None = None
    duration: float | None = None
    duration_unit: str | None = None
    duration_min: float | None = None
    rpe: float | None = None
    rpe_scale: str | None = None
    session_load_au: float | None = None
    measure: str | None = None
    value: float | None = None
    unit: str | None = None
    questionnaire: str | None = None
    questionnaire_version: str | None = None
    adherence: Literal["AS_PLANNED", "MODIFIED", "OMITTED", "UNKNOWN"] | None = None
    deviation: str | None = None
    reason: str | None = None
    source_row: int
    qc: list[str]


def workspace_revision(workspace_id: str, revision_id: str | None = None) -> tuple[dict, dict]:
    entity = store.get_entity(workspace_id)
    if not entity or not entity.get("workspace"):
        raise store.ResearchValidation("Open a research workspace with an attached participant roster.")
    revision = store.get_data_revision(revision_id or entity.get("active_data_revision_id") or "")
    if not revision or revision["workspace_id"] != workspace_id:
        raise store.ResearchValidation("Select a data revision in this workspace.")
    return entity, revision


def anchor_id(revision: dict) -> str:
    while revision["mode"] != "SEPARATE" and revision["parent_revision_id"]:
        _, revision = workspace_revision(revision["workspace_id"], revision["parent_revision_id"])
    return revision["id"]


def roster(revision: dict) -> list[str]:
    snapshot = revision["snapshot"]
    # Reconstructed rosters inherit their checksums from the captured revision.
    table = "subjects" if "subjects" in snapshot["tables"] else next(
        (name for name in ("cmj_trials", "sprint_trials", "monitoring") if name in snapshot["tables"]), None)
    if table and snapshot.get("admitted_source"):
        root = paths()["research"] / "data" if snapshot.get("workspace_snapshot") else paths()["admitted"]
        file = root / snapshot["id"] / f"{table}.parquet"
        if not file.is_file() or importer._sha256(file) != snapshot.get("checksums", {}).get(file.name):
            raise store.ResearchValidation("The participant roster source failed its checksum check.")
    return sorted(store.read_snapshot_table(snapshot["id"], "subjects")["subject_id"].cast(str).unique())


def _rights(source_id: str) -> dict:
    source = admission.get_source(source_id)
    if (not source or source["rights_status"] not in {"VERIFIED", "FIXTURE_ONLY"}
            or "research" not in {str(use).strip().lower() for use in source["permitted_uses"]}):
        raise store.ResearchValidation("Select a registered source with current research permission.")
    keys = ("id", "name", "publisher", "dataset_identity", "version", "rights_status",
            "license_or_agreement", "permitted_uses", "redistribution_restrictions", "privacy_status",
            "retention_limitations")
    return {key: source[key] for key in keys}


def _text(value) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    return (str(value).strip() or None) if value is not None else None


def _number(value, field: str) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
        if math.isfinite(parsed):
            return parsed
    except (ValueError, TypeError):
        pass
    raise ValueError(f"{field} requires a finite number.")


def _time(text: str | None) -> str | None:
    if text is None:
        return None
    try:
        match = TIMESTAMP.fullmatch(text)
        if match:
            offset, _, hours, minutes = match.groups()
            if offset == "Z" or (offset != "-00:00" and int(minutes) < 60
                                 and (int(hours) < 14 or offset in {"+14:00", "-14:00"})):
                return datetime.fromisoformat(text).isoformat()
    except ValueError:
        pass
    raise ValueError("Use an ISO date and time with an explicit UTC offset, for example 2026-08-12T18:00:00-03:00.")


def instant(text: str) -> datetime:
    return datetime.fromisoformat(text).astimezone(UTC)


def _observation(values: dict, subject: str, row: int) -> Observation:
    kind, status = values["kind"], values["status"]
    occurred, scheduled, recorded = (_time(values.get(name)) for name in ("occurred_at", "scheduled_at", "recorded_at"))
    if status == "OBSERVED":
        if not occurred:
            raise ValueError("An observed record requires an actual timestamp.")
    elif occurred or not scheduled or not values.get("reason"):
        raise ValueError("Missing or omitted records require a scheduled timestamp and reason, with no actual timestamp.")
    if occurred and recorded and instant(recorded) < instant(occurred):
        raise ValueError("Recorded time precedes the actual observation.")
    qc = []
    if status != "OBSERVED":
        qc.append(status)
    if occurred and scheduled and instant(occurred) > instant(scheduled):
        qc.append("AFTER_SCHEDULE")
    if occurred and recorded and instant(recorded) > instant(occurred):
        qc.append("RECORDED_LATER")
    fields = {key: values[key] for key in ("measure", "unit", "questionnaire", "questionnaire_version",
                                         "adherence", "deviation", "reason", "duration_unit", "rpe_scale")
              if key in values}
    duration, rpe, value = (_number(values.get(key), key) for key in ("duration", "rpe", "value"))
    minutes = load = None
    if kind == "TRAINING":
        if any(values.get(key) for key in ("measure", "value", "unit", "questionnaire", "questionnaire_version")):
            raise ValueError("Training uses session-level duration and RPE; wellness requires its own record.")
        if status != "OBSERVED" and (duration is not None or rpe is not None):
            raise ValueError("Only actual training sessions may contain duration or RPE.")
        unit, scale = values.get("duration_unit"), values.get("rpe_scale")
        if (unit and unit not in {"min", "s"}) or (duration is not None and (not unit or duration <= 0)):
            raise ValueError("Training duration must be positive and recorded in min or s.")
        if (scale and scale != "CR10") or (rpe is not None and (scale != "CR10" or not 0 <= rpe <= 10)):
            raise ValueError("Session RPE requires a documented CR10 scale and a value from 0 to 10.")
        adherence = values.get("adherence")
        if (adherence == "OMITTED") != (status == "OMITTED"):
            raise ValueError("Record an omitted training session with both OMITTED status and adherence.")
        if adherence == "MODIFIED" and (status != "OBSERVED" or not values.get("deviation")):
            raise ValueError("Modified adherence requires an observed session and recorded deviation.")
        if status != "OBSERVED" and adherence == "AS_PLANNED":
            raise ValueError("As-planned adherence requires an observed session.")
        if duration is not None:
            minutes = duration if unit == "min" else duration / 60
        if minutes is not None and rpe is not None:
            load = minutes * rpe
            if not math.isfinite(load):
                raise ValueError("Derived session load is out of numeric range.")
        if status == "OBSERVED" and load is None:
            qc.append("INCOMPLETE_EXPOSURE")
    elif kind == "WELLNESS":
        if any(values.get(key) for key in ("duration", "duration_unit", "rpe", "rpe_scale", "adherence", "deviation")):
            raise ValueError("Wellness rows use questionnaire/item observations; training fields belong on session rows.")
        if not all(values.get(key) for key in ("measure", "unit", "questionnaire", "questionnaire_version")):
            raise ValueError("Wellness requires the item, unit, questionnaire and questionnaire version.")
        if (value is not None) != (status == "OBSERVED") or status == "OMITTED":
            raise ValueError("Wellness must be an observed numeric response or an explicitly missing observation.")
    return Observation(subject_id=subject, external_id=values["participant"], record_id=values["record_id"],
                       kind=kind, status=status, occurred_at=occurred, scheduled_at=scheduled, recorded_at=recorded,
                       duration=duration, duration_min=minutes, rpe=rpe, session_load_au=load, value=value,
                       source_row=row, qc=qc, **fields)


def source_history(workspace_id: str, revision_id: str) -> list[dict]:
    _, revision = workspace_revision(workspace_id, revision_id)
    with store._connect() as connection:
        return [store._row_document(row) for row in connection.execute(
            "SELECT document FROM context_sources WHERE workspace_id = ? AND anchor_id = ? ORDER BY source_id, version",
            (workspace_id, anchor_id(revision)))]


def _read_observations(record: dict) -> pl.DataFrame:
    current = _rights(record["source"]["id"])
    if current != record["source"]:
        raise store.ResearchValidation("The context source rights have changed since attachment.")
    artifact = admission.get_source_artifact(record["artifact_id"])
    if (not artifact or artifact["source_id"] != current["id"]
            or artifact["content_hash_sha256"] != record["raw_sha256"]
            or importer._sha256(Path(artifact["stored_path"])) != record["raw_sha256"]):
        raise store.ResearchValidation("The retained context source failed its checksum check.")
    file = paths()["research"] / "context" / f"{record['id']}.parquet"
    if importer._sha256(file) != record["parquet_sha256"]:
        raise store.ResearchValidation("The context observation table failed its checksum check.")
    return pl.read_parquet(file)


def preview(workspace_id: str, revision_id: str, source_id: str, file: str | Path,
            mapping: SourceMapping) -> tuple[dict, list[Observation]]:
    _, revision = workspace_revision(workspace_id, revision_id)
    source = _rights(source_id)
    path = Path(file)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise store.ResearchValidation("Select a regular source file of up to 20 MiB.")
    if path.suffix.lower() not in {".csv", ".tsv", ".xlsx", ".parquet", ".pq"}:
        raise store.ResearchValidation("Select a CSV, TSV, Excel or Parquet context source.")
    raw = importer._sha256(path)
    lazy, _ = importer.open_table(path)
    columns = lazy.collect_schema().names()
    names = (*REQUIRED, *OPTIONAL)
    configured = {name: mapping.columns.get(name, name) for name in names
                  if name in mapping.columns or name in columns}
    if (set(mapping.columns) - set(names) or set(configured.values()) - set(columns)
            or len(set(configured.values())) != len(configured) or set(REQUIRED) - set(configured)):
        raise store.ResearchValidation("Map each required field to its own existing source column.")
    lazy, info = importer.open_table(path, text_columns=tuple(configured.values()))
    frame = importer._records(lazy).select([pl.col(col).alias(key) for key, col in configured.items()]).head(MAX_ROWS + 1).collect()
    if not 0 < frame.height <= MAX_ROWS:
        raise store.ResearchValidation("A context source requires between 1 and 50,000 rows.")
    if importer._sha256(path) != raw:
        raise store.ResearchConflict("The source changed during review. Preview it again.")
    records = source_history(workspace_id, revision_id)
    if any(item["raw_sha256"] == raw and item["source"]["id"] != source_id for item in records):
        raise store.ResearchValidation("Identical source bytes already belong to another attached source identity.")
    history = [item for item in records if item["source"]["id"] == source_id]
    prior = history[-1] if history else None
    bindings = prior["bindings"] if prior else {}
    allowed = set(roster(revision))
    participant_ids = sorted({_text(item) or "" for item in frame["participant"]})
    findings = []
    resolved, _ = reconciliation._identity_map("athlete", participant_ids, allowed, mapping.participants,
                                                bindings, lambda *issue: findings.append(issue))
    if any(len(issue) == 4 and issue[3] for issue in findings) or "" in participant_ids:
        raise store.ResearchValidation("Participant mapping conflict: " + "; ".join(str(item[2]) for item in findings))
    previous = {item["record_id"]: item for item in _read_observations(prior).to_dicts()} if prior else {}
    parsed = {}
    grains = set()
    scales = {}
    for index, entry in enumerate(frame.iter_rows(named=True), 1):
        values = {name: _text(value) for name, value in entry.items()}
        key = values["record_id"]
        try:
            if not key or key in parsed:
                raise ValueError("Record identifiers must be present and unique within the source.")
            if any(len(values.get(name) or "") > 150 for name in ("record_id", "participant", "questionnaire", "measure", "unit")):
                raise ValueError("Record, participant and measure identifiers must be at most 150 characters.")
            observation = _observation(values, resolved[values["participant"]], index)
            grain = (observation.external_id, observation.kind, observation.measure,
                     observation.questionnaire, observation.questionnaire_version,
                     instant(observation.occurred_at or observation.scheduled_at))
            if grain in grains:
                raise ValueError("Duplicate observation at the same participant, measure and timestamp.")
            grains.add(grain)
            if observation.kind == "WELLNESS":
                instrument = (observation.questionnaire, observation.questionnaire_version, observation.measure)
                if scales.setdefault(instrument, observation.unit) != observation.unit:
                    raise ValueError("A questionnaire item version must use one explicit measurement unit.")
            original = previous.get(key)
            if original and any(original[field] != getattr(observation, field) for field in
                                ("external_id", "subject_id", "kind", "measure", "questionnaire")):
                raise ValueError("An existing record cannot change participant, observation kind or measure.")
            parsed[key] = observation
        except (ValueError, TypeError) as error:
            raise store.ResearchValidation(f"Source data row {index}: {error}") from error
    if set(previous) - set(parsed):
        raise store.ResearchValidation("A new source version must keep prior record IDs and mark missing or omitted observations explicitly.")
    qc = Counter(flag for observation in parsed.values() for flag in observation.qc)
    changes = Counter("new" if key not in previous else
                      "unchanged" if row.model_dump(exclude={"source_row"}) ==
                      {field: value for field, value in previous[key].items() if field != "source_row"} else "changed"
                      for key, row in parsed.items())
    receipt = {"method": SOURCE_METHOD, "workspace_id": workspace_id, "anchor_id": anchor_id(revision),
               "data_revision_id": revision_id, "source": source, "format": info,
               "filename": path.name, "raw_sha256": raw, "mapping": mapping.model_dump(),
               "columns": configured, "unused_columns": sorted(set(columns) - set(configured.values())),
               "bindings": {**bindings, **resolved}, "row_count": len(parsed), "qc": dict(qc), "changes": dict(changes),
               "prior_id": prior["id"] if prior else None, "version": len(history) + 1}
    return receipt, list(parsed.values())


def attach(workspace_id: str, revision_id: str, source_id: str, file: str | Path,
           mapping: SourceMapping, preview_receipt: dict, reviewer: str) -> dict:
    if not reviewer.strip():
        raise store.ResearchValidation("Record who reviewed participant mappings, units and source rights.")
    identity = destination = None
    committed = False
    try:
        with store._tx() as connection:
            entity, _ = workspace_revision(workspace_id, revision_id)
            if entity["state"] == "ARCHIVED" or entity["active_data_revision_id"] != revision_id:
                raise store.ResearchConflict("Refresh the active workspace revision before attaching context.")
            receipt, rows = preview(workspace_id, revision_id, source_id, file, mapping)
            prior = next((record for record in source_history(workspace_id, revision_id)
                          if record["id"] == receipt["prior_id"]), None)
            if prior and all(prior[key] == receipt[key] for key in ("raw_sha256", "mapping", "columns", "source")):
                return prior
            if receipt != preview_receipt:
                raise store.ResearchConflict("The context source or workspace changed. Review the new preview.")
            artifact = admission.ingest_source_file(source_id, file, SOURCE_METHOD)
            if (artifact["content_hash_sha256"] != receipt["raw_sha256"]
                    or importer._sha256(Path(artifact["stored_path"])) != receipt["raw_sha256"]):
                raise store.ResearchConflict("The retained file differs from the reviewed source.")
            identity = store._new_id("CTX-U")
            target = paths()["research"] / "context" / f"{identity}.parquet"
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as output:
                destination = target
                pl.DataFrame([row.model_dump() for row in rows], infer_schema_length=None).write_parquet(output)
            receipt.update(id=identity, artifact_id=artifact["id"], parquet_sha256=importer._sha256(destination),
                           reviewed_by=reviewer.strip(), created_at=store._now())
            connection.execute("INSERT INTO context_sources VALUES (?, ?, ?, ?, ?, ?)",
                               (workspace_id, receipt["anchor_id"], source_id, receipt["version"],
                                identity, store._canonical(receipt)))
            store._audit(connection, "workspace.context_attached", "study", workspace_id, receipt)
        committed = True
        return receipt
    finally:
        if destination and not committed:
            with store._connect() as connection:
                persisted = connection.execute("SELECT 1 FROM context_sources WHERE id = ?", (identity,)).fetchone()
            if not persisted:
                destination.unlink(missing_ok=True)


def observations(workspace_id: str, revision_id: str, subject_ids: list[str],
                 selected_sources: list[str] | None = None) -> tuple[list[dict], list[dict]]:
    history = source_history(workspace_id, revision_id)
    if selected_sources is None:
        selected = list({row["source"]["id"]: row for row in history}.values())
    else:
        selected = [row for row in history if row["id"] in selected_sources]
        if len(selected) != len(set(selected_sources)) or len({row["source"]["id"] for row in selected}) != len(selected):
            raise store.ResearchValidation("Choose one attached version per source for this participant lineage.")
    rows = []
    for source in selected:
        frame = _read_observations(source).filter(pl.col("subject_id").is_in(subject_ids))
        rows.extend({**row, "context_source_id": source["id"], "artifact_id": source["artifact_id"],
                     "source_name": source["source"]["name"], "rights_status": source["source"]["rights_status"]}
                    for row in frame.to_dicts())
    rows.sort(key=lambda row: (instant(row["occurred_at"] or row["scheduled_at"]), row["subject_id"], row["record_id"]))
    return selected, rows
