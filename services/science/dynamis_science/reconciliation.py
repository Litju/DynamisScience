"""Review follow-up CMJ summaries against a pinned research data revision."""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import uuid
from pathlib import Path
from typing import Any

import polars as pl

from . import admission, importer, researchstore as store
from .data_root import paths

FAMILY = "CMJ_FORCE_PLATFORM"
TABLE = "cmj_trials"
CONTEXT_FIELDS = ("source_id", "instrument_id", "protocol_id")
IDENTITY_FIELDS = ("subject_id", "session_id", "trial_id", "week")
METRICS = set(admission.CMJ_METRIC_COLUMNS) | {"body_mass_kg"}
MAX_ROWS = 50_000
PREVIEW_LIMIT = 30


def history(workspace_id: str) -> list[dict]:
    with store._connect() as connection:
        return [json.loads(row[0]) for row in connection.execute(
            """SELECT document FROM reconciliation_events WHERE workspace_id = ?
               ORDER BY rowid DESC""", (workspace_id,))]


def _event(connection, proposal: dict, **changes) -> dict:
    event = {**proposal, **changes, "version": proposal.get("version", 0) + 1, "recorded_at": store._now()}
    connection.execute("INSERT INTO reconciliation_events VALUES (?, ?, ?, ?)",
                       (event["workspace_id"], event["id"], event["version"], store._canonical(event)))
    return event


def _latest(workspace_id: str, batch_id: str, version: int) -> dict:
    entry = next((event for event in history(workspace_id) if event["id"] == batch_id), None)
    if entry is None or entry["version"] != version:
        raise store.ResearchConflict("The proposal has changed. Refresh review history.")
    return entry


def _workspace(workspace_id: str, base_revision: str | None = None) -> dict:
    entity = store.get_entity(workspace_id)
    if not entity or not entity.get("workspace") or entity["state"] == "ARCHIVED":
        raise store.ResearchValidation("Open an active research workspace to reconcile a follow-up.")
    active = entity.get("active_data_revision_id")
    if base_revision and base_revision != active:
        raise store.ResearchConflict("The active data revision changed. Review the file against the new revision.")
    revision = store.get_data_revision(active) if active else None
    if not revision or not revision["snapshot"].get("admitted_source") or TABLE not in revision["snapshot"]["tables"]:
        raise store.ResearchValidation("Attach an admitted CMJ summary first to establish the research roster and protocol.")
    return revision


def _retain(path: Path) -> tuple[Path, str]:
    if path.is_symlink() or not path.is_file():
        raise importer.ImportBlocked("Choose a regular source file.")
    if path.stat().st_size > importer.MAX_FILE_BYTES:
        raise importer.ImportBlocked("The source exceeds the summary file size limit.")
    checksum = importer._sha256(path)
    # The suffix is needed by the existing parser. File names are display metadata.
    cache = paths()["sources"] / "reconciliation" / checksum
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / ("source" + path.suffix.lower())
    if not target.exists():
        temporary = cache / f".{uuid.uuid4().hex}.tmp"
        try:
            with path.open("rb") as source, temporary.open("xb") as saved:
                remaining = importer.MAX_FILE_BYTES
                while chunk := source.read(1 << 20):
                    remaining -= len(chunk)
                    if remaining < 0:
                        raise importer.ImportBlocked("The source changed size while being copied.")
                    saved.write(chunk)
            if importer._sha256(temporary) != checksum:
                raise importer.ImportBlocked("The source changed while being copied. Choose it again.")
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
    if importer._sha256(target) != checksum:
        raise importer.ImportBlocked("The retained source failed its checksum check.")
    return target, checksum


def _reference(revision: dict) -> tuple[dict, pl.DataFrame, dict, dict]:
    inputs = [snapshot for snapshot in revision["inputs"] if snapshot.get("measurement_family") == FAMILY]
    if not inputs:
        raise importer.ImportBlocked("The revision has no admitted CMJ source.")
    first = inputs[0]
    store._validate_workspace_append(inputs)
    filename = f"{TABLE}.parquet"
    analytical = revision["snapshot"]
    directory = (paths()["research"] / "data" if analytical.get("workspace_snapshot") else paths()["admitted"])
    for snapshot, path in [(analytical, directory / analytical["id"] / filename),
                           *((item, paths()["admitted"] / item["id"] / filename) for item in inputs)]:
        if not path.is_file() or importer._sha256(path) != snapshot.get("checksums", {}).get(filename):
            raise importer.ImportBlocked(f"Reference snapshot {snapshot['id']} failed its checksum check.")
    frame = store.read_snapshot_table(analytical["id"], TABLE)
    for name in (*IDENTITY_FIELDS, "sampling_hz", "instrument_id", "protocol_id"):
        if name not in frame.columns or frame[name].null_count():
            raise importer.ImportBlocked(f"The selected reference lacks complete {name} metadata.")
    if frame["trial_id"].n_unique() != frame.height:
        raise importer.ImportBlocked("The reference contains overlapping trial identifiers.")
    ids = {name: frame[name].unique().to_list() for name in ("instrument_id", "protocol_id", "sampling_hz")}
    if any(len(values) != 1 for values in ids.values()):
        raise importer.ImportBlocked("The selected reference has mixed instrument, protocol or sampling metadata.")
    record = first["admission"]
    source = admission.get_source(record["source_id"])
    instrument = admission.get_instrument(ids["instrument_id"][0])
    protocol = admission.get_protocol(ids["protocol_id"][0])
    if not source or not instrument or not protocol or first["provenance"]["instrument_metadata"] != [instrument]:
        raise importer.ImportBlocked("The registered source, instrument or calibration differs from the captured reference.")
    if source["rights_status"] != first["rights_status"] or source["rights_status"] not in {"VERIFIED", "FIXTURE_ONLY"}:
        raise importer.ImportBlocked("Source rights no longer match the admitted reference.")
    if source["permitted_uses"] != first["source"]["permitted_uses"] or "research" not in {
            use.strip().lower() for use in source["permitted_uses"]}:
        raise importer.ImportBlocked("Source permissions must still allow research under the original terms.")
    if (protocol["units"] != importer.CANONICAL_UNITS[FAMILY] or
            protocol["sampling_hz"] != ids["sampling_hz"][0]):
        raise importer.ImportBlocked("The registered protocol differs from the reference units or sampling rate.")
    receipts = importer.list_receipts()
    prior = [r for item in inputs for r in receipts
             if r["source_artifact_id"] == item["admission"]["source_artifact_id"]]
    return {"source": source, "instrument": instrument, "protocol": protocol}, frame, (prior[-1] if prior else {}), {
        "snapshot_id": first["id"], "raw_exposures": sorted({r["raw_sha256"] for r in prior})}


def propose(workspace_id: str, path: str | Path) -> dict:
    source = Path(path)
    with store._tx() as connection:
        revision = _workspace(workspace_id)
        retained, checksum = _retain(source)
        batch_id = "REC-" + hashlib.sha256(f"{revision['id']}:{checksum}".encode()).hexdigest()[:20].upper()
        records = history(workspace_id)
        found = next((item for item in records if item["raw_sha256"] == checksum and
                      (item["id"] == batch_id or item["state"] == "APPROVED")), None)
        if found:
            return {**found, "repeat_file": True, "repeat_filename": source.name}
        plan = importer.probe_file(retained)
        proposal = {"workspace_id": workspace_id, "id": batch_id, "base_revision": revision["id"],
                    "filename": source.name, "raw_sha256": checksum, "raw_path": str(retained),
                    "plan": plan, "athletes": {}, "sessions": {}, "declared": {}, "state": "PROPOSED"}
        evaluated, _ = _evaluate(proposal, revision, records)
        return _event(connection, proposal, **evaluated)


def revise(workspace_id: str, batch_id: str, version: int, *, edits: dict | None = None,
           constants: dict | None = None, athletes: dict | None = None, sessions: dict | None = None,
           declared: dict | None = None) -> dict:
    with store._tx() as connection:
        entry = _latest(workspace_id, batch_id, version)
        if entry["state"] not in {"PROPOSED", "QUARANTINED"}:
            raise store.ResearchConflict("This proposal has a final decision.")
        revision = _workspace(workspace_id, entry["base_revision"])
        plan = entry["plan"]
        if plan["state"] == "UNSUPPORTED":
            raise importer.ImportBlocked("Choose a readable revised source file.")
        if edits or constants:
            plan = importer.edit_mapping(plan, edits or {}, constants)
        candidate = {**entry, "plan": plan, "athletes": entry["athletes"] if athletes is None else athletes,
                     "sessions": entry["sessions"] if sessions is None else sessions,
                     "declared": entry["declared"] if declared is None else declared}
        evaluated, _ = _evaluate(candidate, revision, history(workspace_id))
        candidate.pop("decision", None)
        return _event(connection, candidate, state="PROPOSED", **evaluated)


def _column_value(plan: dict, headers: list[str]) -> list[str | None]:
    lazy, _ = importer.open_table(Path(plan["path"]), text_columns=tuple(headers))
    return sorted({value for column in headers for value in
                   importer._records(lazy).select(pl.col(column).cast(pl.String).str.strip_chars()).unique()
                   .collect()[column]}, key=lambda value: (value is not None, value or ""))


def _identity_map(kind: str, values: list[str], allowed: set[str], entered: dict, bindings: dict,
                  issue, *, new_sessions: bool = False) -> tuple[dict, list]:
    resolved, evidence = {}, []
    for source in values:
        expected = bindings.get(source) or (source if source in allowed else None)
        target = entered.get(source, expected)
        if not target:
            issue(f"{kind}_identity", expected or "Unconfirmed", source, True)
        elif expected and expected != target:
            issue(f"{kind}_conflict", expected, f"{source} → {target}", True)
        elif not new_sessions and target not in allowed:
            issue(f"{kind}_conflict", "Existing workspace athlete", target, True)
        elif target != target.strip() or len(target) > 150:
            issue(f"{kind}_conflict", "Non-blank identifier up to 150 characters", target, True)
        else:
            resolved[source] = target
            if source != target or source not in allowed:
                issue(f"{kind}_mapping", target, source)
        evidence.append({"source": source, "target": target, "bound": bool(expected),
                         "confirmed": source in entered})
    if set(entered) - set(values):
        issue(f"{kind}_conflict", "Only identifiers in this file", "Mappings contain unused identifiers", True)
    if len(set(resolved.values())) != len(resolved):
        issue(f"{kind}_conflict", "One source identifier per target", "Multiple identifiers resolve to the same target", True)
    return resolved, evidence


def _changed(column: str, previous: Any, incoming: Any) -> bool:
    if previous == incoming:
        return False
    if column in METRICS and isinstance(previous, float) and isinstance(incoming, float):
        # Unit conversion can shift a value by a representational bit. Do not apply a scientific tolerance.
        return abs(previous - incoming) > 2 * max(math.ulp(previous), math.ulp(incoming))
    return True


def _evaluate(proposal: dict, revision: dict, records: list[dict]) -> tuple[dict, dict | None]:
    plan = proposal["plan"]
    result: dict[str, Any] = {"discrepancies": [], "context": {}, "identity_preview": {},
                              "sessions_qc": [], "rows_preview": [], "corrections": [], "counts": {},
                              "ready": False, "quality": None, "import_receipt_id": None}

    def issue(kind: str, reference: Any, incoming: Any, blocked: bool = False) -> None:
        result["discrepancies"].append({"kind": kind, "reference": reference, "incoming": incoming, "blocked": blocked})

    try:
        context, old, prior, reference = _reference(revision)
        source, instrument, protocol = (context[key] for key in ("source", "instrument", "protocol"))
        expected = dict(zip(CONTEXT_FIELDS, (source["id"], instrument["id"], protocol["id"])))
        result["context"] = {**expected, **reference, "source_name": source["name"], "rights": source["rights_status"],
                             "instrument": f"{instrument['manufacturer']} {instrument['model']}",
                             "calibration": instrument["calibration_status"], "protocol": protocol["name"],
                             "protocol_version": protocol["version"], "sampling_hz": protocol["sampling_hz"]}
        checksum = proposal["raw_sha256"]
        if importer._sha256(Path(proposal["raw_path"])) != checksum:
            raise importer.ImportBlocked("The retained original failed its checksum check.")
        raw_matches = [r for r in importer.list_receipts() if r["raw_sha256"] == checksum]
        if any(r["source_id"] != source["id"] for r in raw_matches):
            issue("source_conflict", source["id"], "Identical bytes are registered under another source", True)
        if checksum in reference["raw_exposures"]:
            issue("duplicate_file", "Already in the selected revision", checksum, True)
        if plan["state"] == "UNSUPPORTED":
            issue("unreadable", "Readable summary export", plan.get("reason"), True)
            return result, None
        if plan["raw_sha256"] != checksum:
            raise importer.ImportBlocked("The retained file and the reviewed plan have different checksums.")
        if plan["rows"] > MAX_ROWS:
            raise importer.ImportBlocked(f"Review up to {MAX_ROWS:,} trial rows per file; split larger exports.")
        if prior and plan["columns"] != prior["columns"]:
            issue("source_schema", prior["columns"], plan["columns"])
        columns = plan["mapping"]["columns"]
        if len({entry["source"] for entry in columns.values()}) != len(columns):
            issue("column_mapping", "Distinct input column for each target", "A source column is mapped more than once", True)
        for name, entry in columns.items():
            previous = prior.get("mapping", {}).get("columns", {}).get(name, {})
            _, stated = importer._split_header(entry["source"])
            if importer.COLUMNS[name][1] is not None and stated is not None and (
                    importer._unit_key(stated) != entry["unit"]):
                issue("unit_conflict", stated, f"{entry['source']} mapped as {entry['unit']}", True)
            if previous and previous["unit"] != entry["unit"]:
                issue("unit_change", f"{name}: {previous['unit']}", f"{entry['source']}: {entry['unit']}")
            elif entry["origin"] == "user" and importer.COLUMNS[name][1] is not None:
                issue("unit_mapping", f"{name}: {importer._canonical_unit(name)}", f"{entry['source']}: {entry['unit']}")
        for message in plan["needs"] + plan["ambiguities"]:
            issue("column_mapping", "Explicit source field and unit", message, True)
        for field, value in expected.items():
            headers = [column["name"] for column in plan["columns"]
                       if importer._split_header(column["name"])[0] in
                       {field, *importer.COLUMNS.get(field, ("", None, ()))[2]}]
            mapped = columns.get(field, {}).get("source")
            if mapped and mapped not in headers:
                headers.append(mapped)
            if headers and (observed := _column_value(plan, headers)) != [value]:
                issue(field.removesuffix("_id") + "_drift", value, observed, True)
            declared = proposal["declared"].get(field)
            if declared and declared != value:
                issue(field.removesuffix("_id") + "_drift", value, declared, True)
            elif not declared and not headers:
                issue("context_confirmation", value, f"Confirm {field} from the export or testing log.")
        for field, value in {"protocol_name": protocol["name"], "test_protocol_name": protocol["name"],
                             "protocol_version": protocol["version"], "protocol_revision": protocol["version"],
                             "source_name": source["name"], "dataset_identity": source["dataset_identity"],
                             "serial_number": instrument["serial_number"],
                             "coordinate_system": protocol["coordinate_convention"]}.items():
            headers = [col["name"] for col in plan["columns"] if importer._split_header(col["name"])[0] == field]
            if headers and (observed := _column_value(plan, headers)) != [str(value)]:
                issue("source_metadata_drift", f"{field}: {value}", observed, True)
        if plan["mapping"]["family"] != FAMILY:
            issue("measurement_family", FAMILY, plan["mapping"]["family"] or "Unresolved", True)
        if plan["state"] != "READY" or plan["mapping"]["family"] != FAMILY:
            return result, None
        incoming = importer.read_summary(plan)
        for field in IDENTITY_FIELDS:
            if field not in incoming.columns or incoming[field].null_count():
                issue("missing_identity", field, "Required on every row", True)
        if any(not incoming[name].is_finite().fill_null(True).all()
               for name, dtype in incoming.schema.items() if dtype.is_float()):
            issue("invalid_measurement", "Finite numbers", "NaN or infinity", True)
        if "week" in incoming.columns and not incoming["week"].eq(incoming["week"].floor()).fill_null(False).all():
            issue("session_time", "Integer study week", "Missing or fractional week", True)
        if incoming["sampling_hz"].unique().to_list() != [protocol["sampling_hz"]]:
            issue("timebase_drift", protocol["sampling_hz"], incoming["sampling_hz"].unique().sort().to_list(), True)
        if incoming.is_empty():
            issue("empty_file", "At least one trial", "No data rows", True)
        if any(row["blocked"] for row in result["discrepancies"]):
            return result, None

        roster = set(old["subject_id"])
        sessions = set(old["session_id"])
        result["identity_options"] = {"athletes": sorted(roster), "sessions": sorted(sessions)}
        approvals = [row for row in records if row["state"] == "APPROVED" and row["context"].get("source_id") == source["id"]]
        def bindings(field: str) -> dict:
            return {row["source"]: row["target"] for event in approvals for row in event["identity_preview"][field]}
        athletes, people = _identity_map("athlete", sorted(set(incoming["subject_id"])), roster,
                                         proposal["athletes"], bindings("athletes"), issue)
        mapped_sessions, visits = _identity_map("session", sorted(set(incoming["session_id"])), sessions,
                                               proposal["sessions"], bindings("sessions"), issue, new_sessions=True)
        result["identity_preview"] = {"athletes": people, "sessions": visits}
        if any(row["blocked"] for row in result["discrepancies"]):
            return result, None
        incoming = incoming.with_columns(pl.col("subject_id").replace_strict(athletes),
                                         pl.col("session_id").replace_strict(mapped_sessions),
                                         pl.lit(instrument["id"]).alias("instrument_id"),
                                         pl.lit(protocol["id"]).alias("protocol_id"))
        canonical = set(old.columns) - {"source_artifact_id", "_instrument_default"}
        if set(incoming.columns) != canonical or any(incoming.schema[column] != old.schema[column] for column in canonical):
            issue("canonical_schema", sorted(canonical), sorted(incoming.columns), True)
            return result, None
        for group in incoming.partition_by("session_id", maintain_order=True):
            session = group["session_id"][0]
            _, flags = importer.split_rows(group, FAMILY)
            weeks = group["week"].unique().sort().to_list()
            before = old.filter(pl.col("session_id") == session)["week"].unique().sort().to_list()
            result["sessions_qc"].append({"session": session, "weeks": weeks, "rows": group.height,
                                           "flagged": flags.height, "reasons": sorted(set(flags["qc_flag"]))})
            if len(weeks) != 1 or (before and before != weeks):
                issue("session_time_conflict", before or "One week per session", f"{session}: {weeks}", True)
            if flags.height:
                issue("row_qc", f"{session}: all rows pass", sorted(set(flags["qc_flag"])), True)
        if incoming["trial_id"].n_unique() != incoming.height:
            issue("trial_conflict", "A trial ID appears once per file", "Duplicate trial IDs", True)
        if any(row["blocked"] for row in result["discrepancies"]):
            return result, None

        old_rows = {row["trial_id"]: row for row in old.select(sorted(canonical)).iter_rows(named=True)}
        keep, duplicates, corrections = [], [], []
        columns_for_preview = sorted(canonical & METRICS)
        for row in incoming.sort("trial_id").iter_rows(named=True):
            key = row["trial_id"]
            original = old_rows.get(key)
            status = "New measurement"
            differences = {}
            if original is not None:
                differences = {name: [original[name], value] for name, value in row.items()
                               if _changed(name, original[name], value)}
                if not differences:
                    duplicates.append(key)
                    status = "Duplicate measurement"
                elif not set(differences) <= METRICS:
                    issue("trial_identity_conflict", {k: original[k] for k in IDENTITY_FIELDS},
                          {k: row[k] for k in IDENTITY_FIELDS}, True)
                    status = "Identity or acquisition conflict"
                else:
                    corrections.append(key)
                    keep.append(key)
                    status = "Correction"
            else:
                keep.append(key)
            if len(result["rows_preview"]) < PREVIEW_LIMIT:
                result["rows_preview"].append({"trial": key, "athlete": row["subject_id"], "session": row["session_id"],
                                               "classification": status, "changes": differences or
                                               {k: [None, row[k]] for k in columns_for_preview if original is None}})
        result["corrections"] = corrections
        result["counts"] = {"new": len(keep) - len(corrections), "duplicate": len(duplicates), "correction": len(corrections)}
        if not keep:
            issue("duplicate_measurements", "No new or corrected trials", f"{len(duplicates)} repeated trials", True)
        if any(row["blocked"] for row in result["discrepancies"]):
            return result, None
        stage = importer.stage(plan, context, _reconciled=incoming.filter(pl.col("trial_id").is_in(keep)))
        result["quality"] = stage["quality"]
        result["import_receipt_id"] = stage["receipt"]["id"]
        if not stage["eligible"]:
            issue("admission_qc", "Eligible admission with matching rights", stage["quality"]["status"], True)
        result["ready"] = stage["eligible"] and not any(
            row["kind"] == "context_confirmation" for row in result["discrepancies"])
        return result, stage
    except (ValueError, OSError, LookupError, pl.exceptions.PolarsError) as error:
        issue("input_validation", "Valid source and reference", str(error), True)
        return result, None


def decide(workspace_id: str, batch_id: str, version: int, action: str, *, reviewer: str, reason: str) -> dict:
    reviewer, reason = reviewer.strip(), reason.strip()
    if action not in {"APPROVED", "REJECTED", "QUARANTINED"} or not reviewer or not reason:
        raise store.ResearchValidation("Choose a decision and record the reviewer and reason.")
    if len(reviewer) > 150 or len(reason) > 2000:
        raise store.ResearchValidation("Use a reviewer name up to 150 characters and a reason up to 2,000 characters.")
    revision_id = None
    try:
        with store._tx() as connection:
            entry = _latest(workspace_id, batch_id, version)
            if entry["state"] != "PROPOSED":
                raise store.ResearchConflict("This proposal version already has a decision.")
            decision = {"reviewer": reviewer, "reason": reason, "proposal_version": version}
            if action != "APPROVED":
                return _event(connection, entry, state=action, decision=decision)
            revision = _workspace(workspace_id, entry["base_revision"])
            evaluated, staged = _evaluate(entry, revision, history(workspace_id))
            if not evaluated["ready"] or not staged:
                blockers = [str(row["incoming"]) for row in evaluated["discrepancies"]
                            if row["blocked"] or row["kind"] == "context_confirmation"]
                raise importer.ImportBlocked("Approval requires a compatible, verified proposal. " + " · ".join(blockers[:4]))
            if any(value != entry[key] for key, value in evaluated.items()):
                raise store.ResearchConflict("The reconciliation context changed. Refresh the proposal before approving.")
            admitted = importer.admit(staged)
            snapshot_id = admitted.get("dataset_snapshot_id")
            if not snapshot_id:
                raise importer.ImportBlocked("The existing admission gate did not admit this batch.")
            revision_id = store._new_id("DATA-U")
            store.attach_workspace_data(workspace_id, snapshot_id, append=True, confirm_participant_ids=True,
                                        base_revision=revision["id"], _reconciliation={
                                            "id": batch_id, "version": version + 1,
                                            "corrections": evaluated["corrections"]}, _revision_id=revision_id)
            decision.update(snapshot_id=snapshot_id, revision_id=revision_id, admission_record_id=admitted["id"])
            return _event(connection, entry, state=action, decision=decision)
    except BaseException:
        # SQLite rolls back the decision and revision together. The independently admitted source
        # snapshot is reusable on retry; the unreferenced analytical copy belongs to this attempt.
        if revision_id and store.get_data_revision(revision_id) is None:
            directory = paths()["research"] / "data" / revision_id
            if directory.exists():
                shutil.rmtree(directory)
        raise

