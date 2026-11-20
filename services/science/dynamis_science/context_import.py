"""Read-only mapping suggestions and review for versioned training context imports."""

from hashlib import sha256

import polars as pl

from . import admission, importer, researchstore as store, training_context as context

COLUMN_LABELS = {
    "participant": "Athlete", "record_id": "Observation ID", "kind": "Record type", "status": "Status",
    "occurred_at": "Actual date and time", "scheduled_at": "Scheduled date and time", "recorded_at": "Recorded date and time",
    "duration": "Duration", "duration_unit": "Duration unit", "rpe": "Session RPE", "rpe_scale": "RPE scale",
    "measure": "Wellness item", "value": "Wellness value", "unit": "Wellness unit",
    "questionnaire": "Questionnaire", "questionnaire_version": "Questionnaire version",
    "adherence": "Adherence", "deviation": "Deviation", "reason": "Reason",
}

ALIASES = {
    "participant": ("athlete", "athlete id", "participant id", "subject id"),
    "record_id": ("record id", "observation id", "session id"),
    "kind": ("type", "record type", "observation type"),
    "status": ("record status", "observation status"),
    "occurred_at": ("actual time", "actual timestamp", "timestamp"),
    "scheduled_at": ("scheduled time", "scheduled timestamp", "planned time"),
    "recorded_at": ("recorded time", "logged at"),
    "duration_unit": ("duration units",),
    "rpe": ("session rpe", "srpe"),
    "rpe_scale": ("session rpe scale",),
    "measure": ("wellness item", "questionnaire item"),
}


def _normalized(name):
    return "".join(char for char in name.casefold() if char.isalnum())


def _suggest_columns(columns):
    mapping = {key: key for key in COLUMN_LABELS if key in columns}
    for key in COLUMN_LABELS:
        if key in mapping:
            continue
        names = {_normalized(name) for name in (key, *ALIASES.get(key, ()))}
        candidates = [name for name in columns if name not in mapping.values() and _normalized(name) in names]
        if len(candidates) == 1:
            mapping[key] = candidates[0]
    return mapping


def fingerprint(file):
    return importer._sha256(context.source_file(file))


def mapping_preview(workspace, revision, file, source_id=None, columns=None, *, suggest_source=True):
    """Describe file columns, actual units and the identities that still need confirmation."""
    _, revision_data = context.workspace_revision(workspace, revision)
    path = context.source_file(file)
    digest = importer._sha256(path)
    lazy, _ = importer.open_table(path)
    available = lazy.collect_schema().names()
    columns = _suggest_columns(available) if columns is None else dict(columns)
    selected = {col: key for key, col in columns.items()}
    problems = []
    if set(columns) - set(COLUMN_LABELS) or set(selected) - set(available) or len(selected) != len(columns):
        problems.append("Each mapped field needs its own column from this file.")
        selected = {}
    missing = [COLUMN_LABELS[key] for key in context.REQUIRED if key not in columns]
    if missing:
        problems.append(f"Choose columns for {', '.join(missing)}.")
    content = {}
    if selected:
        lazy, _ = importer.open_table(path, text_columns=tuple(selected))
        fields = {"participant", "record_id", "duration_unit", "rpe_scale", "unit"}
        frame = importer._records(lazy).head(context.MAX_ROWS + 1).collect()
        if frame.is_empty() or frame.height > context.MAX_ROWS:
            raise store.ResearchValidation("A context source requires between 1 and 50,000 rows.")
        content = frame.select([pl.col(col).alias(key) for col, key in selected.items() if key in fields]).to_dict(as_series=False)
    if importer._sha256(path) != digest:
        raise store.ResearchConflict("The file changed during review. Choose it again.")
    history = context.source_history(workspace, revision)
    latest = {row["source"]["id"]: row for row in history}
    if suggest_source and not source_id and content.get("record_id"):
        incoming = {context._text(value) for value in content["record_id"]}
        matches = []
        for identity, receipt in latest.items():
            try:
                previous = set(context._read_observations(receipt)["record_id"])
            except (ValueError, OSError, pl.exceptions.PolarsError):
                continue  # An unreadable prior version cannot suggest a source.
            if previous and previous <= incoming:
                matches.append(identity)
        if len(matches) == 1:
            source_id = matches[0]
    if source_id:
        context._rights(source_id)
    prior = latest.get(source_id)
    bindings = prior["bindings"] if prior else {}
    roster = context.roster(revision_data)
    external = {context._text(value) for value in content.get("participant", [])}
    if None in external:
        problems.append("At least one row is missing its athlete identifier.")
        external.remove(None)
    identities = {key: bindings.get(key) or (key if key in roster else None) for key in sorted(external)}
    units = {key: sorted({value for raw in content.get(key, []) if (value := context._text(raw))})
             for key in ("duration_unit", "rpe_scale", "unit")}
    return {"file_sha256": digest, "available_columns": available, "columns": columns, "source_id": source_id,
            "athletes": roster, "identities": identities, "units": units, "problems": problems}


def review(workspace, revision, source_id, file, mapping):
    receipt, rows = context.preview(workspace, revision, source_id, file, mapping)
    previous = next((item for item in context.source_history(workspace, revision) if item["id"] == receipt["prior_id"]), None)
    examples = []
    if previous and receipt["changes"].get("changed"):
        original = {row["record_id"]: row for row in context._read_observations(previous).to_dicts()}
        for row in rows:
            old = original.get(row.record_id)
            if old and row.model_dump(exclude={"source_row"}) != {key: value for key, value in old.items() if key != "source_row"}:
                examples.append((old, row.model_dump()))
                if len(examples) == 8:
                    break
    return receipt, rows, examples


def quarantine(workspace, revision, source_id, file, reviewed_hash, reviewer, reason):
    """Retain the original under its authorized identity with a quarantined QC decision."""
    if not reviewer.strip() or not reason.strip():
        raise store.ResearchValidation("Identify who reviewed the file and why it is being quarantined.")
    path = context.source_file(file)
    with path.open("rb") as stream:
        raw = stream.read(context.MAX_BYTES + 1)
    if len(raw) > context.MAX_BYTES or sha256(raw).hexdigest() != reviewed_hash:
        raise store.ResearchConflict("The file changed during review. Choose it again.")
    with store._tx() as connection:
        entity, revision_data = context.workspace_revision(workspace, revision)
        if entity["state"] == "ARCHIVED" or entity["active_data_revision_id"] != revision:
            raise store.ResearchConflict("Refresh the active workspace revision before quarantining context.")
        source = context._rights(source_id)
        if any(row["raw_sha256"] == reviewed_hash and row["source"]["id"] != source_id
               for row in context.source_history(workspace, revision)):
            raise store.ResearchValidation("Identical bytes already belong to another context source.")
        artifact = admission.ingest_source_artifact(source_id, path.name, raw, context.SOURCE_METHOD)
        metadata = {"workspace_id": workspace, "data_revision_id": revision, "anchor_id": context.anchor_id(revision_data),
                    "reviewer": reviewer.strip(), "reason": reason.strip(), "source_rights": source}
        quality = admission._quality_result(artifact, "TRAINING_CONTEXT", metadata, "QUARANTINED",
                                           [reason.strip()], [], [], [], {})
        store._audit(connection, "workspace.context_quarantined", "study", workspace,
                     {"quality_id": quality["id"], "artifact_id": artifact["id"], **metadata})
    return {"filename": path.name, "artifact_id": artifact["id"], "quality_id": quality["id"]}
