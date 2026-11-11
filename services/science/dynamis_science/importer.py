"""One-click scientific import (RES-636): probe -> propose mapping -> normalize -> stage QC -> admit.

A thin front end over admission.py: it never validates or stores science itself. It turns a CSV/Parquet
file into the canonical admission schema (canonical names and units), registers the source/instrument/
protocol through the existing registries, ingests the normalized table as a source artifact, and lets the
existing QC and snapshot code decide. Nothing physical is invented: calibration, rights, subject and
trial identity must come from the file or from the researcher.
"""

from __future__ import annotations

import csv
import hashlib
import io
import os
import re
import shutil
from pathlib import Path
from typing import Any

import polars as pl

from . import admission
from .contracts import utc_now
from .data_root import paths

ADAPTER_VERSION = "dynamis-import@0.1.0"
MAX_FILES = 100
MAX_FILE_BYTES = 256 * 1024 * 1024
PREVIEW_ROWS = 8
SUFFIXES = {".csv": "CSV", ".parquet": "PARQUET", ".pq": "PARQUET"}
ADMITTABLE = {"ADMITTED", "ADMITTED_WITH_WARNINGS"}


class ImportBlocked(ValueError):
    """The import cannot continue without a researcher decision; the message says why."""


# canonical column -> (family, canonical unit, {unit: factor to canonical}, aliases)
_MASS = {"kg": 1.0, "g": 0.001, "lb": 0.45359237}
_CM = {"cm": 1.0, "m": 100.0, "mm": 0.1, "in": 2.54}
_M = {"m": 1.0, "cm": 0.01, "mm": 0.001}
_S = {"s": 1.0, "ms": 0.001}
_N = {"n": 1.0, "kn": 1000.0}
_ONE = {"": 1.0}
_ID = None
COLUMNS: dict[str, tuple[str, dict[str, float] | None, tuple[str, ...]]] = {
    "subject_id": ("ANY", _ID, ("subject", "athlete", "athlete_id", "participant", "participant_id", "player", "player_id")),
    "session_id": ("ANY", _ID, ("session", "test_session")),
    "trial_id": ("ANY", _ID, ("trial", "rep", "repetition", "test_id", "trial_number")),
    "instrument_id": ("ANY", _ID, ("instrument", "device", "device_id", "plate")),
    "protocol_id": ("ANY", _ID, ("protocol",)),
    "sampling_hz": ("ANY", {"hz": 1.0}, ("sample_rate", "sampling_rate", "sampling_frequency", "fs", "frequency")),
    "week": ("ANY", _ONE, ()),
    "body_mass_kg": ("CMJ", _MASS, ("body_mass", "bodymass", "mass", "body_weight")),
    "jump_height_cm": ("CMJ", _CM, ("jump_height", "cmj_height")),
    "concentric_impulse_n_s_kg": ("CMJ", {"ns/kg": 1.0}, ("concentric_impulse",)),
    "eccentric_braking_impulse_n_s_kg": ("CMJ", {"ns/kg": 1.0}, ("eccentric_braking_impulse", "braking_impulse")),
    "eccentric_braking_duration_s": ("CMJ", _S, ("eccentric_braking_duration", "braking_duration")),
    "countermovement_depth_cm": ("CMJ", _CM, ("countermovement_depth", "cm_depth")),
    "peak_force_n": ("CMJ", _N, ("peak_force",)),
    "peak_power_w_kg": ("CMJ", {"w/kg": 1.0}, ("peak_power",)),
    "rsi_mod": ("CMJ", {"m/s": 1.0, "": 1.0}, ("rsi_modified", "rsimod")),
    "distance_m": ("SPRINT", _M, ("distance", "sprint_distance")),
    "time_s": ("SPRINT", _S, ("time", "sprint_time", "split_time")),
}
_ALIAS = {alias: name for name, (_, _, aliases) in COLUMNS.items() for alias in (name, *aliases)}
_UNIT_SYNONYMS = {"sec": "s", "secs": "s", "second": "s", "seconds": "s", "milliseconds": "ms", "centimeters": "cm",
                  "centimetres": "cm", "meters": "m", "metres": "m", "kilograms": "kg", "grams": "g", "pounds": "lb",
                  "lbs": "lb", "newton": "n", "newtons": "n", "hertz": "hz", "nsperkg": "ns/kg", "ns/kg": "ns/kg"}
FAMILIES = {"CMJ": "CMJ_FORCE_PLATFORM", "SPRINT": "SPRINT_TIMING"}
CANONICAL_UNITS = {"CMJ_FORCE_PLATFORM": {"body_mass": "kg", "time": "s", "distance": "cm"},
                   "SPRINT_TIMING": {"time": "s", "distance": "m"}}
CONSTANT_FIELDS = ("session_id", "sampling_hz", "coordinate_system")  # researcher-supplied, never invented


def _unit_key(unit: str) -> str:
    key = re.sub(r"[\s·*.]", "", unit.strip().lower()).replace("per", "/")
    return _UNIT_SYNONYMS.get(key, key)


def _split_header(header: str) -> tuple[str, str | None]:
    match = re.match(r"^(.*?)[\s_]*[(\[]\s*([^)\]]*?)\s*[)\]]\s*$", header.strip())
    base, unit = (match.group(1), match.group(2)) if match else (header, None)
    return re.sub(r"[^a-z0-9]+", "_", base.strip().lower()).strip("_"), unit


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_table(path: Path) -> tuple[pl.DataFrame, dict[str, Any]]:
    """Read a CSV (UTF-8/BOM, common delimiters) or Parquet file; raise ImportBlocked when unreadable."""
    kind = SUFFIXES.get(path.suffix.lower())
    if kind is None:
        raise ImportBlocked(f"Unsupported format '{path.suffix}'. Supported: CSV, Parquet.")
    if path.stat().st_size == 0:
        raise ImportBlocked("The file is empty.")
    try:
        if kind == "PARQUET":
            return pl.read_parquet(path), {"format": kind}
        text = path.read_bytes().decode("utf-8-sig")
        sample = text[:8192]
        try:
            delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
        except csv.Error:
            delimiter = ","
        header = next(csv.reader(io.StringIO(text), delimiter=delimiter), [])
        duplicates = sorted({h for h in header if header.count(h) > 1})
        if duplicates:
            raise ImportBlocked(f"Duplicate column names: {', '.join(duplicates)}.")
        frame = pl.read_csv(io.StringIO(text), separator=delimiter, infer_schema_length=1000)
        return frame, {"format": kind, "delimiter": delimiter}
    except ImportBlocked:
        raise
    except UnicodeDecodeError as error:
        raise ImportBlocked("The file is not UTF-8 text.") from error
    except Exception as error:  # polars raises many types for malformed input
        raise ImportBlocked(f"The file could not be parsed ({type(error).__name__}).") from error


def schema_fingerprint(frame: pl.DataFrame) -> str:
    layout = [(name, "numeric" if dtype.is_numeric() else str(dtype)) for name, dtype in frame.schema.items()]
    return hashlib.sha256(repr(layout).encode()).hexdigest()[:16]


# ---------------------------------------------------------------- Adapter contract
# An adapter is (detect -> propose -> normalize). The generic adapter handles canonical/aliased headers;
# vendor adapters (see vendor.py) add profiles only when verified against a documented sample.

def propose_generic(frame: pl.DataFrame) -> tuple[dict[str, Any], list[str]]:
    """Propose {canonical: {source, unit, confidence, origin}} and the ambiguities found."""
    candidates: dict[str, list[dict[str, Any]]] = {}
    ambiguities: list[str] = []
    for header in frame.columns:
        base, bracket = _split_header(header)
        name = _ALIAS.get(base)
        if name is None:
            continue
        _, units, _ = COLUMNS[name]
        exact = header == name
        unit = None
        confidence = 1.0 if exact else 0.8
        if units is None:
            unit = ""
        elif exact:
            unit = _canonical_unit(name)
        elif bracket is not None:
            unit = _unit_key(bracket)
            if unit not in units:
                ambiguities.append(f"'{header}': unit '{bracket}' is not supported for {name}; choose a supported unit.")
                unit, confidence = None, 0.3
        elif name in ("rsi_mod", "week"):
            unit = ""
        else:
            ambiguities.append(f"'{header}': the unit is not stated; choose one for {name}.")
            confidence = 0.4
        candidates.setdefault(name, []).append({"source": header, "unit": unit, "confidence": confidence, "origin": "detected"})
    columns = {}
    for name, found in candidates.items():
        if len(found) > 1:
            ambiguities.append(f"{name}: several columns match ({', '.join(c['source'] for c in found)}); choose one.")
        elif found[0]["unit"] is not None:
            columns[name] = found[0]
    return columns, ambiguities


def _canonical_unit(name: str) -> str:
    units = COLUMNS[name][1] or {}
    return next((u for u, f in units.items() if f == 1.0 and (u or name.endswith("rsi_mod"))), next(iter(units), ""))


def detect_family(columns: dict[str, Any]) -> str | None:
    cmj = sum(COLUMNS[c][0] == "CMJ" for c in columns)
    sprint = sum(COLUMNS[c][0] == "SPRINT" for c in columns)
    if cmj and sprint == 2:
        return None  # both families plausible: the researcher decides
    return FAMILIES["CMJ"] if cmj else FAMILIES["SPRINT"] if sprint == 2 else None


def outstanding(mapping: dict[str, Any]) -> list[str]:
    """What the researcher must still decide before this file can be staged."""
    columns, constants, family = mapping["columns"], mapping.get("constants", {}), mapping.get("family")
    if family is None:
        return ["measurement family not recognised; map at least one measurement column"]
    need = ["subject_id", "trial_id"] + (["distance_m", "time_s"] if family == "SPRINT_TIMING" else [])
    missing = [f"{n} column" for n in need if n not in columns]
    if "session_id" not in columns and not str(constants.get("session_id", "")).strip():
        missing.append("session_id (column or a value you supply)")
    if family == "CMJ_FORCE_PLATFORM":
        if "sampling_hz" not in columns and not constants.get("sampling_hz"):
            missing.append("sampling_hz (column or a value you supply; it is never assumed)")
        if not any(COLUMNS[c][0] == "CMJ" for c in columns):
            missing.append("at least one CMJ measurement column")
    return missing


# ---------------------------------------------------------------- Probe
def probe_file(path: str | os.PathLike[str]) -> dict[str, Any]:
    path = Path(path)
    plan: dict[str, Any] = {"path": str(path), "name": path.name, "state": "UNSUPPORTED", "ambiguities": [], "warnings": []}
    try:
        resolved = path.resolve(strict=True)
        if not resolved.is_file():
            raise ImportBlocked("Not a regular file.")
        size = resolved.stat().st_size
        if size > MAX_FILE_BYTES:
            raise ImportBlocked(f"File is larger than the {MAX_FILE_BYTES // (1 << 20)} MiB import limit.")
        frame, info = read_table(resolved)
    except (ImportBlocked, OSError) as error:
        plan["reason"] = str(error)
        return plan
    columns, ambiguities = propose_generic(frame)
    mapping = {"family": detect_family(columns), "columns": columns, "constants": {}}
    plan.update(
        info,
        raw_sha256=_sha256(resolved), size_bytes=size, rows=frame.height,
        columns=[{"name": n, "dtype": str(d)} for n, d in frame.schema.items()],
        schema_fingerprint=schema_fingerprint(frame), adapter="generic", mapping=mapping,
        ambiguities=ambiguities,
        preview={"columns": frame.columns, "rows": [[("" if v is None else str(v)) for v in row] for row in frame.head(PREVIEW_ROWS).rows()]},
    )
    _refresh_state(plan)
    return plan


def _refresh_state(plan: dict[str, Any]) -> None:
    plan["needs"] = outstanding(plan["mapping"])
    plan["state"] = "READY" if not plan["needs"] and not plan["ambiguities"] else "REVIEW"


def probe_folder(folder: str | os.PathLike[str]) -> dict[str, Any]:
    """Bounded, non-recursive enumeration; symlinks, oversize and out-of-folder files are skipped and reported."""
    root = Path(folder).resolve(strict=True)
    plans, skipped = [], []
    for entry in sorted(os.scandir(root), key=lambda e: e.name.lower()):
        suffix = Path(entry.name).suffix.lower()
        if suffix not in SUFFIXES or entry.name.startswith((".", "~")):
            continue
        if entry.is_symlink() or not entry.is_file(follow_symlinks=False) or Path(entry.path).resolve().parent != root:
            skipped.append({"name": entry.name, "reason": "symbolic link or path outside the folder"})
        elif len(plans) >= MAX_FILES:
            skipped.append({"name": entry.name, "reason": f"more than {MAX_FILES} files; import in batches"})
        else:
            plans.append(probe_file(entry.path))
    return {"kind": "folder", "path": str(root), "files": plans, "skipped": skipped}


def probe(path: str | os.PathLike[str]) -> dict[str, Any]:
    target = Path(path)
    return probe_folder(target) if target.is_dir() else {"kind": "file", "path": str(target), "files": [probe_file(target)], "skipped": []}


def edit_mapping(plan: dict[str, Any], edits: dict[str, dict[str, Any] | None], constants: dict[str, Any] | None = None) -> dict[str, Any]:
    """Apply researcher edits: {canonical: {"source","unit"} | None}. Edited entries are marked origin=user."""
    columns = dict(plan["mapping"]["columns"])
    names = {c["name"] for c in plan["columns"]}
    for name, entry in edits.items():
        if name not in COLUMNS:
            raise ImportBlocked(f"Unknown target column {name}.")
        if entry is None:
            columns.pop(name, None)
            continue
        if entry["source"] not in names:
            raise ImportBlocked(f"Source column '{entry['source']}' is not in the file.")
        unit = _unit_key(entry.get("unit") or "") if COLUMNS[name][1] is not None else ""
        if COLUMNS[name][1] is not None and unit not in COLUMNS[name][1]:
            raise ImportBlocked(f"Unit '{entry.get('unit')}' is not supported for {name}.")
        columns[name] = {"source": entry["source"], "unit": unit, "confidence": 1.0, "origin": "user"}
    mapping = {"family": detect_family(columns), "columns": columns,
               "constants": {**plan["mapping"].get("constants", {}), **{k: v for k, v in (constants or {}).items() if k in CONSTANT_FIELDS}}}
    touched = {t for n, e in edits.items() if e for t in (n, e["source"])}
    edited = dict(plan, mapping=mapping, ambiguities=[a for a in plan["ambiguities"] if not any(t in a for t in touched)])
    _refresh_state(edited)
    return edited


# ---------------------------------------------------------------- Normalize
def normalize(frame: pl.DataFrame, mapping: dict[str, Any]) -> pl.DataFrame:
    """Canonical names and units only; every value comes from the file or a researcher constant."""
    family, constants = mapping["family"], mapping.get("constants", {})
    missing = outstanding(mapping)
    if missing:
        raise ImportBlocked("Mapping is incomplete: " + "; ".join(missing))
    out: dict[str, pl.Expr] = {}
    for name, entry in mapping["columns"].items():
        if entry["source"] not in frame.columns:
            raise ImportBlocked(f"Column '{entry['source']}' is missing from the file (schema changed).")
        units = COLUMNS[name][1]
        if units is None:
            out[name] = pl.col(entry["source"]).cast(pl.Utf8).str.strip_chars().replace("", None).alias(name)
        else:
            try:
                frame[entry["source"]].cast(pl.Float64, strict=True)
            except Exception as error:
                raise ImportBlocked(f"Column '{entry['source']}' contains non-numeric values.") from error
            out[name] = (pl.col(entry["source"]).cast(pl.Float64) * units[entry["unit"]]).alias(name)
    if "session_id" not in out:
        out["session_id"] = pl.lit(str(constants["session_id"]).strip()).alias("session_id")
    if family == "CMJ_FORCE_PLATFORM" and "sampling_hz" not in out:
        out["sampling_hz"] = pl.lit(float(constants["sampling_hz"])).alias("sampling_hz")
    return frame.select(list(out.values()))


def _single(frame: pl.DataFrame, column: str, what: str) -> str | None:
    if column not in frame.columns:
        return None
    values = sorted({str(v) for v in frame[column].drop_nulls().to_list()})
    if len(values) > 1:
        raise ImportBlocked(f"The file contains several {what} ({', '.join(values[:4])}); split it so each file has one.")
    return values[0] if values else None


# ---------------------------------------------------------------- Context (source / instrument / protocol)
def _digest(*parts: Any) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:8].upper()


def build_context(fields: dict[str, Any]) -> dict[str, Any]:
    """Registry payloads from researcher-entered fields. Ids are deterministic, so repeats are idempotent."""
    fixture = fields.get("privacy_status") == "TEST_FIXTURE"
    calibration = (fields.get("calibration_status") or "UNKNOWN").strip().upper()
    if fixture and calibration == "UNKNOWN":
        calibration = "SIMULATED"  # a fixture has no physical calibration; never imply one
    source = {
        "id": fields.get("source_id") or "SRC-IMP-" + _digest(fields.get("source_name"), fields.get("publisher"), fields.get("dataset_identity")),
        "name": fields.get("source_name", ""), "publisher": fields.get("publisher", ""),
        "dataset_identity": fields.get("dataset_identity", ""), "version": fields.get("version", "1"),
        "acquisition_method": fields.get("acquisition_method", "Local file import"),
        "license_or_agreement": fields.get("license_or_agreement", ""),
        "permitted_uses": list(fields.get("permitted_uses") or ["research"]),
        "redistribution_restrictions": fields.get("redistribution_restrictions", ""),
        "privacy_status": fields.get("privacy_status", "NOT_APPLICABLE"),
        "rights_status": "FIXTURE_ONLY" if fixture else "UNVERIFIED",
    }
    instrument = {"manufacturer": fields.get("manufacturer", ""), "model": fields.get("model", ""),
                  "serial_number": fields.get("serial_number", ""), "calibration_status": calibration,
                  "calibration_date": fields.get("calibration_date")}
    protocol = {"name": fields.get("protocol_name", ""), "version": fields.get("protocol_version", "1.0"),
                "coordinate_convention": fields.get("coordinate_system") or "NOT_SPECIFIED"}
    return {"source": source, "instrument": instrument, "protocol": protocol}


def _ensure(kind: str, existing: dict[str, Any] | None, payload: dict[str, Any], keys: tuple[str, ...], register) -> dict[str, Any]:
    if existing is None:
        return register(payload)
    changed = [k for k in keys if k in payload and existing.get(k) != payload[k]]
    if changed:
        raise ImportBlocked(f"{kind} {payload['id']} is already registered with different {', '.join(changed)}; "
                            "a registered record is never silently changed.")
    return existing


# ---------------------------------------------------------------- Stage (register + ingest + QC) and decide
def _receipts() -> list[dict[str, Any]]:
    return admission._load_list(paths()["artifacts"] / "import_receipts.json")


def _save_receipt(receipt: dict[str, Any]) -> None:
    items = [r for r in _receipts() if r["id"] != receipt["id"]]
    admission._save_list(paths()["artifacts"] / "import_receipts.json", items + [receipt])


def list_receipts() -> list[dict[str, Any]]:
    return _receipts()


def stage(plan: dict[str, Any], context: dict[str, Any], *, rights_reviewed_by: str = "") -> dict[str, Any]:
    """Normalize one file and run the existing QC. Registers/ingests but does not admit."""
    if plan["state"] == "UNSUPPORTED":
        raise ImportBlocked(plan.get("reason", "Unsupported file."))
    if plan["state"] != "READY":
        raise ImportBlocked("Review required before import: " + "; ".join(plan["needs"] + plan["ambiguities"]))
    path = Path(plan["path"])
    raw_sha = _sha256(path)
    if raw_sha != plan["raw_sha256"]:
        raise ImportBlocked("The file changed after it was reviewed; probe it again.")
    frame, _ = read_table(path)
    mapping = plan["mapping"]
    if schema_fingerprint(frame) != plan["schema_fingerprint"]:
        raise ImportBlocked("The file schema changed after it was reviewed.")
    family = mapping["family"]
    # ids come from the file when present (one per file), otherwise derive from the entered instrument/protocol
    ctx_i, ctx_p, src = context["instrument"], context["protocol"], context["source"]
    normalized = normalize(frame, mapping)
    sampling = _single(normalized, "sampling_hz", "sampling rates")
    units = CANONICAL_UNITS[family]
    instrument_id = _single(normalized, "instrument_id", "instruments") or "INST-IMP-" + _digest(
        ctx_i["manufacturer"], ctx_i["model"], ctx_i["serial_number"], ctx_i["calibration_status"],
        ctx_i["calibration_date"], family)
    protocol_id = _single(normalized, "protocol_id", "protocols") or "PROT-IMP-" + _digest(
        ctx_p["name"], ctx_p["version"], family, sampling)
    normalized = normalized.with_columns(
        *(pl.lit(v).alias(k) for k, v in (("instrument_id", instrument_id), ("protocol_id", protocol_id)) if k not in normalized.columns))
    metadata: dict[str, Any] = {"units": units, "instrument_default": instrument_id, "protocol_default": protocol_id,
                                "import": {"adapter": plan["adapter"], "adapter_version": ADAPTER_VERSION,
                                           "raw_sha256": raw_sha, "schema_fingerprint": plan["schema_fingerprint"]}}
    constants = mapping.get("constants", {})
    if constants.get("coordinate_system"):
        metadata["coordinate_system"] = constants["coordinate_system"]

    source = _ensure("Source", admission.get_source(src["id"]), src,
                     ("name", "publisher", "dataset_identity", "version", "license_or_agreement",
                      "redistribution_restrictions", "privacy_status"), admission.register_source)
    if source.get("rights_status") == "UNVERIFIED" and rights_reviewed_by:
        admission.verify_rights(src["id"], rights_reviewed_by)
    _ensure("Instrument", admission.get_instrument(instrument_id),
            {"id": instrument_id, "measurement_family": family, **ctx_i, "sampling_capabilities_hz": [float(sampling)] if sampling else []},
            ("measurement_family", "manufacturer", "model", "serial_number", "calibration_status"), admission.register_instrument)
    _ensure("Protocol", admission.get_protocol(protocol_id),
            {"id": protocol_id, "measurement_family": family, "name": ctx_p["name"], "version": ctx_p["version"],
             "sampling_hz": float(sampling or 1),  # sprint timing has no sampling rate; 1 is a placeholder the QC never reads
             "units": units, "coordinate_convention": ctx_p["coordinate_convention"]},
            ("measurement_family", "name", "version", "units"), admission.register_protocol)

    buffer = io.BytesIO()
    normalized.write_parquet(buffer, compression="zstd")
    data = buffer.getvalue()
    name = f"{path.stem}.normalized.parquet"
    duplicate_of = next((a["id"] for a in admission.list_source_artifacts() if a["source_id"] == src["id"]
                         and a["content_hash_sha256"] == hashlib.sha256(data).hexdigest() and a["original_filename"] != name), None)
    artifact = admission.ingest_source_artifact(src["id"], name, data, "one_click_import")
    raw_dir = paths()["sources"] / src["id"] / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_copy = raw_dir / f"{raw_sha[:12]}-{path.name}"
    if not raw_copy.exists():
        shutil.copyfile(path, raw_copy)
    validate = admission.validate_cmj if family == "CMJ_FORCE_PLATFORM" else admission.validate_sprint
    quality = validate(artifact, metadata)
    rights = (admission.get_source(src["id"]) or {}).get("rights_status", "UNVERIFIED")
    eligible = quality["status"] in ADMITTABLE and rights in {"VERIFIED", "FIXTURE_ONLY"} and duplicate_of is None
    receipt = {
        "id": "IR-" + hashlib.sha256(f"{raw_sha}:{artifact['id']}".encode()).hexdigest()[:12].upper(),
        "raw_filename": path.name, "raw_sha256": raw_sha, "raw_size_bytes": plan["size_bytes"], "raw_copy": str(raw_copy),
        "schema_fingerprint": plan["schema_fingerprint"], "columns": plan["columns"], "adapter": plan["adapter"],
        "adapter_version": ADAPTER_VERSION, "mapping": mapping, "family": family, "admission_metadata": metadata,
        "source_id": src["id"], "source_artifact_id": artifact["id"], "quality_assessment_id": quality["id"],
        "normalized_rows": normalized.height, "dropped_columns": [c["name"] for c in plan["columns"] if c["name"] not in
                                                                   {e["source"] for e in mapping["columns"].values()}],
    }
    previous = next((r for r in _receipts() if r["id"] == receipt["id"]), None)
    receipt.update(created_at=previous["created_at"] if previous else utc_now(), decision=previous["decision"] if previous else "STAGED")
    receipt["admission_record_id"] = previous.get("admission_record_id") if previous else None
    _save_receipt(receipt)
    return {"receipt": receipt, "artifact": artifact, "quality": quality, "rights_status": rights, "eligible": eligible,
            "duplicate_of": duplicate_of, "synthetic_only": rights == "FIXTURE_ONLY"}


def admit(staged: dict[str, Any]) -> dict[str, Any]:
    """Admit through the existing gate. Returns the admission record (never bypasses QC or rights)."""
    receipt = staged["receipt"]
    if staged.get("duplicate_of"):
        raise ImportBlocked(f"This content duplicates source artifact {staged['duplicate_of']}; it was not admitted again.")
    record = admission.admit_artifact(receipt["source_artifact_id"], receipt["family"], receipt["admission_metadata"])
    _save_receipt(dict(receipt, decision=record["status"], admission_record_id=record["id"]))
    return record


def quarantine(staged: dict[str, Any], reason: str = "") -> dict[str, Any]:
    """Keep the raw file in the quarantine area; record the QC outcome without creating a snapshot."""
    receipt = staged["receipt"]
    hold = paths()["quarantine"] / receipt["id"]
    hold.mkdir(parents=True, exist_ok=True)
    target = hold / Path(receipt["raw_copy"]).name
    if not target.exists():
        shutil.copyfile(receipt["raw_copy"], target)
    record = None
    if not staged["eligible"]:
        record = admission.admit_artifact(receipt["source_artifact_id"], receipt["family"], receipt["admission_metadata"])
    _save_receipt(dict(receipt, decision="QUARANTINED", quarantine_reason=reason or "researcher decision",
                       admission_record_id=record["id"] if record else None))
    return {"receipt_id": receipt["id"], "quarantine_path": str(target), "admission_record": record}


# ---------------------------------------------------------------- Presets
def _presets() -> list[dict[str, Any]]:
    return admission._load_list(paths()["artifacts"] / "import_presets.json")


def list_presets() -> list[dict[str, Any]]:
    return _presets()


def save_preset(name: str, plan: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Versioned preset keyed to the schema fingerprint; earlier versions are kept."""
    if not name.strip():
        raise ImportBlocked("A preset needs a name.")
    if plan["state"] != "READY":
        raise ImportBlocked("Resolve the open mapping questions before saving a preset.")
    items = _presets()
    same = [p for p in items if p["name"] == name.strip() and p["schema_fingerprint"] == plan["schema_fingerprint"]]
    preset = {"id": f"PRESET-{_digest(name.strip(), plan['schema_fingerprint'])}-v{len(same) + 1}", "name": name.strip(),
              "version": len(same) + 1, "schema_fingerprint": plan["schema_fingerprint"], "adapter": plan["adapter"],
              "mapping": plan["mapping"], "context": context, "created_at": utc_now()}
    admission._save_list(paths()["artifacts"] / "import_presets.json", items + [preset])
    return preset


def match_preset(plan: dict[str, Any]) -> dict[str, Any] | None:
    """Latest preset with the identical schema fingerprint. A different schema never reuses a mapping."""
    same = [p for p in _presets() if p["schema_fingerprint"] == plan.get("schema_fingerprint")]
    return max(same, key=lambda p: p["version"], default=None)


def schema_drift(plan: dict[str, Any]) -> dict[str, Any] | None:
    """Closest preset whose columns differ from this file: report added/removed columns for review."""
    have = {c["name"] for c in plan.get("columns", [])}
    best = None
    for preset in _presets():
        used = {e["source"] for e in preset["mapping"]["columns"].values()}
        if used and len(used & have) >= max(1, len(used) // 2) and preset["schema_fingerprint"] != plan["schema_fingerprint"]:
            best = {"preset": preset["id"], "missing_columns": sorted(used - have), "preset_name": preset["name"]}
    return best


def import_with_preset(path: str | os.PathLike[str], preset: dict[str, Any]) -> dict[str, Any]:
    """Repeat import: identical verified schema stages with the saved mapping; drift raises for review."""
    plan = probe_file(path)
    if plan["state"] == "UNSUPPORTED":
        raise ImportBlocked(plan["reason"])
    if plan["schema_fingerprint"] != preset["schema_fingerprint"]:
        raise ImportBlocked(f"Schema differs from preset {preset['id']}; review the mapping instead of reusing it.")
    plan = dict(plan, mapping=preset["mapping"], ambiguities=[], preset=preset["id"])
    _refresh_state(plan)
    return stage(plan, preset["context"])
