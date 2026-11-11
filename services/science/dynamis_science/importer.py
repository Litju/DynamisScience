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
import codecs
import shutil
import uuid
from pathlib import Path
from typing import Any

import polars as pl
import pyarrow.parquet as pq

from . import admission, traces
from .contracts import utc_now
from .data_root import paths

ADAPTER_VERSION = "dynamis-import@0.1.0"
MAX_FILES = 100
MAX_FILE_BYTES = 256 * 1024 * 1024  # trial-level summary tables are read whole, so they are capped
MAX_TRACE_BYTES = 4 * 1024 * 1024 * 1024  # sample-level recordings are streamed; still an explicit limit
SCHEMA_ROWS = 10_000  # rows used to infer column types
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
_FORCE = {"n": 1.0, "kn": 1000.0, "lbf": 4.4482216152605}
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
    "sample_index": ("ANY", _ONE, ("sample", "sample_number", "frame", "index")),
    "force_z_n": ("TRACE", _FORCE, ("force", "vertical_force", "total_force", "fz", "force_z")),
    "force_left_n": ("TRACE", _FORCE, ("left_force", "leftforce", "force_left", "fz_left")),
    "force_right_n": ("TRACE", _FORCE, ("right_force", "rightforce", "force_right", "fz_right")),
    "force_combined_n": ("TRACE", _FORCE, ("combined_force", "combinedforce", "force_combined")),
    "distance_m": ("SPRINT", _M, ("distance", "sprint_distance")),
    "time_s": ("SPRINT", _S, ("time", "sprint_time", "split_time")),
}
_ALIAS = {alias: name for name, (_, _, aliases) in COLUMNS.items() for alias in (name, *aliases)}
_UNIT_SYNONYMS = {"sec": "s", "secs": "s", "second": "s", "seconds": "s", "milliseconds": "ms", "centimeters": "cm",
                  "centimetres": "cm", "meters": "m", "metres": "m", "kilograms": "kg", "grams": "g", "pounds": "lb",
                  "lbs": "lb", "newton": "n", "newtons": "n", "hertz": "hz", "nsperkg": "ns/kg", "ns/kg": "ns/kg"}
FAMILIES = {"CMJ": "CMJ_FORCE_PLATFORM", "SPRINT": "SPRINT_TIMING", "TRACE": traces.FAMILY}
CANONICAL_UNITS = {"CMJ_FORCE_PLATFORM": {"body_mass": "kg", "time": "s", "distance": "cm"},
                   "SPRINT_TIMING": {"time": "s", "distance": "m"}, traces.FAMILY: {"force": "N", "time": "s"}}
CONSTANT_FIELDS = ("session_id", "sampling_hz", "coordinate_system", "subject_id", "trial_id")  # researcher-supplied, never invented


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


def open_table(path: Path) -> tuple[pl.LazyFrame, dict[str, Any]]:
    """A lazy, streaming view of a CSV (UTF-8/BOM, common delimiters) or Parquet file; ImportBlocked when unreadable.

    Only the first 64 KiB is read here (delimiter, header, encoding); data are scanned lazily by the caller.
    """
    kind = SUFFIXES.get(path.suffix.lower())
    if kind is None:
        raise ImportBlocked(f"Unsupported format '{path.suffix}'. Supported: CSV, Parquet.")
    if path.stat().st_size == 0:
        raise ImportBlocked("The file is empty.")
    try:
        if kind == "PARQUET":
            return pl.scan_parquet(path), {"format": kind}
        with path.open("rb") as handle:
            head = handle.read(65536)
        text = codecs.getincrementaldecoder("utf-8-sig")().decode(head, final=False)  # tolerant of a cut multibyte tail
        try:
            delimiter = csv.Sniffer().sniff(text[:8192], delimiters=",;	|").delimiter
        except csv.Error:
            delimiter = ","
        header = next(csv.reader(io.StringIO(text), delimiter=delimiter), [])
        duplicates = sorted({h for h in header if header.count(h) > 1})
        if duplicates:
            raise ImportBlocked(f"Duplicate column names: {', '.join(duplicates)}.")
        return pl.scan_csv(path, separator=delimiter, infer_schema_length=SCHEMA_ROWS), {"format": kind, "delimiter": delimiter}
    except ImportBlocked:
        raise
    except UnicodeDecodeError as error:
        raise ImportBlocked("The file is not UTF-8 text.") from error
    except Exception as error:  # polars raises many types for malformed input
        raise ImportBlocked(f"The file could not be parsed ({type(error).__name__}).") from error


def _records(lazy: pl.LazyFrame) -> pl.LazyFrame:
    return lazy.filter(~pl.all_horizontal(pl.all().is_null()))  # blank lines carry no record


def schema_fingerprint(schema: pl.Schema) -> str:
    layout = [(name, "numeric" if dtype.is_numeric() else str(dtype)) for name, dtype in schema.items()]
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
        exact = header.lower() == name
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
        elif name in ("rsi_mod", "week", "sample_index"):
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
    count = {g: sum(COLUMNS[c][0] == g for c in columns) for g in ("CMJ", "SPRINT", "TRACE")}
    if count["TRACE"]:
        return None if count["CMJ"] else FAMILIES["TRACE"]  # trace channels with scalar metrics: researcher decides
    if count["CMJ"] and count["SPRINT"] == 2:
        return None  # both families plausible: the researcher decides
    return FAMILIES["CMJ"] if count["CMJ"] else FAMILIES["SPRINT"] if count["SPRINT"] == 2 else None


def outstanding(mapping: dict[str, Any]) -> list[str]:
    """What the researcher must still decide before this file can be staged."""
    columns, constants, family = mapping["columns"], mapping.get("constants", {}), mapping.get("family")
    if family is None:
        return ["measurement family not recognised; map at least one measurement column"]
    supplied = lambda key: bool(str(constants.get(key, "")).strip())  # noqa: E731
    if family == traces.FAMILY:
        missing = [f"{k} (a column, or one value you supply for a single-trace file)" for k in ("subject_id", "trial_id")
                   if k not in columns and not supplied(k)]
        if "time_s" not in columns and not ("sample_index" in columns and ("sampling_hz" in columns or supplied("sampling_hz"))):
            missing.append("time: a time column, or sample_index with a sampling_hz you supply (never assumed)")
    else:
        need = ["subject_id", "trial_id"] + (["distance_m", "time_s"] if family == "SPRINT_TIMING" else [])
        missing = [f"{n} column" for n in need if n not in columns]
    if "session_id" not in columns and not supplied("session_id"):
        missing.append("session_id (column or a value you supply)")
    if family == "CMJ_FORCE_PLATFORM":
        if "sampling_hz" not in columns and not constants.get("sampling_hz"):
            missing.append("sampling_hz (column or a value you supply; it is never assumed)")
        if not any(COLUMNS[c][0] == "CMJ" for c in columns):
            missing.append("at least one CMJ measurement column")
    return missing


# ---------------------------------------------------------------- Probe
def probe_file(path: str | os.PathLike[str]) -> dict[str, Any]:
    """Bounded probe: schema from the first rows, row count by a streaming scan, preview of 8 rows."""
    path = Path(path)
    plan: dict[str, Any] = {"path": str(path), "name": path.name, "state": "UNSUPPORTED", "ambiguities": [], "warnings": []}
    try:
        resolved = path.resolve(strict=True)
        if not resolved.is_file():
            raise ImportBlocked("Not a regular file.")
        size = resolved.stat().st_size
        if size > MAX_TRACE_BYTES:
            raise ImportBlocked(f"File is larger than the {MAX_TRACE_BYTES >> 30} GiB import limit; split it.")
        lazy, info = open_table(resolved)
        records = _records(lazy)
        schema = lazy.collect_schema()
        preview = records.head(PREVIEW_ROWS).collect()
        rows = int(records.select(pl.len()).collect().item())
    except (ImportBlocked, OSError) as error:
        plan["reason"] = str(error)
        return plan
    except Exception as error:
        plan["reason"] = f"The file could not be parsed ({type(error).__name__})."
        return plan
    columns, ambiguities = propose_generic(pl.DataFrame(schema=schema))
    mapping = {"family": detect_family(columns), "columns": columns, "constants": {}}
    plan.update(
        info,
        raw_sha256=_sha256(resolved), size_bytes=size, rows=rows,
        columns=[{"name": n, "dtype": str(d)} for n, d in schema.items()],
        schema_fingerprint=schema_fingerprint(schema), adapter="generic", mapping=mapping,
        ambiguities=ambiguities,
        preview={"columns": preview.columns, "rows": [[("" if v is None else str(v)) for v in row] for row in preview.rows()]},
    )
    _refresh_state(plan)
    if mapping["family"] != traces.FAMILY and size > MAX_FILE_BYTES:
        plan.update(state="UNSUPPORTED", reason=f"Trial-level tables above {MAX_FILE_BYTES >> 20} MiB are not imported; "
                    "only sample-level recordings are streamed.")
    elif mapping["family"] == traces.FAMILY and rows > traces.MAX_ROWS:
        plan.update(state="UNSUPPORTED", reason=f"More than {traces.MAX_ROWS:,} samples; split the recording.")
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


def _unique(lazy: pl.LazyFrame, column: str, what: str) -> str | None:
    """The single value of a column (as text); several values mean the file must be split, never merged."""
    values = sorted(str(v) for v in lazy.select(pl.col(column).cast(pl.Utf8)).unique().head(5).collect()[column].drop_nulls().to_list())
    if len(values) > 1:
        raise ImportBlocked(f"The file contains several {what} ({', '.join(values[:4])}); split it so each file has one.")
    return values[0] if values else None


def _text(mapping: dict[str, Any], name: str) -> pl.Expr:
    entry = mapping["columns"].get(name)
    if entry:
        return pl.col(entry["source"]).cast(pl.Utf8).str.strip_chars().replace("", None).alias(name)
    return pl.lit(str(mapping.get("constants", {}).get(name, "")).strip()).alias(name)


def _normalize_trace(lazy: pl.LazyFrame, mapping: dict[str, Any], context: dict[str, Any]) -> tuple[pl.LazyFrame, dict[str, Any]]:
    """Lazy normalization of a sample-level recording. Returns the stream and the facts needed for registration."""
    columns, constants = mapping["columns"], mapping.get("constants", {})
    missing = outstanding(mapping)
    if missing:
        raise ImportBlocked("Mapping is incomplete: " + "; ".join(missing))
    # sampling: declared (a value you supplied or a file column), else estimated from the timestamps and labelled so
    hz: float | None = None
    source = "declared"
    if "sampling_hz" in columns:
        value = _unique(lazy, columns["sampling_hz"]["source"], "sampling rates")
        hz = float(value) if value else None
    elif str(constants.get("sampling_hz", "")).strip():
        hz = float(constants["sampling_hz"])
    if hz is not None and hz <= 0:
        raise ImportBlocked("The sampling rate must be positive.")
    exprs: dict[str, pl.Expr] = {name: _text(mapping, name) for name in ("subject_id", "session_id", "trial_id")}
    if "sample_index" in columns:
        exprs["sample_index"] = pl.col(columns["sample_index"]["source"]).cast(pl.Int64).alias("sample_index")
    if "time_s" in columns:
        entry = columns["time_s"]
        exprs["time_s"] = (pl.col(entry["source"]).cast(pl.Float64) * _S[entry["unit"]]).alias("time_s")
        time_base = "explicit_time_column"
        if hz is None:
            diffs = lazy.select(exprs["time_s"]).head(10001).collect()["time_s"].diff().drop_nulls()
            positive = diffs.filter(diffs > 0)
            if positive.is_empty():
                raise ImportBlocked("The sampling rate cannot be estimated from the timestamps; enter it.")
            hz, source = round(1.0 / float(positive.median()), 6), "estimated_from_timestamps"
    else:
        exprs["time_s"] = (pl.col(columns["sample_index"]["source"]).cast(pl.Float64) / hz).alias("time_s")
        time_base = "sample_index/sampling_hz"
    exprs["sampling_hz"] = pl.lit(float(hz)).alias("sampling_hz")
    for name in traces.CHANNELS:
        if name in columns:
            exprs[name] = (pl.col(columns[name]["source"]).cast(pl.Float64) * _FORCE[columns[name]["unit"]]).alias(name)
    ctx_i, ctx_p = context["instrument"], context["protocol"]
    instrument_id = (_unique(lazy, columns["instrument_id"]["source"], "instruments") if "instrument_id" in columns else None)         or "INST-IMP-" + _digest(ctx_i["manufacturer"], ctx_i["model"], ctx_i["serial_number"], ctx_i["calibration_status"],
                                 ctx_i["calibration_date"], traces.FAMILY)
    protocol_id = (_unique(lazy, columns["protocol_id"]["source"], "protocols") if "protocol_id" in columns else None)         or "PROT-IMP-" + _digest(ctx_p["name"], ctx_p["version"], traces.FAMILY, hz)
    exprs["instrument_id"] = pl.lit(instrument_id).alias("instrument_id")
    exprs["protocol_id"] = pl.lit(protocol_id).alias("protocol_id")
    facts = {"sampling_hz": hz, "sampling_source": source, "time_base": time_base,
             "instrument_id": instrument_id, "protocol_id": protocol_id}
    return lazy.select(list(exprs.values())), facts


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
    return {"source": source, "instrument": instrument, "protocol": protocol, "fields": dict(fields)}


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
    """Normalize one file and run the existing QC. Registers/ingests but does not admit.

    Trial-level tables are normalized in memory (size-capped); sample-level recordings are streamed to Parquet.
    """
    if plan["state"] == "UNSUPPORTED":
        raise ImportBlocked(plan.get("reason", "Unsupported file."))
    if plan["state"] != "READY":
        raise ImportBlocked("Review required before import: " + "; ".join(plan["needs"] + plan["ambiguities"]))
    path = Path(plan["path"])
    raw_sha = _sha256(path)
    if raw_sha != plan["raw_sha256"]:
        raise ImportBlocked("The file changed after it was reviewed; probe it again.")
    mapping, family = plan["mapping"], plan["mapping"]["family"]
    ctx_i, ctx_p, src = context["instrument"], context["protocol"], context["source"]
    lazy, _ = open_table(path)
    lazy = _records(lazy)
    if schema_fingerprint(lazy.collect_schema()) != plan["schema_fingerprint"]:
        raise ImportBlocked("The file schema changed after it was reviewed.")
    work = paths()["tmp"] / f"import-{uuid.uuid4().hex}"
    work.mkdir(parents=True)
    try:
        name = f"{path.stem}.normalized.parquet"
        normalized_path = work / name
        units = CANONICAL_UNITS[family]
        try:
            if family == traces.FAMILY:
                stream, facts = _normalize_trace(lazy, mapping, context)
                stream.sink_parquet(normalized_path, compression="zstd")
                sampling, instrument_id, protocol_id = facts["sampling_hz"], facts["instrument_id"], facts["protocol_id"]
            else:
                if plan["size_bytes"] > MAX_FILE_BYTES:
                    raise ImportBlocked("Trial-level table exceeds the size limit.")
                normalized = normalize(lazy.collect(), mapping)
                sampling = _unique(normalized.lazy(), "sampling_hz", "sampling rates") if "sampling_hz" in normalized.columns else None
                instrument_id = _unique(normalized.lazy(), "instrument_id", "instruments") if "instrument_id" in normalized.columns else None
                instrument_id = instrument_id or "INST-IMP-" + _digest(ctx_i["manufacturer"], ctx_i["model"], ctx_i["serial_number"],
                                                                    ctx_i["calibration_status"], ctx_i["calibration_date"], family)
                protocol_id = (_unique(normalized.lazy(), "protocol_id", "protocols") if "protocol_id" in normalized.columns else None)                     or "PROT-IMP-" + _digest(ctx_p["name"], ctx_p["version"], family, sampling)
                normalized = normalized.with_columns(*(pl.lit(v).alias(k) for k, v in (("instrument_id", instrument_id), ("protocol_id", protocol_id))
                                                       if k not in normalized.columns))
                normalized.write_parquet(normalized_path, compression="zstd")
                facts = {}
        except ImportBlocked:
            raise
        except Exception as error:
            raise ImportBlocked(f"The data could not be normalized ({type(error).__name__}); check that mapped columns hold numbers.") from error
        metadata: dict[str, Any] = {"units": units, "instrument_default": instrument_id, "protocol_default": protocol_id,
                                    "import": {"adapter": plan["adapter"], "adapter_version": ADAPTER_VERSION,
                                               "raw_sha256": raw_sha, "schema_fingerprint": plan["schema_fingerprint"]}}
        if family == traces.FAMILY:
            metadata.update(sampling_hz=facts["sampling_hz"], sampling_source=facts["sampling_source"], time_base=facts["time_base"])
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

        content_sha = _sha256(normalized_path)
        duplicate_of = next((a["id"] for a in admission.list_source_artifacts() if a["source_id"] == src["id"]
                             and a["content_hash_sha256"] == content_sha and a["original_filename"] != name), None)
        artifact = admission.ingest_source_file(src["id"], normalized_path, "one_click_import")
        normalized_rows = pq.ParquetFile(normalized_path).metadata.num_rows
    finally:
        shutil.rmtree(work, ignore_errors=True)
    raw_dir = paths()["sources"] / src["id"] / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_copy = raw_dir / f"{raw_sha[:12]}-{path.name}"
    if not raw_copy.exists():
        shutil.copyfile(path, raw_copy)
    validate = {"CMJ_FORCE_PLATFORM": admission.validate_cmj, "SPRINT_TIMING": admission.validate_sprint,
                traces.FAMILY: traces.validate_trace}[family]
    quality = validate(artifact, metadata)
    rights = (admission.get_source(src["id"]) or {}).get("rights_status", "UNVERIFIED")
    eligible = quality["status"] in ADMITTABLE and rights in {"VERIFIED", "FIXTURE_ONLY"} and duplicate_of is None
    receipt = {
        "id": "IR-" + hashlib.sha256(f"{raw_sha}:{artifact['id']}".encode()).hexdigest()[:12].upper(),
        "raw_filename": path.name, "raw_sha256": raw_sha, "raw_size_bytes": plan["size_bytes"], "raw_copy": str(raw_copy),
        "schema_fingerprint": plan["schema_fingerprint"], "columns": plan["columns"], "adapter": plan["adapter"],
        "adapter_version": ADAPTER_VERSION, "mapping": mapping, "family": family, "admission_metadata": metadata,
        "source_id": src["id"], "source_artifact_id": artifact["id"], "quality_assessment_id": quality["id"],
        "normalized_rows": normalized_rows, "dropped_columns": [c["name"] for c in plan["columns"] if c["name"] not in
                                                                 {e["source"] for e in mapping["columns"].values()}],
    }
    previous = next((r for r in _receipts() if r["id"] == receipt["id"]), None)
    receipt.update(created_at=previous["created_at"] if previous else utc_now(), decision=previous["decision"] if previous else "STAGED")
    receipt["admission_record_id"] = previous.get("admission_record_id") if previous else None
    _save_receipt(receipt)
    return {"receipt": receipt, "artifact": artifact, "quality": quality, "rights_status": rights, "eligible": eligible,
            "duplicate_of": duplicate_of, "synthetic_only": rights == "FIXTURE_ONLY"}


def expected_snapshot_id(staged: dict[str, Any]) -> str:
    """The immutable snapshot identity admission will create (deterministic from artifact + family)."""
    return admission._snapshot_id(staged["artifact"], staged["receipt"]["family"])


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
        if preset["mapping"].get("family") != plan.get("mapping", {}).get("family"):
            continue  # a preset for another measurement family is unrelated, not drifted
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
